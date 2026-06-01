/**
 * indicator-calculator.js — 计算和组合指标方法集合
 *
 * 从 indicator-engine.js 提取的所有数学计算、组合指标、复合渲染相关方法。
 * 以 prototype 扩展方式挂载到 IndicatorEngine 类上。
 *
 * 提取方法：
 *   _calculateBaseVolume
 *   _calculateSMACombo / _calculateEMACombo / _calculateSMAEMACombo
 *   _calculateCompound
 *   _calcSMA
 *   calculateAndAdd / _calculateAndAdd
 *   setBarData
 *
 * indicator-engine.js 中的对内引用（_resolveAlias, _findCatalogEntry,
 * _renderResult, _register, _requestPythonFallback, _hide 等）保持为 this.xxx 调用，
 * 因为这些方法仍留在主文件中。
 */

/* === _calculateBaseVolume — 基础成交量柱状图 === */
IndicatorEngine.prototype._calculateBaseVolume = function(id) {
  if (!this.barData?.length) return;
  var data = [];
  for (var i = 0; i < this.barData.length; i++) {
    var bar = this.barData[i];
    if (bar.volume === undefined) continue;
    data.push({ time: bar.time, value: bar.volume, color: bar.close >= bar.open ? '#0ecb81' : '#f6465d' });
  }
  if (!data.length) return;
  var cm = window.chartManager;
  if (!cm) return;
  cm.addHistogramSeries(id, data, { subChart: true, color: '#0ecb81', priceFormat: { type: 'volume' }, scaleMargins: { top: 0.8, bottom: 0 }, priceScaleId: 'base_vol_scale' });
  this._register(id, {}, 'VOLUME', [id]);
  console.log('BaseVolume: ' + data.length + ' bars');
};

/* === _calculateSMACombo — SMA组合：6个可配置周期，周期=0时不显示 === */
IndicatorEngine.prototype._calculateSMACombo = function(id, params) {
  if (!this.barData?.length) return;
  params = params || {};
  var periods = [
    params.p1 || 0, params.p2 || 0, params.p3 || 0,
    params.p4 || 0, params.p5 || 0, params.p6 || 0,
  ];
  var colors = ['#2962FF', '#FF9800', '#E91E63', '#4CAF50', '#00BCD4', '#9C27B0'];
  var keys = [], cm = window.chartManager;
  if (!cm) return;
  for (var i = 0; i < periods.length; i++) {
    var l = periods[i];
    if (l <= 0) continue;
    var data = this._calcSMA(this.barData, l, true);
    if (data?.length) {
      var key = id + '_SMA' + l;
      cm.addLineSeries(key, data, { color: colors[i % colors.length], lineWidth: 2 });
      keys.push(key);
    }
  }
  this._register(id, params || {}, 'MOVING AVERAGES', keys);
  console.log('SMA_Combo: ' + keys.length + ' lines from [' + periods.join(',') + ']');
};

/* === _calculateEMACombo — EMA组合：6个可配置周期，周期=0时不显示 === */
IndicatorEngine.prototype._calculateEMACombo = function(id, params) {
  if (!this.barData?.length) return;
  params = params || {};
  var periods = [
    params.p1 || 0, params.p2 || 0, params.p3 || 0,
    params.p4 || 0, params.p5 || 0, params.p6 || 0,
  ];
  var colors = ['#FF9800', '#E91E63', '#4CAF50', '#00BCD4', '#9C27B0', '#FF5722'];
  var keys = [], cm = window.chartManager;
  if (!cm) return;
  for (var i = 0; i < periods.length; i++) {
    var l = periods[i];
    if (l <= 0) continue;
    var data = this._calcSMA(this.barData, l, false);
    if (data?.length) {
      var key = id + '_EMA' + l;
      cm.addLineSeries(key, data, { color: colors[i % colors.length], lineWidth: 2 });
      keys.push(key);
    }
  }
  this._register(id, params || {}, 'MOVING AVERAGES', keys);
  console.log('EMA_Combo: ' + keys.length + ' lines from [' + periods.join(',') + ']');
};

