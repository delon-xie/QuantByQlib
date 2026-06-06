"""
QuantByQlib 浅灰色主题
PyQt6 全局样式表
"""

# ── 颜色常量 ────────────────────────────────────────────────
COLORS = {
    # 主色调（蓝紫色系，适配浅色背景）
    "primary": "#5B5BD6",          # 主色（靛蓝）
    "primary_light": "#7C7CEC",    # 浅主色
    "primary_dark": "#4040B8",     # 深主色
    "primary_hover": "#6868DE",    # 悬停色

    # 背景色（浅灰系）
    "bg_main": "#F4F5F7",          # 主窗口背景（浅灰）
    "bg_sidebar": "#FFFFFF",       # 侧边栏背景（白色）
    "bg_card": "#FFFFFF",          # 卡片背景（白色）
    "bg_card_hover": "#F0F1F5",    # 卡片悬停
    "bg_input": "#FFFFFF",         # 输入框背景
    "bg_table_alt": "#F8F9FB",     # 表格交替行

    # 边框色
    "border": "#E2E4EA",           # 普通边框
    "border_active": "#5B5BD6",    # 激活边框

    # 文字色
    "text_primary": "#1A1D2E",     # 主文字（深色）
    "text_secondary": "#5A5F7A",   # 次要文字（中灰）
    "text_muted": "#9299B0",       # 弱化文字（浅灰）

    # 状态色
    "success": "#16A34A",          # 涨/盈利（绿）
    "danger": "#DC2626",           # 跌/亏损（红）
    "warning": "#D97706",          # 警告（橙）
    "info": "#2563EB",             # 信息（蓝）

    # 信号色
    "signal_buy": "#16A34A",       # 买入信号
    "signal_sell": "#DC2626",      # 卖出信号
    "signal_hold": "#D97706",      # 持有信号
    "signal_watch": "#2563EB",     # 观察信号

    # 渐变（用于按钮/徽章）
    "gradient_start": "#5B5BD6",
    "gradient_end": "#7C7CEC",
}


