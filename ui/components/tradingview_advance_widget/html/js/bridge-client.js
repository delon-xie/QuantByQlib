/**
 * BridgeClient — QWebChannel 客户端。
 * 连接 Python 端 ChartBridge，提供统一的方法调用接口。
 * 拦截 console 日志转发到 Python 端。
 * 新增: debug inspection, Python fallback, dual engine support
 */
class BridgeClient {
  constructor() {
    this.bridge = null;
    this.connected = false;
    this.pendingData = null;
    this.pendingIndicators = [];
    this.pendingPythonRequests = []; // Python-only 指标的待发送请求
    this.callbacks = new Map();
    this._origConsole = {};
  }

  /** 初始化 QWebChannel 连接 */
  connect() {
    if (typeof QWebChannel === 'undefined') {
      console.warn('BridgeClient: QWebChannel not available, retrying in 500ms...');
      var self = this;
      setTimeout(function() { self.connect(); }, 500);
      return;
    }
    var self = this;
    new QWebChannel(qt.webChannelTransport, function(channel) {
      self.bridge = channel.objects.bridge;
      if (self.bridge) {
        self.connected = true;
        console.log('BridgeClient: Connected to Python bridge');
        self._hookConsole();
        self.bridge.on_chart_ready();
        // 延迟 flushPending 确保 initApp() 有足够时间完成初始化
        setTimeout(function() {
          self.flushPending();
          console.log('[BC] flushPending called after delay');
        }, 200);
      }
    });
  }

  /** 拦截 console 日志，转发到 Python 端 */
  _hookConsole() {
    var self = this;
    var methods = ['log', 'warn', 'error', 'info'];
    for (var i = 0; i < methods.length; i++) {
      var method = methods[i];
      var original = console[method];
      this._origConsole[method] = original;
      (function(m, orig) {
        console[m] = function() {
          if (self._inHook) return orig.apply(console, arguments);
          self._inHook = true;
          try {
            var args = Array.prototype.slice.call(arguments);
            var msg = args.map(function(a) {
              try { return typeof a === 'object' ? JSON.stringify(a) : String(a); }
              catch(e) { return String(a); }
            }).join(' ');
            if (self.bridge && self.connected) {
              try { self.bridge.on_console_log('[' + m.toUpperCase() + '] ' + msg); } catch(e) {}
            }
          } finally {
            self._inHook = false;
          }
          orig.apply(console, arguments);
        };
      })(method, original);
    }
  }

  /** 注册回调 */
  on(method, fn) {
    this.callbacks.set(method, fn);
  }

  /** Python 端调用的统一入口 */
  callMethod(method, args) {
    var fn = this.callbacks.get(method);
    if (fn) fn(args);
    var methodMap = {
      setChartData: function(args) { this._handleSetChartData(args[0]); }.bind(this),
      addIndicatorResult: function(args) { this._handleAddIndicatorResult(args[0], args[1], args[2]); }.bind(this),
      loadState: function(args) { this._handleLoadState(args[0]); }.bind(this),
      setComputeSource: function(args) { if (window.indicatorEngine) window.indicatorEngine.setComputeSource(args[0]); }.bind(this),
      debugEngine: function(args) {
        var info = this.inspectEngine();
        console.log('Engine Debug:', JSON.stringify(info, null, 2));
      }.bind(this),
    };
    var handler = methodMap[method];
    if (handler) handler(args);
  }

  // ==================== 新: Python 回退请求 ====================

  /**
   * bridgeCall — 带重试机制的桥接调用
   * @param {string} method - 桥接方法名
   * @param {Array} args - 参数数组
   * @param {number} retries - 剩余重试次数
   * @param {number} delay - 当前延迟(ms)
   */
  bridgeCall(method, args, retries, delay) {
    if (!this.connected || !this.bridge) {
      console.warn('[Bridge] Not connected, cannot call ' + method);
      return;
    }
    try {
      this.bridge[method].apply(this.bridge, args);
    } catch (e) {
      if (retries > 0) {
        var nextDelay = delay * 2;
        console.warn('[Bridge] ' + method + ' failed, retrying in ' + delay + 'ms (' + retries + ' left)');
        var self = this;
        setTimeout(function() { self.bridgeCall(method, args, retries - 1, nextDelay); }, delay);
      } else {
        console.error('[Bridge] ' + method + ' failed after all retries', e);
      }
    }
  }

