/**
 * TradingView Plus Chart - 工具函数和事件处理模块
 * 包含Python桥接、事件监听、快捷键、工具函数等
 */
// 添加数据验证和调试函数
window.validateChartData = function() {
    console.log('🔍 验证图表数据状态');
    
    const status = {
        'window.chartData 存在': !!window.chartData,
        'window.chartData 长度': window.chartData?.length || 0,
        'chartData 变量存在': typeof chartData !== 'undefined',
        'chartData 变量长度': chartData?.length || 0,
        'window.candleSeries 存在': !!window.candleSeries,
        'candleSeries 有数据': !!(window.candleSeries && window.candleSeries.data),
        'setChartData 函数存在': typeof window.setChartData === 'function',
        'mainChart 存在': !!window.mainChart,
        'seriesMap 大小': window.seriesMap?.size || 0
    };
    
    console.table(status);
    
    if (window.chartData && window.chartData.length > 0) {
        console.log('📊 数据示例（前2条）:', window.chartData.slice(0, 2));
    } else if (chartData && chartData.length > 0) {
        console.log('📊 chartData变量有数据（前2条）:', chartData.slice(0, 2));
    }
    
    return status;
};
// 添加数据检查和调试工具
window.debugIndicatorCalculation = function(indicatorName = 'SMA') {
    console.log('🔍 调试指标计算过程');
    
    const debugInfo = {
        '1. window.chartData 存在': !!window.chartData,
        '2. 数据长度': window.chartData?.length || 0,
        '3. 数据示例': window.chartData?.slice(0, 2) || '无数据',
        '4. LightweightChartsIndicators 存在': !!window.LightweightChartsIndicators,
        '5. 指标函数存在': !!(window.LightweightChartsIndicators && 
                              window.LightweightChartsIndicators[indicatorName]),
        '6. 有calculate方法': !!(window.LightweightChartsIndicators && 
                               window.LightweightChartsIndicators[indicatorName] && 
                               typeof window.LightweightChartsIndicators[indicatorName].calculate === 'function'),
        '7. window.mainChart 存在': !!window.mainChart,
        '8. window.seriesMap 存在': !!window.seriesMap
    };
    
    console.table(debugInfo);
    
    // 如果数据存在，进行测试计算
    if (window.chartData && window.chartData.length > 0 && 
        window.LightweightChartsIndicators && 
        window.LightweightChartsIndicators[indicatorName]) {
        
        console.log('🧪 执行测试计算...');
        try {
            const testData = window.chartData.slice(0, 20);
            const result = window.LightweightChartsIndicators[indicatorName].calculate(testData, { length: 5 });
            console.log('📈 测试计算结果:', result);
            
            if (result && result.data) {
                console.log(`✅ 测试计算返回 ${result.data.length} 条数据`);
                if (result.data.length > 0) {
                    console.log('📊 第一条指标数据:', result.data[0]);
                }
            }
        } catch (error) {
            console.error('❌ 测试计算失败:', error);
        }
    }
    
    return debugInfo;
};
// 检查JS指标库可用性
window.checkIndicatorLibrary = function(indicatorsToCheck = []) {
    console.log('🔍 检查JS指标库可用性');
    
    if (!window.LightweightChartsIndicators) {
        console.error('❌ LightweightChartsIndicators 库未加载');
        return { available: false, count: 0 };
    }
    
    const allIndicators = indicatorsToCheck.length > 0 ? indicatorsToCheck : [
        // 您的常用指标列表
        'SMA', 'EMA', 'TEMA', 'WMA', 'RMA', 'DEMA', 'HMA',
        'LSMA', 'ALMA', 'VWMA', 'McGinleyDynamic', 'EMAMACross',
        'MARibbon', 'ZLSMA', 'RSI', 'Stochastic', 'StochRSI',
        'CCI', 'WilliamsPercentRange', 'AwesomeOscillator', 'ChandeMO',
        'DPO', 'RVI', 'TSI', 'UltimateOscillator', 'KDJ', 'WaveTrend',
        'SchaffTrendCycle', 'MACD', 'Momentum', 'ROC', 'BOP',
        'BullBearPower', 'CoppockCurve', 'TRIX', 'SqueezeMomentum',
        'ADX', 'IchimokuCloud', 'ParabolicSAR', 'VolumeSuperTrendAi',
        'Aroon', 'ZigZag', 'WilliamsAlligator', 'DonchianChannels',
        'ATR', 'BollingerBands', 'StandardDeviation', 'HistoricalVolatility',
        'Choppiness', 'BetterVolume', 'MFI', 'OBV', 'VolumeAccumulationPct'
        ,'PROFILE'
    ];
    
    const results = {
        available: [],
        unavailable: []
    };
    
    allIndicators.forEach(indicator => {
        if (window.LightweightChartsIndicators[indicator]) {
            results.available.push(indicator);
        } else {
            results.unavailable.push(indicator);
        }
    });
    
    console.log(`✅ 可用的指标 (${results.available.length}个)`);
    console.log(`❌ 不可用的指标 (${results.unavailable.length}个):`, results.unavailable);
    
    return results;
};

