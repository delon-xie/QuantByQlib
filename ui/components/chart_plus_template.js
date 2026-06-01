/**
 * TradingView Plus Chart - 核心图表功能模块
 * 包含图表初始化、数据管理、指标添加等核心功能
 * 版本: 1.0.0
 * 修复记录:
 * 1. 修复了 LineSeries 未定义错误
 * 2. 修复了 visible 参数处理
 * 3. 修复了指标删除时的错误
 * 4. 优化了副图初始状态
 */

// ==================== 全局变量 ====================
let mainChart = null; 
let subChart = null;
let candleSeries = null;
const seriesMap = new Map(); // 存储指标系列信息 {name: {series, chart, visible}}
const indicatorStates = new Map(); // 存储指标状态
let isChartInitialized = false;
let isSyncing = false;
let chartData = [];

// 批量处理相关
let isBatchAdding = false;
let pendingRangeRestore = null;
let batchAddTimeout = null;

const specialCategory = {
    name: '特殊指标',
    indicators: [
        { key: 'SMA_5', name: 'SMA(5)', en: 'SMA(5)' },
        { key: 'SMA_10', name: 'SMA(10)', en: 'SMA(10)' },
        { key: 'SMA_20', name: 'SMA(20)', en: 'SMA(20)' },
        { key: 'EMA_12', name: 'EMA(12)', en: 'EMA(12)' },
        { key: 'EMA_26', name: 'EMA(26)', en: 'EMA(26)' },
        { key: 'SMAclassic', name: '经典MA组合', en: 'Classic MA Combo' },
        { key: 'MCGINLEY', name: 'McGinley动态', en: 'McGinley Dynamic' },
        { key: 'STOCH', name: '随机指标', en: 'Stochastic' },
        { key: 'StochRSI', name: '随机RSI', en: 'Stochastic RSI' },
        { key: 'ZigZag', name: '之字形指标', en: 'ZigZag' },
        { key: 'BetterVolume', name: '成交量', en: 'BetterVolume' },
        { key: 'PROFILE', name: '成交量分布', en: 'Volume Profile' }
    ]
};

// 指标分类配置
const indicatorCategories = [
    {
        name: '移动平均线 / Moving Averages (15)',
        key: 'MA_CATEGORY',
        indicators: [
            { name: 'SMA', en: 'SMA', key: 'SMA', group: 'MA' },
            { name: 'SMA组合', en: 'SMA Combo', key: 'SMAclassic', group: 'MA' },
            { name: 'SMA(5)', en: 'SMA 5', key: 'SMA_5', group: 'MA' },
            { name: 'SMA(10)', en: 'SMA 10', key: 'SMA_10', group: 'MA' },
            { name: 'SMA(20)', en: 'SMA 20', key: 'SMA_20', group: 'MA' },
            { name: 'EMA', en: 'EMA', key: 'EMA', group: 'MA' },
            { name: 'EMA(12)', en: 'EMA 12', key: 'EMA_12', group: 'MA' },
            { name: 'EMA(26)', en: 'EMA 26', key: 'EMA_26', group: 'MA' },
            { name: '三指数移动平均', en: 'TEMA', key: 'TEMA', group: 'MA' },
            { name: '加权移动平均', en: 'WMA', key: 'WMA', group: 'MA' },
            { name: '平滑移动平均', en: 'RMA', key: 'RMA', group: 'MA' },
            { name: '双指数移动平均', en: 'DEMA', key: 'DEMA', group: 'MA' },
            { name: 'Hull 移动平均', en: 'HMA', key: 'HMA', group: 'MA' },
            { name: '最小二乘移动平均', en: 'LSMA', key: 'LSMA', group: 'MA' },
            { name: 'ALMA 移动平均', en: 'ALMA', key: 'ALMA', group: 'MA' },
            { name: '成交量加权平均', en: 'VWMA', key: 'VWMA', group: 'MA' },
            { name: 'McGinley 动态', en: 'McGinley', key: 'MCGINLEY', group: 'MA' },
            { name: '均线交叉', en: 'EMA Cross', key: 'EMAMACross', group: 'MA' },
            { name: '均线带', en: 'MA Ribbon', key: 'MARibbon', group: 'MA' },
            { name: '零滞后 LSMA', en: 'ZLSMA', key: 'ZLSMA', group: 'MA' }
        ]
    },
    {
        name: '振荡指标 / Oscillators (25)',
        key: 'OSC_CATEGORY',
        indicators: [
            { name: '相对强弱指数', en: 'RSI', key: 'RSI', group: 'OSC' },
            { name: '随机指标', en: 'Stochastic', key: 'Stochastic', group: 'OSC' },
            { name: '随机 RSI', en: 'StochRSI', key: 'StochRSI', group: 'OSC' },
            { name: '商品通道指数', en: 'CCI', key: 'CCI', group: 'OSC' },
            { name: '威廉指标', en: 'Williams %R', key: 'WilliamsPercentRange', group: 'OSC' },
            { name: 'Awesome 振荡器', en: 'AO', key: 'AwesomeOscillator', group: 'OSC' },
            { name: 'Chande 动量', en: 'CMO', key: 'ChandeMO', group: 'OSC' },
            { name: '去趋势价格振荡器', en: 'DPO', key: 'DPO', group: 'OSC' },
            { name: '相对活力指数', en: 'RVI', key: 'RVI', group: 'OSC' },
            { name: '真实强度指数', en: 'TSI', key: 'TSI', group: 'OSC' },
            { name: '终极振荡器', en: 'UO', key: 'UltimateOscillator', group: 'OSC' },
            { name: 'KDJ', en: 'KDJ', key: 'KDJ', group: 'OSC' },
            { name: 'WaveTrend', en: 'WT', key: 'WaveTrend', group: 'OSC' },
            { name: 'Schaff 趋势周期', en: 'STC', key: 'SchaffTrendCycle', group: 'OSC' }
        ]
    },
    {
        name: '动量指标 / Momentum (15)',
        key: 'MOM_CATEGORY',
        indicators: [
            { name: 'MACD', en: 'MACD', key: 'MACD', group: 'MOM' },
            { name: '动量', en: 'Momentum', key: 'Momentum', group: 'MOM' },
            { name: '变化率', en: 'ROC', key: 'ROC', group: 'MOM' },
            { name: '平衡能量', en: 'BOP', key: 'BOP', group: 'MOM' },
            { name: '多空能量', en: 'BBP', key: 'BullBearPower', group: 'MOM' },
            { name: 'Coppock 曲线', en: 'Coppock', key: 'CoppockCurve', group: 'MOM' },
            { name: 'TRIX', en: 'TRIX', key: 'TRIX', group: 'MOM' },
            { name: 'Squeeze Momentum', en: 'Squeeze', key: 'SqueezeMomentum', group: 'MOM' }
        ]
    },
    {
        name: '趋势指标 / Trend (20)',
        key: 'TREND_CATEGORY',
        indicators: [
            { name: '平均趋向指数', en: 'ADX', key: 'ADX', group: 'TREND' },
            { name: '一目均衡图', en: 'Ichimoku', key: 'IchimokuCloud', group: 'TREND' },
            { name: '抛物线 SAR', en: 'SAR', key: 'ParabolicSAR', group: 'TREND' },
            { name: '超级趋势', en: 'SuperTrend', key: 'VolumeSuperTrendAi', group: 'TREND' },
            { name: 'Aroon', en: 'Aroon', key: 'Aroon', group: 'TREND' },
            { name: 'ZigZag', en: 'ZigZag', key: 'ZigZag', group: 'TREND' },
            { name: 'Williams Alligator', en: 'Alligator', key: 'WilliamsAlligator', group: 'TREND' },
            { name: 'Donchian 通道', en: 'Donchian', key: 'DonchianChannels', group: 'TREND' }
        ]
    },
    {
        name: '波动率 / Volatility (10)',
        key: 'VOL_CATEGORY',
        indicators: [
            { name: '平均真实波幅', en: 'ATR', key: 'ATR', group: 'VOL' },
            { name: '布林带', en: 'Bollinger', key: 'BollingerBands', group: 'VOL' },
            { name: '标准差', en: 'StdDev', key: 'StandardDeviation', group: 'VOL' },
            { name: '历史波动率', en: 'HV', key: 'HistoricalVolatility', group: 'VOL' },
            { name: 'Choppiness Index', en: 'CHOP', key: 'Choppiness', group: 'VOL' }
        ]
    },
    {
        name: '成交量 / Volume (10)',
        key: 'VOLUME_CATEGORY',
        indicators: [
            { name: '成交量', en: 'BetterVolume', key: 'BetterVolume', group: 'VOL' },
            { name: '成交量加权', en: 'VWMA', key: 'VWMA', group: 'VOL' },
            { name: '资金流量指数', en: 'MFI', key: 'MFI', group: 'VOL' },
            { name: 'On Balance Volume', en: 'OBV', key: 'OBV', group: 'VOL' },
            { name: 'Accumulation/Distribution', en: 'AD', key: 'VolumeAccumulationPct', group: 'VOL' }
        ]
    },
    {
        name: '自定义指标 / Custom (1)',
        key: 'CUSTOM_CATEGORY',
        indicators: [
            { name: '年度价格剖面', en: 'YEARLY PROFILE', key: 'PROFILE', group: 'PROFILE' }
        ]
    }
];

// ==================== 右侧面板联动逻辑 ====================
/**
 * 初始化右侧面板按钮事件
 */
function initRightPanelEvents() {
    document.addEventListener('click', (event) => {
        const btn = event.target.closest('.indicator-btn');
        if (!btn) return;

        const indicatorName = btn.getAttribute('data-indicator');
        if (indicatorName) {
            toggleIndicatorVisibility(indicatorName);
        }
    });
}

