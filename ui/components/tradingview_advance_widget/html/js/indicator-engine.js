/**
 * IndicatorEngine — 446 指标引擎 + 双引擎回退 + 高级渲染
 *
 * 核心设计：每个指标是一个自包含单元，持有自己的所有图形元素。
 * show = 创建所有元素(hide时已销毁); hide = 销毁所有元素; 
 * 无共享状态、无 key 冲突、无生命周期交叉。
 */
class IndicatorEngine {
  constructor() {
    this._catalog = [];
    this._activeMap = new Map();    // stateId → { params, group, seriesKeys, overlay, elements:[] }
    this._visibleMap = new Map();   // stateId → bool
    this.barData = [];
    this._groupLabels = { standard:'Standard (82)', community:'Community (317)', candlestick:'Candlestick (44)' };
    this._categoryOrder = ['Moving Averages','Momentum','Oscillators','Trend','Volatility','Volume','Channels & Bands','Candlestick Patterns'];
    this._computeSource = 'auto';
    this._pendingPythonResults = new Map();
    this._showData = new Set();
    this._candlestickCounts = {}; // {stateId: count}  K线形态检测计数
    // _elements: stateId → [{type, series, prim}], 由 _renderResult 填充，_hideOne 消费
  }

  init() {
    var lci = window.LightweightChartsIndicators;
    if (!lci) { var s = this; setTimeout(function(){ s.init(); }, 500); return; }
    this._indicators = lci;
    this._buildCatalog();
    console.log('IndicatorEngine: Loaded ' + this._catalog.length + ' indicators');
  }

  // ========== Catalog building (unchanged) ==========

  // extracted → indicator-catalog.js
  _findCalc(lci, name) {
    // extracted → indicator-catalog.js
  }

  _buildCatalog() {
    // extracted → indicator-catalog.js
  }

  setComputeSource(source) {
    // extracted → indicator-catalog.js
  }

  _requestPythonFallback(id, params) {
    // extracted → indicator-catalog.js
  }

  _requestPythonOnly(id, params) {
    // extracted → indicator-catalog.js
  }

  debug() {
    // extracted → indicator-catalog.js
  }

  _resolveAlias(id, params) {
    // extracted → indicator-catalog.js
  }

  _findCatalogEntry(id) {
    // extracted → indicator-catalog.js
  }

  // ========== Core toggle ==========

  toggle(id, params) {
    var r = this._resolveAlias(id, params);
    console.log('[TOGGLE] ' + id + ' -> resolved id=' + r.id + ' baseId=' + r.baseId + ' visibleMap.has=' + this._visibleMap.has(r.id) + ' visibleMap.get=' + this._visibleMap.get(r.id));

    if (this._visibleMap.has(r.id)) {
      if (this._visibleMap.get(r.id)) this._hide(r.id);
      else this._show(r.id);
      return;
    }
    if (this._computeSource === 'python') { this._requestPythonFallback(r.id, r.params); return; }
    if (r.id === 'BaseVolume') { this._calculateBaseVolume(r.id); return; }
    if (r.id === 'Yearly_Profile') { this._requestPythonOnly(r.id, r.params); return; }
    if (r.id === 'MA_Combo') { this._calculateSMACombo(r.id, r.params); return; }
    if (r.id === 'SMA_Combo') { this._calculateSMACombo(r.id, r.params); return; }
    if (r.id === 'EMA_Combo') { this._calculateEMACombo(r.id, r.params); return; }
    if (r.id === 'SMA_EMA_Combo') { this._calculateSMAEMACombo(r.id, r.params); return; }
    if (r.id === 'VolatilitySuite') { this._calculateCompound(r.id, [
      { id: 'BollingerBands', params: { length: 20, std: 2 }, color: '#2962FF' },
      { id: 'ATR', params: { length: 14 }, color: '#FF5722' },
    ], 'VOLATILITY'); return; }
    if (r.id === 'TrendFollowSuite') { this._calculateCompound(r.id, [
      { id: 'ADX', params: { length: 14 }, color: '#FF9800' },
      { id: 'SuperTrend', params: { length: 10, multiplier: 3 }, color: '#E91E63' },
      { id: 'EMA', params: { length: 50 }, color: '#4CAF50' },
    ], 'TREND'); return; }
    if (r.id === 'MomentumSuite') { this._calculateCompound(r.id, [
      { id: 'MACD', params: { fastLength: 12, slowLength: 26, signalLength: 9 }, color: '#FF9800' },
      { id: 'RSI', params: { length: 14 }, color: '#E91E63' },
      { id: 'Stochastic', params: {}, color: '#00BCD4' },
    ], 'MOMENTUM'); return; }
    var entry = this._findCatalogEntry(r.baseId);
    // Fallback: if catalog entry not found but LCI has direct key, use it directly
    if (!entry && this._indicators && this._indicators[r.baseId] && this._indicators[r.baseId].calculate) {
      var lciFn = this._indicators[r.baseId];
      console.log('[DIRECT] ' + r.baseId + ': using LCI direct key (catalog lookup failed)');
      entry = {
        id: r.baseId, name: (lciFn.metadata && lciFn.metadata.title) || r.baseId,
        shortName: (lciFn.metadata && lciFn.metadata.shortTitle) || r.baseId,
        overlay: lciFn.metadata ? lciFn.metadata.overlay !== false : true,
        inputs: lciFn.inputConfig || [],
        plots: lciFn.plotConfig || [],
        defaults: lciFn.defaultInputs || {},
        hlineConfig: lciFn.hlineConfig || null,
        fillConfig: lciFn.fillConfig || null,
        calculate: lciFn.calculate,
      };
    }
    // Verify: if LCI has a direct key with calculate, use it as authoritative
    if (entry && this._indicators && this._indicators[r.baseId] && this._indicators[r.baseId].calculate) {
      var lciFn = this._indicators[r.baseId];
      if (lciFn.calculate !== entry.calculate) {
        // Catalog entry has wrong calculate — fix it and use correct one
        console.warn('[FIX] ' + r.baseId + ': catalog calculate mismatch, patching from LCI direct key');
        entry.calculate = lciFn.calculate;
        entry.plotConfig = lciFn.plotConfig || entry.plotConfig;
        entry.inputConfig = lciFn.inputConfig || entry.inputConfig;
        entry.defaults = lciFn.defaultInputs || entry.defaults;
        entry.hlineConfig = lciFn.hlineConfig || null;
        entry.fillConfig = lciFn.fillConfig || null;
        entry.metadata = lciFn.metadata || entry.metadata;
        if (lciFn.metadata && lciFn.metadata.overlay !== undefined) entry.overlay = lciFn.metadata.overlay;
      }
    }
    if (entry) { this._calculateAndAdd(r.id, entry, r.params); }
    else if (this._computeSource === 'auto') {
      this._register(r.id, r.params, 'PYTHON', []);
      this._requestPythonFallback(r.id, r.params);
    }
  }

