/**
 * IndicatorPanel — 右侧指标面板（4 Tab + 内联参数）
 * Tab: 常用 | 标准 | 社区 | K线
 * 点击指标切换图表显示，参数面板就地展开
 */
class IndicatorPanel {
  constructor(container) {
    this.container = container;
    this.activeTab = 0;
    this._tabKeys = ['quick', 'standard', 'community', 'candlestick'];
    this._render();
  }

  /** 翻译简写 */
  _t(key) {
    var i18n = window.i18n;
    return i18n ? i18n.t(key) : key;
  }

  _indicatorName(id, fallback) {
    var i18n = window.i18n;
    return i18n && i18n.indicatorName ? i18n.indicatorName(id, fallback) : (fallback || id);
  }

  // ==================== 渲染 ====================

  _render() {
    var tabKeys = ['section.quick', 'section.standard', 'section.community', 'section.candlestick'];
    var tabsHtml = '';
    for (var i = 0; i < tabKeys.length; i++) {
      tabsHtml += '<div class="panel-tab' + (i === 0 ? ' active' : '') + '" data-tab="' + i + '">' + this._t(tabKeys[i]) + '</div>';
    }
    // 语言切换按钮放在 tab 栏末尾
    tabsHtml += '<div class="panel-tab lang-toggle" id="panelLangToggle">' + this._t('lang.toggle') + '</div>';

    this.container.innerHTML = '<div class="panel-tabs">' + tabsHtml + '</div>'
      + '<div class="panel-content active" data-tab-content="0"></div>'
      + '<div class="panel-content" data-tab-content="1"></div>'
      + '<div class="panel-content" data-tab-content="2"></div>'
      + '<div class="panel-content" data-tab-content="3"></div>';

    this._bindTabEvents();
    this._bindLangToggle();
    // 监听收藏变化，刷新常用 Tab
    var self4 = this;
    document.addEventListener('favorite-changed', function() {
      var qc = self4.container.querySelector('[data-tab-content="0"]');
      if (qc) {
        if (window.Favorites && window.Favorites.getAll().length > 0) {
          qc.innerHTML = self4._renderQuick();
          self4._bindContentEvents(0);
        } else {
          // 收藏为空，移除收藏区域
          var favSec = qc.querySelector('#favs-section');
          if (favSec) favSec.remove();
        }
      }
    });
    // 渲染初始 tab
    this._renderTab(0, '');
  }

  _renderTab(index, query) {
    var content = this.container.querySelector('[data-tab-content="' + index + '"]');
    if (!content) return;
    // 搜索缓存：相同搜索词跳过渲染及事件绑定（仅限有搜索的 Tab，不影响 Quick tab）
    if (index > 0 && this._lastSearchTab === index && this._lastSearchQuery === query) return;
    // 保存滚动位置
    var savedScroll = content.scrollTop;
    switch (index) {
      case 0: content.innerHTML = this._renderQuick(); break;
      case 1: content.innerHTML = this._renderList('standard', query); break;
      case 2: content.innerHTML = this._renderList('community', query); break;
      case 3: content.innerHTML = this._renderList('candlestick', query); break;
    }
    this._bindContentEvents(index);
    // 恢复滚动位置
    content.scrollTop = savedScroll;
    this._lastSearchTab = index;
    this._lastSearchQuery = query;
    // 保存搜索词到 Tab 缓存（切换 Tab 时恢复用）
    if (!this._tabSearchCache) this._tabSearchCache = {};
    this._tabSearchCache[index] = query;
  }

  // ==================== 分区渲染 ====================

