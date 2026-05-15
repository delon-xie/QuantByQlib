"""
统一市场数据访问层 (Market Data Client)

所有需要 OHLCV 历史行情的模块都应通过本模块获取数据，禁止直接调用 yfinance 或 openbb。

降级链：
  1. OpenBB(alpha_vantage) — 需要 ALPHA_VANTAGE_API_KEY
  2. OpenBB(yfinance)      — 通过 OpenBB 中间层
  3. yfinance 直接调用     — 绕过 OpenBB，最终保底

返回约定：
  - 所有函数失败时返回 None，调用方检查 None 后显示"暂无数据"
  - OHLCV DataFrame 列名统一为小写 open/high/low/close/volume
  - 索引为 pd.DatetimeIndex（升序）
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
from loguru import logger
from workers.binance_downloader import get_crypto_data_binance

# ── OHLCV 历史行情 ────────────────────────────────────────────


def get_ohlcv(
    ticker: str,
    start_date: str,
    end_date: str,
) -> Optional[pd.DataFrame]:
    """
    获取 OHLCV 历史行情，返回标准化 DataFrame（失败返回 None）。

    降级链：OpenBB(alpha_vantage) → OpenBB(yfinance) → yfinance 直接调用

    参数:
        ticker:     股票代码（如 "AAPL"）
        start_date: 起始日期字符串（"YYYY-MM-DD"）
        end_date:   结束日期字符串（"YYYY-MM-DD"）
    """
    ticker = ticker.upper().strip()

    from core.app_state import get_state
    reg = get_state().reg
    
    # 1. OpenBB 降级链
    if reg == "bt":
        #binance
        df = get_crypto_data_binance(ticker=ticker, start_date=start_date, end_date=end_date)
    else :
        df = _fetch_via_openbb(ticker, start_date, end_date)
    
    if df is None or df.empty:
        # 2. yfinance 直接调用（绕过 OpenBB，最终保底）
        df = _fetch_via_yfinance_direct(ticker, start_date, end_date)
        
    if df is not None and not df.empty:
        return _normalize_columns(df)

    logger.warning(f"[MarketData] {ticker} 所有数据源均失败（{start_date} ~ {end_date}）")
    return None


def get_ohlcv_period(
    ticker: str,
    period_days: int = 365,
) -> Optional[pd.DataFrame]:
    """
    按天数获取近期 OHLCV（多取 30 天缓冲应对非交易日）。
    """
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=period_days + 30)).isoformat()
    return get_ohlcv(ticker, start, end)


# ── 内部实现 ──────────────────────────────────────────────────


def _fetch_via_openbb(
    ticker: str,
    start_date: str,
    end_date: str,
) -> Optional[pd.DataFrame]:
    """尝试 OpenBB alpha_vantage → yfinance，返回原始 DataFrame 或 None。"""
    try:
        from openbb import obb
        from data.openbb_client import _configure_providers
        _configure_providers(obb)
    except Exception as e:
        logger.debug(f"[MarketData] OpenBB 不可用：{e}")
        return None

    proxy = _get_proxy()
    for provider in ["alpha_vantage", "yfinance"]:
        try:
            extra = {"proxy": proxy} if proxy else {}
            result = obb.equity.price.historical(
                symbol=ticker,
                start_date=start_date,
                end_date=end_date,
                provider=provider,
                **extra,
            )
            if result and result.results:
                df = result.to_dataframe()
                if df is not None and not df.empty:
                    logger.debug(f"[MarketData] {ticker} via OpenBB({provider})，{len(df)} 条")
                    return df
        except Exception as e:
            logger.debug(f"[MarketData] OpenBB({provider}) 失败 {ticker}：{e}")
            continue

    return None


def _get_proxy() -> Optional[str]:
    """读取系统代理设置（HTTPS_PROXY / HTTP_PROXY / ALL_PROXY）"""
    import os
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return None


def _fetch_via_yfinance_direct(
    ticker: str,
    start_date: str,
    end_date: str,
) -> Optional[pd.DataFrame]:
    """直接调用 yfinance Ticker.history()，比 download() 更稳定，绕过 OpenBB 中间层。"""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        df = t.history(start=start_date, end=end_date, auto_adjust=True)
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            # 去掉时区信息，统一为 date-only DatetimeIndex
            if hasattr(df.index, "tz") and df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            logger.debug(f"[MarketData] {ticker} via yfinance(Ticker)，{len(df)} 条")
            return df
    except Exception as e:
        logger.debug(f"[MarketData] yfinance Ticker.history 失败 {ticker}：{e}")

    return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    统一列名为小写 open/high/low/close/volume，
    确保索引为升序 DatetimeIndex。
    """
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = str(col).lower().replace(" ", "_")
        if cl in ("open", "high", "low", "close", "volume", "adj_close"):
            col_map[col] = cl

    if col_map:
        df = df.rename(columns=col_map)

    # 确保 DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        for candidate in ("date", "Date", "timestamp", "Timestamp"):
            if candidate in df.columns:
                df = df.set_index(candidate)
                df.index = pd.to_datetime(df.index)
                break
    else:
        df.index = pd.to_datetime(df.index)

    return df.sort_index()


# ── 数据源健康检查 ─────────────────────────────────────────────


def check_data_sources() -> dict[str, bool]:
    """
    快速检测各数据源可用性（供 Dashboard 展示）。
    返回 {source_name: is_available}
    """
    import os
    results: dict[str, bool] = {}

    test_ticker = "AAPL"
    test_start = "2025-01-02"
    test_end = "2025-01-06"

    # yfinance 直接
    df = _fetch_via_yfinance_direct(test_ticker, test_start, test_end)
    results["yfinance"] = df is not None and not df.empty

    # OpenBB(yfinance)
    try:
        from openbb import obb
        from data.openbb_client import _configure_providers
        _configure_providers(obb)
        r = obb.equity.price.historical(
            symbol=test_ticker,
            start_date=test_start,
            end_date=test_end,
            provider="yfinance",
        )
        results["openbb_yfinance"] = bool(r and r.results)
    except Exception:
        results["openbb_yfinance"] = False

    # OpenBB(alpha_vantage)
    if os.environ.get("ALPHA_VANTAGE_API_KEY"):
        try:
            from openbb import obb
            r = obb.equity.price.historical(
                symbol=test_ticker,
                start_date=test_start,
                end_date=test_end,
                provider="alpha_vantage",
            )
            results["alpha_vantage"] = bool(r and r.results)
        except Exception:
            results["alpha_vantage"] = False
    else:
        results["alpha_vantage"] = False  # 未配置 Key

    # Finnhub（基本面/新闻）
    finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
    results["finnhub"] = bool(finnhub_key)

    logger.info(f"[MarketData] 数据源健康检查：{results}")
    return results
