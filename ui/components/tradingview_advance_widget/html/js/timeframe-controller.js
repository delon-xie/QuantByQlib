/**
 * timeframe-controller.js — 日线/周线/月线时间周期切换
 * 管理三个周期的 OHLC 数据聚合与切换。
 */

/**
 * 按周期聚合 OHLC 数据
 * @param {Array} dailyBars - [{time, open, high, low, close, volume}, ...]
 * @param {string} tf - 'D' | 'W' | 'M'
 * @returns {Array} 聚合后的 bars
 */
function aggregateOHLC(dailyBars, tf) {
  if (tf === 'D' || !dailyBars || dailyBars.length === 0) return dailyBars;
  var groups = new Map();
  for (var i = 0; i < dailyBars.length; i++) {
    var bar = dailyBars[i];
    var key = getPeriodKey(bar.time, tf);
    if (!groups.has(key)) {
      groups.set(key, {
        time: bar.time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume || 0,
      });
    } else {
      var g = groups.get(key);
      if (bar.high > g.high) g.high = bar.high;
      if (bar.low < g.low) g.low = g.low;
      g.close = bar.close;
      g.volume = (g.volume || 0) + (bar.volume || 0);
      g.time = bar.time;
    }
  }
  return Array.from(groups.values());
}

/** 获取周期 key（用于分组） */
function getPeriodKey(time, tf) {
  var d = new Date(time);
  if (tf === 'M') {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
  }
  if (tf === 'W') {
    // ISO 周号
    var temp = new Date(d.valueOf());
    var dayNum = (d.getDay() + 6) % 7;
    temp.setDate(temp.getDate() - dayNum + 3);
    var firstThursday = temp.valueOf();
    temp.setMonth(0, 1);
    if (temp.getDay() !== 4) {
      temp.setMonth(0, 1 + ((4 - temp.getDay()) + 7) % 7);
    }
    var weekNum = 1 + Math.ceil((firstThursday - temp) / 604800000);
    return temp.getFullYear() + '-W' + String(weekNum).padStart(2, '0');
  }
  return time;
}

/**
 * TimeframeController — 管理日/周/月线数据切换 + 指标状态记录器
 */
class TimeframeController {
  constructor() {
    this._dailyBars = null;
    this._weeklyBars = null;
    this._monthlyBars = null;
    this._currentTf = 'D';
    this._busy = false;
    /** 指标状态记录器: [{id, params, isPython}] 或 null */
    this._savedIndicators = null;
  }

  // ==================== 原始数据 + 聚合 ====================

  /** 由 bridge-client 在数据加载后调用（新股票数据到达） */
  setOriginalBars(dailyBars) {
    // 保存当前时间周期（复权切换时保持当前视图）
    var previousTf = this._currentTf;
    
    this._dailyBars = dailyBars;
    this._weeklyBars = aggregateOHLC(dailyBars, 'W');
    this._monthlyBars = aggregateOHLC(dailyBars, 'M');
    
    // 数据量不足时禁用按钮
    this._updateButtonState();
    
    // 如果之前在周线或月线视图，检查数据是否足够
    var canRestoreTf = previousTf;
    if (previousTf === 'W' && (!this._weeklyBars || this._weeklyBars.length < 2)) {
      canRestoreTf = 'D';
    } else if (previousTf === 'M' && (!this._monthlyBars || this._monthlyBars.length < 2)) {
      canRestoreTf = 'D';
    }
    
    // 如果当前时间周期不可用，回退到日线
    if (canRestoreTf !== previousTf) {
      console.log('[TF] Previous timeframe ' + previousTf + ' not available, falling back to D');
    }
    
    this._currentTf = canRestoreTf;
    this._activateButton(canRestoreTf);
    
    // 如果不是日线视图，需要切换图表到对应周期的数据
    if (canRestoreTf !== 'D') {
      this._applyTimeframeData(canRestoreTf);
    }
    
    console.log('[TF] Initialized: D=' + dailyBars.length + ' W=' + (this._weeklyBars ? this._weeklyBars.length : 0) + ' M=' + (this._monthlyBars ? this._monthlyBars.length : 0) + ', currentTf=' + this._currentTf);
  }
  
