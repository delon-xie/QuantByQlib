// web/js/core/indicator_core.js
class IndicatorCore {
    constructor() {
        this.seriesMap = new Map();
        this.activeIndicators = new Set();
    }
    
    addIndicator(indicatorName, data, options = {}) {
        console.log(`🔧 添加指标: ${indicatorName}`, options);
        
        try {
            // 确定目标图表
            const targetChart = this._getTargetChart(indicatorName, options);
            
            if (!targetChart) {
                console.error('❌ 目标图表未找到');
                return false;
            }
            
            // 创建系列
            const series = this._createSeries(targetChart, indicatorName, options);
            
            if (!series) {
                console.error('❌ 创建系列失败');
                return false;
            }
            
            // 设置数据
            series.setData(data);
            
            // 设置可见性
            const isVisible = options.visible !== false;
            series.applyOptions({ visible: isVisible });
            
            // 保存到映射
            this.seriesMap.set(indicatorName, {
                series: series,
                chart: targetChart === subChart ? 'sub' : 'main',
                visible: isVisible
            });
            
            // 更新活跃指标
            this.activeIndicators.add(indicatorName);
            
            console.log(`✅ 指标添加成功: ${indicatorName}`);
            return true;
            
        } catch (error) {
            console.error(`❌ 添加指标失败: ${indicatorName}`, error);
            return false;
        }
    }
    
    removeIndicator(indicatorName) {
        console.log(`🗑️ 移除指标: ${indicatorName}`);
        
        const info = this.seriesMap.get(indicatorName);
        if (!info) {
            console.warn(`⚠️ 指标未找到: ${indicatorName}`);
            return false;
        }
        
        try {
            const targetChart = info.chart === 'sub' ? subChart : mainChart;
            if (targetChart && info.series) {
                targetChart.removeSeries(info.series);
            }
            
            this.seriesMap.delete(indicatorName);
            this.activeIndicators.delete(indicatorName);
            
            console.log(`✅ 指标移除成功: ${indicatorName}`);
            return true;
            
        } catch (error) {
            console.error(`❌ 移除指标失败: ${indicatorName}`, error);
            return false;
        }
    }
    
    clearAllIndicators() {
        console.log('🧹 清除所有指标');
        
        this.seriesMap.forEach((info, indicatorName) => {
            try {
                const targetChart = info.chart === 'sub' ? subChart : mainChart;
                if (targetChart && info.series) {
                    targetChart.removeSeries(info.series);
                }
            } catch (error) {
                console.warn(`⚠️ 清除指标时出错: ${indicatorName}`, error);
            }
        });
        
        this.seriesMap.clear();
        this.activeIndicators.clear();
        
        console.log('✅ 所有指标已清除');
    }
    
    _getTargetChart(indicatorName, options) {
        const isSubChart = this._isSubChartIndicator(indicatorName, options);
        return isSubChart ? subChart : mainChart;
    }
    
    _isSubChartIndicator(indicatorName, options) {
        const subChartIndicators = [
            'RSI', 'MACD', 'Stochastic', 'CCI', 'WilliamsPercentRange',
            'AwesomeOscillator', 'Momentum', 'ROC', 'BOP', 'ATR',
            'StandardDeviation', 'MFI', 'OBV', 'PROFILE'
        ];
        
        return subChartIndicators.includes(indicatorName) || options.subChart === true;
    }
    
    _createSeries(chart, indicatorName, options) {
        const seriesType = options.type || 'line';
        
        switch (seriesType.toLowerCase()) {
            case 'line':
                return chart.addSeries(LightweightCharts.LineSeries, {
                    color: options.color || '#2196F3',
                    lineWidth: options.lineWidth || 2,
                    title: indicatorName
                });
                
            case 'histogram':
                return chart.addSeries(LightweightCharts.HistogramSeries, {
                    color: options.color || '#666666',
                    priceFormat: options.priceFormat || { type: 'volume' },
                    title: indicatorName
                });
                
            case 'area':
                return chart.addSeries(LightweightCharts.AreaSeries, {
                    lineColor: options.color || '#2196F3',
                    topColor: (options.color || '#2196F3') + '66',
                    bottomColor: (options.color || '#2196F3') + '00',
                    lineWidth: options.lineWidth || 2,
                    title: indicatorName
                });
                
            default:
                return chart.addSeries(LightweightCharts.LineSeries, {
                    color: options.color || '#2196F3',
                    title: indicatorName
                });
        }
    }
}

