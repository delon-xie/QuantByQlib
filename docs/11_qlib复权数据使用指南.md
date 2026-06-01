# QLib 复权数据使用指南

## 一、概述

在使用 QLib 进行A股数据分析时，复权处理是一个关键问题。由于A股分红、送股频繁，价格会出现断层，复权处理可以消除这些断层，保证K线连续性。本指南详细说明 QLib 中复权数据的处理机制及正确使用方法。

---

## 二、QLib 数据字段说明

### 2.1 核心字段

| 字段 | 说明 | 是否复权 |
|------|------|----------|
| `$open` | 开盘价 | **可能已复权** |
| `$high` | 最高价 | **可能已复权** |
| `$low` | 最低价 | **可能已复权** |
| `$close` | 收盘价 | **可能已复权** |
| `$volume` | 成交量 | 不受复权影响 |
| `$factor` | 复权因子 | 用于计算复权价格 |
| `$adjclose` | 调整后收盘价 | A股特有，已复权 |

### 2.2 复权因子说明

复权因子 (`$factor`) 是计算复权价格的关键：
- **公式**：`adjclose = close * factor`
- **因子值含义**：
  - `factor = 1.0`：未复权或原始价格
  - `factor < 1.0`：通常表示已进行前复权
  - `factor > 1.0`：通常表示已进行后复权

---

## 三、前复权 vs 后复权

### 3.1 概念区别

| 类型 | 定义 | 特点 | 适用场景 |
|------|------|------|----------|
| **前复权** | 以当前价格为基准，向前调整历史价格 | 最新价格与实际一致 | 技术分析、指标计算 |
| **后复权** | 以历史价格为基准，向后调整当前价格 | 保持历史价格不变 | 长期收益分析 |

### 3.2 计算公式

```python
# 前复权（Forward Adjustment）
# 价格 = 原始价格 * 复权因子
forward_adj_price = original_price * factor

# 后复权（Backward Adjustment）  
# 价格 = 原始价格 / 复权因子
backward_adj_price = original_price / factor
```

---

## 四、QLib 数据加载与复权处理

### 4.1 数据加载示例

```python
from qlib.data import D

# 获取基础 OHLCV 数据（可能已复权）
df = D.features(
    ["SH600123"],
    fields=["$open", "$high", "$low", "$close", "$volume", "$factor"],
    start_time="2026-01-01",
    end_time="2026-06-01"
)
```

### 4.2 判断数据是否已复权

```python
# 检查复权因子
first_factor = df["$factor"].iloc[0]

if first_factor == 1.0:
    print("数据未复权，使用原始价格")
elif first_factor < 1.0:
    print(f"数据已前复权，因子: {first_factor:.4f}")
elif first_factor > 1.0:
    print(f"数据已后复权，因子: {first_factor:.4f}")
```

### 4.3 原始价格还原

当 QLib 返回的数据已被复权，但您需要原始价格时：

```python
# 如果数据已被前复权（factor < 1），还原为原始价格
if first_factor < 1.0:
    df["$open"] = df["$open"] / df["$factor"]
    df["$high"] = df["$high"] / df["$factor"]
    df["$low"] = df["$low"] / df["$factor"]
    df["$close"] = df["$close"] / df["$factor"]
```

### 4.4 主动应用复权

如果数据未复权，但您需要复权价格：

```python
# 应用前复权
df["adj_open"] = df["$open"] * df["$factor"]
df["adj_high"] = df["$high"] * df["$factor"]
df["adj_low"] = df["$low"] * df["$factor"]
df["adj_close"] = df["$close"] * df["$factor"]
```

---

## 五、本项目的复权处理策略

### 5.1 默认行为

本项目在 `ui/pages/chart_page.py` 的 `_get_qlib_ohlcv` 函数中实现了自动复权检测和处理：

```python
def _get_qlib_ohlcv(ticker: str, period_days: int = 365, use_adj: bool = False) -> pd.DataFrame:
    """
    从 QLib 加载 K 线数据
    
    Args:
        ticker: 股票代码
        period_days: 数据周期天数
        use_adj: 是否使用复权数据（默认 False，使用原始价格）
    """
    # 实现逻辑：
    # 1. 总是获取 $factor 字段
    # 2. 如果 use_adj=False 且数据已复权（factor < 1），自动还原为原始价格
    # 3. 如果 use_adj=True，确保数据已应用复权因子
```

### 5.2 使用示例

```python
# 获取原始价格（默认行为）
df_original = _get_qlib_ohlcv("600123.SS")

# 获取复权价格
df_adjusted = _get_qlib_ohlcv("600123.SS", use_adj=True)
```

### 5.3 调试信息

函数会输出调试信息帮助追踪数据状态：

```
[DEBUG] Checking data with factor=0.9592
[DEBUG] Current close: 6.89, factor: 0.9592
[DEBUG] Factor < 1, reverting to original prices...
[DEBUG] Latest data - Date: 2026-05-30, Open: 6.61, Close: 6.58
```

---

## 六、注意事项

### 6.1 数据一致性

- **跨平台对比**：与其他平台（如东方财富、同花顺）对比时，务必确保两边使用相同的复权方式
- **A股建议**：A股建议使用原始价格或前复权，避免与其他平台数据差异

### 6.2 指标计算

- **使用复权数据**：计算技术指标（如 MA、MACD、RSI）时，建议使用复权数据以保证连续性
- **使用原始数据**：计算收益率、波动率等统计指标时，建议使用原始价格

### 6.3 回测注意

在进行策略回测时：
- **因子计算**：使用复权数据
- **交易信号**：使用原始价格（实际交易价格）
- **收益统计**：使用复权数据（反映真实收益）

---

## 七、常见问题

### Q1：为什么 QLib 返回的价格与其他平台不一致？

**原因**：QLib 默认返回的可能是复权后的数据，而其他平台可能显示原始价格。

**解决方案**：使用 `use_adj=False` 参数获取原始价格。

### Q2：复权因子在哪里查看？

```python
# 查看复权因子
print(df["$factor"].describe())

# 查看特定日期的因子
print(df.loc["2026-05-29", "$factor"])
```

### Q3：如何验证复权处理是否正确？

```python
# 验证：原始价格 * 因子 ≈ 复权后价格
df["calc_adj_close"] = df["$close"] * df["$factor"]
print(df[["$close", "$factor", "$adjclose", "calc_adj_close"]].head())
```

---

## 八、参考资料

1. QLib 官方文档：[https://qlib.readthedocs.io](https://qlib.readthedocs.io)
2. A股复权规则：上海证券交易所、深圳证券交易所官方说明
3. 本项目数据差异说明：`docs/09_各交易市场特征数据差异.md`

---

**版本**：v1.0  
**更新日期**：2026年6月  
**适用范围**：QuantByQlib 项目及所有使用 QLib 进行 A股数据分析的场景
