# strategies/screening/golden_cross_screening.py
import qlib
from qlib.config import REG_CN
from qlib.data import D
import pandas as pd
import numpy as np
from typing import Optional, Callable, List, Tuple, Dict
from loguru import logger
from strategies.base_strategy import BaseStrategy, StrategyResult
from core.qlibhelper import qlib_safeinit
from core.app_state import get_state
from pathlib import Path
import datetime
from strategies.screening.signal_lifecycle_scorer import SignalLifecycleScorer
from strategies.screening.adaptive_time_window_scorer import AdaptiveTimeWindowScorer
from strategies.screening.ma10_screening import momentum_decay_model

class GoldenCrossMAStrategy(BaseStrategy):
    """金叉 + 5-10-20-60日线打开向上策略"""
    
    KEY = "golden_cross_ma"
    NAME = "金叉均线多头策略"
    TOPK = 20
    
    def __init__(self, 
                 topk: Optional[int] = None,
                 require_volume_confirmation: bool = True,  # 成交量确认
                 max_cross_days: int = 10,  # 金叉最大发生天数
                 min_price_above_ma5: bool = True,  # 股价在5日线上
                 freq: str = "day",  # 数据频率
                 golden_cross_type: str = "510",  # 510=5-10金叉, 1020=10-20金叉
                 require_all_ma_up: bool = False,  # 要求所有均线向上
                 divergence_weight: float = 1.5,  # 发散度权重
                 min_ma_distance: float = 0.01,  # 最小均线间距(1%)
                 cross_decay_enabled: bool = True,
                 cross_decay_half_life: int = 3,  # 金叉衰减更快
                 divergence_decay_enabled: bool = True,
                 divergence_start_days: int = 5):  # 发散开始计时的天数
        super().__init__(topk=topk)
        self.require_volume_confirmation = require_volume_confirmation
        self.max_cross_days = max_cross_days
        self.min_price_above_ma5 = min_price_above_ma5
        self.freq = freq
        self.golden_cross_type = golden_cross_type
        self.require_all_ma_up = require_all_ma_up
        self.divergence_weight = divergence_weight
        self.min_ma_distance = min_ma_distance
        self.cross_decay_enabled = cross_decay_enabled
        self.cross_decay_half_life = cross_decay_half_life
        self.divergence_decay_enabled = divergence_decay_enabled
        self.divergence_start_days = divergence_start_days
    
    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        """执行金叉均线多头策略"""
        # 1. 初始化QLib
        self._report(progress_cb, 5, f"初始化QLib，分析 {len(universe)} 支股票...")
        
        homePath = Path.home()
        state = get_state()
        qlib_data = Path(f"{homePath}/.qlib/qlib_data/{state.reg}_data")
        qlib_safeinit(qlib_data)
        
        # 2. 设置时间范围
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if self.freq == "day":
            # 获取足够数据计算60日均线
            start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
        elif self.freq == "week":
            start_date = (datetime.datetime.now() - datetime.timedelta(weeks=120)).strftime("%Y-%m-%d")
        
        debug_results = []
        scores = {}
        total_len = max(1,len(universe))
        
        # 3. 批量处理股票
        for i, ticker in enumerate(universe):
            try:
                # 获取数据
                df = D.features([ticker], ['$close', '$volume'], 
                            start_time=start_date, end_time=end_date, freq=self.freq)
                
                if df.empty:
                    debug_results.append(f"{ticker}: 无数据")
                    continue
                
                # 计算各种技术指标
                result = self._calculate_technical_signals(df, ticker)
                
                if result is None:
                    continue
                
                # 提取结果
                (score, cross_strength, alignment_score, divergence_score, 
                 trend_strength, cross_info, is_golden_cross_recent) = result
                
                if is_golden_cross_recent:
                    # 计算综合分数
                    final_score = self._calculate_comprehensive_score(
                        cross_strength, alignment_score, divergence_score, trend_strength
                    )
                    
                    if final_score > 0:
                        scores[ticker.upper()] = final_score
                        debug_results.append(
                            f"{ticker}: ✓ 金叉({cross_info}), "
                            f"排列={alignment_score:.2f}, 发散={divergence_score:.2f}, "
                            f"趋势={trend_strength:.2f}, 总分={final_score:.2f}"
                        )
                else:
                    debug_results.append(f"{ticker}: ✗ 无近期金叉 (最近金叉:{cross_info})")
                    
            except Exception as e:
                debug_results.append(f"{ticker}: 错误 - {str(e)[:50]}")
                continue
            
            # 进度上报
            if (i + 1) % 10 == 0 or (i + 1) == total_len:
                progress_pct = 10 + int(80 * (i + 1) / total_len)
                self._report(progress_cb, progress_pct, f"处理中 {i+1}/{total_len}...")
        
        # 4. 输出调试信息
        if debug_results:
            logger.info(f"金叉策略调试结果 (前20条):")
            for result in debug_results[:20]:
                logger.info(result)
        
        # 5. 排序和筛选
        self._report(progress_cb, 90, f"计算完成，{len(scores)}支满足条件")
        
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
            strategy_name=f"{self.NAME}({self.golden_cross_type}金叉)",
            scores=scores_series,
            topk_tickers=topk_tickers,
            model_name=f"Golden Cross MA({self.freq})",
            universe_size=len(universe),
        )
    
    def _calculate_technical_signals(self, df: pd.DataFrame, ticker: str) -> Optional[tuple]:
        """计算技术信号"""
        if df.empty or len(df) < 65:  # 需要足够数据计算60日均线
            return None
        
        close_prices = df['$close'].dropna()
        volume = df['$volume'].dropna() if '$volume' in df.columns else None
        
        if len(close_prices) < 65:
            return None
        
        # 计算各种均线
        ma5 = close_prices.rolling(5).mean()
        ma10 = close_prices.rolling(10).mean()
        ma20 = close_prices.rolling(20).mean()
        ma60 = close_prices.rolling(60).mean()
        
        # 1. 检查金叉信号
        cross_result = self._check_golden_cross_signal(ma5, ma10, ma20, ma60)
        if cross_result is None:
            return None
        
        cross_strength, cross_days_ago, cross_type = cross_result
        
        # 2. 检查是否在时间窗口内
        if cross_days_ago > self.max_cross_days:
            return (0, cross_strength, 0, 0, 0, f"{cross_type}({cross_days_ago}天前)", False)
        
        # 3. 检查股价位置
        if self.min_price_above_ma5 and close_prices.iloc[-1] <= ma5.iloc[-1]:
            return None
        
        # 4. 检查成交量确认
        if self.require_volume_confirmation and volume is not None and len(volume) >= 5:
            vol_ma5 = volume.rolling(5).mean()
            if len(vol_ma5) > 0 and volume.iloc[-1] <= vol_ma5.iloc[-1] * 0.8:  # 缩量
                return None
        
        # 5. 计算均线排列分数
        alignment_score = self._calculate_alignment_score(ma5, ma10, ma20, ma60)
        
        # 6. 计算发散度
        divergence_score = self._calculate_divergence_score(ma5, ma10, ma20, ma60)
        
        # 7. 计算趋势强度
        trend_strength = self._calculate_trend_strength(close_prices, ma5, ma10, ma20, ma60)
        
        return (0, cross_strength, alignment_score, divergence_score, 
                trend_strength, f"{cross_type}({cross_days_ago}天前)", True)
    
    def _check_golden_cross_signal(self, ma5: pd.Series, ma10: pd.Series, 
                                 ma20: pd.Series, ma60: pd.Series) -> Optional[tuple]:
        """检查金叉信号"""
        # 确定要检查的金叉类型
        if self.golden_cross_type == "510":
            short_ma, long_ma = ma5, ma10
            cross_type = "5-10金叉"
        elif self.golden_cross_type == "1020":
            short_ma, long_ma = ma10, ma20
            cross_type = "10-20金叉"
        elif self.golden_cross_type == "520":
            short_ma, long_ma = ma5, ma20
            cross_type = "5-20金叉"
        else:
            # 默认检查5-10金叉
            short_ma, long_ma = ma5, ma10
            cross_type = "5-10金叉"
        
        # 查找最近的金叉
        cross_days_ago = None
        max_cross_strength = 0
        
        # 向后查找金叉
        for i in range(2, min(30, len(short_ma))):  # 最近30天
            if (short_ma.iloc[-i] > long_ma.iloc[-i] and 
                short_ma.iloc[-i-1] <= long_ma.iloc[-i-1]):
                # 找到金叉
                cross_days_ago = i - 1
                
                # 计算金叉强度（金叉角度）
                cross_strength = self._calculate_cross_strength(
                    short_cur=short_ma.iloc[-i],
                    long_cur=long_ma.iloc[-i],
                    short_prev=short_ma.iloc[-i-1],
                    long_prev=long_ma.iloc[-i-1],
                    days_since_cross=cross_days_ago
                )
                max_cross_strength = max(max_cross_strength, cross_strength)
                break
        
        if cross_days_ago is not None:
            # 加入时间衰减
            time_weight = self._calculate_cross_decay_weight(cross_days_ago)
            adjusted_strength = max_cross_strength * time_weight
            
            return adjusted_strength, cross_days_ago, cross_type
        
        return None
    
    def _calculate_cross_strength(self, short_cur: float, long_cur: float,
                                short_prev: float, long_prev: float,
                                days_since_cross: int = 0) -> float:
        """计算金叉强度"""
        # 金叉角度 = 短期均线斜率 - 长期均线斜率
        short_slope = (short_cur - short_prev) / short_prev if short_prev != 0 else 0
        long_slope = (long_cur - long_prev) / long_prev if long_prev != 0 else 0
        cross_angle = short_slope - long_slope
        
        # 交叉后的间距
        cross_gap = (short_cur - long_cur) / long_cur if long_cur != 0 else 0
        
        # 综合强度
        original_strength = cross_angle * 100 + cross_gap * 50
        
        # 应用动量衰减
        if days_since_cross > 0:
            decayed_strength = momentum_decay_model(
                initial_momentum=original_strength,
                days_ago=days_since_cross,
                decay_factor=0.8  # 金叉动量衰减较快
            )
            return max(decayed_strength, 0)
        
        return max(original_strength, 0)
    
    def _calculate_alignment_score(self, ma5: pd.Series, ma10: pd.Series,
                                 ma20: pd.Series, ma60: pd.Series) -> float:
        """计算均线排列分数"""
        # 获取最新值
        ma5_cur = ma5.iloc[-1]
        ma10_cur = ma10.iloc[-1]
        ma20_cur = ma20.iloc[-1]
        ma60_cur = ma60.iloc[-1]
        
        # 检查多头排列
        is_aligned = (ma5_cur > ma10_cur > ma20_cur > ma60_cur)
        
        if not is_aligned:
            return 0
        
        # 计算排列质量
        alignment_score = 0
        
        # 1. 间距均匀性
        gap_510 = (ma5_cur - ma10_cur) / ma10_cur if ma10_cur != 0 else 0
        gap_1020 = (ma10_cur - ma20_cur) / ma20_cur if ma20_cur != 0 else 0
        gap_2060 = (ma20_cur - ma60_cur) / ma60_cur if ma60_cur != 0 else 0
        
        # 间距应该逐渐扩大（发散）
        if gap_510 > 0 and gap_1020 > 0 and gap_2060 > 0:
            alignment_score += (gap_510 + gap_1020 + gap_2060) * 100
        
        # 2. 均线方向一致性
        if self.require_all_ma_up:
            # 检查所有均线向上
            ma5_up = ma5.iloc[-1] > ma5.iloc[-5]
            ma10_up = ma10.iloc[-1] > ma10.iloc[-10]
            ma20_up = ma20.iloc[-1] > ma20.iloc[-20]
            ma60_up = ma60.iloc[-1] > ma60.iloc[-60]
            
            up_count = sum([ma5_up, ma10_up, ma20_up, ma60_up])
            alignment_score += up_count * 25
        
        return max(alignment_score, 0)
    
    def _calculate_cross_decay_weight(self, cross_days_ago: int) -> float:
        """金叉时间衰减权重"""
        if not self.cross_decay_enabled or cross_days_ago <= 0:
            return 1.0
        
        # 金叉的衰减更快（半衰期3天）
        return 0.5 ** (cross_days_ago / self.cross_decay_half_life)
    
    def _calculate_divergence_score(self, ma5: pd.Series, ma10: pd.Series,
                                  ma20: pd.Series, ma60: pd.Series) -> float:
        """计算均线发散度"""
        # 获取当前和之前的间距
        ma5_cur, ma10_cur = ma5.iloc[-1], ma10.iloc[-1]
        ma20_cur, ma60_cur = ma20.iloc[-1], ma60.iloc[-1]
        
        # 当前间距
        gap_510_cur = (ma5_cur - ma10_cur) / ma10_cur if ma10_cur != 0 else 0
        gap_1020_cur = (ma10_cur - ma20_cur) / ma20_cur if ma20_cur != 0 else 0
        gap_2060_cur = (ma20_cur - ma60_cur) / ma60_cur if ma60_cur != 0 else 0
        
        # 前期间距（5天前）
        if len(ma5) >= 6:
            ma5_prev, ma10_prev = ma5.iloc[-6], ma10.iloc[-6]
            ma20_prev, ma60_prev = ma20.iloc[-6], ma60.iloc[-6]
            
            gap_510_prev = (ma5_prev - ma10_prev) / ma10_prev if ma10_prev != 0 else 0
            gap_1020_prev = (ma10_prev - ma20_prev) / ma20_prev if ma20_prev != 0 else 0
            gap_2060_prev = (ma20_prev - ma60_prev) / ma60_prev if ma60_prev != 0 else 0
            
            # 计算发散度（间距扩大程度）
            divergence_510 = (gap_510_cur - gap_510_prev) * 100
            divergence_1020 = (gap_1020_cur - gap_1020_prev) * 100
            divergence_2060 = (gap_2060_cur - gap_2060_prev) * 100
            
            # 综合发散度
            divergence_score = (divergence_510 + divergence_1020 + divergence_2060) * 10
   
        # 加入发散开始的时间衰减
        if self.divergence_decay_enabled and divergence_score > 0:
            # 估计发散开始的天数
            divergence_start_estimate = self._estimate_divergence_start(
                ma5, ma10, ma20, ma60
            )
            
            if divergence_start_estimate > 0:
                # 发散开始越久，权重越低
                decay_weight = 0.5 ** (divergence_start_estimate / 10)
                divergence_score *= decay_weight
        
        return max(divergence_score, 0)
    
    def _estimate_divergence_start(self, ma5: pd.Series, ma10: pd.Series,
                                 ma20: pd.Series, ma60: pd.Series) -> int:
        """估计均线发散开始的时间"""
        lookback_days = min(20, len(ma5))
        
        for i in range(2, lookback_days):
            # 计算i天前的均线间距
            gap_510_prev = (ma5.iloc[-i] - ma10.iloc[-i]) / ma10.iloc[-i] if ma10.iloc[-i] != 0 else 0
            gap_1020_prev = (ma10.iloc[-i] - ma20.iloc[-i]) / ma20.iloc[-i] if ma20.iloc[-i] != 0 else 0
            
            # 计算当前的均线间距
            gap_510_cur = (ma5.iloc[-1] - ma10.iloc[-1]) / ma10.iloc[-1] if ma10.iloc[-1] != 0 else 0
            gap_1020_cur = (ma10.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] if ma20.iloc[-1] != 0 else 0
            
            # 如果间距显著扩大，认为发散开始
            if (gap_510_cur > gap_510_prev * 1.5 or 
                gap_1020_cur > gap_1020_prev * 1.5):
                return i
        
        return 0
    
    def _calculate_trend_strength(self, close_prices: pd.Series, ma5: pd.Series,
                                ma10: pd.Series, ma20: pd.Series, ma60: pd.Series) -> float:
        """计算趋势强度"""
        trend_score = 0
        
        # 1. 价格在均线上方
        price = close_prices.iloc[-1]
        above_ma5 = 1 if price > ma5.iloc[-1] else 0
        above_ma10 = 1 if price > ma10.iloc[-1] else 0
        above_ma20 = 1 if price > ma20.iloc[-1] else 0
        above_ma60 = 1 if price > ma60.iloc[-1] else 0
        
        trend_score += (above_ma5 + above_ma10 + above_ma20 + above_ma60) * 25
        
        # 2. 均线斜率
        if len(ma5) >= 6:
            ma5_slope = (ma5.iloc[-1] - ma5.iloc[-5]) / ma5.iloc[-5] if ma5.iloc[-5] != 0 else 0
            ma10_slope = (ma10.iloc[-1] - ma10.iloc[-10]) / ma10.iloc[-10] if ma10.iloc[-10] != 0 else 0
            ma20_slope = (ma20.iloc[-1] - ma20.iloc[-20]) / ma20.iloc[-20] if ma20.iloc[-20] != 0 else 0
            
            trend_score += (ma5_slope + ma10_slope + ma20_slope) * 100
        
        return max(trend_score, 0)
    
    def _calculate_comprehensive_score(self, cross_strength: float, 
                                     alignment_score: float, 
                                     divergence_score: float,
                                     trend_strength: float) -> float:
        """计算综合分数"""
        # 权重分配
        cross_weight = 0.4
        alignment_weight = 0.3
        divergence_weight = 0.2 * self.divergence_weight
        trend_weight = 0.1
        
        # 标准化处理
        max_cross = 10.0
        max_alignment = 200.0
        max_divergence = 50.0
        max_trend = 200.0
        
        # 计算各项得分
        cross_norm = min(cross_strength / max_cross, 1.0) * 100
        alignment_norm = min(alignment_score / max_alignment, 1.0) * 100
        divergence_norm = min(divergence_score / max_divergence, 1.0) * 100
        trend_norm = min(trend_strength / max_trend, 1.0) * 100
        
        # 加权综合
        total_score = (
            cross_norm * cross_weight +
            alignment_norm * alignment_weight +
            divergence_norm * divergence_weight +
            trend_norm * trend_weight
        )
        
        return round(total_score, 4)
    
    def _report(self, cb, pct: int, msg: str) -> None:
        if cb:
            try:
                cb(pct, msg)
            except Exception:
                pass
        logger.debug(f"[{self.KEY}] {pct}% - {msg}")