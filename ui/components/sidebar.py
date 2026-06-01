"""
QuantByQlib 侧边栏导航
可折叠宽度：展开显示图标+文字，折叠只显示图标，悬停浮动提示
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QSpacerItem, QSizePolicy, QFrame, QScrollArea
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPoint
from PyQt6.QtGui import QFont
from ui.components.regionlabel import RegionLabel


NAV_ITEMS = [
    ("dashboard",   "📊", "仪表盘"),
    ("universe",    "🗂️", "股票池管理"),
    ("screening",   "🔍", "量化选股"),
    ("results",     "🤖", "选股结果"),
    ("chart",       "📈", "K线图表"),
    ("portfolio",   "💰", "持仓管理"),
    ("goal",        "🎯", "盈利目标"),
    ("backtest",    "📈", "策略回测"),
    ("signals",     "🔔", "交易信号"),
    ("factor",      "🔬", "因子发现"),
    ("config",      "⚙️",  "参数配置"),
    ("logs",        "📋", "运行日志"),
]


class SidebarButton(QPushButton):
    """单个导航按钮（支持折叠/展开切换）"""

    hovered_label = None

    def __init__(self, icon: str, label: str, page_key: str, parent=None):
        super().__init__(parent)
        self.page_key = page_key
        self._icon = icon
        self._label = label
        self._collapsed = False
        self.setText(f"  {icon}  {label}")
        self.setObjectName("nav_btn")
        self.setCheckable(False)
        self.setMinimumHeight(42)
        self.setMinimumWidth(0)
        self.setProperty("active", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        if collapsed:
            self.setText(self._icon)
            self.setToolTip("")
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.setText(f" {self._icon}  {self._label}")
            self.setToolTip("")
            self.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self._collapsed:
            sidebar = self.findParent(Sidebar)
            if sidebar:
                sidebar.show_button_tooltip(self)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._collapsed:
            sidebar = self.findParent(Sidebar)
            if sidebar:
                sidebar.hide_button_tooltip()

    def findParent(self, cls):
        p = self.parent()
        while p:
            if isinstance(p, cls):
                return p
            p = p.parent()
        return None


class Sidebar(QWidget):
    """左侧导航栏（支持宽度折叠）"""

    page_changed = pyqtSignal(str)
    width_changed = pyqtSignal(int)

    EXPANDED_WIDTH = 200
    COLLAPSED_WIDTH = 50

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._buttons: dict[str, SidebarButton] = {}
        self._current_page = ""
        self._collapsed = False
        self._enter_count = 0
        self._setup_ui()

    def _setup_reg(self, reg: str, reg_name: str) -> None:
        self.version_label.setText(f"{reg_name}量化辅助决策 v1.0")

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._logo_container = QWidget()
        self._logo_layout = QVBoxLayout(self._logo_container)
        self._logo_layout.setContentsMargins(8, 8, 8, 8)
        self._logo_layout.setSpacing(4)

        logo_label = RegionLabel("QuantByQlib", needChangeText=False)
        logo_label.setObjectName("sidebar_logo")
        logo_font = QFont()
        logo_font.setPointSize(13)
        logo_font.setBold(True)
        logo_label.setFont(logo_font)
        self._logo_layout.addWidget(logo_label)

        self.version_label = QLabel("美股量化辅助决策 v1.0")
        self.version_label.setObjectName("sidebar_version")
        self.version_label.setWordWrap(True)
        self._logo_layout.addWidget(self.version_label)

        self.main_layout.addWidget(self._logo_container)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        self.main_layout.addWidget(sep)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll.setAttribute(Qt.WidgetAttribute.WA_Hover)

        self._btn_container = QWidget()
        self._btn_container.setMinimumWidth(0)
        self._btn_layout = QVBoxLayout(self._btn_container)
        self._btn_layout.setContentsMargins(2, 4, 2, 4)
        self._btn_layout.setSpacing(2)

        for page_key, icon, label in NAV_ITEMS:
            btn = SidebarButton(icon, label, page_key, self)
            btn.setMinimumHeight(42)
            btn.clicked.connect(lambda checked, k=page_key: self._on_nav_click(k))
            self._buttons[page_key] = btn
            self._btn_layout.addWidget(btn)

        self._btn_layout.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        self._scroll.setWidget(self._btn_container)
        self.main_layout.addWidget(self._scroll, stretch=1)

        self._status_label = QLabel("⚪ Qlib 未初始化")
        self._status_label.setObjectName("sidebar_version")
        self._status_label.setWordWrap(True)
        self.main_layout.addWidget(self._status_label)

        self._toggle_btn = QPushButton("◀")
        self._toggle_btn.setObjectName("sidebar_toggle")
        self._toggle_btn.setFixedHeight(32)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        self.main_layout.addWidget(self._toggle_btn)

        self._tooltip_widget = QLabel()
        self._tooltip_widget.setObjectName("sidebar_tooltip")
        self._tooltip_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._tooltip_widget.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self._tooltip_widget.setStyleSheet("""
            QLabel {
                background: #1e1e2e;
                border: 1px solid #3b3b4f;
                border-radius: 6px;
                padding: 8px 12px;
                color: white;
                font-size: 13px;
            }
        """)
        self._tooltip_widget.hide()

        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._tooltip_widget.hide)

        self.setFixedWidth(self.EXPANDED_WIDTH)
        self._scroll.setViewportMargins(0, 0, 0, 0)

    def _toggle_collapse(self) -> None:
        print(f"[DEBUG] Toggle collapse clicked. Current: {self._collapsed}")
        self._collapsed = not self._collapsed
        print(f"[DEBUG] New state: {self._collapsed}, target width: {self.COLLAPSED_WIDTH if self._collapsed else self.EXPANDED_WIDTH}")
        self._apply_collapse()

    def _apply_collapse(self) -> None:
        self._tooltip_widget.hide()
        self._hide_timer.stop()
        print(f"[DEBUG] apply_collapse: collapsed={self._collapsed}, current width={self.width()}")
        if self._collapsed:
            self.setFixedWidth(self.COLLAPSED_WIDTH)
            print(f"[DEBUG] After setFixedWidth: width={self.width()}")
            self._logo_container.setVisible(False)
            self.version_label.setVisible(False)
            self._status_label.setVisible(False)
            self._toggle_btn.setText("▶")
            for btn in self._buttons.values():
                btn.set_collapsed(True)
        else:
            self.setFixedWidth(self.EXPANDED_WIDTH)
            self._logo_container.setVisible(True)
            self.version_label.setVisible(True)
            self._status_label.setVisible(True)
            self._toggle_btn.setText("◀")
            for btn in self._buttons.values():
                btn.set_collapsed(False)
        self.updateGeometry()
        self.update()
        self.width_changed.emit(self.width())

    def show_button_tooltip(self, btn: 'SidebarButton') -> None:
        if not self._collapsed:
            return
        self._hide_timer.stop()
        self._tooltip_widget.setText(f"  {btn._icon}  {btn._label}")
        self._tooltip_widget.adjustSize()
        btn_pos = btn.mapToGlobal(QPoint(0, 0))
        x = btn_pos.x() + btn.width() - 25
        y = btn_pos.y()
        self._tooltip_widget.move(x, y)
        self._tooltip_widget.show()

    def hide_button_tooltip(self) -> None:
        self._hide_timer.start(500)

    def _on_nav_click(self, page_key: str) -> None:
        if page_key == self._current_page:
            return
        self.navigate_to(page_key)

    def navigate_to(self, page_key: str) -> None:
        if self._current_page and self._current_page in self._buttons:
            self._buttons[self._current_page].set_active(False)
        if page_key in self._buttons:
            self._buttons[page_key].set_active(True)
        self._current_page = page_key
        self.page_changed.emit(page_key)

    def set_qlib_status(self, initialized: bool) -> None:
        if initialized:
            self._status_label.setText("🟢 Qlib 已初始化")
        else:
            self._status_label.setText("⚪ Qlib 未初始化")

    @property
    def current_page(self) -> str:
        return self._current_page
