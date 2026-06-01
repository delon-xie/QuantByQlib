# core/chart_widget.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QTimer, Qt
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import pandas as pd

class TradingViewChartWidget(QWidget):
    """主图表组件 - 管理整体生命周期"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_managers()
        self._init_ui()
        
    def _setup_managers(self):
        """初始化各个管理器"""
        from .data_manager import DataManager
        from .indicator_manager import IndicatorManager
        from .bridge_manager import BridgeManager
        
        self.data_manager = DataManager()
        self.indicator_manager = IndicatorManager(self)
        self.bridge_manager = BridgeManager(self)
        
    def _init_ui(self):
        """初始化用户界面"""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建浏览器视图
        self.browser = QWebEngineView(self)
        self.layout.addWidget(self.browser)
        
        # 启用开发者工具
        self._enable_developer_tools()
        
        # 加载HTML模板
        html_path = Path(__file__).parent.parent / 'web' / 'html' / 'chart_template.html'
        self.browser.setUrl(QUrl.fromLocalFile(str(html_path)))
        
        # 检查图表就绪
        QTimer.singleShot(500, self._check_chart_ready)
        
    def _enable_developer_tools(self):
        """启用开发者工具"""
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        settings = self.browser.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        
    def update_data(self, df: pd.DataFrame) -> None:
        """更新图表数据"""
        self.data_manager.set_data(df)
        data_json = self.data_manager.get_chart_data_json()
        self.bridge_manager.send_data_to_js(data_json)
        
    def add_indicator(self, indicator_name: str, **options) -> None:
        """添加技术指标"""
        self.indicator_manager.add_indicator(indicator_name, options)
        
    def remove_indicator(self, indicator_name: str) -> None:
        """移除技术指标"""
        self.indicator_manager.remove_indicator(indicator_name)
        
    def clear_indicators(self) -> None:
        """清除所有指标"""
        self.indicator_manager.clear_all_indicators()
        
    def _check_chart_ready(self):
        """检查图表是否初始化完成"""
        self.bridge_manager.check_chart_ready()