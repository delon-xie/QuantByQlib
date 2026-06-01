#!/usr/bin/env python3
"""
TradingView Plus Widget 测试脚本
集成 446 个技术指标（JS 端计算）
"""

import sys
import pandas as pd
import yfinance as yf
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QMenuBar
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from ui.components.tradingview_plus_widget import TradingViewPlusWidget


class ChartPlusTestWindow(QMainWindow):
    """测试窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TradingView Plus Widget Test - 446 Indicators")
        self.setGeometry(100, 100, 1600, 900)
        
        # 创建菜单栏
        self.create_menu()
        
        # 创建主部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 实例化 TradingView Plus Widget
        self.tv_widget = TradingViewPlusWidget(self)
        layout.addWidget(self.tv_widget)
        
        # 添加开发者工具按钮
        dev_btn = QPushButton("Open Dev Tools")
        dev_btn.clicked.connect(self.open_dev_tools)
        layout.addWidget(dev_btn)
        
        # 加载数据
        self.load_stock_data()
        
        # 延迟打开开发者工具，确保页面已加载
        # QTimer.singleShot(2000, self.open_dev_tools)

    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 视图菜单
        view_menu = menubar.addMenu('View')
        
        # 开发者工具动作
        dev_tools_action = QAction('Open Developer Tools', self)
        dev_tools_action.setShortcut('Ctrl+Shift+I')
        dev_tools_action.triggered.connect(self.open_dev_tools)
        view_menu.addAction(dev_tools_action)
        
        # F12 快捷键
        f12_action = QAction('Dev Tools (F12)', self)
        f12_action.setShortcut('F12')
        f12_action.triggered.connect(self.open_dev_tools)
        view_menu.addAction(f12_action)

    def open_dev_tools(self):
        """打开开发者工具"""
        self.tv_widget.open_dev_tools_window()

    def load_stock_data(self):
        """加载股票数据"""
        symbol = "0700.HK"
        print(f"\n{'='*60}")
        print(f"🚀 正在下载 {symbol} 数据...")
        print(f"{'='*60}")
        
        # 下载数据
        df = yf.download(symbol, period="2y", progress=False)
        
        if df.empty:
            print(" 未获取到数据")
            return

        # 标准化列名处理
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = ['_'.join([str(x).lower() for x in c]) for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
        
        # 映射标准列名
        col_mapping = {}
        standard_cols = ['open', 'high', 'low', 'close', 'volume', 'adj close']
        for col in df.columns:
            for std_col in standard_cols:
                if std_col in col:
                    target_name = std_col.replace(' ', '_')
                    col_mapping[col] = target_name
                    break
        
        df.rename(columns=col_mapping, inplace=True)
        
        # 处理索引
        df.reset_index(inplace=True)
        
        # 【修复】检查并统一日期列名
        date_col = None
        for col in df.columns:
            if col.lower() in ['date', 'datetime', 'index']:
                date_col = col
                break
        
        if date_col and date_col != 'date':
            df.rename(columns={date_col: 'date'}, inplace=True)
        
        if 'date' not in df.columns:
            print(f"⚠️ 警告：未找到日期列，当前列名: {list(df.columns)}")
            return
            
        print(f"✅ 数据下载完成")
        print(f" 数据量: {len(df)} 条")
        print(f" 列名: {list(df.columns)}")
        print(f" 时间范围: {df['date'].min()} ~ {df['date'].max()}")
        
        # 更新图表 - 这会触发数据加载
        self.tv_widget.update_chart_data(df)
        
        # 延迟添加指标，确保蜡烛图先加载（增加延迟时间）
        # QTimer.singleShot(2500, lambda: self.add_test_indicators(df))

    def debug_zigzag_data(self, original_df):
        """调试 ZigZag 数据生成"""
        print(f"\n{'='*60}")
        print(f"🔍 DEBUG: Testing ZigZag data generation")
        print(f"{'='*60}")
        
        from ui.components.tradingview_plus_widget import TradingViewPlusWidget
        
        # 创建一个临时实例来测试
        temp_widget = TradingViewPlusWidget()
        
        # 测试不同的阈值
        for threshold in [2.0, 3.0, 5.0]:
            print(f"\n--- Testing with {threshold}% threshold ---")
            temp_widget.add_zigzag_python(original_df, percent_change=threshold, visible=False)
        
        print(f"\n{'='*60}\n")
        
    def add_test_indicators(self, original_df):
        """测试各类指标"""
        print(f"\n{'='*60}")
        print(f" 开始加载技术指标...")
        print(f"{'='*60}")
        
        # 检查图表是否就绪
        if not self.tv_widget.is_chart_ready:
            print("⚠️ 图表尚未就绪，延迟加载指标...")
            QTimer.singleShot(1000, lambda: self.add_test_indicators(original_df))
            return
        
        # ===== 移动平均线组 =====
        print(f"\n📈 【移动平均线】")
        self.tv_widget.add_sma(original_df, length=5, color="#FFFFFF", visible=False)
        print(f"  ✅ SMA(5) - 简单移动平均")
        
        self.tv_widget.add_sma(original_df, length=10, color="#FFFF00", visible=False)
        print(f"  ✅ SMA(10)")
        
        self.tv_widget.add_sma(original_df, length=20, color="#FF00FF", visible=False)
        print(f"  ✅ SMA(20)")
        
        self.tv_widget.add_sma_20(original_df, length=20, color="#FF00FF", visible=False)
        print(f"  ✅ SMA_20(20)")
        
        self.tv_widget.add_sma_10(original_df, length=10, color="#FF00FF", visible=False)
        print(f"  ✅ SMA_10(10)")
        
        self.tv_widget.add_sma_5(original_df, length=5, color="#FF00FF", visible=False)
        print(f"  ✅ SMA_5(5)")
        
        self.tv_widget.add_ema_12(original_df, length=12, color="#E040FB", visible=False)
        print(f"  ✅ EMA(12) - 指数移动平均")
        
        self.tv_widget.add_ema_26(original_df, length=26, color="#2962FF", visible=False)
        print(f"  ✅ EMA(26)")
        
        self.tv_widget.add_ema(original_df, length=12, color="#E040FB", visible=False)
        print(f"  ✅ EMA(12) - 指数移动平均")
        
        self.tv_widget.add_ema(original_df, length=26, color="#2962FF", visible=False)
        print(f"  ✅ EMA(26)")
        
        # 添加 TEMA（三指数移动平均）用于追踪
        self.tv_widget.add_tema(original_df, length=20, color="#00FF00", visible=False)
        print(f"  ✅ TEMA(20) - 三指数移动平均 [追踪测试]")
        
        # 添加其他移动平均线指标
        self.tv_widget.add_wma(original_df, length=20, color="#00BCD4", visible=False)
        print(f"  ✅ WMA(20) - 加权移动平均")
        
        self.tv_widget.add_rma(original_df, length=20, color="#FF5722", visible=False)
        print(f"  ✅ RMA(20) - 平滑移动平均")
        
        self.tv_widget.add_dema(original_df, length=20, color="#9C27B0", visible=False)
        print(f"  ✅ DEMA(20) - 双指数移动平均")
        
        self.tv_widget.add_hma(original_df, length=20, color="#00E5FF", visible=False)
        print(f"  ✅ HMA(20) - Hull 移动平均")
        
        # 以下指标使用 JavaScript 端计算（lightweight-charts-indicators 库）
        self.tv_widget.add_lsma(original_df, length=20, color="#9C27B0", visible=False)
        print(f"  ✅ LSMA(20) - 最小二乘移动平均 [JS计算]")
        
        self.tv_widget.add_alma(original_df, length=20, offset=0.85, sigma=6, color="#00BCD4", visible=False)
        print(f"  ✅ ALMA(20) - ALMA 移动平均 [JS计算]")
        
        self.tv_widget.add_vwma(original_df, length=20, color="#FF9800", visible=False)
        print(f"  ✅ VWMA(20) - 成交量加权平均 [JS计算]")
        
        self.tv_widget.add_mcginley(original_df, length=14, color="#4CAF50", visible=False)
        print(f"  ✅ McGinley(14) - McGinley 动态 [JS计算]")
        
        self.tv_widget.add_ma_cross(original_df, fast=9, slow=21, color="#FF9800", visible=False)
        print(f"  ✅ EMA Cross(9,21) - 均线交叉 [JS计算]")
        
        self.tv_widget.add_ma_ribbon(original_df, lengths=[5, 10, 20, 50], visible=False)
        print(f"  ✅ MA Ribbon - 均线带 [JS计算]")
        
        self.tv_widget.add_zlsma(original_df, length=20, color="#E91E63", visible=False)
        print(f"  ✅ ZLSMA(20) - 零滞后 LSMA [JS计算]")
        
        # ===== 主图叠加指标 =====
        print(f"\n📊 【主图指标】")
        self.tv_widget.add_bbands(original_df, length=20, std=2, visible=False)
        print(f"  ✅ Bollinger Bands - 布林带")
        
        # ===== 副图振荡指标 =====
        print(f"\n📉 【副图指标】")
        self.tv_widget.add_rsi(original_df, length=14, visible=False)
        print(f"  ✅ RSI(14) - 相对强弱指数")
        
        self.tv_widget.add_stochrsi(original_df, length=14, visible=False)
        print(f"  ✅ StochRSI(14) - 随机 RSI")
        
        self.tv_widget.add_cci(original_df, length=20, visible=False)
        print(f"  ✅ CCI(20) - 商品通道指数")
        
        self.tv_widget.add_willr(original_df, length=14, visible=False)
        print(f"  ✅ Williams %R(14) - 威廉指标")
        
        self.tv_widget.add_ao(original_df, visible=False)
        print(f"  ✅ AO - Awesome 振荡器")
        
        self.tv_widget.add_cmo(original_df, length=14, visible=False)
        print(f"  ✅ CMO(14) - Chande 动量振荡器")
        
        self.tv_widget.add_dpo(original_df, length=20, visible=False)
        print(f"  ✅ DPO(20) - 去趋势价格振荡器")
        
        self.tv_widget.add_rvi(original_df, length=10, visible=False)
        print(f"  ✅ RVI(10) - 相对活力指数")
        
        self.tv_widget.add_tsi(original_df, long=25, short=13, signal=13, visible=False)
        print(f"  ✅ TSI(25,13,13) - 真实强度指数")
        
        self.tv_widget.add_uo(original_df, short=7, medium=14, long=28, visible=False)
        print(f"  ✅ UO(7,14,28) - 终极振荡器")
        
        self.tv_widget.add_kdj(original_df, k=9, d=3, visible=False)
        print(f"  ✅ KDJ(9,3) - KDJ 指标")
        
        self.tv_widget.add_wt(original_df, length1=10, length2=11, visible=False)
        print(f"  ✅ WaveTrend(10,11) - WaveTrend")
        
        self.tv_widget.add_stc(original_df, fast=23, slow=50, length=10, visible=False)
        print(f"  ✅ STC(23,50,10) - Schaff 趋势周期")
        
        self.tv_widget.add_macd(original_df, fast=12, slow=26, signal=9, visible=False)
        print(f"  ✅ MACD(12,26,9)")
        
        # ===== 动量指标 / Momentum =====
        print(f"\n📈 【动量指标】")
        self.tv_widget.add_momentum(original_df, length=10, visible=False)
        print(f"  ✅ Momentum(10) - 动量")
        
        self.tv_widget.add_roc(original_df, length=10, visible=False)
        print(f"  ✅ ROC(10) - 变化率")
        
        self.tv_widget.add_bop(original_df, visible=False)
        print(f"  ✅ BOP - 平衡能量")
        
        self.tv_widget.add_bullbearpower(original_df, length=13, visible=False)
        print(f"  ✅ BullBearPower(13) - 多空能量")
        
        self.tv_widget.add_coppock(original_df, visible=False)
        print(f"  ✅ CoppockCurve - Coppock 曲线")
        
        self.tv_widget.add_trix(original_df, length=15, visible=False)
        print(f"  ✅ TRIX(15)")
        
        self.tv_widget.add_squeeze(original_df, visible=False)
        print(f"  ✅ SqueezeMomentum - 挤压动量")
        
        # ===== 趋势指标 / Trend =====
        print(f"\n📊 【趋势指标】")
        self.tv_widget.add_adx(original_df, length=14, visible=False)
        print(f"  ✅ ADX(14) - 平均趋向指数")
        
        self.tv_widget.add_ichimoku(original_df, conversion=9, base=26, span_b=52, visible=False)
        print(f"  ✅ IchimokuCloud - 一目均衡图")
        
        self.tv_widget.add_parabolicsar(original_df, visible=False)
        print(f"  ✅ ParabolicSAR - 抛物线 SAR")
        
        self.tv_widget.add_volumesupertrendai(original_df, visible=False)
        print(f"  ✅ VolumeSuperTrendAi - 超级趋势")
        
        self.tv_widget.add_aroon(original_df, length=14, visible=False)
        print(f"  ✅ Aroon(14)")
        
        # ZigZag - 使用较小的阈值以获得更多转折点，默认可见以便调试
        self.tv_widget.add_zigzag_python(original_df, percent_change=3.0, color="#E91E63", visible=False)
        print(f"  ✅ ZigZag(3%) - 之字转向 [已启用显示，请查看控制台日志]")
        
        self.tv_widget.add_williamsalligator(original_df, jaw=13, teeth=8, lips=5, visible=False)
        print(f"  ✅ WilliamsAlligator - 威廉鳄鱼")
        
        self.tv_widget.add_donchianchannels(original_df, length=20, visible=False)
        print(f"  ✅ DonchianChannels(20) - 唐奇安通道")
        
        # ===== 波动率指标 / Volatility =====
        print(f"\n📉 【波动率指标】")
        self.tv_widget.add_atr(original_df, length=14, visible=False)
        print(f"  ✅ ATR(14) - 平均真实波幅")
        
        self.tv_widget.add_bollingerbands(original_df, length=20, std=2.0, visible=False)
        print(f"  ✅ BollingerBands(20,2) - 布林带")
        
        self.tv_widget.add_standarddeviation(original_df, length=20, visible=False)
        print(f"  ✅ StandardDeviation(20) - 标准差")
        
        self.tv_widget.add_historicalvolatility(original_df, length=20, visible=False)
        print(f"  ✅ HistoricalVolatility(20) - 历史波动率")
        
        self.tv_widget.add_choppiness(original_df, length=14, visible=False)
        print(f"  ✅ Choppiness(14) - 震荡指数")
        
        # ===== 成交量指标 / Volume =====
        print(f"\n💰 【成交量指标】")
        self.tv_widget.add_volume(original_df, visible=False)
        print(f"  ✅ BetterVolume - 成交量")
        
        self.tv_widget.add_vwma(original_df, length=20, visible=False)
        print(f"  ✅ VWMA(20) - 成交量加权平均")
        
        self.tv_widget.add_mfi(original_df, length=14, visible=False)
        print(f"  ✅ MFI(14) - 资金流量指数")
        
        self.tv_widget.add_obv(original_df, visible=False)
        print(f"  ✅ OBV - 能量潮")
        
        self.tv_widget.add_volumeaccumulationpct(original_df, length=20, visible=False)
        print(f"  ✅ VolumeAccumulationPct(20) - 累积/分布")
        
        # ===== 自定义指标 / Custom =====
        print(f"\n🎯 【自定义指标】")
        self.tv_widget.add_yearly_profile(original_df, period=252, visible=False)
        print(f"  ✅ YEARLY PROFILE(252) - 年度价格剖面 [副图显示]")
        
        print(f"\n{'='*60}")
        print(f"✅ 所有指标加载完成！")
        print(f"💡 提示：")
        print(f"   1. 通过右侧面板独立控制每个指标")
        print(f"   2. 通过底部按钮快速切换指标组")
        print(f"   3. 鼠标悬停查看十字光标数值")
        print(f"{'='*60}\n")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    print(f"\n 启动 TradingView Plus Widget 测试...")
    
    window = ChartPlusTestWindow()
    window.show()
    
    sys.exit(app.exec())