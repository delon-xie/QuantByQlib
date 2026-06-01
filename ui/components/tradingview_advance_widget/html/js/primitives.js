/**
 * primitives.js — ISeriesPrimitive 自定义渲染器集合
 * 实现 10+ 项高级渲染特性: linebr, cross, circles, bgColor, plotFill,
 * extendedMarker, label, box, lineDrawing, table, candlePlot
 *
 * 每个 primitive 通过 LightweightCharts ISeriesPrimitive 接口附着到 series。
 * z-order: bgColor(bottom) → plotFill → lineDrawing/box → label/marker(top)
 */

// ==================== BasePrimitive ====================

class BasePrimitive {
  constructor() { this._chart = null; this._series = null; this._requestUpdate = null; this._visible = true; }

  attached(param) {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
  }
  detached() { this._chart = null; this._series = null; this._requestUpdate = null; }

  getChart() { return this._chart; }
  getSeries() { return this._series; }
  requestUpdate() { if (this._requestUpdate) this._requestUpdate(); }
  updateAllViews() {}
  paneViews() { return []; }

  /** 控制 primitive 显隐 */
  setVisible(v) { this._visible = v; this.requestUpdate(); }
  isVisible() { return this._visible; }
}

// ==================== 辅助函数 ====================

function getBarWidth(timeScale, mediaWidth) {
  var logicalRange = timeScale.getVisibleLogicalRange();
  if (!logicalRange) return 6;
  var bars = logicalRange.to - logicalRange.from;
  if (bars <= 0) return 6;
  return Math.max(2, Math.min(20, mediaWidth / bars * 0.8));
}

// ==================== 1. LineBrPrimitive — NaN 断点线 ====================

class LineBrPrimitive extends BasePrimitive {
  constructor() {
    super(); this._data = []; this._color = '#2962FF';
    this._lineWidth = 2; this._lineStyle = 0; this._withSteps = false;
    this._views = [new LineBrPaneView(this)];
  }

  setData(data, color, lineWidth, lineStyle, withSteps) {
    this._data = data; this._color = color || '#2962FF';
    this._lineWidth = lineWidth || 2; this._lineStyle = lineStyle || 0;
    this._withSteps = withSteps || false;
    this.requestUpdate();
  }

  getData() { return this._data; }
  getColor() { return this._color; }
  getLineWidth() { return this._lineWidth; }
  getLineStyle() { return this._lineStyle; }
  getWithSteps() { return this._withSteps; }

  paneViews() { return this._views; }
}

class LineBrPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'normal'; }
  renderer() { return new LineBrRenderer(this._source); }
}

class LineBrRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
    if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var data = this._source.getData();
    var color = this._source.getColor();
    var lw = this._source.getLineWidth();
    var ls = this._source.getLineStyle();
    var withSteps = this._source.getWithSteps();
    var timeScale = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;
      ctx.strokeStyle = color;
      ctx.lineWidth = lw;
      if (ls === 1) ctx.setLineDash([4, 4]);
      else if (ls === 2) ctx.setLineDash([2, 2]);
      else ctx.setLineDash([]);

      var drawing = false, prevY = 0;
      for (var i = 0; i < data.length; i++) {
        var pt = data[i];
        var isNaN = pt.value == null || pt.value === undefined || Number.isNaN(pt.value);
        if (isNaN) {
          if (drawing) { ctx.stroke(); drawing = false; }
          continue;
        }
        var x = timeScale.timeToCoordinate(pt.time);
        var y = series.priceToCoordinate(pt.value);
        if (x == null || y == null) {
          if (drawing) { ctx.stroke(); drawing = false; }
          continue;
        }
        if (!drawing) {
          ctx.beginPath(); ctx.moveTo(x, y); drawing = true;
        } else {
          if (withSteps) ctx.lineTo(x, prevY);
          ctx.lineTo(x, y);
        }
        prevY = y;
      }
      if (drawing) ctx.stroke();
      ctx.setLineDash([]);
    });
  }
}

// ==================== 2. CrossPlotPrimitive — 十字叉 ====================

class CrossPlotPrimitive extends BasePrimitive {
  constructor() {
    super(); this._data = []; this._color = '#2962FF'; this._size = 6;
    this._views = [new CrossPlotPaneView(this)];
  }

  setData(data, color, size) {
    this._data = data; this._color = color || '#2962FF';
    this._size = size || 6; this.requestUpdate();
  }