// 导出到全局
window.IndicatorCore = new IndicatorCore();

// web/js/core/indicator_core.js - 扩展部分
class EnhancedIndicatorCore extends IndicatorCore {
    constructor() {
        super();
        this.indicatorRegistry = new Map();  // 指标注册表
        this.activeIndicatorsWithParams = new Map();  // 活跃指标及其参数
        
        // 注册默认指标
        this._registerDefaultIndicators();
    }
    
    _registerDefaultIndicators() {
        // 常用指标
        this.registerIndicator('SMA_20', this.createSMAHandler(20));
        this.registerIndicator('SMA_50', this.createSMAHandler(50));
        this.registerIndicator('EMA_12', this.createEMAHandler(12));
        this.registerIndicator('RSI', this.createRSIHandler(14));
        this.registerIndicator('MACD', this.createMACDHandler());
        this.registerIndicator('Volume', this.createVolumeHandler());
    }
    
    registerIndicator(name, calculator) {
        this.indicatorRegistry.set(name, calculator);
    }
    
    addIndicatorWithParams(indicatorName, parameters) {
        console.log(`🔧 添加指标(带参数): ${indicatorName}`, parameters);
        
        const calculator = this.indicatorRegistry.get(indicatorName);
        if (!calculator) {
            console.error(`❌ 指标未注册: ${indicatorName}`);
            return false;
        }
        
        try {
            // 使用参数计算指标
            const data = calculator(chartData, parameters);
            
            // 添加指标
            const result = this.addIndicator(indicatorName, data, {
                ...parameters,
                subChart: this._isSubChartIndicator(indicatorName, parameters)
            });
            
            if (result) {
                // 保存参数
                this.activeIndicatorsWithParams.set(indicatorName, parameters);
            }
            
            return result;
            
        } catch (error) {
            console.error(`❌ 计算指标失败: ${indicatorName}`, error);
            return false;
        }
    }
    
    updateIndicatorParams(indicatorName, newParams) {
        console.log(`🔄 更新指标参数: ${indicatorName}`, newParams);
        
        // 移除旧指标
        this.removeIndicator(indicatorName);
        
        // 用新参数重新添加
        return this.addIndicatorWithParams(indicatorName, newParams);
    }
    
    createSMAHandler(length) {
        return (data, params) => {
            const actualLength = params.length || length;
            return this.calculateSMA(data, actualLength, params.source);
        };
    }
    
    createEMAHandler(length) {
        return (data, params) => {
            const actualLength = params.length || length;
            return this.calculateEMA(data, actualLength, params.source);
        };
    }
    
    createRSIHandler(length) {
        return (data, params) => {
            const actualLength = params.length || length;
            return this.calculateRSI(data, actualLength);
        };
    }
    
    createMACDHandler() {
        return (data, params) => {
            const fast = params.fast_length || 12;
            const slow = params.slow_length || 26;
            const signal = params.signal_length || 9;
            return this.calculateMACD(data, fast, slow, signal);
        };
    }
    
    calculateSMA(data, length, source = 'close') {
        // SMA计算逻辑
        const result = [];
        for (let i = length - 1; i < data.length; i++) {
            let sum = 0;
            for (let j = 0; j < length; j++) {
                sum += data[i - j][source];
            }
            result.push({
                time: data[i].time,
                value: sum / length
            });
        }
        return result;
    }
    
    // ... 其他计算方法
}