/**
 * 更新右侧面板按钮视觉状态
 */
function updateRightPanelButton(name, isVisible) {
    const button = document.querySelector(`.indicator-btn[data-indicator="${name}"]`);
    if (!button) return;

    if (isVisible) {
        button.classList.add('active');
        button.textContent = `● ${name}`;
    } else {
        button.classList.remove('active');
        button.textContent = `○ ${name}`;
    }
}

// ==================== 核心指标显隐切换 ====================
function toggleIndicatorVisibility(name) {
    const info = seriesMap.get(name);
    if (!info || !info.series) {
        console.warn(`⚠️ Indicator "${name}" not found`);
        return false;
    }

    try {
        // 切换状态
        const newVisible = !info.visible;
        
        // 【v5.2.0 修复】使用 applyOptions 替代 setMarkers
        info.series.applyOptions({ visible: newVisible });
        info.visible = newVisible;

        // 同步右侧面板按钮
        updateRightPanelButton(name, newVisible);

        console.log(`🔘 Toggled "${name}" to ${newVisible}`);
        return true;
    } catch (error) {
        console.error(`❌ toggleIndicatorVisibility error (${name}):`, error);
        return false;
    }
}

// ==================== 图表初始化 ====================
function initCharts() {
    console.log('🚀 Initializing charts...');
    
    try {
        const mainContainer = document.getElementById('mainChart');
        const subContainer = document.getElementById('subChart');
        
        if (!mainContainer || !subContainer) {
            throw new Error('Chart containers not found');
        }

        // 创建主图
        mainChart = LightweightCharts.createChart(mainContainer, {
            width: mainContainer.clientWidth,
            height: mainContainer.clientHeight,
            layout: {
                background: { color: '#131722' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: '#2a2e39' },
                horzLines: { color: '#2a2e39' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: '#2a2e39',
            },
            timeScale: {
                borderColor: '#2a2e39',
                timeVisible: true,
            },
        });

        // 创建副图 - 初始为空状态
        subChart = LightweightCharts.createChart(subContainer, {
            width: subContainer.clientWidth,
            height: subContainer.clientHeight,
            layout: {
                background: { color: '#131722' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: 'transparent' },
                horzLines: { color: 'transparent' },
            },
            rightPriceScale: {
                visible: true,
                borderColor: '#2a2e39',
                scaleMargins: { // 可选的，提供更好的默认边距
                    top: 0.1,
                    bottom: 0.2,
                },
            },
            timeScale: {
                visible: true,
                borderColor: '#2a2e39',
                timeVisible: true,
            },
        });

        // 【修复】安全的DOM元素操作
        const elementsToHide = ['mainLoading', 'subLoading'];
        elementsToHide.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.style.display = 'none';
            } else {
                // 只警告，不抛出错误
                console.warn(`⚠️ ${id} element not found, continuing...`);
            }
        });

        // 隐藏加载提示 - 添加防御性检查
        const mainLoading = document.getElementById('mainLoading');
        const subLoading = document.getElementById('subLoading');
        
        if (mainLoading) {
            mainLoading.style.display = 'none';
        } else {
            console.warn('⚠️ mainLoading element not found');
        }
        
        if (subLoading) {
            subLoading.style.display = 'none';
        } else {
            console.warn('⚠️ subLoading element not found');
        }

        // 同步主副图时间轴
        setupChartSync();

        // 响应式调整大小
        setupResponsiveLayout();

        // 标记图表已初始化
        isChartInitialized = true;
        window.isChartInitialized = true;
        console.log('✅ Charts initialized successfully - 主图已初始化，副图保持空状态');

        // 1. 初始化 Chart Plus 菜单系统
        if (window.ChartPlus && window.ChartPlus.init) {
            const app = window.ChartPlus.init();
            console.log('✅ Chart Plus 菜单系统已初始化');
            
            // 等待一小段时间确保组件完全加载
            setTimeout(() => {
                // 2. 初始化指标面板
                if (typeof initIndicatorPanel === 'function') {
                    initIndicatorPanel();
                } else if (window.populateIndicatorPanel) {
                    window.populateIndicatorPanel();
                }
                
                // 确保指标面板显示
                if (app.getPanelManager()) {
                    app.getPanelManager().showPanel('indicatorPanel');
                }
            }, 300);
        }

        // 初始化后注册特殊指标
        setTimeout(() => {
            if (typeof registerSpecialIndicators === 'function') {
                registerSpecialIndicators();
            }
        }, 500);
        
        // 通知Python端图表已就绪
        notifyPythonChartReady();

        // 初始化完成后绑定右侧面板事件
        initRightPanelEvents();

        // 运行注册
        registerVolumeIndicator();
        registerStochasticIndicator();

    } catch (e) {
        console.error('❌ Error initializing charts:', e);
        showError('Failed to initialize charts: ' + e.message);
    }
}

// 手动注册Volume指标
function registerVolumeIndicator() {
    console.log('🔄 手动注册Volume指标');
    
    if (!window.LightweightChartsIndicators) {
        window.LightweightChartsIndicators = {};
    }
    
    // 注册基础Volume指标
    if (!window.LightweightChartsIndicators.Volume) {
        window.LightweightChartsIndicators.Volume = {
            calculate: function(data, options = {}) {
                console.log('🧮 计算Volume指标');
                
                if (!data || data.length === 0) {
                    return { data: [] };
                }
                
                const volumeData = data.map(item => ({
                    time: item.time,
                    value: item.volume || 0
                }));
                
                return {
                    metadata: { indicator: 'Volume' },
                    data: volumeData
                };
            },
            metadata: {
                indicator: 'Volume',
                description: '成交量指标'
            }
        };
        console.log('✅ Volume指标已注册');
    }
}

// 手动注册STOCH指标
function registerStochasticIndicator() {
    console.log('🔄 手动注册STOCH指标');
    
    if (!window.LightweightChartsIndicators) {
        window.LightweightChartsIndicators = {};
    }
    
    if (!window.LightweightChartsIndicators.STOCH) {
        window.LightweightChartsIndicators.STOCH = {
            calculate: function(data, options = {}) {
                console.log('🧮 计算STOCH指标');
                
                const kPeriod = options.kPeriod || 14;
                const dPeriod = options.dPeriod || 3;
                const slowing = options.slowing || 3;
                
                if (!data || data.length < kPeriod) {
                    return { data: [] };
                }
                
                const result = [];
                
                for (let i = kPeriod - 1; i < data.length; i++) {
                    const currentData = data[i];
                    const lookbackData = data.slice(i - kPeriod + 1, i + 1);
                    
                    // 计算最高价和最低价
                    const highestHigh = Math.max(...lookbackData.map(d => d.high));
                    const lowestLow = Math.min(...lookbackData.map(d => d.low));
                    
                    // 计算%K
                    const currentClose = currentData.close;
                    const kValue = ((currentClose - lowestLow) / (highestHigh - lowestLow)) * 100;
                    
                    result.push({
                        time: currentData.time,
                        value: kValue
                    });
                }
                
                return {
                    metadata: { indicator: 'STOCH' },
                    data: result
                };
            },
            metadata: {
                indicator: 'STOCH',
                description: '随机指标'
            }
        };
        console.log('✅ STOCH指标已注册');
    }
}

// 设置图表同步
function setupChartSync() {
    mainChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (isSyncing) return;
        isSyncing = true;
        if (range && subChart) {
            subChart.timeScale().setVisibleLogicalRange(range);
        }
        isSyncing = false;
    });

    subChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (isSyncing) return;
        isSyncing = true;
        if (range && mainChart) {
            mainChart.timeScale().setVisibleLogicalRange(range);
        }
        isSyncing = false;
    });
}

// 设置响应式布局
function setupResponsiveLayout() {
    window.addEventListener('resize', () => {
        if (mainChart && subChart) {
            const mainContainer = document.getElementById('mainChart');
            const subContainer = document.getElementById('subChart');
            mainChart.resize(mainContainer.clientWidth, mainContainer.clientHeight);
            subChart.resize(subContainer.clientWidth, subContainer.clientHeight);
        }
    });
}

// 修复主图和副图时间轴同步
function fixTimeScaleSync() {
    if (!mainChart || !subChart) return;
    
    // 禁用自动同步
    isSyncing = true;
    
    // 获取主图的当前时间范围
    const mainRange = mainChart.timeScale().getVisibleLogicalRange();
    
    if (mainRange) {
        // 为副图设置相同的时间范围
        subChart.timeScale().setVisibleLogicalRange(mainRange);
        
        // 设置时间轴选项
        subChart.timeScale().applyOptions({
            visible: true,
            timeVisible: true,
            secondsVisible: false,
            borderColor: 'rgba(197, 203, 206, 0.3)',
        });
    }
    
    // 启用同步
    setTimeout(() => {
        isSyncing = false;
    }, 100);
}

