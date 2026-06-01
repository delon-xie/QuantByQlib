# ui/right_panel.py
from PyQt6.QtWidgets import (QTabWidget, QWidget, QVBoxLayout, 
                             QScrollArea, QGridLayout, QPushButton,
                             QLabel, QLineEdit, QFormLayout, QGroupBox)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Dict, List, Any, Optional
from enum import Enum
from .common_indicators_tab import CommonIndicatorsTab
from .advanced_indicators_tab import AdvancedIndicatorsTab
from .parameter_settings_tab import ParameterSettingsTab

class PanelTab(Enum):
    """面板Tab页枚举"""
    COMMON = "常用"
    ADVANCED = "高级"
    SETTINGS = "参数设置"

class IndicatorButton(QPushButton):
    """指标按钮控件"""
    clicked_with_id = pyqtSignal(str)  # 发射指标ID
    
    def __init__(self, indicator_id: str, name: str, parent=None):
        super().__init__(name, parent)
        self.indicator_id = indicator_id
        self.clicked.connect(self._on_clicked)
        
    def _on_clicked(self):
        self.clicked_with_id.emit(self.indicator_id)

class RightPanel(QTabWidget):
    """右侧面板主组件"""
    
    # 信号定义
    common_indicator_clicked = pyqtSignal(str)  # 常用指标点击
    advanced_indicator_clicked = pyqtSignal(str)  # 高级指标点击
    apply_parameters = pyqtSignal(str, dict)  # 应用参数
    update_parameters = pyqtSignal(str, dict)  # 更新参数
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_indicator = None
        self.current_parameters = {}
        
        self._setup_ui()
        self._load_indicator_configs()
        
    def _setup_ui(self):
        """初始化UI"""
        # 创建三个Tab页
        self.common_tab = CommonIndicatorsTab()
        self.advanced_tab = AdvancedIndicatorsTab()
        self.settings_tab = ParameterSettingsTab()
        
        # 添加Tab页
        self.addTab(self.common_tab, PanelTab.COMMON.value)
        self.addTab(self.advanced_tab, PanelTab.ADVANCED.value)
        self.addTab(self.settings_tab, PanelTab.SETTINGS.value)
        
        # 连接信号
        self.common_tab.indicator_clicked.connect(self._on_common_indicator_clicked)
        self.advanced_tab.indicator_clicked.connect(self._on_advanced_indicator_clicked)
        self.settings_tab.apply_clicked.connect(self._on_apply_parameters)
        
    def _load_indicator_configs(self):
        """加载指标配置"""
        from config.indicator_config import get_common_indicators, get_advanced_indicators
        
        self.common_indicators = get_common_indicators()
        self.advanced_indicators = get_advanced_indicators()
        
        # 更新UI
        self.common_tab.set_indicators(self.common_indicators)
        self.advanced_tab.set_indicators(self.advanced_indicators)
        
    def _on_common_indicator_clicked(self, indicator_id: str):
        """处理常用指标点击"""
        indicator_config = self.common_indicators.get(indicator_id)
        if indicator_config:
            # 使用默认参数
            parameters = indicator_config.get("default_parameters", {})
            self.common_indicator_clicked.emit(indicator_id)
            
            # 直接调用指标计算
            self.apply_parameters.emit(indicator_id, parameters)
            
    def _on_advanced_indicator_clicked(self, indicator_id: str):
        """处理高级指标点击"""
        self.current_indicator = indicator_id
        indicator_config = self.advanced_indicators.get(indicator_id)
        
        if indicator_config:
            # 跳转到参数设置Tab
            self.setCurrentWidget(self.settings_tab)
            
            # 设置参数表单
            parameters = indicator_config.get("parameters", {})
            self.settings_tab.set_indicator(indicator_config, parameters)
            
    def _on_apply_parameters(self, parameters: dict):
        """处理参数应用"""
        if self.current_indicator:
            if self.current_indicator in self.advanced_indicators:
                # 高级指标 - 首次添加
                self.apply_parameters.emit(self.current_indicator, parameters)
            elif self.current_indicator in self._active_indicators:
                # 已存在指标 - 更新参数
                self.update_parameters.emit(self.current_indicator, parameters)