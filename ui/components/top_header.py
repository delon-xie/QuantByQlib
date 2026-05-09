from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox
from PyQt6.QtCore import Qt, pyqtSignal
from core.qlibhelper import MARKETS
from .market_combo import MarketComboBox

class TopHeader(QWidget):
    """
    顶部通栏 Header
    - 左侧：应用名
    - 右侧：市场选择器
    """

    market_changed = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet("""
            TopHeader {
                background-color: #ffffff;
                border-bottom: 1px solid #e5e5e5;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # 左侧标题
        title = QLabel("QuantByQlib")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title)

        layout.addStretch()

        # 右侧市场选择器
        self.market_combo = MarketComboBox()
        self.market_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 2px 6px;
                background-color: white;
                font-size: 12px;
            }
        """)

        layout.addWidget(self.market_combo)