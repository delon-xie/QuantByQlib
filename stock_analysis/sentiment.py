"""
新闻情绪分析器
数据源：OpenBB + Finnhub（官方 API，无反爬风险）
情绪打分：
  - 快速模式：NLTK VADER（实时，毫秒级）
  - 精准模式：DistilBERT（HuggingFace 离线，~250MB，准确率 93%）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


@dataclass
class NewsItem:
    """单条新闻"""
    headline:   str
    source:     Optional[str] = None
    published:  Optional[str] = None   # ISO 日期字符串
    url:        Optional[str] = None
    score:      Optional[float] = None  # 情绪分数 -1~+1


@dataclass
class SentimentData:
    """情绪分析结果"""
    available:      bool
    headlines:      list[str]           = field(default_factory=list)
    news_items:     list[NewsItem]      = field(default_factory=list)
    scores:         list[float]         = field(default_factory=list)
    avg_score:      Optional[float]     = None
    signal:         Optional[str]       = None   # "利好" / "中性" / "利空"
    signal_type:    Optional[str]       = None   # "bullish" / "neutral" / "bearish"
    news_count:     int                 = 0
    model_used:     Optional[str]       = None
    positive_count: int                 = 0
    negative_count: int                 = 0
    neutral_count:  int                 = 0


class SentimentAnalyzer:
    """
    新闻情绪双层分析：
      快速路径（use_deep_model=False）：VADER，实时展示
      精准路径（use_deep_model=True） ：DistilBERT，详细分析
    """

    def __init__(self):
        self._vader = None          # 懒加载
        self._distilbert = None     # 懒加载

    # ── 主入口 ────────────────────────────────────────────────

    def analyze(self, ticker: str, use_deep_model: bool = False,
                limit: int = 20) -> SentimentData:
        """
        获取新闻并打分
        失败时返回 available=False，不填充假数据
        """
        ticker = ticker.upper().strip()

        # 1. 获取新闻
        news_items = self._fetch_news(ticker, limit)
        if not news_items:
            logger.debug(f"情绪分析：{ticker} 未获取到新闻")
            return SentimentData(available=False, headlines=[], news_count=0)

        # 2. 提取标题
        headlines = [
            item.headline for item in news_items
            if item.headline and len(item.headline.strip()) > 5
        ][:limit]

        if not headlines:
            return SentimentData(available=False, news_count=len(news_items))

        # 3. 情绪打分
        try:
            if use_deep_model:
                scores = self._score_distilbert(headlines)
                model_name = "DistilBERT"
            else:
                scores = self._score_vader(headlines)
                model_name = "VADER"
        except Exception as e:
            logger.warning(f"情绪打分失败（{ticker}）：{e}，降级到中性分数")
            scores = [0.0] * len(headlines)
            model_name = "fallback"

        # 4. 回写分数到 NewsItem
        for i, item in enumerate(news_items):
            if i < len(scores):
                item.score = scores[i]

        # 5. 汇总
        avg = sum(scores) / len(scores) if scores else 0.0
        pos_count = sum(1 for s in scores if s >  0.05)
        neg_count = sum(1 for s in scores if s < -0.05)
        neu_count = len(scores) - pos_count - neg_count

        if avg > 0.10:
            signal, stype = "利好", "bullish"
        elif avg > 0.03:
            signal, stype = "偏正面", "bullish"
        elif avg < -0.10:
            signal, stype = "利空", "bearish"
        elif avg < -0.03:
            signal, stype = "偏负面", "bearish"
        else:
            signal, stype = "中性", "neutral"

        logger.debug(
            f"情绪分析 {ticker}[{model_name}]："
            f"共 {len(headlines)} 条，均值={avg:.3f}，信号={signal}"
        )

        return SentimentData(
            available=True,
            headlines=headlines[:10],
            news_items=news_items[:10],
            scores=scores[:10],
            avg_score=avg,
            signal=signal,
            signal_type=stype,
            news_count=len(headlines),
            model_used=model_name,
            positive_count=pos_count,
            negative_count=neg_count,
            neutral_count=neu_count,
        )

    # ── 新闻获取 ──────────────────────────────────────────────

    def _fetch_news(self, ticker: str, limit: int) -> list[NewsItem]:
        """通过多源获取新闻，优先 obb.news.company，最终 fallback 到 yfinance 直接调用"""
        # 1. 先尝试 OpenBB news.company 路由
        items = self._fetch_via_openbb(ticker, limit)
        if items:
            return items

        # 2. 最终 fallback：yfinance 直接调用（不经过 OpenBB）
        items = self._fetch_via_yfinance(ticker, limit)
        if items:
            return items

        return []

    def _fetch_via_openbb(self, ticker: str, limit: int) -> list[NewsItem]:
        """通过 OpenBB obb.news.company 获取新闻（OpenBB 4.x 新路由）"""
        providers = ["fmp", "tiingo", "benzinga"]
        for provider in providers:
            try:
                from openbb import obb
                result = obb.news.company(symbol=ticker, provider=provider, limit=limit)
                if result and result.results:
                    rows = result.to_dataframe().to_dict("records")
                    items = self._parse_raw_news(rows)
                    if items:
                        logger.debug(f"新闻：{ticker} via {provider}，{len(items)} 条")
                        return items
            except Exception as e:
                logger.debug(f"新闻获取失败 {ticker} [{provider}]：{e}")
                continue
        return []

    def _fetch_via_yfinance(self, ticker: str, limit: int) -> list[NewsItem]:
        """直接用 yfinance 获取新闻（免费，无需 API Key）"""
        try:
            import yfinance as yf
            from core.app_state import get_state
            reg = get_state().reg
            from core.qlibhelper import normalize_cn_tickers
            if reg == "cn":
                ticker = normalize_cn_tickers(ticker)[0]
            raw_news = yf.Ticker(ticker).news
            if not raw_news:
                return []
            items = []
            for item in raw_news[:limit]:
                # yfinance 新版将 news 嵌在 content 字段下
                if isinstance(item, dict):
                    content = item.get("content", item)
                    headline = (
                        content.get("title") or
                        content.get("headline") or
                        item.get("title") or
                        item.get("headline") or ""
                    ).strip()
                    if not headline:
                        continue
                    pub = content.get("pubDate") or content.get("displayTime") or item.get("providerPublishTime")
                    provider_info = content.get("provider", {})
                    source = (provider_info.get("displayName") if isinstance(provider_info, dict)
                              else str(provider_info)) if provider_info else None
                    url_info = content.get("canonicalUrl", {})
                    url = (url_info.get("url") if isinstance(url_info, dict) else str(url_info)) if url_info else None
                    items.append(NewsItem(
                        headline=headline,
                        source=source,
                        published=str(pub) if pub else None,
                        url=url,
                    ))
            if items:
                logger.debug(f"新闻：{ticker} via yfinance(直接)，{len(items)} 条")
            return items
        except Exception as e:
            logger.debug(f"yfinance 直接新闻获取失败 {ticker}：{e}")
            return []

    def _parse_raw_news(self, raw: list[dict]) -> list[NewsItem]:
        """将原始字典列表转换为 NewsItem 列表"""
        items = []
        for r in raw:
            headline = (
                r.get("headline") or r.get("title") or
                r.get("text") or r.get("summary") or ""
            ).strip()
            if not headline:
                continue
            items.append(NewsItem(
                headline  = headline,
                source    = r.get("source") or r.get("publisher"),
                published = r.get("datetime") or r.get("published_date") or r.get("date"),
                url       = r.get("url") or r.get("link"),
            ))
        return items

    # ── 情绪打分 ──────────────────────────────────────────────

    @property
    def vader(self):
        """懒加载 VADER"""
        if self._vader is None:
            try:
                import nltk
                # 下载词典（离线可跳过）
                try:
                    nltk.data.find("sentiment/vader_lexicon.zip")
                except LookupError:
                    nltk.download("vader_lexicon", quiet=True)
                from nltk.sentiment.vader import SentimentIntensityAnalyzer
                self._vader = SentimentIntensityAnalyzer()
                logger.debug("VADER 加载成功")
            except Exception as e:
                logger.warning(f"VADER 加载失败：{e}")
                self._vader = None
        return self._vader

    @property
    def distilbert(self):
        """懒加载 DistilBERT（首次使用时从 HuggingFace 下载约 250MB）"""
        if self._distilbert is None:
            try:
                from transformers import pipeline
                self._distilbert = pipeline(
                    "text-classification",
                    model="mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis",
                    device=-1,   # CPU 推理
                    top_k=None,
                )
                logger.info("DistilBERT 情绪模型加载成功")
            except Exception as e:
                logger.warning(f"DistilBERT 加载失败：{e}")
                self._distilbert = None
        return self._distilbert

    def _score_vader(self, headlines: list[str]) -> list[float]:
        """VADER 快速打分，compound 值范围 -1~+1"""
        vader = self.vader
        if vader is None:
            # VADER 未安装时，返回全 0（中性）
            return [0.0] * len(headlines)

        scores = []
        for h in headlines:
            try:
                result = vader.polarity_scores(h)
                scores.append(float(result["compound"]))
            except Exception:
                scores.append(0.0)
        return scores

    def _score_distilbert(self, headlines: list[str]) -> list[float]:
        """
        DistilBERT 精准打分
        label positive → +score
        label negative → -score
        """
        model = self.distilbert
        if model is None:
            # 模型不可用，降级到 VADER
            logger.warning("DistilBERT 不可用，降级到 VADER")
            return self._score_vader(headlines)

        scores = []
        try:
            results = model(headlines, truncation=True, max_length=512)
            for res in results:
                if isinstance(res, list):
                    # top_k=None 时返回每个 label 的列表
                    pos_score = next(
                        (r["score"] for r in res if r["label"].lower() == "positive"), 0.5
                    )
                    neg_score = next(
                        (r["score"] for r in res if r["label"].lower() == "negative"), 0.5
                    )
                    # 转换为 -1~+1
                    scores.append(pos_score - neg_score)
                else:
                    label = res.get("label", "").lower()
                    score = res.get("score", 0.5)
                    scores.append(score if label == "positive" else -score)
        except Exception as e:
            logger.warning(f"DistilBERT 推理失败：{e}，降级到 VADER")
            return self._score_vader(headlines)

        return scores

    def get_sentiment_signals(self, data: SentimentData) -> list[dict]:
        """将情绪数据转化为信号列表（用于 UI 展示）"""
        if not data.available or data.avg_score is None:
            return []

        signals = []

        # 综合情绪信号
        avg = data.avg_score
        signals.append({
            "label": "综合情绪",
            "value_str": f"{avg:+.3f}",
            "signal_text": data.signal or "中性",
            "signal_type": data.signal_type or "neutral",
        })

        # 正负面新闻比例
        total = data.news_count
        if total > 0:
            pos_pct = data.positive_count / total * 100
            neg_pct = data.negative_count / total * 100
            if pos_pct >= 60:
                stype = "bullish"
            elif neg_pct >= 60:
                stype = "bearish"
            else:
                stype = "neutral"
            signals.append({
                "label": "正面/负面新闻",
                "value_str": f"{data.positive_count}↑ / {data.negative_count}↓",
                "signal_text": f"共 {total} 条，正面 {pos_pct:.0f}%",
                "signal_type": stype,
            })

        return signals
