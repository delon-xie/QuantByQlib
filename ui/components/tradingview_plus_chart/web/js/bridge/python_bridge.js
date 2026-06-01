// web/js/bridge/python_bridge.js
class PythonBridge {
    constructor() {
        this.callbacks = new Map();
        this._setupBridge();
    }
    
    _setupBridge() {
        // 创建消息处理器
        window.onPythonMessage = (data) => {
            this.handlePythonMessage(data);
        };
        
        // 创建通知函数
        window.notifyPython = (type, data) => {
            this.notify(type, data);
        };
        
        console.log('✅ Python桥接已设置');
    }
    
    handlePythonMessage(data) {
        console.log('📨 收到Python消息:', data);
        
        if (data.type && this.callbacks.has(data.type)) {
            const callback = this.callbacks.get(data.type);
            callback(data.data);
        }
    }
    
    notify(type, data) {
        console.log(`📤 发送到Python: ${type}`, data);
        
        // 这里需要实现与Python的实际通信
        // 通常是调用Python端的回调函数
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.notify(type, data);
        } else if (window.chrome && window.chrome.webview) {
            window.chrome.webview.postMessage({ type, data });
        } else {
            // 回退方案
            console.log('模拟发送到Python:', { type, data });
        }
    }
    
    registerCallback(type, callback) {
        this.callbacks.set(type, callback);
    }
    
    unregisterCallback(type) {
        this.callbacks.delete(type);
    }
}

// 导出到全局
window.pythonBridge = new PythonBridge();