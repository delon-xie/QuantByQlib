"""
基本面分析器
通过 OpenBB/FMP 获取公司财务数据
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


@dataclass
class FundamentalData:
    """基本面数据结构"""
    # 公司概况
    name:           Optional[str]   = None
    sector:         Optional[str]   = None
    industry:       Optional[str]   = None
    market_cap:     Optional[float] = None
    employees:      Optional[float] = None
    description:    Optional[str]   = None
    website:        Optional[str]   = None
    exchange:       Optional[str]   = None

    # 估值指标
    pe_ratio:       Optional[float] = None
    pb_ratio:       Optional[float] = None
    ps_ratio:       Optional[float] = None
    ev_ebitda:      Optional[float] = None

    # 盈利能力
    roe:            Optional[float] = None
    roa:            Optional[float] = None
    gross_margin:   Optional[float] = None
    operating_margin:Optional[float]= None
    net_margin:     Optional[float] = None

    # 增长指标
    revenue_growth: Optional[float] = None
    eps_growth:     Optional[float] = None

    # 财务健康
    debt_to_equity: Optional[float] = None
    current_ratio:  Optional[float] = None

    # 分析师评级
    analyst_target: Optional[float] = None
    analyst_rating: Optional[str]   = None

    # EPS 历史（最近 4-8 季度）
    earnings_history: list[dict] = field(default_factory=list)

    def analyst_signal(self) -> Optional[str]:
        """根据分析师目标价与当前价的偏差推断信号"""
        # 由外部调用方传入当前价后判断
        return self.analyst_rating


class FundamentalAnalyzer:
    """基本面数据获取与分析"""

    def analyze(self, ticker: str, current_price: Optional[float] = None) -> FundamentalData:
        """
        获取 ticker 的完整基本面数据
        所有子获取失败时对应字段为 None，不抛异常
        """
        ticker = ticker.upper().strip()
        data = FundamentalData()

        # 公司概况（FMP）
        try:
            from data.openbb_client import get_company_profile
            profile = get_company_profile(ticker)
            if profile:
                data.name        = profile.get("name")
                data.sector      = profile.get("sector")
                data.industry    = profile.get("industry")
                data.market_cap  = profile.get("market_cap")
                data.employees   = profile.get("employees")
                data.description = profile.get("description")
                data.website     = profile.get("website")
                data.exchange    = profile.get("exchange")
                data.analyst_target = profile.get("analyst_target")
                data.analyst_rating = profile.get("analyst_rating")
        except Exception as e:
            logger.debug(f"公司概况获取失败 {ticker}：{e}")

        # 估值/盈利指标（FMP）
        try:
            from data.openbb_client import get_fundamental_metrics
            metrics = get_fundamental_metrics(ticker)
            if metrics:
                data.pe_ratio        = metrics.get("pe_ratio")
                data.pb_ratio        = metrics.get("pb_ratio")
                data.ps_ratio        = metrics.get("ps_ratio")
                data.roe             = metrics.get("roe")
                data.roa             = metrics.get("roa")
                data.gross_margin    = metrics.get("gross_margin")
                data.operating_margin= metrics.get("operating_margin")
                data.net_margin      = metrics.get("net_margin")
                data.revenue_growth  = metrics.get("revenue_growth")
                data.eps_growth      = metrics.get("eps_growth")
                data.debt_to_equity  = metrics.get("debt_to_equity")
                data.current_ratio   = metrics.get("current_ratio")
        except Exception as e:
            logger.debug(f"基本面指标获取失败 {ticker}：{e}")

        # EPS 历史（FMP）
        try:
            from data.openbb_client import get_earnings_history
            earnings = get_earnings_history(ticker, limit=8)
            if earnings:
                data.earnings_history = earnings
        except Exception as e:
            logger.debug(f"EPS 历史获取失败 {ticker}：{e}")

        # FMP 全部失败时，用 yfinance 免费 fallback
        if data.pe_ratio is None and data.market_cap is None:
            self._fill_from_yfinance(ticker, data)

        self._sanitize(data, ticker)
        logger.debug(f"基本面分析完成：{ticker} — PE={data.pe_ratio} 市值={data.market_cap}")
        return data

    # ── 数据清洗 ──────────────────────────────────────────────

    @staticmethod
    def _sanitize(data: "FundamentalData", ticker: str) -> None:
        """
        修正/过滤基本面指标的单位和合理性：
        - FMP API 部分字段以百分比数值（如 43.25）而非小数（0.4325）返回
          → 若值在 1~500 之间自动除以 100 换算
        - 仍超出合理范围则丢弃，避免向 LLM 传递错误数据
        """
        # 利润率类：期望小数（-1 ~ 1）；FMP 可能返回百分比（1 ~ 100）
        for attr in ("roe", "roa", "gross_margin", "operating_margin", "net_margin"):
            val = getattr(data, attr, None)
            if val is None:
                continue
            if 1.0 < abs(val) <= 500.0:
                # 疑似百分比格式，自动换算
                converted = val / 100.0
                logger.debug(
                    f"[Fundamental] {ticker}.{attr} 单位换算：{val:.2f} → {converted:.4f}"
                    f"（FMP 返回百分比格式）"
                )
                setattr(data, attr, converted)
                val = converted
            if abs(val) > 5.0:
                # 换算后仍超出 ±500%，视为数据错误
                logger.warning(
                    f"[Fundamental] {ticker}.{attr}={val*100:.0f}% 超出合理范围（±500%），已丢弃"
                )
                setattr(data, attr, None)

        # PE/PB/PS：合法范围（负 PE 表示亏损）
        for attr, lo, hi in [
            ("pe_ratio", -1000, 1000),
            ("pb_ratio", 0, 200),
            ("ps_ratio", 0, 200),
        ]:
            val = getattr(data, attr, None)
            if val is not None and not (lo <= val <= hi):
                logger.warning(
                    f"[Fundamental] {ticker}.{attr}={val:.1f} 超出合理范围，已丢弃"
                )
                setattr(data, attr, None)

        # 增长率：期望小数（-1 ~ 5）；FMP 可能返回百分比
        for attr in ("revenue_growth", "eps_growth"):
            val = getattr(data, attr, None)
            if val is None:
                continue
            if 1.0 < abs(val) <= 1000.0:
                converted = val / 100.0
                logger.debug(
                    f"[Fundamental] {ticker}.{attr} 单位换算：{val:.2f} → {converted:.4f}"
                )
                setattr(data, attr, converted)
                val = converted
            if abs(val) > 10.0:
                logger.warning(
                    f"[Fundamental] {ticker}.{attr}={val*100:.0f}% 超出合理范围，已丢弃"
                )
                setattr(data, attr, None)

    def _fill_from_yfinance(self, ticker: str, data: FundamentalData) -> None:
        """用 yfinance .info 填充基本面（免费，无需 API Key）"""
        try:
            import yfinance as yf
            from core.app_state import get_state
            reg = get_state().reg
            from core.qlibhelper import normalize_cn_tickers
            if reg == "cn":
                ticker = normalize_cn_tickers(ticker)[0]
            info = yf.Ticker(ticker).info
            if not info or info.get("trailingPE") is None and info.get("marketCap") is None:
                return

            # 公司概况
            if data.name     is None: data.name     = info.get("longName")
            if data.sector   is None: data.sector   = info.get("sector")
            if data.industry is None: data.industry = info.get("industry")
            if data.market_cap is None: data.market_cap = info.get("marketCap")
            if data.employees  is None: data.employees  = info.get("fullTimeEmployees")
            if data.website    is None: data.website    = info.get("website")
            if data.exchange   is None: data.exchange   = info.get("exchange")

            # 估值
            if data.pe_ratio is None: data.pe_ratio = info.get("trailingPE")
            if data.pb_ratio is None: data.pb_ratio = info.get("priceToBook")
            if data.ps_ratio is None: data.ps_ratio = info.get("priceToSalesTrailing12Months")

            # 盈利能力
            if data.roe              is None: data.roe              = info.get("returnOnEquity")
            if data.roa              is None: data.roa              = info.get("returnOnAssets")
            if data.gross_margin     is None: data.gross_margin     = info.get("grossMargins")
            if data.operating_margin is None: data.operating_margin = info.get("operatingMargins")
            if data.net_margin       is None: data.net_margin       = info.get("profitMargins")

            # 增长
            if data.revenue_growth is None: data.revenue_growth = info.get("revenueGrowth")
            if data.eps_growth     is None: data.eps_growth     = info.get("earningsGrowth")

            # 财务健康
            if data.debt_to_equity is None: data.debt_to_equity = info.get("debtToEquity")
            if data.current_ratio  is None: data.current_ratio  = info.get("currentRatio")

            # 分析师
            if data.analyst_target is None: data.analyst_target = info.get("targetMeanPrice")
            if data.analyst_rating is None:
                rec = info.get("recommendationKey", "")
                rating_map = {
                    "strong_buy": "强烈买入", "buy": "买入",
                    "hold": "持有", "sell": "卖出", "strong_sell": "强烈卖出",
                }
                data.analyst_rating = rating_map.get(rec.lower(), rec) if rec else None

            # debtToEquity 在 yfinance 是百分比形式（如 3.063 = 306.3%），换算为小数
            if data.debt_to_equity is not None and data.debt_to_equity > 10:
                data.debt_to_equity = data.debt_to_equity / 100

            logger.debug(f"yfinance 基本面 fallback 成功：{ticker} PE={data.pe_ratio}")
        except Exception as e:
            logger.debug(f"yfinance 基本面 fallback 失败 {ticker}：{e}")

    def get_valuation_signals(self, data: FundamentalData) -> list[dict]:
        """
        将基本面数据转化为买卖信号列表（与行业基准比较）
        返回 [{label, value_str, signal_text, signal_type}]
        """
        signals = []

        # PE 分析（以 S&P500 平均 ~22 为基准）
        if data.pe_ratio is not None:
            pe = data.pe_ratio
            if pe <= 0:
                sig, stype = "亏损/负PE", "bearish"
            elif pe < 12:
                sig, stype = "低估", "bullish"
            elif pe < 25:
                sig, stype = "合理", "neutral"
            elif pe < 40:
                sig, stype = "偏高", "bearish"
            else:
                sig, stype = "高估", "bearish"
            signals.append({"label": "PE 市盈率", "value_str": f"{pe:.1f}x",
                             "signal_text": sig, "signal_type": stype})

        # PB 分析
        if data.pb_ratio is not None:
            pb = data.pb_ratio
            if pb < 1:
                sig, stype = "低于账面", "bullish"
            elif pb < 3:
                sig, stype = "合理", "neutral"
            else:
                sig, stype = "溢价", "bearish"
            signals.append({"label": "PB 市净率", "value_str": f"{pb:.1f}x",
                             "signal_text": sig, "signal_type": stype})

        # ROE 分析
        if data.roe is not None:
            roe = data.roe
            if roe > 0.20:
                sig, stype = "盈利能力强", "bullish"
            elif roe > 0.10:
                sig, stype = "良好", "neutral"
            elif roe > 0:
                sig, stype = "偏弱", "bearish"
            else:
                sig, stype = "亏损", "bearish"
            signals.append({"label": "ROE 净资产收益", "value_str": f"{roe*100:.1f}%",
                             "signal_text": sig, "signal_type": stype})

        # 净利率
        if data.net_margin is not None:
            nm = data.net_margin
            if nm > 0.20:
                sig, stype = "高利润率", "bullish"
            elif nm > 0.05:
                sig, stype = "正常", "neutral"
            elif nm > 0:
                sig, stype = "偏低", "bearish"
            else:
                sig, stype = "亏损", "bearish"
            signals.append({"label": "净利润率", "value_str": f"{nm*100:.1f}%",
                             "signal_text": sig, "signal_type": stype})

        # 收入增长
        if data.revenue_growth is not None:
            rg = data.revenue_growth
            if rg > 0.20:
                sig, stype = "高速增长", "bullish"
            elif rg > 0.05:
                sig, stype = "稳健增长", "neutral"
            elif rg > 0:
                sig, stype = "缓慢增长", "neutral"
            else:
                sig, stype = "收入下滑", "bearish"
            signals.append({"label": "收入增速", "value_str": f"{rg*100:.1f}%",
                             "signal_text": sig, "signal_type": stype})

        # 负债率
        if data.debt_to_equity is not None:
            de = data.debt_to_equity
            if de < 0.3:
                sig, stype = "低负债", "bullish"
            elif de < 1.0:
                sig, stype = "适度负债", "neutral"
            else:
                sig, stype = "高负债", "bearish"
            signals.append({"label": "债务/净资产", "value_str": f"{de:.2f}x",
                             "signal_text": sig, "signal_type": stype})

        return signals