/* === _calculateSMAEMACombo — SMA+EMA组合：前3=SMA，后3=EMA，周期=0时不显示 === */
IndicatorEngine.prototype._calculateSMAEMACombo = function(id, params) {
  if (!this.barData?.length) return;
  params = params || {};
  var smaPeriods = [params.p1 || 0, params.p2 || 0, params.p3 || 0];
  var emaPeriods = [params.p4 || 0, params.p5 || 0, params.p6 || 0];
  var smaColors = ['#2962FF', '#FF9800', '#E91E63'];
  var emaColors = ['#4CAF50', '#00BCD4', '#9C27B0'];
  var keys = [], cm = window.chartManager;
  if (!cm) return;
  for (var i = 0; i < smaPeriods.length; i++) {
    var l = smaPeriods[i];
    if (l <= 0) continue;
    var data = this._calcSMA(this.barData, l, true);
    if (data?.length) {
      var key = id + '_SMA' + l;
      cm.addLineSeries(key, data, { color: smaColors[i], lineWidth: 2 });
      keys.push(key);
    }
  }
  for (var i = 0; i < emaPeriods.length; i++) {
    var l = emaPeriods[i];
    if (l <= 0) continue;
    var data = this._calcSMA(this.barData, l, false);
    if (data?.length) {
      var key = id + '_EMA' + l;
      cm.addLineSeries(key, data, { color: emaColors[i], lineWidth: 2 });
      keys.push(key);
    }
  }
  this._register(id, params || {}, 'MOVING AVERAGES', keys);
  console.log('SMA_EMA_Combo: ' + keys.length + ' lines');
};

/**
 * _calculateCompound — 复合指标渲染器
 * 将多个子指标的计算结果渲染到同一个 stateId 下，确保预设与独立指标互不干扰。
 * 每个子指标创建独立的 series/primitive，通过前缀 key 隔离。
 */