  getData() { return this._data; }
  getColor() { return this._color; }
  getSize() { return this._size; }
  paneViews() { return this._views; }
}

class CrossPlotPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'normal'; }
  renderer() { return new CrossPlotRenderer(this._source); }
}

class CrossPlotRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var data = this._source.getData();
    var color = this._source.getColor();
    var half = this._source.getSize();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;
      ctx.strokeStyle = color; ctx.lineWidth = 2;
      for (var i = 0; i < data.length; i++) {
        var pt = data[i];
        if (pt.value == null || Number.isNaN(pt.value)) continue;
        var x = ts.timeToCoordinate(pt.time);
        var y = series.priceToCoordinate(pt.value);
        if (x == null || y == null) continue;
        ctx.beginPath();
        ctx.moveTo(x - half, y - half); ctx.lineTo(x + half, y + half);
        ctx.moveTo(x + half, y - half); ctx.lineTo(x - half, y + half);
        ctx.stroke();
      }
    });
  }
}

// ==================== 3. CirclesPlotPrimitive — 圆点图 ====================

class CirclesPlotPrimitive extends BasePrimitive {
  constructor() {
    super(); this._data = []; this._color = '#2962FF'; this._radius = 4;
    this._views = [new CirclesPlotPaneView(this)];
  }

  setData(data, color, radius) {
    this._data = data; this._color = color || '#2962FF';
    this._radius = radius || 4; this.requestUpdate();
  }

  getData() { return this._data; }
  getColor() { return this._color; }
  getRadius() { return this._radius; }
  paneViews() { return this._views; }
}

class CirclesPlotPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'normal'; }
  renderer() { return new CirclesPlotRenderer(this._source); }
}

class CirclesPlotRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var data = this._source.getData();
    var color = this._source.getColor();
    var r = this._source.getRadius();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;
      ctx.fillStyle = color;
      for (var i = 0; i < data.length; i++) {
        var pt = data[i];
        if (pt.value == null || Number.isNaN(pt.value)) continue;
        var x = ts.timeToCoordinate(pt.time);
        var y = series.priceToCoordinate(pt.value);
        if (x == null || y == null) continue;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, 2 * Math.PI);
        ctx.fill();
      }
    });
  }
}

// ==================== 4. BgColorPrimitive — K线背景着色 ====================

class BgColorPrimitive extends BasePrimitive {
  constructor() {
    super(); this._data = [];
    this._views = [new BgColorPaneView(this)];
  }

  setData(data) { this._data = data || []; this.requestUpdate(); }
  getData() { return this._data; }
  paneViews() { return this._views; }
}

class BgColorPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'top'; }
  renderer() { return new BgColorRenderer(this._source); }
}

class BgColorRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    if (!chart) return;

    var data = this._source.getData();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;
      var w = ctxData.mediaSize.width;
      var bw = getBarWidth(ts, w);

      for (var i = 0; i < data.length; i++) {
        var bar = data[i];
        var x = ts.timeToCoordinate(bar.time);
        if (x == null) continue;
        ctx.fillStyle = bar.color || 'transparent';
        ctx.globalAlpha = bar.alpha !== undefined ? bar.alpha : 0.25;
        ctx.fillRect(x - bw / 2, 0, bw, ctxData.mediaSize.height);
      }
      ctx.globalAlpha = 1.0;
    });
  }
}

// ==================== 5. PlotFillPrimitive — plot间填充 (云带/通道) ====================

class PlotFillPrimitive extends BasePrimitive {
  constructor() {
    super(); this._data = []; this._color = '#2962FF40';
    this._views = [new PlotFillPaneView(this)];
  }

  setData(data, color) {
    this._data = data || []; this._color = color || '#2962FF40';
    this.requestUpdate();
  }

  getData() { return this._data; }
  getColor() { return this._color; }
  paneViews() { return this._views; }
}

class PlotFillPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'bottom'; }
  renderer() { return new PlotFillRenderer(this._source); }
}

class PlotFillRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var data = this._source.getData();
    var color = this._source.getColor();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;
      ctx.fillStyle = color;

      for (var i = 0; i < data.length; i++) {
        var bar = data[i];
        var x = ts.timeToCoordinate(bar.time);
        if (x == null) continue;
        var yUpper = series.priceToCoordinate(bar.upper);
        var yLower = series.priceToCoordinate(bar.lower);
        if (yUpper == null || yLower == null) continue;

        var top = Math.min(yUpper, yLower);
        var bottom = Math.max(yUpper, yLower);
        ctx.fillRect(x - 3, top, 6, bottom - top);
      }
    });
  }
}