  /** 常用区：组合预设 + 快捷指标（列表风格，同标准面板） */
  _renderQuick() {
    var html = '';

    // 组合预设作为第一组
    var presets = [
      { n: this._t('combo.ALL_MAS'),        k:'ALL_MAS' },
      { n: this._t('combo.EMA_COMBO'),      k:'EMA_COMBO' },
      { n: this._t('combo.SMA_EMA_COMBO'),  k:'SMA_EMA_COMBO' },
      { n: this._t('combo.MOMENTUM_SUITE'),  k:'MOMENTUM_SUITE' },
      { n: this._t('combo.VOLATILITY'),      k:'VOLATILITY' },
      { n: this._t('combo.TREND_FOLLOW'),    k:'TREND_FOLLOW' },
    ];
    html += '<div class="cat-group">';
    html += '<div class="cat-group-title">' + this._t('group.combos') + '</div>';
    html += '<div class="cat-items">';
      for (var pi = 0; pi < presets.length; pi++) {
        var p = presets[pi];
        var isActive = window.combinedPresets && window.combinedPresets.isActive(p.k);
        // 查找预设的指示器 ID 用于参数面板
        var preset = window.combinedPresets ? window.combinedPresets._lookupPreset(p.k) : null;
        var dataId = (preset && preset.indicators && preset.indicators.length > 0) ? preset.indicators[0].id : '';
        html += '<div class="indicator-row' + (isActive ? ' active' : '') + '" data-combo="' + p.k + '" data-id="' + dataId + '">';
        html += '<span class="ind-name">' + p.n + '</span>';
        html += '</div>';
      }
    html += '</div></div>';

    // 默认常用指标分组（列表风格，第一个展开，其余折叠）
    // 我的收藏（从所有分组收集）
    var allFavs = window.Favorites ? window.Favorites.getAll() : [];
    if (allFavs.length > 0) {
      html += '<div class="cat-group" id="favs-section">';
      html += '<div class="cat-group-title">⭐ ' + this._t('group.favorites') + '</div>';
      html += '<div class="cat-items">';
      for (var fi = 0; fi < allFavs.length; fi++) {
        var fid = allFavs[fi];
        var fActive = engine && engine.isVisible(fid);
        html += '<div class="indicator-row' + (fActive ? ' active' : '') + '" data-id="' + fid + '">';
        html += '<span class="ind-star on" data-star data-id="' + fid + '" data-group="quick"></span>';
        html += '<span class="ind-name">' + this._indicatorName(fid, fid) + '</span>';
        html += '<span class="ind-badge">' + fid + '</span></div>';
      }
      html += '</div></div>';
    }
    var groups = [
      { n: this._t('group.ma'),     items:['SMA','EMA','TEMA','WMA','RMA','DEMA','HMA','LSMA','ALMA','VWMA','MCGINLEY','EMAMACross','MARibbon','ZLSMA'] },
      { n: this._t('group.osc'),    items:['RSI','Stochastic','StochRSI','CCI','WilliamsPercentRange','AwesomeOscillator','ChandeMO','DPO','RVI','TSI','UltimateOscillator','KDJ','WaveTrend','SchaffTrendCycle'] },
      { n: this._t('group.mom'),    items:['MACD','Momentum','ROC','BOP','BullBearPower','CoppockCurve','TRIX','SqueezeMomentum'] },
      { n: this._t('group.trend'),  items:['ADX','IchimokuCloud','ParabolicSAR','VolumeSuperTrendAi','Aroon','ZigZag','WilliamsAlligator','DonchianChannels'] },
      { n: this._t('group.vol'),    items:['ATR','BollingerBands','StandardDeviation','HistoricalVolatility','Choppiness'] },
      { n: this._t('group.volume'), items:['BaseVolume','BetterVolume','VWMA','MFI','OBV','VolumeAccumulationPct'] },
      { n: this._t('group.custom'), items:['Yearly_Profile'] },
    ];

    for (var g = 0; g < groups.length; g++) {
      var grp = groups[g];
      var collapsed = g > 0 ? ' collapsed' : '';
      html += '<div class="cat-group' + collapsed + '">';
      html += '<div class="cat-group-title">' + grp.n + '</div>';
      html += '<div class="cat-items">';
      for (var i = 0; i < grp.items.length; i++) {
        var k = grp.items[i];
        var engine = window.indicatorEngine;
        var isV = engine && engine.isVisible(k);
        var displayName = this._indicatorName(k, k);
        // 默认参数
        var defaultParams = '';
        if (k === 'SMA') defaultParams = '{"len":20}';
        else if (k === 'EMA') defaultParams = '{"len":12}';
        html += '<div class="indicator-row' + (isV ? ' active' : '') + '" data-id="' + k + '" data-params=\'' + defaultParams + '\'>';
        html += '<span class="ind-name">' + displayName + '</span>';
        html += '<span class="ind-badge">' + k + '</span>';
        html += '</div>';
        if (isV) {
          // 查找 catalog entry 以渲染参数面板
          var entry = engine._findCatalogEntry ? engine._findCatalogEntry(k) : null;
          if (entry) html += this._renderParamsHTML(k, entry);
          // 特殊指标: MA_Combo / MomentumSuite / VolatilitySuite 等无 catalog entry
        }
      }
      html += '</div></div>';
    }
    return html;
  }

