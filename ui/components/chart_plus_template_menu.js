/**
 * 图表增强模板菜单
 * Chart Plus Template Menu
 * 支持指标计算、数据验证、图表显示和多语言界面
 * 版本: 2.0.3 - 修复函数冲突和this绑定问题
 */

// ============================
// 全局状态和配置
// ============================
if (!window.indicatorStates) {
    window.indicatorStates = new Map(); // 存储指标激活状态
}
if (!window.activeGroups) {
    window.activeGroups = new Set(); // 存储激活的指标分组
}
if (!window.activeIndicators) {
    window.activeIndicators = new Set(); // 存储激活的指标系列
}

let currentLanguage = 'zh'; // 默认语言：中文
let chartPlusApp = null; // ChartPlusApp 实例

// 多语言词典
const languageDict = {
    zh: {
        // 通用
        loading: '加载中...',
        success: '成功',
        error: '错误',
        warning: '警告',
        confirm: '确认',
        cancel: '取消',
        
        // 指标相关
        indicator: '指标',
        indicators: '指标',
        addIndicator: '添加指标',
        removeIndicator: '移除指标',
        toggleIndicator: '切换指标',
        calculateIndicator: '计算指标',
        indicatorAdded: '指标已添加',
        indicatorRemoved: '指标已移除',
        indicatorFailed: '指标计算失败',
        
        // 面板相关
        panel: '面板',
        showPanel: '显示面板',
        hidePanel: '隐藏面板',
        togglePanel: '切换面板',
        settingsPanel: '设置面板',
        indicatorPanel: '指标面板',
        chartPanel: '图表面板',
        
        // 图表相关
        chart: '图表',
        mainChart: '主图',
        subChart: '副图',
        priceChart: '价格图表',
        volumeChart: '成交量图表',
        
        // 数据相关
        data: '数据',
        loadingData: '正在加载数据...',
        dataLoaded: '数据加载完成',
        dataError: '数据错误',
        invalidData: '无效数据',
        
        // 操作
        save: '保存',
        load: '加载',
        reset: '重置',
        apply: '应用',
        close: '关闭',
        
        // 消息
        noDataAvailable: '没有可用数据',
        indicatorNotSupported: '指标不支持',
        chartInstanceNotFound: '图表实例未找到',
        panelNotFound: '面板未找到',
        operationFailed: '操作失败',
        operationSuccess: '操作成功',
        
        // 指标面板相关
        technicalIndicators: '技术指标',
        movingAverages: '移动平均线',
        oscillators: '振荡指标',
        momentum: '动量指标',
        trend: '趋势指标',
        volatility: '波动率',
        volume: '成交量',
        custom: '自定义指标'
    },
    en: {
        // General
        loading: 'Loading...',
        success: 'Success',
        error: 'Error',
        warning: 'Warning',
        confirm: 'Confirm',
        cancel: 'Cancel',
        
        // Indicator related
        indicator: 'Indicator',
        indicators: 'Indicators',
        addIndicator: 'Add Indicator',
        removeIndicator: 'Remove Indicator',
        toggleIndicator: 'Toggle Indicator',
        calculateIndicator: 'Calculate Indicator',
        indicatorAdded: 'Indicator Added',
        indicatorRemoved: 'Indicator Removed',
        indicatorFailed: 'Indicator Calculation Failed',
        
        // Panel related
        panel: 'Panel',
        showPanel: 'Show Panel',
        hidePanel: 'Hide Panel',
        togglePanel: 'Toggle Panel',
        settingsPanel: 'Settings Panel',
        indicatorPanel: 'Indicator Panel',
        chartPanel: 'Chart Panel',
        
        // Chart related
        chart: 'Chart',
        mainChart: 'Main Chart',
        subChart: 'Sub Chart',
        priceChart: 'Price Chart',
        volumeChart: 'Volume Chart',
        
        // Data related
        data: 'Data',
        loadingData: 'Loading Data...',
        dataLoaded: 'Data Loaded',
        dataError: 'Data Error',
        invalidData: 'Invalid Data',
        
        // Operations
        save: 'Save',
        load: 'Load',
        reset: 'Reset',
        apply: 'Apply',
        close: 'Close',
        
        // Messages
        noDataAvailable: 'No data available',
        indicatorNotSupported: 'Indicator not supported',
        chartInstanceNotFound: 'Chart instance not found',
        panelNotFound: 'Panel not found',
        operationFailed: 'Operation failed',
        operationSuccess: 'Operation successful',
        
        // Indicator panel related
        technicalIndicators: 'Technical Indicators',
        movingAverages: 'Moving Averages',
        oscillators: 'Oscillators',
        momentum: 'Momentum',
        trend: 'Trend',
        volatility: 'Volatility',
        volume: 'Volume',
        custom: 'Custom Indicators'
    }
};

// ============================
// 全局初始化函数
// ============================
/**
 * 初始化指标面板
 * 与 tool.js 中的调用对齐
 */
window.initIndicatorPanel = function(maxRetries = 5, retryDelay = 300) {
    console.log('🚀 初始化指标面板 (initIndicatorPanel)');
    
    // 检查必要的依赖
    if (!window.indicatorCategories) {
        console.warn('⚠️ indicatorCategories 未加载，等待数据...');
        if (maxRetries > 0) {
            setTimeout(() => {
                window.initIndicatorPanel(maxRetries - 1, retryDelay);
            }, retryDelay);
            return false;
        } else {
            console.error('❌ 指标分类数据加载失败，无法初始化面板');
            return false;
        }
    }
    
    // 方法1: 如果 ChartPlus 已初始化，使用其方法
    if (window.chartPlusApp) {
        console.log('✅ 使用 ChartPlusApp 初始化指标面板');
        return window.chartPlusApp.populateIndicatorPanel();
    }
    
    // 方法2: 尝试初始化 ChartPlus
    if (window.ChartPlus && window.ChartPlus.init) {
        try {
            window.chartPlusApp = window.ChartPlus.init();
            console.log('✅ ChartPlus 已初始化');
            return window.chartPlusApp.populateIndicatorPanel();
        } catch (error) {
            console.error('❌ ChartPlus 初始化失败:', error);
        }
    }
    
    // 方法3: 如果 ChartPlus 未初始化，但全局函数可用
    if (window.populateIndicatorPanel) {
        console.log('✅ 使用全局 populateIndicatorPanel 函数');
        return window.populateIndicatorPanel();
    }
    
    // 方法4: 直接初始化面板
    console.log('✅ 直接初始化指标面板');
    return initializeIndicatorPanelDirectly();
};

// 添加状态检查函数
window.checkChartPlusStatus = function() {
    console.log('🔍 检查 Chart Plus 系统状态:');
    
    const status = {
        'window.chartPlusApp': !!window.chartPlusApp,
        'window.ChartPlus': !!window.ChartPlus,
        'window.ChartPlus.init': !!(window.ChartPlus && window.ChartPlus.init),
        'window.indicatorCategories': !!window.indicatorCategories,
        'window.indicatorCategories.length': window.indicatorCategories ? window.indicatorCategories.length : 0,
        'window.populateIndicatorPanel': !!(window.populateIndicatorPanel),
        'window.initIndicatorPanel': !!(window.initIndicatorPanel),
        'window.isChartInitialized': !!window.isChartInitialized
    };
    
    console.table(status);
    
    // 如果未初始化，尝试初始化
    if (!window.chartPlusApp && window.ChartPlus && window.ChartPlus.init) {
        console.log('🔄 尝试初始化 ChartPlus...');
        window.chartPlusApp = window.ChartPlus.init();
    }
    
    return status;
};