IndicatorEngine.prototype._calculateCompound = function(suiteId, subIndicators, suiteGroup) {
  if (!this.barData?.length) { console.warn('[COMPOUND] ' + suiteId + ': no bar data'); return; }
  var cm = window.chartManager;
  if (!cm) { console.warn('[COMPOUND] ' + suiteId + ': chartManager not ready'); return; }

  var allElements = [], allSeriesKeys = [];
  for (var si = 0; si < subIndicators.length; si++) {
    var sub = subIndicators[si];
    var r = this._resolveAlias(sub.id, sub.params || {});
    var entry = this._findCatalogEntry(r.baseId);
    // Fallback to LCI direct key
    if (!entry && this._indicators && this._indicators[r.baseId] && this._indicators[r.baseId].calculate) {
      var lciFn = this._indicators[r.baseId];
      entry = { id: r.baseId, name: (lciFn.metadata && lciFn.metadata.title) || r.baseId,
        shortName: (lciFn.metadata && lciFn.metadata.shortTitle) || r.baseId,
        overlay: lciFn.metadata ? lciFn.metadata.overlay !== false : true,
        inputs: lciFn.inputConfig || [], plots: lciFn.plotConfig || [],
        defaults: lciFn.defaultInputs || {}, hlineConfig: lciFn.hlineConfig || null,
        fillConfig: lciFn.fillConfig || null, calculate: lciFn.calculate };
      console.log('[COMPOUND] ' + suiteId + ': sub ' + sub.id + ' from LCI direct key');
    }
    if (!entry) { console.warn('[COMPOUND] ' + suiteId + ': sub ' + sub.id + ' not found'); continue; }

    // Merge defaults with request params
    var mp = {};
    for (var k in entry.defaults) if (entry.defaults.hasOwnProperty(k)) mp[k] = entry.defaults[k];
    for (var k2 in r.params) if (r.params.hasOwnProperty(k2)) mp[k2] = r.params[k2];

    try {
      var result = entry.calculate(this.barData, mp);
      if (!result) { console.log('[COMPOUND] ' + suiteId + ': sub ' + sub.id + ' returned null'); continue; }

      // === Plots ===
      if (result.plots) {
        var pk = Object.keys(result.plots);
        for (var pi = 0; pi < pk.length; pi++) {
          var pd = result.plots[pk[pi]];
          if (!pd?.length) continue;
          // NaN filter
          var nanCount = 0;
          for (var ni = 0; ni < pd.length; ni++) {
            if (pd[ni] == null || pd[ni].value == null || (typeof pd[ni].value === 'number' && !isFinite(pd[ni].value))) nanCount++;
          }
          if (nanCount === pd.length) continue;

          var pc = null;
          for (var pj = 0; pj < (entry.plots || []).length; pj++) {
            if (entry.plots[pj].id === pk[pi]) { pc = entry.plots[pj]; break; }
          }
          if (pc && (pc.display === 'none' || pc.visible === false)) continue;

          var style = (pc?.style) || 'line';
          var color = sub.color || '#2962FF';
          var overlay = entry.overlay;
          var opts = { color: color, lineWidth: pc?.lineWidth || 1, visible: true, autoscaleInfoProvider: function() { return null; } };
          if (!overlay) opts.subChart = true;

          var seriesKey = suiteId + '_' + sub.id + '_' + pk[pi];
          try {
            switch (style) {
              case 'line': default:
                cm.addLineSeries(seriesKey, pd, opts);
                allElements.push({ type: 'series', key: seriesKey });
                break;
              case 'histogram': case 'columns':
                cm.addHistogramSeries(seriesKey, pd, opts);
                allElements.push({ type: 'series', key: seriesKey });
                break;
              case 'area':
                cm.addAreaSeries(seriesKey, pd, opts);
                allElements.push({ type: 'series', key: seriesKey });
                break;
              case 'circles':
                cm.setCirclesPlotData(seriesKey, pd, opts);
                allElements.push({ type: 'series', key: seriesKey + '_circles' });
                allElements.push({ type: 'primitive', key: seriesKey + '_circles' });
                break;
              case 'cross':
                cm.setCrossPlotData(seriesKey, pd, opts);
                allElements.push({ type: 'series', key: seriesKey + '_cross' });
                allElements.push({ type: 'primitive', key: seriesKey + '_cross' });
                break;
              case 'stepline':
                cm.setSteplineData(seriesKey, pd, opts);
                allElements.push({ type: 'series', key: seriesKey + '_step' });
                break;
              case 'linebr':
                cm.setLineBrData(seriesKey, pd, opts);
                allElements.push({ type: 'series', key: seriesKey + '_br' });
                allElements.push({ type: 'primitive', key: seriesKey + '_linebr' });
                break;
              case 'steplinebr':
                opts.lineType = 'steplinebr'; cm.setLineBrData(seriesKey, pd, opts);
                allElements.push({ type: 'series', key: seriesKey + '_br' });
                allElements.push({ type: 'primitive', key: seriesKey + '_linebr' });
                break;
            }
            allSeriesKeys.push(seriesKey);
          } catch (plotErr) {
            console.error('[COMPOUND] ' + suiteId + ': sub ' + sub.id + ' plot ' + pk[pi] + ' error', plotErr);
          }
        }
      }

      // === Fills (BollingerBands 等) ===
      if (result.fills?.length > 0) {
        var paneIdx = entry.overlay ? 0 : 1;
        var fillCount = 0;
        for (var fi = 0; fi < result.fills.length; fi++) {
          var fill = result.fills[fi];
          var fKey = '_fill_' + suiteId + '_' + sub.id + '_' + paneIdx + '_' + fi;
          if (fill.top && fill.bottom && result.plots && result.plots[fill.top] && result.plots[fill.bottom]) {
            fillCount++;
            allElements.push({ type: 'fill', key: fKey });
          }
        }
        if (fillCount > 0) {
          try { cm.setPlotFills(result.fills, result.plots, paneIdx, suiteId + '_' + sub.id); } catch (e) { console.error('[COMPOUND] ' + suiteId + ': fills error', e); }
        }
      }

      // === Hlines（仅非叠加指标渲染）===
      if (result.hlines?.length > 0 && !entry.overlay && this.barData.length > 0) {
        // DEBUG: trace hline source for BollingerBands compound
        if (suiteId.indexOf('BollingerBands') >= 0 || sub.id.indexOf('BollingerBands') >= 0) {
          console.log('[HLINE_COMPOUND] ' + suiteId + ' sub=' + sub.id + ' overlay=' + entry.overlay + ' hlines=' + result.hlines.length);
        }
        try {
          var paneIdx2 = entry.overlay ? 0 : 1;
          var hOpts = [];
          for (var hi = 0; hi < result.hlines.length; hi++) {
            var h = result.hlines[hi];
            hOpts.push({ price: h.price || h.value || 0, color: h.color || '#787b86', lineStyle: h.linestyle || h.lineStyle || 'solid', lineWidth: h.lineWidth || 1, label: h.title || h.label || '' });
            allElements.push({ type: 'hline', key: '_hl_' + suiteId + '_' + sub.id + '_' + paneIdx2 + '_' + hi });
          }
          cm.setHLines(hOpts, paneIdx2, this.barData, suiteId + '_' + sub.id);
        } catch (e) { console.error('[COMPOUND] ' + suiteId + ': hline error', e); }
      }

      // === barColors ===
      if (result.barColors?.length > 0) {
        try {
          cm.setBgColors(result.barColors.map(function(bc) { return { time: bc.time, color: bc.color, alpha: bc.alpha !== undefined ? bc.alpha : 0.35 }; }), entry.overlay ? 0 : 1, suiteId + '_' + sub.id);
          allElements.push({ type: 'primitive', key: '_bgcolor_' + suiteId + '_' + sub.id + '_' + (entry.overlay ? 0 : 1) });
        } catch (e) { console.error('[COMPOUND] ' + suiteId + ': barColors error', e); }
      }

      // === bgColors ===
      if (result.bgColors?.length > 0) {
        try {
          cm.setBgColors(result.bgColors, entry.overlay ? 0 : 1, suiteId + '_' + sub.id);
          allElements.push({ type: 'primitive', key: '_bgcolor_' + suiteId + '_' + sub.id + '_' + (entry.overlay ? 0 : 1) });
        } catch (e) { console.error('[COMPOUND] ' + suiteId + ': bgColors error', e); }
      }

      // === lines (drawings) ===
      if (result.lines?.length > 0) {
        try {
          cm.setLineDrawings(result.lines, entry.overlay ? 0 : 1, suiteId + '_' + sub.id);
          allElements.push({ type: 'primitive', key: '_lines_draw_' + suiteId + '_' + sub.id + '_' + (entry.overlay ? 0 : 1) });
        } catch (e) { console.error('[COMPOUND] ' + suiteId + ': lines error', e); }
      }

      // === labels ===
      if (result.labels?.length > 0) {
        try {
          cm.setLabels(result.labels, entry.overlay ? 0 : 1, suiteId + '_' + sub.id);
          allElements.push({ type: 'primitive', key: '_labels_' + suiteId + '_' + sub.id + '_' + (entry.overlay ? 0 : 1) });
        } catch (e) { console.error('[COMPOUND] ' + suiteId + ': labels error', e); }
      }

      console.log('[COMPOUND] ' + suiteId + ': sub ' + sub.id + ' -> ' + pk.length + ' plot(s)');
    } catch (e) {
      console.error('[COMPOUND] ' + suiteId + ': sub ' + sub.id + ' error', e);
    }
  }

  if (allElements.length > 0) {
    // Determine overlay: true if ALL sub-indicators are overlays, false if any is subchart
    var allOverlay = true;
    for (var si2 = 0; si2 < subIndicators.length; si2++) {
      var r2 = this._resolveAlias(subIndicators[si2].id, subIndicators[si2].params || {});
      var e2 = this._findCatalogEntry(r2.baseId);
      if (e2 && !e2.overlay) { allOverlay = false; break; }
    }
    this._register(suiteId, {}, suiteGroup || 'Suite', allSeriesKeys, allOverlay, allElements);
    // Force price scale auto-scaling + time fit
    if (cm) {
      try { cm.mainChart.timeScale().fitContent(); } catch(e) {}
      try {
        // Explicitly trigger price scale auto-scale recalculation
        cm.mainChart.priceScale('right').applyOptions({ autoScale: true });
      } catch(e) {}
      try { cm.subCharts.forEach(function(sub) {
        sub.chart.timeScale().fitContent();
        try { sub.chart.priceScale('right').applyOptions({ autoScale: true }); } catch(e2) {}
      }); } catch(e) {}
      try { cm.candleSeries.applyOptions({}); } catch(e) {}
    }
    console.log('[COMPOUND] ' + suiteId + ' created ' + allSeriesKeys.length + ' series across ' + subIndicators.length + ' sub-indicators (' + allElements.length + ' total elements)');
  } else {
    console.warn('[COMPOUND] ' + suiteId + ': no elements created');
  }
};

