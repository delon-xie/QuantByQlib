"""
K 线图弹窗
显示单支股票的 5日 / 日线 / 周线 K 线图（mplfinance 渲染，内嵌 matplotlib canvas）
"""
from __future__ import annotations

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QPushButton, QLabel, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThreadPool, QRunnable, QObject, pyqtSignal


class _FetchSignals(QObject):
    done  = pyqtSignal(object, str)   # (df, period_key)
    error = pyqtSignal(str, str)       # (msg, period_key)


class _FetchWorker(QRunnable):
    """后台拉取 yfinance 数据"""

    # yfinance fallback 参数
    # zoom：拉120根日K计算准确均线，展示最后20根
    # day：90根日线（约4.5个月）
    # week：60根周线（约15个月）
    _YF_PARAMS = {
        "zoom": dict(period="180d", interval="1d"),
        "day":  dict(period="130d", interval="1d"),   # 130交易日≈6个月，保证90根
        "week": dict(period="80wk", interval="1wk"),  # 80周保证60根
    }

    def __init__(self, ticker: str, period_key: str, signals: _FetchSignals):
        super().__init__()
        self.ticker     = ticker
        self.period_key = period_key
        self.signals    = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            df = self._fetch_longport()
            if df is None or df.empty:
                df = self._fetch_yfinance()
            if df is None or df.empty:
                self.signals.error.emit("无数据", self.period_key)
                return
            self.signals.done.emit(df, self.period_key)
        except Exception as e:
            self.signals.error.emit(str(e), self.period_key)

    def _fetch_longport(self):
        """优先用长桥实时数据（需配置 Key）"""
        try:
            from data.longport_client import get_candlesticks, is_configured
            if not is_configured():
                return None
            return get_candlesticks(self.ticker, self.period_key)
        except Exception:
            return None

    def _fetch_yfinance(self):
        """Fallback：yfinance 公共数据"""
        import yfinance as yf
        params = self._YF_PARAMS[self.period_key]
        
        from core.app_state import get_state
        from workers.binance_downloader import binance_download
        reg = get_state().reg
        if reg == "bt":
            df = binance_download(
                self.ticker, 
                progress=False, 
                auto_adjust=True, 
                threads=True, 
                **params
            )
        else:
            import yfinance as yf
            # yfinance 一次下载所有 ticker，速度远快于逐一下载
            # tickers_str = " ".join(tickers)
            df = yf.download(
                self.ticker, 
                progress=False, 
                auto_adjust=True, 
                threads=True, 
                **params
            )

        if df is not None and not df.empty:
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(0)
            df.index.name = "Date"
            # zoom：保留完整数据，供 _on_data 用全量数据计算均线，xlim 控制显示范围
            # day：展示最近90根
            if self.period_key == "day":
                df = df.tail(90)
            # week：展示最近60根
            elif self.period_key == "week":
                df = df.tail(60)
        return df


