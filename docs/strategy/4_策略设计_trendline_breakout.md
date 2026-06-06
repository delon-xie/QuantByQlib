# 策略设计文档：趋势线突破策略 (Trendline Breakout Strategy)

## 1. 策略概述

**策略名称**: 趋势线突破策略  
**策略标识符**: `trendline_breakout`  
**策略类型**: 技术指标选股  
**核心目标**: 识别下降趋势线突破信号，捕捉趋势反转机会

### 1.1 设计背景

下降趋势线是技术分析中重要的阻力位，价格突破下降趋势线往往预示着趋势由弱转强。本策略通过识别下降趋势线，结合成交量确认和回踩验证，捕捉高质量的突破信号。

### 1.2 核心思想

- **趋势线识别**: 通过高点识别和线性回归绘制下降趋势线
- **突破确认**: 价格突破趋势线且突破幅度超过阈值
- **成交量配合**: 突破时成交量放大确认有效性
- **回踩验证**: 突破后价格回踩趋势线不跌破，确认突破有效
- **质量评分**: 从多个维度评估突破质量，筛选优质信号

---

## 2. 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `topk` | int | 20 | 选取得分最高的股票数量 |
| `trendline_points` | int | 20 | 用于绘制趋势线的点数 |
| `breakthrough_threshold` | float | 0.03 | 突破阈值（3%） |
| `volume_confirmation_ratio` | float | 1.5 | 成交量确认倍数 |
| `consolidation_days` | int | 3 | 突破后整理天数 |
| `retest_confirmation` | bool | True | 是否需要回踩确认 |
| `min_trend_duration` | int | 10 | 最小趋势持续时间 |
| `freq` | str | "day" | 数据频率(day/week) |

---

## 3. 策略核心逻辑

### 3.1 总体流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     趋势线突破策略流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 识别下降趋势                                                 │
│     ├── 寻找近期高点                                             │
│     ├── 使用线性回归绘制趋势线                                    │
│     └── 确认趋势线斜率为负                                        │
│                                                                  │
│  2. 检查突破信号                                                 │
│     ├── 计算当前价格与趋势线距离                                  │
│     ├── 判断突破幅度是否超过阈值                                  │
│     └── 检查成交量是否放大                                        │
│                                                                  │
│  3. 验证突破质量                                                 │
│     ├── 检查突破后整理                                           │
│     ├── 检查是否有回踩确认                                        │
│     └── 计算突破质量分数                                          │
│                                                                  │
│  4. 输出结果                                                     │
│     ├── 按分数排序                                               │
│     └── 返回topk支股票                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 下降趋势识别

**原理**: 通过寻找价格高点，使用线性回归绘制下降趋势线。

**判断逻辑**:
1. 在指定时间范围内寻找局部高点
2. 使用最后3个高点绘制趋势线
3. 计算趋势线斜率，必须为负（下降趋势）

```python
def _identify_downtrend(self, close_prices: pd.Series, high_prices: pd.Series):
    # 1. 寻找近期高点
    peak_indices = self._find_price_peaks(high_prices, lookback=self.trendline_points)
    
    # 2. 使用最后几个高点绘制趋势线
    trend_points = []
    for idx in peak_indices[-min(3, len(peak_indices)):]:
        trend_points.append((idx, high_prices.iloc[idx]))
    
    # 3. 计算趋势线斜率（线性回归）
    x_coords = [p[0] for p in trend_points]
    y_coords = [p[1] for p in trend_points]
    
    # 最小二乘法
    x_mean = np.mean(x_coords)
    y_mean = np.mean(y_coords)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_coords, y_coords))
    denominator = sum((x - x_mean) ** 2 for x in x_coords)
    
    if denominator != 0:
        slope = numerator / denominator
        return slope, trend_points, peak_indices
    
    return None
```

### 3.3 高点识别

**原理**: 识别局部最大值作为趋势线绘制点。

**判断条件**:
```
当前价格 > 前一日价格  且  当前价格 > 后一日价格
```

```python
def _find_price_peaks(self, prices: pd.Series, lookback: int = 20) -> List[int]:
    """寻找价格高点"""
    peaks = []
    
    for i in range(1, min(lookback, len(prices) - 1)):
        idx = len(prices) - i - 1
        if (prices.iloc[idx] > prices.iloc[idx-1] and 
            prices.iloc[idx] > prices.iloc[idx+1]):
            peaks.append(idx)
    
    return sorted(peaks)
```

### 3.4 趋势线计算

**原理**: 使用线性插值计算趋势线在指定位置的值。

**计算方法**:
- 使用最后两个点计算趋势线
- 直线方程：y = kx + b

