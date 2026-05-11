"""
长桥（LongPort）行情数据封装
支持：
- 5分钟线：Min_5 分钟K线（最近 5 × 78 根）
  - 日线：Day K（最近 60 根）
  - 周线：Week K（最近 104 根）

返回 pandas DataFrame，列名与 mplfinance 兼容：
  Open / High / Low / Close / Volume，Index 为 DatetimeTZInfo
"""
from __future__ import annotations

import os
import pandas as pd
from datetime import datetime
from typing import Optional


def _get_config():
    """从环境变量构建长桥 Config，缺少任意 Key 则返回 None"""
    from longport.openapi import Config
    app_key    = os.environ.get("LONGPORT_APP_KEY", "").strip()
    app_secret = os.environ.get("LONGPORT_APP_SECRET", "").strip()
    access_tok = os.environ.get("LONGPORT_ACCESS_TOKEN", "").strip()
    if not (app_key and app_secret and access_tok):
        return None
    return Config(
        app_key=app_key,
        app_secret=app_secret,
        access_token=access_tok,
    )


def is_configured() -> bool:
    """检查长桥 Key 是否已配置"""
    return _get_config() is not None


def get_candlesticks(ticker: str, period_key: str) -> Optional[pd.DataFrame]:
    """
    拉取 K 线数据并返回 mplfinance 兼容 DataFrame。

    period_key:
      "zoom" → Day，  取120根计算均线，展示最后20根（约1个月放大）
      "day"  → Day，  取130根，展示最近90根（约4.5个月）
      "week" → Week， 取80根，展示最近60根（约15个月）

    symbol 格式：长桥要求 "AAPL.US"（美股后缀 .US）
    """
    cfg = _get_config()
    if cfg is None:
        return None

    try:
        from longport.openapi import QuoteContext, Period, AdjustType

        _PERIOD_MAP = {
            "zoom": (Period.Day,  120),  # 取120根日K计算均线，前端截取最后20根展示
            "day":  (Period.Day,  130),  # 取130根，展示最近90根
            "week": (Period.Week,  80),  # 取80根，展示最近60根
        }
        period, count = _PERIOD_MAP[period_key]

        # 长桥 symbol 格式
        symbol = ticker if "." in ticker else f"{ticker}.US"

        ctx = QuoteContext(cfg)
        candles = ctx.candlesticks(
            symbol=symbol,
            period=period,
            count=count,
            adjust_type=AdjustType.ForwardAdjust,
        )

        if not candles:
            return None

        rows = []
        for c in candles:
            rows.append({
                "Date":   c.timestamp,
                "Open":   float(c.open),
                "High":   float(c.high),
                "Low":    float(c.low),
                "Close":  float(c.close),
                "Volume": int(c.volume),
            })

        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        df.index.name = "Date"
        # zoom：返回完整数据供调用方计算准确均线，由调用方控制显示范围
        # day/week：截取展示根数
        _TAIL = {"day": 90, "week": 60}
        tail_n = _TAIL.get(period_key)
        if tail_n:
            df = df.tail(tail_n)
        return df

    except Exception as e:
        from loguru import logger
        logger.warning(f"[长桥] 拉取 {ticker} {period_key} 失败：{e}")
        return None