/* === _calcSMA — SMA/EMA 核心计算 === */
IndicatorEngine.prototype._calcSMA = function(data, length, isSMA) {
  if (!data || data.length < length) return [];
  var result = [];
  for (var i = 0; i < data.length; i++) {
    if (i < length - 1) {
      // 前导期不推送任何数据（匹配 LCI 内置 SMA 行为，避免 null 值引发渲染差异）
      continue;
    }
    if (isSMA) {
      var sum = 0, validCount = 0;
      for (var j = i - length + 1; j <= i; j++) {
        if (data[j].close != null && isFinite(data[j].close)) { sum += data[j].close; validCount++; }
      }
      var smaVal = validCount > 0 ? sum / validCount : null;
      if (smaVal !== null && smaVal !== 0 && isFinite(smaVal)) {
        result.push({ time: data[i].time, value: smaVal });
      }
    } else {
      var m = 2 / (length + 1);
      if (i === length - 1) {
        var s = 0, vc = 0;
        for (var j2 = i - length + 1; j2 <= i; j2++) {
          if (data[j2].close != null && isFinite(data[j2].close)) { s += data[j2].close; vc++; }
        }
        var seedVal = vc > 0 ? s / vc : null;
        if (seedVal !== null && seedVal !== 0 && isFinite(seedVal)) {
          result.push({ time: data[i].time, value: seedVal });
        }
      }
      else {
        var prev = result.length > 0 ? result[result.length - 1].value : null;
        if (prev !== null && prev !== 0 && isFinite(prev)) {
          var close = data[i].close;
          if (close != null && isFinite(close) && close !== 0) {
            result.push({ time: data[i].time, value: close * m + prev * (1 - m) });
          }
        }
      }
    }
  }
  return result;
};

