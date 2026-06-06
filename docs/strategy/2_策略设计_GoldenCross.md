# 策略设计文档：金叉均线多头策略 (Golden Cross MA Strategy)

## 1. 策略概述

**策略名称**: 金叉均线多头策略  
**策略标识符**: `golden_cross_ma`  
**策略类型**: 技术指标选股  
**核心目标**: 捕捉均线金叉后的多头行情，选择均线多头排列且发散良好的股票

### 1.1 设计背景

均线金叉是经典的技术分析信号，但简单的金叉策略往往产生大量虚假信号。本策略在金叉基础上增加了均线排列、发散度、趋势强度等多维度过滤，提高信号质量。

### 1.2 核心思想

- **金叉信号**: 短期均线上穿长期均线，是趋势由弱转强的标志
- **多头排列**: 所有均线从上到下依次排列（5>10>20>60），表明中长期趋势向上
- **均线发散**: 均线间距逐渐扩大，表明趋势在加速
- **时间衰减**: 金叉信号越新越有效，随时间推移信号衰减

---

## 2. 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `topk` | int | 20 | 选取得分最高的股票数量 |
| `require_volume_confirmation` | bool | True | 是否要求成交量确认 |
| `max_cross_days` | int | 10 | 金叉最大发生天数（10天内） |
| `min_price_above_ma5` | bool | True | 股价是否在5日线上 |
| `freq` | str | "day" | 数据频率(day/week) |
| `golden_cross_type` | str | "510" | 金叉类型(510/1020/520) |
| `require_all_ma_up` | bool | False | 是否要求所有均线向上 |
| `divergence_weight` | float | 1.5 | 发散度权重 |
| `min_ma_distance` | float | 0.01 | 最小均线间距(1%) |
| `cross_decay_enabled` | bool | True | 是否启用金叉时间衰减 |
| `cross_decay_half_life` | int | 3 | 金叉衰减半衰期（天） |
| `divergence_decay_enabled` | bool | True | 是否启用发散度时间衰减 |
| `divergence_start_days` | int | 5 | 发散开始计时的天数 |

---

## 3. 策略核心逻辑

### 3.1 总体评分框架

策略从四个维度对股票进行评估：

| 维度 | 权重 | 说明 |
|------|------|------|
| 金叉强度 | 40% | 核心判据，包括角度和间距 |
| 均线排列 | 30% | 多头排列质量 |
| 发散度 | 20%×权重 | 趋势加速程度 |
| 趋势强度 | 10% | 综合趋势判断 |

### 3.2 金叉信号检查

#### 3.2.1 金叉类型选择

| 类型 | 短期均线 | 长期均线 | 适用场景 |
|------|----------|----------|----------|
| 510 | 5日 | 10日 | 短线灵敏信号 |
| 1020 | 10日 | 20日 | 中短线平衡 |
| 520 | 5日 | 20日 | 中线稳健信号 |

#### 3.2.2 金叉判断逻辑

```python
def _check_golden_cross_signal(self, ma5, ma10, ma20, ma60):
    # 确定检查的金叉类型
    if self.golden_cross_type == "510":
        short_ma, long_ma = ma5, ma10
    elif self.golden_cross_type == "1020":
        short_ma, long_ma = ma10, ma20
    else:
        short_ma, long_ma = ma5, ma20
    
    # 在最近30天内查找金叉
    for i in range(2, min(30, len(short_ma))):
        if short_ma.iloc[-i] > long_ma.iloc[-i] and \
           short_ma.iloc[-i-1] <= long_ma.iloc[-i-1]:
            # 找到金叉
            return True, i-1  # (是否找到, 多少天前)
    
    return False, None
```

#### 3.2.3 金叉强度计算

**原理**: 金叉的角度越陡峭（短期均线斜率与长期均线斜率差越大），信号越强。

```python
def _calculate_cross_strength(self, short_cur, long_cur, short_prev, long_prev, days_since_cross):
    # 金叉角度 = 短期均线斜率 - 长期均线斜率
    short_slope = (short_cur - short_prev) / short_prev
    long_slope = (long_cur - long_prev) / long_prev
    cross_angle = short_slope - long_slope
    
    # 交叉后的间距
    cross_gap = (short_cur - long_cur) / long_cur
    
    # 综合强度
    strength = cross_angle * 100 + cross_gap * 50
    
    # 应用动量衰减
    if days_since_cross > 0:
        strength *= 0.5 ** (days_since_cross / 3)  # 半衰期3天
    
    return max(strength, 0)
```

