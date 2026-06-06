class AdaptiveTimeWindowScorer:
    """自适应时间窗口评分器"""
    
    def __init__(self, 
                 market_regime: str = "normal",  # normal/bull/bear/volatile
                 volatility_level: float = 0.0):
        self.market_regime = market_regime
        self.volatility_level = volatility_level
    
    def get_optimal_half_life(self) -> int:
        """根据市场状态获取最优半衰期"""
        if self.market_regime == "bull":
            # 牛市：信号有效期较长
            return 7
        elif self.market_regime == "bear":
            # 熊市：信号有效期很短
            return 3
        elif self.market_regime == "volatile":
            # 高波动市：中等有效期
            return 5
        else:
            # 正常市
            return 5
    
    def calculate_adaptive_score(self,
                               signal_score: float,
                               signal_days_ago: int,
                               current_trend_strength: float) -> float:
        """
        自适应计算信号得分
        """
        # 1. 根据市场状态调整半衰期
        half_life = self.get_optimal_half_life()
        
        # 2. 时间衰减
        time_decay = 0.5 ** (signal_days_ago / half_life)
        
        # 3. 趋势强度调整：趋势越强，衰减越慢
        trend_factor = 1.0 + (current_trend_strength * 0.5)
        
        # 4. 波动率调整：高波动率下，信号有效期缩短
        volatility_factor = 1.0 - (self.volatility_level * 0.3)
        
        # 综合得分
        adjusted_score = (signal_score * time_decay * 
                         trend_factor * volatility_factor)
        
        return adjusted_score