/* === calculateAndAdd — 外部入口：解析+计算+渲染+注册 === */
IndicatorEngine.prototype.calculateAndAdd = function(stateId, params) {
  params = params || {};
  // 组合指标走专用计算函数
  if (stateId === 'SMA_Combo' || stateId === 'MA_Combo') { this._calculateSMACombo(stateId, params); return; }
  if (stateId === 'EMA_Combo') { this._calculateEMACombo(stateId, params); return; }
  if (stateId === 'SMA_EMA_Combo') { this._calculateSMAEMACombo(stateId, params); return; }
  var r = this._resolveAlias(stateId, params);
  var entry = this._findCatalogEntry(r.baseId);
  // Fallback to LCI direct key if catalog lookup fails
  if (!entry && this._indicators && this._indicators[r.baseId] && this._indicators[r.baseId].calculate) {
    var lciFn = this._indicators[r.baseId];
    entry = { id: r.baseId, name: (lciFn.metadata && lciFn.metadata.title) || r.baseId,
      shortName: (lciFn.metadata && lciFn.metadata.shortTitle) || r.baseId,
      overlay: lciFn.metadata ? lciFn.metadata.overlay !== false : true,
      inputs: lciFn.inputConfig || [], plots: lciFn.plotConfig || [],
      defaults: lciFn.defaultInputs || {}, hlineConfig: lciFn.hlineConfig || null,
      fillConfig: lciFn.fillConfig || null, calculate: lciFn.calculate };
  }
  if (entry) this._calculateAndAdd(stateId, entry, r.params);
  else if (this._computeSource === 'auto') this._requestPythonFallback(r.id, r.params);
};

