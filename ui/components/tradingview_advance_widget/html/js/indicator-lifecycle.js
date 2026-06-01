/**
 * IndicatorEngine lifecycle methods (extracted from indicator-engine.js)
 *
 * handlePythonResult, _hide, _show, _hideOne, _toggleLinked, _removeOne
 *
 * These are attached to IndicatorEngine.prototype and depend on:
 *   - window.chartManager
 *   - This._activeMap, _visibleMap
 *   - Other IndicatorEngine methods (_hideOne, _toggleLinked, _show,
 *     _calculateSMACombo, _calculateEMACombo, _calculateSMAEMACombo,
 *     _calculateCompound, _calculateBaseVolume, _requestPythonFallback,
 *     _resolveAlias, _findCatalogEntry, _calculateAndAdd)
 */

// ========== Python result handler ==========

IndicatorEngine.prototype.handlePythonResult = function(stateId, data, opts) {
  if (!data?.length) return;
  var cm = window.chartManager;
  if (!cm) return;

  // 检查用户是否已要求隐藏（_show 提前设 visibleMap=true，但用户在中途又点击了隐藏）
  var prior = this._visibleMap.get(stateId);
  if (prior === false) {
    console.log('[PYTHON] ' + stateId + ' result ignored (user hid before Python responded)');
    return;
  }

  // 创建或重新创建 series
  if (opts && opts.type === 'histogram') cm.addHistogramSeries(stateId, data, opts);
  else cm.addLineSeries(stateId, data, opts);

  if (prior === undefined) {
    // 首次注册
    var elements = [{ type: 'series', key: stateId }];
    this._activeMap.set(stateId, { params: (opts && opts.params) || {}, group: (opts && opts.group) || 'PYTHON', seriesKeys: [stateId], overlay: !(opts && opts.subChart), elements: elements });
    console.log('[PYTHON] ' + stateId + ' registered with 1 element');
    this._visibleMap.set(stateId, true);

    // 链接关联指标：Yearly_Profile_MID 追加到 Yearly_Profile 的 elements
    if (stateId === 'Yearly_Profile_MID') {
      var parentInfo = this._activeMap.get('Yearly_Profile');
      if (parentInfo) {
        parentInfo.seriesKeys.push(stateId);
        parentInfo.elements.push({ type: 'series', key: stateId });
        console.log('[PYTHON] ' + stateId + ' linked to Yearly_Profile elements');
      }
    }
  } else {
    // 重新显示（hide 后 show 触发的 Python 计算返回）
    var info = this._activeMap.get(stateId);
    if (info) {
      // addLineSeries 已在上面注册了 seriesMap，不需要 delete
      // 更新 elements（保留 chart 上已存在的 series）
      info.seriesKeys = [stateId];
      info.elements = [{ type: 'series', key: stateId }];
      // 重新注册 seriesMap（上面 addLineSeries 已重新创建）
      // 重新链接到父级
      if (stateId === 'Yearly_Profile_MID') {
        var parentInfo = this._activeMap.get('Yearly_Profile');
        if (parentInfo) {
          // 先移除旧的 Yearly_Profile_MID 引用（如果存在）
          parentInfo.seriesKeys = parentInfo.seriesKeys.filter(function(k) { return k !== stateId; });
          parentInfo.elements = parentInfo.elements.filter(function(e) { return e.key !== stateId; });
          parentInfo.seriesKeys.push(stateId);
          parentInfo.elements.push({ type: 'series', key: stateId });
        }
      }
    }
    console.log('[PYTHON] ' + stateId + ' re-shown with new data');
  }
};

// ========== 折叠式显隐控制：show=重建，hide=销毁 ==========

IndicatorEngine.prototype._hide = function(stateId) {
  try {
    var cm = window.chartManager, savedRange = null;
    if (cm?.mainChart) try { savedRange = cm.mainChart.timeScale().getVisibleLogicalRange(); } catch(e) {}
    this._hideOne(stateId);
    // Yearly_Profile 的关联指标已通过 handlePythonResult 追加到 PROFILE 的 elements，不需要 _toggleLinked
    if (stateId !== 'Yearly_Profile') this._toggleLinked(stateId, false);
    if (savedRange && cm?.mainChart) try { cm.mainChart.timeScale().setVisibleLogicalRange(savedRange); } catch(e) {}
    console.log(stateId + ': hidden');
  } catch(e) { console.error(stateId + ': hide error', e); this._visibleMap.set(stateId, false); }
};

