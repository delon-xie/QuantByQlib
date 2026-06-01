/**
 * ChartManager - 图表生命周期管理 (LightweightCharts v5.2 API)。
 * 使用 chart.addSeries(Type, opts) 统一 API。
 * 管理主图、副图、系列添加/移除、高级渲染 Primitive。
 */
class ChartManager {
  constructor() {
    this.mainChart = null;
    this.candleSeries = null;
    this.volumeSeries = null;  // 新增：成交量系列
    this.subCharts = new Map();
    this.seriesMap = new Map();
    this.primitiveMap = new Map();
    this.nextSubChartId = 1;
    this.mainContainer = null;
    this.subContainer = null;
    this.maxSubCharts = 5;
    this.darkTheme = {
      background: '#131722',
      textColor: '#d1d4dc',
      gridColor: '#2a2e39',
      crosshairColor: '#758696',
    };
    this._LCache = null;
  }

  _GetLC() {
    if (!this._LCache && window.LightweightCharts) {
      this._LCache = window.LightweightCharts;
    }
    return this._LCache;
  }

  init(mainContainer, subContainer) {
    var lc = this._GetLC();
    if (!lc) { console.warn('LightweightCharts not loaded'); return; }

    this.mainContainer = mainContainer;
    this.subContainer = subContainer;
    this.mainChart = this._createChart(mainContainer);

    this.candleSeries = this.mainChart.addSeries(lc.CandlestickSeries, {
      upColor: '#0ecb81', downColor: '#f6465d',
      borderUpColor: '#0ecb81', borderDownColor: '#f6465d',
      wickUpColor: '#0ecb81', wickDownColor: '#f6465d',
    });
    this.seriesMap.set('CANDLE', {
      series: this.candleSeries, chartId: 'main',
      visible: true, type: 'candlestick',
    });
    
    // 新增：创建成交量柱状图系列
    this.volumeSeries = this.mainChart.addSeries(lc.HistogramSeries, {
      color: '#0ecb81',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '', // 不绑定到右侧价格轴
      scaleMargins: {
        top: 0.85,
        bottom: 0,
      },
    });
    this.seriesMap.set('VOLUME', {
      series: this.volumeSeries, chartId: 'main',
      visible: true, type: 'histogram',
    });
    
    this._setupCrosshair();
    this._setupTimeSync();
    // 添加 ResizeObserver 监听容器大小变化
    var self = this;
    if (typeof ResizeObserver !== 'undefined' && this.mainContainer) {
      this._resizeObserver = new ResizeObserver(function(entries) {
        for (var i = 0; i < entries.length; i++) {
          var entry = entries[i];
          if (entry.target === self.mainContainer) {
            var w = entry.contentRect.width;
            var h = entry.contentRect.height;
            if (w > 0 && h > 0) {
              self.mainChart.resize(w, h);
            }
          }
        }
      });
      this._resizeObserver.observe(this.mainContainer);
      console.log('[CM] ResizeObserver attached to mainContainer');
    }
    console.log('ChartManager: Main chart initialized (v5.2)');
  }

  initSubChart(name) {
    if (this.subCharts.size >= this.maxSubCharts) {
      console.warn('Max sub-charts reached (' + this.maxSubCharts + ')');
      return null;
    }
    var id = 'sub_' + (this.nextSubChartId++);
    var container = document.createElement('div');
    container.className = 'sub-chart-container';
    container.id = id;
    this.subContainer.appendChild(container);
    var chart = this._createChart(container, { height: 200, timeScale: { timeVisible: true } });
    this.subCharts.set(id, { chart: chart, name: name, container: container });
    this._subscribeTimeSync(chart, 'sub');
    this._subscribeCrosshairSync(chart);
    return id;
  }