// ==================== 副图状态管理 ====================
// 更新副图状态
function updateSubChartState(hasData) {
    console.log(`📊 更新副图状态: hasData=${hasData}`);
    
    if (!subChart) {
        console.warn('⚠️ subChart 未定义，跳过副图状态更新');
        return;
    }
    
    // 计算当前副图中是否有可见的指标系列
    const hasVisibleSubChartIndicator = Array.from(seriesMap.values()).some(info => 
        info.chart === 'sub' && info.visible === true
    );
    
    // 【关键修复】根据是否有可见指标，动态调整副图的视觉表现
    if (hasVisibleSubChartIndicator) {
        // 副图有指标需要显示
        console.log('✅ 副图有可见指标，确保坐标轴完全可见');
        
        // 确保价格轴和时间轴可见
        subChart.applyOptions({
            rightPriceScale: { visible: true },
            timeScale: { visible: true }
        });
        
        // 同步主副图时间范围
        if (mainChart) {
            const mainRange = mainChart.timeScale().getVisibleLogicalRange();
            if (mainRange) {
                // 使用requestAnimationFrame避免频繁同步冲突
                requestAnimationFrame(() => {
                    subChart.timeScale().setVisibleLogicalRange(mainRange);
                });
            }
        }
        
    } else {
        // 副图没有可见指标
        console.log('ℹ️ 副图无可见指标，可考虑最小化显示或保持就绪状态');
        // 注意：此处我们不隐藏坐标轴，保持图表“就绪”状态，以便新指标能立即显示。
        // 如果希望完全隐藏，可在此处设置 visible: false，但需要在添加指标时重新设为true。
    }
}

// ==================== 设置蜡烛图数据 ====================
function setChartData(dataJson) {
    if (!isChartInitialized) {
        console.error('❌ Charts not initialized!');
        window.pythonBridge.notify('error', { 
            type: 'chart_not_initialized',
            message: 'Charts are not initialized yet' 
        });
        return;
    }

    try {
        const { CandlestickSeries, LineSeries, HistogramSeries, AreaSeries } = LightweightCharts;
        let data = typeof dataJson === 'string' ? JSON.parse(dataJson) : dataJson;
        
        console.log(`📊 Received ${data.length} data points from Python`);
        console.log('📊 原始数据示例:', data[0]);
        
        if (!Array.isArray(data) || data.length === 0) {
            throw new Error('Invalid data format');
        }

        // 通知 Python 开始处理数据
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('data_loading', { 
                dataCount: data.length,
                timestamp: new Date().toISOString()
            });
        }

        // 【关键修复】确保数据保存到全局变量
        window.chartData = data.map(item => {
            // 处理时间字段
            let timeValue;
            if (item.time) {
                timeValue = item.time;
            } else if (item.date) {
                // 将日期字符串转换为Lightweight Charts期望的格式
                // 格式1: '2024-05-22' -> 转换为时间戳
                // 格式2: 或者保持为字符串，但需要确保格式正确
                timeValue = item.date;
            } else {
                // 如果没有时间字段，使用索引
                timeValue = data.indexOf(item).toString();
            }
            
            return {
                time: timeValue,
                open: parseFloat(item.open) || 0,
                high: parseFloat(item.high) || 0,
                low: parseFloat(item.low) || 0,
                close: parseFloat(item.close) || 0,
                volume: parseFloat(item.volume) || 0
            };
        });
        
        // 同时保存到局部变量，保持向后兼容
        chartData = window.chartData;
        
        console.log(`✅ 数据已设置到 window.chartData (${window.chartData.length} 条)`);
        console.log(`✅ 转换后数据: ${window.chartData.length} 条`);
        console.log('📊 转换后示例:', window.chartData[0]);
        
        // 检查数据格式
        if (window.chartData.length > 0) {
            const sample = window.chartData[0];
            console.log('📊 数据格式验证:', {
                time: sample.time,
                open: sample.open,
                high: sample.high,
                low: sample.low,
                close: sample.close,
                volume: sample.volume
            });
        }

        // 清除现有系列
        if (candleSeries) {
            mainChart.removeSeries(candleSeries);
        }

        // 创建蜡烛图系列
        candleSeries = mainChart.addSeries(CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderUpColor: '#26a69a',
            borderDownColor: '#ef5350',
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        candleSeries.setData(data);
        
        // 使用 fitContent() 自动调整显示范围
        mainChart.timeScale().fitContent();
        
        setTimeout(() => {
            if (subChart) {
                subChart.timeScale().fitContent();
            }
        }, 100);

        window.hasSetInitialRange = true;

        console.log('✅ Chart data set successfully');
        
        // 通知 Python 数据加载完成
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('data_loaded', { 
                dataCount: data.length,
                success: true,
                timestamp: new Date().toISOString()
            });
        }

    } catch (e) {
        console.error('❌ Error setting chart data:', e);
        showError('Failed to load chart data: ' + e.message);
        
        // 通知 Python 数据加载错误
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('data_load_error', { 
                error: e.message,
                timestamp: new Date().toISOString()
            });
        }
    }
}

