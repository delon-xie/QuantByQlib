/**
 * indicator-catalog.js — Catalog 构建与查找，扩展 IndicatorEngine.prototype
 *
 * 从 indicator-engine.js 提取的 catalog 相关方法。
 * 使用 prototype 扩展模式，运行时依赖 IndicatorEngine 构造函数中定义的
 * this._catalog, this._indicators, this._activeMap, this._visibleMap,
 * this._computeSource 等属性。
 */

/* eslint-disable no-unused-vars */

IndicatorEngine.prototype._findCalc = function(lci, name) {
  if (!name) return null;
  var normName = function(s) { return (s || '').toLowerCase().replace(/[-_\s]/g, ''); };
  var nName = normName(name);
  var variants = [name, name.charAt(0).toUpperCase() + name.slice(1)];
  for (var i = 0; i < variants.length; i++) {
    var f = lci[variants[i]];
    if (f && f.calculate) return f;
  }
  for (var k in lci) {
    if (k === 'indicatorRegistry' || k === 'version') continue;
    var c = lci[k];
    if (c && c.calculate) {
      if (k.toLowerCase() === name.toLowerCase() || normName(k) === nName) return c;
      var m = c.metadata;
      if (m) {
        if (m.shortTitle && (m.shortTitle.toLowerCase() === name.toLowerCase() || normName(m.shortTitle) === nName)) return c;
        if (m.title && (m.title.toLowerCase().indexOf(name.toLowerCase()) >= 0 || normName(m.title).indexOf(nName) >= 0)) return c;
      }
    }
  }
  return null;
};

IndicatorEngine.prototype._buildCatalog = function() {
  var reg = this._indicators.indicatorRegistry;
  if (!reg) return;
  var self = this;
  reg.forEach(function(e) {
    var fn = self._findCalc(self._indicators, e.id);
    if (!fn && e.name) fn = self._findCalc(self._indicators, e.name);
    if (!fn && e.shortName) fn = self._findCalc(self._indicators, e.shortName);
    if (!fn) return;
    var m = fn.metadata || {};
    var name = (function(x) {
      for (var k in self._indicators) { if (self._indicators[k] === x) return k; }
      return e.id;
    })(fn);
    self._catalog.push({
      id: name, name: m.title || e.name || name, shortName: m.shortTitle || e.shortName || name,
      group: e.group || 'community', category: e.category || 'Other',
      overlay: (m.overlay !== undefined) ? m.overlay : (e.overlay !== false),
      inputs: fn.inputConfig || [], plots: fn.plotConfig || [],
      defaults: fn.defaultInputs || {},
      hlineConfig: fn.hlineConfig || null, fillConfig: fn.fillConfig || null,
      calculate: fn.calculate,
    });
  });
  console.log('Catalog built: ' + this._catalog.length + ' indicators');
  // 添加自定义组合指标的 catalog 条目（用于参数面板渲染）
  this._catalog.push({
    id: 'SMA_Combo', name: 'SMA Combo', shortName: 'SMA Combo',
    group: 'standard', category: 'Moving Averages', overlay: true,
    inputs: [
      { id: 'p1', type: 'int', title: 'SMA Period 1', defval: 10, min: 0 },
      { id: 'p2', type: 'int', title: 'SMA Period 2', defval: 20, min: 0 },
      { id: 'p3', type: 'int', title: 'SMA Period 3', defval: 50, min: 0 },
      { id: 'p4', type: 'int', title: 'SMA Period 4', defval: 60, min: 0 },
      { id: 'p5', type: 'int', title: 'SMA Period 5', defval: 200, min: 0 },
      { id: 'p6', type: 'int', title: 'SMA Period 6', defval: 0, min: 0 },
    ],
    plots: [], defaults: { p1:10, p2:20, p3:50, p4:60, p5:200, p6:0 },
    hlineConfig: null, fillConfig: null, calculate: null,
  });
  this._catalog.push({
    id: 'EMA_Combo', name: 'EMA Combo', shortName: 'EMA Combo',
    group: 'standard', category: 'Moving Averages', overlay: true,
    inputs: [
      { id: 'p1', type: 'int', title: 'EMA Period 1', defval: 12, min: 0 },
      { id: 'p2', type: 'int', title: 'EMA Period 2', defval: 26, min: 0 },
      { id: 'p3', type: 'int', title: 'EMA Period 3', defval: 50, min: 0 },
      { id: 'p4', type: 'int', title: 'EMA Period 4', defval: 200, min: 0 },
      { id: 'p5', type: 'int', title: 'EMA Period 5', defval: 0, min: 0 },
      { id: 'p6', type: 'int', title: 'EMA Period 6', defval: 0, min: 0 },
    ],
    plots: [], defaults: { p1:12, p2:26, p3:50, p4:200, p5:0, p6:0 },
    hlineConfig: null, fillConfig: null, calculate: null,
  });
  this._catalog.push({
    id: 'SMA_EMA_Combo', name: 'SMA EMA Combo', shortName: 'SMA EMA Combo',
    group: 'standard', category: 'Moving Averages', overlay: true,
    inputs: [
      { id: 'p1', type: 'int', title: 'SMA Period 1', defval: 20, min: 0 },
      { id: 'p2', type: 'int', title: 'SMA Period 2', defval: 60, min: 0 },
      { id: 'p3', type: 'int', title: 'SMA Period 3', defval: 200, min: 0 },
      { id: 'p4', type: 'int', title: 'EMA Period 1', defval: 20, min: 0 },
      { id: 'p5', type: 'int', title: 'EMA Period 2', defval: 50, min: 0 },
      { id: 'p6', type: 'int', title: 'EMA Period 3', defval: 0, min: 0 },
    ],
    plots: [], defaults: { p1:20, p2:60, p3:200, p4:20, p5:50, p6:0 },
    hlineConfig: null, fillConfig: null, calculate: null,
  });
};

