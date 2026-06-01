/**
 * favorites.js — 指标收藏管理
 * 持久化：localStorage + Python 桥接（双向同步）
 */
(function() {
  var STORAGE_KEY = 'tradingview_favorites';
  var _cache = null;

  function load() {
    if (_cache !== null) return _cache;
    try { _cache = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch(e) { _cache = {}; }
    return _cache;
  }

  function save() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(_cache)); } catch(e) {}
    // 同步到 Python 桥接
    try {
      var bc = window.bridgeClient;
      if (bc && bc.bridge && bc.bridge.save_favorites) {
        bc.bridge.save_favorites(JSON.stringify(_cache));
      }
    } catch(e) {}
  }

  window.Favorites = {
    /** 由 Python 端在图表就绪后调用（推送磁盘数据） */
    loadFromPython(jsonStr) {
      if (!jsonStr || jsonStr === '{}') return;
      try {
        _cache = JSON.parse(jsonStr);
        save(); // 写回 localStorage
        console.log('[Fav] Loaded from Python: ' + Object.keys(_cache).length + ' groups');
      } catch(e) {}
    },

    getFor(group) {
      var all = load();
      return all[group] || [];
    },

    getAll() {
      var all = load();
      var merged = [];
      for (var g in all) {
        if (all.hasOwnProperty(g)) {
          for (var i = 0; i < all[g].length; i++) {
            if (merged.indexOf(all[g][i]) < 0) merged.push(all[g][i]);
          }
        }
      }
      return merged;
    },

    toggle(id, group) {
      var all = load();
      if (!all || typeof all !== 'object') { _cache = {}; all = _cache; }
      if (!all[group]) all[group] = [];
      if (!Array.isArray(all[group])) all[group] = [];
      var idx = all[group].indexOf(id);
      if (idx >= 0) all[group].splice(idx, 1);
      else all[group].push(id);
      _cache = all;
      save();
      return idx < 0;
    },

    is(id, group) {
      var all = load();
      if (!all[group]) return false;
      return all[group].indexOf(id) >= 0;
    },
  };
})();