  /** 应用指定时间周期的数据到图表（复权切换时使用） */
  _applyTimeframeData(tf) {
    var cm = window.chartManager;
    var ie = window.indicatorEngine;
    if (!cm || !ie) return;
    
    var barsMap = { D: this._dailyBars, W: this._weeklyBars, M: this._monthlyBars };
    var bars = barsMap[tf];
    if (!bars) return;
    
    console.log('[TF] Applying ' + tf + ' timeframe data (' + bars.length + ' bars)');
    
    // 更新图表数据
    cm.setCandleData(bars);
    ie.barData = bars;
    
    // 同步当前周期数据到 Python 端
    var bc = window.bridgeClient;
    if (bc && bc.setTimeframeData) {
      bc.setTimeframeData(JSON.stringify(bars));
    }
    
    // 最优适配显示
    try { cm.mainChart.timeScale().fitContent(); } catch (e) { console.warn('[TF] fitContent failed:', e.message); }
  }

  getCurrentTf() { return this._currentTf; }

  // ==================== 指标状态记录器 ====================

  /**
   * 保存当前活跃指标（在清空 _activeMap 之前调用）
   * 三种场景：
   *   A) 切换股票 → 由 bridge-client 在 _handleSetChartData 中调用
   *   B) 切换时间框架 → 由 setTimeframe 内部调用
   *   C) 双重切换 → save 一次，restore 一次（新股票日线数据就绪后）
   */
  saveActiveIndicators() {
    var ie = window.indicatorEngine;
    if (!ie) { this._savedIndicators = null; return; }
    var saved = [];
    ie._activeMap.forEach(function(info, sid) {
      // 只记录当前可见（visible=true）的指标，忽略已隐藏的
      if (ie._visibleMap.get(sid) !== true) return;
      var entry = ie._findCatalogEntry(sid);
      saved.push({
        id: sid,
        params: info.params || {},
        isPython: !entry,
      });
    });
    
    // 也保存组合预设状态
    var savedCombos = [];
    if (window.combinedPresets && window.combinedPresets._active) {
      for (var key in window.combinedPresets._active) {
        if (window.combinedPresets._active[key]) {
          savedCombos.push(key);
        }
      }
    }
    
    this._savedIndicators = saved.length > 0 ? saved : null;
    this._savedCombos = savedCombos.length > 0 ? savedCombos : null;
    
    if (this._savedIndicators) {
      console.log('[TF] Saved ' + this._savedIndicators.length + ' active indicators');
    }
    if (this._savedCombos) {
      console.log('[TF] Saved ' + this._savedCombos.length + ' combo presets: ' + savedCombos.join(','));
    }
  }

  /**
   * 在数据就绪 + fitContent 后调用，重建指标。
   * 如果 _savedIndicators 不为空，逐一重算。
   */
  restoreActiveIndicators() {
    var ie = window.indicatorEngine;
    
    // 先恢复组合预设（强制重新计算）
    if (this._savedCombos && window.combinedPresets) {
      var savedCombos = this._savedCombos;
      this._savedCombos = null;
      console.log('[TF] Recalculating ' + savedCombos.length + ' combo presets...');
      
      // 先关闭所有已激活的组合预设（确保干净状态）
      if (window.combinedPresets._active) {
        for (var activeKey in window.combinedPresets._active) {
          if (window.combinedPresets._active[activeKey]) {
            window.combinedPresets.toggle(activeKey);
          }
        }
      }
      
      // 然后重新添加保存的组合预设（会用新数据重新计算）
      for (var i = 0; i < savedCombos.length; i++) {
        var preset = savedCombos[i];
        console.log('[TF] Re-adding combo preset: ' + preset);
        window.combinedPresets.toggle(preset);
      }
    }
    
    // 然后恢复普通指标（强制重新计算）
    if (!this._savedIndicators) return;
    if (!ie) return;
    var saved = this._savedIndicators;
    this._savedIndicators = null;

    console.log('[TF] Recalculating ' + saved.length + ' indicators...');
    
    // 先清除所有已激活的指标（确保干净状态）
    ie._activeMap.forEach(function(info, sid) {
      ie.remove(sid);
    });
    ie._activeMap.clear();
    ie._visibleMap.clear();
    
    // 然后重新添加保存的指标（会用新数据重新计算）
    for (var i = 0; i < saved.length; i++) {
      var item = saved[i];
      if (item.isPython) {
        // 将当前时间框架的数据一起发给 Python，确保数据在计算请求之前就绪
        var bars = this._getCurrentBars();
        if (bars && bars.length > 0 && window.bridgeClient) {
          window.bridgeClient.requestPythonIndicator(
            item.id,
            JSON.stringify({
              params: item.params || {},
              _bars: bars,  // 内联当前周期数据，避免异步竞争
            })
          );
          console.log('[TF] Requested Python calc ' + item.id + ' with ' + bars.length + ' bars');
        }
      } else {
        ie.calculateAndAdd(item.id, item.params);
      }
    }
    // 刷新面板以反映重建后的激活状态
    if (window.indicatorPanel) window.indicatorPanel.refresh();
  }