/** _calculateAndAdd — 计算+渲染+注册，所有图形元素存储在本指标单位内 */
IndicatorEngine.prototype._calculateAndAdd = function(stateId, entry, params) {
  if (!entry || !this.barData?.length) { console.warn('Cannot calc ' + stateId); return; }
  // Verify catalog entry against authoritative LCI direct key
  if (this._indicators && this._indicators[stateId] && this._indicators[stateId].calculate &&
      this._indicators[stateId].calculate !== entry.calculate) {
    var lciFn = this._indicators[stateId];
    console.warn('[FIX] ' + stateId + ': catalog entry mismatch (calculate differs from LCI direct key)');
    entry.calculate = lciFn.calculate;
    entry.plotConfig = lciFn.plotConfig || entry.plotConfig;
    entry.inputConfig = lciFn.inputConfig || entry.inputConfig;
    entry.defaults = lciFn.defaultInputs || entry.defaults;
    entry.hlineConfig = lciFn.hlineConfig || entry.hlineConfig;
    entry.fillConfig = lciFn.fillConfig || entry.fillConfig;
    if (lciFn.metadata && lciFn.metadata.overlay !== undefined) entry.overlay = lciFn.metadata.overlay;
  }
  var mp = {};
  for (var k in entry.defaults) if (entry.defaults.hasOwnProperty(k)) mp[k] = entry.defaults[k];
  for (var k2 in params) if (params.hasOwnProperty(k2)) mp[k2] = params[k2];
  try {
    var result = entry.calculate(this.barData, mp);
    var plotKeys = result && result.plots ? Object.keys(result.plots) : [];
    console.log('[CALC] ' + stateId + ' calculate returned: plots=' + JSON.stringify(plotKeys) + ' hasLines=' + !!(result && result.lines) + ' hasLabels=' + !!(result && result.labels) + ' hasBgColors=' + !!(result && result.bgColors) + ' hasHlines=' + !!(result && result.hlines));
    // DEBUG: trace all plot data ranges
    if (result && result.plots) {
      for (var dk = 0; dk < plotKeys.length; dk++) {
        var pd = result.plots[plotKeys[dk]];
        if (pd && pd.length > 0) {
          var validVals = [];
          for (var dv = 0; dv < pd.length; dv++) {
            if (pd[dv] && pd[dv].value != null && typeof pd[dv].value === 'number' && isFinite(pd[dv].value)) validVals.push(pd[dv].value);
          }
          if (validVals.length > 0) {
            var dmin = Math.min.apply(null, validVals), dmax = Math.max.apply(null, validVals);
            console.log('[TRACE] ' + stateId + ' plot[' + plotKeys[dk] + '] valid=' + validVals.length + ' min=' + dmin.toFixed(4) + ' max=' + dmax.toFixed(4));
          } else {
            console.log('[TRACE] ' + stateId + ' plot[' + plotKeys[dk] + '] ALL NaN/Infinity');
          }
        }
      }
    }
    // DEBUG: trace hlines config source
    var hc = entry.hlineConfig;
    if (!hc && result && result.hlines) hc = Array.isArray(result.hlines) ? result.hlines : (result.hlines?.length ? result.hlines : null);
    if (hc && hc.length > 0) {
      console.log('[TRACE] ' + stateId + ' hlines source=' + (entry.hlineConfig ? 'catalog' : 'result') + ' count=' + hc.length + ' values=' + JSON.stringify(hc.map(function(h){return h.price || h.value || 0;})));
    }
    // Also trace catalog entry info
    console.log('[TRACE] ' + stateId + ' catalog: overlay=' + entry.overlay + ' plots=' + (entry.plots ? entry.plots.length : 0) + ' hlineConfig=' + (entry.hlineConfig ? entry.hlineConfig.length : 0) + ' fillConfig=' + !!entry.fillConfig + ' calculate=' + (entry.calculate ? 'yes' : 'no'));
    if (!result) { console.log('[CALC] ' + stateId + ': calculate returned null, skipping'); return; }

    // --- Data auto-scaling: if hlines far exceed data range, scale data up ---
    // (e.g. BB%B returns 0-1 but hlines are at 100/-100 — scale data x100)
    if (result && result.plots) {
      var allPlotVals = [];
      var pkArr = Object.keys(result.plots);
      for (var _pi = 0; _pi < pkArr.length; _pi++) {
        var _pd = result.plots[pkArr[_pi]];
        if (_pd && _pd.length) {
          for (var _di = 0; _di < _pd.length; _di++) {
            if (_pd[_di] && _pd[_di].value != null && typeof _pd[_di].value === 'number' && isFinite(_pd[_di].value)) allPlotVals.push(_pd[_di].value);
          }
        }
      }
      if (allPlotVals.length > 0) {
        var pMin = Math.min.apply(null, allPlotVals);
        var pMax = Math.max.apply(null, allPlotVals);
        var pRange = pMax - pMin;
        // Check hlines for scale mismatch
        var hcCheck = entry.hlineConfig;
        var hMin = Infinity, hMax = -Infinity;
        if (hcCheck && hcCheck.length > 0) {
          for (var _hi = 0; _hi < hcCheck.length; _hi++) {
            var hp = hcCheck[_hi].price || hcCheck[_hi].value || 0;
            if (hp < hMin) hMin = hp;
            if (hp > hMax) hMax = hp;
          }
          var hRange = hMax - hMin;
          // If hline range is 10x+ larger than data range, scale data up
          if (pRange > 0 && hRange > 0 && hRange / pRange >= 10) {
            var scaleFactor = hRange / pRange;
            // Round to nearest power of 10 (10, 100, 1000...)
            var magnitude = Math.pow(10, Math.round(Math.log10(scaleFactor)));
            if (magnitude >= 10 && magnitude <= 100000) {
              for (var _pi2 = 0; _pi2 < pkArr.length; _pi2++) {
                var _pd2 = result.plots[pkArr[_pi2]];
                if (_pd2 && _pd2.length) {
                  for (var _di2 = 0; _di2 < _pd2.length; _di2++) {
                    if (_pd2[_di2] && _pd2[_di2].value != null && typeof _pd2[_di2].value === 'number' && isFinite(_pd2[_di2].value)) {
                      _pd2[_di2].value *= magnitude;
                    }
                  }
                }
              }
              console.log('[SCALE] ' + stateId + ': auto-scaled data x' + magnitude + ' (plineRange=' + pRange.toFixed(2) + ' hlineRange=' + hRange + ')');
            }
          }
        }
      }
    }

    this._renderResult(stateId, entry, result, mp);
  } catch (e) {
    console.error('Indicator failed: ' + stateId, e);
    if (this._computeSource === 'auto') this._requestPythonFallback(stateId, params);
  }
};

