"""
量化选股页面
- 5种 Qlib 策略卡片选择
- 参数配置
- 运行控制（开始/停止）
- 进度显示
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QFrame, QProgressBar,
    QSizePolicy, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from ui.theme import COLORS
from core.app_state import get_state
from ui.components.instrument_combobox import InstrumentComboBox

# 策略定义
STRATEGIES = [
    {
        "key":   "deep_learning",
        "name":  "深度学习集成",
        "icon":  "🧠",
        "model": "Qlib LSTM（Alpha158，2层，hidden=64）",
        "desc":  "LSTM 时序模型捕捉价量非线性关系，适合中长期趋势跟踪",
        "risk":  "平衡型",
        "risk_color": COLORS["warning"],
        "topk":  50,
        "tags":  ["训练2年", "CPU约5-8分钟", "不支持因子注入"],
        "suitable":   "中长期趋势跟踪，市场方向明确时",
        "unsuitable": "频繁换仓、短期波段",
        "tooltip": (
            "【深度学习集成 — LSTM】\n\n"
            "原理：按时间顺序逐日「阅读」过去2年价量数据，从非线性序列中\n"
            "      提炼规律，预测未来收益排名。\n\n"
            "模型来源：微软 Qlib 官方 pytorch_lstm.LSTM\n"
            "因子集：  Alpha158（158个技术因子）\n"
            "架构：    2层 LSTM，隐藏层64维\n"
            "训练窗口：504个交易日（约2年）\n"
            "最大股票池：300支（防内存溢出）\n\n"
            "✅ 适合：中长期趋势跟踪\n"
            "❌ 不适合：频繁换仓、短期波段\n"
            "⚠ 注意：不支持 RD-Agent 因子注入"
        ),
    },
    {
        "key":   "intraday_profit",
        "name":  "短线获利",
        "icon":  "⚡",
        "model": "Qlib GRU（Alpha158，短窗口 126天训练）",
        "desc":  "GRU 捕捉短期动量效应，训练窗口短，适合活跃交易者",
        "risk":  "进取型",
        "risk_color": COLORS["danger"],
        "topk":  30,
        "tags":  ["训练6个月", "Top 30支", "不支持因子注入"],
        "suitable":   "短期动量，持仓1-2周",
        "unsuitable": "长期持有、震荡市",
        "tooltip": (
            "【短线获利 — GRU】\n\n"
            "原理：只看最近6个月行情，专门捕捉短期动量效应。\n"
            "      GRU 比 LSTM 更轻量，对短序列反应更灵敏。\n\n"
            "模型来源：微软 Qlib 官方 pytorch_gru.GRU\n"
            "因子集：  Alpha158（158个技术因子）\n"
            "架构：    2层 GRU，隐藏层64维\n"
            "训练窗口：126个交易日（约6个月，是其他策略的1/4）\n"
            "目标选出：Top 30支（比其他策略更集中）\n\n"
            "GRU vs LSTM：GRU参数更少，短序列表现更好，训练更快\n\n"
            "✅ 适合：活跃交易，持仓1-2周\n"
            "❌ 不适合：长期持有、震荡市\n"
            "⚠ 注意：不支持 RD-Agent 因子注入"
        ),
    },
    {
        "key":   "growth_stocks",
        "name":  "成长股选股",
        "icon":  "🌱",
        "model": "LightGBM（Alpha158，158个因子）",
        "desc":  "梯度提升树聚焦成长因子，适合中长期持有，回撤相对较小",
        "risk":  "稳健型",
        "risk_color": COLORS["success"],
        "topk":  50,
        "tags":  ["训练2年", "支持因子注入", "可解释性强"],
        "suitable":   "稳健中长期持有，可配合自定义因子",
        "unsuitable": "短期高频换仓",
        "tooltip": (
            "【成长股选股 — LightGBM】\n\n"
            "原理：成千上万棵决策树集体投票，每棵树学习一个规则，\n"
            "      所有树汇总给出最终评分。可解释性强，回撤控制好。\n\n"
            "模型来源：微软 Qlib 官方 gbdt.LGBModel（LightGBM封装）\n"
            "因子集：  Alpha158 + RD-Agent 注入的自定义因子\n"
            "关键参数：max_depth=8, num_leaves=210, lr=0.0421\n"
            "训练窗口：504个交易日（约2年）\n\n"
            "因子注入方式：\n"
            "  valid_factors.json 中的自定义因子\n"
            "  → 通过 Qlib 计算特征值\n"
            "  → 追加到 Alpha158（158列）后面一起训练\n\n"
            "✅ 适合：稳健中长期持有，配合 RD-Agent 因子持续迭代\n"
            "❌ 不适合：短期高频换仓"
        ),
    },
    {
        "key":   "market_adaptive",
        "name":  "市场自适应",
        "icon":  "🔄",
        "model": "LightGBM（Alpha158，牛熊自适应学习率）",
        "desc":  "检测市场状态自动切换学习率参数，适应不同市场周期",
        "risk":  "平衡型",
        "risk_color": COLORS["warning"],
        "topk":  50,
        "tags":  ["SPY牛熊检测", "支持因子注入", "动态学习率"],
        "suitable":   "跨越牛熊周期长期使用",
        "unsuitable": "网络不稳定环境（依赖SPY数据）",
        "tooltip": (
            "【市场自适应 — LightGBM + 牛熊切换】\n\n"
            "原理：在成长股策略基础上，运行前先读取 SPY 最近60天表现，\n"
            "      判断牛熊市，动态调整模型激进程度（学习率）。\n\n"
            "模型来源：LGBModel（同成长股）\n"
            "因子集：  Alpha158 + RD-Agent 注入的自定义因子\n\n"
            "牛熊检测逻辑：\n"
            "  SPY 近60日上涨 → 牛市 → 学习率 0.05（更激进）\n"
            "  SPY 近60日下跌 → 熊市 → 学习率 0.03（更保守）\n\n"
            "✅ 适合：跨越牛熊周期的长期使用\n"
            "❌ 不适合：网络不通时（回退到固定参数）\n"
            "⚠ 依赖：OpenBB/yfinance 拉取 SPY 数据"
        ),
    },
    {
        "key":   "pytorch_full_market",
        "name":  "全市场深度学习",
        "icon":  "🌐",
        "model": "Qlib LSTM（Alpha360，360个因子）",
        "desc":  "Alpha360 宽因子集 + LSTM，覆盖全市场蓝筹股，挖掘被忽视的机会",
        "risk":  "进取型",
        "risk_color": COLORS["danger"],
        "topk":  50,
        "tags":  ["360个因子", "训练最慢", "不支持因子注入"],
        "suitable":   "挖掘冷门股，宽基全市场覆盖",
        "unsuitable": "内存小的机器（360特征更耗资源）",
        "tooltip": (
            "【全市场深度学习 — LSTM + Alpha360】\n\n"
            "原理：使用360个因子（是其他策略的2.3倍），覆盖更广的股票池，\n"
            "      捕捉被常规策略忽视的全市场信号。\n\n"
            "模型来源：微软 Qlib 官方 pytorch_lstm.LSTM\n"
            "因子集：  Alpha360（360个因子 = Alpha158 + 高频微结构因子）\n"
            "架构：    1层 LSTM，隐藏层128维（比策略1更宽但更浅）\n"
            "训练轮数：8轮（特征多，收敛更快）\n"
            "最大股票池：400支\n\n"
            "Alpha158 vs Alpha360：\n"
            "  Alpha158：标准技术因子，适合标普500蓝筹\n"
            "  Alpha360：额外含高频微结构、多周期统计，适合全市场\n\n"
            "✅ 适合：挖掘冷门股、中小盘，宽基全市场覆盖\n"
            "❌ 不适合：内存 < 8GB 的机器\n"
            "⚠ 注意：CPU训练约5-12分钟，不支持因子注入"
        ),
    },
    {
        #"ma10_turnup":         MA10TurnUpScreenStrategy,
        #"ma10_strict":         MA10_STRICT,
        #"ma10_relaxed":        MA10_RELAXED, # ma10_turnup
        #"ma10_trend":          MA10_TREND,
        "key":   "ma10_strict",  # 必须与注册表key一致
        "name":  "MA10 抬头",
        "icon":  "📈",
        "model": "传统技术指标 — MA10 均线拐头 + 成交量确认",
        "desc":  "10日均线刚拐头向上时买入，辅以成交量确认和股价位置过滤",
        "risk":  "稳健型",
        "risk_color": COLORS["success"],  # 绿色标签
        "topk":  20,
        "turn_up_mode": "relaxed",  # 放宽模式
        "min_turn_up_weeks":    1,     # 至少已抬头1周
        "max_turn_up_weeks":    3,     # 最多已抬头3周
        "require_vol_confirm": False,  # 暂时去掉成交量确认
        "require_price_above_ma10": False,  # 暂时去掉股价位置过滤
        "tags":  ["无需训练", "实时运算", "传统技术分析"],
        "suitable":   "趋势初期介入，均线刚拐头时",
        "unsuitable": "震荡市假突破频繁",
        "tooltip": (
            "【MA10 抬头策略】\n\n"
            "原理：10日均线（过去10个交易日收盘价均值）是短线趋势的核心指标。\n"
            "      当均线从下跌/走平转为上升（今天>昨天，昨天≤前天），\n"
            "      说明短期资金开始流入，趋势可能反转向上。\n\n"
            "筛选条件（可配置）：\n"
            "  ① MA10 抬头：cur_ma10 > prev_ma10 ≥ prev2_ma10\n"
            "  ② 成交量确认：当日成交量 > 5日均量（放量突破）\n"
            "  ③ 股价位置：收盘价 > MA10（股价在均线上方运行）\n\n"
            "✅ 适合：趋势初期介入，捕捉底部反转信号\n"
            "❌ 不适合：震荡市、假突破频繁的环境\n"
            "⚡ 优势：无需模型训练，即跑即用"
        ),
    },
    {
        "key":   "golden_cross_510",
        "name":  "5-10金叉策略",
        "icon":  "📈",
        "model": "传统技术指标 — 5-10日均线金叉 + 多头排列",
        "desc":  "5日线上穿10日线金叉，结合5-10-20-60日均线多头排列",
        "risk":  "稳健型",
        "risk_color": COLORS["success"],
        "topk":  20,
        "tags":  ["金叉信号", "多头排列", "趋势确认"],
        "tooltip": (
            "【5-10金叉策略】\n\n"
            "原理：\n"
            "1. 5日线上穿10日线形成金叉（最近10个交易日内）\n"
            "2. 5-10-20-60日均线呈多头排列\n"
            "3. 均线间距发散，趋势加速\n"
            "4. 成交量配合确认\n\n"
            "筛选条件：\n"
            "① 近期金叉：5-10金叉发生在10个交易日内\n"
            "② 多头排列：5>10>20>60日均线\n"
            "③ 发散度：均线间距扩大\n"
            "④ 股价位置：收盘价在5日线上方\n"
            "⑤ 成交量：放量确认\n\n"
            "✅ 适合：趋势初期确认，捕捉主升浪\n"
            "❌ 不适合：震荡市，假突破频繁\n"
            "⚡ 优势：多指标共振，信号可靠"
        ),
    },
    {
        "key":   "early_trend",
        "name":  "趋势早期识别",
        "icon":  "🚀",
        "model": "传统技术指标 — 均线聚拢+小斜率突破",
        "desc":  "识别趋势刚形成的早期信号，避免追高，捕捉启动点",
        "risk":  "稳健型",
        "risk_color": COLORS["success"],
        "topk":  20,
        "tags":  ["趋势启动", "低位潜伏", "风险较低"],
        "tooltip": (
            "【趋势早期识别策略】\n\n"
            "核心理念：\n"
            "1. 识别趋势刚形成的早期信号，而不是趋势中后期的强化信号\n"
            "2. 避免追高，降低买入成本\n"
            "3. 捕捉主升浪启动前的布局机会\n\n"
            "关键特征：\n"
            "① 均线聚拢：多条均线高度收敛\n"
            "② 小斜率向上：刚刚开始向上，斜率不大\n"
            "③ 价格突破：突破近期震荡区间\n"
            "④ 成交量配合：温和放量\n"
            "⑤ 技术指标共振：MACD零轴附近金叉，布林带收口\n\n"
            "✅ 优势：买入位置低，风险小，潜在收益空间大\n"
            "❌ 缺点：可能需要耐心等待，假突破风险\n"
            "⏱️ 适合：中长线布局，价值投资者"
        ),
    },
    {
        "key":   "early_trend_hierarchical",
        "name":  "趋势早期识别(层次化)",
        "icon":  "🚀",
        "model": "层次化评分模型 — 早期趋势识别",
        "desc":  "三层评分体系：核心条件+辅助确认+技术指标，避免一票否决，更灵活识别趋势启动点",
        "risk":  "稳健型",
        "risk_color": COLORS["success"],
        "topk":  20,
        "tags":  ["趋势启动", "多维度评分", "层次化筛选", "风险较低"],
        "tooltip": (
            "【趋势早期识别策略(层次化评分版本)】\n\n"
            "🎯 核心理念：\n"
            "• 避免传统策略的'一票否决'，采用三层评分体系\n"
            "• 核心层(必须项)+辅助层(加分项)+确认层(优化项)\n"
            "• 更灵活适应不同市场环境\n\n"
            "🏆 评分体系：\n"
            "┌─ 核心层(权重60%) ─┐\n"
            "│ 1. 均线聚拢状态 (权重0.4)\n"
            "│ 2. 小斜率向上   (权重0.3)\n"
            "│ 3. MA120比较    (权重0.2)\n"
            "│ → 至少满足2个核心条件\n"
            "└───────────────────┘\n\n"
            "┌─ 辅助层(权重40%) ─┐\n"
            "│ 4. 价格位置分析 (权重0.15)\n"
            "│ 5. 价格突破确认 (权重0.15)\n"
            "│ 6. 成交量配合   (权重0.1)\n"
            "└───────────────────┘\n\n"
            "┌─ 确认层(权重10%) ─┐\n"
            "│ 7. MACD金叉确认  (权重0.05)\n"
            "│ 8. 布林带收口    (权重0.05)\n"
            "└───────────────────┘\n\n"
            "📊 算法流程：\n"
            "1. 计算8个维度的独立分数\n"
            "2. 检查核心条件满足数\n"
            "3. 分层加权计算总分\n"
            "4. 排名选出Top 20\n\n"
            "✅ 优势：\n"
            "• 适应性强：震荡市/趋势市均可\n"
            "• 风险可控：不依赖单一信号\n"
            "• 透明度高：可查看各维度得分\n\n"
            "🔧 核心参数：\n"
            "• 均线聚拢天数：20天\n"
            "• 最大斜率限制：2%\n"
            "• 价格位置范围：30%-70%\n"
            "• 成交量放大：1.2倍\n\n"
            "🎯 适用场景：\n"
            "• 趋势启动前的布局\n"
            "• 震荡市中的突破机会\n"
            "• 价值股的底部反转\n"
            "• 避免追高，降低买入成本"
        ),
    },
    {
        "key":   "trendline_breakout",
        "name":  "趋势线突破",
        "icon":  "📈",
        "model": "传统技术分析 — 下降趋势线突破",
        "desc":  "识别股价放量突破长期下降趋势线的反转信号",
        "risk":  "进取型",
        "risk_color": COLORS["warning"],
        "topk":  20,
        "tags":  ["趋势反转", "突破信号", "量价配合"],
        "tooltip": (
            "【下降趋势线突破策略】\n\n"
            "核心逻辑：\n"
            "1. 识别股票的长期下降趋势线\n"
            "2. 当股价放量突破下降趋势线时\n"
            "3. 意味着下跌趋势可能结束，新的上升趋势可能开始\n\n"
            "筛选条件：\n"
            "① 有效突破：股价突破趋势线至少3%\n"
            "② 成交量确认：突破日成交量明显放大\n"
            "③ 趋势强度：原下降趋势有一定斜率\n"
            "④ 后续整理：突破后能站稳趋势线上方\n"
            "⑤ 回踩确认：突破后有回踩但不跌破趋势线\n\n"
            "✅ 优势：捕捉趋势反转的早期信号\n"
            "❌ 风险：假突破、突破后快速回落\n"
            "🎯 适合：趋势交易者，追求反转收益"
        ),
    },
]


class StrategyCard(QFrame):
    """策略选择卡片"""

    selected = pyqtSignal(str)   # 策略 key

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.state = get_state()
        self.config = config
        self._is_selected = False
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(160)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(5)

        # 整张卡片的 tooltip（详细说明）
        if self.config.get("tooltip"):
            self.setToolTip(self.config["tooltip"])

        # 标题行
        title_row = QHBoxLayout()
        icon_lbl = QLabel(self.config["icon"])
        icon_lbl.setStyleSheet("font-size: 24px;")
        title_row.addWidget(icon_lbl)

        name_lbl = QLabel(self.config["name"])
        name_font = QFont()
        name_font.setPointSize(14)
        name_font.setBold(True)
        name_lbl.setFont(name_font)
        title_row.addWidget(name_lbl)
        title_row.addStretch()

        # 风险标签
        risk_lbl = QLabel(self.config["risk"])
        risk_lbl.setStyleSheet(
            f"color: {self.config['risk_color']}; "
            f"border: 1px solid {self.config['risk_color']}55; "
            f"border-radius: 8px; padding: 2px 8px; font-size: 11px;"
        )
        title_row.addWidget(risk_lbl)
        layout.addLayout(title_row)

        # 模型名
        model_lbl = QLabel(self.config["model"])
        model_lbl.setStyleSheet(f"color: {COLORS['primary_light']}; font-size: 11px;")
        layout.addWidget(model_lbl)

        # 描述
        desc_lbl = QLabel(self.config["desc"])
        desc_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # 特性标签行（tags）
        if self.config.get("tags"):
            tags_row = QHBoxLayout()
            tags_row.setSpacing(4)
            for tag in self.config["tags"]:
                tag_lbl = QLabel(tag)
                tag_lbl.setStyleSheet(
                    f"color: {COLORS['text_muted']}; "
                    f"background: {COLORS['bg_card']}; "
                    f"border: 1px solid {COLORS['border']}; "
                    f"border-radius: 4px; padding: 1px 5px; font-size: 10px;"
                )
                tags_row.addWidget(tag_lbl)
            tags_row.addStretch()
            layout.addLayout(tags_row)

        layout.addStretch()

        # 底部：适用场景 + 选股数量
        bottom_row = QHBoxLayout()
        topk_lbl = QLabel(f"目标选出：Top {self.config['topk']} 支")
        topk_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        bottom_row.addWidget(topk_lbl)
        bottom_row.addStretch()
        if self.config.get("suitable"):
            hint_lbl = QLabel(f"适合：{self.config['suitable']}")
            hint_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
            hint_lbl.setWordWrap(True)
            hint_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            bottom_row.addWidget(hint_lbl)
        layout.addLayout(bottom_row)

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        if selected:
            self.setStyleSheet(
                f"QFrame#card {{ border: 2px solid {COLORS['primary']}; "
                f"background-color: {COLORS['bg_card_hover']}; border-radius: 12px; }}"
            )
        else:
            self.setStyleSheet("")

    def mousePressEvent(self, event) -> None:
        self.selected.emit(self.config["key"])
        super().mousePressEvent(event)


class ScreeningPage(QWidget):
    """量化选股页面"""

    run_requested = pyqtSignal(str, str)    # 策略 key, Region

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = get_state()
        self._selected_strategy = "deep_learning"
        self._strategy_cards: dict[str, StrategyCard] = {}
        self._setup_ui()
        self._connect_events()
        # 默认选中第一个策略
        self._on_strategy_selected("deep_learning")
        # 延迟加载已注入因子状态
        QTimer.singleShot(800, self._refresh_injected_factors)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(16)

        # 页面标题
        title = QLabel("⚙️ 量化选股")
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel(f"选择 Qlib 量化策略，系统将从{self.state.reg_name}全市场筛选最优个股组合")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # ── 策略卡片网格（2×3布局）────────────────────────
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, s in enumerate(STRATEGIES):
            card = StrategyCard(s)
            card.selected.connect(self._on_strategy_selected)
            self._strategy_cards[s["key"]] = card
            row, col = divmod(i, 3)
            grid.addWidget(card, row, col)

        # 补空格（保持网格对齐）
        if len(STRATEGIES) % 3 != 0:
            for j in range(len(STRATEGIES) % 3, 3):
                placeholder = QWidget()
                grid.addWidget(placeholder, len(STRATEGIES) // 3, j)

        layout.addLayout(grid)

        # ── 运行控制区 ────────────────────────────────────
        control_card = QFrame()
        control_card.setObjectName("card")
        control_layout = QVBoxLayout(control_card)
        control_layout.setSpacing(10)

        # 当前选中策略
        self._selected_label = QLabel("已选策略：深度学习集成")
        self._selected_label.setStyleSheet(
            f"color: {COLORS['primary_light']}; font-weight: bold; font-size: 14px;"
        )
        control_layout.addWidget(self._selected_label)

        # ── 已注入因子面板 ────────────────────────────
        injected_frame = QFrame()
        injected_frame.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_card']}55; "
            f"border: 1px solid {COLORS['border']}44; border-radius: 6px; }}"
        )
        injected_inner = QVBoxLayout(injected_frame)
        injected_inner.setContentsMargins(8, 6, 8, 6)
        injected_inner.setSpacing(3)

        injected_title_row = QHBoxLayout()
        injected_title = QLabel("🧬 已注入自定义因子")
        injected_title.setStyleSheet(
            f"color:{COLORS['text_secondary']}; font-size:11px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        injected_title_row.addWidget(injected_title)
        injected_title_row.addStretch()
        self._injected_count_lbl = QLabel("无")
        self._injected_count_lbl.setStyleSheet(
            f"color:{COLORS['text_muted']}; font-size:11px;"
            f" border:none; background:transparent;"
        )
        injected_title_row.addWidget(self._injected_count_lbl)
        injected_inner.addLayout(injected_title_row)

        # 因子标签滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(80)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._inj_tags_widget = QWidget()
        self._inj_tags_widget.setStyleSheet("background: transparent;")
        self._inj_tags_layout = QVBoxLayout(self._inj_tags_widget)
        self._inj_tags_layout.setSpacing(1)
        self._inj_tags_layout.setContentsMargins(0, 0, 0, 0)
        self._inj_tags_layout.addStretch()
        scroll.setWidget(self._inj_tags_widget)
        injected_inner.addWidget(scroll)

        control_layout.addWidget(injected_frame)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setMinimumHeight(10)
        control_layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        control_layout.addWidget(self._status_label)

        # 按钮行
        btn_row = QHBoxLayout()

        self._instrument_combo = InstrumentComboBox()
        self._instrument_combo.setMinimumHeight(38)
        self._instrument_combo.setPlaceholderText("请选择采集范围")
        self._instrument_combo.setToolTip(
            "选择股票范围：\n"
            f"从 {get_state().reg}_data/instruments 选择txt文件作为股票范围\n"
            "默认选择（all）全部股票：采集所有股票的最新数据（耗时较长）\n"
        )
        btn_row.addWidget(self._instrument_combo)

        self._run_btn = QPushButton("▶ 开始选股")
        self._run_btn.setMinimumHeight(42)
        self._run_btn.clicked.connect(self._on_run_clicked)
        btn_row.addWidget(self._run_btn)

        self._stop_btn = QPushButton("⏹ 停止")
        self._stop_btn.setObjectName("btn_danger")
        self._stop_btn.setMinimumHeight(42)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        btn_row.addWidget(self._stop_btn)

        control_layout.addLayout(btn_row)
        layout.addWidget(control_card)

    def _on_strategy_selected(self, key: str) -> None:
        # 取消旧选中
        if self._selected_strategy in self._strategy_cards:
            self._strategy_cards[self._selected_strategy].set_selected(False)
        # 激活新选中
        self._selected_strategy = key
        if key in self._strategy_cards:
            self._strategy_cards[key].set_selected(True)
        # 更新标签
        name = next((s["name"] for s in STRATEGIES if s["key"] == key), key)
        self._selected_label.setText(f"已选策略：{name}")

    def _on_run_clicked(self) -> None:
        from core.app_state import get_state
        state = get_state()
        if not state.qlib_initialized:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Qlib 未初始化",
                f"请先前往「参数配置」下载 Qlib {state.reg_name}数据后再运行选股。")
            return
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self.run_requested.emit(self._selected_strategy, self._instrument_combo.currentText())

    def _on_stop_clicked(self) -> None:
        from core.event_bus import get_event_bus
        get_event_bus().screening_failed.emit("用户手动停止")

    def _build_inj_tags(self, factors: list) -> None:
        """在 _inj_tags_layout 中为每个因子创建带 tooltip 的标签行"""
        while self._inj_tags_layout.count() > 1:
            item = self._inj_tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not factors:
            lbl = QLabel("暂无注入因子，LightGBM 策略将使用标准 Alpha158")
            lbl.setStyleSheet(
                f"color:{COLORS['text_muted']}; font-size:10px; border:none; background:transparent;"
            )
            self._inj_tags_layout.insertWidget(0, lbl)
            self._injected_count_lbl.setText("无")
            return

        self._injected_count_lbl.setText(f"共 {len(factors)} 个（仅 LightGBM 策略使用）")
        for i, f in enumerate(factors):
            expr = f.get("expression", "") if isinstance(f, dict) else str(f)
            name = f.get("name", "")        if isinstance(f, dict) else ""
            desc = f.get("description", "") if isinstance(f, dict) else ""

            display = f"• {name}：{expr[:38]}{'…' if len(expr) > 38 else ''}" if name \
                      else f"• {expr[:48]}{'…' if len(expr) > 48 else ''}"

            lbl = QLabel(display)
            lbl.setStyleSheet(
                f"color:{COLORS['text_secondary']}; font-size:10px; "
                f"border:none; background:transparent; padding:0px 2px;"
            )
            lbl.setCursor(Qt.CursorShape.WhatsThisCursor)

            tooltip_lines = []
            if name:
                tooltip_lines.append(f"<b>{name}</b>")
            if desc:
                tooltip_lines.append(desc)
            tooltip_lines.append(f"<code>{expr}</code>")
            lbl.setToolTip("<br>".join(tooltip_lines))
            lbl.setTextFormat(Qt.TextFormat.PlainText)

            self._inj_tags_layout.insertWidget(i, lbl)

    def _refresh_injected_factors(self) -> None:
        """读取 valid_factors.json 并刷新因子面板"""
        try:
            from strategies.factor_injector import get_inject_status
            status = get_inject_status()
            self._build_inj_tags(status.get("factors", []))
        except Exception:
            self._build_inj_tags([])

    def _connect_events(self) -> None:
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        bus.screening_progress.connect(self._on_progress)
        bus.screening_completed.connect(self._on_completed)
        bus.screening_failed.connect(self._on_failed)
        # 因子注入完成后自动刷新面板
        bus.rdagent_factors_injected.connect(self._build_inj_tags)

    def _on_progress(self, pct: int, msg: str) -> None:
        self._progress_bar.setValue(pct)
        self._status_label.setText(msg)

    def _on_completed(self, results: list) -> None:
        self._reset_controls()
        count = len(results)
        self._status_label.setText(f"✅ 选股完成，共筛出 {count} 支股票，已跳转到选股结果页")
        from core.event_bus import get_event_bus
        get_event_bus().navigate_to.emit("results")

    def _on_failed(self, err: str) -> None:
        self._reset_controls()
        self._status_label.setText(f"❌ 选股失败：{err}")

    def _reset_controls(self) -> None:
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress_bar.setVisible(False)