### 3.3 均线排列评分

#### 3.3.1 多头排列判断

**原理**: 所有均线从上到下依次排列，表明市场整体向上。

**判断条件**:
```
ma5 > ma10 > ma20 > ma60
```

#### 3.3.2 排列质量计算

1. **间距均匀性**: 均线间距应该逐渐扩大
2. **方向一致性**: 所有均线向上

```python
def _calculate_alignment_score(self, ma5, ma10, ma20, ma60):
    # 检查多头排列
    is_aligned = ma5.iloc[-1] > ma10.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1]
    
    if not is_aligned:
        return 0
    
    # 计算间距
    gap_510 = (ma5.iloc[-1] - ma10.iloc[-1]) / ma10.iloc[-1]
    gap_1020 = (ma10.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1]
    gap_2060 = (ma20.iloc[-1] - ma60.iloc[-1]) / ma60.iloc[-1]
    
    # 间距应该为正且逐渐扩大
    alignment_score = (gap_510 + gap_1020 + gap_2060) * 100 if all(g > 0 for g in [gap_510, gap_1020, gap_2060]) else 0
    
    return max(alignment_score, 0)
```

### 3.4 发散度计算

#### 3.4.1 发散度定义

**原理**: 均线发散（间距扩大）表明趋势在加速，是健康上涨的特征。

#### 3.4.2 发散度计算

```python
def _calculate_divergence_score(self, ma5, ma10, ma20, ma60):
    # 当前间距
    gap_510_cur = (ma5.iloc[-1] - ma10.iloc[-1]) / ma10.iloc[-1]
    gap_1020_cur = (ma10.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1]
    
    # 5天前间距
    gap_510_prev = (ma5.iloc[-6] - ma10.iloc[-6]) / ma10.iloc[-6]
    gap_1020_prev = (ma10.iloc[-6] - ma20.iloc[-6]) / ma20.iloc[-6]
    
    # 发散度 = 当前间距 - 之前间距
    divergence_510 = (gap_510_cur - gap_510_prev) * 100
    divergence_1020 = (gap_1020_cur - gap_1020_prev) * 100
    
    # 综合发散度
    divergence_score = (divergence_510 + divergence_1020) * 10
    
    return max(divergence_score, 0)
```

### 3.5 趋势强度计算

#### 3.5.1 评估维度

1. **价格位置**: 股价在各均线上方的数量
2. **均线斜率**: 各均线的上涨角度

```python
def _calculate_trend_strength(self, close_prices, ma5, ma10, ma20, ma60):
    trend_score = 0
    
    # 价格在均线上方
    price = close_prices.iloc[-1]
    above_count = sum([
        price > ma5.iloc[-1],
        price > ma10.iloc[-1],
        price > ma20.iloc[-1],
        price > ma60.iloc[-1]
    ])
    trend_score += above_count * 25
    
    # 均线斜率
    if len(ma5) >= 6:
        ma5_slope = (ma5.iloc[-1] - ma5.iloc[-5]) / ma5.iloc[-5]
        ma10_slope = (ma10.iloc[-1] - ma10.iloc[-10]) / ma10.iloc[-10]
        trend_score += (ma5_slope + ma10_slope) * 100
    
    return max(trend_score, 0)
```

---

## 4. 时间衰减机制

### 4.1 金叉时间衰减

**原理**: 金叉信号越新越有效，随时间推移信号强度衰减。

```python
def _calculate_cross_decay_weight(self, cross_days_ago):
    if not self.cross_decay_enabled or cross_days_ago <= 0:
        return 1.0
    
    # 半衰期3天
    return 0.5 ** (cross_days_ago / self.cross_decay_half_life)
```

### 4.2 发散度时间衰减

**原理**: 发散开始后一段时间内最有效，过久则趋势可能衰竭。

