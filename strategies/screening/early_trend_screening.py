# strategies/screening/early_trend_screening.py
import qlib
from qlib.data import D
import pandas as pd
import numpy as np
from typing import Optional, Callable, Tuple
from loguru import logger
from strategies.base_strategy import BaseStrategy, StrategyResult
from core.qlibhelper import qlib_safeinit
from core.app_state import get_state
from pathlib import Path
import datetime


class EarlyTrendFormationStrategy(BaseStrategy):
    """趋势早期识别策略 - 避免追高，捕捉启动点"""
    
    KEY = "early_trend"
    NAME = "趋势早期识别策略"
    TOPK = 20
    
    def __init__(self, 
                 topk: Optional[int] = None,
                 max_convergence_days: int = 20,  # 均线最大聚拢天数
                 min_price_distance_to_resistance: float = 0.05,  # 距离阻力位最小距离
                 volume_increase_ratio: float = 1.2,  # 成交量放大倍数
                 require_small_slope: bool = True,  # 要求小斜率
                 max_slope: float = 0.02,  # 最大日斜率(2%)
                 freq: str = "day",
                 use_macd_confirmation: bool = True,  # MACD确认
                 use_bollinger_squeeze: bool = True,  # 布林带收口
                 trend_formation_days: int = 5):  # 趋势形成天数
        super().__init__(topk=topk)
        self.max_convergence_days = max_convergence_days
        self.min_price_distance_to_resistance = min_price_distance_to_resistance
        self.volume_increase_ratio = volume_increase_ratio
        self.require_small_slope = require_small_slope
        self.max_slope = max_slope
        self.freq = freq
        self.use_macd_confirmation = use_macd_confirmation
        self.use_bollinger_squeeze = use_bollinger_squeeze
        self.trend_formation_days = trend_formation_days
    
    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        """执行趋势早期识别策略"""
        # 初始化
        self._report(progress_cb, 5, f"分析 {len(universe)} 支股票，寻找趋势早期信号...")
        
        homePath = Path.home()
        state = get_state()
        qlib_data = Path(f"{homePath}/.qlib/qlib_data/{state.reg}_data")
        qlib_safeinit(qlib_data)
        
        # 时间范围
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if self.freq == "day":
            start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
        elif self.freq == "week":
            start_date = (datetime.datetime.now() - datetime.timedelta(weeks=120)).strftime("%Y-%m-%d")
        
        scores = {}
        debug_results = []
        total_len = len(universe)
        
        for i, ticker in enumerate(universe):
            try:
                # 获取数据
                df = D.features([ticker], ['$close', '$open', '$high', '$low', '$volume'], 
                            start_time=start_date, end_time=end_date, freq=self.freq)
                
                if df.empty or len(df) < 30:
                    continue
                
                # 计算技术指标
                close_prices = df['$close'].dropna()
                high_prices = df['$high'].dropna()
                low_prices = df['$low'].dropna()
                volume = df['$volume'].dropna() if '$volume' in df.columns else None
                
                if len(close_prices) < 30:
                    continue
                
                # 核心：趋势早期识别
                trend_score = self._analyze_early_trend_formation(
                    close_prices, high_prices, low_prices, volume
                )
                
                if trend_score > 0:
                    scores[ticker.upper()] = trend_score
                    debug_results.append(f"{ticker}: ✓ 早期趋势分数={trend_score:.2f}")
                
            except Exception as e:
                continue
            
            # 进度上报
            if (i + 1) % 20 == 0 or (i + 1) == total_len:
                progress_pct = 10 + int(80 * (i + 1) / total_len)
                self._report(progress_cb, progress_pct, f"处理中 {i+1}/{total_len}...")
        
        # 生成结果
        if scores:
            scores_series = pd.Series(scores, name="score").sort_values(ascending=False)
            topk = min(self.topk, len(scores_series))
            topk_tickers = scores_series.head(topk).index.tolist()
        else:
            scores_series = pd.Series(dtype=float)
            topk_tickers = []
        
        self._report(progress_cb, 100, f"选出 {len(topk_tickers)} 支")
        
        return StrategyResult(
            strategy_key=self.KEY,
            strategy_name=self.NAME,
            scores=scores_series,
            topk_tickers=topk_tickers,
            model_name="Early Trend Formation",
            universe_size=len(universe),
        )
    
    def _analyze_early_trend_formation(self, close_prices: pd.Series, 
                                     high_prices: pd.Series, 
                                     low_prices: pd.Series,
                                     volume: Optional[pd.Series]) -> float:
        """层次化评分：核心条件权重高，辅助条件权重低"""
        scores = {}
        
        # 核心条件（高权重）
        scores['convergence'] = self._check_ma_convergence(close_prices)
        scores['slope'] = self._check_small_slope_upward(close_prices)
        
        # 辅助条件（中等权重）
        scores['breakout'] = self._check_price_breakout(close_prices, high_prices, low_prices)
        
        # 确认条件（低权重）
        if volume is not None:
            scores['volume'] = self._check_volume_confirmation(close_prices, volume)
        
        if self.use_macd_confirmation:
            scores['macd'] = self._check_macd_confirmation(close_prices)
        
        if self.use_bollinger_squeeze:
            scores['bollinger'] = self._check_bollinger_squeeze(close_prices)
        
        # 计算加权总分
        weights = {
            'convergence': 0.4,  # 核心条件权重高
            'slope': 0.3,        # 核心条件权重高
            'breakout': 0.15,    # 辅助条件
            'volume': 0.1,       # 确认条件
            'macd': 0.05,        # 技术指标
            'bollinger': 0.05,   # 技术指标
        }
        
        total_score = 0
        for key, score in scores.items():
            if key in weights and score > 0:
                total_score += score * weights[key]
        
        # 设置最低门槛：核心条件不能都为0
        if scores['convergence'] <= 0 and scores['slope'] <= 0:
            return 0
        
        return round(total_score, 4)    
    def _check_ma_convergence(self, close_prices: pd.Series) -> float:
        """检查均线聚拢状态"""
        # 计算多周期均线
        ma5 = close_prices.rolling(5).mean()
        ma10 = close_prices.rolling(10).mean()
        ma20 = close_prices.rolling(20).mean()
        
        if len(ma20) < 30:
            return 0
        
        # 1. 计算均线间的距离
        distance_5_10 = abs(ma5.iloc[-1] - ma10.iloc[-1]) / ma10.iloc[-1] if ma10.iloc[-1] != 0 else 0
        distance_10_20 = abs(ma10.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] if ma20.iloc[-1] != 0 else 0
        distance_5_20 = abs(ma5.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] if ma20.iloc[-1] != 0 else 0
        
        # 均线应高度聚拢（距离小于3%）
        max_allowed_distance = 0.03
        if (distance_5_10 > max_allowed_distance or 
            distance_10_20 > max_allowed_distance or
            distance_5_20 > max_allowed_distance):
            return 0
        
        # 2. 检查最近N天是否从发散到聚拢
        if len(ma5) >= self.max_convergence_days + 5:
            # 计算N天前的均线距离
            prev_5_10 = abs(ma5.iloc[-self.max_convergence_days] - ma10.iloc[-self.max_convergence_days]) / ma10.iloc[-self.max_convergence_days] if ma10.iloc[-self.max_convergence_days] != 0 else 0
            
            # 距离应该缩小（从发散到聚拢）
            convergence_improvement = prev_5_10 - distance_5_10
            if convergence_improvement > 0:
                convergence_score = 50 + min(convergence_improvement * 1000, 50)
                return convergence_score
        
        return 0
    
    def _check_small_slope_upward(self, close_prices: pd.Series) -> float:
        """检查小斜率向上"""
        if len(close_prices) < 10:
            return 0
        
        # 1. 计算短期斜率（最近5天）
        recent_slope = self._calculate_slope(close_prices.tail(5))
        
        # 必须向上但斜率不大
        if recent_slope <= 0 or recent_slope > self.max_slope:
            return 0
        
        # 2. 检查斜率变化（从平缓到小斜率）
        if len(close_prices) >= 15:
            # 前5天的斜率
            prev_slope = self._calculate_slope(close_prices.iloc[-10:-5])
            
            # 斜率应该从接近0变为小正数
            slope_increase = recent_slope - prev_slope
            if slope_increase > 0:
                slope_score = 30 + min(slope_increase * 1000, 20)
                return slope_score
        
        return 0
    
    def _check_price_breakout(self, close_prices: pd.Series, 
                            high_prices: pd.Series, 
                            low_prices: pd.Series) -> float:
        """检查价格突破收敛区"""
        if len(close_prices) < 20:
            return 0
        
        # 1. 计算近期波动范围
        recent_high = high_prices.tail(10).max()
        recent_low = low_prices.tail(10).min()
        recent_range = recent_high - recent_low
        range_mid = (recent_high + recent_low) / 2
        
        if recent_range == 0:
            return 0
        
        # 2. 当前价格位置
        current_price = close_prices.iloc[-1]
        
        # 突破到上半区
        price_position = (current_price - range_mid) / (recent_high - range_mid) if (recent_high - range_mid) > 0 else 0
        
        if price_position > 0.5:  # 在上半区
            breakout_score = 20 + (price_position - 0.5) * 100
            return min(breakout_score, 40)
        
        return 0
    
    def _check_volume_confirmation(self, close_prices: pd.Series, 
                                 volume: pd.Series) -> float:
        """检查成交量确认"""
        if len(volume) < 20:
            return 0
        
        # 1. 成交量温和放大
        recent_vol_avg = volume.tail(5).mean()
        prev_vol_avg = volume.iloc[-10:-5].mean()
        
        if prev_vol_avg == 0:
            return 0
        
        volume_ratio = recent_vol_avg / prev_vol_avg
        
        # 温和放量（1.2-2倍最佳）
        if 1.1 <= volume_ratio <= 2.0:
            volume_score = 10 + min((volume_ratio - 1) * 20, 10)
            return volume_score
        
        return 0
    
    def _calculate_slope(self, series: pd.Series) -> float:
        """计算线性回归斜率"""
        if len(series) < 2:
            return 0
        
        x = np.arange(len(series))
        y = series.values
        
        # 简单斜率计算
        slope = (y[-1] - y[0]) / (len(series) - 1) / y[0] if y[0] != 0 else 0
        return slope
    
    def _report(self, cb, pct: int, msg: str) -> None:
        if cb:
            try:
                cb(pct, msg)
            except Exception:
                pass
        logger.debug(f"[{self.KEY}] {pct}% - {msg}")

    def _check_macd_confirmation(self, close_prices: pd.Series) -> float:
            """检查MACD零轴附近金叉（趋势早期信号）"""
            if len(close_prices) < 26:
                return 0
            
            # 计算EMA
            ema12 = close_prices.ewm(span=12, adjust=False).mean()
            ema26 = close_prices.ewm(span=26, adjust=False).mean()
            dif = ema12 - ema26
            dea = dif.ewm(span=9, adjust=False).mean()
            macd = (dif - dea) * 2
            
            if len(dif) < 2:
                return 0
            
            # 1. DIF在零轴附近（-0.5% 到 0.5%）
            current_dif = dif.iloc[-1]
            if abs(current_dif / close_prices.iloc[-1]) > 0.005:  # 超过0.5%
                return 0
            
            # 2. 最近发生金叉
            is_golden_cross = False
            for i in range(1, min(5, len(dif))):
                if (dif.iloc[-i] > dea.iloc[-i] and 
                    dif.iloc[-i-1] <= dea.iloc[-i-1]):
                    is_golden_cross = True
                    break
            
            if is_golden_cross:
                # 3. MACD柱状线由负转正
                if len(macd) >= 3 and macd.iloc[-1] > 0 and macd.iloc[-2] < 0:
                    return 15
            
            return 0

    def _check_bollinger_squeeze(self, close_prices: pd.Series) -> float:
            """检查布林带收口突破（波动率压缩后扩张）"""
            if len(close_prices) < 20:
                return 0
            
            # 计算布林带
            ma20 = close_prices.rolling(20).mean()
            std20 = close_prices.rolling(20).std()
            upper = ma20 + 2 * std20
            lower = ma20 - 2 * std20
            
            if len(upper) < 3:
                return 0
            
            # 1. 布林带收口（带宽缩小）
            current_bandwidth = (upper.iloc[-1] - lower.iloc[-1]) / ma20.iloc[-1] if ma20.iloc[-1] != 0 else 0
            prev_bandwidth = (upper.iloc[-5] - lower.iloc[-5]) / ma20.iloc[-5] if ma20.iloc[-5] != 0 else 0
            
            # 带宽缩小
            if prev_bandwidth > 0 and current_bandwidth < prev_bandwidth * 0.8:
                # 2. 价格突破中轨向上
                current_price = close_prices.iloc[-1]
                if current_price > ma20.iloc[-1]:
                    squeeze_score = 10 + (1 - current_bandwidth/prev_bandwidth) * 20
                    return min(squeeze_score, 20)
            
            return 0