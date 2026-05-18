"""
OpenBB Platform 统一数据接入层
所有市场/基本面/新闻数据均通过此模块获取，禁止在其他模块直接调用 openbb

失败策略：所有方法失败时返回 None（不抛异常），调用方检查 None 后显示"暂无数据"
"""
from __future__ import annotations

import os
from typing import Optional
from loguru import logger


def _get_obb():
    """懒加载 OpenBB 实例，确保 API Key 已从环境变量中读取"""
    try:
        from openbb import obb
        _configure_providers(obb)
        return obb
    except ImportError:
        logger.warning("OpenBB 未安装，请运行：pip3 install openbb")
        return None
    except Exception as e:
        logger.warning(f"OpenBB 初始化失败：{e}")
        return None


def _configure_providers(obb) -> None:
    """将 .env 中的 API Key 注入 OpenBB"""
    try:
        fmp_key = os.environ.get("FMP_API_KEY", "")
        finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
        av_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")

        creds = obb.user.credentials
        if fmp_key:
            try:
                creds.fmp_api_key = fmp_key
            except Exception:
                pass
        if finnhub_key:
            try:
                creds.finnhub_api_key = finnhub_key
            except Exception:
                pass
        if av_key:
            try:
                creds.alpha_vantage_api_key = av_key
            except Exception:
                pass
    except Exception:
        pass  # 配置失败不影响启动


# ── 行情数据 ──────────────────────────────────────────────────

def get_price_history(
    ticker: str,
    start_date: str,
    end_date: str,
    provider_priority: list[str] | None = None,
) -> Optional[object]:
    """
    获取 OHLCV 历史行情
    provider 优先级：alpha_vantage → yfinance
    返回 OpenBB OBBject（.to_dataframe() 可得 DataFrame），失败返回 None
    """
    obb = _get_obb()
    if obb is None:
        return None

    providers = provider_priority or ["alpha_vantage", "yfinance"]
    for provider in providers:
        try:
            result = obb.equity.price.historical(
                symbol=ticker,
                start_date=start_date,
                end_date=end_date,
                provider=provider,
            )
            if result and result.results:
                logger.debug(f"行情数据 {ticker} 来自 {provider}")
                return result
        except Exception as e:
            logger.debug(f"行情 provider {provider} 失败：{e}")
            continue

    logger.warning(f"所有 provider 均无法获取 {ticker} 行情数据")
    return None


def get_latest_quote(ticker: str) -> Optional[dict]:
    """
    获取最新报价（当前价/涨跌幅）
    返回 dict：{price, change, change_pct, volume} 或 None
    """
    obb = _get_obb()
    if obb is None:
        return None

    for provider in ["yfinance", "fmp"]:
        try:
            result = obb.equity.price.quote(symbol=ticker, provider=provider)
            if result and result.results:
                row = result.to_dataframe().iloc[0]
                return {
                    "price":      _safe_float(row, ["last_price", "price", "close"]),
                    "change":     _safe_float(row, ["change", "price_change"]),
                    "change_pct": _safe_float(row, ["change_percent", "price_change_percent"]),
                    "volume":     _safe_float(row, ["volume"]),
                    "provider":   provider,
                }
        except Exception as e:
            logger.debug(f"报价 provider {provider} 失败：{e}")
            continue

    return None


def _get_realtime_quote_yf(ticker: str) -> Optional[dict]:
    """
    用 yfinance 获取单只股票的最新价格（含盘前/盘中/盘后）
    优先：history(interval="1m", prepost=True) 取最新1分钟K线收盘价
    降级：fast_info.last_price（非交易时间/周末分钟数据为空时）
    涨跌幅基准：fast_info.previous_close
    """
    try:
        import yfinance as yf
        import pytz
        from core.app_state import get_state
        reg = get_state().reg
        from core.qlibhelper import normalize_cn_tickers
        if reg == "cn":
            ticker = normalize_cn_tickers(ticker)[0]
        t = yf.Ticker(ticker.lstrip("$"))  # 兼容带 $ 前缀的 ticker

        last_price = None
        is_extended = False

        # 尝试分钟K线（盘中/盘前/盘后最准确）
        try:
            hist = t.history(period="1d", interval="1m", prepost=True)
            if not hist.empty:
                price_candidate = float(hist["Close"].iloc[-1])
                if price_candidate == price_candidate:  # NaN check
                    last_price = price_candidate
                    last_ts = hist.index[-1]
                    try:
                        et = pytz.timezone("America/New_York")
                        last_et = last_ts.astimezone(et)
                        h, m = last_et.hour, last_et.minute
                        in_regular = (h == 9 and m >= 30) or (10 <= h < 16)
                        is_extended = not in_regular
                    except Exception:
                        is_extended = False
        except Exception:
            pass

        # 降级：fast_info（非交易时间分钟数据为空时）
        if last_price is None:
            fi = t.fast_info
            raw = getattr(fi, "last_price", None)
            if raw is not None:
                last_price = float(raw)
            # 非交易时间视为盘外
            is_extended = True

        if last_price is None:
            return None

        # 涨跌幅
        prev_close = getattr(t.fast_info, "previous_close", None)
        change_pct = None
        if prev_close and float(prev_close) > 0:
            change_pct = (last_price - float(prev_close)) / float(prev_close) * 100

        return {
            "price":       last_price,
            "change_pct":  change_pct,
            "is_extended": is_extended,
        }
    except Exception:
        return None