```python
def _calculate_trendline_value(self, trend_points: List[tuple], x_position: int):
    """计算趋势线在指定位置的值"""
    if len(trend_points) < 2:
        return None
    
    # 选择最新的两个点计算趋势线
    p1 = trend_points[-2]
    p2 = trend_points[-1]
    
    # 直线方程：y = kx + b
    if p2[0] != p1[0]:
        k = (p2[1] - p1[1]) / (p2[0] - p1[0])
        b = p1[1] - k * p1[0]
        return k * x_position + b
    
    return None
```

### 3.5 突破检查

**原理**: 检查当前价格是否突破趋势线且突破幅度超过阈值。

**判断条件**:
```python
break_ratio = (当前价格 - 趋势线值) / |趋势线值|
break_ratio > breakthrough_threshold  # 默认3%
```

```python
latest_price = close_prices.iloc[-1]
trendline_value = self._calculate_trendline_value(trend_points, len(close_prices) - 1)

break_ratio = (latest_price - trendline_value) / abs(trendline_value)

if break_ratio <= self.breakthrough_threshold:
    return None  # 未突破或突破幅度不足
```

### 3.6 成交量确认

**原理**: 突破时成交量放大，确认突破有效性。

**判断条件**:
```python
当前成交量 > 最近5日平均成交量 × volume_confirmation_ratio
```

```python
if volume is not None and len(volume) >= 5:
    avg_volume = volume.iloc[-5:].mean()
    if volume.iloc[-1] < avg_volume * self.volume_confirmation_ratio:
        return None  # 成交量不足
```

### 3.7 突破质量评分

**评分维度**:

| 维度 | 权重 | 说明 |
|------|------|------|
| 突破幅度 | 50% | 突破幅度越大，信号越强 |
| 趋势强度 | 20% | 原下降趋势越陡，突破意义越大 |
| 波动率蓄势 | 10% | 突破前低波动率蓄势 |
| 突破K线形态 | 10% | 中阳线或大阳线突破 |
| 成交量配合 | 10% | 成交量放大确认 |

```python
def _calculate_breakout_score(self, break_ratio, trend_slope, close_prices, volume):
    score = 0
    
    # 1. 突破幅度（最多50分）
    score += min(break_ratio * 100, 50)
    
    # 2. 原趋势强度（最多20分）
    trend_strength = abs(trend_slope) * 10000
    score += min(trend_strength, 20)
    
    # 3. 突破前蓄势（最多10分）
    if len(close_prices) >= 20:
        recent_volatility = close_prices.pct_change().std() * 100
        if recent_volatility < 2:  # 低波动率蓄势
            score += 10
    
    # 4. 突破K线形态（最多10分）
    if len(close_prices) >= 3:
        today_change = (close_prices.iloc[-1] - close_prices.iloc[-2]) / close_prices.iloc[-2]
        if today_change > 0.02:  # 涨幅超过2%
            score += 10
    
    # 5. 成交量配合（最多10分）
    if volume is not None and len(volume) >= 5:
        vol_ratio = volume.iloc[-1] / volume.iloc[-5:].mean()
        if vol_ratio > 1.5:
            score += 10
    
    return max(score, 0)
```

### 3.8 整理检查

**原理**: 突破后价格应保持在趋势线上方。

**判断条件**:
```python
突破后N天内，价格 > 趋势线值
```

```python
def _check_consolidation(self, close_prices, trendline_value, consolidation_days):
    """检查突破后的整理"""
    if len(close_prices) < consolidation_days + 1:
        return True
    
    for i in range(1, consolidation_days + 1):
        if close_prices.iloc[-i] < trendline_value:
            return False
    
    return True
```

### 3.9 回踩验证

**原理**: 突破后价格回踩趋势线但不跌破，确认突破有效。

**判断条件**:
```python
价格接近趋势线（1%以内）但未跌破
```

```python
def _check_retest(self, close_prices, trendline_value):
    """检查是否回踩趋势线"""
    if len(close_prices) < 5:
        return False
    
    for i in range(1, min(5, len(close_prices) - 1)):
        idx = -i - 1
        if idx >= 0:
            price_diff = abs(close_prices.iloc[idx] - trendline_value) / trendline_value
            if price_diff < 0.01:  # 1%以内视为回踩
                return True
    
    return False
```

---

## 4. 数据获取与处理

### 4.1 数据源

- 使用QLib的`D.features`接口获取股票数据
- 字段：`$close`, `$high`, `$low`, `$volume`
- 需要至少 `trendline_points + 10` 个交易日数据

### 4.2 时间范围

| 频率 | 时间跨度 |
|------|----------|
| 日线 | 最近60天 |
| 周线 | 最近26周 |

---

## 5. 策略输出

### 5.1 返回格式