  /** 获取当前时间框架的 bars 数据 */
  _getCurrentBars() {
    var map = { D: this._dailyBars, W: this._weeklyBars, M: this._monthlyBars };
    return map[this._currentTf] || null;
  }

  // ==================== 时间框架切换 ====================

  /** 切换时间周期 — 保存指标 → 切换数据 → fitContent → 重建指标 */
  setTimeframe(tf) {
    if (this._busy || tf === this._currentTf) return;
    this._busy = true;

    var cm = window.chartManager;
    var ie = window.indicatorEngine;
    if (!cm || !ie) { this._busy = false; return; }

    var barsMap = { D: this._dailyBars, W: this._weeklyBars, M: this._monthlyBars };
    var bars = barsMap[tf];
    if (!bars) { this._busy = false; return; }

    try {
      // 1. 保存当前活跃指标
      this.saveActiveIndicators();

      // 2. 清空所有指标 + 重置状态
      ie._activeMap.clear();
      ie._visibleMap.clear();
      ie._candlestickCounts = {};
      cm.clearAll();
      if (window.jsStateManager) window.jsStateManager.activeIndicators.clear();
      if (window.combinedPresets) window.combinedPresets._active = {};

      // 3. 加载新周期数据
      cm.setCandleData(bars);
      ie.barData = bars;

      // 4. 同步当前周期数据到 Python 端（无论有无 Python 指标，保证 _current_df 同步）
      var bc = window.bridgeClient;
      if (bc && bc.setTimeframeData) {
        bc.setTimeframeData(JSON.stringify(bars));
      }

      // 5. 最优适配显示
      try { cm.mainChart.timeScale().fitContent(); } catch (e) { console.warn('[TF] fitContent failed:', e.message); }

      // 6. 更新按钮状态
      this._currentTf = tf;
      this._activateButton(tf);

      // 7. 重建保存的指标
      this.restoreActiveIndicators();

      console.log('[TF] Switched to ' + tf + ' (' + bars.length + ' bars), restored ' + (this._savedIndicators ? '(deferred)' : '0') + ' indicators');
    } catch (e) {
      console.error('[TF] setTimeframe error:', e.message);
    } finally {
      this._busy = false;
    }
  }

  // ==================== UI ====================

  /** 按钮样式切换 */
  _activateButton(tf) {
    var bar = document.getElementById('timeframe-bar');
    if (!bar) return;
    var btns = bar.querySelectorAll('.tf-btn');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('active', btns[i].getAttribute('data-tf') === tf);
    }
  }

  /** 数据量不足时禁用周/月按钮 */
  _updateButtonState() {
    var bar = document.getElementById('timeframe-bar');
    if (!bar) return;
    var btns = bar.querySelectorAll('.tf-btn');
    for (var i = 0; i < btns.length; i++) {
      var tf = btns[i].getAttribute('data-tf');
      if (tf === 'D') continue;
      var count = tf === 'W' ? (this._weeklyBars ? this._weeklyBars.length : 0) : (this._monthlyBars ? this._monthlyBars.length : 0);
      var disabled = count < 2;
      btns[i].disabled = disabled;
      btns[i].title = disabled ? ('Need more daily data (' + (tf === 'W' ? 10 : 30) + '+ days) for ' + (tf === 'W' ? 'weekly' : 'monthly') + ' view') : '';
      btns[i].style.opacity = disabled ? '0.3' : '1';
      btns[i].style.cursor = disabled ? 'not-allowed' : 'pointer';
    }
  }
}

window.timeframeController = new TimeframeController();