// ==================== 统一指标添加接口 ====================
function addIndicator(indicatorName, options = {}) {
    console.log(`🔧 开始添加指标: ${indicatorName}`, options);
    
    const { CandlestickSeries, LineSeries, HistogramSeries, AreaSeries, BarSeries } = LightweightCharts;
    
    // ==================== 1. 特殊指标预处理 ====================
    // 检查是否为组合指标
    if (specialIndicators && specialIndicators[indicatorName] && specialIndicators[indicatorName].type === 'COMBO') {
        console.log(`🎯 处理组合指标: ${indicatorName}`);
        
        const config = specialIndicators[indicatorName];
        
        // 检查是否已存在
        if (comboIndicatorManager && comboIndicatorManager.combos && comboIndicatorManager.combos.has(indicatorName)) {
            console.log(`🔄 组合指标 ${indicatorName} 已存在，切换可见性`);
            return comboIndicatorManager.toggleCombo(indicatorName);
        }
        
        // 添加新的组合
        if (comboIndicatorManager && comboIndicatorManager.addCombo) {
            return comboIndicatorManager.addCombo(indicatorName, config.indicators, options);
        }
    }
    
    // 检查是否为其他特殊指标
    if (specialIndicators && specialIndicators[indicatorName]) {
        console.log(`🎯 处理特殊指标: ${indicatorName}`);
        
        const config = specialIndicators[indicatorName];
        
        // PROFILE指标特殊处理
        if (config.type === 'PROFILE') {
            console.log(`📊 PROFILE指标调用Python端计算`);
            
            if (window.pythonBridge && window.pythonBridge.notify) {
                window.pythonBridge.notify('add_yearly_profile', {
                    indicator: indicatorName,
                    options: options
                });
            }
            return;
        }
        
        // 如果特殊指标有自定义计算方法
        if (config.calculate && typeof config.calculate === 'function') {
            console.log(`🔧 使用特殊指标计算方法: ${indicatorName}`);
            try {
                const result = config.calculate(chartData, options);
                if (result) {
                    // 将计算结果注册到指标库，以便后续统一处理
                    if (!window.LightweightChartsIndicators) {
                        window.LightweightChartsIndicators = {};
                    }
                    
                    if (!window.LightweightChartsIndicators[indicatorName]) {
                        window.LightweightChartsIndicators[indicatorName] = {
                            calculate: config.calculate,
                            metadata: {
                                indicator: indicatorName,
                                description: config.name || config.description || indicatorName
                            }
                        };
                    }
                }
            } catch (error) {
                console.error(`❌ 特殊指标计算失败: ${indicatorName}`, error);
            }
        }
    }
    
    // ==================== 2. 数据检查 ====================
    if (!chartData || chartData.length === 0) {
        console.warn('⚠️ 没有可用的图表数据!');
        
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('indicator_error', { 
                indicator: indicatorName,
                error: 'No chart data available'
            });
        }
        return;
    }
    
    // ==================== 3. 检查指标在JS端是否可用 ====================
    if (!window.LightweightChartsIndicators || !window.LightweightChartsIndicators[indicatorName]) {
        console.warn(`⚠️ JS端指标 ${indicatorName} 不可用，尝试Python计算`);
        
        // 对于 PROFILE 指标的特殊处理
        if (indicatorName === 'PROFILE') {
            console.log('📊 PROFILE 指标需要Python端计算');
            // 可以在这里添加更明确的处理逻辑
        }

        // 通知Python端计算
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('fallback_to_python', {
                indicator: indicatorName,
                options: options
            });
        }
        return;
    }
    
    // ==================== 4. 主处理逻辑 ====================
    try {
        console.log(`🔧 计算指标: ${indicatorName}, visible=${options.visible !== false}`);
        console.log(`📐 参数:`, options);
        
        // 通知 Python 开始计算指标
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('indicator_calculating', { 
                indicator: indicatorName,
                options: options
            });
        }
        
        // 获取指标计算器
        const indicatorCalculator = window.LightweightChartsIndicators[indicatorName];
        if (!indicatorCalculator) {
            console.error(`❌ 指标 ${indicatorName} 未找到!`);
            
            if (window.pythonBridge && window.pythonBridge.notify) {
                window.pythonBridge.notify('indicator_error', { 
                    indicator: indicatorName,
                    error: 'Indicator not found'
                });
            }
            return;
        }
        
        // ==================== 5. 批量处理模式 ====================
        // 保存当前可见范围，防止图表位移
        if (!isBatchAdding && window.hasSetInitialRange) {
            pendingRangeRestore = {
                main: mainChart ? mainChart.timeScale().getVisibleLogicalRange() : null,
                sub: subChart ? subChart.timeScale().getVisibleLogicalRange() : null
            };
            
            isBatchAdding = true;
            console.log('📦 批量模式: 开始 - 已保存范围');
            
            if (batchAddTimeout) clearTimeout(batchAddTimeout);
            batchAddTimeout = setTimeout(() => {
                console.log('📦 批量模式: 结束 - 恢复范围');
                if (pendingRangeRestore) {
                    try {
                        isSyncing = true;
                        if (pendingRangeRestore.main && mainChart) {
                            mainChart.timeScale().setVisibleLogicalRange(pendingRangeRestore.main);
                        }
                        if (pendingRangeRestore.sub && subChart) {
                            subChart.timeScale().setVisibleLogicalRange(pendingRangeRestore.sub);
                        }
                        isSyncing = false;
                    } catch (e) {
                        console.warn('⚠️ 恢复范围失败:', e.message);
                    }
                }
                isBatchAdding = false;
                pendingRangeRestore = null;
                batchAddTimeout = null;
            }, 2000);
        }
        
        // ==================== 6. 计算指标 ====================
        console.log(`🔍 计算指标 ${indicatorName}:`);
        console.log('数据长度:', chartData.length);
        console.log('指标计算器:', indicatorCalculator);
        console.log('计算参数:', options);
        
        const result = indicatorCalculator.calculate(chartData, options);
        
        // 调试输出
        console.log(`📈 指标计算结果:`, result);
        console.log('结果类型:', typeof result);
        console.log('结果键名:', Object.keys(result || {}));
        
        if (!result) {
            console.warn(`⚠️ 指标 ${indicatorName} 返回 null 或 undefined`);
            
            if (window.pythonBridge && window.pythonBridge.notify) {
                window.pythonBridge.notify('indicator_error', { 
                    indicator: indicatorName,
                    error: 'Indicator calculation returned null'
                });
            }
            return;
        }
        
        // ==================== 7. 处理不同的结果格式 ====================
        let indicatorData = null;
        let resultType = 'line';  // 默认类型
        let resultColor = '#2196F3';
        let resultName = indicatorName;
        
        // 检查结果格式
        if (result.data && Array.isArray(result.data)) {
            // 格式1: 有 data 属性
            indicatorData = result.data;
            resultType = result.type || 'line';
            resultColor = result.color || getRandomColor();
            resultName = result.name || indicatorName;
            console.log(`📊 格式1: 从 data 获取 ${indicatorData.length} 条数据`);
        } 
        // 处理 plots 格式
        else if (result.plots) {
            console.log('📊 检测到 plots 格式的数据');
            const plotKeys = Object.keys(result.plots);
            console.log('plots键名:', plotKeys);
            
            // 查找可用的plot数据
            for (const plotKey of plotKeys) {
                const plot = result.plots[plotKey];
                if (Array.isArray(plot) && plot.length > 0) {
                    indicatorData = plot;
                    resultName = plotKey === 'main' ? indicatorName : `${indicatorName} (${plotKey})`;
                    console.log(`✅ 从 plots.${plotKey} 获取 ${indicatorData.length} 条数据`);
                    break;
                }
            }
            
            // 如果没有找到有效的plot，尝试第一个plot
            if (!indicatorData && plotKeys.length > 0) {
                const firstPlot = result.plots[plotKeys[0]];
                if (Array.isArray(firstPlot)) {
                    indicatorData = firstPlot;
                    console.log(`🔄 从 plots.${plotKeys[0]} 获取 ${indicatorData.length} 条数据`);
                }
            }
        } 
        else if (Array.isArray(result)) {
            // 格式3: 直接返回数组
            indicatorData = result;
            console.log(`📊 格式3: 直接返回数组 ${indicatorData.length} 条数据`);
        } else {
            console.error('❌ 无法识别的结果格式:', result);
            
            if (window.pythonBridge && window.pythonBridge.notify) {
                window.pythonBridge.notify('indicator_error', { 
                    indicator: indicatorName,
                    error: 'Unrecognized result format: ' + JSON.stringify(result)
                });
            }
            return;
        }
        
        if (!indicatorData || indicatorData.length === 0) {
            console.warn(`⚠️ 指标 ${indicatorName} 在格式解析后返回空数据`);
            console.log('原始结果结构:', Object.keys(result));
            
            if (result.plots) {
                Object.keys(result.plots).forEach(key => {
                    const plot = result.plots[key];
                    console.log(`plots.${key}:`, Array.isArray(plot) ? `${plot.length} 条` : typeof plot);
                });
            }
            
            if (window.pythonBridge && window.pythonBridge.notify) {
                window.pythonBridge.notify('indicator_error', { 
                    indicator: indicatorName,
                    error: 'No data in result after parsing'
                });
            }
            return;
        }
        
        // ==================== 8. 过滤无效数据 ====================
        const validData = indicatorData.filter(item => 
            item && 
            typeof item.value === 'number' && 
            !isNaN(item.value) &&
            item.time  // 确保有时间戳
        );
        
        console.log(`📈 指标数据: 原始 ${indicatorData.length} 条, 有效 ${validData.length} 条`);
        
        if (validData.length === 0) {
            console.warn(`⚠️ 指标 ${indicatorName} 没有有效数据（全是NaN或无效值）`);
            console.log('原始数据示例:', indicatorData.slice(0, 5));
            
            if (window.pythonBridge && window.pythonBridge.notify) {
                window.pythonBridge.notify('indicator_error', { 
                    indicator: indicatorName,
                    error: 'No valid (non-NaN) data in indicator result'
                });
            }
            return;
        }
        
        console.log('第一条有效数据:', validData[0]);
        
        // ==================== 9. 确定目标图表 ====================
        // 检查是否为副图指标
        const isSubChartIndicator = () => {
            const subChartIndicators = [
                'RSI', 'Stochastic', 'StochRSI', 'CCI', 'WilliamsPercentRange',
                'AwesomeOscillator', 'ChandeMO', 'DPO', 'RVI', 'TSI', 
                'UltimateOscillator', 'KDJ', 'WaveTrend', 'SchaffTrendCycle',
                'MACD', 'Momentum', 'ROC', 'BOP', 'BullBearPower', 'CoppockCurve', 
                'TRIX', 'SqueezeMomentum', 'ADX', 'Aroon', 'ZigZag', 'ATR', 
                'StandardDeviation', 'Choppiness', 'Volume', 'MFI', 'OBV', 
                'VolumeAccumulationPct', 'HistoricalVolatility', 'BetterVolume'
                ,'PROFILE'
            ];
            
            return subChartIndicators.includes(indicatorName) || options.subChart === true;
        };
        
        const shouldUseSubChart = isSubChartIndicator();
        console.log(`📊 指标 ${indicatorName} 使用: ${shouldUseSubChart ? '副图' : '主图'}`);
        
        // 【关键修复】检查副图是否存在
        let targetChart = shouldUseSubChart ? subChart : mainChart;
        
        if (shouldUseSubChart && !subChart) {
            console.log('📊 副图不存在，正在初始化副图...');
            
            // 初始化副图
            subChart = initSubChart();
            
            if (subChart) {
                // 设置副图垂直坐标轴缩放
                setupSubChartPriceScaleScaling();
                
                // 设置主图和副图同步
                setupChartSync();
                
                // 初始时隐藏副图
                updateSubChartState(false);
            }
        }
        
        if (!targetChart) {
            console.error('❌ 目标图表未找到');
            return;
        }
        
        // ==================== 10. 保存当前范围，防止位移 ====================
        const currentMainRange = mainChart ? mainChart.timeScale().getVisibleLogicalRange() : null;
        const currentSubRange = subChart ? subChart.timeScale().getVisibleLogicalRange() : null;
        
        // ==================== 11. 创建图表系列 ====================
        let series;
        
        // 特殊处理Volume指标
        if (indicatorName === 'Volume' || indicatorName === 'VolumeColored' || indicatorName === 'NetVolume') {
            console.log(`📊 创建成交量系列: ${indicatorName}`);
            
            if (indicatorName === 'VolumeColored') {
                // 彩色成交量
                const coloredData = validData.map(item => {
                    const isUp = item.color === '#4CAF50' || (item.value >= 0 && !item.color);
                    return {
                        time: item.time,
                        value: item.value,
                        color: isUp ? (options.upColor || '#4CAF50') : (options.downColor || '#F44336')
                    };
                });
                
                series = targetChart.addSeries(HistogramSeries, {
                    title: resultName + (options.length ? `(${options.length})` : ''),
                    priceFormat: { type: 'volume' },
                    priceScaleId: 'volume',
                });
                
                series.setData(coloredData);
            } else {
                // 基础成交量
                series = targetChart.addSeries(HistogramSeries, {
                    color: options.color || '#666666',
                    title: resultName + (options.length ? `(${options.length})` : ''),
                    priceFormat: { type: 'volume' },
                    priceScaleId: 'volume',
                });
                
                series.setData(validData);
            }
            
            // 设置成交量坐标轴
            if (targetChart.priceScale('volume')) {
                targetChart.priceScale('volume').applyOptions({
                    scaleMargins: {
                        top: 0.8,
                        bottom: 0,
                    },
                });
            }
        } 
        // 其他指标类型
        else if (resultType === 'line') {
            series = targetChart.addSeries(LineSeries, {
                color: resultColor,
                lineWidth: options.lineWidth || 2,
                title: resultName + (options.length ? `(${options.length})` : ''),
            });
        } else if (resultType === 'histogram') {
            series = targetChart.addSeries(HistogramSeries, {
                color: resultColor,
                title: resultName + (options.length ? `(${options.length})` : ''),
            });
        } else if (resultType === 'area') {
            series = targetChart.addSeries(AreaSeries, {
                lineColor: resultColor,
                topColor: resultColor + '66',
                bottomColor: resultColor + '00',
                lineWidth: options.lineWidth || 2,
                title: resultName + (options.length ? `(${options.length})` : ''),
            });
        } else if (resultType === 'bar') {
            series = targetChart.addSeries(BarSeries, {
                upColor: options.upColor || '#4CAF50',
                downColor: options.downColor || '#F44336',
                title: resultName + (options.length ? `(${options.length})` : ''),
            });
        } else {
            // 默认使用线图
            series = targetChart.addSeries(LineSeries, {
                color: getRandomColor(),
                lineWidth: 2,
                title: resultName + (options.length ? `(${options.length})` : ''),
            });
        }
        
        if (!series) {
            console.error(`❌ 创建指标系列失败: ${indicatorName}`);
            return;
        }
        
        // 如果不是成交量指标，设置数据
        if (!['Volume', 'VolumeColored', 'NetVolume'].includes(indicatorName)) {
            series.setData(validData);
        }
        
        // ==================== 12. 设置可见性 ====================
        const isVisible = options.visible !== false;
        series.applyOptions({ visible: isVisible });
        
        // ==================== 13. 保存到映射 ====================
        seriesMap.set(indicatorName, {
            series: series,
            chart: shouldUseSubChart ? 'sub' : 'main',
            visible: isVisible
        });
        
        // 同步右侧面板初始状态
        if (window.updateRightPanelButton) {
            window.updateRightPanelButton(indicatorName, isVisible);
        }
        
        console.log(`✅ 添加指标: ${indicatorName} (visible=${isVisible}, 图表: ${shouldUseSubChart ? '副图' : '主图'})`);

        // ==================== 14. 恢复图表范围，防止位移 ====================
        setTimeout(() => {
            // 【关键修复】恢复主图和副图的原始范围
            if (currentMainRange && mainChart) {
                try {
                    mainChart.timeScale().setVisibleLogicalRange(currentMainRange);
                } catch (e) {
                    console.warn('恢复主图范围失败:', e.message);
                }
            }
            
            if (currentSubRange && subChart) {
                try {
                    subChart.timeScale().setVisibleLogicalRange(currentSubRange);
                } catch (e) {
                    console.warn('恢复副图范围失败:', e.message);
                }
            }
            
            console.log('🔄 已恢复图表范围，避免位移');
        }, 50);
        
        // ==================== 15. 更新副图状态 ====================
        if (shouldUseSubChart) {
            // 【修复】在调用前检查
            if (typeof updateSubChartState === 'function') {
                updateSubChartState(true);
            }
        }
        
        // ==================== 16. 通知成功 ====================
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('indicator_added', { 
                indicator: indicatorName,
                seriesCount: seriesMap.size,
                dataPoints: validData.length,
                chartType: resultType,
                visible: isVisible,
                chart: shouldUseSubChart ? 'sub' : 'main'
            });
        }
        
    } catch (e) {
        console.error(`❌ 添加指标 ${indicatorName} 时出错:`, e);
        console.error('错误堆栈:', e.stack);
        
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('indicator_error', { 
                indicator: indicatorName,
                error: e.message,
                stack: e.stack
            });
        }
    }
}

