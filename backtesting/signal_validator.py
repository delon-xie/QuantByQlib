"""
历史信号胜率验证 (Signal Validator)

自动评估过去 N 天导出的买入信号实际准确率：
  - 读取 ~/Documents/美股交易日记/signals/ 下的历史 CSV 文件
  - 对每个买入信号，用 yfinance 拉取 T+5 / T+20 实际价格
  - 计算胜率、平均收益率、最大盈利/亏损

使用方式：
  validator = SignalValidator()
  result = validator.validate(lookback_days=30, forward_days=[5, 20])
  print(result.summary())
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger


@dataclass
class SignalRecord:
    """单条历史信号"""
    ticker:        str
    signal_date:   date
    signal_type:   str          # 买入/卖出/持有
    score:         Optional[float]
    price_at_signal: Optional[float]
    strategy:      str


@dataclass
class ForwardReturn:
    """单条信号的前瞻收益"""
    ticker:      str
    signal_date: date
    strategy:    str
    price_t0:    Optional[float]    # 信号日收盘价
    price_t5:    Optional[float]    # T+5 收盘价
    price_t20:   Optional[float]    # T+20 收盘价
    ret_t5:      Optional[float]    # T+5 收益率（小数）
    ret_t20:     Optional[float]    # T+20 收益率（小数）
    win_t5:      Optional[bool]
    win_t20:     Optional[bool]


@dataclass
class ValidationResult:
    """验证汇总结果"""
    total_signals:    int
    validated:        int
    # T+5
    win_rate_t5:      Optional[float]   # 0-1
    avg_ret_t5:       Optional[float]   # 平均收益率（小数）
    max_gain_t5:      Optional[float]
    max_loss_t5:      Optional[float]
    # T+20
    win_rate_t20:     Optional[float]
    avg_ret_t20:      Optional[float]
    max_gain_t20:     Optional[float]
    max_loss_t20:     Optional[float]
    # 明细
    records:          list[ForwardReturn] = field(default_factory=list)
    by_strategy:      dict = field(default_factory=dict)   # {strategy: sub_result_dict}

    def summary(self) -> str:
        lines = [
            f"历史信号胜率验证报告",
            f"  信号总数：{self.total_signals}，已验证：{self.validated}",
            "",
        ]
        if self.win_rate_t5 is not None:
            lines += [
                f"  T+5  胜率：{self.win_rate_t5*100:.1f}%   "
                f"均收：{self.avg_ret_t5*100:+.2f}%   "
                f"最大盈：{self.max_gain_t5*100:+.1f}%   "
                f"最大亏：{self.max_loss_t5*100:+.1f}%",
            ]
        if self.win_rate_t20 is not None:
            lines += [
                f"  T+20 胜率：{self.win_rate_t20*100:.1f}%   "
                f"均收：{self.avg_ret_t20*100:+.2f}%   "
                f"最大盈：{self.max_gain_t20*100:+.1f}%   "
                f"最大亏：{self.max_loss_t20*100:+.1f}%",
            ]
        return "\n".join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        """返回 DataFrame，每行一条信号的前瞻收益数据"""
        rows = []
        for r in self.records:
            rows.append({
                "ticker":      r.ticker,
                "signal_date": r.signal_date,
                "strategy":    r.strategy,
                "price_t0":    r.price_t0,
                "price_t5":    r.price_t5,
                "price_t20":   r.price_t20,
                "ret_t5_pct":  round(r.ret_t5 * 100, 2) if r.ret_t5 is not None else None,
                "ret_t20_pct": round(r.ret_t20 * 100, 2) if r.ret_t20 is not None else None,
                "win_t5":      r.win_t5,
                "win_t20":     r.win_t20,
            })
        return pd.DataFrame(rows)


class SignalValidator:
    """历史信号胜率验证器"""

    # 信号 CSV 列名映射（兼容不同格式）
    _TICKER_COLS  = ["股票", "symbol", "ticker", "Symbol"]
    _SIGNAL_COLS  = ["信号", "signal", "direction"]
    _SCORE_COLS   = ["Qlib评分", "score", "qlib_score"]

    def __init__(self, signals_dir: Optional[Path] = None):
        if signals_dir is not None:
            self._signals_dir = Path(signals_dir)
        else:
            from services.output_paths import get_signals_dir
            self._signals_dir = get_signals_dir()

    def validate(
        self,
        lookback_days: int = 30,
        forward_days: list[int] | None = None,
        strategy_filter: str | None = None,
    ) -> ValidationResult:
        """
        验证过去 lookback_days 天的买入信号准确率。

        参数：
            lookback_days:    往前查看几天的信号文件
            forward_days:     前瞻天数列表，默认 [5, 20]
            strategy_filter:  只验证某个策略（文件名前缀），None = 全部
        """
        if forward_days is None:
            forward_days = [5, 20]

        signals = self._load_signals(lookback_days, strategy_filter)
        logger.info(f"[SignalValidator] 加载 {len(signals)} 条买入信号（过去 {lookback_days} 天）")

        if not signals:
            return ValidationResult(
                total_signals=0, validated=0,
                win_rate_t5=None, avg_ret_t5=None, max_gain_t5=None, max_loss_t5=None,
                win_rate_t20=None, avg_ret_t20=None, max_gain_t20=None, max_loss_t20=None,
            )

        # 批量获取历史价格
        records = self._fetch_forward_returns(signals, forward_days)

        return self._aggregate(signals, records)

    # ── 内部方法 ──────────────────────────────────────────────

    def _load_signals(
        self, lookback_days: int, strategy_filter: Optional[str]
    ) -> list[SignalRecord]:
        """扫描信号 CSV 目录，读取买入信号"""
        cutoff = date.today() - timedelta(days=lookback_days)
        signals: list[SignalRecord] = []

        pattern = f"{strategy_filter}_*.csv" if strategy_filter else "strategy*.csv"
        csv_files = sorted(self._signals_dir.glob(pattern), reverse=True)

        for csv_path in csv_files:
            # 从文件名提取日期：strategy2_20260318.csv
            signal_date = self._parse_date_from_filename(csv_path.name)
            if signal_date is None or signal_date < cutoff:
                continue
            # 未来日期跳过（T+5/T+20 价格尚不存在）
            if signal_date > date.today() - timedelta(days=5):
                continue

            strategy = csv_path.stem  # e.g. strategy2_20260318

            try:
                df = pd.read_csv(csv_path, encoding="utf-8-sig")
                ticker_col  = next((c for c in self._TICKER_COLS  if c in df.columns), None)
                signal_col  = next((c for c in self._SIGNAL_COLS  if c in df.columns), None)
                score_col   = next((c for c in self._SCORE_COLS   if c in df.columns), None)

                if ticker_col is None:
                    logger.debug(f"[SignalValidator] 跳过 {csv_path.name}（无股票代码列）")
                    continue

                for _, row in df.iterrows():
                    ticker = str(row[ticker_col]).strip().upper()
                    if not ticker or ticker == "NAN":
                        continue
                    signal_type = str(row.get(signal_col, "买入")).strip() if signal_col else "买入"
                    # 只验证买入信号
                    if not any(kw in signal_type for kw in ["买", "Buy", "BUY"]):
                        continue
                    score = None
                    if score_col and score_col in row.index:
                        try:
                            score = float(row[score_col])
                        except (ValueError, TypeError):
                            pass

                    signals.append(SignalRecord(
                        ticker=ticker,
                        signal_date=signal_date,
                        signal_type=signal_type,
                        score=score,
                        price_at_signal=None,
                        strategy=strategy,
                    ))
            except Exception as e:
                logger.debug(f"[SignalValidator] 读取 {csv_path.name} 失败：{e}")

        return signals

    def _fetch_forward_returns(
        self, signals: list[SignalRecord], forward_days: list[int]
    ) -> list[ForwardReturn]:
        """批量拉取前瞻价格（yfinance，按股票分组以减少请求次数）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 按 ticker 分组
        ticker_signals: dict[str, list[SignalRecord]] = {}
        for s in signals:
            ticker_signals.setdefault(s.ticker, []).append(s)

        records: list[ForwardReturn] = []

        def fetch_one(ticker: str, sig_list: list[SignalRecord]) -> list[ForwardReturn]:
            results = []
            try:
                import yfinance as yf
                earliest = min(s.signal_date for s in sig_list) - timedelta(days=5)
                latest   = max(s.signal_date for s in sig_list) + timedelta(days=max(forward_days) + 10)
                latest   = min(latest, date.today())

                hist = yf.download(
                    ticker,
                    start=earliest.isoformat(),
                    end=latest.isoformat(),
                    progress=False,
                    auto_adjust=True,
                    threads=True,
                )
                if hist is None or hist.empty:
                    return results

                # 展平 MultiIndex
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = [c[0].lower() for c in hist.columns]
                else:
                    hist.columns = [c.lower() for c in hist.columns]

                hist.index = pd.to_datetime(hist.index).date

                for sig in sig_list:
                    t0_price = self._closest_price(hist, sig.signal_date)
                    t5_price  = self._closest_price(hist, sig.signal_date + timedelta(days=5))
                    t20_price = self._closest_price(hist, sig.signal_date + timedelta(days=20))

                    ret5  = (t5_price  / t0_price - 1) if t0_price and t5_price  else None
                    ret20 = (t20_price / t0_price - 1) if t0_price and t20_price else None

                    results.append(ForwardReturn(
                        ticker=ticker,
                        signal_date=sig.signal_date,
                        strategy=sig.strategy,
                        price_t0=t0_price,
                        price_t5=t5_price,
                        price_t20=t20_price,
                        ret_t5=ret5,
                        ret_t20=ret20,
                        win_t5=ret5 > 0 if ret5 is not None else None,
                        win_t20=ret20 > 0 if ret20 is not None else None,
                    ))
            except Exception as e:
                logger.debug(f"[SignalValidator] 拉取 {ticker} 价格失败：{e}")
            return results

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(fetch_one, t, sigs): t
                       for t, sigs in ticker_signals.items()}
            for future in as_completed(futures):
                try:
                    records.extend(future.result())
                except Exception:
                    pass

        return records

    def _closest_price(self, hist_df: pd.DataFrame, target_date: date) -> Optional[float]:
        """在历史 DataFrame 中找最接近 target_date 的收盘价（±5天内）"""
        for delta in range(6):
            for sign in [0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5]:
                check = target_date + timedelta(days=sign + delta * 0)
                # 只尝试 ±5 天
                break
            break

        for delta in range(6):
            for sign in [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5]:
                check = target_date + timedelta(days=sign)
                if check in hist_df.index:
                    close_col = next(
                        (c for c in ["close", "Close", "adj_close"] if c in hist_df.columns),
                        None
                    )
                    if close_col:
                        val = hist_df.loc[check, close_col]
                        try:
                            return float(val)
                        except (TypeError, ValueError):
                            pass

        return None

    def _aggregate(
        self, signals: list[SignalRecord], records: list[ForwardReturn]
    ) -> ValidationResult:
        """汇总统计"""
        validated = [r for r in records if r.ret_t5 is not None or r.ret_t20 is not None]

        def stats(rets: list[float]) -> tuple:
            if not rets:
                return None, None, None, None
            wins = [r for r in rets if r > 0]
            return (
                len(wins) / len(rets),
                sum(rets) / len(rets),
                max(rets),
                min(rets),
            )

        rets5  = [r.ret_t5  for r in validated if r.ret_t5  is not None]
        rets20 = [r.ret_t20 for r in validated if r.ret_t20 is not None]

        wr5, avg5, max5, min5   = stats(rets5)
        wr20, avg20, max20, min20 = stats(rets20)

        # 按策略分组
        by_strategy: dict = {}
        for strat in {r.strategy for r in validated}:
            sub = [r for r in validated if r.strategy == strat]
            sub5  = [r.ret_t5  for r in sub if r.ret_t5  is not None]
            sub20 = [r.ret_t20 for r in sub if r.ret_t20 is not None]
            wr5_s, avg5_s, _, _   = stats(sub5)
            wr20_s, avg20_s, _, _ = stats(sub20)
            by_strategy[strat] = {
                "count":       len(sub),
                "win_rate_t5": wr5_s,
                "avg_ret_t5":  avg5_s,
                "win_rate_t20": wr20_s,
                "avg_ret_t20": avg20_s,
            }

        return ValidationResult(
            total_signals=len(signals),
            validated=len(validated),
            win_rate_t5=wr5,
            avg_ret_t5=avg5,
            max_gain_t5=max5,
            max_loss_t5=min5,
            win_rate_t20=wr20,
            avg_ret_t20=avg20,
            max_gain_t20=max20,
            max_loss_t20=min20,
            records=validated,
            by_strategy=by_strategy,
        )

    @staticmethod
    def _parse_date_from_filename(filename: str) -> Optional[date]:
        """从 strategy2_20260318.csv 中提取日期"""
        m = re.search(r"(\d{8})", filename)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y%m%d").date()
            except ValueError:
                pass
        return None
