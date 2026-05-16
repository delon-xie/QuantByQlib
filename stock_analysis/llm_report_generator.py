"""
LLM 驱动的个股分析报告生成器

基于 StockReport 中的技术面/基本面/情绪分析结果，调用 Claude API
生成结构化自然语言决策报告（Markdown 格式）。

报告结构：
  1. 核心结论   — 一句话买入/观望/卖出信号及理由
  2. 技术面解读 — 基于六维评分 + Alpha158 的趋势分析
  3. 基本面评估 — PE/ROE/增长率等关键指标解读
  4. 情绪与新闻 — 市场情绪及近期重要消息
  5. 风险提示   — 当前追涨风险/超买超卖等警示
  6. 作战计划   — 建议入场区间、止损位、持仓比例

使用方式：
  # 同步（阻塞）
  report_md = LLMReportGenerator().generate(stock_report)

  # 流式（用于 UI 实时更新）
  for chunk in LLMReportGenerator().generate_stream(stock_report):
      text_widget.append(chunk)
"""
from __future__ import annotations

import os
from typing import Iterator, Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from stock_analysis.stock_analyzer import StockReport


# ── 配置 ─────────────────────────────────────────────────────

DEFAULT_MODEL         = "claude-opus-4-6"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_TOKENS    = 1500

_SYSTEM_PROMPT = """你是一位专业的美股量化投资分析师，擅长将技术分析、基本面指标和市场情绪综合成清晰可执行的交易建议。

【数据诚信原则——最高优先级，不得违反】
- 严禁虚构任何数据、数字、事件或新闻。所有数据必须来自本次提供的上下文信息。
- 若某项数据未在输入中提供（如基本面指标、新闻条目），必须明确注明"数据不足"或"暂无数据"，禁止推测或捏造。
- 入场价、止损价须基于输入中的实际价格和技术指标计算得出，不得凭空给出。
- 不得引用任何未在输入中出现的具体事件、财报数据、机构评级或新闻内容。

输出要求：
- 用中文输出
- 报告简洁专业，每个章节控制在 3-5 句话
- 风险提示要客观，不要过度乐观
- 格式：使用 Markdown 标题和要点列表"""

# Claude 不可用时的触发条件
_CLAUDE_FALLBACK_CODES = {"529", "overloaded", "529 overloaded", "service_unavailable", "503"}


def _is_claude_unavailable(err: Exception) -> bool:
    """判断异常是否属于 Claude 服务不可用（过载/宕机），应触发 DeepSeek 降级"""
    msg = str(err).lower()
    return any(k in msg for k in ("529", "overloaded", "service_unavailable", "503", "rate_limit"))


# ── 主类 ─────────────────────────────────────────────────────