/* === setBarData — 数据更新时重建所有激活指标 === */
IndicatorEngine.prototype.setBarData = function(data) {
  this.barData = data;
  var self = this;
  this._activeMap.forEach(function(info, sid) {
    var r = self._resolveAlias(sid, info.params);
    // 销毁旧元素
    var cm = window.chartManager;
    var elements = info.elements || [];
    if (cm) for (var ei = 0; ei < elements.length; ei++) {
      var el = elements[ei];
      if (el.type === 'series') cm.removeSeries(el.key);
      else cm.setExtraKeyVisible(el.key, false);
    }
    var wv = self._visibleMap.get(sid) || false;
    self._activeMap.delete(sid);
    self._visibleMap.delete(sid);
    var entry = self._findCatalogEntry(r.baseId);
    if (entry) {
      self._calculateAndAdd(sid, entry, r.params);
      if (!wv) self._hide(sid);
    } else if (sid === 'MA_Combo') {
      self._calculateSMACombo(sid, info.params);
      if (!wv) self._hide(sid);
    } else if (sid === 'SMA_Combo') {
      self._calculateSMACombo(sid, info.params);
      if (!wv) self._hide(sid);
    } else if (sid === 'EMA_Combo') {
      self._calculateEMACombo(sid, info.params);
      if (!wv) self._hide(sid);
    } else if (sid === 'SMA_EMA_Combo') {
      self._calculateSMAEMACombo(sid, info.params);
      if (!wv) self._hide(sid);
    } else if (sid === 'BaseVolume') {
      self._calculateBaseVolume(sid);
      if (!wv) self._hide(sid);
    } else if (sid === 'VolatilitySuite') {
      self._calculateCompound(sid, [
        { id: 'BollingerBands', params: { length: 20, std: 2 }, color: '#2962FF' },
        { id: 'ATR', params: { length: 14 }, color: '#FF5722' },
      ], 'VOLATILITY');
      if (!wv) self._hide(sid);
    } else if (sid === 'TrendFollowSuite') {
      self._calculateCompound(sid, [
        { id: 'ADX', params: { length: 14 }, color: '#FF9800' },
        { id: 'SuperTrend', params: { length: 10, multiplier: 3 }, color: '#E91E63' },
        { id: 'EMA', params: { length: 50 }, color: '#4CAF50' },
      ], 'TREND');
      if (!wv) self._hide(sid);
    } else if (sid === 'MomentumSuite') {
      self._calculateCompound(sid, [
        { id: 'MACD', params: { fastLength: 12, slowLength: 26, signalLength: 9 }, color: '#FF9800' },
        { id: 'RSI', params: { length: 14 }, color: '#E91E63' },
        { id: 'Stochastic', params: {}, color: '#00BCD4' },
      ], 'MOMENTUM');
      if (!wv) self._hide(sid);
    }
  });
};
