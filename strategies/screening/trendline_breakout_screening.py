# strategies/screening/trendline_breakout_screening.py
import qlib
from qlib.data import D
import pandas as pd
import numpy as np
from typing import Optional, Callable, List, Tuple
from loguru import logger
from strategies.base_strategy import BaseStrategy, StrategyResult
from core.qlibhelper import qlib_safeinit
from core.app_state import get_state
from pathlib import Path
import datetime


class TrendlineBreakoutStrategy(BaseStrategy):
    """突破下降趋势线策略"""
    
    KEY = "trendline_breakout"
    NAME = "趋势线突破策略"
    TOPK = 20
    
    def __init__(self, 
                 topk: Optional[int] = None,
                 trendline_points: int = 20,  # 用于绘制趋势线的点数
                 breakthrough_threshold: float = 0.03,  # 突破阈值（3%）
                 volume_confirmation_ratio: float = 1.5,  # 成交量确认倍数
                 consolidation_days: int = 3,  # 突破后整理天数
                 retest_confirmation: bool = True,  # 是否需要回踩确认
                 min_trend_duration: int = 10,  # 最小趋势持续时间
                 freq: str = "day"):
        super().__init__(topk=topk)
        self.trendline_points = trendline_points
        self.breakthrough_threshold = breakthrough_threshold
        self.volume_confirmation_ratio = volume_confirmation_ratio
        self.consolidation_days = consolidation_days
        self.retest_confirmation = retest_confirmation
        self.min_trend_duration = min_trend_duration
        self.freq = freq
    
    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        """执行趋势线突破策略"""
        # 初始化
        self._report(progress_cb, 5, f"分析 {len(universe)} 支股票，寻找突破信号...")
        
        homePath = Path.home()
        state = get_state()
        qlib_data = Path(f"{homePath}/.qlib/qlib_data/{state.reg}_data")
        qlib_safeinit(qlib_data)
        
        # 时间范围
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if self.freq == "day":
            start_date = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        else:
            start_date = (datetime.datetime.now() - datetime.timedelta(weeks=26)).strftime("%Y-%m-%d")
        
        scores = {}
        debug_results = []
        total_len = len(universe)
        
        for i, ticker in enumerate(universe):
            try:
                # 获取数据
                df = D.features([ticker], ['$close', '$high', '$low', '$volume'], 
                            start_time=start_date, end_time=end_date, freq=self.freq)
                
                if df.empty or len(df) < self.trendline_points + 10:
                    continue
                
                close_prices = df['$close'].dropna()
                high_prices = df['$high'].dropna()
                low_prices = df['$low'].dropna()
                volume = df['$volume'].dropna() if '$volume' in df.columns else None
                
                if len(close_prices) < self.trendline_points + 10:
                    continue
                
                # 分析下降趋势线突破
                result = self._analyze_trendline_breakout(
                    close_prices, high_prices, low_prices, volume
                )
                
                if result is None:
                    continue
                
                break_score, break_info, is_valid_breakout = result
                
                if is_valid_breakout and break_score > 0:
                    scores[ticker.upper()] = break_score
                    debug_results.append(f"{ticker}: ✓ {break_info}, 分数={break_score:.2f}")
                    
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
            model_name="Trendline Breakout Strategy",
            universe_size=len(universe),
        )
    
    def _analyze_trendline_breakout(self, close_prices: pd.Series,
                                  high_prices: pd.Series,
                                  low_prices: pd.Series,
                                  volume: Optional[pd.Series]) -> Optional[tuple]:
        """分析下降趋势线突破"""
        # 1. 识别下降趋势
        trend_result = self._identify_downtrend(close_prices, high_prices)
        if trend_result is None:
            return None
        
        trend_slope, trend_points, peak_indices = trend_result
        
        # 必须是下降趋势
        if trend_slope >= 0:
            return None
        
        # 2. 检查当前价格是否突破趋势线
        latest_price = close_prices.iloc[-1]
        trendline_value = self._calculate_trendline_value(
            trend_points, len(close_prices) - 1
        )
        
        if trendline_value is None:
            return None
        
        # 计算突破幅度
        break_ratio = (latest_price - trendline_value) / abs(trendline_value)
        
        # 必须突破阈值
        if break_ratio <= self.breakthrough_threshold:
            return None
        
        # 3. 检查成交量确认
        volume_confirmed = True
        if volume is not None and len(volume) >= 5:
            avg_volume = volume.iloc[-5:].mean()
            if len(volume) > 0 and volume.iloc[-1] < avg_volume * self.volume_confirmation_ratio:
                volume_confirmed = False
        
        if not volume_confirmed:
            return None
        
        # 4. 计算突破质量分数
        break_score = self._calculate_breakout_score(
            break_ratio, trend_slope, close_prices, volume
        )
        
        # 5. 检查后续整理
        if self.consolidation_days > 0:
            consolidation_ok = self._check_consolidation(
                close_prices, trendline_value, self.consolidation_days
            )
            if not consolidation_ok:
                break_score *= 0.7  # 分数打折
        
        # 6. 检查回踩
        if self.retest_confirmation:
            retest_ok = self._check_retest(close_prices, trendline_value)
            if retest_ok:
                break_score *= 1.2  # 有回踩加分
        
        info = f"突破{break_ratio:.1%} 斜率{trend_slope:.4f}"
        
        return break_score, info, True
    
    def _identify_downtrend(self, close_prices: pd.Series, 
                          high_prices: pd.Series) -> Optional[tuple]:
        """识别下降趋势"""
        if len(close_prices) < self.trendline_points:
            return None
        
        # 方法1：寻找近期高点（用于绘制下降趋势线）
        peak_indices = self._find_price_peaks(high_prices, lookback=self.trendline_points)
        
        if len(peak_indices) < 2:
            return None
        
        # 使用最后几个高点绘制趋势线
        trend_points = []
        for idx in peak_indices[-min(3, len(peak_indices)):]:
            if idx < len(close_prices):
                trend_points.append((idx, high_prices.iloc[idx]))
        
        if len(trend_points) < 2:
            return None
        
        # 计算趋势线斜率
        x_coords = [p[0] for p in trend_points]
        y_coords = [p[1] for p in trend_points]
        
        # 线性回归计算斜率
        if len(x_coords) >= 2:
            x_mean = np.mean(x_coords)
            y_mean = np.mean(y_coords)
            
            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_coords, y_coords))
            denominator = sum((x - x_mean) ** 2 for x in x_coords)
            
            if denominator != 0:
                slope = numerator / denominator
                return slope, trend_points, peak_indices
        
        return None
    
    def _find_price_peaks(self, prices: pd.Series, lookback: int = 20) -> List[int]:
        """寻找价格高点"""
        peaks = []
        
        for i in range(1, min(lookback, len(prices) - 1)):
            idx = len(prices) - i - 1
            if (prices.iloc[idx] > prices.iloc[idx-1] and 
                prices.iloc[idx] > prices.iloc[idx+1]):
                peaks.append(idx)
        
        return sorted(peaks)
    
    def _calculate_trendline_value(self, trend_points: List[tuple], 
                                 x_position: int) -> Optional[float]:
        """计算趋势线在指定位置的值"""
        if len(trend_points) < 2:
            return None
        
        # 使用线性插值
        x_coords = [p[0] for p in trend_points]
        y_coords = [p[1] for p in trend_points]
        
        # 选择最新的两个点计算趋势线
        if len(trend_points) >= 2:
            p1 = trend_points[-2]
            p2 = trend_points[-1]
            
            # 直线方程：y = kx + b
            if p2[0] != p1[0]:
                k = (p2[1] - p1[1]) / (p2[0] - p1[0])
                b = p1[1] - k * p1[0]
                return k * x_position + b
        
        return None
    
    def _calculate_breakout_score(self, break_ratio: float,
                                trend_slope: float,
                                close_prices: pd.Series,
                                volume: Optional[pd.Series]) -> float:
        """计算突破质量分数"""
        score = 0
        
        # 1. 突破幅度（越大越好）
        score += min(break_ratio * 100, 50)  # 最多50分
        
        # 2. 原趋势强度（斜率越陡，突破意义越大）
        trend_strength = abs(trend_slope) * 10000
        score += min(trend_strength, 20)  # 最多20分
        
        # 3. 突破前的蓄势（波动率收缩）
        if len(close_prices) >= 20:
            recent_volatility = close_prices.pct_change().std() * 100
            if recent_volatility < 2:  # 低波动率蓄势
                score += 10
        
        # 4. 突破K线形态
        if len(close_prices) >= 3:
            # 检查是否是中阳线或大阳线突破
            today_change = (close_prices.iloc[-1] - close_prices.iloc[-2]) / close_prices.iloc[-2] if close_prices.iloc[-2] != 0 else 0
            if today_change > 0.02:  # 涨幅超过2%
                score += 10
        
        # 5. 成交量配合
        if volume is not None and len(volume) >= 5:
            vol_ratio = volume.iloc[-1] / volume.iloc[-5:].mean() if volume.iloc[-5:].mean() != 0 else 1
            if vol_ratio > 1.5:
                score += 10
        
        return max(score, 0)
    
    def _check_consolidation(self, close_prices: pd.Series,
                           trendline_value: float,
                           consolidation_days: int) -> bool:
        """检查突破后的整理"""
        if len(close_prices) < consolidation_days + 1:
            return True
        
        # 检查突破后几天是否保持在趋势线上方
        for i in range(1, consolidation_days + 1):
            if close_prices.iloc[-i] < trendline_value:
                return False
        
        return True
    
    def _check_retest(self, close_prices: pd.Series,
                     trendline_value: float) -> bool:
        """检查是否回踩趋势线"""
        if len(close_prices) < 5:
            return False
        
        # 寻找突破后的回踩
        for i in range(1, min(5, len(close_prices) - 1)):
            idx = -i - 1
            if idx >= 0:
                # 价格接近趋势线但未跌破
                price_diff = abs(close_prices.iloc[idx] - trendline_value) / trendline_value
                if price_diff < 0.01:  # 1%以内视为回踩
                    return True
        
        return False
    
    def _report(self, cb, pct: int, msg: str) -> None:
        if cb:
            try:
                cb(pct, msg)
            except Exception:
                pass
        logger.debug(f"[{self.KEY}] {pct}% - {msg}")