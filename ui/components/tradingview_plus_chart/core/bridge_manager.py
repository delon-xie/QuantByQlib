# core/bridge_manager.py
from PyQt6.QtCore import QTimer
import json
from typing import Dict, Any, Optional

class BridgeManager:
    """桥接管理器 - 处理Python-JavaScript通信"""
    
    def __init__(self, widget):
        self.widget = widget
        self.is_chart_ready = False
        
    def check_chart_ready(self):
        """检查图表是否就绪"""
        js_code = """
        (function() {
            return {
                isChartInitialized: window.isChartInitialized === true,
                hasMainChart: typeof window.mainChart !== 'undefined',
                hasSetChartData: typeof window.setChartData === 'function'
            };
        })();
        """
        
        self.widget.browser.page().runJavaScript(js_code, self._on_chart_ready_check)
        
    def _on_chart_ready_check(self, result: Optional[Dict]):
        """图表就绪检查回调"""
        if result and result.get('isChartInitialized'):
            self.is_chart_ready = True
            print("✅ Chart is ready!")
        else:
            QTimer.singleShot(300, self.check_chart_ready)
            
    def send_data_to_js(self, data_json: str):
        """发送数据到JavaScript"""
        js_code = f"""
        if (typeof window.setChartData === 'function') {{
            window.setChartData({data_json});
        }}
        """
        self.widget.browser.page().runJavaScript(js_code)
        
    def send_indicator_to_js(self, indicator_name: str, data_json: str, options: Dict):
        """发送指标数据到JavaScript"""
        js_code = f"""
        (function() {{
            const options = {json.dumps(options)};
            options.data = {data_json};
            
            if (typeof window.addIndicator === 'function') {{
                window.addIndicator('{indicator_name}', options);
            }}
        }})();
        """
        self.widget.browser.page().runJavaScript(js_code)
        
    def remove_indicator_from_js(self, indicator_name: str):
        """从JavaScript移除指标"""
        js_code = f"""
        if (typeof window.removeIndicator === 'function') {{
            window.removeIndicator('{indicator_name}');
        }}
        """
        self.widget.browser.page().runJavaScript(js_code)
        
    def clear_all_indicators_from_js(self):
        """从JavaScript清除所有指标"""
        js_code = """
        if (typeof window.clearAllIndicators === 'function') {
            window.clearAllIndicators();
        }
        """
        self.widget.browser.page().runJavaScript(js_code)