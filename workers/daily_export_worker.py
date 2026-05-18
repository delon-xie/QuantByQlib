"""
每日批量导出 Worker
统一协调 F1（图表）+ F2（信号）+ F3（政体，仅周日）+ F4（回测，仅月末）+ F5（Manifest）
输出到「美股交易日记/」下各子目录。

触发方式：
  - GUI：由 portfolio_page 或新增「一键运行」按钮触发
  - 命令行：python -m workers.daily_export_worker --tickers NVDA,MSFT,...

信号 (pyqtSignal):
  progress(int, str)    — 总体进度百分比 + 状态消息
  completed(str)        — 输出根目录路径
  error(str)            — 严重错误消息
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot


class DailyExportSignals(QObject):
    progress  = pyqtSignal(int, str)   # pct, message
    completed = pyqtSignal(str)        # output root dir
    error     = pyqtSignal(str)        # fatal error


class DailyExportWorker(QRunnable):
    """
    每日导出 Worker。

    Parameters
    ----------
    tickers       : 持仓股票列表（用于 F1 图表和 F2 信号）
    strategy_keys : 要运行的策略列表（默认全部3个）；None = 跳过信号生成
    trade_date    : 信号/图表日期标签（None = 今日）
    run_charts    : 是否生成 K 线图（F1）
    run_signals   : 是否生成信号 CSV（F2）
    force_regime  : 强制运行 HMM 政体识别（默认仅周日）
    force_backtest: 强制运行月度回测（默认仅月末）
    """

    def __init__(
        self,
        tickers: list[str],
        strategy_keys: Optional[list[str]] = None,
        trade_date: Optional[date] = None,
        run_charts: bool = True,
        run_signals: bool = True,
        force_regime: bool = False,
        force_backtest: bool = False,
    ):
        super().__init__()
        self.tickers        = tickers
        self.strategy_keys  = strategy_keys  # None → 跳过信号
        self.trade_date     = trade_date or date.today()
        self.run_charts     = run_charts
        self.run_signals    = run_signals
        self.force_regime   = force_regime
        self.force_backtest = force_backtest
        self.signals        = DailyExportSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        from services.output_paths import get_root, cleanup_old_files
        from services.manifest_writer import ManifestBuilder

        d = self.trade_date
        mb = ManifestBuilder(
            run_type=self._detect_run_type(),
            tickers=self.tickers,
        )

        self._emit(2, "初始化输出目录...")
        root = get_root()

        # ── F1：K 线图表 ──────────────────────────────────────────────────
        chart_files: list[str] = []
        chart_errors: list[str] = []

        if self.run_charts and self.tickers:
            self._emit(5, f"F1 生成 K 线图表（{len(self.tickers)} 支股票）...")
            chart_files, chart_errors = self._run_charts(d, root)
            if chart_errors:
                for e in chart_errors:
                    mb.add_error(e)

            if chart_files:
                relative = [f"pics/{Path(f).name}" for f in chart_files]
                mb.set_charts(
                    status="success",
                    files=relative,
                    count=len(relative),
                )
            else:
                mb.set_charts(status="failed", reason="所有图表生成失败")
        else:
            mb.set_charts(status="skipped", reason="未配置股票或已禁用")

        # ── F1b：VPVR 筹码峰图 ────────────────────────────────────────────
        if self.run_charts and self.tickers:
            self._emit(36, f"F1b 生成 VPVR 筹码峰图（{len(self.tickers)} 支股票）...")
            vpvr_files, vpvr_errors = self._run_vpvr(d)
            for e in vpvr_errors:
                mb.add_error(e)

        # ── F2：策略信号 CSV ──────────────────────────────────────────────
        signal_files: list[str] = []

        if self.run_signals and self.strategy_keys:
            self._emit(40, f"F2 生成策略信号 CSV（{len(self.strategy_keys)} 个策略）...")
            signal_files, sig_errors = self._run_signals(d)
            for e in sig_errors:
                mb.add_error(e)

            relative_sigs = [f"signals/{Path(f).name}" for f in signal_files]
            mb.set_signals(
                status="success" if signal_files else "failed",
                files=relative_sigs,
            )
        else:
            mb.set_signals(status="skipped", reason="未配置策略或已禁用")

        # ── F3：HMM 政体（仅周日或强制）────────────────────────────────────
        is_sunday = d.weekday() == 6
        if self.force_regime or is_sunday:
            self._emit(70, "F3 运行 HMM 市场政体识别...")
            regime_path = self._run_regime(d)
            if regime_path:
                mb.set_regime(
                    status="success",
                    last_available=d.isoformat(),
                )
            else:
                mb.set_regime(status="failed", reason="HMM 运行失败")
                from services.manifest_writer import find_last_available
                last = find_last_available("regime")
                mb.set_regime(status="failed", last_available=last or "",
                              reason="HMM 运行失败")
        else:
            from services.manifest_writer import find_last_available
            last = find_last_available("regime")
            mb.set_regime(
                status="skipped",
                reason="仅周日运行",
                last_available=last or "",
            )

        # ── F4：回测绩效（仅月末或强制）────────────────────────────────────
        is_month_end = self._is_month_end(d)
        if self.force_backtest or is_month_end:
            self._emit(80, "F4 运行月度回测绩效报告...")
            bt_path = self._run_backtest(d)
            if bt_path:
                mb.set_backtest(
                    status="success",
                    last_available=d.isoformat(),
                )
            else:
                from services.manifest_writer import find_last_available
                last = find_last_available("backtest")
                mb.set_backtest(status="failed", last_available=last or "",
                                reason="回测运行失败")
        else:
            from services.manifest_writer import find_last_available
            last = find_last_available("backtest")
            mb.set_backtest(
                status="skipped",
                reason="仅月末运行",
                last_available=last or "",
            )

        # ── F5a：每日摘要 MD 报告 ─────────────────────────────────────────
        try:
            self._emit(92, "生成每日摘要 MD 报告...")
            self._write_daily_summary_md(d, signal_files)
        except Exception as e:
            logger.warning(f"[DailyExport] 每日摘要 MD 生成失败：{e}")

        # ── F5：Manifest ──────────────────────────────────────────────────
        self._emit(95, "F5 写入 Manifest...")
        mb.write()

        # ── 清理旧文件 ────────────────────────────────────────────────────
        try:
            removed = cleanup_old_files()
            if any(v > 0 for v in removed.values()):
                mb.add_warning(f"已清理旧文件：{removed}")
        except Exception as e:
            logger.warning(f"[DailyExport] 清理旧文件失败：{e}")

        self._emit(100, f"全部完成 → {root}")
        self.signals.completed.emit(str(root))

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _emit(self, pct: int, msg: str) -> None:
        logger.info(f"[DailyExport] {pct}% {msg}")
        self.signals.progress.emit(pct, msg)

    def _detect_run_type(self) -> str:
        d = self.trade_date
        if d.weekday() == 6:
            return "weekly"
        if self._is_month_end(d):
            return "monthly"
        return "daily"

    @staticmethod
    def _is_month_end(d: date) -> bool:
        """判断 d 是否为当月最后一个工作日（简单：下一天是次月）"""
        return (d + timedelta(days=1)).month != d.month

    def _run_charts(self, d: date, root: Path) -> tuple[list[str], list[str]]:
        """调用 ChartExportWorker 的同步版本逻辑，输出到 pics/"""
        from services.output_paths import get_pics_dir
        pics_dir = get_pics_dir()

        files: list[str] = []
        errors: list[str] = []

        try:
            import yfinance as yf
            import mplfinance as mpf
            import matplotlib
            matplotlib.use("Agg")   # 无头模式
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm

            _cn_font = None
            for _fname in ["PingFang HK", "PingFang SC", "STHeiti",
                           "Heiti TC", "Arial Unicode MS"]:
                try:
                    _fp = fm.FontProperties(family=_fname)
                    if fm.findfont(_fp, fallback_to_default=False):
                        _cn_font = _fp
                        plt.rcParams["font.family"] = _fname
                        break
                except Exception:
                    pass
            plt.rcParams["axes.unicode_minus"] = False

            _PERIOD_PARAMS = {
                "zoom": {"period": "180d",  "interval": "1d"},
                "day":  {"period": "130d",  "interval": "1d"},
                "week": {"period": "80wk",  "interval": "1wk"},
            }
            _TAIL  = {"day": 90, "week": 60}
            _MAV   = {
                "zoom": (5, 10, 20),
                "day":  (5, 10, 20, 30),
                "week": (5, 10, 20, 30),
            }
            _MAVCOLORS = ["#F59E0B", "#3B82F6", "#8B5CF6", "#EC4899"]
            _LABELS = {"zoom": "Zoom(20d)", "day": "Daily(90d)", "week": "Weekly(60wk)"}

            style = mpf.make_mpf_style(
                base_mpf_style="charles",
                marketcolors=mpf.make_marketcolors(
                    up="#22C55E", down="#EF4444",
                    edge="inherit", wick="inherit",
                    volume={"up": "#22C55E88", "down": "#EF444488"},
                ),
                figcolor="#FFFFFF",
                gridcolor="#E2E4EA",
                gridstyle="--",
                mavcolors=_MAVCOLORS,
            )

            date_str = d.strftime("%Y%m%d")

            for ticker in self.tickers:
                for period_key, params in _PERIOD_PARAMS.items():
                    try:
                        # 优先长桥
                        df = None
                        src = "yfinance"
                        try:
                            from data.longport_client import get_candlesticks, is_configured
                            if is_configured():
                                df = get_candlesticks(ticker, period_key)
                                if df is not None and not df.empty:
                                    src = "LongPort"
                        except Exception:
                            pass

                        if df is None or df.empty:
                            from core.app_state import get_state
                            from workers.binance_downloader import binance_download
                            reg = get_state().reg
                            if reg == "bt":
                                df = binance_download(
                                    ticker, progress=False, 
                                    auto_adjust=True,
                                    period=params["period"], 
                                    interval=params["interval"],
                                    threads=True,
                                )
                            else:
                                import yfinance as yf
                                from core.qlibhelper import normalize_cn_tickers
                                if reg == "cn":
                                    ticker = normalize_cn_tickers(ticker)[0]
                                # yfinance 一次下载所有 ticker，速度远快于逐一下载
                                # tickers_str = " ".join(tickers)
                                df = yf.download(
                                    ticker, progress=False, 
                                    auto_adjust=True,
                                    period=params["period"], 
                                    interval=params["interval"],
                                    threads=True,
                                )

                            if df is not None and not df.empty:
                                if hasattr(df.columns, "levels"):
                                    df.columns = df.columns.get_level_values(0)
                                df.index.name = "Date"
                                tail_n = _TAIL.get(period_key)
                                if tail_n:
                                    df = df.tail(tail_n)

                        if df is None or df.empty:
                            errors.append(f"{ticker} {period_key} 无数据")
                            continue

                        title  = f"{ticker}  {_LABELS[period_key]}  [{src}]"
                        mav    = _MAV[period_key]
                        fig, axes = mpf.plot(
                            df, type="candle", style=style,
                            title=title, volume=True, mav=mav,
                            returnfig=True, figsize=(14, 9), tight_layout=True,
                        )

                        # zoom：xlim 限制显示最后20根，确保 MA20 正确显示
                        if period_key == "zoom":
                            n = len(df)
                            for ax in axes:
                                ax.set_xlim(n - 20 - 0.5, n - 0.5)
                                ax.autoscale_view()

                        if _cn_font:
                            for ax in fig.get_axes():
                                for lbl in ax.get_xticklabels() + ax.get_yticklabels():
                                    lbl.set_fontproperties(_cn_font)

                        fname = f"{ticker}_{period_key}_{date_str}.png"
                        save_path = pics_dir / fname
                        fig.savefig(str(save_path), dpi=100, bbox_inches="tight")
                        plt.close(fig)
                        files.append(str(save_path))
                        self._emit(
                            5 + int(len(files) / (len(self.tickers) * 3) * 30),
                            f"图表已保存：{fname}"
                        )

                    except Exception as e:
                        msg = f"{ticker} {period_key} 图表生成失败：{e}"
                        logger.warning(f"[DailyExport] {msg}")
                        errors.append(msg)

        except Exception as e:
            errors.append(f"图表模块初始化失败：{e}")
            logger.error(f"[DailyExport] 图表模块异常：{e}")

        return files, errors

    def _run_signals(self, d: date) -> tuple[list[str], list[str]]:
        """对每个 strategy_key 运行选股并导出规范化 CSV"""
        from services.signal_exporter import export_signals, export_signals_empty
        from screening.stock_screener import StockScreener

        files: list[str] = []
        errors: list[str] = []
        screener = StockScreener()

        for i, sk in enumerate(self.strategy_keys or []):
            try:
                self._emit(
                    40 + int(i / len(self.strategy_keys) * 25),
                    f"运行策略信号：{sk}..."
                )
                results = screener.run(
                    strategy_key=sk,
                    universe=None,  # 使用 Qlib 自动获取的宇宙
                )
                if results:
                    p = export_signals(sk, results, trade_date=d)
                else:
                    p = export_signals_empty(sk, trade_date=d)
                files.append(str(p))

            except Exception as e:
                msg = f"策略 {sk} 信号生成失败：{e}"
                logger.error(f"[DailyExport] {msg}")
                errors.append(msg)
                try:
                    p = export_signals_empty(sk, trade_date=d)
                    files.append(str(p))
                except Exception:
                    pass

        return files, errors

    def _run_vpvr(self, d: date) -> tuple[list[str], list[str]]:
        """
        生成 Volume Profile Visible Range (VPVR) 筹码峰图。
        数据：252 个交易日日线 OHLCV（约 1 年）
        价格区间：(High-Low) / 100 bins，按 (H+L+C)/3 典型价聚合成交量
        输出：pics/{TICKER}_vpvr_{YYYYMMDD}.png，与 K 线图同目录
        """
        from services.output_paths import get_pics_dir
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import matplotlib.font_manager as fm
        import numpy as np
        import yfinance as yf
        import pandas as pd

        pics_dir = get_pics_dir()
        date_str = d.strftime("%Y%m%d")
        files: list[str] = []
        errors: list[str] = []

        # 中文字体
        _cn_font = None
        for _fname in ["PingFang HK", "PingFang SC", "STHeiti",
                       "Heiti TC", "Arial Unicode MS"]:
            try:
                _fp = fm.FontProperties(family=_fname)
                if fm.findfont(_fp, fallback_to_default=False):
                    _cn_font = _fp
                    plt.rcParams["font.family"] = _fname
                    break
            except Exception:
                pass
        plt.rcParams["axes.unicode_minus"] = False

        for ticker in self.tickers:
            try:
                # ── 1. 获取数据（252 交易日 ≈ 1 年）─────────────────────
                df = None
                try:
                    from data.longport_client import get_candlesticks, is_configured
                    if is_configured():
                        df = get_candlesticks(ticker, "day")  # 130d，够用
                except Exception:
                    pass

                if df is None or df.empty:
                    from core.app_state import get_state
                    from workers.binance_downloader import binance_download
                    reg = get_state().reg
                    if reg == "bt":
                        raw = binance_download(
                            ticker, period="252d", 
                            interval="1d",
                            progress=False, 
                            auto_adjust=True,
                            threads=True,
                        )
                    else:
                        import yfinance as yf
                        from core.qlibhelper import normalize_cn_tickers
                        if reg == "cn":
                            ticker = normalize_cn_tickers(ticker)[0]
                        # yfinance 一次下载所有 ticker，速度远快于逐一下载
                        # tickers_str = " ".join(tickers)
                        raw = yf.download(
                            ticker, period="252d", 
                            interval="1d",
                            progress=False, 
                            auto_adjust=True,
                            threads=True,
                        )

                    if raw is not None and not raw.empty:
                        if hasattr(raw.columns, "levels"):
                            raw.columns = raw.columns.get_level_values(0)
                        raw.index.name = "Date"
                        df = raw

                if df is None or df.empty or len(df) < 10:
                    errors.append(f"{ticker} vpvr 无数据")
                    continue

                # ── 2. Volume Profile 计算 ────────────────────────────────
                # 典型价（Typical Price）= (H + L + C) / 3
                hi = df["High"].astype(float)
                lo = df["Low"].astype(float)
                cl = df["Close"].astype(float)
                vol = df["Volume"].astype(float)
                tp = (hi + lo + cl) / 3.0

                price_min = lo.min()
                price_max = hi.max()
                n_bins = 100
                bins = np.linspace(price_min, price_max, n_bins + 1)
                bin_centers = (bins[:-1] + bins[1:]) / 2

                # 每根 K 线按典型价落入 bin，成交量归属该 bin
                bin_idx = np.digitize(tp.values, bins) - 1
                bin_idx = np.clip(bin_idx, 0, n_bins - 1)

                vol_profile = np.zeros(n_bins)
                for i, v in zip(bin_idx, vol.values):
                    vol_profile[i] += v

                # ── 3. 关键价位 ───────────────────────────────────────────
                poc_idx   = int(np.argmax(vol_profile))          # Point of Control
                poc_price = bin_centers[poc_idx]

                cum_vol   = np.cumsum(vol_profile)
                total_vol = cum_vol[-1]
                val_lvl   = 0.0  # Value Area Low  (70% 以下边界)
                vah_lvl   = 0.0  # Value Area High (70% 以上边界)

                # Value Area = 中心向两侧扩展到 70% 总成交量
                va_target = total_vol * 0.70
                lo_idx, hi_idx = poc_idx, poc_idx
                va_vol = vol_profile[poc_idx]
                while va_vol < va_target:
                    can_lo = lo_idx > 0
                    can_hi = hi_idx < n_bins - 1
                    if not can_lo and not can_hi:
                        break
                    add_lo = vol_profile[lo_idx - 1] if can_lo else 0
                    add_hi = vol_profile[hi_idx + 1] if can_hi else 0
                    if add_lo >= add_hi and can_lo:
                        lo_idx -= 1
                        va_vol += vol_profile[lo_idx]
                    elif can_hi:
                        hi_idx += 1
                        va_vol += vol_profile[hi_idx]
                    else:
                        lo_idx -= 1
                        va_vol += vol_profile[lo_idx]
                val_lvl = bin_centers[lo_idx]
                vah_lvl = bin_centers[hi_idx]

                # 当前价（最后收盘）
                current_price = float(cl.iloc[-1])
                va_pct = va_vol / total_vol * 100

                # ── 4. 绘图 ───────────────────────────────────────────────
                BG      = "#0D1117"
                AX_BG   = "#161B22"
                RED     = "#EF4444"
                GREEN   = "#22C55E"
                YELLOW  = "#FACC15"
                PINK    = "#EC4899"
                GRAY    = "#6B7280"
                WHITE   = "#F0F6FC"

                fig = plt.figure(figsize=(16, 10), facecolor=BG)
                # 左：K 线迷你图；右：Volume Profile 横柱
                gs = fig.add_gridspec(2, 2,
                                      width_ratios=[3, 1],
                                      height_ratios=[3, 1],
                                      hspace=0.04, wspace=0.02)
                ax_price  = fig.add_subplot(gs[0, 0])  # K线
                ax_vol    = fig.add_subplot(gs[1, 0], sharex=ax_price)  # 成交量
                ax_vp     = fig.add_subplot(gs[:, 1])  # Volume Profile

                for ax in [ax_price, ax_vol, ax_vp]:
                    ax.set_facecolor(AX_BG)
                    ax.tick_params(colors=GRAY, labelsize=9)
                    for spine in ax.spines.values():
                        spine.set_edgecolor("#30363D")

                # K 线（简化为收盘价折线 + 蜡烛影线）
                x = np.arange(len(df))
                ax_price.set_xlim(-0.5, len(df) - 0.5)

                up_mask   = cl.values >= df["Open"].astype(float).values
                down_mask = ~up_mask

                # 影线
                ax_price.vlines(x[up_mask],   lo.values[up_mask],   hi.values[up_mask],
                                color=GREEN, linewidth=0.8, alpha=0.8)
                ax_price.vlines(x[down_mask], lo.values[down_mask], hi.values[down_mask],
                                color=RED,   linewidth=0.8, alpha=0.8)

                # 实体
                body_w = 0.6
                for i in x:
                    o = float(df["Open"].iloc[i])
                    c = float(cl.iloc[i])
                    color = GREEN if c >= o else RED
                    ax_price.bar(i, abs(c - o), bottom=min(o, c),
                                 width=body_w, color=color, alpha=0.9)

                # MA20 / MA60
                for period, color, label in [(20, "#F59E0B", "MA20"), (60, "#8B5CF6", "MA60")]:
                    ma = cl.rolling(period).mean()
                    ax_price.plot(x, ma.values, color=color,
                                  linewidth=1.2, label=label, alpha=0.9)

                # 水平线：POC / VAH / VAL
                ax_price.axhline(poc_price, color=YELLOW,   linewidth=1.2, linestyle="-",  alpha=0.9,
                                 label=f"POC ${poc_price:.1f}")
                ax_price.axhline(vah_lvl,   color=PINK,     linewidth=1.0, linestyle="--", alpha=0.8)
                ax_price.axhline(val_lvl,   color=GRAY,     linewidth=1.0, linestyle="--", alpha=0.7)

                # 右侧价格标签
                ax_price.text(len(df) - 0.3, vah_lvl, f"VAH\n${vah_lvl:.1f}",
                              color=PINK,   fontsize=7, va="center", ha="left")
                ax_price.text(len(df) - 0.3, val_lvl, f"VAL\n${val_lvl:.1f}",
                              color=GRAY,   fontsize=7, va="center", ha="left")
                ax_price.text(len(df) - 0.3, poc_price, f"POC ${poc_price:.1f}",
                              color=YELLOW, fontsize=7, va="center", ha="left")

                ax_price.set_ylabel("价格 ($)", color=WHITE, fontsize=10)
                ax_price.yaxis.label.set_color(WHITE)
                ax_price.tick_params(axis="x", labelbottom=False)
                ax_price.legend(loc="upper left", fontsize=8,
                                facecolor=AX_BG, edgecolor="#30363D",
                                labelcolor=WHITE, framealpha=0.8)

                # X 轴日期刻度（间隔约 20 根）
                step = max(1, len(df) // 8)
                xticks = x[::step]
                xlabels = [str(df.index[i])[:10] if i < len(df) else "" for i in xticks]
                ax_vol.set_xticks(xticks)
                ax_vol.set_xticklabels(xlabels, rotation=30, ha="right", fontsize=8)

                # 成交量
                vol_colors = [GREEN if c >= o else RED
                              for c, o in zip(cl.values, df["Open"].astype(float).values)]
                ax_vol.bar(x, vol.values, color=vol_colors, alpha=0.7, width=0.8)
                ax_vol.set_ylabel("成交量", color=WHITE, fontsize=9)
                ax_vol.yaxis.label.set_color(WHITE)

                # Volume Profile 横柱（右侧）
                bar_colors = []
                for i, (bc, bv) in enumerate(zip(bin_centers, vol_profile)):
                    if i == poc_idx:
                        bar_colors.append(YELLOW)
                    elif lo_idx <= i <= hi_idx:
                        bar_colors.append(RED if bc < poc_price else "#EF444488")
                    else:
                        bar_colors.append(GREEN if bc > current_price else "#6B728088")

                ax_vp.barh(bin_centers, vol_profile,
                           height=(bins[1] - bins[0]) * 0.85,
                           color=bar_colors, alpha=0.9)

                # VP 水平线
                ax_vp.axhline(poc_price,     color=YELLOW, linewidth=1.2, linestyle="-")
                ax_vp.axhline(vah_lvl,       color=PINK,   linewidth=1.0, linestyle="--", alpha=0.8)
                ax_vp.axhline(val_lvl,       color=GRAY,   linewidth=1.0, linestyle="--", alpha=0.7)
                ax_vp.axhline(current_price, color=WHITE,  linewidth=0.8, linestyle=":",  alpha=0.6)

                # VP 标签
                max_vol = vol_profile.max()
                ax_vp.text(max_vol * 1.02, poc_price, f"POC\n${poc_price:.1f}",
                           color=YELLOW, fontsize=7, va="center")
                ax_vp.text(max_vol * 1.02, vah_lvl, f"高\n${vah_lvl:.1f}",
                           color=PINK,   fontsize=7, va="center")
                ax_vp.text(max_vol * 1.02, val_lvl, f"低\n${val_lvl:.1f}",
                           color=GRAY,   fontsize=7, va="center")

                ax_vp.set_xlabel("成交量", color=WHITE, fontsize=9)
                ax_vp.xaxis.label.set_color(WHITE)
                ax_vp.tick_params(axis="y", labelleft=False)
                ax_vp.yaxis.set_tick_params(labelright=True, labelsize=8)
                ax_vp.yaxis.tick_right()
                ax_vp.set_ylim(price_min * 0.998, price_max * 1.002)

                # 标题
                pct_from_poc = (current_price - poc_price) / poc_price * 100
                sign = "+" if pct_from_poc >= 0 else ""
                title = (
                    f"NVDA  筹码分布(VPVR)  {date_str}  （近{len(df)}交易日）"
                    .replace("NVDA", ticker)
                )
                fig.suptitle(title, color=WHITE, fontsize=13, fontweight="bold", y=0.98)

                # 底部统计信息
                stats = (
                    f"POC: ${poc_price:.2f}  |  VAH: ${vah_lvl:.2f}  |  VAL: ${val_lvl:.2f}  |  "
                    f"VA占比: {va_pct:.1f}%  |  现价距POC: {sign}{pct_from_poc:.1f}%  |  "
                    f"现价距VAL: {(current_price - val_lvl) / val_lvl * 100:+.1f}%"
                )
                fig.text(0.5, 0.01, stats, ha="center", color=GRAY, fontsize=9)

                # 保存
                fname = f"{ticker}_vpvr_{date_str}.png"
                save_path = pics_dir / fname
                fig.savefig(str(save_path), dpi=120, bbox_inches="tight",
                            facecolor=BG, edgecolor="none")
                plt.close(fig)
                files.append(str(save_path))
                self._emit(
                    36 + int(len(files) / len(self.tickers) * 4),
                    f"VPVR 已保存：{fname}"
                )

            except Exception as e:
                msg = f"{ticker} vpvr 图表生成失败：{e}"
                logger.warning(f"[DailyExport] {msg}")
                errors.append(msg)

        return files, errors

    def _run_regime(self, d: date) -> Optional[Path]:
        try:
            from services.hmm_regime import run_regime_detection
            return run_regime_detection(trade_date=d)
        except Exception as e:
            logger.error(f"[DailyExport] HMM 政体识别失败：{e}")
            return None

    def _write_daily_summary_md(self, d: date, signal_files: list[str]) -> None:
        """读取最新信号 CSV，生成每日摘要 MD 报告"""
        import pandas as pd
        from services.report_writer import ReportWriter

        # 尝试读取最新的信号 CSV
        signals_df = None
        strategy_name = ""
        if signal_files:
            latest_csv = signal_files[-1]
            try:
                signals_df = pd.read_csv(latest_csv, encoding="utf-8-sig")
                strategy_name = Path(latest_csv).stem  # e.g. strategy2_20260318
            except Exception as e:
                logger.debug(f"[DailyExport] 读取信号 CSV 失败：{e}")

        # 尝试读取最新的 HMM 政体信息
        regime_info = None
        try:
            from services.output_paths import get_regime_dir
            regime_dir = get_regime_dir()
            regime_files = sorted(regime_dir.glob("hmm_regime_*.json"), reverse=True)
            if regime_files:
                import json
                with open(regime_files[0], "r", encoding="utf-8") as f:
                    regime_info = json.load(f)
        except Exception as e:
            logger.debug(f"[DailyExport] 读取政体文件失败：{e}")

        writer = ReportWriter()
        path = writer.save_daily_summary(
            signals_df=signals_df,
            regime_info=regime_info,
            trade_date=d,
            strategy_name=strategy_name,
        )
        logger.info(f"[DailyExport] 每日摘要已保存：{path}")

    def _run_backtest(self, d: date) -> Optional[Path]:
        try:
            from services.backtest_reporter import run_backtest_report
            return run_backtest_report(
                trade_date=d,
                progress_cb=lambda pct, msg: self._emit(
                    80 + int(pct * 0.12), msg
                ),
            )
        except Exception as e:
            logger.error(f"[DailyExport] 回测报告生成失败：{e}")
            return None


# ── 命令行入口 ────────────────────────────────────────────────────────────────

def _cli_main() -> None:
    """
    命令行使用：
      python -m workers.daily_export_worker --tickers NVDA,MSFT,GOOG
      python -m workers.daily_export_worker --tickers NVDA --force-regime --force-backtest
    """
    import argparse
    from PyQt6.QtWidgets import QApplication

    parser = argparse.ArgumentParser(description="QuantByQlib 每日数据导出")
    parser.add_argument("--tickers",        required=True,
                        help="逗号分隔的股票列表，如 NVDA,MSFT,GOOG")
    parser.add_argument("--strategies",     default="deep_learning,intraday_profit,growth_stocks",
                        help="逗号分隔的策略 key 列表")
    parser.add_argument("--no-charts",      action="store_true", help="跳过图表生成")
    parser.add_argument("--no-signals",     action="store_true", help="跳过信号生成")
    parser.add_argument("--force-regime",   action="store_true", help="强制运行 HMM")
    parser.add_argument("--force-backtest", action="store_true", help="强制运行月度回测")
    parser.add_argument("--date",           default=None,
                        help="日期 YYYYMMDD，默认今日")
    args = parser.parse_args()

    tickers  = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    strats   = [s.strip() for s in args.strategies.split(",") if s.strip()]
    td       = date.today()
    if args.date:
        from datetime import datetime
        td = datetime.strptime(args.date, "%Y%m%d").date()

    # 需要 QApplication 以使 QRunnable 工作（无头模式）
    app = QApplication.instance() or QApplication(sys.argv[:1])

    import threading
    done_event = threading.Event()
    exit_code  = [0]

    from PyQt6.QtCore import QThreadPool

    worker = DailyExportWorker(
        tickers=tickers,
        strategy_keys=None if args.no_signals else strats,
        trade_date=td,
        run_charts=not args.no_charts,
        run_signals=not args.no_signals,
        force_regime=args.force_regime,
        force_backtest=args.force_backtest,
    )

    def on_progress(pct, msg):
        print(f"[{pct:3d}%] {msg}")

    def on_done(root):
        print(f"\n✅ 完成！输出目录：{root}")
        done_event.set()

    def on_error(msg):
        print(f"\n❌ 错误：{msg}", file=sys.stderr)
        exit_code[0] = 1
        done_event.set()

    worker.signals.progress.connect(on_progress)
    worker.signals.completed.connect(on_done)
    worker.signals.error.connect(on_error)

    QThreadPool.globalInstance().start(worker)

    # 等待完成（最多60分钟）
    done_event.wait(timeout=3600)
    QThreadPool.globalInstance().waitForDone(5000)
    sys.exit(exit_code[0])


if __name__ == "__main__":
    _cli_main()