// 直接初始化指标面板的函数
function initializeIndicatorPanelDirectly() {
    const panel = document.getElementById('indicatorPanel');
    if (!panel) {
        console.error('❌ 指标面板未找到: #indicatorPanel');
        return false;
    }
    
    // 检查是否有指标分类数据
    if (!window.indicatorCategories) {
        console.warn('⚠️ 指标分类数据未加载，等待数据就绪');
        
        // 尝试延迟初始化
        setTimeout(() => {
            if (window.indicatorCategories) {
                initializeIndicatorPanelDirectly();
            } else {
                console.warn('⚠️ 指标分类数据仍未加载，请检查数据源');
            }
        }, 1000);
        
        return false;
    }
    
    console.log(`📊 开始填充指标面板，共 ${window.indicatorCategories.length} 个分类`);
    
    // 获取面板内容区域
    let content = panel.querySelector('.panel-content');
    if (!content) {
        content = document.createElement('div');
        content.className = 'panel-content';
        content.style.padding = '10px';
        content.style.overflowY = 'auto';
        content.style.maxHeight = 'calc(100% - 40px)';
        panel.appendChild(content);
    }
    
    // 清空现有内容
    content.innerHTML = '';
    
    // 遍历每个指标分类
    window.indicatorCategories.forEach(category => {
        // 创建分类容器
        const categoryDiv = document.createElement('div');
        categoryDiv.className = 'indicator-category';
        categoryDiv.style.marginBottom = '15px';
        categoryDiv.style.border = '1px solid #2a2e39';
        categoryDiv.style.borderRadius = '6px';
        categoryDiv.style.overflow = 'hidden';
        categoryDiv.style.background = '#1e222d';
        
        // 创建分类标题
        const categoryTitle = document.createElement('div');
        categoryTitle.className = 'category-title';
        categoryTitle.textContent = category.name;
        categoryTitle.style.background = '#2a2e39';
        categoryTitle.style.padding = '8px 12px';
        categoryTitle.style.fontWeight = 'bold';
        categoryTitle.style.fontSize = '12px';
        categoryTitle.style.cursor = 'pointer';
        categoryTitle.style.userSelect = 'none';
        categoryTitle.style.color = '#d1d4dc';
        categoryTitle.style.transition = 'background 0.2s ease';
        
        // 创建指标容器
        const indicatorsContainer = document.createElement('div');
        indicatorsContainer.className = 'category-content';
        indicatorsContainer.style.padding = '8px';
        indicatorsContainer.style.display = 'grid';
        indicatorsContainer.style.gridTemplateColumns = 'repeat(2, 1fr)';
        indicatorsContainer.style.gap = '5px';
        indicatorsContainer.style.backgroundColor = '#1e222d';
        
        // 为分类标题添加点击事件
        let isCollapsed = false;
        categoryTitle.addEventListener('click', () => {
            isCollapsed = !isCollapsed;
            indicatorsContainer.style.display = isCollapsed ? 'none' : 'grid';
            const icon = categoryTitle.querySelector('.collapse-icon') || 
                        categoryTitle.firstChild;
            if (isCollapsed) {
                categoryTitle.innerHTML = '▶ ' + category.name;
            } else {
                categoryTitle.innerHTML = '▼ ' + category.name;
            }
        });
        
        // 在标题前添加折叠图标
        categoryTitle.innerHTML = '▼ ' + category.name;
        
        // 遍历分类中的指标
        category.indicators.forEach(indicator => {
            const button = document.createElement('button');
            button.className = 'indicator-button';
            button.setAttribute('data-indicator', indicator.key);
            button.textContent = indicator.name;
            
            // 设置样式
            button.style.cssText = `
                padding: 6px 8px;
                margin: 2px;
                border: 1px solid #2a2e39;
                background: #131722;
                color: #d1d4dc;
                cursor: pointer;
                border-radius: 4px;
                font-size: 11px;
                text-align: center;
                transition: all 0.2s ease;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            `;
            
            // 添加悬停效果
            button.addEventListener('mouseenter', () => {
                if (!button.classList.contains('active')) {
                    button.style.background = '#2a2e39';
                    button.style.borderColor = '#2962FF';
                }
            });
            
            button.addEventListener('mouseleave', () => {
                if (!button.classList.contains('active')) {
                    button.style.background = '#131722';
                    button.style.borderColor = '#2a2e39';
                }
            });
            
            // 【关键修复】使用箭头函数避免 this 绑定问题
            button.addEventListener('click', (event) => {
                const indicatorKey = button.getAttribute('data-indicator');
                handleIndicatorButtonClick(indicatorKey, button);
                event.stopPropagation();
            });
            
            // 添加工具提示
            button.title = `${indicator.name} (${indicator.en})`;
            
            indicatorsContainer.appendChild(button);
        });
        
        // 组装分类
        categoryDiv.appendChild(categoryTitle);
        categoryDiv.appendChild(indicatorsContainer);
        content.appendChild(categoryDiv);
    });
    
    // 注册全局指标按钮事件
    registerIndicatorButtonEvents();
    
    const totalIndicators = countTotalIndicators();
    console.log(`✅ 指标面板已成功填充，共添加了 ${totalIndicators} 个指标按钮`);
    
    return true;
}

// 显示指标
function showIndicator(indicatorKey, button) {
    console.log(`👁️ 显示指标: ${indicatorKey}`);
    
    // 更新按钮状态
    button.classList.add('active');
    button.style.backgroundColor = '#2962FF';
    button.style.color = 'white';
    button.style.borderColor = '#2962FF';
    
    // 获取指标参数
    const options = getIndicatorOptions(indicatorKey);
    options.visible = true;  // 确保可见性设置为true
    
    // 【修改】调用图表系统的显示指标函数
    if (window.showIndicatorFromPython) {
        window.showIndicatorFromPython(indicatorKey, options);
    } else if (window.addIndicatorFromPython) {
        // 如果没有专门的显示函数，使用添加函数
        window.addIndicatorFromPython(indicatorKey, options);
    } else {
        console.error('❌ 没有可用的显示指标函数');
    }
}

// 隐藏指标
function hideIndicator(indicatorKey, button) {
    console.log(`🙈 隐藏指标: ${indicatorKey}`);
    
    // 更新按钮状态
    button.classList.remove('active');
    button.style.backgroundColor = '#131722';
    button.style.color = '#d1d4dc';
    button.style.borderColor = '#2a2e39';
    
    // 【修改】调用图表系统的隐藏指标函数
    if (window.hideIndicatorFromPython) {
        window.hideIndicatorFromPython(indicatorKey);
    } else if (window.updateIndicatorVisibility) {
        // 如果有更新可见性的函数
        window.updateIndicatorVisibility(indicatorKey, false);
    } else {
        console.error('❌ 没有可用的隐藏指标函数');
    }
}

// 显示指标操作
function showIndicatorAction(indicatorKey, button) {
    console.log(`👁️ 显示指标: ${indicatorKey}`);
    
    // 更新按钮状态
    button.classList.add('active');
    button.style.backgroundColor = '#2962FF';
    button.style.color = 'white';
    button.style.borderColor = '#2962FF';
    
    // 获取指标参数
    const options = getIndicatorOptions(indicatorKey);
    options.visible = true;
    
    // 检查是否为组合指标
    if (indicatorKey === 'SMAclassic') {
        // 处理组合指标
        if (window.showComboIndicator) {
            window.showComboIndicator(indicatorKey, options);
        } else if (window.addIndicatorFromPython) {
            window.addIndicatorFromPython(indicatorKey, options);
        } else {
            console.error('❌ 没有可用的显示组合指标函数');
        }
    } else {
        // 处理单个指标
        if (window.showIndicatorFromPython) {
            window.showIndicatorFromPython(indicatorKey, options);
        } else if (window.addIndicatorFromPython) {
            window.addIndicatorFromPython(indicatorKey, options);
        } else {
            console.error('❌ 没有可用的显示指标函数');
        }
    }
}

