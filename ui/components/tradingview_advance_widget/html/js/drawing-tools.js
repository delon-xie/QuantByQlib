/**
 * DrawingTools - 绘图基元。
 * 支持水平线、竖直线、趋势线、矩形、标签。
 */
class DrawingTools {
  constructor(chartManager) {
    this.cm = chartManager;
    this.drawings = new Map();
    this.activeTool = null;
    this.tempPoints = [];
  }

  enableTool(type) {
    this.activeTool = type;
    this.tempPoints = [];
  }

  disableTool() {
    this.activeTool = null;
    this.tempPoints = [];
  }

  drawHorizontalLine(price, color, label) {
    color = color || '#2962FF';
    label = label || '';
    var id = 'hline_' + Date.now();
    var series = this.cm.mainChart.addLineSeries({
      color: color, lineWidth: 1, lineStyle: 2,
      lastValueVisible: !!label,
      priceLineVisible: false,
    });
    var candleData = this.cm.candleSeries ? this.cm.candleSeries.data() : [];
    if (candleData.length > 0) {
      series.setData([
        { time: candleData[0].time, value: price },
        { time: candleData[candleData.length - 1].time, value: price },
      ]);
    }
    this.drawings.set(id, { type: 'hline', series: series });
    return id;
  }

  drawVerticalLine(time, color, label) {
    color = color || '#f6465d';
    label = label || '';
    var id = 'vline_' + Date.now();
    var marker = { time: time, position: 'inBar', color: color, shape: 'circle', text: label };
    if (this.cm.candleSeries && this.cm.candleSeries.setMarkers) {
      this.cm.candleSeries.setMarkers([marker]);
    }
    this.drawings.set(id, { type: 'vline', marker: marker });
    return id;
  }

  drawTrendLine(x1, y1, x2, y2, color) {
    color = color || '#FF9800';
    var id = 'trend_' + Date.now();
    var series = this.cm.mainChart.addLineSeries({
      color: color, lineWidth: 2,
      lastValueVisible: false, priceLineVisible: false,
    });
    series.setData([
      { time: x1, value: y1 },
      { time: x2, value: y2 },
    ]);
    this.drawings.set(id, { type: 'trend', series: series });
    return id;
  }

  drawRectangle(x1, y1, x2, y2, color, fill) {
    color = color || '#2962FF';
    fill = fill || '#2962FF20';
    var id = 'rect_' + Date.now();
    var top = Math.max(y1, y2);
    var bottom = Math.min(y1, y2);
    var left = x1 < x2 ? x1 : x2;
    var right = x1 < x2 ? x2 : x1;
    var cm = this.cm;
    var opts = {
      color: color, lineWidth: 1, lastValueVisible: false, priceLineVisible: false,
    };
    var topS = cm.mainChart.addLineSeries(opts);
    var botS = cm.mainChart.addLineSeries(opts);
    var leftS = cm.mainChart.addLineSeries(opts);
    var rightS = cm.mainChart.addLineSeries(opts);
    topS.setData([{ time: left, value: top }, { time: right, value: top }]);
    botS.setData([{ time: left, value: bottom }, { time: right, value: bottom }]);
    leftS.setData([{ time: left, value: top }, { time: left, value: bottom }]);
    rightS.setData([{ time: right, value: top }, { time: right, value: bottom }]);
    this.drawings.set(id, { type: 'rect', series: [topS, botS, leftS, rightS] });
    return id;
  }

  drawLabel(time, price, text, color) {
    color = color || '#2962FF';
    var id = 'label_' + Date.now();
    var marker = { time: time, position: 'aboveBar', color: color, shape: 'arrowUp', text: text };
    if (this.cm.candleSeries && this.cm.candleSeries.setMarkers) {
      this.cm.candleSeries.setMarkers([marker]);
    }
    this.drawings.set(id, { type: 'label', marker: marker });
    return id;
  }

  clearAll() {
    for (var entry of this.drawings) {
      var drawing = entry[1];
      if (drawing.series) {
        var arr = Array.isArray(drawing.series) ? drawing.series : [drawing.series];
        for (var i = 0; i < arr.length; i++) {
          try { this.cm.mainChart.removeSeries(arr[i]); } catch (e) {}
        }
      }
    }
    this.drawings.clear();
    if (this.cm.candleSeries && this.cm.candleSeries.setMarkers) {
      this.cm.candleSeries.setMarkers([]);
    }
  }

  export() {
    var result = [];
    for (var entry of this.drawings) {
      var dw = entry[1];
      var obj = { id: entry[0], type: dw.type };
      if (dw.marker) obj.marker = dw.marker;
      if (dw.color) obj.color = dw.color;
      if (dw.label) obj.label = dw.label;
      if (dw.x1 !== undefined) { obj.x1 = dw.x1; obj.y1 = dw.y1; obj.x2 = dw.x2; obj.y2 = dw.y2; }
      if (dw.price !== undefined) obj.price = dw.price;
      if (dw.time !== undefined) obj.time = dw.time;
      if (dw.text !== undefined) obj.text = dw.text;
      if (dw.fill) obj.fill = dw.fill;
      result.push(obj);
    }
    return result;
  }

  /** 从保存的数据恢复全部画线 */
  import(drawings) {
    if (!drawings || !drawings.length) return;
    for (var i = 0; i < drawings.length; i++) {
      var d = drawings[i];
      switch (d.type) {
        case 'hline':
          this.drawHorizontalLine(d.price, d.color, d.label);
          break;
        case 'vline':
          this.drawVerticalLine(d.time, d.color, d.label);
          break;
        case 'trend':
          this.drawTrendLine(d.x1, d.y1, d.x2, d.y2, d.color);
          break;
        case 'rect':
          this.drawRectangle(d.x1, d.y1, d.x2, d.y2, d.color, d.fill);
          break;
        case 'label':
          this.drawLabel(d.time, d.price, d.text, d.color);
          break;
      }
    }
  }
}

window.drawingTools = null;
window.DrawingTools = DrawingTools;