  /** 通知 Python 端切换到当前时间框架的数据（用于 Python 指标重算） */
  setTimeframeData(barsJson) {
    this.bridgeCall('set_timeframe_data', [barsJson], 2, 500);
  }

  /**
   * requestPythonIndicator — 请求 Python 端计算指标
   * 由 indicatorEngine._requestPythonFallback() 调用
   */
  requestPythonIndicator(key, paramsJson) {
    if (!this.connected || !this.bridge) {
      console.warn('[Bridge] Not connected, queuing Python request: ' + key);
      this.pendingPythonRequests.push({ key: key, paramsJson: paramsJson });
      return;
    }
    this.bridgeCall('request_python_calc', [key, paramsJson], 1, 1000);
  }

  /**
   * requestPythonInspect — 请求 Python 端返回可用的自定义指标列表
   */
  requestPythonInspect() {
    if (!this.connected || !this.bridge) return;
    try {
      this.bridge.request_python_inspect();
    } catch (e) {
      console.error('BridgeClient: Failed to request Python inspect', e);
    }
  }

  // ==================== 新: JS 引擎调试 ====================

  /**
   * inspectEngine — 引擎自检
   * 返回 JS indicatorEngine 的完整调试信息
   */
  inspectEngine() {
    var ie = window.indicatorEngine;
    if (!ie) return { error: 'indicatorEngine not initialized' };
    return ie.debug();
  }

  // ==================== 原有方法 ====================

  setChartData(data) {
    console.log('[BC] setChartData called: connected=' + this.connected + ', bars=' + (data ? data.length : 0));
    console.log('[BC] window.isChartInitialized:', window.isChartInitialized);
    console.log('[BC] window.chartManager:', !!window.chartManager);
    console.log('[BC] window.indicatorEngine:', !!window.indicatorEngine);
    if (!this.connected) { 
      this.pendingData = data; 
      console.log('[BC] data stored in pendingData, will retry after connect'); 
      return; 
    }
    this._handleSetChartData(data);
  }

  addIndicatorResult(key, data, opts) {
    if (!this.connected) { this.pendingIndicators.push({ key: key, data: data, opts: opts }); return; }
    this._handleAddIndicatorResult(key, data, opts);
  }

  loadState(state) {
    if (!this.connected) return;
    this._handleLoadState(state);
  }

  exportState() {
    var state = window.jsStateManager ? window.jsStateManager.serialize() : null;
    if (state && this.bridge) {
      this.bridge.on_state_exported(JSON.stringify(state));
    }
  }

  // ==================== 内部处理方法 ====================

