"""
选股结果页面
左侧：排名列表（股票/得分/信号/今日涨跌）
右侧：StockDetailPanel 个股详情面板（点击行后加载）
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QSplitter, QHeaderView, QLineEdit, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from ui.theme import COLORS
from ui.components.stock_detail_panel import StockDetailPanel


class ResultsPage(QWidget):
    """选股结果页面：排名列表 + 右侧个股详情面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results: list[dict] = []
        self._setup_ui()
        self._connect_events()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(12)

        # ── 页面标题行 ────────────────────────────────────────
        header_row = QHBoxLayout()
        self._title_label = QLabel("📋 选股结果")
        self._title_label.setObjectName("page_title")
        header_row.addWidget(self._title_label)
        header_row.addStretch()

        self._export_btn = QPushButton("📥 导出CSV")
        self._export_btn.setObjectName("btn_secondary")
        self._export_btn.clicked.connect(self._on_export)
        header_row.addWidget(self._export_btn)

        self._signal_btn = QPushButton("⚡ 生成信号")
        self._signal_btn.clicked.connect(self._on_generate_signals)
        header_row.addWidget(self._signal_btn)

        self._chart_btn = QPushButton("📊 股票图表")
        self._chart_btn.clicked.connect(self._on_open_chart)
        header_row.addWidget(self._chart_btn)
        layout.addLayout(header_row)

        # ── 筛选行 ────────────────────────────────────────────
        filter_row = QHBoxLayout()
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["全部信号", "买入", "持有", "卖出"])
        self._filter_combo.currentTextChanged.connect(self._apply_filter)
        filter_row.addWidget(QLabel("筛选:"))
        filter_row.addWidget(self._filter_combo)
        filter_row.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索股票代码...")
        self._search_input.setMaximumWidth(200)
        self._search_input.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._search_input)
        layout.addLayout(filter_row)

        # ── 左右分割器 ────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)

        # 左侧：排名表格
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        #self._table.setColumnCount(5)
        #self._table.setHorizontalHeaderLabels(["排名", "股票", "Qlib 得分", "信号", "今日"])
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["股票", "Qlib 得分", "信号", "今日"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        #header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        #for col in (0, 2, 3, 4):
        #    header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        left_layout.addWidget(self._table)

        self._count_label = QLabel("共 0 支股票")
        self._count_label.setStyleSheet(f"color:{COLORS['text_muted']}; font-size:12px;")
        left_layout.addWidget(self._count_label)

        splitter.addWidget(left_widget)

        # 右侧：StockDetailPanel
        self._detail_panel = StockDetailPanel()
        self._detail_panel.add_to_portfolio.connect(self._on_add_to_portfolio)
        self._detail_panel.run_strategy.connect(self._on_run_strategy)
        splitter.addWidget(self._detail_panel)

        splitter.setSizes([360, 640])
        layout.addWidget(splitter, stretch=1)

    def _connect_events(self) -> None:
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        bus.screening_completed.connect(self.load_results)

    def load_results(self, results: list[dict]) -> None:
        """加载选股结果数据（由事件总线触发）"""
        self._results = results
        strategy = results[0].get("strategy", "未知策略") if results else "未知策略"
        from datetime import datetime
        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        self._title_label.setText(f"📋 选股结果  策略: {strategy}  {now}")
        self._populate_table(results)
        self._detail_panel.clear()

    def _populate_table(self, results: list[dict]) -> None:
        self._table.setRowCount(0)
        signal_map = {
            "BUY":        ("买入",    COLORS["success"]),
            "STRONG_BUY": ("强烈买入", COLORS["success"]),
            "SELL":       ("卖出",    COLORS["danger"]),
            "HOLD":       ("持有",    COLORS["warning"]),
            "WATCH":      ("观察",    COLORS["info"]),
        }
        for i, item in enumerate(results):
            row = self._table.rowCount()
            self._table.insertRow(row)

            #rank_item = QTableWidgetItem(str(i + 1))
            #rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            ticker_item = QTableWidgetItem(item.get("ticker", "--"))
            bold_font = QFont()
            bold_font.setBold(True)
            ticker_item.setFont(bold_font)

            score = item.get("score", 0.0)
            score_item = QTableWidgetItem(f"{score:.3f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            signal = item.get("signal", "HOLD")
            sig_label, sig_color = signal_map.get(signal, (signal, COLORS["text_muted"]))
            signal_item = QTableWidgetItem(sig_label)
            signal_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            signal_item.setForeground(QColor(sig_color))

            change = item.get("change_pct")
            if change is not None:
                sign = "+" if change >= 0 else ""
                change_text = f"{sign}{change:.2f}%"
                change_color = COLORS["success"] if change >= 0 else COLORS["danger"]
            else:
                change_text = "--"
                change_color = COLORS["text_muted"]
            change_item = QTableWidgetItem(change_text)
            change_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            change_item.setForeground(QColor(change_color))

            #for col, cell in enumerate(
            #    [rank_item, ticker_item, score_item, signal_item, change_item]
            #):
            for col, cell in enumerate(
                [ticker_item, score_item, signal_item, change_item]
            ):
                self._table.setItem(row, col, cell)

        self._count_label.setText(f"共 {len(results)} 支股票")

    def _on_row_selected(self) -> None:
        rows = self._table.selectedItems()
        if not rows:
            return
        row = self._table.currentRow()
        ticker_item = self._table.item(row, 0)
        score_item  = self._table.item(row, 1)
        if not ticker_item:
            return

        ticker = ticker_item.text()
        score  = float(score_item.text()) if score_item else None
        # 读取 Qlib 信号列（第3列）和排名（第0列）
        signal_item = self._table.item(row, 2)
        #rank_item   = self._table.item(row, 0)
        qlib_signal = signal_item.text() if signal_item else None
        #qlib_rank   = int(rank_item.text()) if rank_item else None
        qlib_rank   = None

        # 直接加载个股详情面板（不经过事件总线，避免双重触发）
        self._detail_panel.load(ticker, quant_score=score,
                                qlib_signal=qlib_signal, qlib_rank=qlib_rank)

    def _apply_filter(self) -> None:
        keyword = self._search_input.text().strip().upper()
        signal_filter = self._filter_combo.currentText()
        signal_map = {"买入": "BUY", "持有": "HOLD", "卖出": "SELL", "全部信号": None}
        target_signal = signal_map.get(signal_filter)

        filtered = [
            r for r in self._results
            if (not keyword or keyword in r.get("ticker", "").upper())
            and (target_signal is None or r.get("signal") == target_signal)
        ]
        self._populate_table(filtered)

    def _on_add_to_portfolio(self, ticker: str) -> None:
        """跳转到持仓管理页并打开买入对话框"""
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        bus.navigate_to.emit("portfolio")
        # 延迟触发，等页面切换完成
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, lambda: bus.open_buy_dialog.emit(ticker)
                          if hasattr(bus, "open_buy_dialog") else None)

    def _on_run_strategy(self, ticker: str) -> None:
        """跳转到回测页，并携带 ticker 提示"""
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        bus.navigate_to.emit("backtest")
        bus.backtest_ticker_hint.emit(ticker)

    def _on_export(self) -> None:
        if not self._results:
            return
        from PyQt6.QtWidgets import QFileDialog
        import csv
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "选股结果.csv", "CSV 文件 (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, fieldnames=["ticker", "score", "signal", "change_pct"]
            )
            writer.writeheader()
            writer.writerows(self._results)

    def _on_generate_signals(self) -> None:
        from core.event_bus import get_event_bus
        get_event_bus().navigate_to.emit("signals")

    def _on_open_chart(self) -> None:
        ticker = None
        
        if self._detail_panel._current_ticker:
            ticker = self._detail_panel._current_ticker
        else:
            row = self._table.currentRow()
            if row < 0 and self._table.rowCount() > 0:
                row = 0
                self._table.selectRow(0)
            if row >= 0:
                ticker_item = self._table.item(row, 0)
                if ticker_item:
                    ticker = ticker_item.text()
        
        if not ticker:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "请先搜索或选择一支股票")
            return
        
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        bus.navigate_to.emit("chart")
        bus.stock_chart_requested.emit(ticker)