  /** 标准/社区/K线: 搜索 + 分类列表 */
  _renderList(group, query) {
    // 搜索缓存：相同搜索词不重复生成 HTML
    if (this._lastSearchGroup === group && this._lastSearchQuery === query) {
      return this._lastSearchHTML || '';
    }
    var engine = window.indicatorEngine;
    if (!engine) return '<div class="panel-empty">' + this._t('loading.indicators') + '</div>';

    var catalog = engine.getCatalog();
    var catOrder = engine.getCategoryOrder();

    // 按分类分组
    var byCat = {};
    for (var ci = 0; ci < catalog.length; ci++) {
      var ind = catalog[ci];
      if (ind.group !== group) continue;
      if (query && ind.name.toLowerCase().indexOf(query) === -1 && ind.id.toLowerCase().indexOf(query) === -1) {
        // 多语言显示名搜索
        var dispName = this._indicatorName(ind.id, ind.name);
        if (dispName && dispName !== ind.name && dispName.toLowerCase().indexOf(query) === -1) continue;
        else if (!dispName || dispName === ind.name) continue;
      }
      if (!byCat[ind.category]) byCat[ind.category] = [];
      byCat[ind.category].push(ind);
    }

    var html = '<div class="section-search"><input type="text" class="section-search-input" placeholder="' + this._t('search.placeholder') + '" value="' + (query || '') + '" /></div>';
    var catCount = 0;
    for (var ci2 = 0; ci2 < catOrder.length; ci2++) {
      var catName = catOrder[ci2];
      var indicators = byCat[catName];
      if (!indicators || indicators.length === 0) continue;
      catCount++;
      var collapsed = catCount > 1 ? ' collapsed' : '';
      var catKey = 'cat.' + catName.toLowerCase().replace(/[&]+/g, 'and').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
      html += '<div class="cat-group' + collapsed + '">';
      html += '<div class="cat-group-title">' + this._t(catKey) + ' (' + indicators.length + ')</div>';
      html += '<div class="cat-items">';
      for (var ii = 0; ii < indicators.length; ii++) {
        var ind = indicators[ii];
        var active = engine.isVisible(ind.id);
        var starred = window.Favorites.is(ind.id, ind.group);
        var displayName = this._indicatorName(ind.id, ind.name);
        html += '<div class="indicator-row' + (active ? ' active' : '') + '" data-id="' + ind.id + '">';
        html += '<span class="ind-star' + (starred ? ' on' : '') + '" data-star data-id="' + ind.id + '" data-group="' + ind.group + '"></span>';
        html += '<span class="ind-name">' + displayName + '</span>';
        // K 线形态检测计数
        if (ind.group === 'candlestick' && engine) {
          var pc = engine.getPatternCount(ind.id);
          if (pc > 0) html += '<span class="pat-count">' + pc + '</span>';
        }
        html += '<span class="ind-badge">' + ind.id + '</span>';
        html += '</div>';
        // 已显示的指标 → 内联参数面板
        if (active) {
          html += this._renderParamsHTML(ind.id, ind);
        }
      }
      html += '</div></div>';
    }
    // 缓存搜索结果
    this._lastSearchGroup = group;
    this._lastSearchQuery = query;
    this._lastSearchHTML = html;
    return html;
  }