IndicatorEngine.prototype.setComputeSource = function(source) {
  if (['js', 'python', 'auto'].indexOf(source) >= 0) {
    this._computeSource = source;
    console.log('IndicatorEngine: compute source set to ' + source);
  }
};

IndicatorEngine.prototype._requestPythonFallback = function(id, params) {
  var bc = window.bridgeClient;
  if (!bc || !bc.bridge) { console.warn('Python fallback unavailable: no bridge'); return; }
  console.log('Requesting Python fallback for: ' + id);
  bc.requestPythonIndicator(id, JSON.stringify(params || {}));
};

IndicatorEngine.prototype._requestPythonOnly = function(id, params) {
  if (!this._activeMap.has(id)) { this._register(id, params, 'PYTHON', []); }
  this._requestPythonFallback(id, params);
};

IndicatorEngine.prototype.debug = function() {
  var info = { catalogSize: this._catalog.length, activeCount: this._activeMap.size, visibleCount: 0, computeSource: this._computeSource, groups: {}, activeIndicators: [], lciKeys: [] };
  this._visibleMap.forEach(function(v, k) { if (v) info.visibleCount++; });
  for (var i = 0; i < this._catalog.length; i++) {
    var ind = this._catalog[i];
    if (!info.groups[ind.group]) info.groups[ind.group] = 0;
    info.groups[ind.group]++;
  }
  this._activeMap.forEach(function(v, k) { info.activeIndicators.push({ id: k, params: v.params, overlay: v.overlay }); });
  if (window.LightweightChartsIndicators) {
    info.lciKeys = Object.keys(window.LightweightChartsIndicators).filter(function(k) { return k !== 'indicatorRegistry' && k !== 'version'; });
  }
  return info;
};