IndicatorEngine.prototype._show = function(stateId) {
  try {
    var cm = window.chartManager, savedRange = null;
    if (cm?.mainChart) try { savedRange = cm.mainChart.timeScale().getVisibleLogicalRange(); } catch(e) {}
    // 从 activeMap 读取参数，重新计算渲染（完整重建）
    var info = this._activeMap.get(stateId);
    if (info) {
      // 内置指标的 show 特殊处理
      if (stateId === 'BaseVolume') { this._calculateBaseVolume(stateId); }
      else if (stateId === 'MA_Combo') { this._calculateSMACombo(stateId, info.params); }
      else if (stateId === 'SMA_Combo') { this._calculateSMACombo(stateId, info.params); }
      else if (stateId === 'EMA_Combo') { this._calculateEMACombo(stateId, info.params); }
      else if (stateId === 'SMA_EMA_Combo') { this._calculateSMAEMACombo(stateId, info.params); }
      else if (stateId === 'VolatilitySuite') {
        this._calculateCompound(stateId, [
          { id: 'BollingerBands', params: { length: 20, std: 2 }, color: '#2962FF' },
          { id: 'ATR', params: { length: 14 }, color: '#FF5722' },
        ], 'VOLATILITY');
      }
      else if (stateId === 'TrendFollowSuite') {
        this._calculateCompound(stateId, [
          { id: 'ADX', params: { length: 14 }, color: '#FF9800' },
          { id: 'SuperTrend', params: { length: 10, multiplier: 3 }, color: '#E91E63' },
          { id: 'EMA', params: { length: 50 }, color: '#4CAF50' },
        ], 'TREND');
      }
      else if (stateId === 'MomentumSuite') {
        this._calculateCompound(stateId, [
          { id: 'MACD', params: { fastLength: 12, slowLength: 26, signalLength: 9 }, color: '#FF9800' },
          { id: 'RSI', params: { length: 14 }, color: '#E91E63' },
          { id: 'Stochastic', params: {}, color: '#00BCD4' },
        ], 'MOMENTUM');
      }
      else if (stateId === 'Yearly_Profile') {
        this._requestPythonFallback(stateId, info.params);
        // 清除旧 elements，准备接收 Python 返回
        info.elements = [];
        info.seriesKeys = [];
        // 同步 PROFILE_MID 的 visibleMap——hideOne 之前设为了 false，show 时需恢复
        this._visibleMap.set('Yearly_Profile_MID', true);
        this._visibleMap.set(stateId, true);
        // 不执行 _toggleLinked → PROFILE_MID 由 Python 返回时通过 handlePythonResult 自动加到 PROFILE 的 elements
        if (savedRange && cm?.mainChart) try { cm.mainChart.timeScale().setVisibleLogicalRange(savedRange); } catch(e) {}
        console.log('[SHOW] ' + stateId + ' rebuilt via Python fallback');
        return;
      }
      else {
        var r = this._resolveAlias(stateId, info.params || {});
        var entry = this._findCatalogEntry(r.baseId);
        if (entry) { this._calculateAndAdd(stateId, entry, r.params); }
        else if (this._computeSource === 'auto') {
          this._requestPythonFallback(stateId, info.params);
          // 清除旧 elements（hide 时已销毁，这里准备接收 Python 返回的新 series）
          var info2 = this._activeMap.get(stateId);
          if (info2) info2.elements = [];
          this._visibleMap.set(stateId, true);
        }
      }
    } else { this._visibleMap.set(stateId, true); }
    this._toggleLinked(stateId, true);
    if (savedRange && cm?.mainChart) try { cm.mainChart.timeScale().setVisibleLogicalRange(savedRange); } catch(e) {}
    console.log('[SHOW] ' + stateId + ' rebuilt via _calculateAndAdd');
  } catch(e) { console.error(stateId + ': show error', e); this._visibleMap.set(stateId, true); }
};

