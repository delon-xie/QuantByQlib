# ui/common_indicators_tab.py
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QScrollArea, 
                             QGridLayout, QGroupBox, QLabel)
from PyQt6.QtCore import pyqtSignal
from typing import Dict, List

class CommonIndicatorsTab(QWidget):
    """常用指标Tab页"""
    
    indicator_clicked = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.indicators = {}
        self._setup_ui()
        
    def _setup_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        # 内容容器
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        
        # 分组布局
        self.group_widgets = {}
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
    def set_indicators(self, indicators: Dict[str, Dict]):
        """设置指标列表"""
        self.indicators = indicators
        
        # 清空现有内容
        for widget in self.group_widgets.values():
            widget.setParent(None)
        self.group_widgets.clear()
        
        # 按类别分组
        categories = {}
        for indicator_id, config in indicators.items():
            category = config.get("category", "其他")
            if category not in categories:
                categories[category] = []
            categories[category].append((indicator_id, config))
            
        # 创建分组
        for category, items in categories.items():
            group_box = self._create_category_group(category, items)
            self.content_layout.addWidget(group_box)
            self.group_widgets[category] = group_box
            
    def _create_category_group(self, category: str, items: List[tuple]):
        """创建分类组"""
        group = QGroupBox(category)
        layout = QGridLayout()
        
        # 创建指标按钮
        row, col = 0, 0
        max_cols = 3
        
        for indicator_id, config in items:
            btn = IndicatorButton(indicator_id, config["name"])
            btn.setToolTip(config.get("description", ""))
            btn.clicked_with_id.connect(self.indicator_clicked.emit)
            
            layout.addWidget(btn, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
                
        group.setLayout(layout)
        return group