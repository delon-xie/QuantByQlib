"""
参数配置页面
- API Key 配置（FMP/Finnhub/Alpha Vantage/DeepSeek）
- Qlib 数据下载与初始化（真实 Worker）
- OpenBB 连接测试（真实 Worker）
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QGroupBox, QGridLayout,
    QProgressBar, QTextEdit, QScrollArea, QFrame,
    QSizePolicy, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QFileDialog
)
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QColor
from ui.theme import COLORS
from core.app_state import get_state
from ui.components.instrument_combobox import InstrumentComboBox

class ConfigPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._download_worker = None
        self._test_worker = None
        self._collect_worker = None
        self._setup_ui()
        self._load_saved_keys()
        self._refresh_qlib_status()

    def _on_collect_clicked(self):
        instrument = self._instrument_combo.currentText()
        if not instrument:
            return "all"

        # 复用你原来的逻辑
        self._on_collect(instrument)

    def _setup_ui(self) -> None:
        # 外层滚动区（内容较多）
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(16)

        title = QLabel("⚙️ 参数配置")
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("配置 API Key 和下载 Qlib 数据后，系统各功能将正常工作。")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # ── API Key 配置区 ────────────────────────────────
        api_group = QGroupBox("数据源 API Key 配置（均为免费注册）")
        api_layout = QGridLayout(api_group)
        api_layout.setSpacing(10)
        api_layout.setColumnStretch(1, 1)

        labels = [
            ("FMP Key:",           "Financial Modeling Prep — 基本面/分析师评级（免费 250次/天）",   "FMP_API_KEY"),
            ("Finnhub Key:",       "Finnhub — 新闻/情绪（免费 60次/分钟）",                        "FINNHUB_API_KEY"),
            ("Alpha Vantage Key:", "Alpha Vantage — K线历史数据（免费 25次/天）",                   "ALPHA_VANTAGE_API_KEY"),
            ("DeepSeek Key:",      "DeepSeek API Key（sk-...）",                                  "DEEPSEEK_API_KEY"),
            ("Anthropic Key:",     "Anthropic Claude API Key（sk-ant-...）— 用于 Claude 因子发现", "ANTHROPIC_API_KEY"),
            ("LongPort App Key:",  "长桥 App Key — open.longportapp.com 申请",                   "LONGPORT_APP_KEY"),
            ("LongPort Secret:",   "长桥 App Secret",                                             "LONGPORT_APP_SECRET"),
            ("LongPort Token:",    "长桥 Access Token（持仓账户行情权限）",                         "LONGPORT_ACCESS_TOKEN"),
        ]

        self._key_inputs: dict[str, QLineEdit] = {}
        self._key_status: dict[str, QLabel] = {}

        for i, (lbl_text, placeholder, env_key) in enumerate(labels):
            lbl = QLabel(lbl_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            api_layout.addWidget(lbl, i, 0)

            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setEchoMode(QLineEdit.EchoMode.Password)
            api_layout.addWidget(inp, i, 1)
            self._key_inputs[env_key] = inp

            status = QLabel("⚪")
            status.setFixedWidth(24)
            api_layout.addWidget(status, i, 2)
            self._key_status[env_key] = status

        # ── RD-Agent LLM 选择 ──
        llm_row = QHBoxLayout()
        llm_lbl = QLabel("因子发现 LLM：")
        llm_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        llm_lbl.setFixedWidth(120)
        llm_row.addWidget(llm_lbl)

        self._llm_combo = QComboBox()
        self._llm_combo.addItems([
            "deepseek-chat          (DeepSeek — 低成本，适合高频运行)",
            "deepseek-reasoner      (DeepSeek R1 — 推理增强，更严格遵循约束)",
            "claude-opus-4-6        (Claude Opus 4.6 — 最强创新力，最高质量)",
            "claude-sonnet-4-6      (Claude Sonnet 4.6 — 均衡性价比)",
            "gpt-4o                 (OpenAI GPT-4o — 均衡)",
        ])
        self._llm_combo.setToolTip(
            "选择 RD-Agent 因子发现使用的 LLM。\n"
            "Claude 系列需要填写 Anthropic Key；DeepSeek 需要 DeepSeek Key；GPT 需要 OpenAI Key。"
        )
        llm_row.addWidget(self._llm_combo, stretch=1)
        api_layout.addLayout(llm_row, len(labels), 0, 1, 3)

        # 操作按钮行
        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 保存配置")
        save_btn.setMinimumHeight(38)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        self._test_btn = QPushButton("🔗 测试连接")
        self._test_btn.setObjectName("btn_secondary")
        self._test_btn.setMinimumHeight(38)
        self._test_btn.clicked.connect(self._on_test_connection)
        btn_row.addWidget(self._test_btn)
        btn_row.addStretch()

        # 显示/隐藏密码
        show_btn = QPushButton("👁 显示Key")
        show_btn.setObjectName("btn_secondary")
        show_btn.setMinimumHeight(38)
        show_btn.setCheckable(True)
        show_btn.toggled.connect(self._toggle_key_visibility)
        btn_row.addWidget(show_btn)

        api_layout.addLayout(btn_row, len(labels) + 1, 0, 1, 3)
        layout.addWidget(api_group)

        # ── 测试结果表格 ─────────────────────────────────
        self._test_table = QTableWidget(0, 3)
        self._test_table.setHorizontalHeaderLabels(["数据源", "状态", "详情"])
        self._test_table.setMaximumHeight(160)
        self._test_table.setVisible(False)
        self._test_table.verticalHeader().setVisible(False)
        self._test_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hdr = self._test_table.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._test_table)

        # ── Qlib 数据管理区 ──────────────────────────────
        qlib_group = QGroupBox("Qlib 美股数据管理")
        qlib_layout = QVBoxLayout(qlib_group)
        qlib_layout.setSpacing(10)

        # 状态行
        status_row = QHBoxLayout()
        self._qlib_status_label = QLabel("状态：⚪ 检测中...")
        self._qlib_status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        status_row.addWidget(self._qlib_status_label)
        status_row.addStretch()
        self._qlib_stats_label = QLabel("")
        self._qlib_stats_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        status_row.addWidget(self._qlib_stats_label)
        qlib_layout.addLayout(status_row)

        # 说明
        info = QLabel(
            "数据集：SunsetWolf/qlib_dataset 美股日频数据（约 450MB zip，解压后约 1.5GB）。\n"
            "包含约 8994 支美股，日期范围 1999-12-31 ~ 2020-11-10，供 LightGBM/LSTM/GRU 模型训练使用。\n"
            "下载完成后 Qlib ML 量化模型即可正常使用，请确保网络稳定。"
        )
        info.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        info.setWordWrap(True)
        qlib_layout.addWidget(info)

        # 进度条
        self._download_progress = QProgressBar()
        self._download_progress.setVisible(False)
        self._download_progress.setMinimumHeight(12)
        qlib_layout.addWidget(self._download_progress)

        self._download_status = QLabel("")
        self._download_status.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        qlib_layout.addWidget(self._download_status)

        # 下载日志
        self._download_log = QTextEdit()
        self._download_log.setReadOnly(True)
        self._download_log.setMaximumHeight(140)
        self._download_log.setPlaceholderText("下载日志将在这里实时显示...")
        self._download_log.setStyleSheet(
            f"background: #0A0718; color: {COLORS['text_secondary']}; "
            f"font-family: 'Courier New', monospace; font-size: 11px;"
        )
        qlib_layout.addWidget(self._download_log)

        # 按钮行
        dl_btn_row = QHBoxLayout()
        self._dl_sp500_btn = QPushButton("⬇️ 下载美股 Qlib 数据（约 450MB）")
        self._dl_sp500_btn.setMinimumHeight(38)
        self._dl_sp500_btn.setToolTip(
            "下载 SunsetWolf/qlib_dataset 美股日频数据集\n"
            "8994 支美股，1999-12-31 ~ 2020-11-10\n"
            "下载后 LightGBM/LSTM/GRU 模型可正常运行"
        )
        self._dl_sp500_btn.clicked.connect(lambda: self._on_download("sp500"))
        dl_btn_row.addWidget(self._dl_sp500_btn)

        self._update_btn = QPushButton("🔄 重新下载（覆盖更新）")
        self._update_btn.setObjectName("btn_secondary")
        self._update_btn.setMinimumHeight(38)
        self._update_btn.setToolTip(
            "重新下载并覆盖本地数据\n"
            "适用于本地数据损坏或需要重置的情况"
        )
        self._update_btn.clicked.connect(self._on_update)
        dl_btn_row.addWidget(self._update_btn)

        self._dl_cancel_btn = QPushButton("⏹ 取消")
        self._dl_cancel_btn.setObjectName("btn_danger")
        self._dl_cancel_btn.setMinimumHeight(38)
        self._dl_cancel_btn.setVisible(False)
        self._dl_cancel_btn.clicked.connect(self._on_cancel_download)
        dl_btn_row.addWidget(self._dl_cancel_btn)

        qlib_layout.addLayout(dl_btn_row)
        layout.addWidget(qlib_group)

        # ── yfinance 采集最新数据区 ───────────────────────
        collect_group = QGroupBox("采集最新美股数据（yfinance）")
        collect_layout = QVBoxLayout(collect_group)
        collect_layout.setSpacing(10)

        collect_info = QLabel(
            "现有 Qlib 数据截至 2020-11-10，此功能通过 Yahoo Finance 补充最新行情，直接写入 Qlib 二进制格式。\n"
            "历史数据不会被覆盖，仅追加新日期的 OHLCV 数据（含复权因子 factor）。\n"
            "S&P 500 约 503 支，预计 1-2 分钟；Nasdaq 100 约 100 支，预计 20-40 秒。"
        )
        collect_info.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        collect_info.setWordWrap(True)
        collect_layout.addWidget(collect_info)

        # 进度条
        self._collect_progress = QProgressBar()
        self._collect_progress.setVisible(False)
        self._collect_progress.setMinimumHeight(12)
        collect_layout.addWidget(self._collect_progress)

        self._collect_status = QLabel("")
        self._collect_status.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        collect_layout.addWidget(self._collect_status)

        # 日志框
        self._collect_log = QTextEdit()
        self._collect_log.setReadOnly(True)
        self._collect_log.setMaximumHeight(140)
        self._collect_log.setPlaceholderText("采集日志将在这里实时显示...")
        self._collect_log.setStyleSheet(
            f"background: #0A0718; color: {COLORS['text_secondary']}; "
            f"font-family: 'Courier New', monospace; font-size: 11px;"
        )
        collect_layout.addWidget(self._collect_log)

        # 按钮行
        col_btn_row = QHBoxLayout()
        # ---- 下拉框 ----
        self._instrument_combo = InstrumentComboBox()
        self._instrument_combo.setMinimumHeight(38)
        self._instrument_combo.setPlaceholderText("请选择采集范围")
        self._instrument_combo.setToolTip(
            "选择股票范围：\n"
            f"从 {get_state().reg}_data/instruments 选择txt文件作为股票范围\n"
            "默认选择（all）全部股票：采集所有股票的最新数据（耗时较长）\n"
        )

        # ---- 采集按钮 ----
        self._col_collect_btn = QPushButton("⬇️ 采集（选中范围）")
        self._col_collect_btn.setObjectName("btn_primary")
        self._col_collect_btn.setMinimumHeight(38)
        self._col_collect_btn.clicked.connect(self._on_collect_clicked)

        col_btn_row.addWidget(self._instrument_combo, 2)
        col_btn_row.addWidget(self._col_collect_btn, 2)
        
        #self._col_sp500_btn = QPushButton("⬇️ 采集 S&P 500（推荐）")
        #self._col_sp500_btn.setMinimumHeight(38)
        #self._col_sp500_btn.setToolTip(
        #    "从 Yahoo Finance 采集 S&P 500 约 503 支股票最新日频数据\n"
        #    "追加写入 Qlib 二进制格式，历史数据不会被覆盖\n"
        #    "预计 1-2 分钟（取决于网络速度）"
        #)
        #self._col_sp500_btn.clicked.connect(lambda: self._on_collect("sp500"))
        #col_btn_row.addWidget(self._col_sp500_btn)

        #self._col_ndx_btn = QPushButton("⬇️ 采集 Nasdaq 100")
        #self._col_ndx_btn.setObjectName("btn_secondary")
        #self._col_ndx_btn.setMinimumHeight(38)
        #self._col_ndx_btn.setToolTip(
        #    "从 Yahoo Finance 采集 Nasdaq 100 约 100 支股票最新日频数据\n"
        #    "预计 20-40 秒"
        #)
        #col_btn_row.addWidget(self._col_ndx_btn)
        
        #self._col_all_btn = QPushButton("⬇️ 采集全部股票")
        #self._col_all_btn.setObjectName("btn_secondary")
        #self._col_all_btn.setMinimumHeight(38)
        #self._col_all_btn.setToolTip(
        #    "从 Yahoo Finance 采集 全部 9000 余支股票最新日频数据\n"
        #    "追加写入 Qlib 二进制格式，历史数据不会被覆盖\n"
        #    "预计 10-20 分钟（取决于网络速度）"
        #)
        #self._col_all_btn.clicked.connect(lambda: self._on_collect("all"))
        #col_btn_row.addWidget(self._col_all_btn)

        self._col_cancel_btn = QPushButton("⏹ 取消")
        self._col_cancel_btn.setObjectName("btn_danger")
        self._col_cancel_btn.setMinimumHeight(38)
        self._col_cancel_btn.setVisible(False)
        self._col_cancel_btn.clicked.connect(self._on_cancel_collect)
        col_btn_row.addWidget(self._col_cancel_btn)

        collect_layout.addLayout(col_btn_row)
        layout.addWidget(collect_group)

        # ── 每日导出目录配置 ──────────────────────────────
        export_group = QGroupBox("每日数据导出目录配置")
        export_layout = QGridLayout(export_group)
        export_layout.setSpacing(8)
        export_layout.setColumnStretch(1, 1)

        export_dirs = [
            ("根目录：",       "TRADING_JOURNAL_DIR",  f"~/{self._state.reg_name}交易日记",         "K线图/信号/政体/回测等所有导出文件的根目录"),
            ("K线图目录：",    "EXPORT_PICS_DIR",      "（默认：根目录/pics）",   "每日导出 K线图 PNG 的存放目录"),
            ("信号CSV目录：",  "EXPORT_SIGNALS_DIR",   "（默认：根目录/signals）","策略选股信号 CSV 的存放目录"),
            ("HMM政体目录：",  "EXPORT_REGIME_DIR",    "（默认：根目录/regime）", "HMM 市场政体 JSON 的存放目录"),
            ("回测报告目录：", "EXPORT_BACKTEST_DIR",  "（默认：根目录/backtest）","月度回测绩效 JSON 的存放目录"),
            ("AI报告目录：",   "REPORTS_DIR",          f"~/Documents/{self._state.reg_name}交易日记/reports", "AI 分析报告和每日摘要 MD 文件的存放目录"),
        ]

        self._export_dir_inputs: dict[str, QLineEdit] = {}
        for i, (lbl_text, env_key, placeholder, tooltip) in enumerate(export_dirs):
            lbl = QLabel(lbl_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            export_layout.addWidget(lbl, i, 0)

            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setToolTip(tooltip)
            export_layout.addWidget(inp, i, 1)
            self._export_dir_inputs[env_key] = inp

            browse_btn = QPushButton("📂")
            browse_btn.setFixedWidth(36)
            browse_btn.setToolTip("浏览选择目录")
            browse_btn.clicked.connect(lambda checked, e=env_key: self._on_browse_dir(e))
            export_layout.addWidget(browse_btn, i, 2)

        export_hint = QLabel(
            "留空则使用默认路径。修改后点击「保存配置」立即生效，下次导出将写入新目录。"
        )
        export_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        export_hint.setWordWrap(True)
        export_layout.addWidget(export_hint, len(export_dirs), 0, 1, 3)

        layout.addWidget(export_group)
        layout.addStretch()

    # ── 数据加载 ───────────────────────────────────────────

    # model id 与下拉项索引的映射
    _LLM_MODEL_IDS = [
        "deepseek-chat",
        "deepseek-reasoner",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "gpt-4o",
    ]

    def _load_saved_keys(self) -> None:
        """从 .env 文件加载已保存的 Key 和 LLM 选择"""
        env_path = Path(".env")
        if not env_path.exists():
            return
        try:
            from dotenv import dotenv_values
            vals = dotenv_values(env_path)
            placeholders = {
                "your_fmp_api_key_here", "your_finnhub_api_key_here",
                "your_alpha_vantage_key_here", "your_deepseek_api_key_here",
            }
            for env_key, inp in self._key_inputs.items():
                val = vals.get(env_key, "")
                if val and val not in placeholders:
                    inp.setText(val)
                    self._key_status[env_key].setText("🟡")
            # 恢复 LLM 选择
            saved_model = vals.get("CHAT_MODEL", "deepseek-chat")
            model_id = saved_model.split("/")[-1]  # 兼容 "deepseek/deepseek-chat" 格式
            if model_id in self._LLM_MODEL_IDS:
                self._llm_combo.setCurrentIndex(self._LLM_MODEL_IDS.index(model_id))
            # 恢复导出目录
            for env_key, inp in self._export_dir_inputs.items():
                val = vals.get(env_key, "")
                if val:
                    inp.setText(val)
        except Exception as e:
            #logger.debug(f"加载 .env 失败：{e}")
            pass

    def _refresh_qlib_status(self) -> None:
        """检测并刷新 Qlib 数据状态"""
        try:
            from data.qlib_manager import is_initialized, get_data_stats
            ok = is_initialized()
            if ok:
                stats = get_data_stats()
                self._qlib_status_label.setText("状态：🟢 已初始化")
                self._qlib_stats_label.setText(
                    f"{stats['stock_count']} 支股票  |  "
                    f"{stats['date_range']}  |  "
                    f"{stats['size_gb']} GB  |  "
                    f"更新：{stats['last_modified']}"
                )
            else:
                self._qlib_status_label.setText("状态：⚪ 未初始化（需要下载数据）")
                self._qlib_stats_label.setText("")
        except Exception as e:
            self._qlib_status_label.setText(f"状态：❌ 检测失败：{e}")

    # ── 保存配置 ───────────────────────────────────────────

    def _on_save(self) -> None:
        """将 API Key 写入 .env 文件并更新环境变量"""
        env_path = Path(".env")

        # 读取现有内容
        existing: dict[str, str] = {}
        if env_path.exists():
            try:
                from dotenv import dotenv_values
                existing = dict(dotenv_values(env_path))
            except Exception:
                pass

        saved_count = 0
        for env_key, inp in self._key_inputs.items():
            val = inp.text().strip()
            if val:
                existing[env_key] = val
                os.environ[env_key] = val
                self._key_status[env_key].setText("🟡")
                saved_count += 1

        selected_model = self._LLM_MODEL_IDS[self._llm_combo.currentIndex()]
        existing["CHAT_MODEL"] = selected_model
        os.environ["CHAT_MODEL"] = selected_model

        # 保存导出目录
        for env_key, inp in self._export_dir_inputs.items():
            val = inp.text().strip()
            if val:
                existing[env_key] = val
                os.environ[env_key] = val
            elif env_key in existing:
                # 用户清空则删除，回退默认
                del existing[env_key]
                os.environ.pop(env_key, None)

        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in existing.items():
                f.write(f"{k}={v}\n")

        QMessageBox.information(
            self, "保存成功",
            f"已保存 {saved_count} 个 API Key 到 .env 文件。\n"
            "点击「测试连接」验证各数据源是否正常。"
        )

    # ── 连接测试 ───────────────────────────────────────────

    def _on_test_connection(self) -> None:
        """启动 OpenBB 连接测试 Worker"""
        self._test_btn.setEnabled(False)
        self._test_btn.setText("🔗 测试中...")

        # 准备测试结果表格
        providers = [("yfinance", "yfinance（无需Key）"),
                     ("fmp", "FMP"),
                     ("finnhub", "Finnhub"),
                     ("alpha_vantage", "Alpha Vantage")]
        self._test_table.setRowCount(0)
        self._provider_rows: dict[str, int] = {}
        for pkey, pname in providers:
            row = self._test_table.rowCount()
            self._test_table.insertRow(row)
            self._test_table.setItem(row, 0, QTableWidgetItem(pname))
            self._test_table.setItem(row, 1, QTableWidgetItem("⏳ 等待..."))
            self._test_table.setItem(row, 2, QTableWidgetItem(""))
            self._provider_rows[pkey] = row
        self._test_table.setVisible(True)

        from workers.openbb_test_worker import OpenBBTestWorker
        worker = OpenBBTestWorker()
        worker.signals.provider_result.connect(self._on_test_provider_result)
        worker.signals.completed.connect(self._on_test_completed)
        worker.signals.error.connect(lambda e: self._reset_test_btn())
        QThreadPool.globalInstance().start(worker)

    def _on_test_provider_result(self, provider: str, ok: bool, detail: str) -> None:
        row = self._provider_rows.get(provider, -1)
        if row < 0:
            return
        status = "✅ 正常" if ok else "❌ 失败"
        status_color = COLORS["success"] if ok else COLORS["danger"]
        status_item = QTableWidgetItem(status)
        status_item.setForeground(QColor(status_color))
        self._test_table.setItem(row, 1, status_item)
        self._test_table.setItem(row, 2, QTableWidgetItem(detail))

        # 如果成功，更新对应状态圆点
        key_map = {"fmp": "FMP_API_KEY", "finnhub": "FINNHUB_API_KEY",
                   "alpha_vantage": "ALPHA_VANTAGE_API_KEY"}
        env_key = key_map.get(provider)
        if env_key and ok and env_key in self._key_status:
            self._key_status[env_key].setText("🟢")

    def _on_test_completed(self, results: dict) -> None:
        self._reset_test_btn()
        ok_count = sum(1 for v in results.values() if v)
        from core.event_bus import get_event_bus
        get_event_bus().status_message.emit(f"连接测试完成：{ok_count}/{len(results)} 个数据源正常")
        if ok_count > 0:
            get_event_bus().openbb_configured.emit()

    def _reset_test_btn(self) -> None:
        self._test_btn.setEnabled(True)
        self._test_btn.setText("🔗 测试连接")

    # ── 导出目录浏览 ───────────────────────────────────────

    def _on_browse_dir(self, env_key: str) -> None:
        inp = self._export_dir_inputs.get(env_key)
        if inp is None:
            return
        start = inp.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "选择目录", start)
        if chosen:
            inp.setText(chosen)

    # ── Qlib 数据下载 ─────────────────────────────────────

    def _on_download(self, scope: str) -> None:
        """启动 Qlib 数据下载 Worker"""
        confirm = QMessageBox.question(
            self, "确认下载",
            f"将从 SunsetWolf/qlib_dataset 下载{self._state.reg_name} Qlib 数据集（真正的{self._state.reg_name}日频数据）。\n"
            f"文件约 450MB zip，解压后约 1.5GB，耗时约 5-15 分钟（取决于网速）。\n\n"
            f"下载完成后 LightGBM/LSTM/GRU 量化模型即可正常使用。\n\n"
            "确认开始下载？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._set_download_running(True)
        self._download_log.clear()
        self._append_log(f"[INFO] 开始下载{self._state.reg_name} Qlib 数据集（SunsetWolf/qlib_dataset）...")

        from workers.qlib_downloader import QlibDownloadWorker
        worker = QlibDownloadWorker(scope=scope)

        worker.signals.progress.connect(self._on_download_progress)
        worker.signals.log_line.connect(self._append_log)
        worker.signals.completed.connect(self._on_download_completed)
        worker.signals.error.connect(self._on_download_error)

        if(self._download_worker):
            self._download_worker = None
        self._download_worker = worker
        QThreadPool.globalInstance().start(self._download_worker)

    def _on_update(self) -> None:
        """重新下载最新美股 Qlib 数据集（SunsetWolf/qlib_dataset）"""
        confirm = QMessageBox.question(
            self, "确认更新",
            f"将从 SunsetWolf/qlib_dataset 重新下载{self._state.reg_name} Qlib 数据集。\n"
            f"约 450MB zip，解压后替换本地数据，Qlib ML 模型将可正常使用。\n\n"
            f"确认开始下载？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._set_download_running(True)
        self._download_log.clear()
        self._append_log(f"[INFO] 开始更新{self._state.reg_name} Qlib 数据集（SunsetWolf/qlib_dataset）...")

        from workers.qlib_downloader import QlibUpdateWorker
        worker = QlibUpdateWorker()
        worker.signals.progress.connect(self._on_download_progress)
        worker.signals.log_line.connect(self._append_log)
        worker.signals.completed.connect(self._on_download_completed)
        worker.signals.error.connect(self._on_download_error)
        self._download_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_cancel_download(self) -> None:
        if self._download_worker:
            self._download_worker.cancel()
        self._set_download_running(False)
        self._append_log("[INFO] 用户取消下载")

    def _on_download_progress(self, pct: int, msg: str) -> None:
        self._download_progress.setValue(pct)
        self._download_status.setText(msg)

    def _on_download_completed(self, ok: bool, msg: str) -> None:
        self._set_download_running(False)
        if ok:
            self._download_status.setText(f"✅ {msg}")
            self._download_progress.setValue(100)
            self._refresh_qlib_status()
        else:
            self._download_status.setText(f"❌ {msg}")
        self._download_worker = None

    def _on_download_error(self, err: str) -> None:
        self._set_download_running(False)
        self._append_log(f"[ERROR] {err}")
        self._download_worker = None

    def _set_download_running(self, running: bool) -> None:
        self._dl_sp500_btn.setEnabled(not running)
        self._update_btn.setEnabled(not running)
        self._dl_cancel_btn.setVisible(running)
        self._download_progress.setVisible(running)
        if running:
            self._download_progress.setValue(0)

    def _append_log(self, text: str) -> None:
        self._download_log.append(text)
        sb = self._download_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── 辅助 ──────────────────────────────────────────────

    def _toggle_key_visibility(self, visible: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        for inp in self._key_inputs.values():
            inp.setEchoMode(mode)

    def update_qlib_status(self, initialized: bool, last_update: str = "--") -> None:
        """由主窗口调用"""
        if initialized:
            self._qlib_status_label.setText("状态：🟢 已初始化")
        else:
            self._qlib_status_label.setText("状态：⚪ 未初始化")

    # ── yfinance 采集 ─────────────────────────────────────

    def _on_collect(self, scope: str) -> None:
        """启动 yfinance 数据采集 Worker"""
        # 根据scope参数确定scope_name的值
        if scope == "sp500":
            scope_name = "S&P 500（约 503 支）"
        elif scope == "nasdaq100":
            scope_name = "Nasdaq 100（约 100 支）"
        elif scope == "all":
            scope_name = "全部股票（约 9000 支）"
        else:
            scope_name = "未知范围"
        confirm = QMessageBox.question(
            self, "确认采集",
            f"将从 Yahoo Finance 采集 {scope_name} 最新日频数据。\n"
            "历史数据不会被覆盖，仅追加 2020-11-10 之后的新数据。\n\n"
            "确认开始采集？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._set_collect_running(True)
        self._collect_log.clear()
        self._collect_log.append(f"[INFO] 开始采集 {scope_name} 数据（yfinance）...")

        from workers.yfinance_collector import YFinanceCollectorWorker
        worker = YFinanceCollectorWorker(scope=scope)
        worker.signals.progress.connect(self._on_collect_progress)
        worker.signals.log_line.connect(self._append_collect_log)
        worker.signals.completed.connect(self._on_collect_completed)
        worker.signals.error.connect(self._on_collect_error)

        if(self._collect_worker):
            self._collect_worker = None
        self._collect_worker = worker
    
        QThreadPool.globalInstance().start(worker)

    def _on_cancel_collect(self) -> None:
        if self._collect_worker:
            self._collect_worker.cancel()
        self._set_collect_running(False)
        self._append_collect_log("[INFO] 用户取消采集")

    def _on_collect_progress(self, pct: int, msg: str) -> None:
        self._collect_progress.setValue(pct)
        self._collect_status.setText(msg)

    def _on_collect_completed(self, ok: bool, msg: str) -> None:
        self._set_collect_running(False)
        if ok:
            self._collect_status.setText(f"✅ {msg}")
            self._collect_progress.setValue(100)
            self._refresh_qlib_status()
            try:
                from core.event_bus import get_event_bus
                get_event_bus().status_message.emit("yfinance 数据采集完成，Qlib 数据已更新")
            except Exception:
                pass
        else:
            self._collect_status.setText(f"❌ {msg}")
        self._collect_worker = None

    def _on_collect_error(self, err: str) -> None:
        self._set_collect_running(False)
        self._append_collect_log(f"[ERROR] {err}")
        self._collect_worker = None

    def _set_collect_running(self, running: bool) -> None:
        self._instrument_combo.setEnabled(not running)
        self._col_collect_btn.setEnabled(not running)
        self._col_cancel_btn.setVisible(running)
        self._collect_progress.setVisible(running)
        if running:
            self._collect_progress.setValue(0)

    def _append_collect_log(self, text: str) -> None:
        self._collect_log.append(text)
        sb = self._collect_log.verticalScrollBar()
        sb.setValue(sb.maximum())
