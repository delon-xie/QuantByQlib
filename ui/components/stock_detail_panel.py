"""
可复用个股详情面板
复用于：
  ① 选股结果页右侧面板（带 Qlib 模型评分）
  ② 持仓管理页"查看"按钮触发（无模型评分）
  ③ 仪表盘搜索框结果
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy,
    QProgressBar, QStackedWidget, QTextEdit, QMainWindow
)
from PyQt6.QtCore import Qt, pyqtSignal, QThreadPool, QObject, pyqtSlot
from PyQt6.QtGui import QFont

from ui.theme import COLORS
from loguru import logger

class _SignalBadge(QLabel):
    """彩色信号徽章"""

    STYLES = {
        "bullish": f"background:{COLORS['success']}22; color:{COLORS['success']}; "
                   f"border:1px solid {COLORS['success']}; border-radius:4px; padding:2px 8px;",
        "bearish": f"background:{COLORS['danger']}22; color:{COLORS['danger']}; "
                   f"border:1px solid {COLORS['danger']}; border-radius:4px; padding:2px 8px;",
        "neutral": f"background:{COLORS['text_muted']}22; color:{COLORS['text_secondary']}; "
                   f"border:1px solid {COLORS['text_muted']}; border-radius:4px; padding:2px 8px;",
    }

    def __init__(self, text: str, signal_type: str = "neutral", parent=None):
        super().__init__(text, parent)
        style = self.STYLES.get(signal_type, self.STYLES["neutral"])
        self.setStyleSheet(style)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class _SectionTitle(QLabel):
    """区段标题"""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet(f"color:{COLORS['text_primary']}; margin-top:8px;")


class _MetricRow(QWidget):
    """单行指标：标签 + 值 + 信号徽章"""

    def __init__(self, label: str, value_str: str,
                 signal_text: str = "", signal_type: str = "neutral",
                 parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color:{COLORS['text_muted']}; font-size:12px;")
        lbl.setFixedWidth(130)
        row.addWidget(lbl)

        val = QLabel(value_str or "--")
        val.setStyleSheet(f"color:{COLORS['text_primary']}; font-size:12px; font-weight:bold;")
        val.setFixedWidth(100)
        row.addWidget(val)

        if signal_text:
            badge = _SignalBadge(signal_text, signal_type)
            badge.setStyleSheet(
                badge.styleSheet() + " font-size:11px;"
            )
            row.addWidget(badge)

        row.addStretch()


class StockDetailPanel(QWidget):
    """
    可嵌入任意页面的个股分析面板。
    信号：
      add_to_portfolio(ticker) — 记录买入按钮
      run_strategy(ticker)     — 加入回测按钮
    """

    add_to_portfolio = pyqtSignal(str)
    run_strategy     = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_ticker: Optional[str] = None
        self._last_report = None
        self._setup_ui()

    # ── 公开接口 ──────────────────────────────────────────────

    def load(self, ticker: str, quant_score: Optional[float] = None,
             qlib_signal: Optional[str] = None, qlib_rank: Optional[int] = None) -> None:
        """
        触发后台分析并加载个股数据
        quant_score: 来自选股模型的原始预测分数，None 表示非选股场景
        qlib_signal: Qlib 信号文字（买入/观察/持有），用于面板展示
        qlib_rank:   在选股结果中的排名
        """
        ticker = ticker.upper().strip()
        if not ticker:
            return
        self._current_ticker = ticker
        self._quant_score    = quant_score
        self._qlib_signal    = qlib_signal
        self._qlib_rank      = qlib_rank
        self._show_loading(ticker)
        self._start_worker(ticker)

    def clear(self) -> None:
        """清空面板显示空白占位"""
        self._current_ticker = None
        self._show_placeholder()

    # ── UI 初始化 ─────────────────────────────────────────────

    # 状态页索引常量
    _PAGE_PLACEHOLDER = 0
    _PAGE_LOADING     = 1
    _PAGE_CONTENT     = 2
    _PAGE_ERROR       = 3

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 用 QStackedWidget 管理四个互斥状态页，彻底避免叠加显示问题
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

        # 0: 占位页（未选中任何股票时显示）
        placeholder = QWidget()
        pl_layout = QVBoxLayout(placeholder)
        pl_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl_icon = QLabel("📊")
        pl_icon.setStyleSheet("font-size:48px;")
        pl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl_text = QLabel("点击左侧股票查看个股分析")
        pl_text.setStyleSheet(f"color:{COLORS['text_muted']}; font-size:14px;")
        pl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl_layout.addWidget(pl_icon)
        pl_layout.addWidget(pl_text)
        self._stack.addWidget(placeholder)   # index 0

        # 1: 加载页
        loading_widget = QWidget()
        ld_layout = QVBoxLayout(loading_widget)
        ld_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label = QLabel("正在分析 ...")
        self._loading_label.setStyleSheet(f"color:{COLORS['text_secondary']}; font-size:14px;")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 100)
        self._loading_bar.setValue(0)
        self._loading_bar.setMaximumWidth(300)
        self._loading_status = QLabel("")
        self._loading_status.setStyleSheet(f"color:{COLORS['text_muted']}; font-size:11px;")
        self._loading_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ld_layout.addWidget(self._loading_label)
        ld_layout.addWidget(self._loading_bar)
        ld_layout.addWidget(self._loading_status)
        self._stack.addWidget(loading_widget)  # index 1

        # 2: 内容区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setSpacing(6)
        self._content_layout.setContentsMargins(12, 8, 12, 20)
        scroll.setWidget(self._content_widget)
        self._scroll_area = scroll
        self._stack.addWidget(scroll)          # index 2

        # 3: 错误页
        error_widget = QWidget()
        err_layout = QVBoxLayout(error_widget)
        err_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label = QLabel("分析失败")
        self._error_label.setStyleSheet(f"color:{COLORS['danger']}; font-size:14px;")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        err_layout.addWidget(self._error_label)
        self._stack.addWidget(error_widget)    # index 3

        self._stack.setCurrentIndex(self._PAGE_PLACEHOLDER)

    def _show_placeholder(self) -> None:
        self._stack.setCurrentIndex(self._PAGE_PLACEHOLDER)

    def _show_loading(self, ticker: str) -> None:
        self._loading_label.setText(f"正在分析 {ticker} ...")
        self._loading_bar.setValue(10)
        self._loading_status.setText("初始化中...")
        self._stack.setCurrentIndex(self._PAGE_LOADING)

    def _show_content(self) -> None:
        self._stack.setCurrentIndex(self._PAGE_CONTENT)

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(f"❌ 分析失败：{msg}")
        self._stack.setCurrentIndex(self._PAGE_ERROR)

    # ── Worker 管理 ───────────────────────────────────────────

    def _start_worker(self, ticker: str) -> None:
        from workers.analysis_worker import AnalysisWorker
        worker = AnalysisWorker(ticker)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _on_progress(self, ticker: str, pct: int, status: str) -> None:
        if ticker != self._current_ticker:
            return
        self._loading_bar.setValue(pct)
        self._loading_status.setText(status)

    def _on_result(self, ticker: str, report) -> None:
        if ticker != self._current_ticker:
            return
        self._last_report = report   # 保存供 AI 报告按钮使用
        logger.info(
            f"[DetailPanel] {ticker} 收到结果："
            f"overall.score={report.overall.score if report.overall else 'N/A'}，"
            f"ohlcv_score={report.overall.ohlcv_score if report.overall else 'N/A'}，"
            f"tech_score.available={report.tech_score.available if report.tech_score else 'None'}，"
            f"tech_score.total={report.tech_score.total_score if report.tech_score else 'None'}"
        )
        self._render_report(report)
        self._show_content()

    def _on_error(self, ticker: str, msg: str) -> None:
        if ticker != self._current_ticker:
            return
        self._show_error(msg)

    # ── 渲染报告 ──────────────────────────────────────────────

    def _render_report(self, report) -> None:
        """清空旧内容，重新渲染报告所有区块"""
        # 同步清空旧内容（setParent(None) 立即从布局中分离，避免 deleteLater 的异步叠加）
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        # ── 价格头部 ──
        self._render_price_header(report)
        self._add_separator()

        # ── 综合评分 ──
        if report.overall.available:
            self._render_overall_score(report.overall)
            self._add_separator()

        # ── Qlib 模型评分（若来自选股页面）──
        quant_score = getattr(self, "_quant_score", None)
        if quant_score is not None:
            self._render_quant_score(quant_score)
            self._add_separator()

        # ── 六维技术评分（TechnicalScorer）──
        if report.tech_score and report.tech_score.available:
            self._render_tech_score(report.tech_score)
            self._add_separator()

        # ── Alpha158 技术信号 ──
        if report.technical:
            self._render_technical(report.technical)
            self._add_separator()

        # ── 基本面 ──
        if report.fundamental:
            self._render_fundamental(report.fundamental)
            self._add_separator()

        # ── 情绪 ──
        if report.sentiment and report.sentiment.available:
            self._render_sentiment(report.sentiment)
            self._add_separator()

        # ── 操作按钮 ──
        self._render_actions(report.ticker)

        self._content_layout.addStretch()

    def _render_price_header(self, report) -> None:
        """价格 + 涨跌幅标题区"""
        name = report.company_name
        price  = report.current_price
        change = report.change_pct

        title_row = QHBoxLayout()

        name_label = QLabel(f"{name}")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        name_label.setFont(font)
        name_label.setStyleSheet(f"color:{COLORS['text_primary']};")
        name_label.setWordWrap(True)
        title_row.addWidget(name_label, 1)

        ticker_badge = QLabel(report.ticker)
        ticker_badge.setStyleSheet(
            f"background:{COLORS['primary']}33; color:{COLORS['primary']}; "
            f"border:1px solid {COLORS['primary']}; border-radius:4px; "
            f"padding:2px 8px; font-size:11px; font-weight:bold;"
        )
        title_row.addWidget(ticker_badge)

        self._content_layout.addLayout(title_row)

        # 价格行
        if price:
            price_row = QHBoxLayout()
            price_label = QLabel(f"${price:,.2f}")
            font2 = QFont()
            font2.setPointSize(20)
            font2.setBold(True)
            price_label.setFont(font2)
            price_label.setStyleSheet(f"color:{COLORS['text_primary']};")
            price_row.addWidget(price_label)

            if change is not None:
                pct = change * 100
                color = COLORS["success"] if pct >= 0 else COLORS["danger"]
                sign  = "▲" if pct >= 0 else "▼"
                chg_label = QLabel(f"{sign}{abs(pct):.2f}%")
                chg_label.setStyleSheet(f"color:{color}; font-size:16px; font-weight:bold;")
                price_row.addWidget(chg_label)

            price_row.addStretch()
            self._content_layout.addLayout(price_row)
        else:
            no_price = QLabel("暂无实时价格数据")
            no_price.setStyleSheet(f"color:{COLORS['text_muted']}; font-size:12px;")
            self._content_layout.addWidget(no_price)

    def _render_overall_score(self, overall) -> None:
        self._content_layout.addWidget(_SectionTitle("综合分析评分（独立于Qlib）"))

        row = QHBoxLayout()

        score_label = QLabel(f"{overall.score:.0f}")
        font = QFont()
        font.setPointSize(36)
        font.setBold(True)
        score_label.setFont(font)
        color = (COLORS["success"] if overall.grade_type == "bullish"
                 else COLORS["danger"] if overall.grade_type == "bearish"
                 else COLORS["warning"])
        score_label.setStyleSheet(f"color:{color};")
        row.addWidget(score_label)

        sub_col = QVBoxLayout()
        sub_col.setSpacing(4)

        grade_badge = _SignalBadge(
            f"  {overall.grade}  ",
            overall.grade_type or "neutral"
        )
        font2 = QFont()
        font2.setPointSize(12)
        font2.setBold(True)
        grade_badge.setFont(font2)
        sub_col.addWidget(grade_badge)

        # 分维度进度
        for label, score in [
            ("Alpha158", overall.tech_score),
            ("六维技术", (overall.ohlcv_score / 100.0) if overall.ohlcv_score is not None else None),
            ("基本面",   overall.fund_score),
            ("情绪面",   overall.senti_score),
        ]:
            if score is None:
                continue
            bar_row = QHBoxLayout()
            bar_lbl = QLabel(label)
            bar_lbl.setStyleSheet(f"color:{COLORS['text_muted']}; font-size:11px;")
            bar_lbl.setFixedWidth(42)
            bar_row.addWidget(bar_lbl)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(score * 100))
            bar.setMaximumHeight(8)
            bar.setTextVisible(False)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background:{COLORS['bg_card']};
                    border-radius:4px;
                    border:none;
                }}
                QProgressBar::chunk {{
                    background:{color};
                    border-radius:4px;
                }}
            """)
            bar_row.addWidget(bar, 1)

            pct_lbl = QLabel(f"{score*100:.0f}")
            pct_lbl.setStyleSheet(f"color:{COLORS['text_muted']}; font-size:11px;")
            pct_lbl.setFixedWidth(28)
            bar_row.addWidget(pct_lbl)

            sub_col.addLayout(bar_row)

        row.addLayout(sub_col, 1)
        self._content_layout.addLayout(row)

    def _render_quant_score(self, score: float) -> None:
        self._content_layout.addWidget(_SectionTitle("Qlib 量化选股信号"))

        # 用选股信号判断强弱（信号由 stock_screener 按相对排名计算，与综合评分无关）
        qlib_signal = getattr(self, "_qlib_signal", None)
        qlib_rank   = getattr(self, "_qlib_rank",   None)

        if qlib_signal in ("买入",):
            grade, grade_type = "量化买入", "bullish"
        elif qlib_signal in ("卖出",):
            grade, grade_type = "量化卖出", "bearish"
        else:
            grade, grade_type = "量化观察", "neutral"

        rank_str = f"第 {qlib_rank} 名" if qlib_rank else "--"
        self._content_layout.addWidget(_MetricRow(
            "选股排名", rank_str, grade, grade_type,
        ))
        self._content_layout.addWidget(_MetricRow(
            "模型原始分数", f"{score:.4f}", "LightGBM 相对收益预测", "neutral",
        ))

        # 说明文字
        note = QLabel("⚠ 此信号为 Qlib 量化模型输出，与上方综合分析评分相互独立")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{COLORS['text_muted']}; font-size:10px; padding:4px 0;")
        self._content_layout.addWidget(note)

    def _render_technical(self, tech) -> None:
        self._content_layout.addWidget(_SectionTitle("Alpha158 技术信号"))

        from stock_analysis.alpha_reader import Alpha158Reader
        reader = Alpha158Reader()

        # 调用 get_factor_signals 生成信号列表（若 tech 有 factor_values 属性）
        factor_values = getattr(tech, "factor_values", {})
        if factor_values:
            signals = reader.get_factor_signals(factor_values)
            for sig in signals[:8]:  # 最多显示 8 条
                row = _MetricRow(
                    sig["label"],
                    sig["value_str"],
                    sig["signal_text"],
                    sig["signal_type"],
                )
                self._content_layout.addWidget(row)
        else:
            # 仅显示综合信号
            signal_text = getattr(tech, "signal", "未知")
            stype_map = {"bullish": "bullish", "bearish": "bearish"}
            stype = stype_map.get(signal_text, "neutral")
            row = _MetricRow("综合技术信号", signal_text, signal_text, stype)
            self._content_layout.addWidget(row)

        # 量化综合分
        composite = getattr(tech, "composite_score", None)
        if composite is not None:
            row = _MetricRow(
                "量化综合分",
                f"{composite:.3f}",
                "强势" if composite > 0.65 else ("弱势" if composite < 0.35 else "中性"),
                "bullish" if composite > 0.65 else ("bearish" if composite < 0.35 else "neutral"),
            )
            self._content_layout.addWidget(row)

    # ── 六维技术评分各维度解读 ────────────────────────────────

    @staticmethod
    def _dim_interpretation(dim_key: str, score_val: float, ts) -> str:
        """根据分数和原始指标值生成通俗解读"""
        if dim_key == "ma_trend":
            if score_val >= 80:
                return "价格强势站上所有均线，趋势明确向上"
            elif score_val >= 65:
                return "价格站上多条均线，中期趋势偏多"
            elif score_val >= 50:
                return "均线多空交织，方向尚不明朗"
            elif score_val >= 35:
                return "价格跌破部分均线，趋势偏弱"
            else:
                return "价格跌破多条均线，趋势向下"

        elif dim_key == "deviation":
            pct = getattr(ts, "deviation_pct", None)
            pct_str = f"（偏离 MA20 {pct:+.1f}%）" if pct is not None else ""
            if getattr(ts, "chase_warning", False):
                return f"⚠ 偏离过大{pct_str}，高位追涨风险较高"
            elif score_val >= 65:
                return f"价格与均线距离适中{pct_str}，无明显追涨风险"
            else:
                return f"价格大幅偏离均线下方{pct_str}，超卖区域"

        elif dim_key == "volume":
            if score_val >= 75:
                return "放量上涨，主力资金积极介入"
            elif score_val >= 55:
                return "量能温和配合，整体健康"
            elif score_val >= 40:
                return "量能一般，资金观望情绪较重"
            else:
                return "缩量或量价背离，信号偏弱"

        elif dim_key == "macd":
            cross = getattr(ts, "macd_cross", None)
            if cross == "金叉":
                return "MACD 金叉，短期动能由弱转强，看涨信号"
            elif cross == "死叉":
                return "MACD 死叉，短期动能走弱，注意风险"
            else:
                return "MACD 无明确金叉/死叉，动能方向待定"

        elif dim_key == "rsi":
            rsi = getattr(ts, "rsi6", None)
            rsi_str = f"RSI(6)={rsi:.0f}" if rsi is not None else "RSI"
            if rsi is not None and rsi > 80:
                return f"{rsi_str}，严重超买，回调风险较大"
            elif rsi is not None and rsi > 70:
                return f"{rsi_str}，进入超买区，注意短期回调"
            elif rsi is not None and rsi < 20:
                return f"{rsi_str}，严重超卖，存在反弹机会"
            elif rsi is not None and rsi < 30:
                return f"{rsi_str}，进入超卖区，存在反弹机会"
            else:
                return f"{rsi_str}，处于正常区间（30-70），动能中性"

        elif dim_key == "bband":
            bp = getattr(ts, "bband_pct", None)
            bp_str = f"%B={bp:.2f}" if bp is not None else ""
            if bp is not None and bp > 0.85:
                return f"价格接近布林上轨{f'（{bp_str}）' if bp_str else ''}，短期超买"
            elif bp is not None and bp < 0.15:
                return f"价格接近布林下轨{f'（{bp_str}）' if bp_str else ''}，超卖支撑"
            else:
                return f"价格在布林带中轨附近{f'（{bp_str}）' if bp_str else ''}，波动正常"

        return ""

    def _render_tech_score(self, ts) -> None:
        """六维技术评分展示（TechnicalScore）"""
        signal_type = ts.signal_type or "neutral"

        title_row = QHBoxLayout()
        title_row.addWidget(_SectionTitle("六维技术评分"))
        score_badge = _SignalBadge(f"{ts.total_score:.0f}分  {ts.signal or ''}", signal_type)
        title_row.addWidget(score_badge)
        title_row.addStretch()
        self._content_layout.addLayout(title_row)

        # 追涨警告
        if ts.chase_warning and ts.deviation_pct is not None:
            warn = QLabel(f"⚠️ 追涨风险：价格偏离 MA20 达 {ts.deviation_pct:+.1f}%（超过 5% 阈值）")
            warn.setStyleSheet(f"color:{COLORS['warning']}; font-size:11px; padding:2px 0;")
            warn.setWordWrap(True)
            self._content_layout.addWidget(warn)

        # 各维度进度条 + 解读
        dim_key_map = {
            "MA 趋势":  "ma_trend",
            "背离率":   "deviation",
            "量能模式": "volume",
            "MACD":     "macd",
            "RSI 动量": "rsi",
            "布林带":   "bband",
        }
        dims = ts.to_dimension_list() if hasattr(ts, "to_dimension_list") else []
        for dim in dims:
            score_val = dim["score"]
            if score_val is None:
                continue

            # 进度条行
            bar_row = QHBoxLayout()
            name_lbl = QLabel(f"{dim['name']}（{dim['weight']}）")
            name_lbl.setStyleSheet(f"color:{COLORS['text_secondary']}; font-size:11px; font-weight:bold;")
            name_lbl.setFixedWidth(110)
            bar_row.addWidget(name_lbl)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(score_val))
            bar.setMaximumHeight(8)
            bar.setTextVisible(False)
            bar_color = (COLORS["success"] if score_val >= 65
                         else COLORS["danger"] if score_val < 40
                         else COLORS["warning"])
            bar.setStyleSheet(f"""
                QProgressBar {{background:{COLORS['bg_card']};border-radius:4px;border:none;}}
                QProgressBar::chunk {{background:{bar_color};border-radius:4px;}}
            """)
            bar_row.addWidget(bar, 1)

            num_lbl = QLabel(f"{score_val:.0f}")
            num_lbl.setStyleSheet(
                f"color:{bar_color}; font-size:11px; font-weight:bold;"
            )
            num_lbl.setFixedWidth(28)
            bar_row.addWidget(num_lbl)
            self._content_layout.addLayout(bar_row)

            # 解读文字
            dim_key = dim_key_map.get(dim["name"], "")
            interp = self._dim_interpretation(dim_key, score_val, ts) if dim_key else ""
            if interp:
                interp_lbl = QLabel(interp)
                interp_lbl.setStyleSheet(
                    f"color:{COLORS['text_muted']}; font-size:10px; "
                    f"padding-left:114px; padding-bottom:4px;"
                )
                interp_lbl.setWordWrap(True)
                self._content_layout.addWidget(interp_lbl)

        # 关键数值行
        key_vals: list[tuple] = []
        if ts.ma5 and ts.current_price:
            key_vals.append(("MA5", f"${ts.ma5:.2f}",
                             "上方" if ts.current_price > ts.ma5 else "下方",
                             "bullish" if ts.current_price > ts.ma5 else "bearish"))
        if ts.ma20 and ts.deviation_pct is not None:
            key_vals.append(("MA20 背离率", f"{ts.deviation_pct:+.1f}%",
                             "追涨警告" if ts.chase_warning else "正常",
                             "bearish" if ts.chase_warning else "neutral"))
        if ts.macd_cross:
            key_vals.append(("MACD", ts.macd_cross,
                             ts.macd_cross,
                             "bullish" if ts.macd_cross == "金叉" else
                             "bearish" if ts.macd_cross == "死叉" else "neutral"))
        if ts.rsi6 is not None:
            rsi_sig = "超买" if ts.rsi6 > 70 else "超卖" if ts.rsi6 < 30 else "中性"
            rsi_type = "bearish" if ts.rsi6 > 70 else "bullish" if ts.rsi6 < 30 else "neutral"
            key_vals.append(("RSI(6)", f"{ts.rsi6:.1f}", rsi_sig, rsi_type))
        if ts.bband_pct is not None:
            bp = ts.bband_pct
            bb_sig = "触上轨" if bp > 0.9 else "触下轨" if bp < 0.1 else f"%B={bp:.2f}"
            bb_type = "bearish" if bp > 0.9 else "bullish" if bp < 0.1 else "neutral"
            key_vals.append(("布林带", bb_sig, bb_sig, bb_type))

        for label, val, sig_text, sig_type in key_vals:
            self._content_layout.addWidget(_MetricRow(label, val, sig_text, sig_type))

    def _render_fundamental(self, fund) -> None:
        self._content_layout.addWidget(_SectionTitle("基本面指标（FMP）"))

        from stock_analysis.fundamental import FundamentalAnalyzer
        analyzer = FundamentalAnalyzer()
        signals = analyzer.get_valuation_signals(fund)

        for sig in signals:
            row = _MetricRow(
                sig["label"],
                sig["value_str"],
                sig["signal_text"],
                sig["signal_type"],
            )
            self._content_layout.addWidget(row)

        # 公司概况信息
        if fund.market_cap:
            mc = fund.market_cap
            if mc >= 1e12:
                mc_str = f"${mc/1e12:.2f}T"
            elif mc >= 1e9:
                mc_str = f"${mc/1e9:.2f}B"
            else:
                mc_str = f"${mc/1e6:.0f}M"
            self._content_layout.addWidget(
                _MetricRow("市值", mc_str)
            )

        if fund.analyst_rating and fund.analyst_target:
            stype = "bullish" if "买" in fund.analyst_rating else "neutral"
            self._content_layout.addWidget(
                _MetricRow(
                    "分析师评级",
                    f"目标价 ${fund.analyst_target:.2f}",
                    fund.analyst_rating,
                    stype,
                )
            )

    def _render_sentiment(self, senti) -> None:
        self._content_layout.addWidget(
            _SectionTitle(f"新闻情绪（{senti.model_used or 'VADER'}）")
        )

        if senti.avg_score is not None:
            row = _MetricRow(
                "情绪均值",
                f"{senti.avg_score:+.3f}",
                senti.signal or "中性",
                senti.signal_type or "neutral",
            )
            self._content_layout.addWidget(row)

        stat_row = _MetricRow(
            "正/负/中性",
            f"{senti.positive_count} / {senti.negative_count} / {senti.neutral_count}",
            f"共 {senti.news_count} 条新闻",
            "neutral",
        )
        self._content_layout.addWidget(stat_row)

        # 最新几条新闻标题
        if senti.headlines:
            news_title = QLabel("最新新闻：")
            news_title.setStyleSheet(f"color:{COLORS['text_secondary']}; font-size:11px; margin-top:4px;")
            self._content_layout.addWidget(news_title)

            for i, headline in enumerate(senti.headlines[:5]):
                score = senti.scores[i] if i < len(senti.scores) else 0.0
                color = (COLORS["success"] if score > 0.05
                         else COLORS["danger"] if score < -0.05
                         else COLORS["text_muted"])
                h_label = QLabel(f"• {headline}")
                h_label.setStyleSheet(
                    f"color:{color}; font-size:11px; margin-left:8px;"
                )
                h_label.setWordWrap(True)
                self._content_layout.addWidget(h_label)

    def _render_actions(self, ticker: str) -> None:
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        buy_btn = QPushButton("💼 记录买入")
        buy_btn.setObjectName("btn_primary")
        buy_btn.setMinimumHeight(36)
        buy_btn.clicked.connect(lambda: self.add_to_portfolio.emit(ticker))
        btn_row.addWidget(buy_btn)

        bt_btn = QPushButton("📊 加入回测")
        bt_btn.setObjectName("btn_secondary")
        bt_btn.setMinimumHeight(36)
        bt_btn.clicked.connect(lambda: self.run_strategy.emit(ticker))
        btn_row.addWidget(bt_btn)

        ai_btn = QPushButton("🤖 AI 分析报告")
        ai_btn.setObjectName("btn_secondary")
        ai_btn.setMinimumHeight(36)
        ai_btn.clicked.connect(lambda: self._request_ai_report(ticker))
        ai_btn.setProperty("actionKey", "cached")
        self._ai_btn = ai_btn
        btn_row.addWidget(ai_btn)

        self._content_layout.addLayout(btn_row)

        # AI 报告展示区（初始隐藏，点击按钮后展开）
        self._ai_report_label = _SectionTitle("AI 分析报告")
        self._ai_report_label.hide()
        self._content_layout.addWidget(self._ai_report_label)

        self._ai_report_text = QTextEdit()
        self._ai_report_text.setReadOnly(True)
        self._ai_report_text.setMinimumHeight(300)
        self._ai_report_text.setStyleSheet(f"""
            QTextEdit {{
                background:{COLORS.get('bg_card', '#1e1e2e')};
                color:{COLORS.get('text_primary', '#cdd6f4')};
                border:1px solid {COLORS.get('border', '#313244')};
                border-radius:6px;
                padding:10px;
                font-size:12px;
                font-family: 'Courier New', monospace;
            }}
        """)
        self._ai_report_text.hide()
        self._content_layout.addWidget(self._ai_report_text)
        
        from ui.components.md_preview_only import MDPreviewOnly
        self._ai_report_viewer = MDPreviewOnly()
        self._ai_report_viewer.hide()
        self._content_layout.addWidget(self._ai_report_viewer)

    def _request_ai_report(self, ticker: str) -> None:
        """启动后台 worker 生成 AI 分析报告（流式）"""
        if not hasattr(self, "_last_report") or self._last_report is None:
            return

        from services.report_writer import ReportWriter
        from ui.components.md_preview_only import MDPreviewOnly
        
        writer = ReportWriter()
        report_content = writer.get_report(ticker)
        
        if self._ai_btn.property("actionKey") == "cached" and report_content != None and len(report_content) > 0:
            #显示缓存
            self._ai_btn.setProperty("actionKey", "nocache")
            self._ai_btn.setText("🤖 重新生成 AI 分析报告")
            self._ai_report_label.hide()
            
            if self._ai_report_text != None and self._ai_report_text.isHidden() == False:
                self._ai_report_text.hide()
            self._render_airesult(report_content)
        else:
            self._ai_btn.setProperty("actionKey", "cached")
            self._ai_btn.setText("🤖 AI 分析报告")
            self._ai_report_label.show()
            self._ai_report_text.show()
            self._ai_report_text.setPlainText("正在生成 AI 分析报告，请稍候...")

            from workers.llm_report_worker import LLMReportWorker
            worker = LLMReportWorker(self._last_report)
            worker.signals.chunk.connect(self._on_ai_chunk)
            worker.signals.finished.connect(self._on_ai_finished)
            worker.signals.error.connect(self._on_ai_error)
            QThreadPool.globalInstance().start(worker)

    def _on_ai_chunk(self, ticker: str, chunk: str) -> None:
        """流式接收文本块"""
        if self._ai_report_viewer != None and self._ai_report_viewer.isHidden() == False:
            self._ai_report_viewer.hide()
        
        if ticker != self._current_ticker:
            return
        current = self._ai_report_text.toPlainText()
        if current == "正在生成 AI 分析报告，请稍候...":
            self._ai_report_text.setPlainText(chunk)
        else:
            self._ai_report_text.setPlainText(current + chunk)
        # 滚动到底部
        sb = self._ai_report_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_ai_finished(self, ticker: str, full_text: str) -> None:
        """报告生成完成"""
        if ticker != self._current_ticker:
            return
        logger.debug(f"AI 报告生成完成：{ticker}，{len(full_text)} 字符")
        
        # 切换到浏览器
        self._render_airesult(full_text)

    def _on_ai_error(self, ticker: str, msg: str) -> None:
        if ticker != self._current_ticker:
            return
        self._ai_report_text.setPlainText(f"AI 报告生成失败：{msg}")

    # ── 工具方法 ──────────────────────────────────────────────

    def _clear_layout(self, layout) -> None:
        """递归清空嵌套布局中的所有 widget"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _add_separator(self) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{COLORS['border']}; margin:4px 0;")
        self._content_layout.addWidget(sep)
    
    def get_mainwindow(self) -> QMainWindow | None:
        """获取控件所在的 MainWindow"""
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QMainWindow):
                return parent
            parent = parent.parent()
        return None
    def _render_airesult(self, full_content: str) -> None:
        # AI 报告展示区（初始隐藏，点击按钮后展开）
        from ui.components.md_preview_only import MDPreviewOnly
        
        if self._ai_report_text != None and self._ai_report_text.isHidden() == False:
            self._ai_report_text.hide()
        
        self._ai_report_viewer.set_markdown(full_content)
        self._ai_report_viewer.show()
