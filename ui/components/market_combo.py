from PyQt6.QtWidgets import QComboBox
from PyQt6.QtCore import Qt, pyqtSignal
from core.qlibhelper import MARKETS

class MarketComboBox(QComboBox):
    """
    市场选择器（A股 / 美股 / 港股 / 台股 / 日股 / 韩股 / Crypto）
    """

    reg_changed = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        for code, name in MARKETS:
            self.addItem(name, userData=code)

        self.currentIndexChanged.connect(self._on_index_changed)

    def _on_index_changed(self, index: int):
        code, name = MARKETS[index]
        self.reg_changed.emit(code, name)

    def set_market(self, code: str):
        for i, (c, _) in enumerate(MARKETS):
            if c == code:
                self.setCurrentIndex(i)
                break