// 隐藏指标操作
function hideIndicatorAction(indicatorKey, button) {
    console.log(`🙈 隐藏指标: ${indicatorKey}`);
    
    // 更新按钮状态
    button.classList.remove('active');
    button.style.backgroundColor = '#131722';
    button.style.color = '#d1d4dc';
    button.style.borderColor = '#2a2e39';
    
    // 检查是否为组合指标
    if (indicatorKey === 'SMAclassic') {
        // 处理组合指标
        if (window.hideComboIndicator) {
            window.hideComboIndicator(indicatorKey);
        } else if (window.hideIndicatorFromPython) {
            window.hideIndicatorFromPython(indicatorKey);
        } else {
            console.error('❌ 没有可用的隐藏组合指标函数');
        }
    } else {
        // 处理单个指标
        if (window.hideIndicatorFromPython) {
            window.hideIndicatorFromPython(indicatorKey);
        } else if (window.removeIndicatorFromPython) {
            window.removeIndicatorFromPython(indicatorKey);
        } else {
            console.error('❌ 没有可用的隐藏指标函数');
        }
    }
}

// 处理指标按钮点击
function handleIndicatorButtonClick(indicatorKey, button) {
    const isActive = button.classList.contains('active');
    
    console.log(`🔄 点击指标按钮: ${indicatorKey}, 当前状态: ${isActive ? '激活' : '未激活'}`);
    
    if (isActive) {
        // 隐藏指标
        hideIndicatorAction(indicatorKey, button);
    } else {
        // 显示指标
        showIndicatorAction(indicatorKey, button);
    }
}

// 添加指标操作
function addIndicatorAction(indicatorKey, button) {
    console.log(`➕ 添加指标: ${indicatorKey}`);
    
    // 更新按钮状态
    button.classList.add('active');
    button.style.backgroundColor = '#2962FF';
    button.style.color = 'white';
    button.style.borderColor = '#2962FF';
    
    // 获取指标参数
    const options = getIndicatorOptions(indicatorKey);
    
    // 【关键修复】直接调用图表系统的函数，避免循环调用
    if (window.addIndicatorFromPython) {
        window.addIndicatorFromPython(indicatorKey, options);
    } else {
        console.error('❌ window.addIndicatorFromPython 函数未找到');
    }
}

// 移除指标操作
function removeIndicatorAction(indicatorKey, button) {
    console.log(`➖ 移除指标: ${indicatorKey}`);
    
    // 更新按钮状态
    button.classList.remove('active');
    button.style.backgroundColor = '#131722';
    button.style.color = '#d1d4dc';
    button.style.borderColor = '#2a2e39';
    
    // 【关键修复】直接调用图表系统的移除函数
    if (window.removeIndicatorFromPython) {
        window.removeIndicatorFromPython(indicatorKey);
    } else {
        console.error('❌ window.removeIndicatorFromPython 函数未找到');
    }
}

// 注册指标按钮事件
function registerIndicatorButtonEvents() {
    // 通过事件委托处理指标按钮点击
    document.addEventListener('click', (e) => {
        const button = e.target.closest('.indicator-button');
        if (!button) return;
        
        const indicatorKey = button.getAttribute('data-indicator');
        if (!indicatorKey) return;
        
        handleIndicatorButtonClick(indicatorKey, button);
    });
}

// 获取指标参数
function getIndicatorOptions(indicatorKey, baseOptions = {}) {
    const options = { ...baseOptions, visible: true };
    
    // 【关键修复】为SMA设置正确的参数
    if (indicatorKey === 'SMA') {
        //SMA 参数特殊，采用的len，而EMA 等用的length
        options.len = 20;  // 默认周期
    } else if (indicatorKey.includes('SMA_')) {
        const length = indicatorKey.split('_')[1];
        options.len = parseInt(length) || 20;
    } else if (indicatorKey === 'EMA') {
        options.length = 12;  // 默认周期
    } else if (indicatorKey === 'EMA_') {
        const length = indicatorKey.split('_')[1];
        options.length = parseInt(length) || 12;
    } else if (indicatorKey === 'RSI') {
        options.length = 14;
    } else if (indicatorKey === 'MACD') {
        options.fastLength = 12;
        options.slowLength = 26;
        options.signalLength = 9;
    } else if (indicatorKey === 'BollingerBands') {
        options.length = 20;
        options.stdDev = 2;
    } else if (indicatorKey === 'Stochastic') {
        options.length = 14;
        options.smoothK = 3;
        options.smoothD = 3;
    } else if (indicatorKey === 'AwesomeOscillator') {
        options.fastPeriod = 5;
        options.slowPeriod = 34;
    } else if (indicatorKey === 'UltimateOscillator') {
        options.period1 = 7;
        options.period2 = 14;
        options.period3 = 28;
    } else if (indicatorKey === 'ChandeMO' || indicatorKey === 'CMO') {
        options.length = 14;
    } else if (indicatorKey === 'DPO') {
        options.length = 20;
    } else if (indicatorKey === 'RVI') {
        options.length = 14;
    } else if (indicatorKey === 'TSI') {
        options.long = 25;
        options.short = 13;
    } else if (indicatorKey === 'KDJ') {
        options.kPeriod = 9;
        options.dPeriod = 3;
        options.jPeriod = 3;
    } else if (indicatorKey === 'WaveTrend') {
        options.channelLength = 10;
        options.averageLength = 21;
        options.movingAverageLength = 9;
    } else if (indicatorKey === 'SchaffTrendCycle') {
        options.macdPeriod = 23;
        options.signalPeriod = 50;
        options.cyclePeriod = 10;
    } else {
        // 默认参数
        options.length = options.length || 20;
    }
    
    // 判断是否是副图指标
    const subChartIndicators = [
        'RSI', 'Stochastic', 'StochRSI', 'CCI', 'WilliamsPercentRange',
        'AwesomeOscillator', 'ChandeMO', 'DPO', 
        
        'RVI', 'TSI', 'UltimateOscillator', 'KDJ', 'WaveTrend', 'SchaffTrendCycle', 
        'MACD', 'Momentum', 'ROC', 'BOP',
        'BullBearPower', 'CoppockCurve', 'TRIX', 'SqueezeMomentum',
        'ADX', 'Aroon', 'ZigZag', 'ATR', 'StandardDeviation',
        'Choppiness', 'BetterVolume', 'MFI', 'OBV', 'VolumeAccumulationPct', 'HistoricalVolatility', 'BetterVolume'
        ,'PROFILE'
    ];
    
    if (subChartIndicators.includes(indicatorKey)) {
        options.subChart = true;
    }
    
    return options;
}

// 计算总指标数量
function countTotalIndicators() {
    if (!window.indicatorCategories) return 0;
    return window.indicatorCategories.reduce((total, category) => {
        return total + (category.indicators ? category.indicators.length : 0);
    }, 0);
}

// ============================
// 多语言管理器
// ============================
class LanguageManager {
    constructor() {
        this.currentLang = localStorage.getItem('chart_language') || 'zh';
        this.init();
    }
    
    init() {
        console.log(`🌐 初始化多语言管理器，当前语言: ${this.getLanguageName()}`);
    }
    
    setLanguage(lang) {
        if (languageDict[lang]) {
            this.currentLang = lang;
            localStorage.setItem('chart_language', lang);
            this.updateAllTexts();
            console.log(`🌐 语言已切换为: ${this.getLanguageName()}`);
            return true;
        }
        return false;
    }
    
    toggleLanguage() {
        const newLang = this.currentLang === 'zh' ? 'en' : 'zh';
        return this.setLanguage(newLang);
    }
    