class _ChartCanvas(QWidget):
    """单个周期的 K 线图 tab 内容"""

    def __init__(self, ticker: str, period_key: str, parent=None):
        super().__init__(parent)
        self.ticker     = ticker
        self.period_key = period_key
        self._loaded    = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._status = QLabel("⏳ 加载中...")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: #9299B0; font-size: 13px; padding: 40px;")
        layout.addWidget(self._status)

        self._figure_widget: QWidget | None = None
        self._layout = layout

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        signals = _FetchSignals()
        signals.done.connect(self._on_data)
        signals.error.connect(self._on_error)
        worker = _FetchWorker(self.ticker, self.period_key, signals)
        # signals 需保活
        self._signals = signals
        QThreadPool.globalInstance().start(worker)

    # 各周期均线配置
    _MAV = {
        "zoom": (5, 10, 20),        # 放大图：MA5/MA10/MA20（MA30数据点不足，不显示）
        "day":  (5, 10, 20, 30),    # 日线：MA5/MA10/MA20/MA30
        "week": (5, 10, 20, 30),    # 周线：MA5/MA10/MA20/MA30
    }

    def _on_data(self, df, period_key: str) -> None:
        try:
            import mplfinance as mpf
            import matplotlib
            matplotlib.use("QtAgg")
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm

            # 找到可用中文字体的 FontProperties 对象
            _cn_font = None
            for _fname in ["PingFang HK", "PingFang SC", "STHeiti", "Heiti TC", "Arial Unicode MS"]:
                try:
                    _fp = fm.FontProperties(family=_fname)
                    if fm.findfont(_fp, fallback_to_default=False):
                        _cn_font = _fp
                        plt.rcParams["font.family"] = _fname
                        break
                except Exception:
                    continue
            plt.rcParams["axes.unicode_minus"] = False

            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

            _TITLES = {
                "zoom": "Zoom (20d)",
                "day":  "Daily (90d)",
                "week": "Weekly (60wk)",
            }
            try:
                from data.longport_client import is_configured
                src = "LongPort" if is_configured() else "yfinance"
            except Exception:
                src = "yfinance"
            title = f"{self.ticker}  {_TITLES.get(period_key, period_key)}  [{src}]"

            mav = self._MAV.get(period_key, (5, 20))

            style = mpf.make_mpf_style(
                base_mpf_style="charles",
                marketcolors=mpf.make_marketcolors(
                    up="#22C55E", down="#EF4444",
                    edge="inherit", wick="inherit",
                    volume={"up": "#22C55E88", "down": "#EF444488"},
                ),
                figcolor="#FFFFFF",
                gridcolor="#E2E4EA",
                gridstyle="--",
                mavcolors=["#F59E0B", "#3B82F6", "#8B5CF6", "#EC4899"],  # MA5橙/MA10蓝/MA20紫/MA30粉
            )

            fig, axes = mpf.plot(
                df,
                type="candle",
                style=style,
                title=title,
                volume=True,
                mav=mav,
                returnfig=True,
                figsize=(12, 7),
                tight_layout=True,
            )

            # zoom：MA 基于完整数据计算，xlim 限制显示最后20根（确保 MA20 正确显示）
            if period_key == "zoom":
                n = len(df)
                display = 20
                for ax in axes:
                    ax.set_xlim(n - display - 0.5, n - 0.5)

            # 对所有 axes 的 tick label 强制应用中文字体（修复 X 轴月份乱码）
            if _cn_font:
                for ax in fig.get_axes():
                    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
                        lbl.set_fontproperties(_cn_font)

            canvas = FigureCanvas(fig)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            self._status.hide()
            self._layout.addWidget(canvas)
            self._figure_widget = canvas
            plt.close(fig)

        except Exception as e:
            self._on_error(str(e), period_key)

    def _on_error(self, msg: str, period_key: str) -> None:
        self._status.setText(f"❌ 加载失败：{msg}")


class ChartDialog(QDialog):
    """
    K 线图弹窗
    三个 tab：5日图 / 日线 / 周线
    """

    def __init__(self, ticker: str, parent=None):
        super().__init__(parent)
        self.ticker = ticker
        self.setWindowTitle(f"📈 {ticker} — K 线图")
        self.resize(900, 580)
        self.setModal(False)   # 非模态，允许继续操作主窗口
        self._setup_ui()
        # 默认加载日线 tab
        self._canvases["day"].load()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # tab 切换
        self._tabs = QTabWidget()
        self._canvases: dict[str, _ChartCanvas] = {}

        for key, label in [("zoom", "🔍 放大图"), ("day", "📈 日线"), ("week", "📊 周线")]:
            canvas = _ChartCanvas(self.ticker, key)
            self._canvases[key] = canvas
            self._tabs.addTab(canvas, label)

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.setCurrentIndex(1)   # 默认显示日线 tab
        layout.addWidget(self._tabs)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("btn_secondary")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_tab_changed(self, index: int) -> None:
        key = list(self._canvases.keys())[index]
        self._canvases[key].load()