IndicatorEngine.prototype._resolveAlias = function(id, params) {
  params = params || {};
  var m = id.match(/^([A-Za-z]+)_(\d+)$/);
  if (m) {
    var entry = this._findCatalogEntry(m[1]);
    // Verify catalog entry: if LCI has a direct key, prefer it as authoritative
    var baseKey = m[1];
    if (this._indicators && this._indicators[baseKey] && this._indicators[baseKey].calculate) {
      // Use the authoritative LCI function directly
      var lciFn = this._indicators[baseKey];
      var p = {};
      for (var k in lciFn.defaultInputs) if (lciFn.defaultInputs.hasOwnProperty(k)) p[k] = lciFn.defaultInputs[k];
      var found = false;
      for (var k2 in lciFn.defaultInputs) { if (typeof lciFn.defaultInputs[k2] === 'number') { p[k2] = parseInt(m[2], 10); found = true; break; } }
      if (!found) for (var ii = 0; ii < (lciFn.inputConfig || []).length; ii++) { var inp = lciFn.inputConfig[ii]; if (inp.type === 'int' || inp.type === 'float') { p[inp.id] = parseInt(m[2], 10); break; } }
      for (var k3 in params) if (params.hasOwnProperty(k3)) p[k3] = params[k3];
      return { id: id, baseId: baseKey, params: p };
    }
    if (entry) {
      var p = {};
      for (var k in entry.defaults) if (entry.defaults.hasOwnProperty(k)) p[k] = entry.defaults[k];
      var found = false;
      for (var k2 in entry.defaults) { if (typeof entry.defaults[k2] === 'number') { p[k2] = parseInt(m[2], 10); found = true; break; } }
      if (!found) for (var ii = 0; ii < (entry.inputs || []).length; ii++) { var inp = entry.inputs[ii]; if (inp.type === 'int' || inp.type === 'float') { p[inp.id] = parseInt(m[2], 10); break; } }
      for (var k3 in params) if (params.hasOwnProperty(k3)) p[k3] = params[k3];
      return { id: id, baseId: entry.id, params: p };
    }
  }
  return { id: id, baseId: id, params: params };
};

IndicatorEngine.prototype._findCatalogEntry = function(id) {
  if (this._catalog.length === 0 && this._indicators && this._indicators.indicatorRegistry) { this._buildCatalog(); }
  // Tier 1: strict exact match on id (highest priority — prevents %B variants shadowing the real indicator)
  for (var i = 0; i < this._catalog.length; i++) { var c = this._catalog[i]; if (c.id === id) return c; }
var clean = function(s) { return (s || '').toLowerCase().replace(/[-_\s()\[\]{}]/g, ''); };
  var target = clean(id);
  // Tier 2: cleaned id/shortName/name exact match
  for (var i = 0; i < this._catalog.length; i++) { var c = this._catalog[i]; if (clean(c.id) === target || clean(c.shortName) === target || clean(c.name) === target) return c; }
  var minRatio = 0.5;
  for (var i = 0; i < this._catalog.length; i++) {
    var c = this._catalog[i], cId = clean(c.id), cShort = clean(c.shortName), cName = clean(c.name);
    if ((cShort?.length > 0 && target.length / cShort.length >= minRatio && (cShort.indexOf(target) >= 0 || target.indexOf(cShort) >= 0)) ||
        (cName?.length > 0 && target.length / cName.length >= minRatio && (cName.indexOf(target) >= 0 || target.indexOf(cName) >= 0)) ||
        (cId.length > 0 && target.length / cId.length >= minRatio && (cId.indexOf(target) >= 0 || target.indexOf(cId) >= 0))) return c;
  }
  var lci = this._indicators;
  if (lci) {
    if (lci[id] && lci[id].calculate) { var e = lci[id], m = e.metadata || {}; this._catalog.push({ id: id, name: m.title || id, shortName: m.shortTitle || id, overlay: m.overlay !== false, inputs: e.inputConfig || [], plots: e.plotConfig || [], defaults: e.defaultInputs || {}, hlineConfig: e.hlineConfig || null, fillConfig: e.fillConfig || null, calculate: e.calculate }); return this._catalog[this._catalog.length - 1]; }
    for (var k in lci) { if (k === 'indicatorRegistry' || k === 'version' || k.indexOf('calculate') === 0) continue; var c = lci[k]; if (c && c.calculate) { if (clean(k) === target || clean(c.metadata?.shortTitle || '') === target || clean(c.metadata?.title || '') === target) { var m2 = c.metadata || {}; this._catalog.push({ id: k, name: m2.title || k, shortName: m2.shortTitle || k, group: 'standard', category: m2.category || 'Other', overlay: m2.overlay !== false, inputs: c.inputConfig || [], plots: c.plotConfig || [], defaults: c.defaultInputs || {}, hlineConfig: c.hlineConfig || null, fillConfig: c.fillConfig || null, calculate: c.calculate }); return this._catalog[this._catalog.length - 1]; } } }
  }
  return null;
};