// ==================== 添加主图指标 ====================
function addMainIndicator(name, dataJson, options = {}) {
    const { CandlestickSeries, LineSeries, HistogramSeries, AreaSeries } = LightweightCharts;
    if (!mainChart) {
        console.error('❌ Main chart not initialized!');
        window.pythonBridge.notify('indicator_error', { 
            indicator: name,
            error: 'Main chart not initialized'
        });
        return;
    }
    
    try {
        let data = typeof dataJson === 'string' ? JSON.parse(dataJson) : dataJson;
        
        console.log(`🔧 Adding main indicator: ${name}, visible=${options.visible !== false}`);
        console.log(`📊 Data points: ${data.length}`);
        
        // 通知 Python
        window.pythonBridge.notify('main_indicator_adding', { 
            indicator: name,
            dataPoints: data.length
        });
        
        // 【批量处理】
        if (!isBatchAdding && window.hasSetInitialRange) {
            pendingRangeRestore = {
                main: mainChart.timeScale().getVisibleLogicalRange(),
                sub: subChart.timeScale().getVisibleLogicalRange()
            };
            
            isBatchAdding = true;
            console.log('📦 Batch mode: STARTED - Range saved (addMainIndicator)');
            
            if (batchAddTimeout) clearTimeout(batchAddTimeout);
            batchAddTimeout = setTimeout(() => {
                console.log('📦 Batch mode: ENDING - Restoring range (addMainIndicator)');
                if (pendingRangeRestore) {
                    try {
                        isSyncing = true;
                        if (pendingRangeRestore.main) {
                            mainChart.timeScale().setVisibleLogicalRange(pendingRangeRestore.main);
                        }
                        if (pendingRangeRestore.sub) {
                            subChart.timeScale().setVisibleLogicalRange(pendingRangeRestore.sub);
                        }
                        isSyncing = false;
                    } catch (e) {
                        console.warn('⚠️ Failed to restore range:', e.message);
                    }
                }
                isBatchAdding = false;
                pendingRangeRestore = null;
                batchAddTimeout = null;
            }, 2000);
        }
        
        const seriesOptions = {
            color: options.color || getRandomColor(),
            lineWidth: options.lineWidth || 2,
            title: options.title || name,
        };
        
        const series = mainChart.addSeries(LineSeries, seriesOptions);
        series.setData(data);
        
        // 【v5.2.0 修复】统一使用 applyOptions
        const isVisible = options.visible !== false;
        series.applyOptions({ visible: isVisible });
        
        // 保存到映射
        seriesMap.set(name, {
            series: series,
            chart: 'main',
            visible: isVisible
        });
        
        // 【新增】同步右侧面板
        updateRightPanelButton(name, isVisible);
    
        console.log(`✅ Added main indicator: ${name} (visible=${isVisible})`);

        // 通知 Python
        window.pythonBridge.notify('main_indicator_added', { 
            indicator: name,
            dataPoints: data.length,
            success: true
        });
        
    } catch (e) {
        console.error(`❌ Error adding main indicator ${name}:`, e);
        console.error('Stack trace:', e.stack);
        
        // 通知 Python
        window.pythonBridge.notify('main_indicator_error', { 
            indicator: name,
            error: e.message
        });
    }
}

// ==================== 添加副图指标 ====================
function addSubIndicator(name, dataJson, options = {}) {
    const { CandlestickSeries, LineSeries, HistogramSeries, AreaSeries } = LightweightCharts;
    if (!subChart) {
        console.error('❌ Sub chart not initialized!');
        window.pythonBridge.notify('indicator_error', { 
            indicator: name,
            error: 'Sub chart not initialized'
        });
        return;
    }
    
    try {
        let data = typeof dataJson === 'string' ? JSON.parse(dataJson) : dataJson;
        
        console.log(`🔧 Adding sub indicator: ${name}, visible=${options.visible !== false}`);
        console.log(`📊 Data points: ${data.length}`);
        
        // 更新副图状态
        updateSubChartState(true);
        
        // 【批量处理】
        if (!isBatchAdding && window.hasSetInitialRange) {
            pendingRangeRestore = {
                main: mainChart.timeScale().getVisibleLogicalRange(),
                sub: subChart.timeScale().getVisibleLogicalRange()
            };
            
            isBatchAdding = true;
            console.log('📦 Batch mode: STARTED - Range saved (addSubIndicator)');
            
            if (batchAddTimeout) clearTimeout(batchAddTimeout);
            batchAddTimeout = setTimeout(() => {
                console.log('📦 Batch mode: ENDING - Restoring range (addSubIndicator)');
                if (pendingRangeRestore) {
                    try {
                        isSyncing = true;
                        if (pendingRangeRestore.main) {
                            mainChart.timeScale().setVisibleLogicalRange(pendingRangeRestore.main);
                        }
                        if (pendingRangeRestore.sub) {
                            subChart.timeScale().setVisibleLogicalRange(pendingRangeRestore.sub);
                        }
                        isSyncing = false;
                    } catch (e) {
                        console.warn('⚠️ Failed to restore range:', e.message);
                    }
                }
                isBatchAdding = false;
                pendingRangeRestore = null;
                batchAddTimeout = null;
            }, 2000);
        }
        
        const seriesOptions = {
            color: options.color || getRandomColor(),
            lineWidth: options.lineWidth || 2,
            title: options.title || name,
        };
        
        const series = subChart.addSeries(LineSeries, seriesOptions);
        series.setData(data);
        
        // 【v5.2.0 修复】统一使用 applyOptions
        const isVisible = options.visible !== false;
        series.applyOptions({ visible: isVisible });
        
        // 保存到映射
        seriesMap.set(name, {
            series: series,
            chart: 'sub',
            visible: isVisible
        });
        
        // 【新增】同步右侧面板
        updateRightPanelButton(name, isVisible);
    
        console.log(`✅ Added sub indicator: ${name} (visible=${isVisible})`);

        // 通知 Python
        window.pythonBridge.notify('sub_indicator_added', { 
            indicator: name,
            dataPoints: data.length,
            success: true
        });
        
    } catch (e) {
        console.error(`❌ Error adding sub indicator ${name}:`, e);
        console.error('Stack trace:', e.stack);
        
        // 通知 Python
        window.pythonBridge.notify('sub_indicator_error', { 
            indicator: name,
            error: e.message
        });
    }
}