    getLanguage() {
        return this.currentLang;
    }
    
    getLanguageName() {
        return this.currentLang === 'zh' ? '中文' : 'English';
    }
    
    t(key, params = {}) {
        let text = languageDict[this.currentLang][key] || key;
        
        // 参数替换
        Object.keys(params).forEach(param => {
            text = text.replace(new RegExp(`{{${param}}}`, 'g'), params[param]);
        });
        
        return text;
    }
    
    updateAllTexts() {
        // 更新所有带 data-i18n 属性的元素
        document.querySelectorAll('[data-i18n]').forEach(element => {
            const key = element.getAttribute('data-i18n');
            const text = this.t(key);
            
            if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
                element.placeholder = text;
            } else {
                element.textContent = text;
            }
        });
        
        // 更新页面标题
        const title = this.t('chartPlusTemplate');
        document.title = title;
        
        // 触发语言变更事件
        this.triggerLanguageChange();
    }
    
    triggerLanguageChange() {
        const event = new CustomEvent('languageChanged', {
            detail: { language: this.currentLang }
        });
        document.dispatchEvent(event);
    }
}

// ============================
// 面板管理器 (支持多语言)
// ============================
class PanelManager {
    constructor() {
        this.panels = new Map();
        this.panelStates = {};
        this.languageManager = null;
        this.init();
    }
    
    setLanguageManager(lm) {
        this.languageManager = lm;
    }
    
    init() {
        console.log('🚀 初始化面板管理器');
        this.restorePanelStates();
    }
    
    t(key, params = {}) {
        if (this.languageManager) {
            return this.languageManager.t(key, params);
        }
        return key;
    }
    
    registerPanel(panelId, options = {}) {
        const panel = document.getElementById(panelId);
        if (!panel) {
            console.error(`❌ ${this.t('panelNotFound')}: #${panelId}`);
            return false;
        }
        
        const defaultOptions = {
            title: panelId,
            closable: true,
            draggable: true,
            resizable: true,
            minWidth: 200,
            minHeight: 150,
            defaultPosition: { x: window.innerWidth - 320, y: 20 }, // 【修改】确保在右侧显示
            defaultSize: { width: 300, height: 500 },
            rememberState: true
        };
        
        this.panels.set(panelId, {
            element: panel,
            visible: true,
            options: { ...defaultOptions, ...options },
            zIndex: 1000
        });
        
        console.log(`✅ ${this.t('panel')} 注册: #${panelId}`);
        
        // 初始化面板UI
        this.initPanelUI(panelId);
        
        return true;
    }
    
    initPanelUI(panelId) {
        const panelData = this.panels.get(panelId);
        if (!panelData) return;
        
        const panel = panelData.element;
        const options = panelData.options;
        
        // 如果面板已有 header，移除并重新创建
        const existingHeader = panel.querySelector('.panel-header');
        if (existingHeader) {
            existingHeader.remove();
        }
        
        // 添加面板标题栏
        const header = document.createElement('div');
        header.className = 'panel-header';
        header.innerHTML = `
            <span class="panel-title" data-i18n="indicatorPanel">${options.title}</span>
            <div class="panel-controls">
                ${options.closable ? '<button class="panel-close" data-i18n="close">×</button>' : ''}
            </div>
        `;
        panel.insertBefore(header, panel.firstChild);
        
        // 添加关闭按钮事件
        if (options.closable) {
            const closeBtn = header.querySelector('.panel-close');
            closeBtn.addEventListener('click', () => this.hidePanel(panelId));
        }
        
        // 添加拖拽功能
        if (options.draggable) {
            header.style.cursor = 'move';
            this.makeDraggable(panel, header);
        }
        
        // 应用样式
        this.applyPanelStyles(panel, header);
        
        // 【新增】设置初始位置，确保在右侧
        this.applyInitialPosition(panel, options.defaultPosition);
    }
    
    applyInitialPosition(panel, defaultPosition) {
        // 确保面板显示在右侧
        if (defaultPosition) {
            panel.style.position = 'fixed';
            panel.style.left = defaultPosition.x + 'px';
            panel.style.top = defaultPosition.y + 'px';
        }
    }
    
    applyPanelStyles(panel, header) {
        // 确保面板有基本样式
        panel.style.position = 'fixed';  // 改为 fixed 以准确定位
        panel.style.background = '#1e222d';
        panel.style.border = '1px solid #2a2e39';
        panel.style.borderRadius = '4px';
        panel.style.boxShadow = '0 2px 10px rgba(0,0,0,0.3)';
        panel.style.fontFamily = 'Arial, sans-serif';
        panel.style.zIndex = '1000';
        panel.style.display = 'block';
        
        // 标题栏样式
        header.style.background = '#2a2e39';
        header.style.padding = '8px 12px';
        header.style.borderBottom = '1px solid #2a2e39';
        header.style.cursor = 'move';
        header.style.display = 'flex';
        header.style.justifyContent = 'space-between';
        header.style.alignItems = 'center';
        header.style.borderRadius = '4px 4px 0 0';
        
        // 标题样式
        const title = header.querySelector('.panel-title');
        if (title) {
            title.style.fontWeight = 'bold';
            title.style.fontSize = '14px';
            title.style.color = '#d1d4dc';
        }
        
        // 关闭按钮样式
        const closeBtn = header.querySelector('.panel-close');
        if (closeBtn) {
            closeBtn.style.background = 'none';
            closeBtn.style.border = 'none';
            closeBtn.style.fontSize = '18px';
            closeBtn.style.cursor = 'pointer';
            closeBtn.style.color = '#999';
            closeBtn.style.width = '20px';
            closeBtn.style.height = '20px';
            closeBtn.style.display = 'flex';
            closeBtn.style.alignItems = 'center';
            closeBtn.style.justifyContent = 'center';
            closeBtn.style.borderRadius = '3px';
            
            closeBtn.addEventListener('mouseenter', () => {
                closeBtn.style.color = '#fff';
                closeBtn.style.background = '#363a45';
            });
            
            closeBtn.addEventListener('mouseleave', () => {
                closeBtn.style.color = '#999';
                closeBtn.style.background = 'none';
            });
        }
    }
    
    makeDraggable(panel, handle) {
        let isDragging = false;
        let startX, startY, startLeft, startTop;
        
        handle.addEventListener('mousedown', (e) => {
            isDragging = true;
            startX = e.clientX;
            startY = e.clientY;
            
            const rect = panel.getBoundingClientRect();
            startLeft = rect.left;
            startTop = rect.top;
            
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            
            e.preventDefault();
        });
        
        const onMouseMove = (e) => {
            if (!isDragging) return;
            
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            
            panel.style.left = (startLeft + dx) + 'px';
            panel.style.top = (startTop + dy) + 'px';
        };
        
        const onMouseUp = () => {
            isDragging = false;
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            this.savePanelState(panel.id);
        };
    }
    
    showPanel(panelId, bringToFront = true) {
        if (!this.panels.has(panelId)) {
            console.error(`❌ ${this.t('panelNotFound')}: #${panelId}`);
            return false;
        }
        
        const panelData = this.panels.get(panelId);
        panelData.element.style.display = 'block';
        panelData.element.classList.remove('hidden');
        panelData.visible = true;
        
        if (bringToFront) {
            this.bringToFront(panelId);
        }
        
        console.log(`✅ ${this.t('showPanel')}: #${panelId}`);
        this.savePanelState(panelId);
        
        // 触发显示事件
        this.triggerPanelEvent(panelId, 'show');
        
        return true;
    }
    
