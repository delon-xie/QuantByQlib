"""
yfinance → Qlib 格式数据采集 Worker
从 Yahoo Finance 批量下载美股 OHLCV 数据，直接写入 Qlib 二进制格式，
无需 qlib.init()，支持追加（保留历史数据）和新建两种模式。

二进制格式：[start_idx: float32][v0: float32][v1: float32]...
  - start_idx：该股票在日历中的起始偏移量（对应 calendars/day.txt 的行号）
  - v0..vN：OHLCV / factor 值（float32，NaN 表示无数据）
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from core.qlibhelper import _find_data_dir

import numpy as np
import pandas as pd
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtCore import QEventLoop
import yfinance as yf
def _find_us_data_dir() -> Path:
    """自动探测美股 Qlib 数据目录（与 qlib_manager 保持一致）"""
    candidates = [
        Path.home() / ".qlib" / "qlib_data",
        Path.home() / ".qlib" / "qlib_data" / "us_data",
    ]
    for path in candidates:
        features = path / "features"
        if not features.exists():
            continue
        for d in features.iterdir():
            if (d.is_dir()
                    and d.name.replace("-", "").replace(".", "").isalpha()
                    and not any(d.name.lower().startswith(p) for p in ("sh", "sz", "bj"))):
                return path
    return candidates[0]


QLIB_DATA_DIR = _find_data_dir()
# yfinance 下载每批的股票数量（过大会超时）
BATCH_SIZE = 50
# 获取交易日历用的参考指数
CALENDAR_REF_TICKER = "^GSPC"
# 需要写入的字段（与现有 features/ 目录一致）
FIELDS = ["open", "high", "low", "close", "volume", "factor"]


class CollectorSignals(QObject):
    """Worker 信号（必须继承 QObject）"""
    progress  = pyqtSignal(int, str)    # (0-100, 状态描述)
    log_line  = pyqtSignal(str)         # 实时日志行
    completed = pyqtSignal(bool, str)   # (成功?, 最终消息)
    error     = pyqtSignal(str)         # 错误消息


class YFinanceCollectorWorker(QRunnable):
    """
    yfinance → Qlib 格式数据采集 Worker

    scope: "sp500" | "nasdaq100"
    start_date: 历史数据起始日期（仅对全新安装生效，追加模式自动从现有数据末尾续接）
    """

    def __init__(self, scope: str = "sp500", start_date: str = "2010-01-01"):
        super().__init__()
        self.scope = scope
        self.start_date = start_date
        self.signals = CollectorSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @pyqtSlot()
    def run(self) -> None:
        try:
            self._run_collect()
            self.signals.log_line.emit("采集完成")
        except Exception as e:
            self.signals.log_line.emit(f"yfinance 采集 Worker 异常：{e}")
            self.signals.error.emit(str(e))
        finally:
            # ✅ 延迟删除，确保信号已派发
            #QTimer.singleShot(0, self.deleteLater)
            pass

    # ── 主流程 ──────────────────────────────────────────────

    def _run_collect(self) -> None:
        self._log("[INFO] === yfinance 数据采集开始 ===")
        self._progress(2, "准备中...")

        # 1. 读取现有日历
        cal_dates, cal_index = self._load_calendar()
        old_cal_end = cal_dates[-1] if cal_dates else date(2000, 1, 1)
        self._log(f"[INFO] 现有日历：{cal_dates[0]} ~ {old_cal_end}，共 {len(cal_dates)} 个交易日")

        if self._cancelled:
            return self._cancel_exit()

        # 2. 获取最新交易日历（从现有末尾之后到今天）
        self._progress(5, "获取交易日历...")
        fetch_start = old_cal_end + timedelta(days=1)
        today = date.today()
        new_trading_days = self._fetch_trading_days(fetch_start, today)

        if not new_trading_days:
            self._log("[INFO] 数据已是最新，无需追加")
            self.signals.completed.emit(True, "数据已是最新，无需采集")
            return

        self._log(f"[INFO] 新增交易日：{new_trading_days[0]} ~ {new_trading_days[-1]}，共 {len(new_trading_days)} 天")

        if self._cancelled:
            return self._cancel_exit()

        # 3. 合并日历，建立日期→index 映射
        all_dates = cal_dates + new_trading_days
        date_to_idx = {d: i for i, d in enumerate(all_dates)}
        # 新日期的 index 从 len(cal_dates) 开始
        new_start_idx = len(cal_dates)

        # 4. 获取股票列表
        self._progress(8, "加载股票列表...")
        tickers = self._get_tickers()
        self._log(f"[INFO] 采集范围：{self.scope.upper()}，共 {len(tickers)} 支")

        if self._cancelled:
            return self._cancel_exit()

        # 5. 分批下载 + 写入
        total_batches = math.ceil(len(tickers) / BATCH_SIZE)
        written_count = 0
        failed_tickers = []

        for batch_idx, batch_start in enumerate(range(0, len(tickers), BATCH_SIZE)):
            if self._cancelled:
                return self._cancel_exit()

            batch = tickers[batch_start: batch_start + BATCH_SIZE]
            pct = 10 + int(85 * batch_idx / total_batches)
            self._progress(pct, f"下载第 {batch_idx+1}/{total_batches} 批（{batch[0]}...）")
            self._log(f"[INFO] 批次 {batch_idx+1}/{total_batches}：{', '.join(batch[:5])}{'...' if len(batch)>5 else ''}")

            try:
                batch_written, batch_failed = self._process_batch(
                    batch, new_trading_days, date_to_idx, new_start_idx, cal_dates, cal_index
                )
                written_count += batch_written
                failed_tickers.extend(batch_failed)
            except Exception as e:
                self._log(f"[WARN] 批次 {batch_idx+1} 异常：{e}")

        if self._cancelled:
            return self._cancel_exit()

        # 6. 更新日历文件
        self._progress(97, "更新日历...")
        self._extend_calendar(new_trading_days)
        self._log(f"[INFO] 日历已更新至 {new_trading_days[-1]}")

        # 7. 更新 instruments 文件
        self._update_instruments(tickers, new_trading_days[-1])

        # 8. 重新 init Qlib
        self._progress(99, "重新初始化 Qlib...")
        try:
            from data.qlib_manager import init_qlib
            init_qlib()
            self._log("[INFO] Qlib 已重新初始化")
        except Exception as e:
            self._log(f"[WARN] Qlib 重新初始化失败：{e}")

        self._progress(100, "完成")
        summary = (
            f"采集完成：写入 {written_count} 支股票，"
            f"数据覆盖至 {new_trading_days[-1]}"
        )
        if failed_tickers:
            summary += f"，{len(failed_tickers)} 支真正失败（无历史数据且无法下载）"
            self._log(f"[WARN] 失败 ticker 列表：{failed_tickers}")
        self._log(f"[INFO] {summary}")
        self.signals.completed.emit(True, summary)

    # ── 日历处理 ─────────────────────────────────────────────

    def _load_calendar(self) -> tuple[list[date], dict[date, int]]:
        """读取现有 calendars/day.txt，返回 (有序日期列表, 日期→index 字典)"""
        cal_file = QLIB_DATA_DIR / "calendars" / "day.txt"
        if not cal_file.exists():
            return [], {}
        lines = cal_file.read_text().strip().split("\n")
        dates = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    dates.append(datetime.strptime(line, "%Y-%m-%d").date())
                except ValueError:
                    pass
        date_to_idx = {d: i for i, d in enumerate(dates)}
        return dates, date_to_idx

    def _fetch_trading_days(self, start: date, end: date) -> list[date]:
        """通过下载参考指数获取美股交易日列表"""
        if start > end:
            return []
        try:
            # 保持 threads 设置 和 _process_batch 中 download 一致
            # 否则容易造成崩溃
            df = yf.download(
                CALENDAR_REF_TICKER,
                start=f"{start}", #.strftime("%Y-%m-%d"),
                end=f"{end}", #.strftime("%Y-%m-%d"),
                auto_adjust=False,
                progress=False,
                threads=True,
            )
            if df.empty:
                self.signals.log_line.emit("获取空日历数据")
                return []
            
            trading_days = sorted([ts.date() for ts in df.index])
            self.signals.log_line.emit(f"获取日历天数:{len(trading_days)}")
            return trading_days
        except Exception as e:
            self.signals.log_line.emit(f"获取交易日历失败：{e}")
            
        return []

    def _extend_calendar(self, new_dates: list[date]) -> None:
        """将新交易日追加到 calendars/day.txt（自动去重）"""
        cal_file = QLIB_DATA_DIR / "calendars" / "day.txt"
        if not cal_file.exists():
            return
        # 读取已有日期集合，避免写入重复行
        existing = set(cal_file.read_text().strip().split("\n"))
        to_write = [d for d in new_dates if f'{d}' not in existing]
        if not to_write:
            return
        with cal_file.open("a", encoding="utf-8") as f:
            for d in to_write:
                f.write(f"\n{d}") #.strftime('%Y-%m-%d')

    # ── 股票列表 ─────────────────────────────────────────────

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        """标准化 ticker：将 Qlib 格式（BRK.B）转换为 yfinance 格式（BRK-B）"""
        return ticker.replace(".", "-")

    def _get_tickers(self) -> list[str]:
        """从 instruments/ 文件读取股票列表，如不存在则使用内置列表"""
        inst_file = QLIB_DATA_DIR / "instruments" / f"{self.scope}.txt"
        if inst_file.exists():
            lines = inst_file.read_text().strip().split("\n")
            tickers = []
            for line in lines:
                parts = line.split("\t")
                if parts:
                    t = self._normalize_ticker(parts[0].strip().upper())
                    if t and not t.startswith("^"):
                        tickers.append(t)
            if tickers:
                return tickers

        # 内置备用列表（Nasdaq 100 核心成分）
        if self.scope == "nasdaq100":
            return _NASDAQ100_TICKERS
        return _SP500_SUBSET_TICKERS

    # ── 批量下载 + 写入 ──────────────────────────────────────

    def _process_batch(
        self,
        tickers: list[str],
        new_dates: list[date],
        date_to_idx: dict[date, int],
        new_start_idx: int,
        existing_cal: list[date],
        existing_cal_index: dict[date, int],
    ) -> tuple[int, list[str]]:
        """
        下载一批股票数据并写入 Qlib bin 文件
        返回 (写入成功数, 失败 ticker 列表)
        """
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")

        # 确定下载的时间范围
        # 对于追加模式：只需要 new_dates 对应的数据
        # 对于全新 ticker：需要从 start_date 开始
        dl_start = self.start_date
        dl_end = f'{date.today()}' #.strftime("%Y-%m-%d")

        try:
            raw = yf.download(
                tickers,
                start=dl_start,
                end=dl_end,
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            self.signals.log_line.emit(f"批量下载失败：{e}")
            return 0, tickers

        written = 0
        failed = []
        skipped_delisted = 0

        for ticker in tickers:
            if self._cancelled:
                break
            try:
                # 检查该 ticker 是否已有本地数据（退市股票）
                feat_dir = QLIB_DATA_DIR / "features" / ticker.lower()
                close_bin = feat_dir / "close.day.bin"
                has_existing_data = close_bin.exists()

                # 提取单个 ticker 的 DataFrame
                # 注意：yfinance group_by='ticker' 时，无论单支还是多支，
                # MultiIndex 的 level 0 均为 ticker，level 1 为字段名
                if isinstance(raw.columns, pd.MultiIndex):
                    ticker_in_raw = ticker in raw.columns.get_level_values(0)
                    if ticker_in_raw:
                        df = raw[ticker].copy()
                    else:
                        df = pd.DataFrame()
                else:
                    # 极少数情况：单 ticker 且 yfinance 返回普通列（字段名为列名）
                    ticker_in_raw = not raw.empty
                    df = raw.copy() if ticker_in_raw else pd.DataFrame()

                # 退市/被收购股票：yfinance 在追加窗口内无新数据属正常，跳过不算失败
                if not ticker_in_raw or df.empty or df["Close"].isna().all():
                    if has_existing_data:
                        # 已有历史数据，只是无新数据（正常退市），追加 NaN 占位
                        self._append_nan_for_delisted(ticker.lower(), date_to_idx, new_start_idx)
                        skipped_delisted += 1
                        written += 1  # 算作"已处理"，不计入失败
                    else:
                        # 真正失败：无历史数据也无新数据
                        failed.append(ticker)
                    continue

                # 计算 factor = Adj Close / Close
                df = df.dropna(subset=["Close"])
                df["factor"] = df["Adj Close"] / df["Close"]
                df["factor"] = df["factor"].fillna(1.0).clip(0.01, 100.0)

                # 将日期 index 规范化为 date 对象
                df.index = pd.to_datetime(df.index).normalize()
                df.index = [ts.date() for ts in df.index]

                ok = self._write_ticker_data(
                    ticker.lower(),
                    df,
                    date_to_idx,
                    new_start_idx,
                    existing_cal,
                )
                if ok:
                    written += 1
                else:
                    # 写入返回 False 通常是追加时无新数据（已是最新），若有历史数据也不算失败
                    if has_existing_data:
                        written += 1
                    else:
                        failed.append(ticker)
            except Exception as e:
                self.signals.log_line.emit(f"{ticker} 写入失败：{e}")
                failed.append(ticker)

        if skipped_delisted:
            self.signals.log_line.emit(f"已退市/停牌跳过（有历史数据）：{skipped_delisted} 支")
        return written, failed

    def _write_ticker_data(
        self,
        ticker_lower: str,
        df: pd.DataFrame,
        date_to_idx: dict[date, int],
        new_start_idx: int,
        existing_cal: list[date],
    ) -> bool:
        """
        将单个 ticker 的数据写入 Qlib bin 文件
        - 已有 bin 文件：只追加新日期数据
        - 无 bin 文件：全量写入（从最早可用数据开始）
        返回是否成功
        """
        feat_dir = QLIB_DATA_DIR / "features" / ticker_lower
        feat_dir.mkdir(parents=True, exist_ok=True)

        # 检查现有数据的末尾 index
        close_bin = feat_dir / "close.day.bin"
        existing_end_idx: Optional[int] = None
        if close_bin.exists():
            try:
                raw_data = np.fromfile(close_bin, dtype="<f")
                if len(raw_data) >= 2:
                    start_i = int(raw_data[0])
                    existing_end_idx = start_i + len(raw_data) - 2  # 最后一个有效 index
            except Exception:
                pass

        wrote_any = False

        for field in FIELDS:
            bin_file = feat_dir / f"{field}.day.bin"

            if existing_end_idx is not None:
                # 追加模式：只写 index > existing_end_idx 的数据
                values_to_append = self._extract_new_values(
                    df, field, date_to_idx, existing_end_idx
                )
                if values_to_append is not None and len(values_to_append) > 0:
                    arr = np.array(values_to_append, dtype="<f")
                    with bin_file.open("ab") as f:
                        arr.tofile(f)
                    wrote_any = True
            else:
                # 新建模式：找到最早有效日期，计算 start_idx
                series = self._get_field_series(df, field)
                if series is None or series.empty:
                    continue
                # 找到该 ticker 在 date_to_idx 中第一个有效日期
                valid_dates = [d for d in series.index if d in date_to_idx and not pd.isna(series.get(d, float("nan")))]
                if not valid_dates:
                    continue
                first_date = min(valid_dates)
                start_idx = date_to_idx[first_date]
                # 从 first_date 开始，到数据末尾，按日历顺序填充
                all_cal_dates = existing_cal + [
                    d for d in sorted(date_to_idx.keys()) if d not in set(existing_cal)
                ]
                # 取 [start_idx:] 的所有日历日期，填充数据
                values = []
                for cal_date in sorted(date_to_idx.keys()):
                    if date_to_idx[cal_date] < start_idx:
                        continue
                    v = series.get(cal_date, float("nan"))
                    values.append(float("nan") if pd.isna(v) else float(v))

                if not values:
                    continue
                arr = np.hstack([[start_idx], values]).astype("<f")
                with bin_file.open("wb") as f:
                    arr.tofile(f)
                wrote_any = True

        return wrote_any

    def _append_nan_for_delisted(
        self,
        ticker_lower: str,
        date_to_idx: dict[date, int],
        new_start_idx: int,
    ) -> None:
        """
        为退市股票在新增交易日追加 NaN 占位，保持日历对齐。
        只追加 index >= new_start_idx 的 NaN，不修改历史数据。
        """
        feat_dir = QLIB_DATA_DIR / "features" / ticker_lower
        if not feat_dir.exists():
            return
        # 计算需要追加的 NaN 数量
        new_dates_count = sum(1 for i in date_to_idx.values() if i >= new_start_idx)
        if new_dates_count <= 0:
            return
        nan_arr = np.full(new_dates_count, np.nan, dtype="<f")
        for field in FIELDS:
            bin_file = feat_dir / f"{field}.day.bin"
            if bin_file.exists():
                with bin_file.open("ab") as f:
                    nan_arr.tofile(f)

    def _extract_new_values(
        self,
        df: pd.DataFrame,
        field: str,
        date_to_idx: dict[date, int],
        existing_end_idx: int,
    ) -> Optional[list[float]]:
        """提取 index > existing_end_idx 的新数据，按日历顺序，缺失填 NaN"""
        series = self._get_field_series(df, field)
        if series is None:
            return None

        # 找出所有 index > existing_end_idx 的日历日期
        new_dates = sorted(
            d for d, i in date_to_idx.items() if i > existing_end_idx
        )
        if not new_dates:
            return []

        values = []
        for d in new_dates:
            v = series.get(d, float("nan"))
            values.append(float("nan") if pd.isna(v) else float(v))
        return values

    @staticmethod
    def _get_field_series(df: pd.DataFrame, field: str) -> Optional[pd.Series]:
        """从 DataFrame 提取指定字段的 Series（date → value）"""
        col_map = {
            "open":   "Open",
            "high":   "High",
            "low":    "Low",
            "close":  "Close",
            "volume": "Volume",
            "factor": "factor",
        }
        col = col_map.get(field)
        if col is None or col not in df.columns:
            return None
        return df[col]

    # ── instruments 更新 ─────────────────────────────────────

    def _update_instruments(self, tickers: list[str], end_date: date) -> None:
        """更新 instruments 文件的末尾日期（all.txt 和 scope 文件）"""
        end_str = f'{end_date}' #.strftime("%Y-%m-%d")
        files_to_update = [
            QLIB_DATA_DIR / "instruments" / "all.txt",
            QLIB_DATA_DIR / "instruments" / f"{self.scope}.txt",
        ]
        ticker_set = {t.upper() for t in tickers}

        for inst_file in files_to_update:
            if not inst_file.exists():
                continue
            try:
                lines = inst_file.read_text(encoding="utf-8").strip().split("\n")
                new_lines = []
                for line in lines:
                    parts = line.split("\t")
                    if len(parts) >= 3 and parts[0].upper() in ticker_set:
                        # 更新末尾日期
                        new_lines.append(f"{parts[0]}\t{parts[1]}\t{end_str}")
                    else:
                        new_lines.append(line)
                inst_file.write_text("\n".join(new_lines), encoding="utf-8")
            except Exception as e:
                self.signals.log_line.emit(f"更新 {inst_file.name} 失败：{e}")

    # ── 辅助 ─────────────────────────────────────────────────

    def _log(self, msg: str) -> None:

        self.signals.log_line.emit(msg)

    def _progress(self, pct: int, msg: str) -> None:
        self.signals.progress.emit(pct, msg)

    def _cancel_exit(self) -> None:
        self._log("[INFO] 已取消")
        self.signals.completed.emit(False, "用户取消")


# ── 内置股票列表（备用，当 instruments 文件不存在时使用） ──────

_NASDAQ100_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
    "NFLX", "AMD", "ADBE", "QCOM", "PEP", "CSCO", "INTC", "TMUS", "AMAT", "TXN",
    "AMGN", "INTU", "HON", "SBUX", "BKNG", "ISRG", "VRTX", "LRCX", "GILD", "REGN",
    "ADI", "MU", "MDLZ", "PDD", "KDP", "PANW", "ASML", "SNPS", "CDNS", "MELI",
    "KLAC", "MAR", "ABNB", "CTAS", "ORLY", "FTNT", "WDAY", "MNST", "PYPL", "ADP",
    "MRVL", "NXPI", "PAYX", "PCAR", "ODFL", "FAST", "ROST", "CPRT", "KHC", "DDOG",
    "CEG", "FANG", "ON", "IDXX", "VRSK", "EXC", "BIIB", "XEL", "CTSH", "GEHC",
    "MRNA", "ZS", "TEAM", "DLTR", "CRWD", "ALGN", "ILMN", "MDB",   # ANSS→退市(Synopsys收购2024), WBA→私有化退市2024
    "SIRI", "ENPH", "LCID", "RIVN", "ZM", "TTD", "CDW", "OKTA", "DXCM",  # SPLK→Cisco收购退市2024
    "EBAY", "TTWO", "GFS", "NTES", "JD", "LULU", "SMCI", "DECK", "APP", "ARM",
    "CSCO", "MSTR", "COIN", "PLTR", "HOOD",  # 补充替换退市空位
]

_SP500_SUBSET_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "TSLA", "AVGO",
    "JPM", "LLY", "UNH", "V", "XOM", "MA", "COST", "HD", "PG", "JNJ",
    "WMT", "ABBV", "ORCL", "CRM", "BAC", "CVX", "KO", "MRK", "NFLX", "AMD",
    "PEP", "TMO", "ADBE", "ACN", "LIN", "MCD", "IBM", "GE", "PM", "DHR",
    "ABT", "ISRG", "CAT", "QCOM", "TXN", "GS", "SPGI", "VZ", "INTU", "NOW",
    "BKNG", "NEE", "AMGN", "RTX", "LOW", "MS", "AXP", "HON", "SYK", "PFE",
    "T", "ELV", "AMAT", "DE", "TJX", "BSX", "UNP", "BLK", "PANW", "CB",
    "VRTX", "GILD", "MMC", "LRCX", "MDLZ", "REGN", "PGR", "ADI", "MU", "C",
    "ZTS", "SBUX", "KLAC", "SNPS", "WFC", "CME", "DUK", "SO", "COP", "MCO",
    "CDNS", "ICE", "HCA", "CTAS", "USB", "NSC", "SHW", "ITW", "GD", "PSA",
] * 5  # 使用前 100 支
