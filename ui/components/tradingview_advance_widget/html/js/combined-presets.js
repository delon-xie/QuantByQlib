/**
 * CombinedPresets - 组合指标预设。
 * 每个预设作为一个整体切换，而非分别激活多个独立指标。
 * 使用 engine.toggle() 添加子指标，但通过本类跟踪整体状态。
 */
class CombinedPresets {
  constructor() {
    this._active = {}; // {presetKey: true/false}
    this.presets = [
      {
        key: 'ALL_MAS', name: '均线组合',
        description: 'SMA10/20/50/60/200 (单指标渲染, 6周期可配)',
        indicators: [
          { id: 'SMA_Combo', params: { p1:10, p2:20, p3:50, p4:60, p5:200, p6:0 } },
        ],
      },
      {
        key: 'EMA_COMBO', name: 'EMA组合',
        description: 'EMA12/26/50/200 (单指标渲染, 6周期可配)',
        indicators: [
          { id: 'EMA_Combo', params: { p1:12, p2:26, p3:50, p4:200, p5:0, p6:0 } },
        ],
      },
      {
        key: 'SMA_EMA_COMBO', name: 'SMA+EMA组合',
        description: 'SMA20/60/200 + EMA20/50 (前3SMA后3EMA, 6周期可配)',
        indicators: [
          { id: 'SMA_EMA_Combo', params: { p1:20, p2:60, p3:200, p4:20, p5:50, p6:0 } },
        ],
      },
      {
        key: 'MOMENTUM_SUITE', name: '动量套件',
        description: 'MACD + RSI + Stochastic (复合指标，不与独立 MACD/RSI/Stoch 冲突)',
        indicators: [
          { id: 'MomentumSuite', params: {} },
        ],
      },
      {
        key: 'VOLATILITY', name: '波动率套件',
        description: 'BollingerBands + ATR (复合指标，不与独立 ATR/BB 冲突)',
        indicators: [
          { id: 'VolatilitySuite', params: {} },
        ],
      },
      {
        key: 'TREND_FOLLOW', name: '趋势跟踪',
        description: 'ADX + SuperTrend + EMA50 (复合指标，不与独立 ADX 冲突)',
        indicators: [
          { id: 'TrendFollowSuite', params: {} },
        ],
      },
    ];
  }

  getPresets() { return this.presets; }
  isActive(key) { return this._active[key] === true; }
  _lookupPreset(key) {
    for (var i = 0; i < this.presets.length; i++) {
      if (this.presets[i].key === key) return this.presets[i];
    }
    return null;
  }

  /**
   * toggle — 切换预设整体开关
   * 开启: 添加所有子指标，标记为活跃
   * 关闭: 移除所有子指标，标记为不活跃
   */
  toggle(key) {
    var preset = null;
    for (var i = 0; i < this.presets.length; i++) {
      if (this.presets[i].key === key) { preset = this.presets[i]; break; }
    }
    if (!preset) return;

    var engine = window.indicatorEngine;
    if (!engine) return;

    if (this._active[key]) {
      // 关闭: 移除所有子指标
      for (var ii = 0; ii < preset.indicators.length; ii++) {
        var ind = preset.indicators[ii];
        // 尝试先通过 alias id 移除
        var r = engine._resolveAlias ? engine._resolveAlias(ind.id, ind.params || {}) : null;
        if (r && engine.getVisibleMap().has(r.id)) {
          engine.remove(r.id);
        } else if (engine.getVisibleMap().has(ind.id)) {
          engine.remove(ind.id);
        } else {
          // 尝试通过 catalog entry id 移除
          var entry = engine._findCatalogEntry ? engine._findCatalogEntry(ind.id) : null;
          if (entry && engine.getVisibleMap().has(entry.id)) {
            engine.remove(entry.id);
          }
        }
      }
      this._active[key] = false;
      console.log('Preset off: ' + preset.name);
    } else {
      // 开启: 逐个添加
      for (var ii = 0; ii < preset.indicators.length; ii++) {
        var ind = preset.indicators[ii];
        // 检查是否真正可见（get()===true），而非仅检查 key 是否存在（has()）
        // 避免已隐藏的指标（visibleMap 值为 false）被跳过导致首次点击无效
        if (engine.getVisibleMap().get(ind.id) !== true) {
          engine.toggle(ind.id, ind.params || {});
        }
      }
      this._active[key] = true;
      console.log('Preset on: ' + preset.name);
    }
    if (window.chartManager) window.chartManager.fitContent();
  }
}

window.combinedPresets = new CombinedPresets();
window.CombinedPresets = CombinedPresets;
