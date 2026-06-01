// web/js/core/chart_core.js
let mainChart = null;
let subChart = null;
let candleSeries = null;
let isChartInitialized = false;

class ChartCore {
    static init() {
        console.log('🚀 初始化图表核心...');
        
        try {
            const mainContainer = document.getElementById('mainChart');
            const subContainer = document.getElementById('subChart');
            
            if (!mainContainer || !subContainer) {
                throw new Error('图表容器未找到');
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
            
            // 创建副图
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
                },
                timeScale: {
                    visible: true,
                    borderColor: '#2a2e39',
                },
            });
            
            // 设置同步
            this.setupChartSync();
            
            // 设置响应式
            this.setupResponsiveLayout();
            
            isChartInitialized = true;
            window.isChartInitialized = true;
            
            console.log('✅ 图表核心初始化完成');
            
        } catch (error) {
            console.error('❌ 图表核心初始化失败:', error);
        }
    }
    
    static setupChartSync() {
        let isSyncing = false;
        
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
    
    static setupResponsiveLayout() {
        window.addEventListener('resize', () => {
            if (mainChart && subChart) {
                const mainContainer = document.getElementById('mainChart');
                const subContainer = document.getElementById('subChart');
                mainChart.resize(mainContainer.clientWidth, mainContainer.clientHeight);
                subChart.resize(subContainer.clientWidth, subContainer.clientHeight);
            }
        });
    }
    
    static getMainChart() {
        return mainChart;
    }
    
    static getSubChart() {
        return subChart;
    }
    
    static getCandleSeries() {
        return candleSeries;
    }
    
    static isInitialized() {
        return isChartInitialized;
    }
}

// 导出到全局
window.ChartCore = ChartCore;