  /** 单个指标的参数面板 HTML */
  _renderParamsHTML(id, entry) {
    var inputs = entry.inputs || [];
    if (!inputs.length) return '';
    var engine = window.indicatorEngine;
    var info = engine ? engine.getActiveMap().get(id) : null;
    var params = info ? (info.params || {}) : {};
    // 从 localStorage 加载持久化的参数
    var savedParams = null;
    try { var sp = localStorage.getItem('tradingview_params_' + id); if (sp) savedParams = JSON.parse(sp); } catch(e) {}
    if (savedParams) { for (var pk in savedParams) { params[pk] = savedParams[pk]; } }

    var html = '<div class="params-panel open" data-params-for="' + id + '">';
    for (var i = 0; i < inputs.length; i++) {
      var inp = inputs[i];
      var val = params[inp.id] !== undefined ? params[inp.id] : inp.defval;
      html += '<div class="params-row">';
      html += '<label>' + (inp.title || inp.name || inp.id) + '</label>';
      if (inp.options) {
        html += '<select data-param="' + inp.id + '">';
        for (var oi = 0; oi < inp.options.length; oi++) {
          var o = inp.options[oi];
          html += '<option value="' + o + '"' + (val === o ? ' selected' : '') + '>' + o + '</option>';
        }
        html += '</select>';
      } else {
        html += '<input type="number" data-param="' + inp.id + '" value="' + (val !== undefined ? val : '') + '"'
          + (inp.min !== undefined ? ' min="' + inp.min + '"' : '')
          + (inp.max !== undefined ? ' max="' + inp.max + '"' : '')
          + ' step="' + (inp.step || 1) + '" />';
      }
      html += '</div>';
    }
    html += '<button class="params-apply" data-id="' + id + '">' + this._t('params.apply') + '</button>';
    html += '<div style="clear:both"></div></div>';
    return html;
  }

  // ==================== 事件绑定 ====================

  _bindTabEvents() {
    var self = this;
    var tabs = this.container.querySelectorAll('.panel-tab[data-tab]');
    for (var i = 0; i < tabs.length; i++) {
      (function(tab) {
        tab.addEventListener('click', function() {
          var idx = parseInt(tab.getAttribute('data-tab'), 10);
          if (!isNaN(idx)) self.switchTab(idx);
        });
      })(tabs[i]);
    }
  }

