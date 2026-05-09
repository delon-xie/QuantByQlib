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