    hidePanel(panelId) {
        if (!this.panels.has(panelId)) {
            console.error(`❌ ${this.t('panelNotFound')}: #${panelId}`);
            return false;
        }
        
        const panelData = this.panels.get(panelId);
        panelData.element.style.display = 'none';
        panelData.element.classList.add('hidden');
        panelData.visible = false;
        
        console.log(`⏸️ ${this.t('hidePanel')}: #${panelId}`);
        this.savePanelState(panelId);
        
        // 触发隐藏事件
        this.triggerPanelEvent(panelId, 'hide');
        
        return true;
    }
    
    togglePanel(panelId) {
        if (!this.panels.has(panelId)) {
            console.error(`❌ ${this.t('panelNotFound')}: #${panelId}`);
            return false;
        }
        
        const panelData = this.panels.get(panelId);
        const isVisible = panelData.element.style.display !== 'none' && 
                         !panelData.element.classList.contains('hidden');
        
        if (isVisible) {
            return this.hidePanel(panelId);
        } else {
            return this.showPanel(panelId);
        }
    }
    
    bringToFront(panelId) {
        if (!this.panels.has(panelId)) return;
        
        const maxZIndex = Math.max(...Array.from(this.panels.values())
            .map(p => p.zIndex)
            .filter(z => typeof z === 'number'), 1000);
        
        const panelData = this.panels.get(panelId);
        panelData.zIndex = maxZIndex + 1;
        panelData.element.style.zIndex = panelData.zIndex;
    }
    
    savePanelState(panelId) {
        try {
            const panelData = this.panels.get(panelId);
            if (panelData && panelData.options.rememberState) {
                const state = {
                    visible: panelData.visible,
                    left: panelData.element.style.left,
                    top: panelData.element.style.top,
                    width: panelData.element.style.width,
                    height: panelData.element.style.height
                };
                localStorage.setItem(`panel_state_${panelId}`, JSON.stringify(state));
            }
        } catch (e) {
            console.warn(`⚠️ ${this.t('operationFailed')}: ${panelId}`);
        }
    }
    
    restorePanelStates() {
        this.panels.forEach((panelData, panelId) => {
            try {
                const savedState = localStorage.getItem(`panel_state_${panelId}`);
                if (savedState) {
                    const state = JSON.parse(savedState);
                    if (state.visible !== undefined) {
                        if (state.visible) {
                            this.showPanel(panelId, false);
                        } else {
                            this.hidePanel(panelId);
                        }
                    }
                    
                    // 恢复位置和大小
                    if (state.left) panelData.element.style.left = state.left;
                    if (state.top) panelData.element.style.top = state.top;
                    if (state.width) panelData.element.style.width = state.width;
                    if (state.height) panelData.element.style.height = state.height;
                }
            } catch (e) {
                console.warn(`⚠️ ${this.t('operationFailed')}: ${panelId}`);
            }
        });
    }
    
    triggerPanelEvent(panelId, eventName) {
        const event = new CustomEvent(`panel${eventName.charAt(0).toUpperCase() + eventName.slice(1)}`, {
            detail: { panelId: panelId }
        });
        document.dispatchEvent(event);
    }
    
    getAllPanels() {
        return Array.from(this.panels.keys());
    }
    
    getPanelInfo(panelId) {
        if (!this.panels.has(panelId)) return null;
        
        const panelData = this.panels.get(panelId);
        return {
            id: panelId,
            visible: panelData.visible,
            element: panelData.element,
            options: panelData.options
        };
    }
}

// ============================
// 指标管理器
// ============================
class IndicatorManager {
    constructor() {
        this.indicatorStates = new Map();
        this.activeIndicators = {};
        this.panelManager = null;
        this.languageManager = null;
        this.init();
    }
    
    setPanelManager(pm) {
        this.panelManager = pm;
    }
    
    setLanguageManager(lm) {
        this.languageManager = lm;
    }
    
    t(key, params = {}) {
        if (this.languageManager) {
            return this.languageManager.t(key, params);
        }
        return key;
    }
    
    init() {
        console.log('📊 初始化指标管理器');
        
        // 确保全局变量存在
        if (!window.activeIndicators) {
            window.activeIndicators = {};
        }
        
        // 初始化指标状态
        this.indicatorStates.clear();
    }
    
    registerIndicatorButtonEvents() {
        // 通过事件委托处理指标按钮点击
        document.addEventListener('click', (e) => {
            const button = e.target.closest('.indicator-button');
            if (!button) return;
            
            const indicatorName = button.getAttribute('data-indicator');
            if (!indicatorName) return;
            
            this.toggleIndicator(indicatorName);
        });
    }
    
    toggleIndicator(indicatorName, options = {}) {
        const isActive = this.indicatorStates.get(indicatorName) || false;
        
        console.log(`🔄 ${this.t('toggleIndicator')}: ${indicatorName}, 当前状态: ${isActive ? '激活' : '未激活'}`);
        
        if (isActive) {
            // 【修改】隐藏指标
            this.hideIndicator(indicatorName);
        } else {
            // 【修改】显示指标
            this.showIndicator(indicatorName, options);
        }
        
        return !isActive;
    }

    showIndicator(indicatorName, options = {}) {
        console.log(`👁️ ${this.t('showIndicator')}: ${indicatorName}`, options);
        
        // 特殊处理PROFILE
        if (indicatorName === 'PROFILE') {
            console.log('🎯 IndicatorManager: 特殊处理PROFILE显示');
            
            this.indicatorStates.set(indicatorName, true);
            this.updateIndicatorButtonState(indicatorName, true);
            
            if (window.showIndicatorFromPython) {
                return window.showIndicatorFromPython(indicatorName, options);
            }
            return true;
        }

        // 更新按钮状态
        this.updateIndicatorButtonState(indicatorName, true);
        
        // 【修改】保存可见状态
        this.indicatorStates.set(indicatorName, true);
        
        // 设置可见性
        options.visible = true;
        
        // 【修改】调用图表系统的显示函数
        if (window.showIndicatorFromPython) {
            try {
                return window.showIndicatorFromPython(indicatorName, options);
            } catch (error) {
                console.error(`❌ 显示指标失败:`, error);
                this.indicatorStates.set(indicatorName, false);
                this.updateIndicatorButtonState(indicatorName, false);
                return false;
            }
        } else if (window.addIndicatorFromPython) {
            // 回退到添加指标
            try {
                return window.addIndicatorFromPython(indicatorName, options);
            } catch (error) {
                console.error(`❌ 显示指标失败:`, error);
                this.indicatorStates.set(indicatorName, false);
                this.updateIndicatorButtonState(indicatorName, false);
                return false;
            }
        } else {
            console.error('❌ 没有可用的显示指标函数');
            this.indicatorStates.set(indicatorName, false);
            this.updateIndicatorButtonState(indicatorName, false);
            return false;
        }
    }
    
    hideIndicator(indicatorName) {
        console.log(`🙈 ${this.t('hideIndicator')}: ${indicatorName}`);
        
        // 特殊处理PROFILE
        if (indicatorName === 'PROFILE') {
            console.log('🎯 IndicatorManager: 特殊处理PROFILE隐藏');
            
            this.indicatorStates.set(indicatorName, false);
            this.updateIndicatorButtonState(indicatorName, false);
            
            if (window.hideIndicatorFromPython) {
                return window.hideIndicatorFromPython(indicatorName);
            }
            return true;
        }

        // 更新按钮状态
        this.updateIndicatorButtonState(indicatorName, false);
        
        // 【修改】保存隐藏状态
        this.indicatorStates.set(indicatorName, false);
        
        // 【修改】调用图表系统的隐藏函数
        if (window.hideIndicatorFromPython) {
            return window.hideIndicatorFromPython(indicatorName);
        } else if (window.removeIndicatorFromPython) {
            // 回退到移除指标
            return window.removeIndicatorFromPython(indicatorName);
        } else {
            console.error('❌ 没有可用的隐藏指标函数');
            return false;
        }
    }
    