// ==================== 6. ExtendedMarkerPrimitive — 扩展标记 ====================

class ExtendedMarkerPrimitive extends BasePrimitive {
  constructor() {
    super(); this._markers = [];
    this._views = [new ExtendedMarkerPaneView(this)];
  }

  setMarkers(markers) { this._markers = markers || []; this.requestUpdate(); }
  getMarkers() { return this._markers; }
  paneViews() { return this._views; }
}

class ExtendedMarkerPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'normal'; }
  renderer() { return new ExtendedMarkerRenderer(this._source); }
}

class ExtendedMarkerRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var markers = this._source.getMarkers();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;

      for (var mi = 0; mi < markers.length; mi++) {
        var m = markers[mi];
        var x = ts.timeToCoordinate(m.time);
        if (x == null) continue;

        var logical = ts.coordinateToLogical(x);
        if (logical == null) continue;
        var barData = series.dataByIndex(logical);
        if (!barData) continue;
        var bar = barData;
        var baseY;
        if (m.position === 'aboveBar') {
          baseY = series.priceToCoordinate(bar.high != null ? bar.high : (bar.value != null ? bar.value : 0));
          if (baseY != null) baseY -= 10;
        } else if (m.position === 'belowBar') {
          baseY = series.priceToCoordinate(bar.low != null ? bar.low : (bar.value != null ? bar.value : 0));
          if (baseY != null) baseY += 10;
        } else {
          baseY = series.priceToCoordinate(bar.close != null ? bar.close : (bar.value != null ? bar.value : 0));
        }
        if (baseY == null) continue;

        var size = (m.size || 1) * 6;
        ctx.fillStyle = m.color;
        ctx.strokeStyle = m.color;
        ctx.lineWidth = 2;

        switch (m.shape) {
          case 'diamond':
            ctx.beginPath();
            ctx.moveTo(x, baseY - size);
            ctx.lineTo(x + size, baseY);
            ctx.lineTo(x, baseY + size);
            ctx.lineTo(x - size, baseY);
            ctx.closePath();
            ctx.fill();
            break;
          case 'triangleUp':
            ctx.beginPath();
            ctx.moveTo(x, baseY - size);
            ctx.lineTo(x - size, baseY + size);
            ctx.lineTo(x + size, baseY + size);
            ctx.closePath();
            ctx.fill();
            break;
          case 'triangleDown':
            ctx.beginPath();
            ctx.moveTo(x, baseY + size);
            ctx.lineTo(x - size, baseY - size);
            ctx.lineTo(x + size, baseY - size);
            ctx.closePath();
            ctx.fill();
            break;
          case 'arrowUp':
            ctx.beginPath();
            ctx.moveTo(x, baseY - size);
            ctx.lineTo(x - size * 0.6, baseY);
            ctx.lineTo(x - size * 0.3, baseY);
            ctx.lineTo(x - size * 0.3, baseY + size);
            ctx.lineTo(x + size * 0.3, baseY + size);
            ctx.lineTo(x + size * 0.3, baseY);
            ctx.lineTo(x + size * 0.6, baseY);
            ctx.closePath();
            ctx.fill();
            break;
          case 'arrowDown':
            ctx.beginPath();
            ctx.moveTo(x, baseY + size);
            ctx.lineTo(x - size * 0.6, baseY);
            ctx.lineTo(x - size * 0.3, baseY);
            ctx.lineTo(x - size * 0.3, baseY - size);
            ctx.lineTo(x + size * 0.3, baseY - size);
            ctx.lineTo(x + size * 0.3, baseY);
            ctx.lineTo(x + size * 0.6, baseY);
            ctx.closePath();
            ctx.fill();
            break;
          default: // square
            ctx.fillRect(x - size / 2, baseY - size / 2, size, size);
        }

        if (m.text) {
          ctx.fillStyle = m.color;
          ctx.font = '11px sans-serif';
          ctx.textAlign = 'center';
          var textY = m.position === 'aboveBar' ? baseY - size - 4 : baseY + size + 12;
          ctx.fillText(m.text, x, textY);
        }
      }
    });
  }
}

// ==================== 7. LabelPrimitive — 文本标签 ====================

