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
from typing import List

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
    
    def _get_tickers(self, current_scope: str) -> List[str]:
        """加载可用股票列表，返回股票代码列表"""
        from core.app_state import get_state
        reg = get_state().reg
        
        instruments_file = self.qlib_data_dir / "instruments" / f"{current_scope}.txt"
        if not instruments_file.exists():
            logger.info(f"file {instruments_file} not exist")
            return []
        
        available_tickers = []  # 使用局部变量
        from core.qlibhelper import _normalize_ticker
        
        try:
            lines = instruments_file.read_text().strip().split("\n")
            
            for line in lines:
                if not line.strip():
                    continue
                    
                parts = line.split("\t")
                if parts and len(parts) >= 1:
                    ticker = _normalize_ticker(parts[0].strip().upper(), reg)
                    if ticker:  # 确保标准化后的代码不为空
                        available_tickers.append(ticker)
                    else:
                        logger.info(f"{ticker} 不符合规则，已剔除")
            
            return available_tickers
            
        except Exception as e:
            logger.error(f"加载股票列表失败: {e}")
            return []