    addIndicator(indicatorName, options = {}) {
        console.log(`➕ ${this.t('addIndicator')}: ${indicatorName}`, options);
        
        // 【修复】更新按钮状态
        this.updateIndicatorButtonState(indicatorName, true);
        
        // 【关键修复】保存当前状态
        this.indicatorStates.set(indicatorName, true);
        
        // 【关键修复】直接调用图表系统的原始函数
        if (window.addIndicatorFromPython) {
            try {
                const result = window.addIndicatorFromPython(indicatorName, options);
                if (!result) {
                    // 如果失败，恢复按钮状态
                    this.indicatorStates.set(indicatorName, false);
                    this.updateIndicatorButtonState(indicatorName, false);
                }
                return result;
            } catch (error) {
                console.error(`❌ 添加指标 ${indicatorName} 失败:`, error);
                this.indicatorStates.set(indicatorName, false);
                this.updateIndicatorButtonState(indicatorName, false);
                return false;
            }
        } else {
            console.error('❌ window.addIndicatorFromPython 函数未找到');
            this.indicatorStates.set(indicatorName, false);
            this.updateIndicatorButtonState(indicatorName, false);
            return false;
        }
    }
    
    removeIndicator(indicatorName) {
        console.log(`➖ ${this.t('removeIndicator')}: ${indicatorName}`);
        
        // 更新按钮状态
        this.updateIndicatorButtonState(indicatorName, false);
        
        // 更新本地状态
        this.indicatorStates.set(indicatorName, false);
        
        // 【关键修复】直接调用图表系统的移除函数
        if (window.removeIndicatorFromPython) {
            return window.removeIndicatorFromPython(indicatorName);
        } else {
            console.error('❌ 没有可用的移除指标函数');
            return false;
        }
    }
    
    updateIndicatorButtonState(indicatorName, isActive) {
        const button = document.querySelector(`[data-indicator="${indicatorName}"]`);
        if (button) {
            if (isActive) {
                button.classList.add('active');
                button.style.backgroundColor = '#2962FF';
                button.style.color = 'white';
                button.style.borderColor = '#2962FF';
            } else {
                button.classList.remove('active');
                button.style.backgroundColor = '#131722';
                button.style.color = '#d1d4dc';
                button.style.borderColor = '#2a2e39';
            }
        }
    }
    
    getIndicatorOptions(indicatorName, baseOptions = {}) {
        const options = { ...baseOptions, visible: true };
        
        // 根据指标名称设置特定参数
        if (indicatorName.includes('SMA_')) {
            const length = indicatorName.split('_')[1];
            options.length = parseInt(length) || 20;
        } else if (indicatorName === 'EMA_12') {
            options.length = 12;
        } else if (indicatorName === 'EMA_26') {
            options.length = 26;
        } else if (indicatorName === 'RSI') {
            options.length = 14;
        } else if (indicatorName === 'MACD') {
            options.fastLength = 12;
            options.slowLength = 26;
            options.signalLength = 9;
        } else if (indicatorName === 'BollingerBands') {
            options.length = 20;
            options.stdDev = 2;
        } else if (indicatorName === 'Stochastic') {
            options.length = 14;
            options.smoothK = 3;
            options.smoothD = 3;
        } else {
            // 默认参数
            options.length = options.length || 20;
        }
        
        // 判断是否是副图指标
        const subChartIndicators = [
            'RSI', 'Stochastic', 'StochRSI', 'CCI', 'WilliamsPercentRange',
            'AwesomeOscillator', 'ChandeMO', 'DPO', 
            
            'RVI', 'TSI', 'UltimateOscillator', 'KDJ', 'WaveTrend', 'SchaffTrendCycle', 
            'MACD', 'Momentum', 'ROC', 'BOP',
            'BullBearPower', 'CoppockCurve', 'TRIX', 'SqueezeMomentum',
            'ADX', 'Aroon', 'ZigZag', 'ATR', 'StandardDeviation',
            'Choppiness', 'BetterVolume', 'MFI', 'OBV', 'VolumeAccumulationPct', 'HistoricalVolatility', 'BetterVolume'
            ,'PROFILE'
        ];
        
        if (subChartIndicators.includes(indicatorName)) {
            options.subChart = true;
        }
        
        return options;
    }
    
    getAllIndicators() {
        return Array.from(this.indicatorStates.keys());
    }
    
    getActiveIndicators() {
        return Array.from(this.indicatorStates.entries())
            .filter(([name, active]) => active)
            .map(([name]) => name);
    }
}

// ============================
// 主应用程序
// ============================
class ChartPlusApp {
    constructor() {
        this.languageManager = null;
        this.panelManager = null;
        this.indicatorManager = null;
        this.init();
    }
    
    init() {
        console.log('🚀 启动 Chart Plus 应用程序');
        
        // 初始化管理器
        this.languageManager = new LanguageManager();
        this.panelManager = new PanelManager();
        this.indicatorManager = new IndicatorManager();
        
        // 设置依赖
        this.panelManager.setLanguageManager(this.languageManager);
        this.indicatorManager.setLanguageManager(this.languageManager);
        this.indicatorManager.setPanelManager(this.panelManager);
        
        // 初始化UI
        this.initUI();
        
        // 填充指标面板
        setTimeout(() => {
            this.populateIndicatorPanel();
        }, 100);
        
        // 注册事件监听
        this.registerEventListeners();
        
        // 应用语言
        this.languageManager.updateAllTexts();
        
        console.log('✅ Chart Plus 应用程序初始化完成');
    }
    
    registerEventListeners() {
        // 语言切换按钮
        document.getElementById('language-toggle')?.addEventListener('click', () => {
            this.languageManager.toggleLanguage();
        });
        
        // 监听语言变更事件
        document.addEventListener('languageChanged', (e) => {
            console.log(`🌐 语言已更改为: ${e.detail.language}`);
        });
    }
    
    initUI() {
        // 注册指标面板
        this.panelManager.registerPanel('indicatorPanel', {
            title: '技术指标 / Indicators',
            closable: false,
            draggable: false,
            resizable: true,
            defaultPosition: { x: window.innerWidth - 280, y: 0 }, // 右侧位置
            defaultSize: { width: 300, height: 500 }
        });
        
        // 显示指标面板
        this.panelManager.showPanel('indicatorPanel');
    }
    