  switchTab(index) {
    if (index === this.activeTab) return;
    this.activeTab = index;
    // 更新 tab 高亮
    var tabs = this.container.querySelectorAll('.panel-tab:not(.lang-toggle)');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle('active', i === index);
    }
    // 切换内容
    var contents = this.container.querySelectorAll('.panel-content');
    for (var i = 0; i < contents.length; i++) {
      contents[i].classList.toggle('active', i === index);
    }
    // 恢复该 Tab 最后的搜索词，没有则传空
    var savedQ = this._tabSearchCache && this._tabSearchCache[index] ? this._tabSearchCache[index] : '';
    if (!contents[index].hasChildNodes() || contents[index].innerHTML.trim() === '') {
      this._renderTab(index, savedQ);
    }
  }

  _bindContentEvents(index) {
    var content = this.container.querySelector('[data-tab-content="' + index + '"]');
    if (!content) return;
    var self = this;

    // 分类折叠（手风琴：只展开一个）
    var catTitles = content.querySelectorAll('.cat-group-title');
    for (var ct = 0; ct < catTitles.length; ct++) {
      (function(ctTitle) {
        ctTitle.addEventListener('click', function() {
          var parent = this.parentElement;
          var isCollapsed = parent.classList.contains('collapsed');
          // 折叠当前组内所有分类
          var container = parent.closest('[data-tab-content]') || parent.closest('.panel-section-content') || parent.parentElement;
          var allGroups = container.querySelectorAll('.cat-group');
          for (var gi = 0; gi < allGroups.length; gi++) {
            allGroups[gi].classList.add('collapsed');
          }
          // 如果点击前是折叠的，展开它
          if (isCollapsed) {
            parent.classList.remove('collapsed');
          }
        });
      })(catTitles[ct]);
    }

    // 指标/按钮点击
    var items = content.querySelectorAll('.quick-item, .indicator-row');
    for (var i = 0; i < items.length; i++) {
      items[i].addEventListener('click', function() {
        var combo = this.dataset.combo;
        if (combo) {
          if (window.combinedPresets) {
            window.combinedPresets.toggle(combo);
            self._syncAllButtons();
            // 组合预设切换后更新内联参数面板
            var preset = window.combinedPresets._lookupPreset ? window.combinedPresets._lookupPreset(combo) : null;
            if (preset) {
              for (var pi = 0; pi < preset.indicators.length; pi++) {
                self._updateParamsPanel(preset.indicators[pi].id);
              }
            }
          }
          return;
        }
        var id = this.dataset.id;
        if (!id) return;
        var params = {};
        try { params = JSON.parse(this.dataset.params || '{}'); } catch(e) {}
        self._toggleIndicator(id, params);
      });
    }

    // 搜索框
    var searchInput = content.querySelector('.section-search-input');
    if (searchInput) {
      (function(inp) {
        inp.addEventListener('compositionstart', function() { inp._composing = true; });
        inp.addEventListener('compositionend', function() {
          inp._composing = false;
          // 组合完成立即触发搜索
          var q = inp.value.toLowerCase();
          if (self._searchTimer) clearTimeout(self._searchTimer);
          var caretPos = inp.selectionStart;
          self._renderTab(index, q);
          var newInput = self.container.querySelector('[data-tab-content="' + index + '"] .section-search-input');
          if (newInput) { newInput.focus(); newInput.selectionStart = newInput.selectionEnd = Math.min(caretPos, newInput.value.length); }
        });
        inp.addEventListener('input', function(e) {
          // IME 组合中不渲染，防止破坏输入法状态
          if (inp._composing) return;
          var q = e.target.value.toLowerCase();
          if (self._searchTimer) clearTimeout(self._searchTimer);
          self._searchTimer = setTimeout(function() {
            if (self._lastSearchQuery === q && self._lastSearchTab === index) return;
            var caretPos = inp.selectionStart;
            self._renderTab(index, q);
            var newInput = self.container.querySelector('[data-tab-content="' + index + '"] .section-search-input');
            if (newInput) { newInput.focus(); newInput.selectionStart = newInput.selectionEnd = Math.min(caretPos, newInput.value.length); }
          }, 150);
        });
        // 回车立即搜索
        inp.addEventListener('keydown', function(e) {
          if (e.key === 'Enter') {
            if (self._searchTimer) clearTimeout(self._searchTimer);
            var q = e.target.value.toLowerCase();
            var caretPos = inp.selectionStart;
            self._renderTab(index, q);
            var newInput = self.container.querySelector('[data-tab-content="' + index + '"] .section-search-input');
            if (newInput) { newInput.focus(); newInput.selectionStart = newInput.selectionEnd = Math.min(caretPos, newInput.value.length); }
          }
        });
      })(searchInput);
    }

    // 收藏星标点击（独立事件，不触发行切换）
    var stars = content.querySelectorAll('[data-star]');
    for (var si = 0; si < stars.length; si++) {
      (function(el) {
        el.addEventListener('click', function(e) {
          e.stopPropagation();
          var id = el.getAttribute('data-id');
          var group = el.getAttribute('data-group');
          if (!id || !window.Favorites) return;
          window.Favorites.toggle(id, group);
          el.classList.toggle('on');
          // 用自定义事件通知面板刷新
          document.dispatchEvent(new CustomEvent('favorite-changed'));
        });
      })(stars[si]);
    }

    // 参数应用按钮
    var applyBtns = content.querySelectorAll('.params-apply');
    for (var ai = 0; ai < applyBtns.length; ai++) {
      applyBtns[ai].addEventListener('click', function() {
        self._applyParams(this.dataset.id);
      });
    }
  }

  _bindLangToggle() {
    var self = this;
    var toggle = this.container.querySelector('#panelLangToggle');
    if (!toggle) return;
    toggle.addEventListener('click', function() {
      window.i18n.toggleLang();
      self.refresh();
    });
  }

  // ==================== 指标操作 ====================

  _toggleIndicator(id, params) {
    try {
      var engine = window.indicatorEngine;
      if (!engine) return;
      engine.toggle(id, params || {});
      this._syncButtonState(id);
      // 仅更新该指标的参数面板，不重建整个列表（保留分组展开状态）
      this._updateParamsPanel(id);
    } catch(e) {
      console.error('toggle error: ' + id, e);
    }
  }

  /** 在指标行下方插入/移除参数面板，不重建整个列表 */
  _updateParamsPanel(id) {
    var engine = window.indicatorEngine;
    if (!engine) return;
    var isVisible = engine.isVisible(id);
    var rows = this.container.querySelectorAll('.indicator-row[data-id="' + id + '"]');
    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri];
      var container = row.parentElement;
      // 查找已存在的参数面板
      var existing = container.querySelector('[data-params-for="' + id + '"]');
      if (isVisible && !existing) {
        // 插入参数面板
        var entry = engine._findCatalogEntry ? engine._findCatalogEntry(id) : null;
        if (entry && entry.inputs && entry.inputs.length) {
          var html = this._renderParamsHTML(id, entry);
          row.insertAdjacentHTML('afterend', html);
          var newPanel = container.querySelector('[data-params-for="' + id + '"]');
          if (newPanel) {
            var btn = newPanel.querySelector('.params-apply');
            if (btn) {
              var self = this;
              btn.addEventListener('click', function() {
                self._applyParams(this.dataset.id);
              });
            }
          }
        }
      } else if (!isVisible && existing) {
        existing.remove();
      }
    }
  }

  _applyParams(id) {
    try {
      var engine = window.indicatorEngine;
      if (!engine) return;
      var panel = this.container.querySelector('[data-params-for="' + id + '"]');
      if (!panel) return;
      var params = {};
      var inputs = panel.querySelectorAll('[data-param]');
      for (var i = 0; i < inputs.length; i++) {
        var el = inputs[i];
        params[el.dataset.param] = parseFloat(el.value) || el.value;
      }
      // 持久化参数到 localStorage
      try { localStorage.setItem('tradingview_params_' + id, JSON.stringify(params)); } catch(e) {}
      engine.remove(id);
      engine.calculateAndAdd(id, params);
      // 更新参数面板中的值（无需重建列表）
      this._updateParamsPanel(id);
    } catch(e) {
      console.error('apply params error: ' + id, e);
    }
  }

  _syncButtonState(id) {
    var engine = window.indicatorEngine;
    if (!engine) return;
    var allBtns = this.container.querySelectorAll('[data-id="' + id + '"]');
    var isVisible = engine.isVisible(id);
    for (var i = 0; i < allBtns.length; i++) {
      if (isVisible) allBtns[i].classList.add('active');
      else allBtns[i].classList.remove('active');
    }
  }

  _syncAllButtons() {
    var engine = window.indicatorEngine;
    if (!engine) return;
    var allBtns = this.container.querySelectorAll('[data-id]');
    for (var bi = 0; bi < allBtns.length; bi++) {
      var id = allBtns[bi].dataset.id;
      if (id) {
        if (engine.isVisible(id)) allBtns[bi].classList.add('active');
        else allBtns[bi].classList.remove('active');
      }
    }
    var combos = this.container.querySelectorAll('[data-combo]');
    for (var ci = 0; ci < combos.length; ci++) {
      var key = combos[ci].dataset.combo;
      if (key && window.combinedPresets) {
        if (window.combinedPresets.isActive(key)) combos[ci].classList.add('active');
        else combos[ci].classList.remove('active');
      }
    }
  }

  refresh() {
    this._render();
  }
}

window.indicatorPanel = null;
window.IndicatorPanel = IndicatorPanel;
