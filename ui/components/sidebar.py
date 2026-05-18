"""
QuantByQlib 侧边栏导航
10个功能模块的导航入口
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont
from ui.components.regionlabel import RegionLabel


# 导航项定义：(页面键, 图标文字, 显示标签)
NAV_ITEMS = [
    ("dashboard",   "📊", "仪表盘"),
    ("universe",    "🗂️", "股票池管理"),
    ("screening",   "🔍",  "量化选股"),
    ("results",     "🤖", "选股结果"), #📄
    ("portfolio",   "💰", "持仓管理"), #💼
    ("goal",        "🎯", "盈利目标"),
    ("backtest",    "📈", "策略回测"),
    ("signals",     "🔔", "交易信号"), #⚡
    ("factor",      "🔬", "因子发现"),
    ("config",      "⚙️",  "参数配置"),
    ("logs",        "📋", "运行日志"),
]


class SidebarButton(QPushButton):
    """单个导航按钮"""

    def __init__(self, icon: str, label: str, page_key: str, parent=None):
        super().__init__(parent)
        self.page_key = page_key
        self.setText(f"  {icon}  {label}")
        self.setObjectName("nav_btn")
        self.setCheckable(False)
        self.setMinimumHeight(42)
        self.setProperty("active", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        # 刷新样式（Qt 属性变更后需要重刷）
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    """左侧导航栏"""

    page_changed = pyqtSignal(str)   # 发射目标页面键

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._buttons: dict[str, SidebarButton] = {}
        self._current_page = ""
        # 屏幕较小时收窄侧边栏
        from PyQt6.QtWidgets import QApplication
        avail_h = QApplication.primaryScreen().availableGeometry().height()
        self._compact = avail_h < 700
        self._setup_ui()

    def _setup_reg(self, reg: str, reg_name: str) -> None:
        self.version_label.setText(f"{reg_name}量化辅助决策 v1.0")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Logo 区域 ──────────────────────────────────────
        logo_label = RegionLabel("QuantByQlib", needChangeText = False)
        logo_label.setObjectName("sidebar_logo")
        logo_font = QFont()
        logo_font.setPointSize(13 if self._compact else 15)
        logo_font.setBold(True)
        logo_label.setFont(logo_font)
        layout.addWidget(logo_label)
        self.version_label = QLabel("美股量化辅助决策 v1.0")

        if not self._compact:
            self.version_label.setObjectName("sidebar_version")
            layout.addWidget(self.version_label)

        # ── 分隔线 ────────────────────────────────────────
        from PyQt6.QtWidgets import QFrame, QScrollArea
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        layout.addWidget(sep)
        layout.addSpacing(4 if self._compact else 8)

        # ── 导航按钮（小屏用滚动区域包裹）──────────────────
        btn_height = 36 if self._compact else 42

        if self._compact:
            # 用 ScrollArea 包裹按钮列表，防止超出屏幕
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            btn_container = QWidget()
            btn_layout = QVBoxLayout(btn_container)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(0)
        else:
            btn_layout = layout
            btn_container = None

        for page_key, icon, label in NAV_ITEMS:
            btn = SidebarButton(icon, label, page_key, self)
            btn.setMinimumHeight(btn_height)
            btn.setMaximumHeight(btn_height)
            btn.clicked.connect(lambda checked, k=page_key: self._on_nav_click(k))
            self._buttons[page_key] = btn
            btn_layout.addWidget(btn)

        if self._compact:
            btn_layout.addStretch()
            scroll.setWidget(btn_container)
            layout.addWidget(scroll, stretch=1)
        else:
            # ── 底部弹性空间 ──────────────────────────────
            layout.addSpacerItem(
                QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
            )

        # ── 底部状态（Qlib 初始化状态指示）────────────────
        self._status_label = QLabel("⚪ Qlib 未初始化")
        self._status_label.setObjectName("sidebar_version")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)
        layout.addSpacing(4 if self._compact else 8)

    def _on_nav_click(self, page_key: str) -> None:
        if page_key == self._current_page:
            return
        self.navigate_to(page_key)

    def navigate_to(self, page_key: str) -> None:
        """切换激活状态并发射信号"""
        # 取消旧按钮激活
        if self._current_page and self._current_page in self._buttons:
            self._buttons[self._current_page].set_active(False)
        # 激活新按钮
        if page_key in self._buttons:
            self._buttons[page_key].set_active(True)
        self._current_page = page_key
        self.page_changed.emit(page_key)

    def set_qlib_status(self, initialized: bool) -> None:
        """更新 Qlib 初始化状态指示"""
        if initialized:
            self._status_label.setText("🟢 Qlib 已初始化")
        else:
            self._status_label.setText("⚪ Qlib 未初始化")

    @property
    def current_page(self) -> str:
        return self._current_page
