class SignalLifecycleScorer:
    """信号生命周期评分器"""
    
    def __init__(self, signal_type: str = "ma10_turnup"):
        self.signal_type = signal_type
        
    def calculate_lifecycle_score(self, 
                                signal_days_ago: int,
                                signal_strength: float,
                                trend_acceleration: float = 0) -> float:
        """
        根据信号的生命周期阶段计算综合分数
        
        信号生命周期阶段：
        1. 初期 (0-2天): 权重最高，潜力最大
        2. 中期 (3-7天): 权重中等，趋势确认
        3. 后期 (>7天): 权重降低，风险增加
        """
        # 1. 时间衰减分量
        if signal_days_ago <= 2:
            time_weight = 1.0
        elif signal_days_ago <= 5:
            time_weight = 0.7
        elif signal_days_ago <= 10:
            time_weight = 0.4
        else:
            time_weight = 0.2
        
        # 2. 信号强度分量
        strength_weight = min(signal_strength * 10, 1.0)
        
        # 3. 趋势加速度分量（越加速越好）
        acceleration_weight = 1.0 + min(trend_acceleration, 0.5)
        
        # 4. 成交量确认分量（可选）
        volume_weight = 1.0  # 可根据实际情况调整
        
        # 综合得分
        base_score = signal_strength * 1000
        lifecycle_score = (base_score * time_weight * 
                         strength_weight * acceleration_weight * volume_weight)
        
        return lifecycle_score