/** _hideOne — 遍历本指标的 elements，全部物理销毁（直接操作 primitiveMap/candleSeries） */
IndicatorEngine.prototype._hideOne = function(stateId) {
  var info = this._activeMap.get(stateId);
  if (!info) { this._visibleMap.set(stateId, false); return; }
  var cm = window.chartManager;
  if (!cm) { this._visibleMap.set(stateId, false); return; }
  if (cm._isSyncing !== undefined) cm._isSyncing = true;

  var elements = info.elements || [];
  for (var ei = 0; ei < elements.length; ei++) {
    var el = elements[ei];
    if (el.type === 'series') {
      cm.removeSeries(el.key);
      // 如果该 series key 是另一个 stateId（如 PROFILE_MID），同步其 visibleMap
      if (el.key !== stateId && this._visibleMap.has(el.key)) {
        this._visibleMap.set(el.key, false);
      }
    } else {
      // hline / primitive / fill: 直接从 primitiveMap 查找并物理移除
      var obj = cm.primitiveMap.get(el.key);
      if (!obj) continue;
      if (obj.series && obj.chart) {
        // hline: {series, chart, config}
        try { obj.chart.removeSeries(obj.series); } catch(e) {}
      } else if (obj.parentSeries) {
        // Primitive 附着在子 series 上（如 LineBrPrimitive 在 LineSeries 上）
        try { obj.parentSeries.detachPrimitive(obj.prim); } catch(e) {}
      } else {
        // Primitive 直接附着在 candleSeries 上（如 BgColorPrimitive）
        try { cm.candleSeries.detachPrimitive(obj); } catch(e) {}
      }
      cm.primitiveMap.delete(el.key);
    }
  }
  // 清理 seriesMap 残留
  for (var si = 0; si < info.seriesKeys.length; si++) {
    cm.seriesMap.delete(info.seriesKeys[si]);
  }

  // 清理 markers（通过 stateId 隔离的 ExtendedMarkerPrimitive）
  cm.clearMarkerPrimitive(stateId);

  if (cm._isSyncing !== undefined) cm._isSyncing = false;
  this._visibleMap.set(stateId, false);
  // 强制重绘
  if (cm) {
    try { cm.mainChart.timeScale().fitContent(); } catch(e) {}
    try { cm.subCharts.forEach(function(sub) { sub.chart.timeScale().fitContent(); }); } catch(e) {}
    try { cm.candleSeries.applyOptions({}); } catch(e) {}
  }
  console.log('[HIDE] ' + stateId + ' removed ' + elements.length + ' elements:' + ' (series=' + info.seriesKeys.length + ' extras=' + (elements.length - info.seriesKeys.length) + ')');
  for (var ei = 0; ei < elements.length; ei++) {
    console.log('[HIDE]   ' + stateId + ' → key=' + elements[ei].key + ' type=' + elements[ei].type);
  }
};

IndicatorEngine.prototype._toggleLinked = function(stateId, show) {
  var prefix = stateId + '_';
  var self = this;
  this._activeMap.forEach(function(v, k) {
    if (k !== stateId && k.indexOf(prefix) === 0) {
      if (show) self._show(k);
      else self._hideOne(k);
    }
  });
};

IndicatorEngine.prototype._removeOne = function(id) {
  var info = this._activeMap.get(id);
  var cm = window.chartManager;
  if (info && cm) {
    var elements = info.elements || [];
    for (var ei = 0; ei < elements.length; ei++) {
      var el = elements[ei];
      if (el.type === 'series') {
        cm.removeSeries(el.key);
      } else {
        var obj = cm.primitiveMap.get(el.key);
        if (!obj) continue;
        if (obj.series && obj.chart) { try { obj.chart.removeSeries(obj.series); } catch(e) {} }
        else if (obj.parentSeries) { try { obj.parentSeries.detachPrimitive(obj.prim); } catch(e) {} }
        else { try { cm.candleSeries.detachPrimitive(obj); } catch(e) {} }
        cm.primitiveMap.delete(el.key);
      }
    }
  }
  this._activeMap.delete(id);
  this._visibleMap.delete(id);
};
