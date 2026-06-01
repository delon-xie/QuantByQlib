/**
 * JSStateManager - 前端状态序列化。
 * 记录活跃指标、参数、可见范围，支持序列化/反序列化。
 */
class JSStateManager {
  constructor() {
    this.activeIndicators = new Map();
  }

  update(id, params, group) {
    this.activeIndicators.set(id, { params: Object.assign({}, params), group: group });
  }

  remove(id) {
    this.activeIndicators.delete(id);
  }

  serialize() {
    var indicators = {};
    for (var entry of this.activeIndicators) {
      indicators[entry[0]] = { params: entry[1].params, group: entry[1].group };
    }
    var range = window.chartManager ? window.chartManager.getVisibleRange() : null;
    return {
      version: 2,
      indicators: indicators,
      chart_range: range,
      drawings: window.drawingTools ? window.drawingTools.export() : [],
      timeframe: window.timeframeController ? window.timeframeController.getCurrentTf() : 'D',
      timestamp: new Date().toISOString(),
    };
  }

  syncFromEngine() {
    this.activeIndicators.clear();
    var engine = window.indicatorEngine;
    if (engine) {
      engine._activeMap.forEach(function(info, sid) {
        var entry = engine._findCatalogEntry(sid);
        this.activeIndicators.set(sid, {
          params: info.params || {},
          group: entry && entry.group || 'unknown',
        });
      }.bind(this));
    }
  }
}

window.jsStateManager = new JSStateManager();
window.JSStateManager = JSStateManager;