  _handleSetChartData(data) {
    console.log('[BC] _handleSetChartData: bars=' + (data ? data.length : 0));
    if (data && data.length > 0) {
      console.log('[BC] first bar:', JSON.stringify(data[0]));
      console.log('[BC] last bar:', JSON.stringify(data[data.length - 1]));
    }
    // 检查关键组件是否全部就绪
    var components = {
      chartManager: !!window.chartManager,
      indicatorEngine: !!window.indicatorEngine,
      timeframeController: !!window.timeframeController,
      indicatorPanel: !!window.indicatorPanel,
    };
    console.log('[BC] components ready:', JSON.stringify(components));
    var allReady = components.chartManager && components.indicatorEngine;
    if (!allReady) {
      console.log('[BC] Components not ready, storing data to pending, will retry...');
      this.pendingData = data;
      var self = this;
      setTimeout(function() {
        console.log('[BC] Retrying _handleSetChartData after delay');
        if (window.chartManager && window.indicatorEngine) {
          self._handleSetChartData(data);
        } else {
          console.error('[BC] Components still not ready after retry, giving up');
        }
      }, 500);
      return;
    }
    // 0. 保存当前画线（在清除之前）
    var savedDrawings = null;
    if (window.drawingTools) {
      try { savedDrawings = window.drawingTools.export(); } catch(e) { console.warn('[BC] drawingTools.export failed:', e.message); }
    }
    // 0. 保存当前活跃指标（在清除之前）
    if (window.timeframeController) {
      window.timeframeController.saveActiveIndicators();
    }
    // 完全重置：清除所有历史指标、子图、面板状态，恢复初始状态
    if (window.indicatorEngine) {
      // 清除所有已注册指标的图形元素
      window.indicatorEngine._activeMap.forEach(function(info, sid) {
        var cm = window.chartManager;
        if (cm && info.elements) {
          for (var ei = 0; ei < info.elements.length; ei++) {
            var el = info.elements[ei];
            if (el.type === 'series') { try { cm.removeSeries(el.key); } catch(e) {} }
            else { try { cm.setExtraKeyVisible(el.key, false); } catch(e) {} }
          }
        }
      });
      window.indicatorEngine._activeMap.clear();
      window.indicatorEngine._visibleMap.clear();
      window.indicatorEngine.barData = [];
    }
    if (window.chartManager) {
      console.log('[BC] chartManager.clearAll and setCandleData');
      window.chartManager.clearAll();
      window.chartManager.setCandleData(data);
    } else {
      console.error('[BC] chartManager not found!');
    }
    if (window.indicatorEngine) {
      window.indicatorEngine.setBarData(data);
    }
    // 初始化时间周期控制器
    if (window.timeframeController) {
      window.timeframeController.setOriginalBars(data);
    }
    // 重设价格坐标轴自适应，所有数据线和指标线渲染完毕后最佳化显示
    if (window.chartManager) {
      try {
        window.chartManager.mainChart.priceScale('right').applyOptions({ autoScale: true });
        window.chartManager.mainChart.timeScale().fitContent();
      } catch(e) { console.warn('[BC] chart reset failed:', e.message); }
    }
    // 重置右侧面板状态 — 延迟执行确保所有初始化完成
    if (window.indicatorPanel) {
      var self = this;
      setTimeout(function() {
        window.indicatorPanel.refresh();
        console.log('[RESET] Panel refresh (deferred)');
      }, 50);
    }
    // 重置组合预设状态
    if (window.combinedPresets) {
      window.combinedPresets._active = {};
    }
    // 强制重建 catalog（确保 _findCalc 修正后重新解析注册表条目）
    if (window.indicatorEngine) {
      window.indicatorEngine._catalog = [];
      window.indicatorEngine._buildCatalog();
      console.log('[RESET] Catalog rebuilt: ' + window.indicatorEngine._catalog.length + ' indicators');
    }
    // 重建保存的活跃指标（数据就绪 + fitContent + catalog 重建后执行）
    if (window.timeframeController) {
      window.timeframeController.restoreActiveIndicators();
    }
    // 恢复画线
    if (savedDrawings && savedDrawings.length > 0 && window.drawingTools) {
      window.drawingTools.import(savedDrawings);
      console.log('[RESET] Restored ' + savedDrawings.length + ' drawings');
    }
    console.log('[RESET] Full chart reset on data load: ' + (data ? data.length : 0) + ' bars');
  }

  _handleAddIndicatorResult(key, data, opts) {
    // 调用 indicatorEngine.handlePythonResult 以保持状态同步
    if (window.indicatorEngine) {
      window.indicatorEngine.handlePythonResult(key, data, opts);
    } else if (window.chartManager) {
      window.chartManager.addLineSeries(key, data, opts);
    }
  }

  _handleLoadState(state) {
    if (window.chartManager) window.chartManager.clearAll();
    if (state.indicators) {
      for (var key in state.indicators) {
        if (state.indicators.hasOwnProperty(key)) {
          var info = state.indicators[key];
          if (window.indicatorEngine) window.indicatorEngine.calculateAndAdd(key, info.params || {});
        }
      }
    }
    if (state.drawings && window.drawingTools) {
      window.drawingTools.import(state.drawings);
    }
    if (window.chartManager) window.chartManager.fitContent();
  }

  flushPending() {
    if (this.pendingData) {
      this._handleSetChartData(this.pendingData);
      this.pendingData = null;
    }
    for (var i = 0; i < this.pendingIndicators.length; i++) {
      var item = this.pendingIndicators[i];
      this._handleAddIndicatorResult(item.key, item.data, item.opts);
    }
    this.pendingIndicators = [];
    // 刷新 Python 待发送请求
    for (var pi = 0; pi < this.pendingPythonRequests.length; pi++) {
      var req = this.pendingPythonRequests[pi];
      try {
        this.bridge.request_python_calc(req.key, req.paramsJson);
        console.log('BridgeClient: Flushed Python calc request: ' + req.key);
      } catch (e) {
        console.error('BridgeClient: Failed to flush Python request', e);
      }
    }
    this.pendingPythonRequests = [];
  }
}

window.bridgeClient = new BridgeClient();
