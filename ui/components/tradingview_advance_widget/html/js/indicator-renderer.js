/**
 * indicator-renderer.js — IndicatorEngine 渲染方法提取
 *
 * 从 indicator-engine.js 提取 _renderResult 和 _register 方法。
 * 这些方法依赖于运行时存在的 `this._activeMap`、`this._visibleMap`、
 * `window.chartManager`、`window.Primitives` 等。
 */

IndicatorEngine.prototype._renderResult = function(stateId, entry, result, mergedParams) {
    var elements = []; // [{type, series?, prim?, data, opts}] — 本指标的全量元素清单
    var cm = window.chartManager;

    // K 线形态检测计数
    if (entry && entry.category === 'Candlestick Patterns') {
      var bgCount = 0;
      if (result && result.bgColors && result.bgColors.length > 0) bgCount = result.bgColors.length;
      else if (result && result.barColors && result.barColors.length > 0) bgCount = result.barColors.length;
      var markerCount = result && result.markers ? result.markers.length : 0;
      var total = bgCount + markerCount;
      if (total > 0) {
        this._candlestickCounts[stateId] = total;
      } else if (this._candlestickCounts[stateId]) {
        delete this._candlestickCounts[stateId];
      }
    }

    // --- Plots (LineSeries / HistogramSeries / etc.) ---
    if (result && result.plots) {
      var pk = Object.keys(result.plots);
      for (var pi = 0; pi < pk.length; pi++) {
        var pd = result.plots[pk[pi]];
        if (!pd?.length) continue;
        var nanCount = 0;
        for (var ni = 0; ni < pd.length; ni++) { if (pd[ni] == null || pd[ni].value == null || (typeof pd[ni].value === 'number' && !isFinite(pd[ni].value))) nanCount++; }
        if (nanCount === pd.length) { console.log(stateId + ': plot ' + pk[pi] + ' all NaN'); continue; }
        var pc = null;
        for (var pj = 0; pj < (entry.plots || []).length; pj++) { if (entry.plots[pj].id === pk[pi]) { pc = entry.plots[pj]; break; } }
        if (pc && (pc.display === 'none' || pc.visible === false)) continue;
        if (!cm) throw new Error('chartManager not ready');
        var style = (pc?.style) || 'line';
        var color = (pc?.color) || this._pickColor(stateId, pi);
        // MACD 暗色主题配色: 快线=金黄(#FFD700) 慢线=白(#F0F3FA) 柱=保持
        if (stateId === 'MACD') {
          if (pi === 0) color = '#FFD700';
          else if (pi === 1) color = '#F0F3FA';
        }
        var overlay = entry.overlay;
        var opts = { color: color, lineWidth: pc?.lineWidth || 1, visible: true };
        if (!overlay) opts.subChart = true;
        var seriesKey = stateId + '_' + pk[pi];
        try {
          switch (style) {
            case 'line': default:
              cm.addLineSeries(seriesKey, pd, opts);
              elements.push({ type: 'series', key: seriesKey });
              break;
            case 'histogram': case 'columns':
              cm.addHistogramSeries(seriesKey, pd, opts);
              elements.push({ type: 'series', key: seriesKey });
              break;
            case 'area':
              cm.addAreaSeries(seriesKey, pd, opts);
              elements.push({ type: 'series', key: seriesKey });
              break;
            case 'circles':
              cm.setCirclesPlotData(seriesKey, pd, opts);
              elements.push({ type: 'series', key: seriesKey + '_circles' });
              elements.push({ type: 'primitive', key: seriesKey + '_circles' });
              break;
            case 'cross':
              cm.setCrossPlotData(seriesKey, pd, opts);
              elements.push({ type: 'series', key: seriesKey + '_cross' });
              elements.push({ type: 'primitive', key: seriesKey + '_cross' });
              break;
            case 'stepline':
              cm.setSteplineData(seriesKey, pd, opts);
              elements.push({ type: 'series', key: seriesKey + '_step' });
              break;
            case 'linebr':
              cm.setLineBrData(seriesKey, pd, opts);
              elements.push({ type: 'series', key: seriesKey + '_br' });
              elements.push({ type: 'primitive', key: seriesKey + '_linebr' });
              break;
            case 'steplinebr':
              opts.lineType = 'steplinebr'; cm.setLineBrData(seriesKey, pd, opts);
              elements.push({ type: 'series', key: seriesKey + '_br' });
              elements.push({ type: 'primitive', key: seriesKey + '_linebr' });
              break;
          }
        } catch (plotErr) { console.error(stateId + ': plot ' + pk[pi] + ' error', plotErr); }
      }
    }

    // --- Non-plot rendering: hlines, fills, bgColors, lines, labels ---
    if (result && cm) {
      var paneIdx = entry.overlay ? 0 : 1;

      // 对于叠加指标，先清理所有本 stateId 可能残留的 hlines
      if (entry.overlay && cm.primitiveMap) {
        var cleanPrefix = '_hl_' + stateId + '_';
        var cleanKeys = [];
        cm.primitiveMap.forEach(function(v, k) { if (k.indexOf(cleanPrefix) === 0) cleanKeys.push(k); });
        for (var ck = 0; ck < cleanKeys.length; ck++) {
          var old = cm.primitiveMap.get(cleanKeys[ck]);
          if (old && old.series && old.chart) { try { old.chart.removeSeries(old.series); } catch(e) {} }
          cm.primitiveMap.delete(cleanKeys[ck]);
        }
      }

      // hlines: 仅子图指标使用 result.hlines 回退，叠加指标不渲染多余水平线
      var hc = entry.hlineConfig;
      if (!hc && result.hlines && !entry.overlay) hc = Array.isArray(result.hlines) ? result.hlines : (result.hlines?.length ? result.hlines : null);
      if (hc?.length > 0 && this.barData.length > 0) {
        // DEBUG: trace hline source for BollingerBands
        if (stateId.indexOf('BollingerBands') >= 0) {
          console.log('[HLINE_TRACE] ' + stateId + ' hc from=' + (entry.hlineConfig ? 'catalog' : (result.hlines ? 'result' : 'none')) + ' overlay=' + entry.overlay + ' count=' + hc.length);
          for (var _ht = 0; _ht < hc.length; _ht++) { console.log('[HLINE_TRACE]   val=' + (hc[_ht].price || hc[_ht].value || 0)); }
        }
        try {
          var hOpts = [];
          for (var hi = 0; hi < hc.length; hi++) {
            var h = hc[hi]; hOpts.push({ price: h.price || h.value || 0, color: h.color || '#787b86', lineStyle: h.linestyle || h.lineStyle || 'solid', lineWidth: h.lineWidth || 1, label: h.title || h.label || '' });
            elements.push({ type: 'hline', key: '_hl_' + stateId + '_' + paneIdx + '_' + hi });
          }
          cm.setHLines(hOpts, paneIdx, this.barData, stateId);
        } catch (e) { console.error(stateId + ': hline error', e); }
      }

      // fills — 只有当 setPlotFills 成功创建了 data 后才 push element
      if (result.fills?.length > 0) {
        try {
          var fillCount = 0;
          for (var fi = 0; fi < result.fills.length; fi++) {
            var fill = result.fills[fi];
            var fKey = '_fill_' + stateId + '_' + paneIdx + '_' + fi;
            // 检查是否有有效数据
            if (fill.top && fill.bottom && result.plots && result.plots[fill.top] && result.plots[fill.bottom]) {
              fillCount++;
              elements.push({ type: 'fill', key: fKey });
            }
          }
          if (fillCount > 0) cm.setPlotFills(result.fills, result.plots, paneIdx, stateId);
        } catch (e) { console.error(stateId + ': fills error', e); }
      }

      // 通用 bar/bgColors 处理: 遍历所有可能返回颜色数据的字段
      // K 线形态指标打印原始数据
      if (entry.category === 'Candlestick Patterns' && result) {
        if (result.barColors && result.barColors.length > 0) {
          console.log('[CANDLESTICK] ' + stateId + ' barColors(' + result.barColors.length + '):', JSON.stringify(result.barColors.slice(0, 10)));
        } else if (result.bgColors && result.bgColors.length > 0) {
          console.log('[CANDLESTICK] ' + stateId + ' bgColors(' + result.bgColors.length + '):', JSON.stringify(result.bgColors.slice(0, 10)));
        } else {
          console.log('[CANDLESTICK] ' + stateId + ' bgColors=[] (empty)');
        }
        if (result.markers && result.markers.length > 0) {
          console.log('[CANDLESTICK] ' + stateId + ' markers(' + result.markers.length + '):', JSON.stringify(result.markers.slice(0, 10)));
        }
      }
      var colorSources = [];
      if (result.barColors) colorSources.push({ name: 'barColors', data: result.barColors });
      if (result.bgColors) colorSources.push({ name: 'bgColors', data: result.bgColors });
      for (var ci = 0; ci < colorSources.length; ci++) {
        var src = colorSources[ci];
        if (src.data && src.data.length > 0) {
          try {
            var mapped = Array.isArray(src.data) ? src.data : Object.values(src.data);
            cm.setBgColors(mapped.map(function(bc) { return { time: bc.time, color: bc.color, alpha: bc.alpha !== undefined ? bc.alpha : 0.35 }; }), paneIdx, stateId);
            elements.push({ type: 'primitive', key: '_bgcolor_' + stateId + '_' + paneIdx });
            break;  // 只取第一个有效的数据源
          } catch (e) { console.error(stateId + ': ' + src.name + ' error', e); }
        }
      }

      // lines (ZigZag等)
      if (result.lines?.length > 0) {
        try {
          cm.setLineDrawings(result.lines, paneIdx, stateId);
          elements.push({ type: 'primitive', key: '_lines_draw_' + stateId + '_' + paneIdx });
          console.log(stateId + ': ' + result.lines.length + ' line(s)');
        } catch (e) { console.error(stateId + ': lines error', e); }
      }

      // labels (ZigZag等)
      if (result.labels?.length > 0) {
        try {
          cm.setLabels(result.labels, paneIdx, stateId);
          elements.push({ type: 'primitive', key: '_labels_' + stateId + '_' + paneIdx });
          console.log(stateId + ': ' + result.labels.length + ' label(s)');
        } catch (e) { console.error(stateId + ': labels error', e); }
      }

      // markers — K线形态等的箭头标记（通过 stateId 隔离）
      if (result.markers?.length > 0) {
        try {
          // 确保每个 marker 有完整格式
          var validMarkers = [];
          for (var mi = 0; mi < result.markers.length; mi++) {
            var m = result.markers[mi];
            if (m && m.time) {
              validMarkers.push({
                time: m.time,
                position: m.position || 'aboveBar',
                shape: m.shape || 'arrowUp',
                color: m.color || '#2962FF',
                text: m.text || ''
              });
            }
          }
          if (validMarkers.length > 0) {
            cm.setMarkerPrimitive(validMarkers, stateId);
            elements.push({ type: 'primitive', key: '_marker_' + stateId });
          }
        } catch (e) { console.error(stateId + ': markers error', e); }
      }
    }

    // 提取所有 seriesKeys
    var seriesKeys = [];
    for (var ei = 0; ei < elements.length; ei++) {
      if (elements[ei].type === 'series') seriesKeys.push(elements[ei].key);
    }

    this._activeMap.set(stateId, { params: mergedParams, group: entry.category, seriesKeys: seriesKeys, overlay: entry.overlay, elements: elements });
    this._visibleMap.set(stateId, true);
    // 强制 LC 重绘：fitContent + requestUpdate
    if (cm) {
      try { cm.mainChart.timeScale().fitContent(); } catch(e) {}
      try { 
        cm.subCharts.forEach(function(sub) { sub.chart.timeScale().fitContent(); });
      } catch(e) {}
      // 触发 candleSeries 刷新 - 如果有 primitives 需要重新绘制
      try { cm.candleSeries.applyOptions({}); } catch(e) {}
    }
    console.log('[RENDER] ' + stateId + ' created ' + seriesKeys.length + ' series + ' + (elements.length - seriesKeys.length) + ' extras');
    for (var ei = 0; ei < elements.length; ei++) {
      console.log('[RENDER]   ' + stateId + ' → element[' + ei + '] type=' + elements[ei].type + ' key=' + elements[ei].key);
    }
};

IndicatorEngine.prototype._register = function(stateId, params, group, seriesKeys, overlay, elements) {
    overlay = overlay !== false;
    elements = elements || [];
    for (var ei = 0; ei < (seriesKeys || []).length; ei++) {
      // 自动为每个 seriesKey 创建对应的 element
      var found = false;
      for (var ej = 0; ej < elements.length; ej++) { if (elements[ej].key === seriesKeys[ei]) { found = true; break; } }
      if (!found) elements.push({ type: 'series', key: seriesKeys[ei] });
    }
    this._activeMap.set(stateId, { params: params, group: group, seriesKeys: seriesKeys || [], overlay: overlay, elements: elements });
    console.log('[REGISTER] ' + stateId + ' -> ' + elements.length + ' elements');
    for (var ek = 0; ek < elements.length; ek++) {
      console.log('[REGISTER]   ' + stateId + ' → element[' + ek + '] type=' + elements[ek].type + ' key=' + elements[ek].key);
    }
    this._visibleMap.set(stateId, true);
};
