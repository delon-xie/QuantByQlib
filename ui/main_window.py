"""
QuantByQlib 主窗口
- 左侧侧边栏（Sidebar）
- 右侧 QStackedWidget（10个页面）
- 状态栏
- 全局事件总线连接
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout,
    QStackedWidget, QStatusBar, QLabel
)
from PyQt6.QtCore import Qt, QTimer

from PyQt6.QtWidgets import QScrollArea
from ui.components.sidebar import Sidebar
from ui.pages.dashboard_page  import DashboardPage
from ui.pages.screening_page  import ScreeningPage
from ui.pages.results_page    import ResultsPage
from ui.pages.portfolio_page  import PortfolioPage
from ui.pages.goal_page       import GoalPage
from ui.pages.backtest_page   import BacktestPage
from ui.pages.signals_page    import SignalsPage
from ui.pages.factor_page     import FactorPage
from ui.pages.config_page     import ConfigPage
from ui.pages.logs_page       import LogsPage
from ui.pages.poolconfig_page import PoolConfigPage
from ui.theme import COLORS
from ui.components.market_combo import MarketComboBox
from utils.logger import logger
import sys
import traceback
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot, QTimer, QThread
from PyQt6.QtWidgets import QApplication, QMessageBox
from ui.components.market_combo import MarketComboBox
from ui.components.regionlabel import RegionLabel
from core.qlibhelper import _check_qlib_init

class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self, app):
        from core.app_state import get_state
        reg_name = get_state().reg_name
        super().__init__()
        self.setWindowTitle("QuantByQlib — 美股量化辅助决策平台")
        self.setWindowTitle(f"QuantByQlib — {reg_name}量化辅助决策平台")
        self.app = app

        # 自适应屏幕大小：取可用区域的 95%，但不低于 960×600
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry()
        w = max(960,  int(avail.width()  * 0.95))
        h = max(600,  int(avail.height() * 0.95))
        self.setMinimumSize(960, 600)
        self.resize(w, h)
        # 居中显示
        self.move(
            avail.x() + (avail.width()  - w) // 2,
            avail.y() + (avail.height() - h) // 2,
        )

        self._pages: dict[str, QWidget] = {}
        self._scrolls: dict[str, QScrollArea] = {}
        self._setup_ui()
        self._setup_statusbar()
        self._connect_events()

        # 启动后默认显示仪表盘（延迟到事件循环开始后执行，确保 stack 已就绪）
        QTimer.singleShot(0, lambda: self._sidebar.navigate_to("dashboard"))
        # 若本地已有美股 Qlib 数据，后台自动初始化（不阻塞 UI）
        QTimer.singleShot(500, self._auto_init_qlib)

    # ── UI 构建 ────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        # ===== 左右结构=====
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 左侧：侧边栏
        self._sidebar = Sidebar()
        self._sidebar.page_changed.connect(self._on_page_changed)
        root_layout.addWidget(self._sidebar)

        # 右侧：页面容器
        self._stack = QStackedWidget()
        self._stack.setObjectName("content_area")
        root_layout.addWidget(self._stack, stretch=1)

        # 注册所有页面（用 QScrollArea 包裹，适配小屏）
        page_classes = {
            "dashboard": DashboardPage,
            "screening": ScreeningPage,
            "results":   ResultsPage,
            "portfolio": PortfolioPage,
            "goal":      GoalPage,
            "backtest":  BacktestPage,
            "signals":   SignalsPage,
            "factor":    FactorPage,
            "config":    ConfigPage,
            "logs":      LogsPage,
            "universe":  PoolConfigPage,
        }
        for key, PageClass in page_classes.items():
            page = PageClass()
            self._pages[key] = page
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(page)
            self._scrolls[key] = scroll
            self._stack.addWidget(scroll)

    def _setup_statusbar(self) -> None:
        bar = QStatusBar()
        bar.setObjectName("statusbar")
        self.setStatusBar(bar)

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        bar.addWidget(self._status_label)

        bar.addPermanentWidget(QLabel("  "))
        self._qlib_reg_status = RegionLabel()
        self._qlib_reg_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        bar.addPermanentWidget(self._qlib_reg_status)

        bar.addPermanentWidget(QLabel("  "))
        self._qlib_status = QLabel("Qlib: 未初始化")
        self._qlib_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        bar.addPermanentWidget(self._qlib_status)

        bar.addPermanentWidget(QLabel("  "))
        self._time_label = QLabel("")
        self._time_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        bar.addPermanentWidget(self._time_label)

        # 时钟更新
        timer = QTimer(self)
        timer.timeout.connect(self._update_clock)
        timer.start(1000)
        self._update_clock()

    # ── 事件连接 ───────────────────────────────────────────

    def _connect_events(self) -> None:
        from core.event_bus import get_event_bus
        bus = get_event_bus()

        # 导航事件（来自其他页面触发跳转）
        bus.navigate_to.connect(self._on_navigate_to)

        # 状态栏消息
        bus.status_message.connect(self._show_status)

        # 切换市场事件
        bus.reg_changed.connect(self._on_reg_changed_to)  # 切换市场后导航到仪表盘 
        
        # Qlib 初始化事件
        bus.qlib_initialized.connect(self._on_qlib_initialized)

        # 选股运行（由 screening_page 触发，_pages 仍保存 page 实例）
        screening_page: ScreeningPage = self._pages["screening"]
        screening_page.run_requested.connect(self._on_run_screening)

        # 个股详情（仪表盘搜索 / 选股结果点击 → 导航到结果页并加载面板）
        bus.show_ticker_detail.connect(self._on_show_ticker_detail)

    # ── 页面切换 ───────────────────────────────────────────

    def _on_page_changed(self, page_key: str) -> None:
        if page_key in self._scrolls:
            self._stack.setCurrentWidget(self._scrolls[page_key])

    def _on_navigate_to(self, page_key: str) -> None:
        """事件总线触发的页面跳转（带侧边栏同步）"""
        self._sidebar.navigate_to(page_key)
        
        
    def _on_reg_changed_to(self, reg: str, reg_name: str) -> None:
        """响应市场切换事件：导航到仪表盘并显示提示"""
        self.app.setApplicationDisplayName(f"QuantByQlib — {reg_name}量化辅助决策平台")
        self.setWindowTitle(f"QuantByQlib — {reg_name}量化辅助决策平台")
        self._sidebar._setup_reg(reg, reg_name)
        # 触发全局事件通知其他组件（如主窗口）更新显示
        self._show_status(f"已切换市场到 {reg}，请在「参数配置」确认数据源设置")
        
        # 强制初始化 qlib 状态（切换市场后需要重新检测数据）
        # ── 检测 Qlib 初始化状态（延迟到事件循环后，确保主窗口信号连接就绪）
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        QTimer.singleShot(50, lambda: _check_qlib_init(bus))
        bus.status_message.emit("QuantByQlib 已就绪")
    
        # 启动后默认显示仪表盘（延迟到事件循环开始后执行，确保 stack 已就绪）
        QTimer.singleShot(0, lambda: self._sidebar.navigate_to("dashboard"))
        
        # 若本地已有美股 Qlib 数据，后台自动初始化（不阻塞 UI）
        QTimer.singleShot(500, self._auto_init_qlib) # 会自动转到{reg}_data （异常）

    # ── 业务事件处理 ───────────────────────────────────────

    def _on_run_screening(self, strategy_key: str, instrument_range: str) -> None:
        """启动量化选股 Worker"""
        from core.event_bus import get_event_bus
        from PyQt6.QtCore import QThreadPool
        from workers.screening_worker import ScreeningWorker

        bus = get_event_bus()
        bus.status_message.emit(f"正在运行策略：{strategy_key}...")
        bus.screening_started.emit(strategy_key)
        
        # 需要测试，用新的WorkerManager，还是用原来的 _screening_worker
        # 创建管理器
        #from workers.screening_worker import WorkerManager
        #manager = WorkerManager()
        #worker = manager.start_screening(strategy_key, instrument_range, bus)
        #QThreadPool.globalInstance().start(manager.current_worker)

        # 记录当前 worker 以支持取消
        self._screening_worker = ScreeningWorker(strategy_key, instrument_range)
        # Worker 信号同步到事件总线
        self._screening_worker.signals.progress.connect(bus.screening_progress.emit)
        self._screening_worker.signals.completed.connect(bus.screening_completed.emit)
        self._screening_worker.signals.failed.connect(bus.screening_failed.emit)

        QThreadPool.globalInstance().start(self._screening_worker)

    def _on_qlib_initialized(self) -> None:
        self._qlib_status.setText("Qlib: 🟢 就绪")
        self._qlib_status.setStyleSheet(f"color: {COLORS['success']}; font-size: 12px;")
        self._sidebar.set_qlib_status(True)

    def _on_show_ticker_detail(self, ticker: str, quant_score: object) -> None:
        """响应 show_ticker_detail 事件：导航到结果页并加载个股面板"""
        from ui.pages.results_page import ResultsPage
        from PyQt6.QtCore import QTimer
        results_page: ResultsPage = self._pages["results"]
        self._sidebar.navigate_to("results")
        score = float(quant_score) if quant_score is not None else None
        # 延迟一帧，确保页面已切换完成再加载面板
        QTimer.singleShot(50, lambda: results_page._detail_panel.load(ticker, quant_score=score))

    # ── 工具方法 ───────────────────────────────────────────

    def _auto_init_qlib(self) -> None:
        """后台检测并自动初始化 Qlib（若美股数据已存在）"""
        from PyQt6.QtCore import QThreadPool, QRunnable, QObject, pyqtSignal, pyqtSlot

        class _InitSignals(QObject):
            done = pyqtSignal(bool)

        class _InitWorker(QRunnable):
            def __init__(self):
                super().__init__()
                self.signals = _InitSignals()
                self.setAutoDelete(True)

            @pyqtSlot()
            def run(self):
                try:
                    from data.qlib_manager import auto_init_if_data_ready
                    ok = auto_init_if_data_ready()
                    self.signals.done.emit(ok)
                except Exception:
                    self.signals.done.emit(False)

        worker = _InitWorker()
        worker.signals.done.connect(self._on_auto_init_done)
        QThreadPool.globalInstance().start(worker)

    def _on_auto_init_done(self, ok: bool) -> None:
        if ok:
            self._on_qlib_initialized()

    def _show_status(self, message: str) -> None:
        self._status_label.setText(message)
        # 5秒后恢复"就绪"
        QTimer.singleShot(5000, lambda: self._status_label.setText("就绪"))

    def _update_clock(self) -> None:
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._time_label.setText(now)