    populateIndicatorPanel() {
        const panel = document.getElementById('indicatorPanel');
        if (!panel) {
            console.error('❌ 指标面板未找到: #indicatorPanel');
            return;
        }
        
        // 获取面板内容区域
        let content = panel.querySelector('.panel-content');
        if (!content) {
            content = document.createElement('div');
            content.className = 'panel-content';
            content.style.padding = '10px';
            content.style.overflowY = 'auto';
            content.style.maxHeight = 'calc(100% - 40px)';
            panel.appendChild(content);
        }
        
        // 清空现有内容
        content.innerHTML = '';
        
        // 检查是否有 indicatorCategories
        if (!window.indicatorCategories) {
            console.warn('⚠️ 指标分类数据未加载');
            content.innerHTML = '<div style="color: #666; padding: 20px; text-align: center;">'
                              + '指标分类数据未加载...</div>';
            return;
        }
        
        console.log(`📊 开始填充指标面板，共 ${window.indicatorCategories.length} 个分类`);
        
        // 遍历每个指标分类
        window.indicatorCategories.forEach(category => {
            // 创建分类容器
            const categoryDiv = document.createElement('div');
            categoryDiv.className = 'indicator-category';
            categoryDiv.style.marginBottom = '15px';
            categoryDiv.style.border = '1px solid #2a2e39';
            categoryDiv.style.borderRadius = '6px';
            categoryDiv.style.overflow = 'hidden';
            categoryDiv.style.background = '#1e222d';
            
            // 创建分类标题
            const categoryTitle = document.createElement('div');
            categoryTitle.className = 'category-title';
            categoryTitle.textContent = category.name;
            categoryTitle.style.background = '#2a2e39';
            categoryTitle.style.padding = '8px 12px';
            categoryTitle.style.fontWeight = 'bold';
            categoryTitle.style.fontSize = '12px';
            categoryTitle.style.cursor = 'pointer';
            categoryTitle.style.userSelect = 'none';
            categoryTitle.style.color = '#d1d4dc';
            categoryTitle.style.transition = 'background 0.2s ease';
            
            // 创建指标容器
            const indicatorsContainer = document.createElement('div');
            indicatorsContainer.className = 'category-content';
            indicatorsContainer.style.padding = '8px';
            indicatorsContainer.style.display = 'grid';
            indicatorsContainer.style.gridTemplateColumns = 'repeat(2, 1fr)';
            indicatorsContainer.style.gap = '5px';
            indicatorsContainer.style.backgroundColor = '#1e222d';
            
            // 为分类标题添加点击事件
            let isCollapsed = false;
            categoryTitle.addEventListener('click', () => {
                isCollapsed = !isCollapsed;
                indicatorsContainer.style.display = isCollapsed ? 'none' : 'grid';
                const icon = categoryTitle.querySelector('.collapse-icon') || 
                            categoryTitle.firstChild;
                if (isCollapsed) {
                    categoryTitle.innerHTML = '▶ ' + category.name;
                } else {
                    categoryTitle.innerHTML = '▼ ' + category.name;
                }
            });
            
            // 在标题前添加折叠图标
            categoryTitle.innerHTML = '▼ ' + category.name;
            
            // 【关键修复】保存当前实例的引用
            const appInstance = this;
            
            // 遍历分类中的指标
            category.indicators.forEach(indicator => {
                const button = document.createElement('button');
                button.className = 'indicator-button';
                button.setAttribute('data-indicator', indicator.key);
                button.textContent = indicator.name;
                
                // 设置样式
                button.style.cssText = `
                    padding: 6px 8px;
                    margin: 2px;
                    border: 1px solid #2a2e39;
                    background: #131722;
                    color: #d1d4dc;
                    cursor: pointer;
                    border-radius: 4px;
                    font-size: 11px;
                    text-align: center;
                    transition: all 0.2s ease;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                `;
                
                // 添加悬停效果
                button.addEventListener('mouseenter', () => {
                    if (!button.classList.contains('active')) {
                        button.style.background = '#2a2e39';
                        button.style.borderColor = '#2962FF';
                    }
                });
                
                button.addEventListener('mouseleave', () => {
                    if (!button.classList.contains('active')) {
                        button.style.background = '#131722';
                        button.style.borderColor = '#2a2e39';
                    }
                });
                
                // 【关键修复】使用箭头函数避免 this 绑定问题
                button.addEventListener('click', (event) => {
                    const indicatorKey = button.getAttribute('data-indicator');
                    console.log(`🔄 点击指标按钮: ${indicatorKey}`);
                    
                    if (appInstance.indicatorManager) {
                        appInstance.indicatorManager.toggleIndicator(indicatorKey);
                    } else {
                        console.error('❌ IndicatorManager 未初始化');
                    }
                    
                    event.stopPropagation();
                });
                
                // 添加工具提示
                button.title = `${indicator.name} (${indicator.en})`;
                
                indicatorsContainer.appendChild(button);
            });
            
            // 组装分类
            categoryDiv.appendChild(categoryTitle);
            categoryDiv.appendChild(indicatorsContainer);
            content.appendChild(categoryDiv);
        });
        
        console.log(`✅ 指标面板已成功填充，共添加了 ${this.countTotalIndicators()} 个指标按钮`);
    }
    
    countTotalIndicators() {
        if (!window.indicatorCategories) return 0;
        return window.indicatorCategories.reduce((total, category) => {
            return total + (category.indicators ? category.indicators.length : 0);
        }, 0);
    }
    
    getLanguageManager() {
        return this.languageManager;
    }
    
    getPanelManager() {
        return this.panelManager;
    }
    
    getIndicatorManager() {
        return this.indicatorManager;
    }
    
    t(key, params = {}) {
        return this.languageManager.t(key, params);
    }
}

// ============================
// 全局导出
// ============================
function initChartPlusApp() {
    if (!chartPlusApp) {
        chartPlusApp = new ChartPlusApp();
    }
    return chartPlusApp;
}

// 【关键修复】移除全局的 addIndicator 和 removeIndicator 函数定义
// 避免与 chart_plus_template.js 中的同名函数冲突
// 菜单系统通过 IndicatorManager 直接调用 addIndicatorFromPython 和 removeIndicatorFromPython

// 全局函数
window.togglePanel = function(panelId) {
    if (chartPlusApp) {
        return chartPlusApp.getPanelManager().togglePanel(panelId);
    }
    return false;
};

window.toggleLanguage = function() {
    if (chartPlusApp) {
        return chartPlusApp.getLanguageManager().toggleLanguage();
    }
    return false;
};

window.populateIndicatorPanel = function() {
    if (chartPlusApp) {
        return chartPlusApp.populateIndicatorPanel();
    } else {
        console.warn('⚠️ ChartPlusApp 未初始化，请稍后重试');
        return false;
    }
};

// 【简化】导出到全局
window.ChartPlus = {
    init: initChartPlusApp,
    togglePanel: window.togglePanel,
    toggleLanguage: window.toggleLanguage,
    populateIndicatorPanel: window.populateIndicatorPanel,
    t: function(key, params) {
        if (chartPlusApp) {
            return chartPlusApp.t(key, params);
        }
        return key;
    }
};

// ============================
// 自动初始化
// ============================
document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化，确保DOM完全加载
    setTimeout(() => {
        chartPlusApp = initChartPlusApp();
        console.log('📊 Chart Plus 模板菜单已加载');
        
        // 调用 initIndicatorPanel 以确保与 tool.js 对齐
        if (typeof window.initIndicatorPanel === 'function') {
            window.initIndicatorPanel();
        }
    }, 100);
});

// ============================
// CSS样式
// ============================
const style = document.createElement('style');
style.textContent = `
    .panel {
        position: absolute;
        background: #1e222d;
        border: 1px solid #2a2e39;
        border-radius: 4px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        font-family: Arial, sans-serif;
        z-index: 1000;
    }
    
    .panel.hidden {
        display: none;
    }
    
    .panel-header {
        background: #2a2e39;
        padding: 8px 12px;
        border-bottom: 1px solid #2a2e39;
        cursor: move;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-radius: 4px 4px 0 0;
    }
    
    .panel-title {
        font-weight: bold;
        font-size: 14px;
        color: #d1d4dc;
    }
    
    .panel-controls {
        display: flex;
        gap: 4px;
    }
    
    .panel-close {
        background: none;
        border: none;
        font-size: 18px;
        cursor: pointer;
        color: #999;
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 3px;
    }
    
    .panel-close:hover {
        color: #fff;
        background: #363a45;
    }
    
    .panel-content {
        padding: 10px;
        overflow-y: auto;
        max-height: calc(100% - 40px);
    }
    
    /* 指标分类样式 */
    .indicator-category {
        margin-bottom: 15px;
        border: 1px solid #2a2e39;
        border-radius: 6px;
        overflow: hidden;
        background: #1e222d;
        transition: all 0.3s ease;
    }
    
    .indicator-category:hover {
        border-color: #363a45;
    }
    
    .category-title {
        background: #2a2e39;
        padding: 8px 12px;
        font-weight: bold;
        font-size: 12px;
        cursor: pointer;
        user-select: none;
        color: #d1d4dc;
        transition: background 0.2s ease;
    }
    
    .category-title:hover {
        background: #363a45;
    }
    
    .category-content {
        padding: 8px;
        display: grid;
        grid-templateColumns: repeat(2, 1fr);
        gap: 5px;
        background-color: #1e222d;
        transition: all 0.3s ease;
    }
    
    .indicator-button {
        padding: 6px 8px;
        margin: 2px;
        border: 1px solid #2a2e39;
        background: #131722;
        color: #d1d4dc;
        cursor: pointer;
        border-radius: 4px;
        font-size: 11px;
        text-align: center;
        transition: all 0.2s ease;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    .indicator-button:hover {
        background: #2a2e39;
        border-color: #2962FF;
    }
    
    .indicator-button.active {
        background: #2962FF;
        color: white;
        border-color: '#2962FF';
    }
    
    .language-toggle {
        position: fixed;
        top: 10px;
        right: 10px;
        padding: 6px 12px;
        background: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        z-index: 9999;
    }
`;