  setCandleData(data) {
    console.log('[CM] setCandleData: bars=' + (data ? data.length : 0) + ', candleSeries=' + (this.candleSeries ? 'exists' : 'null'));
    if (!data || !this.candleSeries) {
      console.error('[CM] setCandleData failed: data=' + (data ? 'exists' : 'null') + ', candleSeries=' + (this.candleSeries ? 'exists' : 'null'));
      return;
    }
    console.log('[CM] calling candleSeries.setData with', data.length, 'bars');
    console.log('[CM] candleSeries type:', typeof this.candleSeries);
    console.log('[CM] candleSeries methods:', Object.keys(this.candleSeries).join(', '));
    try {
      this.candleSeries.setData(data);
      console.log('[CM] setData succeeded');
    } catch(e) {
      console.error('[CM] setData failed:', e.message);
    }
    
    // 新增：设置成交量数据
    if (this.volumeSeries) {
      var volumeData = [];
      var hasVolume = false;
      for (var i = 0; i < data.length; i++) {
        var bar = data[i];
        var vol = bar.volume;
        if (vol !== undefined && vol !== null && vol > 0) {
          hasVolume = true;
        }
        volumeData.push({
          time: bar.time,
          value: vol || 0,
          color: bar.close >= bar.open ? '#0ecb81' : '#f6465d'
        });
      }
      console.log('[CM] setting volume data, hasVolume=' + hasVolume + ', points=' + volumeData.length);
      try {
        this.volumeSeries.setData(volumeData);
        console.log('[CM] volumeSeries.setData succeeded');
      } catch(e) {
        console.error('[CM] volumeSeries.setData failed:', e.message);
      }
    } else {
      console.warn('[CM] volumeSeries not initialized');
    }
    
    console.log('[CM] setData called, now calling fitContent');
    this.fitContent();
    console.log('[CM] fitContent called, data should be visible now');
    // 验证数据是否真的被设置
    try {
      var count = this.candleSeries.data().length;
      console.log('[CM] verify: candleSeries.data().length =', count);
    } catch(e) {
      console.warn('[CM] verify failed:', e.message);
    }
    // 强制 resize 确保图表正确渲染
    var self = this;
    setTimeout(function() {
      if (self.mainChart) {
        var container = self.mainContainer;
        var w = container ? container.clientWidth : 0;
        var h = container ? container.clientHeight : 0;
        console.log('[CM] container size:', w, 'x', h);
        if (w > 0 && h > 0) {
          self.mainChart.resize(w, h);
          console.log('[CM] chart.resize called');
          self.fitContent();
        } else {
          console.warn('[CM] container has 0 size, chart might not be visible');
        }
      }
    }, 100);
  }

  /** addLineSeries — 创建 LineSeries，支持 subChart 路由 */
  addLineSeries(key, data, opts) {
    opts = opts || {};
    var lc = this._GetLC();
    if (!lc) return null;
    var chart = this.mainChart;
    var chartId = 'main';
    if (opts.subChart) {
      var subId = this._getSharedSubChart();
      var sub = this.subCharts.get(subId);
      if (sub) { chart = sub.chart; chartId = subId; }
    }
    var series = chart.addSeries(lc.LineSeries, {
      color: opts.color || '#2962FF',
      lineWidth: opts.lineWidth || 2,
      visible: opts.visible !== false,
      lastValueVisible: true,
      priceFormat: { type: 'custom', minMove: 0.01, formatter: function(v) { return v.toFixed(2); } },
    });
    series.setData(data);
    this.seriesMap.set(key, {
      series: series, chartId: chartId, visible: opts.visible !== false, type: 'line', data: data,
    });
    if (opts.subChart || chartId !== 'main') {
      try { chart.timeScale().fitContent(); } catch(e) { console.warn('[CM] fitContent failed:', e.message); }
    }
    return series;
  }

  /** addHistogramSeries — 创建 HistogramSeries */
  addHistogramSeries(key, data, opts) {
    opts = opts || {};
    var lc = this._GetLC();
    if (!lc) return null;
    var chart = this.mainChart;
    var chartId = 'main';
    if (opts.subChart) {
      var subId = this._getSharedSubChart();
      var sub = this.subCharts.get(subId);
      if (sub) { chart = sub.chart; chartId = subId; }
    }
    var series = chart.addSeries(lc.HistogramSeries, {
      color: opts.color || '#2962FF',
      priceFormat: { type: 'volume' },
      visible: opts.visible !== false,
    });
    series.setData(data);
    this.seriesMap.set(key, {
      series: series, chartId: chartId, visible: opts.visible !== false, type: 'histogram', data: data,
    });
    if (opts.subChart || chartId !== 'main') {
      try { chart.timeScale().fitContent(); } catch(e) { console.warn('[CM] histogram fitContent failed:', e.message); }
    }
    return series;
  }

  addAreaSeries(key, data, opts) {
    opts = opts || {};
    var lc = this._GetLC();
    if (!lc) return null;
    var series = this.mainChart.addSeries(lc.AreaSeries, {
      lineColor: opts.color || '#2962FF',
      topColor: opts.color ? opts.color + '40' : '#2962FF40',
      bottomColor: opts.color ? opts.color + '05' : '#2962FF05',
      lineWidth: opts.lineWidth || 2,
      visible: opts.visible !== false,
    });
    series.setData(data);
    this.seriesMap.set(key, {
      series: series, chartId: 'main', visible: opts.visible !== false, type: 'area', data: data,
    });
    return series;
  }