// 添加JS指标库检查
window.checkJSLibrary = function() {
    console.log('🔍 检查JS指标库可用性');
    
    if (!window.LightweightChartsIndicators) {
        console.error('❌ LightweightChartsIndicators 库未加载');
        return false;
    }
    
    const allIndicators = [
        'SMA', 'EMA', 'TEMA', 'WMA', 'RMA', 'DEMA', 'HMA', 'LSMA', 'ALMA', 'VWMA',
        'RSI', 'Stochastic', 'StochasticRSI', 'CCI', 'WilliamsR', 'WilliamsPercentR',
        'AO', 'AwesomeOscillator', 'CMO', 'DPO', 'RVI', 'TSI', 
        'UltimateOscillator', 'KDJ', 'WaveTrend', 'SchaffTrendCycle', 'STC',
        'MACD', 'Momentum', 'ROC', 'BOP', 'BullBearPower', 'CoppockCurve',
        'TRIX', 'SqueezeMomentum', 'ADX', 'IchimokuCloud', 'ParabolicSAR',
        'SuperTrend', 'Aroon', 'ZigZag', 'WilliamsAlligator', 'DonchianChannels',
        'ATR', 'BollingerBands', 'StandardDeviation', 'HistoricalVolatility',
        'ChoppinessIndex', 'BetterVolume', 'MFI', 'OBV', 'AccumulationDistribution'
        ,'PROFILE'
    ];
    
    const available = [];
    const unavailable = [];
    
    allIndicators.forEach(indicator => {
        if (window.LightweightChartsIndicators[indicator]) {
            available.push(indicator);
        } else {
            unavailable.push(indicator);
        }
    });
    
    console.log(`✅ 可用的指标 (${available.length}个):`, available);
    console.log(`❌ 不可用的指标 (${unavailable.length}个):`, unavailable);
    
    return available.length > 0;
};

// ==================== Python 桥接相关 ====================
// 全局变量，用于与 Python 交互
window.pythonBridge = {
    // 存储回调函数
    callbacks: new Map(),
    
    // 调用 Python 函数
    // 移除call方法，只保留notify，移除不必要的双向调用
    /* call: function(method, data) {
        console.log(`🔄 Calling Python: ${method}`, data);
        
        // 生成唯一 ID
        const callbackId = Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        
        return new Promise((resolve, reject) => {
            // 存储回调
            this.callbacks.set(callbackId, { resolve, reject });
            
            // 向 Python 发送消息
            if (window.pywebview) {
                window.pywebview.api[method]({...data, callbackId});
            } else if (window.eel) {
                window.eel[method]({...data, callbackId})(function(response) {
                    resolve(response);
                });
            } else if (window.pybridge) {
                window.pybridge[method](JSON.stringify({...data, callbackId}));
            } else {
                console.warn('⚠️ No Python bridge found');
                reject(new Error('No Python bridge available'));
            }
        });
    }, */
    
    // Python 调用此函数来返回结果
    onPythonResult: function(callbackId, result, error) {
        if (this.callbacks.has(callbackId)) {
            const { resolve, reject } = this.callbacks.get(callbackId);
            this.callbacks.delete(callbackId);
            
            if (error) {
                reject(new Error(error));
            } else {
                resolve(result);
            }
        }
    },
    
    // 通知 Python 端事件
    notify: function(event, data) {
        if (window.pywebview) {
            window.pywebview.api.onEvent(event, data);
        } else if (window.eel) {
            window.eel.on_event(event, JSON.stringify(data));
        } else if (window.pybridge) {
            window.pybridge.onEvent(event, JSON.stringify(data));
        } else {
            console.log(`📡 Event: ${event}`, data);
        }
    }
};