class LLMReportGenerator:
    """
    LLM 个股分析报告生成器。
    主力：Claude（ANTHROPIC_API_KEY）
    降级：DeepSeek（DEEPSEEK_API_KEY），当 Claude 过载/不可用时自动切换。
    """

    def __init__(self, model: str | None = None, max_tokens: int = DEFAULT_MAX_TOKENS):
        self._model      = model or self._resolve_model()
        self._max_tokens = max_tokens
        self._client     = None   # 懒加载（Anthropic）
        self._ds_client  = None   # 懒加载（DeepSeek）

    # ── 公开接口 ──────────────────────────────────────────────

    def generate(self, report: "StockReport") -> str:
        """
        同步生成完整报告（阻塞）。
        返回 Markdown 字符串，失败时返回错误占位文本。
        """
        try:
            client = self._get_client()
            prompt = self._build_prompt(report)
            response = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"[LLMReport] {report.ticker} 报告生成失败：{e}")
            return f"_AI 报告生成失败：{e}_\n\n请检查 ANTHROPIC_API_KEY 是否已配置。"

    def generate_stream(self, report: "StockReport") -> Iterator[str]:
        """
        流式生成报告：优先 Claude，不可用时自动降级到 DeepSeek。
        每次 yield 一个文本块，异常向上抛出由 worker 处理。
        """
        prompt = self._build_prompt(report)

        # ── 尝试 Claude ──
        claude_err: Exception | None = None
        try:
            client = self._get_client()
            with client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text_chunk in stream.text_stream:
                    yield text_chunk
            return   # Claude 成功，直接返回
        except Exception as e:
            claude_err = e
            if _is_claude_unavailable(e):
                logger.warning(
                    f"[LLMReport] Claude 不可用（{e}），自动切换到 DeepSeek..."
                )
            else:
                logger.warning(f"[LLMReport] Claude 报告生成失败：{e}")
                #key错误 也进行降级
                #raise   # 非过载错误（如 Key 错误），直接抛出，不降级

        # ── 降级到 DeepSeek ──
        #yield "\n\n> ⚠️ Claude 服务暂时不可用，已自动切换到 DeepSeek 生成报告...\n\n"
        logger.warning(f"[LLMReport] ⚠️ Claude 服务暂时不可用，已自动切换到 DeepSeek 生成报告...")
        try:
            yield from self._stream_deepseek(prompt)
        except Exception as ds_err:
            logger.warning(f"[LLMReport] DeepSeek 也失败了：{ds_err}")
            # 两个都失败，把原始 Claude 错误抛出
            raise claude_err from ds_err

    # ── Prompt 构建 ───────────────────────────────────────────

    def _build_prompt(self, report: "StockReport") -> str:
        """将 StockReport 数据序列化为 LLM 输入 prompt"""
        sections: list[str] = [f"## 请为 {report.ticker}（{report.company_name}）生成一份投资分析报告\n"]

        # 当前价格
        price = report.current_price
        change = report.change_pct
        if price:
            change_str = f"（今日 {change*100:+.2f}%）" if change is not None else ""
            sections.append(f"**当前价格**：${price:,.2f} {change_str}\n")

        # 综合评分
        overall = report.overall
        if overall.available:
            sections.append(f"**综合评分**：{overall.score}/100 → {overall.grade}")
            if overall.ohlcv_score is not None:
                sections.append(f"  - 六维技术评分：{overall.ohlcv_score:.1f}/100")
            if overall.tech_score is not None:
                sections.append(f"  - Alpha158 技术分：{overall.tech_score*100:.0f}/100")
            if overall.fund_score is not None:
                sections.append(f"  - 基本面分：{overall.fund_score*100:.0f}/100")
            if overall.senti_score is not None:
                sections.append(f"  - 情绪分：{overall.senti_score*100:.0f}/100")
            sections.append("")

        # 六维技术评分详情
        tech_score = report.tech_score
        if tech_score and tech_score.available:
            sections.append("### 六维技术评分")
            sections.append(f"- **综合**：{tech_score.total_score:.1f}/100（{tech_score.signal}）")
            if tech_score.chase_warning:
                sections.append(f"- ⚠️ **追涨警告**：价格偏离 MA20 达 {tech_score.deviation_pct:+.1f}%，高于 5% 阈值")
            for dim in tech_score.to_dimension_list():
                sections.append(f"- {dim['name']}（{dim['weight']}）：{dim['score']:.0f}分")
            _append_optional(sections, "MA5/MA20/MA60",
                             _ma_str(price, tech_score.ma5, tech_score.ma20, tech_score.ma60))
            _append_optional(sections, "MACD 状态", tech_score.macd_cross)
            _append_optional(sections, "RSI(6/12/24)",
                             _rsi_str(tech_score.rsi6, tech_score.rsi12, tech_score.rsi24))
            _append_optional(sections, "布林带 %B",
                             f"{tech_score.bband_pct:.2f}（0=下轨，1=上轨）" if tech_score.bband_pct is not None else None)
            sections.append("")

        # 基本面
        fund = report.fundamental
        if fund:
            sections.append("### 基本面指标")
            _append_optional(sections, "公司",    fund.name)
            _append_optional(sections, "行业",    fund.sector)
            # 利润率类：仅在合理范围内（-500% ~ +500%）输出，否则省略
            _append_optional(sections, "PE（TTM）", f"{fund.pe_ratio:.1f}x"
                             if fund.pe_ratio and -1000 < fund.pe_ratio < 1000 else None)
            _append_optional(sections, "PB",       f"{fund.pb_ratio:.2f}x"
                             if fund.pb_ratio and 0 < fund.pb_ratio < 200 else None)
            _append_optional(sections, "ROE（TTM）", f"{fund.roe*100:.1f}%"
                             if fund.roe and abs(fund.roe) < 5.0 else None)
            _append_optional(sections, "净利率",   f"{fund.net_margin*100:.1f}%"
                             if fund.net_margin and abs(fund.net_margin) < 5.0 else None)
            _append_optional(sections, "毛利率",   f"{fund.gross_margin*100:.1f}%"
                             if fund.gross_margin and 0 <= fund.gross_margin <= 1.0 else None)
            _append_optional(sections, "收入增长（YoY）", f"{fund.revenue_growth*100:.1f}%"
                             if fund.revenue_growth and abs(fund.revenue_growth) < 10.0 else None)
            _append_optional(sections, "分析师评级", fund.analyst_rating)
            _append_optional(sections, "分析师目标价", f"${fund.analyst_target:.2f}" if fund.analyst_target else None)
            sections.append("")

        # 情绪
        senti = report.sentiment
        if senti and senti.available:
            sections.append("### 市场情绪")
            _append_optional(sections, "情绪信号", senti.signal)
            _append_optional(sections, "情绪均分", f"{senti.avg_score:+.3f}" if senti.avg_score is not None else None)
            sections.append(f"- 分析新闻数：{senti.news_count} 条"
                            f"（正面 {senti.positive_count} / 负面 {senti.negative_count} / 中性 {senti.neutral_count}）")
            if senti.headlines:
                sections.append("- 近期新闻标题：")
                for h in senti.headlines[:3]:
                    sections.append(f"  - {h}")
            sections.append("")

        # 指令
        sections.append(
            "---\n"
            "请严格基于以上提供的数据生成报告，包含以下章节：\n"
            "1. **核心结论**（一句话信号）\n"
            "2. **技术面解读**\n"
            "3. **基本面评估**\n"
            "4. **情绪与催化剂**\n"
            "5. **风险提示**\n"
            "6. **作战计划**（入场区间、止损位、持仓建议）\n\n"
            "⚠️ 重要约束：\n"
            "- 若某章节所需数据在上方未提供，请注明「数据不足，无法评估」，禁止编造。\n"
            "- 所有价格数字必须来源于上方提供的实际数据，不得凭空生成。\n"
            "- 不得引用上方未出现的任何新闻、事件、财报或机构观点。"
        )

        return "\n".join(sections)

    # ── 私有工具 ──────────────────────────────────────────────

    def _get_client(self):
        """懒加载 Anthropic 客户端"""
        if self._client is None:
            try:
                import anthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY 未配置")
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError("请安装 anthropic SDK：pip install anthropic")
        return self._client

    def _get_deepseek_client(self):
        """懒加载 DeepSeek 客户端（OpenAI 兼容接口）"""
        if self._ds_client is None:
            try:
                import openai
            except ImportError:
                raise ImportError("请安装 openai SDK：pip install openai")
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY 未配置，无法降级到 DeepSeek")
            self._ds_client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
            )
        return self._ds_client

    def _stream_deepseek(self, prompt: str) -> Iterator[str]:
        """调用 DeepSeek 流式 API，yield 文本块"""
        client = self._get_deepseek_client()
        stream = client.chat.completions.create(
            model=DEFAULT_DEEPSEEK_MODEL,
            max_tokens=self._max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def _resolve_model(self) -> str:
        """从 app_config.yaml 读取模型配置，默认 claude-opus-4-6"""
        try:
            import yaml
            from pathlib import Path
            cfg_path = Path(__file__).parent.parent / "config" / "app_config.yaml"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                return cfg.get("llm", {}).get("model", DEFAULT_MODEL)
        except Exception:
            pass
        return DEFAULT_MODEL


# ── 工具函数 ──────────────────────────────────────────────────

def _append_optional(sections: list[str], label: str, value: Optional[str]) -> None:
    """仅当值非空时追加一行"""
    if value:
        sections.append(f"- **{label}**：{value}")


def _ma_str(price: Optional[float], ma5: Optional[float],
            ma20: Optional[float], ma60: Optional[float]) -> Optional[str]:
    if not price:
        return None
    parts = []
    if ma5:
        diff = (price / ma5 - 1) * 100
        parts.append(f"MA5 ${ma5:.2f}（{diff:+.1f}%）")
    if ma20:
        diff = (price / ma20 - 1) * 100
        parts.append(f"MA20 ${ma20:.2f}（{diff:+.1f}%）")
    if ma60:
        diff = (price / ma60 - 1) * 100
        parts.append(f"MA60 ${ma60:.2f}（{diff:+.1f}%）")
    return "，".join(parts) if parts else None


def _rsi_str(rsi6: Optional[float], rsi12: Optional[float],
             rsi24: Optional[float]) -> Optional[str]:
    parts = []
    if rsi6 is not None:
        parts.append(f"RSI6={rsi6:.1f}")
    if rsi12 is not None:
        parts.append(f"RSI12={rsi12:.1f}")
    if rsi24 is not None:
        parts.append(f"RSI24={rsi24:.1f}")
    return "，".join(parts) if parts else None
