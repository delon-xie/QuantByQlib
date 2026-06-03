# strategies/screening/ma10_screening.py
import qlib
from qlib.config import REG_CN
from qlib.data import D
import pandas as pd
import numpy as np
from typing import Optional, Callable, List
from loguru import logger
from strategies.base_strategy import BaseStrategy, StrategyResult


class MA10TurnUpScreenStrategy(BaseStrategy):
    """MA10抬头选股策略 —— 放宽条件版本"""
    
    KEY = "ma10_turnup"
    NAME = "MA10抬头策略"
    TOPK = 20
    
    def __init__(self, 
                 topk: Optional[int] = None,
                 require_vol_confirm: bool = False,  # 默认关闭，先测试基本功能
                 require_price_above_ma10: bool = False,  # 默认关闭
                 turn_up_mode: str = "relaxed",  # 默认用放宽模式
                 min_turn_up_weeks: int = 1,
                 max_turn_up_weeks: int = 4,
                 freq: str = "day",
                 time_decay_enabled: bool = True,  # 是否启用时间衰减
                 decay_half_life: int = 5,  # 半衰期（天）
                 decay_type: str = "exponential"):  # 衰减类型
        super().__init__(topk=topk)
        self.require_vol_confirm = require_vol_confirm
        self.require_price_above_ma10 = require_price_above_ma10
        self.turn_up_mode = turn_up_mode
        self.min_turn_up_weeks = min_turn_up_weeks
        self.max_turn_up_weeks = max_turn_up_weeks
        self.freq = freq
        self.time_decay_enabled = time_decay_enabled
        self.decay_half_life = decay_half_life
        self.decay_type = decay_type
    
    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        """带调试信息的运行"""
        self._report(progress_cb, 10, f"开始调试模式，分析 {len(universe)} 支股票...")
        
        from core.qlibhelper import qlib_safeinit
        from core.app_state import get_state
        from pathlib import Path
        homePath = Path.home()
        state = get_state()
        qlib_data = Path(f"{homePath}/.qlib/qlib_data/{state.reg}_data")
        qlib_safeinit(qlib_data)
        
        from qlib.data import D
        import datetime
        
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if self.freq == "day":
            start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
        elif self.freq == "week":
            start_date = (datetime.datetime.now() - datetime.timedelta(weeks=120)).strftime("%Y-%m-%d")
        
        debug_results = []
        scores = {}
        total_len = max(1,len(universe))
        for i, ticker in enumerate(universe[:]):
            try:
                # 获取数据
                df = D.features([ticker], ['$close', '$volume'], 
                            start_time=start_date, end_time=end_date, freq=self.freq)
                
                if df.empty:
                    debug_results.append(f"{ticker}: 无数据")
                    continue
                
                close_prices = df['$close'].dropna()
                
                if len(close_prices) < 15:
                    debug_results.append(f"{ticker}: 数据不足 ({len(close_prices)}天)")
                    continue
                
                ma10 = close_prices.rolling(10).mean()
                
                # 计算各条件
                cur_ma = ma10.iloc[-1]
                prev_ma = ma10.iloc[-2]
                prev2_ma = ma10.iloc[-3]
                
                # 检查严格条件
                strict_condition = (cur_ma > prev_ma) and (prev_ma <= prev2_ma)
                
                # 检查放宽条件（已抬头1-4周）
                recent_ma = ma10.iloc[-8:].values if len(ma10) >= 8 else ma10.values
                relaxed_condition = False
                turn_up_weeks = 0
                
                for j in range(1, len(recent_ma)):
                    if recent_ma[j] > recent_ma[j-1]:
                        turn_up_weeks += 1
                    else:
                        turn_up_weeks = 0
                
                relaxed_condition = 1 <= turn_up_weeks <= 4
                
                debug_results.append(f"{ticker}: MA10[{len(ma10)}] "
                                f"当前={cur_ma:.2f}, 上周={prev_ma:.2f}, 上上周={prev2_ma:.2f} "
                                f"严格条件={'✓' if strict_condition else '✗'} "
                                f"放宽条件={'✓' if relaxed_condition else f'✗({turn_up_weeks}周)'}")
                
                # 如果满足放宽条件，给分
                if relaxed_condition:
                    strength = (cur_ma - prev_ma) / prev_ma if prev_ma != 0 else 0
                    scores[ticker.upper()] = round(strength * 1000, 4)
                    
            except Exception as e:
                debug_results.append(f"{ticker}: 错误 - {str(e)}")
                continue
            
            if (i + 1) % 10 == 0:
                self._report(progress_cb, 20 + int(60 * i / total_len), f"调试中 {i+1}/{total_len}...")
        
        # 输出调试信息
        for result in debug_results:
            logger.info(result)
        
        self._report(progress_cb, 90, f"调试完成，{len(scores)}支满足条件")
        
        if scores:
            scores_series = pd.Series(scores, name="score").sort_values(ascending=False)
            topk = min(self.topk, len(scores_series))
            topk_tickers = scores_series.head(topk).index.tolist()
        else:
            scores_series = pd.Series(dtype=float)
            topk_tickers = []
        
        self._report(progress_cb, 100, f"选出 {len(topk_tickers)} 支")
        
        return StrategyResult(
            strategy_key=self.KEY + "_debug",
            strategy_name=self.NAME + "(调试版)",
            scores=scores_series,
            topk_tickers=topk_tickers,
            model_name="MA10 Turn-Up (调试模式)",
            universe_size=min(50, len(universe)),
        )
    
    def _calculate_ma10_score_extended(self, ticker: str, start_date: str, end_date: str) -> Optional[float]:
        """计算放宽条件的MA10分数"""
        from qlib.data import D
        
        if ticker.startswith(('SH', 'SZ', 'sh', 'sz')):
            qlib_ticker = ticker[2:].lower()
        else:
            qlib_ticker = ticker.lower()
        
        try:
            # 获取更多天的数据，用于计算已抬头周数
            df = D.features([qlib_ticker], ['$close', '$volume'], 
                          start_time=start_date, end_time=end_date, freq='day')
            
            if df.empty or len(df) < 15:  # 需要至少15天数据
                return None
            
            close_prices = df['$close'].dropna()
            volume = df['$volume'].dropna() if '$volume' in df.columns else None
            
            if len(close_prices) < 15:
                return None
            
            # 计算MA10
            ma10 = close_prices.rolling(10).mean()
            
            # 根据不同的抬头模式判断
            is_turn_up = False
            turn_up_strength = 0
            
            if self.turn_up_mode == "strict":
                # 原始严格模式：必须刚刚抬头
                is_turn_up, turn_up_strength = self._check_strict_turn_up(ma10)
                
            elif self.turn_up_mode == "relaxed":
                # 放宽模式：可以已抬头1-4周
                is_turn_up, turn_up_strength = self._check_relaxed_turn_up(ma10)
                
            elif self.turn_up_mode == "trend":
                # 趋势模式：MA10整体向上趋势
                is_turn_up, turn_up_strength = self._check_trend_turn_up(ma10)
            
            if not is_turn_up:
                return None
            
            # 可选过滤：成交量确认
            if self.require_vol_confirm and volume is not None and len(volume) >= 5:
                vol_ma5 = volume.rolling(5).mean()
                if len(vol_ma5) > 0 and volume.iloc[-1] <= vol_ma5.iloc[-1]:
                    return None
            
            # 可选过滤：股价在MA10之上
            if self.require_price_above_ma10:
                if close_prices.iloc[-1] <= ma10.iloc[-1]:
                    return None
            
            # 打分：基于抬头强度
            score = self._calculate_score(turn_up_strength, ma10, close_prices)
            return score
            
        except Exception as e:
            logger.debug(f"计算{ticker}失败: {e}")
            return None
    
    def _check_strict_turn_up(self, ma10: pd.Series) -> tuple[bool, float]:
        """严格模式：本周刚刚抬头"""
        if len(ma10) < 3:
            return False, 0
        
        cur_ma = ma10.iloc[-1]
        prev_ma = ma10.iloc[-2]
        prev2_ma = ma10.iloc[-3]
        
        # 条件：cur > prev 且 prev <= prev2
        is_turn_up = (cur_ma > prev_ma) and (prev_ma <= prev2_ma)
        strength = (cur_ma - prev_ma) / prev_ma if prev_ma != 0 else 0
        
        return is_turn_up, strength
    
    def _calculate_time_decay_weight(self, signal_days_ago: int) -> float:
        """计算时间衰减权重"""
        if not self.time_decay_enabled or signal_days_ago <= 0:
            return 1.0
        
        if self.decay_type == "exponential":
            # 指数衰减
            return 0.5 ** (signal_days_ago / self.decay_half_life)
        elif self.decay_type == "linear":
            # 线性衰减
            max_days = self.decay_half_life * 2
            return max(0, 1 - (signal_days_ago / max_days))
        else:
            return 0.5 ** (signal_days_ago / self.decay_half_life)
    
    def _check_relaxed_turn_up(self, ma10: pd.Series) -> tuple[bool, float, int]:
        """放宽模式：已抬头若干周"""
        if len(ma10) < 8:  # 至少看最近8周
            return False, 0, 0
        
        # 取最近N周的MA10值
        lookback = min(self.max_turn_up_weeks + 2, len(ma10))
        recent_ma = ma10.iloc[-lookback:].values
        
        # 检查是否连续上升若干周
        turn_up_weeks = 0
        total_strength = 0
        
        for i in range(1, len(recent_ma)):
            if recent_ma[i] > recent_ma[i-1]:
                turn_up_weeks += 1
                strength = (recent_ma[i] - recent_ma[i-1]) / recent_ma[i-1] if recent_ma[i-1] != 0 else 0
                total_strength += strength
            else:
                # 如果下降，重新计数
                turn_up_weeks = 0
                total_strength = 0
        
        # 判断是否在指定周数范围内
        is_turn_up = (self.min_turn_up_weeks <= turn_up_weeks <= self.max_turn_up_weeks)
        avg_strength = total_strength / turn_up_weeks if turn_up_weeks > 0 else 0
        
        # 计算抬头开始的天数
        if turn_up_weeks > 0:
            # 向上回溯查找抬头开始点
            turn_up_start_days_ago = 0
            for i in range(1, len(ma10)):
                if ma10.iloc[-i] > ma10.iloc[-i-1]:
                    turn_up_start_days_ago += 1
                else:
                    break
            
            # 计算时间衰减权重
            decay_weight = self._calculate_time_decay_weight(turn_up_start_days_ago)
            
            # 调整强度
            adjusted_strength = avg_strength * decay_weight
            
            return is_turn_up, adjusted_strength, turn_up_start_days_ago
        
        return False, 0, 0
    
    def _check_trend_turn_up(self, ma10: pd.Series) -> tuple[bool, float]:
        """趋势模式：MA10整体向上趋势"""
        if len(ma10) < 8:
            return False, 0
        
        # 使用线性回归判断趋势
        x = np.arange(len(ma10))
        slope, intercept = np.polyfit(x, ma10.values, 1)
        
        # 趋势向上且最近在加速
        is_trend_up = slope > 0
        
        # 计算最近3周的加速度
        if len(ma10) >= 4:
            recent_slope1 = (ma10.iloc[-1] - ma10.iloc[-2]) / ma10.iloc[-2] if ma10.iloc[-2] != 0 else 0
            recent_slope2 = (ma10.iloc[-2] - ma10.iloc[-3]) / ma10.iloc[-3] if ma10.iloc[-3] != 0 else 0
            acceleration = recent_slope1 - recent_slope2
        else:
            acceleration = 0
        
        return is_trend_up, slope + acceleration
    
    def _calculate_score(self, turn_up_strength: float, ma10: pd.Series, close_prices: pd.Series) -> float:
        """计算综合分数"""
        # 1. 抬头强度基础分，斜率越陡，信号越强
        """
        计算逻辑：
        turn_up_strength= (当前MA10 - 前一日MA10) / 前一日MA10
        本质是MA10的日变化率，反映了抬头的"陡峭程度"
        乘以1000是缩放因子，避免分数过小
        技术意义：
        斜率越陡，信号越强
        例如：MA10从10元涨到10.1元（1%涨幅），得分 = 0.01 × 1000 = 10分
        这个维度占总分的主导权重（1000倍放大）
        """
        strength_score = turn_up_strength * 1000
        
        # 2. 股价相对MA10位置加分
        """
        计算逻辑：
        price_position= 股价相对于MA10的偏离百分比
        正数表示股价在MA10之上，负数表示在MA10之下
        乘以500是缩放因子，权重低于抬头强度
        技术意义：
        确认突破有效性：股价在MA10之上，确认上涨趋势
        反映强势程度：偏离越大，股票越强势
        安全边际：股价远离均线，回调有支撑
        例如：股价12元，MA10=10元，偏离20%，得分 = 0.2 × 500 = 100分
        """
        price_position = (close_prices.iloc[-1] - ma10.iloc[-1]) / ma10.iloc[-1] if ma10.iloc[-1] != 0 else 0
        position_score = price_position * 500  # 股价高于MA10越多越好
        
        # 3. 趋势稳定性加分
        """
        计算逻辑：
        计算最近4个交易日MA10的日变化率序列
        计算这个序列的标准差，衡量波动性
        波动越小（标准差越小），稳定性越高
        用1减去标准差，确保稳定性与分数正相关
        乘以200是缩放因子
        技术意义：
        识别健康上涨：平稳上升的MA10比剧烈波动的更可靠
        过滤虚假信号：排除MA10剧烈波动的股票
        反映趋势质量：稳步上涨优于暴涨暴跌
        例如：最近4天MA10变化率为[1.2%, 1.1%, 0.9%, 1.0%]，标准差=0.12%，稳定性=0.9988，得分≈200分
        """

        if len(ma10) >= 5:
            recent_changes = ma10.pct_change().dropna().tail(4)
            stability = 1 - recent_changes.std()  # 波动越小越稳定
            stability_score = stability * 200
        else:
            stability_score = 0
        
        # 综合分数
        total_score = strength_score + position_score + stability_score
        
        return round(total_score, 4)
    
    def _report(self, cb, pct: int, msg: str) -> None:
        if cb:
            try:
                cb(pct, msg)
            except Exception:
                pass
        logger.debug(f"[{self.KEY}] {pct}% - {msg}")