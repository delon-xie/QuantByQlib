"""
K 线图数据提供者
通过 market_data_client 获取历史 OHLCV（降级链：OpenBB → yfinance 直接调用）
本地计算 ATR（止损参考）和 OBV（量价背离）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class ChartData:
    """K 线图数据结构"""
    ticker:         str
    ohlcv:          pd.DataFrame        # 列：open, high, low, close, volume
    current_price:  float
    change_pct:     float               # 今日涨跌幅（小数，如 0.023 = +2.3%）
    atr14:          Optional[float]     # 14 日 ATR
    obv_trend:      Optional[str]       # "上升" / "下降" / "横盘"
    support:        Optional[float]     # 近 20 日支撑位
    resistance:     Optional[float]     # 近 20 日阻力位
    ma5:            Optional[float]     # 5 日均线最新值
    ma20:           Optional[float]     # 20 日均线最新值
    ma60:           Optional[float]     # 60 日均线最新值
    period_days:    int = 365           # 实际返回的数据天数
    available:      bool = True


class PriceChart:
    """
    K 线数据提供者：通过 OpenBB 获取历史 OHLCV
    优先 alpha_vantage（更稳定），失败时降级到 yfinance
    ATR 和 OBV 在本地计算（Alpha158 未包含这两个指标）
    """

    def get_chart_data(self, ticker: str, period_days: int = 365) -> ChartData:
        """
        获取 K 线数据，包含 ATR/OBV/均线
        任何数据源失败时返回 available=False 的占位对象
        """
        ticker = ticker.upper().strip()
        from core.app_state import get_state
        reg = get_state().reg
        from core.qlibhelper import normalize_cn_tickers
        if reg == "cn":
            ticker = normalize_cn_tickers(ticker)[0]
        df = self._fetch_ohlcv(ticker, period_days)

        if df is None or df.empty or len(df) < 5:
            logger.warning(f"无法获取 {ticker} 的价格数据（所有数据源失败）")
            return ChartData(
                ticker=ticker,
                ohlcv=pd.DataFrame(),
                current_price=0.0,
                change_pct=0.0,
                atr14=None,
                obv_trend=None,
                support=None,
                resistance=None,
                ma5=None,
                ma20=None,
                ma60=None,
                period_days=period_days,
                available=False,
            )

        # 列名标准化（不同 provider 的列名可能不同）
        df = self._normalize_columns(df)

        # 计算技术指标
        atr14 = self._calc_atr(df, period=14)
        obv_trend = self._calc_obv_trend(df)
        support    = float(df["low"].rolling(20).min().iloc[-1])  if len(df) >= 20 else None
        resistance = float(df["high"].rolling(20).max().iloc[-1]) if len(df) >= 20 else None
        ma5  = float(df["close"].rolling(5).mean().iloc[-1])  if len(df) >= 5  else None
        ma20 = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else None
        ma60 = float(df["close"].rolling(60).mean().iloc[-1]) if len(df) >= 60 else None

        current_price = float(df["close"].iloc[-1])
        prev_close    = float(df["close"].iloc[-2]) if len(df) >= 2 else current_price
        change_pct    = (current_price / prev_close - 1) if prev_close > 0 else 0.0

        atr_str = f"{atr14:.2f}" if atr14 else "N/A"
        logger.debug(
            f"K线数据 {ticker}：{len(df)} 条记录，"
            f"最新收盘 ${current_price:.2f}，ATR={atr_str}"
        )

        return ChartData(
            ticker=ticker,
            ohlcv=df[["open", "high", "low", "close", "volume"]],
            current_price=current_price,
            change_pct=change_pct,
            atr14=atr14,
            obv_trend=obv_trend,
            support=support,
            resistance=resistance,
            ma5=ma5,
            ma20=ma20,
            ma60=ma60,
            period_days=len(df),
            available=True,
        )

    # ── 私有方法 ──────────────────────────────────────────────

    def _fetch_ohlcv(self, ticker: str, period_days: int) -> Optional[pd.DataFrame]:
        """委托给统一数据访问层（OpenBB → yfinance 降级链）"""
        from data.market_data_client import get_ohlcv_period
        return get_ohlcv_period(ticker, period_days)

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一列名为小写：open/high/low/close/volume（market_data_client 已处理，保留作保障）"""
        from data.market_data_client import _normalize_columns
        return _normalize_columns(df)

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """计算 ATR（平均真实波幅）"""
        try:
            high  = df["high"]
            low   = df["low"]
            close = df["close"]

            tr = pd.concat([
                high - low,
                (high - close.shift(1)).abs(),
                (low  - close.shift(1)).abs(),
            ], axis=1).max(axis=1)

            atr = tr.rolling(period).mean()
            val = atr.iloc[-1]
            return float(val) if not np.isnan(val) else None
        except Exception as e:
            logger.debug(f"ATR 计算失败：{e}")
            return None

    def _calc_obv_trend(self, df: pd.DataFrame, lookback: int = 5) -> Optional[str]:
        """
        计算 OBV 趋势
        OBV 上升→ 放量上涨，下降→ 缩量/空头
        """
        try:
            close  = df["close"]
            volume = df["volume"]

            sign = np.sign(close.diff())
            sign.iloc[0] = 0
            obv = (sign * volume).cumsum()

            if len(obv) < lookback + 1:
                return None

            latest = float(obv.iloc[-1])
            prev   = float(obv.iloc[-1 - lookback])

            diff_pct = (latest - prev) / (abs(prev) + 1e-9)
            if diff_pct > 0.05:
                return "上升"
            elif diff_pct < -0.05:
                return "下降"
            else:
                return "横盘"
        except Exception as e:
            logger.debug(f"OBV 计算失败：{e}")
            return None

    def get_ma_signals(self, chart: ChartData) -> list[dict]:
        """将均线数据转化为信号列表"""
        signals = []
        price = chart.current_price
        if price <= 0:
            return signals

        pairs = [
            ("MA5",  chart.ma5,  "5 日均线"),
            ("MA20", chart.ma20, "20 日均线"),
            ("MA60", chart.ma60, "60 日均线"),
        ]
        for key, ma_val, label in pairs:
            if ma_val is None:
                continue
            diff_pct = (price / ma_val - 1) * 100
            if diff_pct > 3:
                sig, stype = f"价格高于均线 {diff_pct:+.1f}%", "bullish"
            elif diff_pct > -3:
                sig, stype = f"价格靠近均线 {diff_pct:+.1f}%", "neutral"
            else:
                sig, stype = f"价格低于均线 {diff_pct:+.1f}%", "bearish"
            signals.append({
                "label": label,
                "value_str": f"${ma_val:.2f}",
                "signal_text": sig,
                "signal_type": stype,
            })

        # ATR 止损参考
        if chart.atr14 and price > 0:
            stop_loss = price - chart.atr14 * 2
            signals.append({
                "label": "ATR 止损位（2×ATR）",
                "value_str": f"${stop_loss:.2f}",
                "signal_text": f"ATR={chart.atr14:.2f}，止损参考 ${stop_loss:.2f}",
                "signal_type": "neutral",
            })

        # OBV 信号
        if chart.obv_trend:
            obv_type = "bullish" if chart.obv_trend == "上升" else (
                "bearish" if chart.obv_trend == "下降" else "neutral"
            )
            signals.append({
                "label": "OBV 能量潮",
                "value_str": chart.obv_trend,
                "signal_text": {
                    "上升": "放量上涨，量价配合",
                    "下降": "缩量或空头占优",
                    "横盘": "量价中性",
                }[chart.obv_trend],
                "signal_type": obv_type,
            })

        return signals
