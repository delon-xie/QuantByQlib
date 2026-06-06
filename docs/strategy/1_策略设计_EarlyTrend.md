# 策略设计文档：趋势早期识别策略 (Early Trend Formation Strategy)

## 1. 策略概述

**策略名称**: 趋势早期识别策略  
**策略标识符**: `early_trend`  
**策略类型**: 技术指标选股  
**核心目标**: 在趋势启动早期识别潜在机会，避免追高，捕捉启动点

### 1.1 设计背景

传统的趋势跟踪策略往往在趋势已经形成后才发出信号，此时风险收益比已经不理想。本策略通过识别均线聚拢、价格收敛等特征，在趋势形成早期发出信号，帮助投资者以更优的价格介入潜在的趋势行情。

### 1.2 核心思想

- **均线聚拢理论**: 当多条均线从发散状态逐渐聚拢时，往往预示着趋势即将启动
- **小斜率启动**: 真正的趋势启动初期，价格上涨斜率较小且平稳，而非陡峭
- **量价配合**: 趋势启动需要成交量确认，但要求温和放量而非突发放量
- **多维确认**: 结合均线、MACD、布林带等多个维度综合判断

---

## 2. 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `topk` | int | 20 | 选取得分最高的股票数量 |
| `max_convergence_days` | int | 20 | 均线最大聚拢天数 |
| `min_price_distance_to_resistance` | float | 0.05 | 距离阻力位最小距离(5%) |
| `volume_increase_ratio` | float | 1.2 | 成交量放大倍数(1.2倍) |
| `require_small_slope` | bool | True | 是否要求小斜率 |
| `max_slope` | float | 0.02 | 最大日斜率(2%) |
| `freq` | str | "day" | 数据频率(day/week) |
| `use_macd_confirmation` | bool | True | 是否使用MACD确认 |
| `use_bollinger_squeeze` | bool | True | 是否使用布林带收口 |
| `trend_formation_days` | int | 5 | 趋势形成天数 |

---

## 3. 策略核心逻辑

### 3.1 总体评分框架

策略从四个维度对股票进行评估，每个维度有不同的权重：

| 维度 | 权重 | 说明 |
|------|------|------|
| 均线聚拢状态 | 40% | 最重要，核心判据 |
| 小斜率向上 | 30% | 判断启动特征 |
| 价格突破收敛区 | 20% | 确认突破有效性 |
| 成交量确认 | 10% | 量价配合验证 |

### 3.2 均线聚拢状态检查

**原理**: 均线从发散到聚拢的过程意味着市场筹码从分散到集中，为后续趋势启动积蓄能量。

**判断逻辑**:
1. 计算5日、10日、20日均线的当前间距
2. 要求间距小于3%（高度聚拢）
3. 检查最近N天间距是否在缩小（从发散到聚拢）

**评分标准**:
- 间距缩小程度越好，得分越高
- 基础分50分 + 改善程度加分（最高50分）

```python
def _check_ma_convergence(self, close_prices: pd.Series) -> float:
    ma5 = close_prices.rolling(5).mean()
    ma10 = close_prices.rolling(10).mean()
    ma20 = close_prices.rolling(20).mean()
    
    # 计算均线间距
    distance_5_10 = abs(ma5.iloc[-1] - ma10.iloc[-1]) / ma10.iloc[-1]
    distance_10_20 = abs(ma10.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1]
    distance_5_20 = abs(ma5.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1]
    
    # 均线应高度聚拢（距离小于3%）
    if any(d > 0.03 for d in [distance_5_10, distance_10_20, distance_5_20]):
        return 0
    
    # 检查是否从发散到聚拢
    prev_5_10 = abs(ma5.iloc[-self.max_convergence_days] - ma10.iloc[-self.max_convergence_days]) / ma10.iloc[-self.max_convergence_days]
    convergence_improvement = prev_5_10 - distance_5_10
    
    if convergence_improvement > 0:
        return 50 + min(convergence_improvement * 1000, 50)
    
    return 0
```

### 3.3 小斜率向上检查

**原理**: 真正的趋势启动初期，价格上涨应该是缓慢且持续的，而非急剧上涨。急剧上涨往往是短期炒作，不可持续。