```python
def _estimate_divergence_start(self, ma5, ma10, ma20, ma60):
    # 估计发散开始的天数
    for i in range(2, min(20, len(ma5))):
        gap_510_prev = (ma5.iloc[-i] - ma10.iloc[-i]) / ma10.iloc[-i]
        gap_510_cur = (ma5.iloc[-1] - ma10.iloc[-1]) / ma10.iloc[-1]
        
        if gap_510_cur > gap_510_prev * 1.5:
            return i
    
    return 0
```

---

## 5. 综合评分计算

### 5.1 评分公式

```python
def _calculate_comprehensive_score(self, cross_strength, alignment_score, 
                                  divergence_score, trend_strength):
    # 权重
    weights = {
        'cross': 0.4,
        'alignment': 0.3,
        'divergence': 0.2 * self.divergence_weight,
        'trend': 0.1
    }
    
    # 标准化（各维度归一化到0-100）
    cross_norm = min(cross_strength / 10.0, 1.0) * 100
    alignment_norm = min(alignment_score / 200.0, 1.0) * 100
    divergence_norm = min(divergence_score / 50.0, 1.0) * 100
    trend_norm = min(trend_strength / 200.0, 1.0) * 100
    
    # 加权求和
    total = (
        cross_norm * weights['cross'] +
        alignment_norm * weights['alignment'] +
        divergence_norm * weights['divergence'] +
        trend_norm * weights['trend']
    )
    
    return round(total, 4)
```

---

## 6. 数据获取与处理

### 6.1 数据源

- 使用QLib的`D.features`接口获取股票数据
- 字段：`$close`, `$volume`
- 需要至少65个交易日数据（计算60日均线）

### 6.2 时间范围

| 频率 | 时间跨度 |
|------|----------|
| 日线 | 最近120天 |
| 周线 | 最近120周 |

---

## 7. 策略输出

### 7.1 返回格式

```python
StrategyResult(
    strategy_key="golden_cross_ma",
    strategy_name="金叉均线多头策略(510金叉)",
    scores=pd.Series,  # 所有满足条件的股票得分
    topk_tickers=list,  # 得分最高的topk支股票
    model_name="Golden Cross MA(day/week)",
    universe_size=int,  # 原始股票池大小
)
```

### 7.2 调试日志

策略运行时会输出详细的调试信息：

```
AAPL: ✓ 金叉(5-10金叉,2天前), 排列=85.32, 发散=42.15, 趋势=68.20, 总分=72.58
GOOGL: ✗ 无近期金叉 (最近金叉:15天前)
```

---

## 8. 集成到选股页面

### 8.1 注册策略

```python
from strategies.qlib_strategy import STRATEGY_REGISTRY

STRATEGY_REGISTRY["golden_cross_ma"] = {
    "class": GoldenCrossMAStrategy,
    "name": "金叉均线多头策略",
    "description": "均线金叉+多头排列+发散度选股",
    "params": {
        "topk": 20,
        "require_volume_confirmation": True,
        "golden_cross_type": "510",
        # ...
    }
}
```

### 8.2 UI卡片定义

```python
{
    "key": "golden_cross_ma",
    "name": "金叉均线多头策略",
    "icon": "✨",
    "description": "5-10-20-60均线金叉多头排列",
    "params": {
        "golden_cross_type": {"type": "select", "options": ["510", "1020", "520"]},
        "max_cross_days": {"type": "spin", "min": 5, "max": 30, "default": 10},
        # ...
    }
}
```

---

## 9. 使用示例

### 9.1 基本使用

```python
from strategies.screening.golden_cross_screening import GoldenCrossMAStrategy

strategy = GoldenCrossMAStrategy(topk=20)
result = strategy.run(universe=["AAPL", "GOOGL", "MSFT"])
print(result.topk_tickers)
```

### 9.2 自定义金叉类型

```python
# 10-20日均线金叉（更稳健）
strategy = GoldenCrossMAStrategy(
    golden_cross_type="1020",
    max_cross_days=15,
    divergence_weight=2.0
)
```

---

## 10. 注意事项

1. **数据要求**: 需要至少65天数据，不足的股票会被跳过
2. **金叉类型选择**: 510适合短线，1020/520适合中线
3. **时间窗口**: `max_cross_days`控制金叉的新旧程度，过久信号可能失效
4. **参数调优**: 发散度权重和衰减半衰期可根据市场环境调整
5. **风险控制**: 金叉信号可能失败，建议结合止损策略使用
