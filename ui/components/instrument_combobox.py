from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QGroupBox, QGridLayout,
    QProgressBar, QTextEdit, QScrollArea, QFrame,
    QSizePolicy, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QFileDialog
)
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QColor
import os
from pathlib import Path
from loguru import logger
from core.qlibhelper import _find_data_dir

class InstrumentComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.qlib_data_dir = _find_data_dir()

    def showPopup(self):
        # 在下拉前动态加载
        self._load_instrument_list()
        super().showPopup()

    def _load_instrument_list(self):
        current = self.currentText()
        self.clear()

        self.qlib_data_dir = _find_data_dir()
        instruments_dir = self.qlib_data_dir / "instruments"
        if not instruments_dir.exists():
            self.addItem("all")
            return

        for file in instruments_dir.glob("*.txt"):
            self.addItem(file.stem)

        # 尽量恢复之前的选择
        index = self.findText(current)
        if index >= 0:
            self.setCurrentIndex(index)