// 暴露给全局的接口
window.pyBridge = window.pythonBridge;

// ==================== Python 通知函数 ====================
function notifyPythonChartReady() {
    try {
        // 方法1: 如果存在 pybridge
        if (window.pybridge && typeof window.pybridge.chartReady === 'function') {
            window.pybridge.chartReady();
            console.log('📡 Notified Python via pybridge.chartReady()');
        }
        // 方法2: 如果存在 pywebview
        else if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.on_chart_ready && window.pywebview.api.on_chart_ready();
            console.log('📡 Notified Python via pywebview.api.on_chart_ready()');
        }
        // 方法3: 如果存在 eel
        else if (window.eel) {
            window.eel.on_chart_ready();
            console.log('📡 Notified Python via eel.on_chart_ready()');
        }
        // 方法4: 通过 window.pythonBridge
        else if (window.pythonBridge) {
            window.pythonBridge.notify('chart_ready', { 
                message: 'Charts initialized successfully',
                timestamp: new Date().toISOString()
            });
        }
        // 方法5: 触发自定义事件
        else {
            const event = new CustomEvent('chart_ready', {
                detail: { 
                    isInitialized: isChartInitialized,
                    timestamp: new Date().toISOString()
                }
            });
            window.dispatchEvent(event);
            console.log('📡 Dispatched chart_ready event');
        }
    } catch (error) {
        console.warn('⚠️ Could not notify Python, continuing:', error);
    }
}

// ==================== 事件处理 ====================
function setupEventListeners() {
    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
        // Ctrl+I 切换指标面板
        if (e.ctrlKey && e.key === 'i') {
            togglePanel();
            e.preventDefault();
        }
        
        // Ctrl+R 重新加载图表
        if (e.ctrlKey && e.key === 'r') {
            window.pythonBridge.notify('reload_requested', { 
                timestamp: new Date().toISOString()
            });
        }
        
        // Ctrl+C 清除所有指标
        if (e.ctrlKey && e.key === 'c') {
            window.clearAllIndicators();
            e.preventDefault();
        }
        
        // Ctrl+Shift+I 显示指标信息
        if (e.ctrlKey && e.shiftKey && e.key === 'I') {
            const status = window.getChartStatus();
            window.pythonBridge.notify('chart_info_requested', {
                status: status,
                activeIndicators: Array.from(indicatorStates.entries())
                    .filter(([_, isActive]) => isActive)
                    .map(([key]) => key)
            });
        }
        
        // Ctrl+D 下载图表截图
        if (e.ctrlKey && e.key === 'd') {
            downloadChartScreenshot();
            e.preventDefault();
        }
    });
    
    // 窗口事件处理
    window.addEventListener('beforeunload', () => {
        window.pythonBridge.notify('window_closing', { 
            timestamp: new Date().toISOString(),
            activeIndicatorsCount: seriesMap.size
        });
    });
    
    // 窗口焦点事件
    window.addEventListener('focus', () => {
        window.pythonBridge.notify('window_focused', { 
            timestamp: new Date().toISOString()
        });
    });
    
    window.addEventListener('blur', () => {
        window.pythonBridge.notify('window_blurred', { 
            timestamp: new Date().toISOString()
        });
    });
}

