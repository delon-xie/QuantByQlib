# ui/advanced_indicators_tab.py
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QScrollArea,
                             QGridLayout, QGroupBox, QTreeWidget,
                             QTreeWidgetItem, QHeaderView)
from PyQt6.QtCore import pyqtSignal, Qt
import json
from typing import Optional, List, Dict, Any, Tuple

class AdvancedIndicatorsTab(QWidget):
    """高级指标Tab页 - 树形结构展示"""
    
    indicator_selected = pyqtSignal(str, dict)  # 指标选中，包含参数模板
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.indicators = {}
        self._setup_ui()
        
    def _setup_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 树形控件
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["指标名称", "类型", "描述"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        layout.addWidget(self.tree)
        
    def set_indicators(self, indicators: Dict[str, Dict]):
        """设置指标树"""
        self.indicators = indicators
        self.tree.clear()
        
        # 按分类构建树结构
        categories = {}
        for indicator_id, config in indicators.items():
            category = config.get("category", "未分类")
            if category not in categories:
                categories[category] = []
            categories[category].append((indicator_id, config))
            
        # 创建树节点
        for category, items in categories.items():
            category_item = QTreeWidgetItem(self.tree, [category])
            category_item.setExpanded(True)
            
            for indicator_id, config in items:
                indicator_item = QTreeWidgetItem(category_item, [
                    config["name"],
                    config.get("type", "line"),
                    config.get("description", "")[:50] + "..."
                ])
                indicator_item.setData(0, Qt.ItemDataRole.UserRole, indicator_id)
                indicator_item.setData(0, Qt.ItemDataRole.UserRole + 1, config)
                
    def _on_item_double_clicked(self, item, column):
        """处理指标双击"""
        indicator_id = item.data(0, Qt.ItemDataRole.UserRole)
        config = item.data(0, Qt.ItemDataRole.UserRole + 1)
        
        if indicator_id and config:
            self.indicator_selected.emit(indicator_id, config)