def get_batch_quotes(tickers: list[str]) -> dict[str, Optional[dict]]:
    """
    批量获取多只股票的实时报价（含盘前/盘中/盘后）
    使用 yfinance fast_info 多线程并发，无需 API Key
    返回 {ticker: {price, change_pct} or None}
    """
    if not tickers:
        return {}
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results: dict[str, Optional[dict]] = {}
        with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as executor:
            future_to_ticker = {
                executor.submit(_get_realtime_quote_yf, t): t for t in tickers
            }
            for future in as_completed(future_to_ticker):
                t = future_to_ticker[future]
                try:
                    results[t] = future.result()
                except Exception:
                    results[t] = None
        ok = sum(1 for v in results.values() if v)
        logger.debug(f"yfinance 实时报价完成：{ok}/{len(tickers)} 支有数据")
        return results
    except Exception as e:
        logger.warning(f"yfinance 批量报价失败，回退逐个 OpenBB：{e}")
        result = {}
        for ticker in tickers:
            result[ticker] = get_latest_quote(ticker)
        return result


# ── Finnhub 直接调用工具 ──────────────────────────────────────

def _finnhub_get(path: str, params: dict) -> Optional[dict]:
    """调用 Finnhub REST API，返回 JSON dict 或 None"""
    key = os.environ.get("FINNHUB_API_KEY", "")
    if not key:
        return None
    try:
        import requests
        params["token"] = key
        r = requests.get(f"https://finnhub.io/api/v1{path}", params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug(f"Finnhub {path} 失败：{e}")
    return None


# ── 基本面数据 ────────────────────────────────────────────────

def get_fundamental_metrics(ticker: str) -> Optional[dict]:
    """
    获取基本面指标（PE/PB/市值/ROE 等）via Finnhub basic financials
    返回 dict 或 None
    """
    data = _finnhub_get("/stock/metric", {"symbol": ticker, "metric": "all"})
    if not data or "metric" not in data:
        return None
    m = data["metric"]
    def _f(key):
        v = m.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    return {
        "pe_ratio":         _f("peNormalizedAnnual") or _f("peTTM"),
        "pb_ratio":         _f("pbQuarterly") or _f("pbAnnual"),
        "ps_ratio":         _f("psTTM"),
        "roe":              _f("roeTTM"),
        "roa":              _f("roaTTM"),
        "debt_to_equity":   _f("totalDebt/totalEquityAnnual"),
        "current_ratio":    _f("currentRatioQuarterly") or _f("currentRatioAnnual"),
        "revenue_growth":   _f("revenueGrowthTTMYoy"),
        "eps_growth":       _f("epsGrowthTTMYoy"),
        "gross_margin":     _f("grossMarginTTM"),
        "operating_margin": _f("operatingMarginTTM"),
        "net_margin":       _f("netProfitMarginTTM"),
    }


def get_company_profile(ticker: str) -> Optional[dict]:
    """
    获取公司概况（名称/行业/市值/描述/分析师目标价）via Finnhub
    返回 dict 或 None
    """
    data = _finnhub_get("/stock/profile2", {"symbol": ticker})
    if not data or not data.get("name"):
        return None

    profile: dict = {
        "name":        data.get("name"),
        "sector":      data.get("finnhubIndustry"),
        "industry":    data.get("finnhubIndustry"),
        "market_cap":  data.get("marketCapitalization"),  # 单位：百万美元
        "description": None,
        "employees":   data.get("employeeTotal"),
        "country":     data.get("country"),
        "website":     data.get("weburl"),
        "exchange":    data.get("exchange"),
    }

    # 分析师目标价
    pt_data = _finnhub_get("/stock/price-target", {"symbol": ticker})
    if pt_data:
        profile["analyst_target"] = pt_data.get("targetMean")
        profile["analyst_rating"] = pt_data.get("targetMean")  # Finnhub 无直接 rating 字符串

    # 分析师推荐趋势（取最新一期）
    rec_data = _finnhub_get("/stock/recommendation", {"symbol": ticker})
    if isinstance(rec_data, list) and rec_data:
        latest = rec_data[0]
        buy   = (latest.get("buy", 0) or 0) + (latest.get("strongBuy", 0) or 0)
        sell  = (latest.get("sell", 0) or 0) + (latest.get("strongSell", 0) or 0)
        hold  = latest.get("hold", 0) or 0
        total = buy + sell + hold
        if total > 0:
            if buy / total >= 0.6:
                profile["analyst_rating"] = "买入"
            elif sell / total >= 0.4:
                profile["analyst_rating"] = "卖出"
            else:
                profile["analyst_rating"] = "持有"

    return profile


def get_earnings_history(ticker: str, limit: int = 8) -> Optional[list[dict]]:
    """
    获取历史 EPS 实际/预期对比 via Finnhub earnings surprises
    返回 list[dict] 或 None
    """
    data = _finnhub_get("/stock/earnings", {"symbol": ticker})
    if not isinstance(data, list) or not data:
        return None
    records = []
    for item in data[:limit]:
        records.append({
            "date":              item.get("period", "--"),
            "eps_actual":        item.get("actual"),
            "eps_estimated":     item.get("estimate"),
            "revenue_actual":    None,
            "revenue_estimated": None,
        })
    return records


# ── 新闻与情绪 ────────────────────────────────────────────────

def get_news(ticker: str, limit: int = 20) -> list[dict]:
    """
    获取个股新闻 via Finnhub company-news（直接 REST，无需 OpenBB）
    返回 list[dict]，失败返回空列表
    """
    from datetime import date, timedelta
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    data = _finnhub_get("/company-news", {
        "symbol": ticker, "from": week_ago, "to": today
    })
    if not isinstance(data, list):
        return []

    records = []
    for item in data[:limit]:
        records.append({
            "headline": item.get("headline", ""),
            "summary":  item.get("summary", ""),
            "url":      item.get("url", ""),
            "datetime": str(item.get("datetime", "--")),
            "source":   item.get("source", ""),
        })
    logger.debug(f"Finnhub 新闻 {ticker}：{len(records)} 条")
    return records


# ── 期权数据 ──────────────────────────────────────────────────

def get_options_chain(ticker: str) -> Optional[object]:
    """
    获取期权链 via CBOE（无需 API Key）
    返回 OBBject 或 None
    """
    obb = _get_obb()
    if obb is None:
        return None

    try:
        result = obb.derivatives.options.chains(symbol=ticker, provider="cboe")
        if result and result.results:
            return result
    except Exception as e:
        logger.debug(f"期权链 {ticker} 失败：{e}")

    return None


# ── 宏观数据 ──────────────────────────────────────────────────

def get_macro_indicator(series_id: str, limit: int = 60) -> Optional[object]:
    """
    获取 FRED 宏观指标（无需 API Key）
    series_id 示例：FEDFUNDS（联邦基金利率）、T10Y2Y（收益率曲线）
    返回 OBBject 或 None
    """
    obb = _get_obb()
    if obb is None:
        return None

    try:
        result = obb.economy.fred_series(symbol=series_id, limit=limit, provider="fred")
        if result and result.results:
            return result
    except Exception as e:
        logger.debug(f"宏观数据 {series_id} 失败：{e}")

    return None


# ── 连接测试 ──────────────────────────────────────────────────

def test_connection() -> dict[str, bool]:
    """
    测试各数据源连通性
    返回 {provider_name: True/False}
    """
    results = {}

    # yfinance（无需 Key，测试基础连通）
    try:
        r = get_price_history("AAPL", "2024-01-01", "2024-01-05", ["yfinance"])
        results["yfinance"] = r is not None
    except Exception:
        results["yfinance"] = False

    # FMP
    try:
        r = get_company_profile("AAPL")
        results["fmp"] = r is not None and r.get("name") is not None
    except Exception:
        results["fmp"] = False

    # 新闻（benzinga）
    try:
        news = get_news("AAPL", limit=1)
        results["benzinga"] = len(news) > 0
    except Exception:
        results["benzinga"] = False

    # Alpha Vantage
    try:
        r = get_price_history("AAPL", "2024-01-01", "2024-01-05", ["alpha_vantage"])
        results["alpha_vantage"] = r is not None
    except Exception:
        results["alpha_vantage"] = False

    logger.info(f"连接测试结果：{results}")
    return results


# ── 工具函数 ──────────────────────────────────────────────────

def _safe_float(row, field_names: list[str]) -> Optional[float]:
    """从 DataFrame 行中安全提取 float 值，尝试多个字段名"""
    import pandas as pd
    for name in field_names:
        val = row.get(name) if hasattr(row, "get") else getattr(row, name, None)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _safe_str(row, field_names: list[str]) -> Optional[str]:
    """从 DataFrame 行中安全提取 str 值，尝试多个字段名"""
    import pandas as pd
    for name in field_names:
        val = row.get(name) if hasattr(row, "get") else getattr(row, name, None)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            s = str(val).strip()
            if s and s != "nan" and s != "None":
                return s
    return None
