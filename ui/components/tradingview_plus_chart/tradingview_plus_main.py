# main.py
import sys
import pandas as pd
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt

from core.chart_widget import TradingViewChartWidget
from ui.right_panel import RightPanel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TradingView Plus Chart")
        self.setGeometry(100, 100, 1400, 800)
        
        self._setup_ui()
        self._load_sample_data()
        
    def _setup_ui(self):
        """设置UI布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # 创建图表组件
        self.chart_widget = TradingViewChartWidget()
        layout.addWidget(self.chart_widget, 3)  # 图表占3/4
        
        # 创建右侧面板
        self.right_panel = RightPanel()
        layout.addWidget(self.right_panel, 1)  # 面板占1/4
        
        # 连接信号
        self._connect_signals()
        
    def _connect_signals(self):
        """连接信号和槽"""
        # 常用指标
        self.right_panel.common_indicator_clicked.connect(
            self._on_common_indicator_clicked
        )
        
        # 高级指标
        self.right_panel.advanced_indicator_clicked.connect(
            self._on_advanced_indicator_selected
        )
        
        # 参数应用
        self.right_panel.apply_parameters.connect(
            self._on_apply_parameters
        )
        
        # 参数更新
        self.right_panel.update_parameters.connect(
            self._on_update_parameters
        )
        
    def _load_sample_data(self):
        """加载示例数据"""
        # 创建示例数据
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': 100 + pd.Series(range(100)).cumsum() * 0.1 + 
                   pd.Series(range(100)).apply(lambda x: pd.np.random.normal(0, 2)),
            'high': 102 + pd.Series(range(100)).cumsum() * 0.1 + 
                   pd.Series(range(100)).apply(lambda x: pd.np.random.normal(0, 3)),
            'low': 98 + pd.Series(range(100)).cumsum() * 0.1 + 
                  pd.Series(range(100)).apply(lambda x: pd.np.random.normal(0, 3)),
            'close': 101 + pd.Series(range(100)).cumsum() * 0.1 + 
                    pd.Series(range(100)).apply(lambda x: pd.np.random.normal(0, 2)),
            'volume': pd.Series(range(100)).apply(
                lambda x: 1000 + pd.np.random.normal(0, 200)
            ).abs()
        })
        
        # 更新图表数据
        self.chart_widget.update_data(df)
        
    def _on_common_indicator_clicked(self, indicator_id: str):
        """处理常用指标点击"""
        print(f"常用指标点击: {indicator_id}")
        
        # 这里可以直接调用指标计算
        # 常用指标使用默认参数
        self.chart_widget.add_indicator(indicator_id)
        
    def _on_advanced_indicator_selected(self, indicator_id: str):
        """处理高级指标选择"""
        print(f"高级指标选择: {indicator_id}")
        # 面板会自动跳转到参数设置Tab
        
    def _on_apply_parameters(self, indicator_id: str, parameters: dict):
        """处理参数应用"""
        print(f"应用参数: {indicator_id}, 参数: {parameters}")
        
        # 使用参数添加指标
        self.chart_widget.add_indicator(indicator_id, **parameters)
        
    def _on_update_parameters(self, indicator_id: str, parameters: dict):
        """处理参数更新"""
        print(f"更新参数: {indicator_id}, 新参数: {parameters}")
        
        # 先移除旧指标
        self.chart_widget.remove_indicator(indicator_id)
        
        # 使用新参数重新添加
        self.chart_widget.add_indicator(indicator_id, **parameters)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())