```python
StrategyResult(
    strategy_key="trendline_breakout",
    strategy_name="趋势线突破策略",
    scores=pd.Series,  # 所有满足条件的股票得分
    topk_tickers=list,  # 得分最高的topk支股票
    model_name="Trendline Breakout Strategy",
    universe_size=int,  # 原始股票池大小
)
```

### 5.2 调试日志

策略运行时会输出详细的调试信息：

```
AAPL: ✓ 突破3.5% 斜率-0.0023, 分数=65.32
GOOGL: ✓ 突破4.2% 斜率-0.0035, 分数=72.15
MSFT: ✗ 未突破（突破幅度1.8%）
```

---

## 6. 集成到选股页面

### 6.1 注册策略

```python
from strategies.qlib_strategy import STRATEGY_REGISTRY

STRATEGY_REGISTRY["trendline_breakout"] = {
    "class": TrendlineBreakoutStrategy,
    "name": "趋势线突破策略",
    "description": "下降趋势线突破+成交量确认+回踩验证",
    "params": {
        "topk": 20,
        "trendline_points": 20,
        "breakthrough_threshold": 0.03,
        # ...
    }
}
```

### 6.2 UI卡片定义

```python
{
    "key": "trendline_breakout",
    "name": "趋势线突破策略",
    "icon": "📈",
    "description": "识别下降趋势线突破信号",
    "params": {
        "breakthrough_threshold": {
            "type": "spin",
            "min": 0.01,
            "max": 0.10,
            "step": 0.01,
            "default": 0.03
        },
        "volume_confirmation_ratio": {
            "type": "spin",
            "min": 1.0,
            "max": 3.0,
            "step": 0.1,
            "default": 1.5
        },
        "retest_confirmation": {
            "type": "checkbox",
            "default": True
        },
        # ...
    }
}
```

---

## 7. 使用示例

### 7.1 基本使用

```python
from strategies.screening.trendline_breakout_screening import TrendlineBreakoutStrategy

strategy = TrendlineBreakoutStrategy(topk=20)
result = strategy.run(universe=["AAPL", "GOOGL", "MSFT"])
print(result.topk_tickers)
```

### 7.2 自定义参数

```python
strategy = TrendlineBreakoutStrategy(
    topk=30,
    breakthrough_threshold=0.05,  # 突破5%
    volume_confirmation_ratio=2.0,  # 成交量放大2倍
    retest_confirmation=True,
    consolidation_days=5
)
```

### 7.3 周线模式

```python
strategy = TrendlineBreakoutStrategy(
    freq="week",
    trendline_points=26,  # 半年高点
    breakthrough_threshold=0.04
)
```

---

## 8. 注意事项

1. **数据要求**: 需要至少 `trendline_points + 10` 天数据，不足的股票会被跳过
2. **突破阈值**: `breakthrough_threshold` 控制突破的严格程度，过高可能错过机会，过低可能产生虚假信号
3. **成交量确认**: `volume_confirmation_ratio` 应根据市场流动性调整
4. **回踩验证**: 开启 `retest_confirmation` 可提高信号质量，但会错过快速上涨的股票
5. **风险控制**: 趋势线突破信号可能失败，建议结合止损策略使用
6. **市场环境**: 在震荡市中，趋势线突破信号可能频繁失效
7. **趋势线稳定性**: 高点识别和趋势线计算对参数敏感，建议使用默认值

---

## 9. 策略优化建议

### 9.1 高点识别优化

**问题**: 当前仅用局部最大值，可能遗漏真正的趋势高点。

**改进方案**: 考虑高点之间的距离和相对高度，保留重要高点。

### 9.2 趋势线计算优化

**问题**: 当前仅用最后2个点计算趋势线，稳定性差。

**改进方案**: 使用线性回归（最小二乘法）计算趋势线，提高稳定性。

### 9.3 评分权重优化

**问题**: 当前评分权重（50/20/10/10/10）未经验证。

**改进方案**: 通过回测优化各维度权重，提高策略表现。

---

## 10. 适用场景

| 市场环境 | 适用性 | 说明 |
|----------|--------|------|
| 明确下降趋势 | ★★★ | 趋势线清晰，突破信号可靠 |
| 震荡市 | ★☆☆ | 趋势线不稳定，信号质量差 |
| 上升趋势 | ★★☆ | 可能产生虚假突破信号 |
| 反转初期 | ★★★ | 捕捉趋势反转的最佳时机 |

---

## 11. 风险提示

1. **虚假突破**: 价格可能短暂突破后回落
2. **趋势线误判**: 高点识别错误导致趋势线绘制错误
3. **成交量陷阱**: 放量突破可能是主力出货
4. **滞后性**: 突破信号往往在趋势已经形成后才出现
5. **参数敏感**: 策略表现对参数设置较为敏感