**判断逻辑**:
1. 计算最近5天的价格斜率
2. 要求斜率大于0但小于2%（小斜率）
3. 检查斜率是否在逐渐变大（从平缓到加速）

**评分标准**:
- 斜率变化越大，得分越高
- 基础分30分 + 斜率变化加分（最高20分）

### 3.4 价格突破收敛区检查

**原理**: 当价格在收敛区间内震荡后向上突破，说明整理结束，趋势开始。

**判断逻辑**:
1. 计算最近10天的最高价和最低价
2. 取波动区间的中点
3. 判断当前价格是否处于上半区

**评分标准**:
- 价格位置越高（在上半区），得分越高
- 得分范围：20-40分

### 3.5 成交量确认

**原理**: 趋势启动需要成交量配合，但温和放量更健康。

**判断逻辑**:
1. 计算最近5天平均成交量
2. 与前10天平均成交量对比
3. 要求放量比例在1.1-2.0倍之间

**评分标准**:
- 放量比例越接近1.5倍，得分越高
- 得分范围：10-20分

---

## 4. MACD确认机制

### 4.1 零轴附近金叉

**原理**: MACD在零轴附近发生金叉是趋势由弱转强的信号，比远离零轴的金叉更有意义。

**判断条件**:
1. DIF在零轴附近（-0.5%到0.5%）
2. 最近5天内发生金叉
3. MACD柱状线由负转正

**加分**: 满足条件加15分

### 4.2 布林带收口突破

**原理**: 布林带收口意味着波动率压缩，随后往往伴随趋势行情。

**判断条件**:
1. 布林带带宽缩小20%以上
2. 价格突破中轨向上

**加分**: 满足条件加10-20分

---

## 5. 数据获取与处理

### 5.1 数据源

- 使用QLib的`D.features`接口获取股票数据
- 字段：`$close`, `$open`, `$high`, `$low`, `$volume`
- 需要至少30个交易日数据

### 5.2 时间范围

| 频率 | 时间跨度 |
|------|----------|
| 日线 | 最近120天 |
| 周线 | 最近120周 |

---

## 6. 策略输出

### 6.1 返回格式

```python
StrategyResult(
    strategy_key="early_trend",
    strategy_name="趋势早期识别策略",
    scores=pd.Series,  # 所有满足条件的股票得分
    topk_tickers=list,  # 得分最高的topk支股票
    model_name="Early Trend Formation",
    universe_size=int,  # 原始股票池大小
)
```

### 6.2 得分排序

得分由四个维度加权计算，分数范围0-100，按降序排列。

---

## 7. 集成到选股页面

### 7.1 注册策略

```python
from strategies.qlib_strategy import STRATEGY_REGISTRY

STRATEGY_REGISTRY["early_trend"] = {
    "class": EarlyTrendFormationStrategy,
    "name": "趋势早期识别策略",
    "description": "识别均线聚拢后的趋势启动点",
    "params": {
        "topk": 20,
        "max_convergence_days": 20,
        "volume_increase_ratio": 1.2,
        # ...
    }
}
```

### 7.2 UI卡片定义

在`screening_page.py`中添加策略卡片：

```python
{
    "key": "early_trend",
    "name": "趋势早期识别策略",
    "icon": "📈",
    "description": "均线聚拢 + 小斜率启动 + 量价配合",
    "params": {...}
}
```

---

## 8. 使用示例

### 8.1 基本使用

```python
from strategies.screening.early_trend_screening import EarlyTrendFormationStrategy

strategy = EarlyTrendFormationStrategy(topk=20)
result = strategy.run(universe=["600000.SH", "000001.SZ"])
print(result.topk_tickers)
```

### 8.2 自定义参数

```python
strategy = EarlyTrendFormationStrategy(
    topk=30,
    max_convergence_days=15,
    volume_increase_ratio=1.5,
    use_macd_confirmation=True,
    use_bollinger_squeeze=True,
)
```

---

## 9. 注意事项

1. **数据充足性**: 策略需要至少30个交易日数据，数据不足的股票会被跳过
2. **参数调优**: `max_slope`和`volume_increase_ratio`可根据市场环境调整
3. **频率选择**: 日线适合短线操作，周线适合中线趋势跟踪
4. **风险控制**: 早期趋势信号可能失败，建议结合止损策略使用