  // ==================== 高级渲染方法（全部接受 stateId 参数，生成唯一 key）====================

  setLineBrData(key, data, opts) {
    opts = opts || {};
    var series = this.addLineSeries(key + '_br', data, opts);
    if (!series) return;
    var lc = this._GetLC();
    if (!lc) return;
    var chart = this.mainChart;
    var chartId = 'main';
    if (opts.subChart) {
      var subId = this._getSharedSubChart();
      var sub = this.subCharts.get(subId);
      if (sub) { chart = sub.chart; chartId = subId; }
    }
    var prim = new window.Primitives.LineBrPrimitive();
    prim.setData(data, opts.color, opts.lineWidth, opts.lineStyle, opts.lineType === 'steplinebr');
    series.attachPrimitive(prim);
    this.primitiveMap.set(key + '_linebr', { prim: prim, parentSeries: series });
  }

  setCrossPlotData(key, data, opts) {
    opts = opts || {};
    var series = this.addLineSeries(key + '_cross', data, { ...opts, visible: false, lastValueVisible: false });
    if (!series) return;
    var prim = new window.Primitives.CrossPlotPrimitive();
    prim.setData(data, opts.color);
    series.attachPrimitive(prim);
    this.primitiveMap.set(key + '_cross', { prim: prim, parentSeries: series });
  }

  setCirclesPlotData(key, data, opts) {
    opts = opts || {};
    var series = this.addLineSeries(key + '_circles', data, { ...opts, visible: false, lastValueVisible: false });
    if (!series) return;
    var prim = new window.Primitives.CirclesPlotPrimitive();
    prim.setData(data, opts.color);
    series.attachPrimitive(prim);
    this.primitiveMap.set(key + '_circles', { prim: prim, parentSeries: series });
  }

  setSteplineData(key, data, opts) {
    opts = opts || {};
    var lc = this._GetLC();
    if (!lc) return null;
    var chart = this.mainChart;
    var chartId = 'main';
    if (opts.subChart) {
      var subId = this._getSharedSubChart();
      var sub = this.subCharts.get(subId);
      if (sub) { chart = sub.chart; chartId = subId; }
    }
    var series = chart.addSeries(lc.LineSeries, {
      color: opts.color || '#2962FF',
      lineWidth: opts.lineWidth || 2,
      lineType: lc.LineType.WithSteps,
      visible: opts.visible !== false,
      lastValueVisible: true,
      priceFormat: { type: 'custom', minMove: 0.01, formatter: function(v) { return v.toFixed(2); } },
    });
    series.setData(data);
    this.seriesMap.set(key + '_step', {
      series: series, chartId: chartId, visible: opts.visible !== false, type: 'line', data: data,
    });
    return series;
  }

  /** setBgColors — K线背景着色（接受 stateId 参数生成唯一 key） */
  setBgColors(data, paneIndex, stateId) {
    if (!this.candleSeries) return;
    stateId = stateId || 'unknown';
    var key = '_bgcolor_' + stateId + '_' + (paneIndex || 0);

    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }

