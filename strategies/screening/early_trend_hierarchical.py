# strategies/screening/early_trend_hierarchical_fixed.py
import qlib
from qlib.data import D
import pandas as pd
import numpy as np
from typing import Optional, Callable, Tuple, Dict, List
from loguru import logger
from strategies.base_strategy import BaseStrategy, StrategyResult
from core.qlibhelper import qlib_safeinit
from core.app_state import get_state
from pathlib import Path
import datetime


class EarlyTrendHierarchicalStrategy(BaseStrategy):
    """趋势早期识别策略 - 基于early_trend_screening的层次化评分版本"""
    
    KEY = "early_trend_hierarchical"
    NAME = "趋势早期识别策略(层次化评分)"
    TOPK = 20
    
    def __init__(self, 
                 topk: Optional[int] = None,
                 # 基础参数（继承自early_trend_screening）
                 max_convergence_days: int = 20,
                 min_price_distance_to_resistance: float = 0.05,
                 volume_increase_ratio: float = 1.2,
                 require_small_slope: bool = True,
                 max_slope: float = 0.02,
                 freq: str = "day",
                 use_macd_confirmation: bool = True,
                 use_bollinger_squeeze: bool = True,
                 trend_formation_days: int = 5,
                 
                 # 新增参数：价格位置分析
                 use_price_position: bool = True,
                 price_position_weight: float = 0.15,
                 lookback_period: int = 120,
                 min_position_ratio: float = 0.3,
                 max_position_ratio: float = 0.7,
                 ideal_position_range: tuple = (0.5, 0.6),
                 
                 # 新增参数：MA120比较
                 use_ma120_comparison: bool = True,
                 ma120_weight: float = 0.12,
                 require_price_above_ma120: bool = False,
                 
                 # 层次化评分参数
                 core_conditions_required: int = 1,  # 默认只需1个核心条件
                 convergence_weight: float = 0.4,
                 slope_weight: float = 0.3,
                 breakout_weight: float = 0.15,
                 volume_weight: float = 0.1,
                 macd_weight: float = 0.05,
                 bollinger_weight: float = 0.05):
        
        super().__init__(topk=topk)
        
        # 基础参数（继承自early_trend_screening）
        self.max_convergence_days = max_convergence_days
        self.min_price_distance_to_resistance = min_price_distance_to_resistance
        self.volume_increase_ratio = volume_increase_ratio
        self.require_small_slope = require_small_slope
        self.max_slope = max_slope
        self.freq = freq
        self.use_macd_confirmation = use_macd_confirmation
        self.use_bollinger_squeeze = use_bollinger_squeeze
        self.trend_formation_days = trend_formation_days
        
        # 价格位置参数
        self.use_price_position = use_price_position
        self.price_position_weight = price_position_weight
        self.lookback_period = lookback_period
        self.min_position_ratio = min_position_ratio
        self.max_position_ratio = max_position_ratio
        self.ideal_position_range = ideal_position_range
        
        # MA120参数
        self.use_ma120_comparison = use_ma120_comparison
        self.ma120_weight = ma120_weight
        self.require_price_above_ma120 = require_price_above_ma120
        
        # 层次化评分参数
        self.core_conditions_required = core_conditions_required
        
        # 权重配置
        self.weights = {
            # 核心层
            'convergence': convergence_weight,
            'slope': slope_weight,
            
            # 新增核心条件
            'ma120': ma120_weight if use_ma120_comparison else 0,
            
            # 辅助层
            'position': price_position_weight if use_price_position else 0,
            'breakout': breakout_weight,
            'volume': volume_weight,
            
            # 确认层
            'macd': macd_weight if use_macd_confirmation else 0,
            'bollinger': bollinger_weight if use_bollinger_squeeze else 0,
        }
    
    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        """执行层次化评分策略"""
        # 初始化QLib
        self._report(progress_cb, 5, f"开始层次化评分，分析 {len(universe)} 支股票...")
        
        homePath = Path.home()
        state = get_state()
        qlib_data = Path(f"{homePath}/.qlib/qlib_data/{state.reg}_data")
        qlib_safeinit(qlib_data)
        
        # 时间范围
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if self.freq == "day":
            start_date = (datetime.datetime.now() - datetime.timedelta(days=150)).strftime("%Y-%m-%d")
        elif self.freq == "week":
            start_date = (datetime.datetime.now() - datetime.timedelta(weeks=120)).strftime("%Y-%m-%d")
        
        scores = {}
        debug_results = []
        total_len = len(universe)
        
        # 执行统计
        stats = {
            'total': 0,
            'data_ok': 0,
            'exception': 0,
            'zero_score': 0,
            'positive_score': 0
        }
        
        for i, ticker in enumerate(universe):
            stats['total'] += 1
            
            try:
                # 获取数据
                df = D.features([ticker], ['$close', '$open', '$high', '$low', '$volume'], 
                            start_time=start_date, end_time=end_date, freq=self.freq)
                
                if df.empty or len(df) < 30:
                    debug_results.append(f"{ticker}: 数据不足")
                    continue
                
                stats['data_ok'] += 1
                
                # 计算技术指标
                close_prices = df['$close'].dropna()
                high_prices = df['$high'].dropna()
                low_prices = df['$low'].dropna()
                volume = df['$volume'].dropna() if '$volume' in df.columns else None
                
                if len(close_prices) < 30:
                    continue
                
                # 层次化评分
                result = self._hierarchical_scoring(
                    close_prices, high_prices, low_prices, volume
                )
                
                if isinstance(result, tuple) and len(result) == 2:
                    total_score, score_details = result
                    
                    if total_score > 0:
                        stats['positive_score'] += 1
                        scores[ticker.upper()] = total_score
                        
                        # 调试输出
                        core_satisfied = score_details.get('core_satisfied', 0)
                        core_score = score_details.get('core_score', 0)
                        assist_score = score_details.get('assist_score', 0)
                        confirm_score = score_details.get('confirm_score', 0)
                        
                        info_str = (
                            f"{ticker}: 核心{core_satisfied}项, "
                            f"总分={total_score:.2f}, "
                            f"核心分={core_score:.1f}, "
                            f"辅助分={assist_score:.1f}, "
                            f"确认分={confirm_score:.1f}"
                        )
                        debug_results.append(info_str)
                    else:
                        stats['zero_score'] += 1
                        core_satisfied = score_details.get('core_satisfied', 0)
                        if core_satisfied < self.core_conditions_required:
                            debug_results.append(f"{ticker}: 核心条件不足 ({core_satisfied}/{self.core_conditions_required})")
                
            except Exception as e:
                stats['exception'] += 1
                debug_results.append(f"{ticker}: 异常 - {str(e)[:50]}")
                continue
            
            # 进度上报
            if (i + 1) % 20 == 0 or (i + 1) == total_len:
                progress_pct = 10 + int(80 * (i + 1) / total_len)
                self._report(progress_cb, progress_pct, f"处理中 {i+1}/{total_len}...")
        
        # 输出统计信息
        logger.info(f"策略执行统计:")
        logger.info(f"  总股票数: {stats['total']}")
        logger.info(f"  有效数据: {stats['data_ok']}")
        logger.info(f"  发生异常: {stats['exception']}")
        logger.info(f"  零分股票: {stats['zero_score']}")
        logger.info(f"  正分股票: {stats['positive_score']}")
        
        # 输出前20条调试信息
        if debug_results:
            logger.info(f"详细调试信息 (前20条):")
            for detail in debug_results[:20]:
                logger.info(f"  {detail}")
        
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
            model_name="Early Trend Hierarchical Scoring",
            universe_size=len(universe),
        )
    
    def _hierarchical_scoring(self, close_prices: pd.Series,
                            high_prices: pd.Series,
                            low_prices: pd.Series,
                            volume: Optional[pd.Series]) -> tuple:
        """层次化评分核心逻辑"""
        scores = {}
        score_details = {}
        
        # 1. 计算各条件分数
        # 核心层条件（从early_trend_screening继承）
        scores['convergence'] = self._check_ma_convergence(close_prices)
        scores['slope'] = self._check_small_slope_upward(close_prices)
        
        # 新增核心条件
        if self.use_ma120_comparison:
            scores['ma120'] = self._check_ma120_comparison(close_prices)
        else:
            scores['ma120'] = 0
        
        # 辅助层条件
        scores['breakout'] = self._check_price_breakout(close_prices, high_prices, low_prices)
        
        if self.use_price_position:
            scores['position'] = self._check_price_position(close_prices, high_prices, low_prices)
        else:
            scores['position'] = 0
        
        if volume is not None:
            scores['volume'] = self._check_volume_confirmation(close_prices, volume)
        else:
            scores['volume'] = 0
        
        # 确认层条件
        if self.use_macd_confirmation:
            scores['macd'] = self._check_macd_confirmation(close_prices)
        else:
            scores['macd'] = 0
        
        if self.use_bollinger_squeeze:
            scores['bollinger'] = self._check_bollinger_squeeze(close_prices)
        else:
            scores['bollinger'] = 0
        
        # 记录原始分数用于调试
        score_details['raw_scores'] = {k: round(v, 2) for k, v in scores.items() if v > 0}
        
        # 2. 检查核心条件满足数
        core_conditions = ['convergence', 'slope', 'ma120']
        core_satisfied = 0
        for cond in core_conditions:
            if isinstance(scores[cond], (int, float)) and scores[cond] > 0:
                core_satisfied += 1
        
        score_details['core_satisfied'] = core_satisfied
        
        # 必须满足最小核心条件数
        if core_satisfied < self.core_conditions_required:
            return 0, score_details
        
        # 3. 分层计算分数
        core_score = 0
        assist_score = 0
        confirm_score = 0
        
        for key, score in scores.items():
            if not isinstance(score, (int, float)) or score <= 0:
                continue
                
            weight = self.weights.get(key, 0)
            if weight <= 0:  # 权重为0的条件不计算
                continue
                
            weighted_score = score * weight
            
            # 分类到不同层次
            if key in ['convergence', 'slope', 'ma120']:
                core_score += weighted_score
            elif key in ['position', 'breakout', 'volume']:
                assist_score += weighted_score
            elif key in ['macd', 'bollinger']:
                confirm_score += weighted_score
        
        # 4. 计算总分（层次化加权）
        total_score = (
            core_score * 1.0 +      # 核心层保持原权重
            assist_score * 0.8 +    # 辅助层打8折
            confirm_score * 0.6     # 确认层打6折
        )
        
        # 记录详细分数
        score_details.update({
            'core_score': round(core_score, 2),
            'assist_score': round(assist_score, 2),
            'confirm_score': round(confirm_score, 2),
        })
        
        return round(total_score, 4), score_details
    
    # ============ 以下方法继承自 early_trend_screening ============
    
    def _check_ma_convergence(self, close_prices: pd.Series) -> float:
        """检查均线聚拢状态（从early_trend_screening继承）"""
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
        """检查小斜率向上（从early_trend_screening继承）"""
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
        """检查价格突破收敛区（从early_trend_screening继承）"""
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
        """检查成交量确认（从early_trend_screening继承）"""
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
    
    def _check_macd_confirmation(self, close_prices: pd.Series) -> float:
        """检查MACD零轴附近金叉（从early_trend_screening继承）"""
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
        """检查布林带收口突破（从early_trend_screening继承）"""
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
    
    def _calculate_slope(self, series: pd.Series) -> float:
        """计算线性回归斜率（从early_trend_screening继承）"""
        if len(series) < 2:
            return 0
        
        x = np.arange(len(series))
        y = series.values
        
        # 简单斜率计算
        slope = (y[-1] - y[0]) / (len(series) - 1) / y[0] if y[0] != 0 else 0
        return slope
    
    # ============ 新增方法 ============
    
    def _check_price_position(self, close_prices: pd.Series, 
                            high_prices: pd.Series, 
                            low_prices: pd.Series) -> float:
        """检查价格位置（新增）"""
        if len(close_prices) < self.lookback_period:
            return 0
        
        recent_closes = close_prices.tail(self.lookback_period)
        recent_highs = high_prices.tail(self.lookback_period)
        recent_lows = low_prices.tail(self.lookback_period)
        
        if len(recent_closes) < 10:
            return 0
        
        current_price = recent_closes.iloc[-1]
        period_high = recent_highs.max()
        period_low = recent_lows.min()
        
        if period_high == period_low or period_low == 0:
            return 0
        
        # 计算位置比率
        position_ratio = (current_price - period_low) / (period_high - period_low)
        
        # 检查是否在合理范围内
        if self.min_position_ratio <= position_ratio <= self.max_position_ratio:
            # 离理想中心越近，分数越高
            ideal_center = (self.ideal_position_range[0] + self.ideal_position_range[1]) / 2
            distance_from_ideal = abs(position_ratio - ideal_center)
            position_score = 30 * (1 - distance_from_ideal / 0.5)
            return max(position_score, 0)
        
        return 0
    
    def _check_ma120_comparison(self, close_prices: pd.Series) -> float:
        """检查MA120比较（新增）"""
        if len(close_prices) < 120:  # 降低要求，最少120天
            return 0
        
        # 计算MA120
        ma120 = close_prices.rolling(120, min_periods=60).mean()  # 最少60天
        
        if len(ma120.dropna()) < 20:  # 有20个有效MA120值即可
            return 0
        
        current_price = close_prices.iloc[-1]
        current_ma120 = ma120.iloc[-1]
        
        if current_ma120 == 0:
            return 0
        
        # 计算价格与MA120的相对位置
        price_to_ma120_ratio = (current_price - current_ma120) / current_ma120
        
        # 条件1：价格在MA120之上
        if self.require_price_above_ma120 and price_to_ma120_ratio <= -0.1:
            return 0
        
        score = 0
        
        # 评分
        if price_to_ma120_ratio > -0.1:
            if 0.15 <= price_to_ma120_ratio <= 0.25:
                score += 5
            elif 0.05 <= price_to_ma120_ratio < 0.15:
                score += 15
            elif -0.05 <= price_to_ma120_ratio < 0.05:
                score += 20
            elif price_to_ma120_ratio > -0.1:
                score += 10
            else:
                score += 0
        
        # 条件2：MA120斜率
        if len(ma120) >= 20:
            recent_ma120 = ma120.tail(20)
            ma120_slope = self._calculate_slope(recent_ma120)
            if -0.001 < ma120_slope < 0.003:
                score += (0.003-ma120_slope) * 5000
        
        return score
    
    def _report(self, cb, pct: int, msg: str) -> None:
        if cb:
            try:
                cb(pct, msg)
            except Exception:
                pass
        logger.debug(f"[{self.KEY}] {pct}% - {msg}")