// ==================== 指标管理函数 ====================
function removeIndicator(indicatorName) {
    try {
        console.log(`🔧 Removing indicator: ${indicatorName}`);

        // 检查是否为组合指标
        if (comboIndicatorManager.combos.has(indicatorName)) {
            console.log(`🔧 检测到组合指标 ${indicatorName}，执行组合移除`);
            return comboIndicatorManager.removeCombo(indicatorName);
        }
    
        // 检查是否为组合的子指标
        const parentCombo = comboIndicatorManager.isComboIndicator(indicatorName);
        if (parentCombo) {
            console.log(`🔍 指标 ${indicatorName} 属于组合 ${parentCombo}`);
            // 如果是组合的子指标，移除整个组合
            return comboIndicatorManager.removeCombo(parentCombo);
        }
        
        // 1. 检查 seriesMap 中是否存在该指标
        if (!seriesMap.has(indicatorName)) {
            console.warn(`⚠️ Indicator "${indicatorName}" not found in seriesMap, skipping removal.`);
            return;
        }
        
        const seriesInfo = seriesMap.get(indicatorName);
        
        // 2. 检查 series 对象是否有效
        if (!seriesInfo || !seriesInfo.series) {
            console.warn(`⚠️ Series for "${indicatorName}" is undefined, skipping removal.`);
            seriesMap.delete(indicatorName);
            return;
        }
        
        const { series, chart } = seriesInfo;
        
        // 3. 确定图表实例
        const targetChart = chart === 'main' ? mainChart : subChart;
        if (!targetChart) {
            console.error(`❌ ${chart} chart not available to remove series from.`);
            return;
        }
        
        // 4. 执行删除
        targetChart.removeSeries(series);
        seriesMap.delete(indicatorName);

        if (isSubChart) {
            // 检查副图是否还有其他可见指标
            const hasOtherVisibleSubIndicators = Array.from(seriesMap.values()).some(
                info => info.chart === 'sub' && info.visible === true
            );
            
            if (typeof updateSubChartState === 'function') {
                updateSubChartState(hasOtherVisibleSubIndicators);
            }
        }
        
        console.log(`✅ Removed indicator: ${indicatorName}`);
        
        // 如果是副图指标被删除，检查副图是否还有系列
        if (chart === 'sub') {
            const subSeriesCount = subChart ? subChart.getSeries().length : 0;
            if (subSeriesCount === 0) {
                updateSubChartState(false);
            }
        }
        
        // 通知 Python
        window.pythonBridge.notify('indicator_removed', { 
            indicator: indicatorName
        });
        
    } catch (e) {
        console.error(`❌ Error removing indicator ${indicatorName}:`, e);
        
        // 通知 Python
        window.pythonBridge.notify('indicator_removal_error', { 
            indicator: indicatorName,
            error: e.message
        });
    }
}

function clearAllIndicators() {
    seriesMap.forEach((seriesInfo, name) => {
        try {
            if (seriesInfo && seriesInfo.series) {
                const targetChart = seriesInfo.chart === 'main' ? mainChart : subChart;
                if (targetChart) {
                    targetChart.removeSeries(seriesInfo.series);
                }
            }
        } catch (e) {
            console.error(`❌ Error removing indicator ${name}:`, e);
        }
    });
    seriesMap.clear();
    
    // 重置副图状态
    updateSubChartState(false);
    
    console.log('✅ Cleared all indicators');
    
    // 通知 Python
    window.pythonBridge.notify('indicators_cleared', { 
        count: seriesMap.size
    });
}

// 清除副图所有指标
function clearSubChartIndicators() {
    const seriesToRemove = [];
    
    // 收集所有副图系列
    seriesMap.forEach((seriesInfo, name) => {
        if (seriesInfo && seriesInfo.chart === 'sub') {
            seriesToRemove.push({ name, seriesInfo });
        }
    });
    
    // 从副图移除系列
    seriesToRemove.forEach(({ name, seriesInfo }) => {
        try {
            if (seriesInfo.series && subChart) {
                subChart.removeSeries(seriesInfo.series);
                seriesMap.delete(name);
            }
        } catch (e) {
            console.warn(`⚠️ Error removing sub indicator ${name}:`, e);
        }
    });
    
    // 更新副图状态
    updateSubChartState(false);
    
    console.log(`✅ Cleared ${seriesToRemove.length} sub chart indicators`);
    
    // 通知 Python
    window.pythonBridge.notify('sub_indicators_cleared', { 
        count: seriesToRemove.length
    });
}

// ==================== 工具函数 ====================
function getRandomColor() {
    const colors = ['#2196F3', '#FF9800', '#4CAF50', '#E91E63', '#9C27B0', '#00BCD4', '#FFEB3B'];
    return colors[Math.floor(Math.random() * colors.length)];
}

function showError(message) {
    const mainError = document.createElement('div');
    mainError.className = 'error';
    mainError.textContent = message;
    document.querySelector('.main-chart').appendChild(mainError);
    
    // 通知 Python 端错误
    window.pythonBridge.notify('chart_error', { error: message });
}

function getChartStatus() {
    return {
        isInitialized: isChartInitialized,
        chartDataLength: chartData.length,
        activeIndicators: Array.from(indicatorStates.entries())
            .filter(([_, isActive]) => isActive)
            .map(([key]) => key),
        seriesCount: seriesMap.size
    };
}

function getAvailableIndicators() {
    return indicatorCategories.map(category => ({
        name: category.name,
        key: category.key,
        indicators: category.indicators.map(ind => ({
            name: ind.name,
            en: ind.en,
            key: ind.key,
            group: ind.group
        }))
    }));
}

// ==================== 暴露给全局的 API ====================
window.indicatorCategories = indicatorCategories;
window.setChartData = setChartData;
window.addIndicator = addIndicator;
window.addMainIndicator = addMainIndicator;
window.addSubIndicator = addSubIndicator;
window.removeIndicator = removeIndicator;
window.clearAllIndicators = clearAllIndicators;
window.clearSubChartIndicators = clearSubChartIndicators;
window.getChartStatus = getChartStatus;
window.getAvailableIndicators = getAvailableIndicators;
window.updateSubChartState = updateSubChartState;

// ==================== Python 可调用的函数 ====================
window.setChartDataFromPython = function(data) {
    return setChartData(data);
};

window.addIndicatorFromPython = function(indicatorName, options) {
    console.log(`🐍 来自Python的添加指标调用: ${indicatorName}`);
    
    // 【关键修复】直接调用本地的 addIndicator 函数，而不是通过 window.addIndicator
    try {
        // 检查本地函数是否存在
        if (typeof addIndicator === 'function') {
            return addIndicator(indicatorName, options);
        } else {
            console.error('❌ 本地的 addIndicator 函数未找到');
            return false;
        }
    } catch (error) {
        console.error(`❌ 添加指标失败:`, error);
        return false;
    }
};

window.addMainIndicatorFromPython = function(name, data, options) {
    return addMainIndicator(name, data, options);
};

window.addSubIndicatorFromPython = function(name, data, options) {
    return addSubIndicator(name, data, options);
};

window.removeIndicatorFromPython = function(name) {
    return removeIndicator(name);
};

window.clearAllIndicatorsFromPython = function() {
    return clearAllIndicators();
};

window.clearSubChartIndicatorsFromPython = function() {
    return clearSubChartIndicators();
};

// 基础成交量计算函数
function calculateBasicVolume(data, options = {}) {
    console.log('🧮 计算基础成交量指标');
    
    if (!data || data.length === 0) {
        console.warn('⚠️ 没有可用的数据');
        return { data: [], metadata: { indicator: 'Volume' } };
    }
    
    const volumeData = [];
    data.forEach(item => {
        if (item.volume !== undefined && item.volume !== null) {
            volumeData.push({
                time: item.time,
                value: item.volume
            });
        }
    });
    
    console.log(`📈 成交量数据: ${volumeData.length} 条`);
    
    return {
        metadata: { 
            indicator: 'Volume',
            description: '基础成交量',
            type: 'volume'
        },
        data: volumeData
    };
}

// ==================== 特殊指标处理 ====================
// 特殊指标配置
const specialIndicators = {
    // Volume 成交量指标
    'Volume': { 
        type: 'BASIC_VOLUME',
        name: '成交量',
        description: '基础成交量指标',
        volumeField: 'volume',
        subChart: true,  // 明确指定在副图显示
        calculate: calculateBasicVolume
    },
    // SMA 系列别名
    'SMA_5': { type: 'SMA', length: 5 },
    'SMA_10': { type: 'SMA', length: 10 },
    'SMA_20': { type: 'SMA', length: 20 },
    
    // EMA 系列别名
    'EMA_12': { type: 'EMA', length: 12 },
    'EMA_26': { type: 'EMA', length: 26 },
    
    // 组合指标
    'SMAclassic': { 
        type: 'COMBO', 
        name: 'SMAclassic',  // 添加组合名称
        indicators: [
            { name: 'SMA_5', type: 'SMA', length: 5, color: '#FF6B6B' },
            { name: 'SMA_10', type: 'SMA', length: 10, color: '#4ECDC4' },
            { name: 'SMA_20', type: 'SMA', length: 20, color: '#45B7D1' },
            { name: 'SMA_60', type: 'SMA', length: 60, color: '#96CEB4' }
        ],
        // 添加组合特定的方法
        add: function(options) {
            return comboIndicatorManager.addCombo('SMAclassic', this.indicators, options);
        },
        remove: function() {
            return comboIndicatorManager.removeCombo('SMAclassic');
        },
        hide: function() {
            return comboIndicatorManager.hideCombo('SMAclassic');
        },
        show: function() {
            return comboIndicatorManager.showCombo('SMAclassic');
        },
        toggle: function() {
            return comboIndicatorManager.toggleCombo('SMAclassic');
        }
    },
    
    // MCGINLEY 动态指标
    'MCGINLEY': { 
        type: 'CUSTOM',
        calculate: calculateMcGinley
    },
    
    // STOCH 随机指标
    'STOCH': { 
        type: 'STOCH',
        kPeriod: 14,
        dPeriod: 3,
        smoothing: 3
    },
    
    // StochRSI 随机RSI
    'StochRSI': { 
        type: 'StochRSI',
        rsiLength: 14,
        stochLength: 14,
        kPeriod: 3,
        dPeriod: 3
    },
    
    // ZigZag 之字形指标
    'ZigZag': { 
        type: 'CUSTOM',
        calculate: calculateZigZag
    },
    
    // Volume 成交量
    'Volume': { 
        type: 'VOLUME',
        volumeField: 'Volume'
    },
    
    // PROFILE 成交量分布
    'PROFILE': { 
        type: 'PROFILE',
        pythonMethod: 'add_yearly_profile'
    }
};