document.head.appendChild(style);

// 调试函数
window.debugChartPlus = function() {
    console.log('🔧 调试 Chart Plus 系统:');
    
    // 检查状态
    const status = {
        'window.chartPlusApp': !!window.chartPlusApp,
        'window.ChartPlus': !!window.ChartPlus,
        'window.ChartPlus.init': !!(window.ChartPlus && window.ChartPlus.init),
        'window.indicatorCategories': !!window.indicatorCategories,
        'window.addIndicatorFromPython': !!(window.addIndicatorFromPython),
        'window.removeIndicatorFromPython': !!(window.removeIndicatorFromPython),
        'window.initIndicatorPanel': !!(window.initIndicatorPanel)
    };
    
    console.table(status);
    
    // 检查 DOM 元素
    const panel = document.getElementById('indicatorPanel');
    console.log('📄 indicatorPanel 元素:', panel ? '找到' : '未找到');
    
    if (panel) {
        console.log('📄 面板内容长度:', panel.innerHTML.length);
    }
    
    // 检查按钮事件绑定
    const buttons = document.querySelectorAll('.indicator-button');
    console.log(`找到 ${buttons.length} 个指标按钮`);
    
    if (buttons.length > 0) {
        const firstButton = buttons[0];
        console.log('第一个按钮的 data-indicator:', firstButton.getAttribute('data-indicator'));
        
        // 测试添加指标
        const indicatorKey = firstButton.getAttribute('data-indicator');
        if (indicatorKey && window.addIndicatorFromPython) {
            console.log(`🧪 测试添加指标: ${indicatorKey}`);
            window.addIndicatorFromPython(indicatorKey, { length: 20 });
        }
    }
};

// 显示/隐藏指标的函数
function updateIndicatorVisibility(indicatorName, visible) {
    console.log(`🔧 更新指标可见性: ${indicatorName} = ${visible}`);
    
    if (!seriesMap.has(indicatorName)) {
        console.warn(`⚠️ 指标 ${indicatorName} 未找到`);
        return false;
    }
    
    const indicatorInfo = seriesMap.get(indicatorName);
    if (indicatorInfo && indicatorInfo.series) {
        indicatorInfo.series.applyOptions({ visible: visible });
        indicatorInfo.visible = visible;
        
        // 更新右侧面板按钮状态
        updateRightPanelButton(indicatorName, visible);
        
        console.log(`✅ 指标 ${indicatorName} 可见性已更新: ${visible}`);
        return true;
    }
    
    return false;
}

// 暴露到全局
window.updateIndicatorVisibility = updateIndicatorVisibility;
window.showIndicatorFromPython = function(indicatorName, options = {}) {
    console.log(`🐍 来自Python的显示指标调用: ${indicatorName}`);
    
    // 特殊处理PROFILE指标
    if (indicatorName === 'PROFILE') {
        console.log('🎯 特殊处理PROFILE指标显示');
        
        // 检查是否已激活
        if (window.indicatorStates && window.indicatorStates.get(indicatorName) === true) {
            console.log(`ℹ️ 指标 ${indicatorName} 已激活，跳过`);
            return true;
        }
        
        // 1. 更新按钮状态
        const button = document.querySelector(`[data-indicator="${indicatorName}"]`);
        if (button) {
            button.classList.add('active');
            button.style.backgroundColor = '#2962FF';
            button.style.color = 'white';
            button.style.borderColor = '#2962FF';
        }
        
        // 2. 更新指标状态
        if (window.indicatorStates) {
            window.indicatorStates.set(indicatorName, true);
        }
        
        // 3. 直接调用Python端添加PROFILE
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('add_yearly_profile', {
                indicator: indicatorName,
                options: { ...options, visible: true }
            });
        }
        
        return true;
    }

    // 增强的状态检查函数
    const isIndicatorTrulyExists = (indicatorName) => {
        // 1. 检查是否在 seriesMap 中存在
        if (!seriesMap.has(indicatorName)) {
            console.log(`🔍 指标 ${indicatorName} 不在 seriesMap 中`);
            return false;
        }
        
        const indicatorInfo = seriesMap.get(indicatorName);
        
        // 2. 检查 indicatorInfo 是否有效
        if (!indicatorInfo) {
            console.log(`🔍 指标 ${indicatorName} 的 info 为空`);
            return false;
        }
        
        // 3. 检查是否有 series 对象
        if (!indicatorInfo.series) {
            console.log(`🔍 指标 ${indicatorName} 没有 series 对象`);
            return false;
        }
        
        // 4. 检查 series 对象是否有效
        try {
            // 尝试访问 series 的属性，确认其存在
            if (typeof indicatorInfo.series !== 'object') {
                console.log(`🔍 指标 ${indicatorName} 的 series 不是有效对象`);
                return false;
            }
            
            // 额外检查：是否有必要的图表方法
            if (!indicatorInfo.series.applyOptions) {
                console.log(`🔍 指标 ${indicatorName} 的 series 缺少 applyOptions 方法`);
                return false;
            }
            
            return true;
        } catch (error) {
            console.log(`🔍 检查指标 ${indicatorName} 的 series 时出错:`, error);
            return false;
        }
    };
    
    // 检查指标是否真正存在
    if (isIndicatorTrulyExists(indicatorName)) {
        console.log(`✅ 指标 ${indicatorName} 已存在，更新可见性`);
        return updateIndicatorVisibility(indicatorName, true);
    } else {
        console.log(`🔄 指标 ${indicatorName} 不存在或无效，添加新指标`);
        return addIndicator(indicatorName, { ...options, visible: true });
    }
};

window.hideIndicatorFromPython = function(indicatorName) {
    console.log(`🐍 来自Python的隐藏指标调用: ${indicatorName}`);

    // 特殊处理PROFILE指标
    if (indicatorName === 'PROFILE') {
        console.log('🎯 特殊处理PROFILE指标隐藏');
        
        // 1. 更新按钮状态
        const button = document.querySelector(`[data-indicator="${indicatorName}"]`);
        if (button) {
            button.classList.remove('active');
            button.style.backgroundColor = '#131722';
            button.style.color = '#d1d4dc';
            button.style.borderColor = '#2a2e39';
        }
        
        // 2. 更新指标状态
        window.indicatorStates.set(indicatorName, false);
        
        // 3. 调用Python端移除PROFILE图表
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('remove_profile', {
                indicator: indicatorName
            });
        }
        
        return true;
    }

    if (seriesMap.has(indicatorName)) {
        return updateIndicatorVisibility(indicatorName, false);
    }
    
    console.warn(`⚠️ 指标 ${indicatorName} 未找到，无法隐藏`);
    return false;
};