// ==================== 工具函数 ====================
function downloadChartScreenshot() {
    try {
        if (!mainChart) {
            console.warn('图表未初始化');
            return;
        }
        
        // 创建临时的Canvas用于截图
        const canvas = document.createElement('canvas');
        const mainContainer = document.getElementById('mainChart');
        const subContainer = document.getElementById('subChart');
        
        // 设置Canvas尺寸
        canvas.width = mainContainer.clientWidth;
        canvas.height = mainContainer.clientHeight + (subContainer ? subContainer.clientHeight : 0);
        const ctx = canvas.getContext('2d');
        
        // 填充背景色
        ctx.fillStyle = '#131722';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // 获取图表Canvas
        const chartCanvas = mainContainer.querySelector('canvas');
        if (chartCanvas) {
            ctx.drawImage(chartCanvas, 0, 0);
        }
        
        if (subContainer) {
            const subCanvas = subContainer.querySelector('canvas');
            if (subCanvas) {
                ctx.drawImage(subCanvas, 0, mainContainer.clientHeight);
            }
        }
        
        // 创建下载链接
        const link = document.createElement('a');
        link.download = `chart_${Date.now()}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
        
        window.pythonBridge.notify('screenshot_downloaded', { 
            filename: link.download,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('截图下载失败:', error);
        window.pythonBridge.notify('screenshot_error', { 
            error: error.message,
            timestamp: new Date().toISOString()
        });
    }
}

function getActiveIndicators() {
    return Array.from(indicatorStates.entries())
        .filter(([_, isActive]) => isActive)
        .map(([key]) => key);
}

function getChartInfo() {
    return {
        timestamp: new Date().toISOString(),
        chartInitialized: isChartInitialized,
        dataPoints: chartData.length,
        mainChart: {
            hasData: !!candleSeries,
            indicatorsCount: Array.from(seriesMap.entries()).filter(([_, series]) => 
                mainChart && mainChart.getSeries().includes(series)
            ).length
        },
        subChart: {
            indicatorsCount: Array.from(seriesMap.entries()).filter(([_, series]) => 
                subChart && subChart.getSeries().includes(series)
            ).length
        },
        activeIndicators: getActiveIndicators(),
        indicatorStates: Object.fromEntries(indicatorStates)
    };
}

// ==================== 导出给Python的函数 ====================
// 这些函数可以直接从Python调用
window.getChartInfo = getChartInfo;
window.downloadChartScreenshot = downloadChartScreenshot;
window.notifyPythonChartReady = notifyPythonChartReady;

// ==================== 初始化函数 ====================
// 在 chart_plus_template_tool.js 的 initializeAll 函数中
function initializeAll() {
    console.log('📄 DOM loaded, initializing charts and UI...');
    
    // 1. 首先初始化图表
    if (typeof initCharts === 'function') {
        console.log('🔧 调用 initCharts...');
        initCharts();
    }
    
    // 2. 等待图表初始化完成后再初始化指标面板
    const waitForCharts = () => {
        if (window.isChartInitialized) {
            console.log('✅ 图表已初始化，开始初始化指标面板');
            
            // 使用延迟确保所有脚本已加载
            setTimeout(() => {
                // 方法1: 通过 ChartPlus 系统
                if (window.ChartPlus && window.ChartPlus.init) {
                    const app = window.ChartPlus.init();
                    console.log('📊 Chart Plus 应用程序已初始化');
                    
                    // 初始化指标面板
                    if (window.initIndicatorPanel) {
                        window.initIndicatorPanel();
                    }
                }
                // 方法2: 直接调用
                else if (window.initIndicatorPanel) {
                    window.initIndicatorPanel();
                }
            }, 500);
        } else {
            console.log('⏳ 等待图表初始化...');
            setTimeout(waitForCharts, 100);
        }
    };
    
    // 开始等待图表初始化
    waitForCharts();
    
    // 3. 设置事件监听器
    setupEventListeners();
    
    // 4. 向 Python 发送初始化完成消息
    window.pythonBridge.notify('dom_loaded', { 
        timestamp: new Date().toISOString(),
        chartVersion: '5.2.0',
        templateVersion: 'chart_plus_template_split_v1',
        features: ['charts', 'indicators', 'python_bridge', 'keyboard_shortcuts']
    });
    
    console.log('✅ All modules initialized successfully');
}

// ==================== 页面初始化 ====================
window.addEventListener('DOMContentLoaded', initializeAll);

// 导出初始化函数
window.initializeChartApp = initializeAll;