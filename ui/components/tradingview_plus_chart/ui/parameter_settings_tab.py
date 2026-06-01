# ui/parameter_settings_tab.py
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
                             QComboBox, QCheckBox, QPushButton, QHBoxLayout,
                             QGroupBox, QScrollArea)
from PyQt6.QtCore import pyqtSignal, Qt
from typing import Dict, Any, List
import re

class ParameterField:
    """参数字段基类"""
    
    def __init__(self, param_config: Dict):
        self.name = param_config.get("name", "")
        self.key = param_config.get("key", "")
        self.type = param_config.get("type", "int")
        self.default = param_config.get("default")
        self.description = param_config.get("description", "")
        self.required = param_config.get("required", True)
        self.min_value = param_config.get("min")
        self.max_value = param_config.get("max")
        self.options = param_config.get("options", [])
        
    def create_widget(self, parent=None):
        """创建对应的输入控件"""
        if self.type == "int":
            widget = QSpinBox(parent)
            if self.min_value is not None:
                widget.setMinimum(self.min_value)
            if self.max_value is not None:
                widget.setMaximum(self.max_value)
            if self.default is not None:
                widget.setValue(self.default)
                
        elif self.type == "float":
            widget = QDoubleSpinBox(parent)
            widget.setDecimals(4)
            if self.min_value is not None:
                widget.setMinimum(self.min_value)
            if self.max_value is not None:
                widget.setMaximum(self.max_value)
            if self.default is not None:
                widget.setValue(self.default)
                
        elif self.type == "string":
            widget = QLineEdit(parent)
            if self.default:
                widget.setText(str(self.default))
                
        elif self.type == "bool":
            widget = QCheckBox("启用", parent)
            if self.default is not None:
                widget.setChecked(bool(self.default))
                
        elif self.type == "select":
            widget = QComboBox(parent)
            for option in self.options:
                if isinstance(option, dict):
                    widget.addItem(option.get("label", ""), option.get("value"))
                else:
                    widget.addItem(str(option), option)
            if self.default is not None:
                index = widget.findData(self.default)
                if index >= 0:
                    widget.setCurrentIndex(index)
                    
        elif self.type == "color":
            widget = QLineEdit(parent)
            if self.default:
                widget.setText(self.default)
            widget.setPlaceholderText("#RRGGBB")
            
        return widget
        
    def validate(self, value) -> bool:
        """验证输入值"""
        if self.required and value in [None, ""]:
            return False
            
        if self.type == "int":
            try:
                int_val = int(value)
                if self.min_value is not None and int_val < self.min_value:
                    return False
                if self.max_value is not None and int_val > self.max_value:
                    return False
            except:
                return False
                
        elif self.type == "float":
            try:
                float_val = float(value)
                if self.min_value is not None and float_val < self.min_value:
                    return False
                if self.max_value is not None and float_val > self.max_value:
                    return False
            except:
                return False
                
        elif self.type == "color":
            if value and not re.match(r'^#[0-9A-Fa-f]{6}$', value):
                return False
                
        return True

class ParameterSettingsTab(QWidget):
    """参数设置Tab页"""
    
    apply_clicked = pyqtSignal(dict)  # 参数应用
    cancel_clicked = pyqtSignal()  # 取消
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_indicator = None
        self.parameter_fields = {}
        self.parameter_widgets = {}
        self._setup_ui()
        
    def _setup_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        # 内容容器
        self.content_widget = QWidget()
        self.main_layout = QVBoxLayout(self.content_widget)
        
        # 指标信息区域
        self.info_group = QGroupBox("指标信息")
        self.info_layout = QVBoxLayout()
        self.info_group.setLayout(self.info_layout)
        self.main_layout.addWidget(self.info_group)
        
        # 参数表单区域
        self.form_group = QGroupBox("参数设置")
        self.form_layout = QFormLayout()
        self.form_group.setLayout(self.form_layout)
        self.main_layout.addWidget(self.form_group)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.apply_btn = QPushButton("应用")
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_btn.setEnabled(False)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_clicked.emit)
        
        button_layout.addStretch()
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.cancel_btn)
        
        self.main_layout.addLayout(button_layout)
        
        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll)
        
    def set_indicator(self, indicator_config: Dict, parameters: Dict[str, Dict]):
        """设置当前指标和参数"""
        self.current_indicator = indicator_config.get("id")
        
        # 清空表单
        self._clear_form()
        
        # 显示指标信息
        self._show_indicator_info(indicator_config)
        
        # 创建参数表单
        self._create_parameter_form(parameters)
        
        self.apply_btn.setEnabled(True)
        
    def _show_indicator_info(self, config: Dict):
        """显示指标信息"""
        # 清空信息区域
        for i in reversed(range(self.info_layout.count())): 
            self.info_layout.itemAt(i).widget().setParent(None)
            
        # 添加信息
        info_items = [
            ("指标名称", config.get("name", "")),
            ("指标类型", config.get("type", "line")),
            ("显示位置", "主图" if config.get("chart") == "main" else "副图"),
            ("描述", config.get("description", ""))
        ]
        
        for label, value in info_items:
            if value:
                layout = QHBoxLayout()
                layout.addWidget(QLabel(f"<b>{label}:</b>"))
                layout.addWidget(QLabel(str(value)))
                layout.addStretch()
                self.info_layout.addLayout(layout)
                
    def _create_parameter_form(self, parameters: Dict[str, Dict]):
        """创建参数表单"""
        self.parameter_fields.clear()
        self.parameter_widgets.clear()
        
        for param_key, param_config in parameters.items():
            field = ParameterField(param_config)
            self.parameter_fields[param_key] = field
            
            # 创建控件
            widget = field.create_widget(self)
            self.parameter_widgets[param_key] = widget
            
            # 添加到表单
            label = QLabel(f"{field.name}:")
            if field.description:
                label.setToolTip(field.description)
                
            self.form_layout.addRow(label, widget)
            
    def _clear_form(self):
        """清空表单"""
        # 清空参数区域
        for i in reversed(range(self.form_layout.rowCount())):
            self.form_layout.removeRow(i)
            
        self.parameter_fields.clear()
        self.parameter_widgets.clear()
        
    def _on_apply(self):
        """处理应用按钮点击"""
        parameters = self._collect_parameters()
        if parameters is not None:
            self.apply_clicked.emit(parameters)
            
    def _collect_parameters(self) -> Dict:
        """收集所有参数值"""
        parameters = {}
        
        for key, field in self.parameter_fields.items():
            widget = self.parameter_widgets.get(key)
            if not widget:
                continue
                
            # 获取值
            if isinstance(widget, QSpinBox) or isinstance(widget, QDoubleSpinBox):
                value = widget.value()
            elif isinstance(widget, QLineEdit):
                value = widget.text().strip()
            elif isinstance(widget, QComboBox):
                value = widget.currentData()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            else:
                value = None
                
            # 验证
            if not field.validate(value):
                self._show_error(f"参数验证失败: {field.name}")
                return None
                
            parameters[key] = value
            
        return parameters
        
    def _show_error(self, message: str):
        """显示错误信息"""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "参数错误", message)