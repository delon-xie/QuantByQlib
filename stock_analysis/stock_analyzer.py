"""
个股综合分析整合入口
并行获取：Alpha158技术信号 + K线 + 基本面 + 情绪
任一维度失败不影响其他维度展示
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from stock_analysis.alpha_reader import Alpha158Reader, TechnicalSignal  # noqa: F401
from stock_analysis.price_chart import PriceChart, ChartData
from stock_analysis.fundamental import FundamentalAnalyzer, FundamentalData
from stock_analysis.binance_analyzer import BinanceAnalyzer
from stock_analysis.sentiment import SentimentAnalyzer, SentimentData
from stock_analysis.technical_scorer import TechnicalScorer, TechnicalScore  # noqa: F401


@dataclass
class OverallScore:
    """综合评分结果"""
    score:          Optional[float]  = None   # 0-100，None = 数据不足
    grade:          Optional[str]    = None   # "强势买入" / "买入" / "持有" / "观望" / "卖出"
    grade_type:     Optional[str]    = None   # "bullish" / "neutral" / "bearish"
    tech_score:     Optional[float]  = None   # Alpha158 技术面分数 0-1
    ohlcv_score:    Optional[float]  = None   # 六维技术评分 0-100
    fund_score:     Optional[float]  = None   # 基本面分数 0-1
    senti_score:    Optional[float]  = None   # 情绪分数 0-1（归一化）
    available:      bool             = False


@dataclass
class StockReport:
    """个股综合分析报告"""
    ticker:      str
    technical:   Optional[TechnicalSignal]
    chart:       Optional[ChartData]
    fundamental: Optional[FundamentalData]
    sentiment:   Optional[SentimentData]
    tech_score:  Optional[TechnicalScore]     # 六维技术评分（新增）
    overall:     OverallScore

    @property
    def current_price(self) -> Optional[float]:
        if self.chart and self.chart.available:
            return self.chart.current_price
        return None

    @property
    def change_pct(self) -> Optional[float]:
        if self.chart and self.chart.available:
            return self.chart.change_pct
        return None

    @property
    def company_name(self) -> str:
        if self.fundamental and self.fundamental.name:
            return self.fundamental.name
        return self.ticker


class StockAnalyzer:
    """个股综合分析器：并行获取五个数据维度"""

    def __init__(self):
        from core.app_state import get_state
        self.reg = get_state().reg
        self._alpha_reader    = Alpha158Reader()
        self._price_chart     = PriceChart()
        self._fundamental     = FundamentalAnalyzer()
        self._bfundamental     = BinanceAnalyzer()
        self._sentiment       = SentimentAnalyzer()
        self._tech_scorer     = TechnicalScorer()

    def analyze(self, ticker: str,
                use_deep_sentiment: bool = False,
                price_period_days: int = 365) -> StockReport:
        """
        并行获取五个维度数据，任一失败不影响其他维度
        返回 StockReport，overall.available=False 表示数据严重不足
        """
        ticker = ticker.upper().strip()
        from core.app_state import get_state
        reg = get_state().reg
        from core.qlibhelper import normalize_cn_tickers
        if reg == "cn":
            ticker = normalize_cn_tickers(ticker)[0]
        logger.info(f"开始分析 {ticker}（并行五维度）")

        tech_result   = None
        chart_result  = None
        fund_result   = None
        senti_result  = None
        score_result  = None

        tasks = {
            "technical":   lambda: self._alpha_reader.get_technical_signal(ticker),  # type: ignore[attr-defined]
            "chart":       lambda: self._price_chart.get_chart_data(ticker, price_period_days),
            "fundamental": lambda: self._bfundamental.analyze(ticker) if self.reg == "bt" else self._fundamental.analyze(ticker),
            "sentiment":   lambda: self._sentiment.analyze(ticker, use_deep_model=use_deep_sentiment),
        }

        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="StockAnalyzer") as executor:
            futures = {executor.submit(fn): name for name, fn in tasks.items()}

            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result(timeout=30)
                    if name == "technical":
                        tech_result = result
                    elif name == "chart":
                        chart_result = result
                    elif name == "fundamental":
                        fund_result = result
                    elif name == "sentiment":
                        senti_result = result
                except Exception as e:
                    logger.warning(f"分析子任务 [{name}] 失败（{ticker}）：{e}")

        # Alpha158 无数据时，从 K线数据推算技术信号（fallback）
        if (tech_result is None or not tech_result.available) and (
            chart_result is not None and chart_result.available
        ):
            tech_result = self._tech_from_chart(ticker, chart_result)

        # 六维技术评分（基于 K线 OHLCV，独立于 Alpha158）
        if chart_result is not None and chart_result.available and not chart_result.ohlcv.empty:
            try:
                score_result = self._tech_scorer.score(ticker, chart_result.ohlcv)
            except Exception as e:
                logger.warning(f"六维技术评分失败 {ticker}：{e}")

        overall = self._calc_overall_score(tech_result, fund_result, senti_result, score_result)

        logger.info(
            f"{ticker} 分析完成：综合评分={overall.score}，"
            f"技术={'✓' if tech_result else '✗'}，"
            f"六维={score_result.total_score if score_result and score_result.available else '✗'}，"
            f"K线={'✓' if chart_result and chart_result.available else '✗'}，"
            f"基本面={'✓' if fund_result else '✗'}，"
            f"情绪={'✓' if senti_result and senti_result.available else '✗'}"
        )

        return StockReport(
            ticker=ticker,
            technical=tech_result,
            chart=chart_result,
            fundamental=fund_result,
            sentiment=senti_result,
            tech_score=score_result,
            overall=overall,
        )

    # ── 综合评分 ──────────────────────────────────────────────

    def _calc_overall_score(
        self,
        tech:       Optional[TechnicalSignal],
        fund:       Optional[FundamentalData],
        senti:      Optional[SentimentData],
        ohlcv_score: Optional[TechnicalScore] = None,
    ) -> OverallScore:
        """
        综合评分（0-100）：
          Alpha158 技术信号  25%
          六维 OHLCV 技术评分 25%（新增，来自 TechnicalScorer）
          基本面             35%（PE/成长/质量）
          情绪               15%（VADER/DistilBERT）
        任何维度为 None 时，其权重分配给其他维度
        全部为 None 时返回 available=False
        """
        ohlcv_s = (ohlcv_score.total_score / 100.0
                   if ohlcv_score and ohlcv_score.available and ohlcv_score.total_score is not None
                   else None)

        weights: dict[str, float] = {
            "tech":  0.25,
            "ohlcv": 0.25,
            "fund":  0.35,
            "senti": 0.15,
        }
        scores: dict[str, Optional[float]] = {
            "tech":  self._tech_to_score(tech),
            "ohlcv": ohlcv_s,
            "fund":  self._fund_to_score(fund),
            "senti": self._senti_to_score(senti),
        }

        # 过滤出可用的维度
        available = {k: v for k, v in scores.items() if v is not None}
        if not available:
            return OverallScore(available=False)

        # 重新分配缺失维度的权重
        total_weight = sum(weights[k] for k in available)
        if total_weight <= 0:
            return OverallScore(available=False)

        weighted_sum = sum(available[k] * weights[k] for k in available)
        normalized_score = (weighted_sum / total_weight) * 100

        # 等级映射
        if normalized_score >= 75:
            grade, gtype = "强势买入", "bullish"
        elif normalized_score >= 60:
            grade, gtype = "买入", "bullish"
        elif normalized_score >= 45:
            grade, gtype = "持有", "neutral"
        elif normalized_score >= 30:
            grade, gtype = "观望", "neutral"
        else:
            grade, gtype = "卖出", "bearish"

        return OverallScore(
            score=round(normalized_score, 1),
            grade=grade,
            grade_type=gtype,
            tech_score=scores["tech"],
            ohlcv_score=ohlcv_score.total_score if ohlcv_score and ohlcv_score.available else None,
            fund_score=scores["fund"],
            senti_score=scores["senti"],
            available=True,
        )

    def _tech_to_score(self, tech: Optional[TechnicalSignal]) -> Optional[float]:
        """Alpha158 技术信号 → 0-1 分数"""
        if tech is None or not tech.available:
            return None
        return tech.composite_score

    def _fund_to_score(self, fund: Optional[FundamentalData]) -> Optional[float]:
        """基本面数据 → 0-1 分数（综合 PE/ROE/增长/利润）"""
        if fund is None:
            return None

        sub_scores: list[float] = []

        # PE 分析（得分范围 0-1）
        if fund.pe_ratio is not None:
            pe = fund.pe_ratio
            if pe <= 0:
                sub_scores.append(0.1)
            elif pe < 12:
                sub_scores.append(0.9)
            elif pe < 20:
                sub_scores.append(0.7)
            elif pe < 30:
                sub_scores.append(0.5)
            elif pe < 50:
                sub_scores.append(0.3)
            else:
                sub_scores.append(0.1)

        # ROE
        if fund.roe is not None:
            roe = fund.roe
            if roe > 0.25:
                sub_scores.append(1.0)
            elif roe > 0.15:
                sub_scores.append(0.7)
            elif roe > 0.08:
                sub_scores.append(0.5)
            elif roe > 0:
                sub_scores.append(0.3)
            else:
                sub_scores.append(0.1)

        # 净利率
        if fund.net_margin is not None:
            nm = fund.net_margin
            if nm > 0.20:
                sub_scores.append(1.0)
            elif nm > 0.10:
                sub_scores.append(0.7)
            elif nm > 0.05:
                sub_scores.append(0.5)
            elif nm > 0:
                sub_scores.append(0.3)
            else:
                sub_scores.append(0.1)

        # 收入增长
        if fund.revenue_growth is not None:
            rg = fund.revenue_growth
            if rg > 0.25:
                sub_scores.append(1.0)
            elif rg > 0.10:
                sub_scores.append(0.7)
            elif rg > 0:
                sub_scores.append(0.5)
            else:
                sub_scores.append(0.2)

        if not sub_scores:
            return None

        return sum(sub_scores) / len(sub_scores)

    def _senti_to_score(self, senti: Optional[SentimentData]) -> Optional[float]:
        """情绪均值（-1~+1）→ 0-1 分数"""
        if senti is None or not senti.available or senti.avg_score is None:
            return None
        # 线性映射：-1 → 0，0 → 0.5，+1 → 1
        return (senti.avg_score + 1) / 2

    def _tech_from_chart(self, ticker: str, chart: ChartData) -> TechnicalSignal:
        """
        Alpha158 无数据时，从 K线数据推算基础技术信号（fallback）
        计算 MA 偏离、ATR 波动、OBV 方向等基础指标
        """
        import numpy as np
        factor_values: dict[str, float] = {}

        try:
            df = chart.ohlcv
            if df.empty or len(df) < 5:
                return TechnicalSignal(ticker=ticker, available=False)

            close  = df["close"]
            volume = df["volume"] if "volume" in df.columns else None
            price  = chart.current_price

            # 均价比（类 Alpha158 MA5/20/60）
            for n, key in [(5, "MA5"), (10, "MA10"), (20, "MA20"), (60, "MA60")]:
                if len(close) >= n:
                    ma = float(close.rolling(n).mean().iloc[-1])
                    if ma > 0:
                        factor_values[key] = price / ma  # > 1 价格偏高, < 1 偏低

            # 动量：5/20 日超额收益（相对区间涨跌幅）
            for n, key in [(5, "RESI5"), (10, "RESI10"), (20, "RESI20")]:
                if len(close) >= n + 1:
                    past = float(close.iloc[-(n + 1)])
                    if past > 0:
                        factor_values[key] = (price - past) / past

            # 相对波动率（5/20 日标准差 / 均价）
            for n, key in [(5, "RVOL5"), (20, "RVOL20")]:
                if len(close) >= n:
                    std = float(close.rolling(n).std().iloc[-1])
                    mean = float(close.rolling(n).mean().iloc[-1])
                    if mean > 0:
                        factor_values[key] = std / mean

            # MACD（12/26 EMA 差值归一化）
            if len(close) >= 26:
                ema12 = float(close.ewm(span=12, adjust=False).mean().iloc[-1])
                ema26 = float(close.ewm(span=26, adjust=False).mean().iloc[-1])
                if ema26 > 0:
                    factor_values["MACD"] = (ema12 - ema26) / ema26

            # RSI(14)
            if len(close) >= 15:
                delta = close.diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / (loss + 1e-9)
                rsi   = 100 - (100 / (1 + rs))
                factor_values["RSI"] = float(rsi.iloc[-1])

            # 量价动量（OBV 斜率，类 WVMA）
            if volume is not None and len(close) >= 6:
                sign = np.sign(close.diff().fillna(0))
                obv  = (sign * volume).cumsum()
                obv_recent = float(obv.iloc[-1])
                obv_past5  = float(obv.iloc[-6])
                obv_mean   = float(obv.abs().mean())
                if obv_mean > 0:
                    factor_values["WVMA5"] = (obv_recent - obv_past5) / obv_mean

        except Exception as e:
            logger.debug(f"K线技术指标计算失败 {ticker}：{e}")

        # 用与 Alpha158Reader 相同的评分逻辑
        from stock_analysis.alpha_reader import Alpha158Reader, _interpret_factor, DISPLAY_FACTORS
        reader = Alpha158Reader()
        signals = reader.get_factor_signals(factor_values)

        composite = None
        if signals:
            score = sum(
                1 if s["signal_type"] == "bullish" else
                (-1 if s["signal_type"] == "bearish" else 0)
                for s in signals
            )
            composite = round((score + len(signals)) / (2 * len(signals)), 3)

        return TechnicalSignal(
            ticker=ticker,
            factor_values=factor_values,
            composite_score=composite,
            available=bool(factor_values),
        )