    var prim = new window.Primitives.BgColorPrimitive();
    prim.setData(data);
    this.candleSeries.attachPrimitive(prim);
    this.primitiveMap.set(key, prim);
  }

  /** setPlotFills — plot-to-plot 填充（接受 stateId 参数生成唯一 key） */
  setPlotFills(fills, plots, paneIndex, stateId) {
    if (!fills || !plots) return;
    stateId = stateId || 'unknown';
    for (var fi = 0; fi < fills.length; fi++) {
      var fill = fills[fi];
      var key = '_fill_' + stateId + '_' + (paneIndex || 0) + '_' + fi;

      var data = [];
      if (fill.top && fill.bottom) {
        var top = plots[fill.top];
        var bot = plots[fill.bottom];
        if (top && bot && top.length === bot.length) {
          for (var di = 0; di < top.length; di++) {
            if (top[di] && bot[di] && top[di].time === bot[di].time) {
              data.push({ time: top[di].time, upper: top[di].value, lower: bot[di].value });
            }
          }
        }
      }

      if (data.length > 0) {
        var series = this.candleSeries;
        var prim = new window.Primitives.PlotFillPrimitive();
        prim.setData(data, fill.color || '#2962FF40');
        series.attachPrimitive(prim);
        this.primitiveMap.set(key, prim);
      }
    }
  }

  /** setMarkers — 设置标记 */
  setMarkers(builtinMarkers, extendedMarkers) {
    if (this.candleSeries && builtinMarkers && builtinMarkers.length > 0) {
      this.candleSeries.setMarkers(builtinMarkers);
    } else if (this.candleSeries) {
      this.candleSeries.setMarkers([]);
    }
    var key = '_extended_markers';
    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    if (extendedMarkers && extendedMarkers.length > 0) {
      var prim = new window.Primitives.ExtendedMarkerPrimitive();
      prim.setMarkers(extendedMarkers);
      this.candleSeries.attachPrimitive(prim);
      this.primitiveMap.set(key, prim);
    }
  }

  /** setMarkerPrimitive — 用 ExtendedMarkerPrimitive 按 stateId 隔离渲染标记 */
  setMarkerPrimitive(markers, stateId) {
    if (!this.candleSeries) return;
    stateId = stateId || 'unknown';
    var key = '_marker_' + stateId;
    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    if (!markers || markers.length === 0) return;
    var prim = new window.Primitives.ExtendedMarkerPrimitive();
    prim.setMarkers(markers);
    this.candleSeries.attachPrimitive(prim);
    this.primitiveMap.set(key, prim);
  }

  clearMarkerPrimitive(stateId) {
    stateId = stateId || 'unknown';
    var key = '_marker_' + stateId;
    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    this.primitiveMap.delete(key);
  }

  /** clearMarkers — 清除所有标记（ExtendedMarkerPrimitive + 内置 markers） */
  clearMarkers() {
    if (this.candleSeries) {
      try { this.candleSeries.setMarkers([]); } catch(e) {}
    }
    var key = '_extended_markers';
    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    this.primitiveMap.delete(key);
  }

  /** setHLines — 水平参考线（接受 stateId 参数生成唯一 key） */
  setHLines(configs, paneIndex, bars, stateId) {
    stateId = stateId || 'unknown';
    // 先清理所有 _hl_{stateId}_... 相关 key
    var prefix = '_hl_' + stateId;
    var self = this;
    this.primitiveMap.forEach(function(v, k) {
      if (k.indexOf(prefix) === 0) {
        try {
          if (v && v.series && v.chart) { v.chart.removeSeries(v.series); }
        } catch(e) {}
      }
    });
    var delKeys = [];
    this.primitiveMap.forEach(function(v, k) { if (k.indexOf(prefix) === 0) delKeys.push(k); });
    for (var dk = 0; dk < delKeys.length; dk++) self.primitiveMap.delete(delKeys[dk]);

    if (!configs || !bars || bars.length === 0) return;
    var lc = this._GetLC();
    if (!lc) return;

    var chart = paneIndex === 0 ? this.mainChart : null;
    if (paneIndex > 0) {
      var subId = this._getSharedSubChart();
      var sub = this.subCharts.get(subId);
      if (sub) chart = sub.chart;
    }
    if (!chart) return;

    for (var hi = 0; hi < configs.length; hi++) {
      var cfg = configs[hi];
      var hKey = prefix + '_' + paneIndex + '_' + hi;
      try {
        var series = chart.addSeries(lc.LineSeries, {
          color: cfg.color || '#787b86',
          lineWidth: cfg.lineWidth || 1,
          lineStyle: cfg.lineStyle === 'dashed' ? lc.LineStyle.Dashed : (cfg.lineStyle === 'dotted' ? lc.LineStyle.Dotted : lc.LineStyle.Solid),
          lastValueVisible: !!cfg.label,
          priceLineVisible: false,
        });
        var hData = [
          { time: bars[0].time, value: cfg.price || cfg.value || 0 },
          { time: bars[bars.length - 1].time, value: cfg.price || cfg.value || 0 },
        ];
        series.setData(hData);
        this.primitiveMap.set(hKey, { series: series, chart: chart, config: cfg, barStart: bars[0].time, barEnd: bars[bars.length - 1].time });
      } catch(e) {}
    }
  }

  /** setFills — hlines 区间填充 */
  setFills(fillConfigs, hlineConfigs, paneIndex, bars) {
    var key = '_fill_hl_' + (paneIndex || 0);
    this.primitiveMap.forEach(function(v, k) {
      if (k.indexOf(key) >= 0) {
        try { if (v.setData) v.setData([]); } catch(e) {}
      }
    });
    if (!fillConfigs || !hlineConfigs || !bars || bars.length === 0) return;
    var hlineMap = {};
    for (var hi = 0; hi < hlineConfigs.length; hi++) {
      hlineMap[hlineConfigs[hi].name] = hlineConfigs[hi].price || 0;
    }
    for (var fi = 0; fi < fillConfigs.length; fi++) {
      var fc = fillConfigs[fi];
      var top = hlineMap[fc.top];
      var bot = hlineMap[fc.bottom];
      if (top === undefined || bot === undefined) continue;
      var pKey = key + '_' + fi;
      var fillData = bars.map(function(b) {
        return { time: b.time, color: fc.color || '#2962FF', alpha: fc.alpha || 0.1 };
      });
      var series = this.candleSeries;
      if (!series) continue;
      var prim = new window.Primitives.BgColorPrimitive();
      prim.setData(fillData);
      series.attachPrimitive(prim);
      this.primitiveMap.set(pKey, prim);
    }
  }

  /** setLabels — 文本标签（接受 stateId 参数生成唯一 key） */
  setLabels(labels, paneIndex, stateId) {
    stateId = stateId || 'unknown';
    var key = '_labels_' + stateId + '_' + (paneIndex || 0);
    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    if (labels && labels.length > 0) {
      var prim = new window.Primitives.LabelPrimitive();
      prim.setLabels(labels);
      this.candleSeries.attachPrimitive(prim);
      this.primitiveMap.set(key, prim);
    }
  }

  /** setLineDrawings — 线段（接受 stateId 参数生成唯一 key） */
  setLineDrawings(lines, paneIndex, stateId) {
    stateId = stateId || 'unknown';
    var key = '_lines_draw_' + stateId + '_' + (paneIndex || 0);
    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    if (lines && lines.length > 0) {
      var prim = new window.Primitives.LineDrawingPrimitive();
      prim.setLines(lines);
      this.candleSeries.attachPrimitive(prim);
      this.primitiveMap.set(key, prim);
    }
  }

  setBoxes(boxes, paneIndex) {
    var key = '_boxes_' + (paneIndex || 0);
    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    if (boxes && boxes.length > 0) {
      var prim = new window.Primitives.BoxPrimitive();
      prim.setBoxes(boxes);
      this.candleSeries.attachPrimitive(prim);
      this.primitiveMap.set(key, prim);
    }
  }

  setTable(table) {
    var key = '_table';
    var old = this.primitiveMap.get(key);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    if (table) {
      var prim = new window.Primitives.TablePrimitive();
      prim.setTable(table);
      this.candleSeries.attachPrimitive(prim);
      this.primitiveMap.set(key, prim);
    }
  }

  setCandlePlotData(key, data, paneIndex) {
    var pKey = '_candle_' + key;
    var old = this.primitiveMap.get(pKey);
    if (old) { try { this.candleSeries.detachPrimitive(old); } catch(e) {} }
    if (data && data.length > 0) {
      var prim = new window.Primitives.CandlePlotPrimitive();
      prim.setData(data);
      this.candleSeries.attachPrimitive(prim);
      this.primitiveMap.set(pKey, prim);
    }
  }

  // ==================== 清理方法 ====================

  clearIndicators() {
    var self = this;
    this.primitiveMap.forEach(function(v, k) {
      if (v && v.series && v.chart) {
        try { v.chart.removeSeries(v.series); } catch(e) {}
      } else if (v && v.parentSeries) {
        try { v.parentSeries.detachPrimitive(v.prim); } catch(e) {}
      } else {
        try { self.candleSeries.detachPrimitive(v); } catch(e) {}
      }
    });
    this.primitiveMap.clear();
    var keys = [];
    this.seriesMap.forEach(function(v, k) { if (k !== 'CANDLE') keys.push(k); });
    keys.forEach(function(k) { self.removeSeries(k); });
  }

  updateSeries(key, data) {
    var entry = this.seriesMap.get(key);
    if (entry) entry.series.setData(data);
  }

  removeSeries(key) {
    var entry = this.seriesMap.get(key);
    if (!entry) return;
    var chart = entry.chartId === 'main'
      ? this.mainChart
      : (this.subCharts.get(entry.chartId) ? this.subCharts.get(entry.chartId).chart : null);
    if (chart) {
      try { chart.removeSeries(entry.series); } catch (e) { }
    }
    this.seriesMap.delete(key);
    if (entry.chartId !== 'main') {
      var hasSeries = false;
      this.seriesMap.forEach(function(s) {
        if (s.chartId === entry.chartId) hasSeries = true;
      });
      if (!hasSeries) {
        var sub = this.subCharts.get(entry.chartId);
        if (sub) {
          sub.container.remove();
          this.subCharts.delete(entry.chartId);
        }
      }
    }
  }

  /** setSeriesVisible — 通过 remove/add 切换 series 可见性 */
  setSeriesVisible(key, visible) {
    var entry = this.seriesMap.get(key);
    if (!entry) return false;
    if (visible === entry.visible) return true;
    var lc = this._GetLC();
    if (!lc) return false;
    var chart = entry.chartId === 'main'
      ? this.mainChart
      : (this.subCharts.get(entry.chartId) ? this.subCharts.get(entry.chartId).chart : null);
    if (!chart) return false;
    if (visible) {
      var SeriesCtor = entry.type === 'histogram' ? lc.HistogramSeries : lc.LineSeries;
      var opts = {};
      if (entry.series && entry.series.options) {
        var oldOpts = entry.series.options();
        opts.color = oldOpts.color;
        opts.lineWidth = oldOpts.lineWidth;
        opts.lineStyle = oldOpts.lineStyle;
      }
      var series = chart.addSeries(SeriesCtor, {
        color: opts.color || (entry.type === 'histogram' ? undefined : '#2962FF'),
        lineWidth: opts.lineWidth || (entry.type === 'histogram' ? undefined : 2),
        visible: true,
        lastValueVisible: entry.type !== 'histogram',
      });
      if (entry.data) series.setData(entry.data);
      entry.series = series;
      entry.visible = true;
    } else {
      try { chart.removeSeries(entry.series); } catch(e) {}
      entry.visible = false;
    }
    return true;
  }

  /** setExtraKeyVisible — 切换附加对象可见性 */
  setExtraKeyVisible(ek, visible) {
    var obj = this.primitiveMap.get(ek);
    if (!obj) {
      console.log('[EXTRA] ' + ek + ' not found in primitiveMap (already clean)');
      return false;
    }
    if (obj.series && obj.chart && obj.config) {
      var entry = obj;
      if (visible) {
        var lc = this._GetLC();
        if (!lc) return false;
        try {
          var newSeries = entry.chart.addSeries(lc.LineSeries, {
            color: entry.config.color || '#787b86',
            lineWidth: entry.config.lineWidth || 1,
            lineStyle: entry.config.lineStyle === 'dashed' ? lc.LineStyle.Dashed : (entry.config.lineStyle === 'dotted' ? lc.LineStyle.Dotted : lc.LineStyle.Solid),
            lastValueVisible: !!entry.config.label,
            priceLineVisible: false,
          });
          newSeries.setData([
            { time: entry.barStart, value: entry.config.price || entry.config.value || 0 },
            { time: entry.barEnd, value: entry.config.price || entry.config.value || 0 },
          ]);
          entry.series = newSeries;
        } catch(e) { return false; }
      } else {
        try { entry.chart.removeSeries(entry.series); } catch(e) {}
      }
      console.log('[EXTRA] ' + ek + ' hline -> ' + (visible ? 'show' : 'hide'));
      return true;
    }
    // Primitive: 用 setVisible(false) 保留在 chart 上但停止绘制
    try {
      if (obj.setVisible) {
        obj.setVisible(!!visible);
        console.log('[EXTRA] ' + ek + ' primitive setVisible(' + !!visible + ')');
      } else if (obj.applyOptions) {
        obj.applyOptions({ visible: !!visible });
        console.log('[EXTRA] ' + ek + ' primitive applyOptions(visible=' + !!visible + ')');
      } else {
        console.log('[EXTRA] ' + ek + ' primitive has no setVisible/applyOptions method');
      }
    } catch(e) {
      console.error('[EXTRA] ' + ek + ' error: ' + e);
    }
    return true;
  }

  clearAll() {
    var self = this;
    this.clearIndicators();
    var keys = [];
    this.seriesMap.forEach(function(v, k) { if (k !== 'CANDLE') keys.push(k); });
    keys.forEach(function(k) { self.removeSeries(k); });
    this.subCharts.forEach(function(sub) { sub.container.remove(); });
    this.subCharts.clear();
    this.nextSubChartId = 1;
    // 必须先 detach 所有 primitive，再 clear map（否则旧 primitive 继续附着在 series 上）
    var self2 = this;
    this.primitiveMap.forEach(function(v, k) {
      if (v && v.parentSeries && v.prim) {
        try { v.parentSeries.detachPrimitive(v.prim); } catch(e) {}
      } else if (v && v.series && v.chart) {
        try { v.chart.removeSeries(v.series); } catch(e) {}
      } else if (v && self2.candleSeries) {
        try { self2.candleSeries.detachPrimitive(v); } catch(e) {}
      }
    });
    this.primitiveMap.clear();
  }

  fitContent() {
    if (this.mainChart) {
      try { this.mainChart.timeScale().fitContent(); } catch(e) { console.warn('[CM] fitContent failed:', e.message); }
    }
  }

  getVisibleRange() {
    if (!this.mainChart) return null;
    try { return this.mainChart.timeScale().getVisibleRange(); } catch(e) { return null; }
  }

  setVisibleRange(range) {
    if (this.mainChart) {
      try { this.mainChart.timeScale().setVisibleRange(range); } catch(e) { console.warn('[CM] setVisibleRange failed:', e.message); }
    }
  }

  _getSharedSubChart() {
    var found = null;
    this.subCharts.forEach(function(sub, id) {
      if (sub.name === '_shared_sub') found = id;
    });
    if (found !== null) return found;
    return this.initSubChart('_shared_sub');
  }

  _createChart(container, extraOpts) {
    extraOpts = extraOpts || {};
    var lc = this._GetLC();
    if (!lc) return null;
    var opts = {
      layout: {
        background: { type: 'solid', color: this.darkTheme.background },
        textColor: this.darkTheme.textColor,
      },
      grid: {
        vertLines: { color: this.darkTheme.gridColor },
        horzLines: { color: this.darkTheme.gridColor },
      },
      crosshair: { mode: lc.CrosshairMode.Normal },
      rightPriceScale: { borderColor: this.darkTheme.gridColor },
      timeScale: { borderColor: this.darkTheme.gridColor },
    };
    for (var k in extraOpts) { if (extraOpts.hasOwnProperty(k)) opts[k] = extraOpts[k]; }
    return lc.createChart(container, opts);
  }

  _getOrCreateSubChart(group) {
    var groupMap = {
      OSC: 'oscillators', MOM: 'momentum', VOL: 'volume',
      Yearly_Profile: 'yearly_profile', VOLATILITY: 'volatility',
    };
    var name = groupMap[group] || group || 'sub_' + this.nextSubChartId;
    var found = null;
    this.subCharts.forEach(function(sub, id) {
      if (sub.name === name) found = id;
    });
    if (found !== null) return found;
    return this.initSubChart(name);
  }

  _subscribeCrosshairSync(chart) {
    var self = this;
    try {
      chart.subscribeCrosshairMove(function(param) {
        if (!param.point || !param.time) return;
        try { self.mainChart.setCrosshairPosition(param.point, param.time); } catch(e) {}
        self.subCharts.forEach(function(sub, id) {
          if (sub.chart !== chart) {
            try { sub.chart.setCrosshairPosition(param.point, param.time); } catch(e) {}
          }
        });
      });
    } catch(e) {}
  }

  _setupCrosshair() {
    var self = this;
    if (!this.mainChart) return;
    
    // 创建自定义 tooltip
    this._tooltip = document.createElement('div');
    this._tooltip.className = 'custom-tooltip';
    this._tooltip.style.cssText = `
      position: absolute;
      background: rgba(19, 23, 34, 0.95);
      border: 1px solid #2a2e39;
      border-radius: 8px;
      padding: 12px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 12px;
      color: #d1d4dc;
      pointer-events: none;
      z-index: 1000;
      display: none;
      min-width: 180px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    `;
    document.body.appendChild(this._tooltip);
    
    this.mainChart.subscribeCrosshairMove(function(param) {
      if (!param.point || !param.time) {
        self._tooltip.style.display = 'none';
        return;
      }
      
      // 获取蜡烛图数据
      var candleData = null;
      var volumeData = null;
      if (self.candleSeries && typeof self.candleSeries.data === 'function') {
        try {
          var data = self.candleSeries.data();
          candleData = data.find(function(d) { return d.time === param.time; });
        } catch(e) {}
      }
      
      // 从成交量系列获取成交量数据
      if (self.volumeSeries && typeof self.volumeSeries.data === 'function') {
        try {
          var volData = self.volumeSeries.data();
          volumeData = volData.find(function(d) { return d.time === param.time; });
        } catch(e) {}
      }
      
      if (candleData) {
        // 计算涨跌幅和涨跌额
        var prevData = null;
        if (self.candleSeries && typeof self.candleSeries.data === 'function') {
          try {
            var data = self.candleSeries.data();
            var idx = data.findIndex(function(d) { return d.time === param.time; });
            if (idx > 0) prevData = data[idx - 1];
          } catch(e) {}
        }
        
        var change = 0;
        var changePercent = 0;
        if (prevData) {
          change = candleData.close - prevData.close;
          changePercent = (change / prevData.close) * 100;
        }
        
        // 格式化日期（支持字符串日期格式和整数时间戳）
        var date;
        if (typeof param.time === 'string') {
          // 字符串日期格式 'YYYY-MM-DD'
          date = new Date(param.time);
        } else if (typeof param.time === 'number') {
          // 整数时间戳（秒）
          date = new Date(param.time * 1000);
        } else {
          date = new Date();
        }
        
        var weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        var dateStr = date.toLocaleDateString('zh-CN', { 
          year: 'numeric', 
          month: '2-digit', 
          day: '2-digit' 
        });
        var weekdayStr = weekdays[date.getDay()];
        
        // 构建 tooltip 内容
        var color = candleData.close >= candleData.open ? '#0ecb81' : '#f6465d';
        var changeColor = change >= 0 ? '#0ecb81' : '#f6465d';
        
        // 获取成交量
        var volume = 0;
        if (volumeData && volumeData.value !== undefined) {
          volume = volumeData.value;
        }
        
        self._tooltip.innerHTML = `
          <div style="display: grid; grid-template-columns: 60px 1fr; gap: 4px;">
            <div style="color: #758696;">日期</div>
            <div style="font-weight: 600;">${dateStr}</div>
            <div style="color: #758696;">星期</div>
            <div>${weekdayStr}</div>
            <div style="color: #758696;">开盘</div>
            <div style="color: ${color};">${candleData.open.toFixed(2)}</div>
            <div style="color: #758696;">最高</div>
            <div style="color: ${color};">${candleData.high.toFixed(2)}</div>
            <div style="color: #758696;">最低</div>
            <div style="color: ${color};">${candleData.low.toFixed(2)}</div>
            <div style="color: #758696;">收盘</div>
            <div style="color: ${color}; font-weight: 600;">${candleData.close.toFixed(2)}</div>
            <div style="color: #758696;">涨跌额</div>
            <div style="color: ${changeColor};">${change >= 0 ? '+' : ''}${change.toFixed(2)}</div>
            <div style="color: #758696;">涨跌幅</div>
            <div style="color: ${changeColor};">${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(2)}%</div>
            <div style="color: #758696;">成交量</div>
            <div>${self._formatVolume(volume)}</div>
          </div>
        `;
        
        // 设置位置
        var rect = self.mainContainer.getBoundingClientRect();
        var x = rect.left + param.point.x + 15;
        var y = rect.top + param.point.y - 50;
        
        // 防止溢出屏幕
        if (x + self._tooltip.offsetWidth > window.innerWidth) {
          x = rect.left + param.point.x - self._tooltip.offsetWidth - 15;
        }
        if (y + self._tooltip.offsetHeight > window.innerHeight) {
          y = window.innerHeight - self._tooltip.offsetHeight - 20;
        }
        if (y < 20) y = 20;
        
        self._tooltip.style.left = x + 'px';
        self._tooltip.style.top = y + 'px';
        self._tooltip.style.display = 'block';
      } else {
        self._tooltip.style.display = 'none';
      }
      
      self.subCharts.forEach(function(sub) {
        try { sub.chart.setCrosshairPosition(param.point, param.time); } catch(e) {}
      });
    });
  }
  
  _formatVolume(volume) {
    if (volume === undefined || volume === null || isNaN(volume)) {
      return '-';
    }
    volume = Number(volume);
    if (volume >= 100000000) {
      return (volume / 100000000).toFixed(2) + ' 亿';
    } else if (volume >= 10000) {
      return (volume / 10000).toFixed(2) + ' 万';
    }
    return volume.toString();
  }

  _subscribeTimeSync(chart, chartType) {
    var self = this;
    try {
      chart.timeScale().subscribeVisibleLogicalRangeChange(function(range) {
        if (!self._isSyncing && range) {
          self._isSyncing = true;
          if (chartType !== 'main') {
            try { self.mainChart.timeScale().setVisibleLogicalRange(range); } catch(e) {}
          }
          self.subCharts.forEach(function(sub, id) {
            if (sub.chart !== chart) {
              try { sub.chart.timeScale().setVisibleLogicalRange(range); } catch(e) {}
            }
          });
          self._isSyncing = false;
        }
      });
    } catch(e) {}
  }

  _setupTimeSync() {
    this._isSyncing = false;
    this._subscribeTimeSync(this.mainChart, 'main');
    var self = this;
    this.subCharts.forEach(function(sub, id) {
      self._subscribeTimeSync(sub.chart, 'sub');
    });
  }
}

// 实例化全局 ChartManager
window.chartManager = new ChartManager();