def get_stylesheet() -> str:
    """返回完整的应用样式表"""
    c = COLORS
    return f"""
/* ── 全局基础 ─────────────────────────────────────────── */
QWidget {{
    background-color: {c['bg_main']};
    color: {c['text_primary']};
    font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {c['bg_main']};
}}

/* ── 滚动条 ──────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {c['bg_main']};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {c['border']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['primary']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {c['bg_main']};
    height: 8px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {c['border']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c['primary']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── 侧边栏 ──────────────────────────────────────────── */
#sidebar {{
    background-color: {c['bg_sidebar']};
    border-right: 1px solid {c['border']};
}}

#sidebar_logo {{
    font-size: 16px;
    font-weight: bold;
    color: {c['primary']};
    padding: 20px 16px 10px 16px;
}}

#sidebar_version {{
    font-size: 11px;
    color: {c['text_muted']};
    padding: 0 16px 16px 16px;
}}

/* 侧边栏导航按钮 */
#nav_btn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 10px 16px;
    color: {c['text_secondary']};
    font-size: 13px;
    margin: 2px 8px;
}}
#nav_btn:hover {{
    background-color: {c['bg_card_hover']};
    color: {c['text_primary']};
}}
#nav_btn[active="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['primary_dark']}, stop:1 {c['primary']});
    color: white;
    font-weight: bold;
}}

#nav_btn_active {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['primary_dark']}, stop:1 {c['primary']});
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 10px 16px;
    color: white;
    font-size: 13px;
    font-weight: bold;
    margin: 2px 8px;
}}

/* 侧边栏导航分组标题 */
#nav_group_header {{
    background: transparent;
    border: none;
    text-align: left;
    padding: 6px 16px;
    color: {c['text_muted']};
    font-size: 11px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

#nav_group_header:hover {{
    color: {c['text_secondary']};
}}

#sidebar_toggle {{
    background: transparent;
    border: none;
    border-radius: 4px;
    color: {c['text_muted']};
    font-size: 14px;
    padding: 4px;
    margin: 0 8px;
}}

#sidebar_toggle:hover {{
    background-color: {c['bg_card_hover']};
    color: {c['text_primary']};
}}

/* ── 主内容区 ─────────────────────────────────────────── */
#content_area {{
    background-color: {c['bg_main']};
}}

/* 页面标题 */
#page_title {{
    font-size: 20px;
    font-weight: bold;
    color: {c['text_primary']};
    padding: 20px 24px 8px 24px;
}}

#page_subtitle {{
    font-size: 12px;
    color: {c['text_muted']};
    padding: 0 24px 16px 24px;
}}

/* ── 卡片 ────────────────────────────────────────────── */
#card {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    padding: 16px;
}}

#card_header {{
    font-size: 14px;
    font-weight: bold;
    color: {c['text_primary']};
    border-bottom: 1px solid {c['border']};
    padding-bottom: 10px;
    margin-bottom: 12px;
}}

/* ── 按钮 ────────────────────────────────────────────── */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['primary_dark']}, stop:1 {c['primary']});
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: bold;
    font-size: 13px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['primary']}, stop:1 {c['primary_light']});
}}
QPushButton:pressed {{
    background: {c['primary_dark']};
}}
QPushButton:disabled {{
    background: {c['border']};
    color: {c['text_muted']};
}}

/* 次要按钮（轮廓样式） */
QPushButton#btn_secondary {{
    background: transparent;
    border: 1px solid {c['primary']};
    color: {c['primary']};
}}
QPushButton#btn_secondary:hover {{
    background: {c['bg_card_hover']};
}}

/* 危险按钮（红色） */
QPushButton#btn_danger {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #991B1B, stop:1 #EF4444);
}}
QPushButton#btn_danger:hover {{
    background: {c['danger']};
}}

/* ── 输入框 ──────────────────────────────────────────── */
QLineEdit {{
    background-color: {c['bg_input']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px 12px;
    color: {c['text_primary']};
    font-size: 13px;
}}
QLineEdit:focus {{
    border: 1px solid {c['primary']};
}}
QLineEdit::placeholder {{
    color: {c['text_muted']};
}}

QTextEdit, QPlainTextEdit {{
    background-color: {c['bg_input']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px;
    color: {c['text_primary']};
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {c['primary']};
}}

/* ── 下拉框 ──────────────────────────────────────────── */
QComboBox {{
    background-color: {c['bg_input']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 7px 12px;
    color: {c['text_primary']};
    font-size: 13px;
}}
QComboBox:focus {{
    border: 1px solid {c['primary']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {c['text_secondary']};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    color: {c['text_primary']};
    selection-background-color: {c['primary']};
    selection-color: white;
    padding: 4px;
}}

/* ── 标签页 ──────────────────────────────────────────── */
/* ── background-color: {c['bg_card']}; ──────────────── */
QTabWidget {{
    background: {COLORS['bg_sidebar']};
    background-color: {COLORS['bg_sidebar']};
    border: none;
    padding: 0;
}}
QTabWidget::pane {{
    background: {COLORS['bg_sidebar']};
    background-color: {COLORS['bg_sidebar']};
    border: 1px solid {c['border']};
    border-radius: 0 8px 8px 8px;
}}
QTabBar {{
    background: {COLORS['bg_sidebar']};
    background-color: {COLORS['bg_sidebar']};
    border: none;
    padding: 0;
    margin: 0;
}}
QTabBar::tab {{
    background-color: {c['bg_main']};
    color: {c['text_secondary']};
    padding: 8px 18px;
    border: 1px solid {c['border']};
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {c['bg_card']};
    color: {c['primary']};
    font-weight: bold;
    border-bottom: 2px solid {c['primary']};
}}
QTabBar::tab:hover:!selected {{
    background-color: {c['bg_card_hover']};
    color: {c['text_primary']};
}}

/* ── 表格 ────────────────────────────────────────────── */
QTableWidget, QTableView {{
    background-color: {c['bg_card']};
    alternate-background-color: {c['bg_table_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    gridline-color: {c['border']};
    color: {c['text_primary']};
    font-size: 13px;
}}
QTableWidget::item, QTableView::item {{
    padding: 8px 12px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: #EEF0FF;
    color: {c['primary_dark']};
}}
QTableWidget::item:hover, QTableView::item:hover {{
    background-color: {c['bg_card_hover']};
}}
QHeaderView::section {{
    background-color: {c['bg_main']};
    color: {c['text_secondary']};
    border: none;
    border-bottom: 1px solid {c['border']};
    padding: 8px 12px;
    font-weight: bold;
    font-size: 12px;
}}
QHeaderView::section:first {{
    border-radius: 8px 0 0 0;
}}

/* ── 进度条 ──────────────────────────────────────────── */
QProgressBar {{
    background-color: {c['bg_main']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    height: 12px;
    text-align: center;
    color: {c['text_secondary']};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['primary_dark']}, stop:1 {c['primary_light']});
    border-radius: 6px;
}}

/* ── 滑块 ────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {c['border']};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {c['primary']};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {c['primary']};
    border-radius: 3px;
}}

/* ── 复选框 ──────────────────────────────────────────── */
QCheckBox {{
    color: {c['text_primary']};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {c['border']};
    border-radius: 4px;
    background: {c['bg_input']};
}}
QCheckBox::indicator:checked {{
    background: {c['primary']};
    border-color: {c['primary']};
}}

/* ── 分隔线 ──────────────────────────────────────────── */
QFrame[frameShape="4"],  /* HLine */
QFrame[frameShape="5"]   /* VLine */
{{
    color: {c['border']};
    background-color: {c['border']};
    border: none;
    max-height: 1px;
}}

/* ── 工具提示 ────────────────────────────────────────── */
QToolTip {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── 状态栏 ──────────────────────────────────────────── */
QStatusBar {{
    background-color: {c['bg_sidebar']};
    color: {c['text_secondary']};
    border-top: 1px solid {c['border']};
    font-size: 12px;
}}

/* ── 菜单 ────────────────────────────────────────────── */
QMenu {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 16px;
    border-radius: 4px;
    color: {c['text_primary']};
}}
QMenu::item:selected {{
    background-color: {c['primary']};
    color: white;
}}

/* ── SpinBox ─────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background-color: {c['bg_input']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 7px 12px;
    color: {c['text_primary']};
    font-size: 13px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {c['primary']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {c['bg_main']};
    border: none;
    width: 20px;
}}

/* ── DateEdit ────────────────────────────────────────── */
QDateEdit {{
    background-color: {c['bg_input']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 7px 12px;
    color: {c['text_primary']};
}}
QDateEdit:focus {{
    border: 1px solid {c['primary']};
}}

/* ── Splitter ────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {c['border']};
    width: 2px;
    height: 2px;
}}
QSplitter::handle:hover {{
    background-color: {c['primary']};
}}

/* ── GroupBox ────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {c['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    color: {c['text_secondary']};
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {c['text_secondary']};
    font-weight: bold;
}}

/* ── 侧边栏分隔线专用 ────────────────────────────────── */
#sidebar_sep {{
    color: {c['border']};
    background-color: {c['border']};
}}
"""


def get_badge_style(color: str) -> str:
    """返回彩色徽章的内联样式"""
    return (
        f"background-color: {color}22; "
        f"color: {color}; "
        f"border: 1px solid {color}55; "
        f"border-radius: 10px; "
        f"padding: 2px 8px; "
        f"font-weight: bold; "
        f"font-size: 11px;"
    )


def get_signal_badge_style(signal: str) -> str:
    """根据信号类型返回对应颜色的徽章样式"""
    signal_colors = {
        "BUY": COLORS["success"],
        "STRONG_BUY": COLORS["success"],
        "SELL": COLORS["danger"],
        "STRONG_SELL": COLORS["danger"],
        "HOLD": COLORS["warning"],
        "WATCH": COLORS["info"],
    }
    color = signal_colors.get(signal.upper() if signal else "", COLORS["text_muted"])
    return get_badge_style(color)