// 注册特殊指标到 LightweightChartsIndicators
function registerSpecialIndicators() {
    console.log('🚀 注册特殊指标');
    
    if (!window.LightweightChartsIndicators) {
        window.LightweightChartsIndicators = {};
    }

    // 注册Volume指标
    const volumeIndicators = ['Volume'];
    
    volumeIndicators.forEach(indicatorName => {
        const config = specialIndicators[indicatorName];
        
        if (config && config.calculate) {
            window.LightweightChartsIndicators[indicatorName] = {
                calculate: config.calculate,
                metadata: {
                    indicator: indicatorName,
                    description: config.description || '成交量指标',
                    requiresVolumeData: true
                },
                inputConfig: [
                    { name: 'length', type: 'number', defaultValue: 20, min: 1, max: 200 },
                    { name: 'source', type: 'string', defaultValue: 'volume' }
                ],
                plotConfig: [
                    { name: 'main', type: 'histogram', color: config.defaultColor || '#666666' }
                ]
            };
            
            console.log(`✅ 注册成交量指标: ${indicatorName}`);
        }
    });
    
    Object.keys(specialIndicators).forEach(indicatorName => {
        const config = specialIndicators[indicatorName];
        
        switch (config.type) {
            case 'SMA':
            case 'EMA':
                // 简单别名指标
                window.LightweightChartsIndicators[indicatorName] = {
                    calculate: function(data, options = {}) {
                        const baseIndicator = window.LightweightChartsIndicators[config.type];
                        if (!baseIndicator) {
                            console.error(`❌ 基础指标 ${config.type} 未找到`);
                            return null;
                        }
                        console.log(`✅ 注册名: ${config.type}，参数: ${config.length}`);
                        
                        //SMA len
                        //EMA length
                        const mergedOptions = { ...options, len: config.length, length: config.length };
                        //console.log(`📈 全部数据:`, data);
                        //console.log(`📈 全部参数:`, mergedOptions);
                        return baseIndicator.calculate(data, mergedOptions);
                    },
                    metadata: {
                        indicator: indicatorName,
                        description: `${config.type}(${config.length}) 指标`
                    }
                };
                console.log(`✅ 注册别名指标: ${indicatorName}`);
                break;
                
            case 'COMBO':
                // 组合指标
                window.LightweightChartsIndicators[indicatorName] = {
                    calculate: function(data, options = {}) {
                        console.log(`🔧 计算组合指标: ${indicatorName}`);
                        
                        const results = {
                            metadata: { indicator: indicatorName },
                            plots: {},
                            data: []
                        };
                        
                        // 计算每个子指标
                        config.indicators.forEach(indicatorConfig => {
                            const baseIndicator = window.LightweightChartsIndicators[indicatorConfig.type];
                            if (baseIndicator) {
                                const indicatorResult = baseIndicator.calculate(data, { 
                                    length: indicatorConfig.length 
                                });
                                
                                if (indicatorResult && indicatorResult.data) {
                                    // 为每个子指标创建单独的 plot
                                    results.plots[indicatorConfig.name] = indicatorResult.data.map(item => ({
                                        time: item.time,
                                        value: item.value
                                    }));
                                    
                                    // 添加颜色信息
                                    if (indicatorConfig.color) {
                                        if (!results.metadata.colors) results.metadata.colors = {};
                                        results.metadata.colors[indicatorConfig.name] = indicatorConfig.color;
                                    }
                                }
                            }
                        });
                        
                        return results;
                    },
                    metadata: {
                        indicator: indicatorName,
                        description: '经典移动平均线组合'
                    }
                };
                console.log(`✅ 注册组合指标: ${indicatorName}`);
                break;
                
            case 'CUSTOM':
                // 自定义计算指标
                if (config.calculate) {
                    window.LightweightChartsIndicators[indicatorName] = {
                        calculate: config.calculate,
                        metadata: {
                            indicator: indicatorName,
                            description: '自定义指标'
                        }
                    };
                    console.log(`✅ 注册自定义指标: ${indicatorName}`);
                }
                break;
                
            case 'STOCH':
            case 'StochRSI':
            case 'VOLUME':
                // 这些指标应该已经在指标库中
                if (!window.LightweightChartsIndicators[indicatorName]) {
                    console.warn(`⚠️ ${indicatorName} 指标未在指标库中找到`);
                } else {
                    console.log(`✅ ${indicatorName} 已存在`);
                }
                break;
                
            case 'PROFILE':
                // 成交量分布指标，需要Python端处理
                window.LightweightChartsIndicators[indicatorName] = {
                    calculate: function(data, options = {}) {
                        console.log(`📊 PROFILE指标需要Python端计算`);
                        
                        // 返回占位结果，实际计算在Python端
                        return {
                            metadata: { indicator: 'PROFILE' },
                            plots: { profile: [] },
                            data: []
                        };
                    },
                    metadata: {
                        indicator: 'PROFILE',
                        description: '成交量分布图',
                        requiresPython: true
                    }
                };
                console.log(`✅ 注册PROFILE指标（Python端计算）`);
                break;
        }
    });
}

// MCGINLEY 动态指标计算函数
function calculateMcGinley(data, options = {}) {
    const length = options.length || 20;
    const mg = options.mg || 0.6;
    
    console.log(`🧮 计算MCGINLEY指标: length=${length}, mg=${mg}`);
    
    if (!data || data.length < length) {
        return { data: [], metadata: { indicator: 'MCGINLEY' } };
    }
    
    const result = [];
    
    // 计算McGinley动态指标
    for (let i = length - 1; i < data.length; i++) {
        const currentPrice = data[i].close;
        let mgValue = currentPrice;
        
        if (i > length - 1) {
            const prevMg = result[result.length - 1].value;
            const k = mg * Math.pow(currentPrice / prevMg, 4);
            mgValue = prevMg + (currentPrice - prevMg) / k;
        }
        
        result.push({
            time: data[i].time,
            value: mgValue
        });
    }
    
    return {
        metadata: { indicator: 'MCGINLEY' },
        data: result
    };
}

// ZigZag 指标计算函数
function calculateZigZag(data, options = {}) {
    const depth = options.depth || 12;
    const deviation = options.deviation || 5;
    const backstep = options.backstep || 3;
    
    console.log(`📈 计算ZigZag指标: depth=${depth}, deviation=${deviation}, backstep=${backstep}`);
    
    if (!data || data.length < depth) {
        return { data: [], metadata: { indicator: 'ZigZag' } };
    }
    
    const highs = data.map(d => d.high);
    const lows = data.map(d => d.low);
    const times = data.map(d => d.time);
    
    const result = [];
    
    // 简化的ZigZag算法
    let lastHighIdx = -1;
    let lastLowIdx = -1;
    let direction = 0; // 1: 上涨, -1: 下跌
    
    for (let i = depth; i < data.length; i++) {
        // 查找高点和低点
        let isHigh = true;
        let isLow = true;
        
        for (let j = 1; j <= depth; j++) {
            if (highs[i] <= highs[i - j]) isHigh = false;
            if (lows[i] >= lows[i - j]) isLow = false;
        }
        
        if (isHigh) {
            if (direction !== 1 || (lastHighIdx >= 0 && (highs[i] - highs[lastHighIdx]) / highs[lastHighIdx] * 100 >= deviation)) {
                result.push({
                    time: times[i],
                    value: highs[i],
                    type: 'high'
                });
                lastHighIdx = i;
                direction = 1;
            }
        } else if (isLow) {
            if (direction !== -1 || (lastLowIdx >= 0 && (lows[lastLowIdx] - lows[i]) / lows[lastLowIdx] * 100 >= deviation)) {
                result.push({
                    time: times[i],
                    value: lows[i],
                    type: 'low'
                });
                lastLowIdx = i;
                direction = -1;
            }
        }
    }
    
    return {
        metadata: { indicator: 'ZigZag' },
        data: result
    };
}