class LabelPrimitive extends BasePrimitive {
  constructor() {
    super(); this._labels = [];
    this._views = [new LabelPaneView(this)];
  }

  setLabels(labels) { this._labels = labels || []; this.requestUpdate(); }
  getLabels() { return this._labels; }
  paneViews() { return this._views; }
}

class LabelPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'top'; }
  renderer() { return new LabelRenderer(this._source); }
}

class LabelRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var labels = this._source.getLabels();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;

      for (var li = 0; li < labels.length; li++) {
        var lbl = labels[li];
        var x = ts.timeToCoordinate(lbl.time);
        if (x == null) continue;
        var y = series.priceToCoordinate(lbl.price);
        if (y == null) continue;

        ctx.fillStyle = lbl.color || '#f0f3fa';
        ctx.font = '12px sans-serif';
        ctx.textAlign = lbl.textAlign || 'center';
        ctx.fillText(lbl.text || '', x, y - 6);
      }
    });
  }
}

// ==================== 8. BoxPrimitive — 矩形框 ====================

class BoxPrimitive extends BasePrimitive {
  constructor() {
    super(); this._boxes = [];
    this._views = [new BoxPaneView(this)];
  }

  setBoxes(boxes) { this._boxes = boxes || []; this.requestUpdate(); }
  getBoxes() { return this._boxes; }
  paneViews() { return this._views; }
}

class BoxPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'normal'; }
  renderer() { return new BoxRenderer(this._source); }
}

class BoxRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var boxes = this._source.getBoxes();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;

      for (var bi = 0; bi < boxes.length; bi++) {
        var box = boxes[bi];
        var x1 = ts.timeToCoordinate(box.time1);
        var x2 = ts.timeToCoordinate(box.time2);
        var y1 = series.priceToCoordinate(box.price1);
        var y2 = series.priceToCoordinate(box.price2);
        if (x1 == null || x2 == null || y1 == null || y2 == null) continue;

        var left = Math.min(x1, x2);
        var top = Math.min(y1, y2);
        var w = Math.abs(x2 - x1);
        var h = Math.abs(y2 - y1);

        if (box.fill) {
          ctx.fillStyle = box.fill;
          ctx.fillRect(left, top, w, h);
        }
        ctx.strokeStyle = box.color || '#2962FF';
        ctx.lineWidth = box.lineWidth || 1;
        ctx.strokeRect(left, top, w, h);
      }
    });
  }
}

// ==================== 9. LineDrawingPrimitive — 线段 ====================

class LineDrawingPrimitive extends BasePrimitive {
  constructor() {
    super(); this._lines = [];
    this._views = [new LineDrawingPaneView(this)];
  }

  setLines(lines) { this._lines = lines || []; this.requestUpdate(); }
  getLines() { return this._lines; }
  paneViews() { return this._views; }
}

class LineDrawingPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'normal'; }
  renderer() { return new LineDrawingRenderer(this._source); }
}

class LineDrawingRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var lines = this._source.getLines();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;

      for (var li = 0; li < lines.length; li++) {
        var line = lines[li];
        var x1 = ts.timeToCoordinate(line.time1);
        var x2 = ts.timeToCoordinate(line.time2);
        var y1 = series.priceToCoordinate(line.price1);
        var y2 = series.priceToCoordinate(line.price2);
        if (x1 == null || x2 == null || y1 == null || y2 == null) continue;

        if (line.lineStyle === 1) ctx.setLineDash([4, 4]);
        else if (line.lineStyle === 2) ctx.setLineDash([2, 2]);
        else ctx.setLineDash([]);

        ctx.strokeStyle = line.color || '#FF9800';
        ctx.lineWidth = line.lineWidth || 2;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
      ctx.setLineDash([]);
    });
  }
}

// ==================== 10. TablePrimitive — 表格叠加 ====================

class TablePrimitive extends BasePrimitive {
  constructor() {
    super(); this._table = null;
    this._views = [new TablePaneView(this)];
  }

  setTable(table) { this._table = table; this.requestUpdate(); }
  getTable() { return this._table; }
  paneViews() { return this._views; }
}

class TablePaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'top'; }
  renderer() { return new TableRenderer(this._source); }
}

class TableRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var table = this._source.getTable();
    if (!table || !table.rows) return;

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;
      var w = ctxData.mediaSize.width;
      var cellH = 20;
      var padding = 8;
      var startX = w - 200 - padding;
      var startY = padding;

      // 表头
      if (table.title) {
        ctx.fillStyle = '#f0f3fa';
        ctx.font = 'bold 12px sans-serif';
        ctx.fillText(table.title, startX, startY + 14);
        startY += cellH + 4;
      }

      for (var ri = 0; ri < table.rows.length; ri++) {
        var row = table.rows[ri];
        var cols = Array.isArray(row) ? row : [row];
        var x = startX;

        // 行背景
        ctx.fillStyle = ri % 2 === 0 ? '#1e222d' : '#2a2e39';
        ctx.fillRect(x, startY, 200, cellH);

        for (var ci = 0; ci < cols.length; ci++) {
          var cell = cols[ci];
          if (typeof cell === 'object' && cell !== null) {
            ctx.fillStyle = cell.color || '#d1d4dc';
            ctx.fillText(String(cell.value || ''), x + 4, startY + 14);
          } else {
            ctx.fillStyle = '#d1d4dc';
            ctx.fillText(String(cell || ''), x + 4, startY + 14);
          }
          x += 100;
        }
        startY += cellH + 2;
      }
    });
  }
}

// ==================== 11. CandlePlotPrimitive — 自定义K线 ====================

class CandlePlotPrimitive extends BasePrimitive {
  constructor() {
    super(); this._data = [];
    this._views = [new CandlePlotPaneView(this)];
  }

  setData(data) { this._data = data || []; this.requestUpdate(); }
  getData() { return this._data; }
  paneViews() { return this._views; }
}

class CandlePlotPaneView {
  constructor(source) { this._source = source; }
  zOrder() { return 'normal'; }
  renderer() { return new CandlePlotRenderer(this._source); }
}

class CandlePlotRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
      if (!this._source.isVisible()) return;
    var chart = this._source.getChart();
    var series = this._source.getSeries();
    if (!chart || !series) return;

    var data = this._source.getData();
    var ts = chart.timeScale();

    target.useMediaCoordinateSpace(function(ctxData) {
      var ctx = ctxData.context;
      var w = ctxData.mediaSize.width;
      var bw = getBarWidth(ts, w);
      var halfBw = Math.max(1, bw / 2 - 1);

      for (var i = 0; i < data.length; i++) {
        var cdl = data[i];
        var x = ts.timeToCoordinate(cdl.time);
        if (x == null) continue;

        var yO = series.priceToCoordinate(cdl.open);
        var yH = series.priceToCoordinate(cdl.high);
        var yL = series.priceToCoordinate(cdl.low);
        var yC = series.priceToCoordinate(cdl.close);
        if (yO == null || yH == null || yL == null || yC == null) continue;

        var isUp = cdl.close >= cdl.open;
        var color = isUp ? (cdl.upColor || '#0ecb81') : (cdl.downColor || '#f6465d');
        var bodyTop = Math.min(yO, yC);
        var bodyBot = Math.max(yO, yC);
        var bodyH = Math.max(1, bodyBot - bodyTop);

        ctx.fillStyle = color;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;

        // 影线
        ctx.beginPath();
        ctx.moveTo(x, yH);
        ctx.lineTo(x, bodyTop);
        ctx.moveTo(x, bodyBot);
        ctx.lineTo(x, yL);
        ctx.stroke();

        // 实体
        if (isUp) {
          ctx.fillRect(x - halfBw, bodyTop, halfBw * 2, bodyH);
        } else {
          ctx.fillRect(x - halfBw, bodyTop, halfBw * 2, bodyH);
        }
      }
    });
  }
}

// ==================== 导出声明的基类 ====================

// 导出到全局命名空间
window.Primitives = {
  BasePrimitive: BasePrimitive,
  LineBrPrimitive: LineBrPrimitive,
  CrossPlotPrimitive: CrossPlotPrimitive,
  CirclesPlotPrimitive: CirclesPlotPrimitive,
  BgColorPrimitive: BgColorPrimitive,
  PlotFillPrimitive: PlotFillPrimitive,
  ExtendedMarkerPrimitive: ExtendedMarkerPrimitive,
  LabelPrimitive: LabelPrimitive,
  BoxPrimitive: BoxPrimitive,
  LineDrawingPrimitive: LineDrawingPrimitive,
  TablePrimitive: TablePrimitive,
  CandlePlotPrimitive: CandlePlotPrimitive,
};