  // ========== Built-in indicators ==========

  _calculateBaseVolume(id) {
    // extracted → indicator-calculator.js
  }

  /** SMA组合：6个可配置周期，周期=0时不显示 */
  _calculateSMACombo(id, params) {
    // extracted → indicator-calculator.js
  }

  /** EMA组合：6个可配置周期，周期=0时不显示 */
  _calculateEMACombo(id, params) {
    // extracted → indicator-calculator.js
  }

  /** SMA+EMA组合：前3=SMA，后3=EMA，周期=0时不显示 */
  _calculateSMAEMACombo(id, params) {
    // extracted → indicator-calculator.js
  }

  /**
   * _calculateCompound — 复合指标渲染器
   * 将多个子指标的计算结果渲染到同一个 stateId 下，确保预设与独立指标互不干扰。
   * 每个子指标创建独立的 series/primitive，通过前缀 key 隔离。
   */
  _calculateCompound(suiteId, subIndicators, suiteGroup) {
    // extracted → indicator-calculator.js
  }

  _calcSMA(data, length, isSMA) {
    // extracted → indicator-calculator.js
  }

  calculateAndAdd(stateId, params) {
    // extracted → indicator-calculator.js
  }

  /** _calculateAndAdd — 计算+渲染+注册，所有图形元素存储在本指标单位内 */
  _calculateAndAdd(stateId, entry, params) {
    // extracted → indicator-calculator.js
  }

  /** _renderResult — 渲染计算结果，所有元素存入 _activeMap 的 elements 数组 */
  _renderResult(stateId, entry, result, mergedParams) {
    // extracted → indicator-renderer.js
  }

  _register(stateId, params, group, seriesKeys, overlay, elements) {
    // extracted → indicator-renderer.js
  }

  handlePythonResult(stateId, data, opts) {
    // extracted → indicator-lifecycle.js
  }

  // ========== 折叠式显隐控制：show=重建，hide=销毁 ==========

  _hide(stateId) {
    // extracted → indicator-lifecycle.js
  }

  _show(stateId) {
    // extracted → indicator-lifecycle.js
  }

  /** _hideOne — 遍历本指标的 elements，全部物理销毁（直接操作 primitiveMap/candleSeries） */
  _hideOne(stateId) {
    // extracted → indicator-lifecycle.js
  }

  _toggleLinked(stateId, show) {
    // extracted → indicator-lifecycle.js
  }

  _removeOne(id) {
    // extracted → indicator-lifecycle.js
  }

  remove(id) {
    this._removeOne(id);
    var prefix = id + '_';
    var self = this;
    var linked = [];
    this._activeMap.forEach(function(v, k) { if (k !== id && k.indexOf(prefix) === 0) linked.push(k); });
    for (var li = 0; li < linked.length; li++) self._removeOne(linked[li]);
  }

  search(q) {
    q = (q || '').toLowerCase().trim();
    if (!q) return this._catalog;
    return this._catalog.filter(function(e) { return e.id.toLowerCase().indexOf(q) >= 0 || e.name.toLowerCase().indexOf(q) >= 0 || (e.shortName && e.shortName.toLowerCase().indexOf(q) >= 0); });
  }

  setBarData(data) {
    // extracted → indicator-calculator.js
  }

  _pickColor(id, pi) {
    var p = { SMA:'#2962FF', EMA:'#FF9800', WMA:'#00BCD4', HMA:'#00E5FF', DEMA:'#9C27B0', TEMA:'#E91E63', RMA:'#FF5722', LSMA:'#9C27B0', ALMA:'#00BCD4', VWMA:'#FF9800', MCGINLEY:'#4CAF50', RSI:'#E91E63', MACD:'#FF9800', CCI:'#FF9800', ADX:'#FF9800', ATR:'#FF5722', MFI:'#E91E63', OBV:'#4CAF50' };
    if (p[id]) return p[id];
    var c = ['#2962FF','#FF9800','#E91E63','#4CAF50','#00BCD4','#9C27B0','#FF5722','#00E5FF','#FFEB3B','#0ecb81'];
    return c[pi % c.length];
  }

  isVisible(id) { return this._visibleMap.get(id) === true; }
  getCatalog() { return this._catalog; }
  getGroupLabels() { return this._groupLabels; }
  getCategoryOrder() { return this._categoryOrder; }
  getActiveMap() { return this._activeMap; }
  getVisibleMap() { return this._visibleMap; }
  getPatternCount(id) { return this._candlestickCounts[id] || 0; }
}

window.indicatorEngine = new IndicatorEngine();