// ==================== 组合指标管理器 ====================
const comboIndicatorManager = {
    // 存储组合指标和其子指标
    combos: new Map(),
    
    // 添加组合指标
    addCombo: function(comboName, indicatorConfigs, options) {
        console.log(`🔧 添加组合指标: ${comboName}, 包含 ${indicatorConfigs.length} 个子指标`);
        
        const subIndicators = [];
        
        // 添加所有子指标
        indicatorConfigs.forEach((config, index) => {
            const indicatorKey = config.name || config.type;
            
            // 延迟添加每个子指标
            setTimeout(() => {
                const subResult = addIndicator(indicatorKey, {
                    ...options,
                    length: config.length,
                    color: config.color,
                    comboName: comboName,  // 标记属于哪个组合
                    comboIndex: index
                });
                
                if (subResult !== false) {
                    subIndicators.push(indicatorKey);
                }
            }, index * 50);  // 间隔50ms添加
        });
        
        // 保存组合信息
        this.combos.set(comboName, {
            subIndicators: subIndicators,
            visible: true,
            configs: indicatorConfigs
        });
        
        console.log(`✅ 组合指标 ${comboName} 添加完成`);
        return true;
    },
    
    // 移除组合指标
    removeCombo: function(comboName) {
        console.log(`🗑️ 移除组合指标: ${comboName}`);
        
        if (!this.combos.has(comboName)) {
            console.warn(`⚠️ 组合指标 ${comboName} 未找到`);
            return false;
        }
        
        const combo = this.combos.get(comboName);
        
        // 移除所有子指标
        combo.subIndicators.forEach(indicatorKey => {
            if (window.removeIndicator) {
                window.removeIndicator(indicatorKey);
            } else if (window.removeIndicatorFromPython) {
                window.removeIndicatorFromPython(indicatorKey);
            }
        });
        
        // 从管理器移除
        this.combos.delete(comboName);
        
        console.log(`✅ 组合指标 ${comboName} 移除完成`);
        return true;
    },
    
    // 隐藏组合指标
    hideCombo: function(comboName) {
        console.log(`🙈 隐藏组合指标: ${comboName}`);
        
        if (!this.combos.has(comboName)) {
            console.warn(`⚠️ 组合指标 ${comboName} 未找到`);
            return false;
        }
        
        const combo = this.combos.get(comboName);
        
        // 隐藏所有子指标
        combo.subIndicators.forEach(indicatorKey => {
            if (window.hideIndicatorFromPython) {
                window.hideIndicatorFromPython(indicatorKey);
            } else if (window.updateIndicatorVisibility) {
                window.updateIndicatorVisibility(indicatorKey, false);
            }
        });
        
        combo.visible = false;
        this.combos.set(comboName, combo);
        
        console.log(`✅ 组合指标 ${comboName} 隐藏完成`);
        return true;
    },
    
    // 显示组合指标
    showCombo: function(comboName) {
        console.log(`👁️ 显示组合指标: ${comboName}`);
        
        if (!this.combos.has(comboName)) {
            console.warn(`⚠️ 组合指标 ${comboName} 未找到`);
            return false;
        }
        
        const combo = this.combos.get(comboName);
        
        // 显示所有子指标
        combo.subIndicators.forEach(indicatorKey => {
            if (window.showIndicatorFromPython) {
                window.showIndicatorFromPython(indicatorKey, {});
            } else if (window.updateIndicatorVisibility) {
                window.updateIndicatorVisibility(indicatorKey, true);
            }
        });
        
        combo.visible = true;
        this.combos.set(comboName, combo);
        
        console.log(`✅ 组合指标 ${comboName} 显示完成`);
        return true;
    },
    
    // 切换组合指标可见性
    toggleCombo: function(comboName) {
        if (!this.combos.has(comboName)) {
            console.warn(`⚠️ 组合指标 ${comboName} 未找到`);
            return false;
        }
        
        const combo = this.combos.get(comboName);
        if (combo.visible) {
            return this.hideCombo(comboName);
        } else {
            return this.showCombo(comboName);
        }
    },
    
    // 检查指标是否属于某个组合
    isComboIndicator: function(indicatorKey) {
        for (const [comboName, combo] of this.combos) {
            if (combo.subIndicators.includes(indicatorKey)) {
                return comboName;
            }
        }
        return null;
    }
};

// 暴露组合指标管理函数到全局
window.showComboIndicator = function(comboName, options = {}) {
    console.log(`🌍 显示组合指标: ${comboName}`);
    
    if (comboIndicatorManager.combos.has(comboName)) {
        return comboIndicatorManager.toggleCombo(comboName);
    } else {
        // 如果不存在，检查是否为特殊组合指标
        if (specialIndicators[comboName] && specialIndicators[comboName].type === 'COMBO') {
            return comboIndicatorManager.addCombo(comboName, specialIndicators[comboName].indicators, options);
        }
    }
    return false;
};

window.hideComboIndicator = function(comboName) {
    console.log(`🌍 隐藏组合指标: ${comboName}`);
    
    if (comboIndicatorManager.combos.has(comboName)) {
        return comboIndicatorManager.hideCombo(comboName);
    }
    return false;
};

window.removeComboIndicator = function(comboName) {
    console.log(`🌍 移除组合指标: ${comboName}`);
    
    if (comboIndicatorManager.combos.has(comboName)) {
        return comboIndicatorManager.removeCombo(comboName);
    }
    return false;
};

// 初始化副图时添加垂直坐标轴
function initSubChart() {    
    // 创建副图
    const chart = LightweightCharts.createChart(subContainer, {
        width: subContainer.clientWidth,
        height: 200,
        layout: {
            backgroundColor: '#131722',
            textColor: '#d1d4dc',
        },
        grid: {
            vertLines: {
                color: 'rgba(42, 46, 57, 0.6)',
            },
            horzLines: {
                color: 'rgba(42, 46, 57, 0.6)',
            },
        },
        rightPriceScale: {
            scaleMargins: {
                top: 0.1,
                bottom: 0.1,
            },
            borderColor: 'rgba(197, 203, 206, 0.8)',
            visible: true,
            entireTextOnly: false,
        },
        timeScale: {
            borderColor: 'rgba(197, 203, 206, 0.8)',
            timeVisible: true,
            secondsVisible: false,
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        handleScroll: {
            mouseWheel: true,
            pressedMouseMove: true,
            horzTouchDrag: true,
            vertTouchDrag: true,
        },
        handleScale: {
            axisPressedMouseMove: true,
            mouseWheel: true,
            pinch: true,
        },
    });
    
    // 【修复】为副图添加独立的垂直坐标轴
    const rightPriceScale = chart.priceScale('right');
    if (rightPriceScale) {
        rightPriceScale.applyOptions({
            autoScale: true,
            scaleMargins: {
                top: 0.1,
                bottom: 0.1,
            },
            borderVisible: true,
            borderColor: 'rgba(197, 203, 206, 0.3)',
            textColor: '#787B86',
            fontSize: 12,
        });
    }
    
    // 【新增】为副图添加左侧价格坐标轴
    chart.priceScale('left').applyOptions({
        visible: false,  // 默认隐藏左侧坐标轴
    });
    
    return chart;
}

// 添加副图垂直坐标轴缩放功能
function setupSubChartPriceScaleScaling() {
    if (!subChart) return;
    
    const priceScale = subChart.priceScale('right');
    if (!priceScale) return;
    
    let isScaling = false;
    let startY = 0;
    let startTopMargin = 0.1;
    let startBottomMargin = 0.1;
    
    // 在副图容器上添加鼠标事件监听
    subContainer.style.cursor = 'ns-resize';  // 垂直缩放光标
    
    subContainer.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;  // 只处理左键
        
        const rect = subContainer.getBoundingClientRect();
        const relativeX = e.clientX - rect.left;
        
        // 只处理右侧价格区域（右边20像素范围）
        if (relativeX > rect.width - 20) {
            isScaling = true;
            startY = e.clientY;
            
            // 获取当前坐标轴边距
            const options = priceScale.options();
            startTopMargin = options.scaleMargins?.top || 0.1;
            startBottomMargin = options.scaleMargins?.bottom || 0.1;
            
            e.preventDefault();
            e.stopPropagation();
        }
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isScaling || !priceScale) return;
        
        const deltaY = e.clientY - startY;
        const containerHeight = subContainer.clientHeight;
        
        if (containerHeight > 0) {
            const deltaPercent = deltaY / containerHeight;
            
            // 计算新的边距
            const newTopMargin = Math.max(0, Math.min(0.9, startTopMargin + deltaPercent));
            const newBottomMargin = Math.max(0, Math.min(0.9, startBottomMargin - deltaPercent));
            
            // 应用新的坐标轴边距
            priceScale.applyOptions({
                scaleMargins: {
                    top: newTopMargin,
                    bottom: newBottomMargin,
                }
            });
        }
        
        e.preventDefault();
    });
    
    document.addEventListener('mouseup', (e) => {
        if (isScaling) {
            isScaling = false;
            e.preventDefault();
        }
    });
    
    console.log('✅ 副图垂直坐标轴缩放功能已启用');
}

// 监听PROFILE指标添加结果
if (window.pythonBridge && window.pythonBridge.on) {
    window.pythonBridge.on('profile_added', (data) => {
        console.log('📊 PROFILE指标添加结果:', data);
        
        if (data.success !== false) {
            // 更新指标状态
            window.indicatorStates.set('PROFILE', true);
            
            // 同步按钮状态
            const button = document.querySelector('[data-indicator="PROFILE"]');
            if (button) {
                button.classList.add('active');
                button.style.backgroundColor = '#2962FF';
                button.style.color = 'white';
                button.style.borderColor = '#2962FF';
            }
        }
    });
}

window.addProfileIndicator = function(dataJson, options = {}) {
    console.log('📊 添加 PROFILE 指标');
    
    try {
        const data = typeof dataJson === 'string' ? JSON.parse(dataJson) : dataJson;
        
        if (!data || data.length === 0) {
            console.warn('⚠️ PROFILE 数据为空');
            return;
        }
        
        // 确保副图存在
        if (!subChart) {
            console.error('❌ 副图未初始化，无法添加 PROFILE 指标');
            return;
        }
        
        // 创建柱状图系列
        const series = subChart.addSeries(HistogramSeries, {
            color: options.color || '#FF6B6B',
            title: options.title || 'PROFILE',
            priceFormat: { type: 'volume' },
            visible: options.visible !== false
        });
        
        // 设置数据
        series.setData(data);
        
        // 保存到映射
        const indicatorKey = 'PROFILE';
        seriesMap.set(indicatorKey, {
            series: series,
            chart: 'sub',
            visible: options.visible !== false
        });
        
        // 更新副图状态
        if (typeof updateSubChartState === 'function') {
            updateSubChartState(true);
        }
        
        console.log(`✅ PROFILE 指标添加成功 (${data.length} 个数据点)`);
        
    } catch (error) {
        console.error('❌ 添加 PROFILE 指标失败:', error);
    }
};