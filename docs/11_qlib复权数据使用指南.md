# QLib 复权数据使用指南

## 一、概述

在使用 QLib 进行数据分析时，复权处理是一个关键问题。由于分红、送股频繁，价格会出现断层，复权处理可以消除这些断层，保证K线连续性。本指南详细说明 QLib 中复权数据的处理机制及正确使用方法。

---

## 二、QLib 数据字段说明

### 2.1 核心字段

| 字段 | 说明 | 是否复权 |
|------|------|----------|
| `$open` | 开盘价 | **取决于数据源** |
| `$high` | 最高价 | **取决于数据源** |
| `$low` | 最低价 | **取决于数据源** |
| `$close` | 收盘价 | **取决于数据源** |
| `$volume` | 成交量 | 不受复权影响 |
| `$factor` | 复权因子 | 用于计算复权价格 |
| `$adjclose` | 调整后收盘价 | A股特有，已复权 |

### 2.2 复权因子说明

复权因子 (`$factor`) 是计算复权价格的关键：

> **重要提示**：复权因子的计算方向取决于数据源！

| 数据源 | factor 计算方式 | 说明 |
|--------|----------------|------|
| **yfinance 采集** | `factor = Adj Close / Close` | factor > 1 表示有分红送股 |
| **investment_data** | `factor = Close / Adj Close` | factor < 1 表示有分红送股 |

---

## 三、QLib 数据归一化机制

### 3.1 什么是归一化

QLib 的 bin 格式文件存储的是**归一化索引**而非日期。数据文件结构如下：

```
二进制格式：[start_idx: float32][v0: float32][v1: float32]...
  - start_idx：股票在日历中的起始偏移量（对应 calendars/day.txt 的行号，从0开始）
  - v0..vN：OHLCV / factor 值（float32，NaN 表示无数据）
```

**示例**：假设 `calendars/day.txt` 第 7300 行是 2026-01-02
- 某股票从 2026-01-02 开始有数据
- 则该股票的 `start_idx = 7300`
- 2026-01-02 的价格存储在第 2 个 float32（index 1）

### 3.2 归一化的优势

| 优势 | 说明 |
|------|------|
| **存储高效** | 只需存储偏移量和数值，无需存储日期 |
| **查询快速** | 根据日期计算偏移量，直接定位数据位置 |
| **跨市场统一** | 不同市场使用同一日历文件，保证数据对齐 |

### 3.3 数据写入流程

```
原始数据（yfinance / investment_data）
    ↓
按日历对齐数据
    ↓
计算复权因子 factor
    ↓
写入 bin 文件（start_idx + 数值数组）
```

---

## 四、不同数据源的数据结构

### 4.1 yfinance 采集数据（本项目）

当使用本项目的 `yfinance_collector.py` 采集数据时：

```
yfinance: Close=6.85, Adj Close=7.14
       ↓
factor = Adj Close / Close = 7.14 / 6.85 ≈ 1.0417
       ↓
按日历归一化，存储到 QLib:
  - close = 6.85 (原始价格)
  - factor = 1.0417 (复权因子)
       ↓
读取时:
  - 未复权: close = 6.85 (直接使用)
  - 后复权: close × factor = 6.85 × 1.0417 ≈ 7.14
```

**关键代码**（`yfinance_collector.py`）：
```python
# 计算复权因子
df["factor"] = df["Adj Close"] / df["Close"]
df["factor"] = df["factor"].fillna(1.0).clip(0.01, 100.0)

# 按日历对齐后写入
# 二进制格式：[start_idx: float32][v0: float32][v1: float32]...
```

### 4.2 investment_data 导出数据（官方数据）

**investment_data 是已经归一化好的标准 QLib bin 格式文件**，直接可用，无需额外处理。

```
investment_data 原始数据: close=6.85, adjclose=89.41
       ↓
investment_data 已完成归一化处理
       ↓
存储到 bin 文件:
  - close = 89.41 (复权后价格!)
  - factor = 0.0766 (还原因子!)
       ↓
读取时:
  - 未复权: close / factor = 89.41 / 0.0766 ≈ 6.85
  - 后复权: close = 89.41 (直接使用)
```

**注意**：investment_data 的 `factor` 计算方向与 yfinance 相反：
- yfinance：`factor = Adj Close / Close`
- investment_data：`factor = Close / Adj Close`

### 4.3 关键差异总结

| 数据源 | QLib close | factor 含义 | 未复权计算 | 后复权计算 |
|--------|------------|-------------|------------|------------|
| **yfinance** | 原始价格 | 复权因子 | 直接使用 | `close × factor` |
| **investment_data** | 复权后价格 | 还原因子 | `close / factor` | 直接使用 |

### 4.4 区域与数据源的对应关系

本项目根据股票代码后缀自动推断区域，并使用相应的数据源：

| 区域标识 | 股票代码后缀 | 数据源 | 说明 |
|----------|-------------|--------|------|
| **cn** | `.SH`, `.SS`, `.SZ`, `.BJ` | investment_data | A股官方数据（已归一化） |
| **hk** | `.HK` | yfinance | 港股数据（需归一化） |
| **us** | `.US` | yfinance | 美股数据（需归一化） |

### 4.5 各区域复权处理差异

| 区域 | 数据源 | `close` 存储类型 | 未复权计算 | 后复权计算 |
|------|--------|-----------------|------------|------------|
| **CN** | investment_data | 复权后价格 | `close / factor` | 直接使用 |
| **HK** | yfinance | 原始价格 | 直接使用 | `close × factor` |
| **US** | yfinance | 原始价格 | 直接使用 | `close × factor` |

---

## 五、本项目的复权处理策略

### 5.1 自动检测与适配

本项目在 `ui/pages/chart_page.py` 的 `_get_qlib_ohlcv` 函数中实现了智能复权处理：

```python
def _get_qlib_ohlcv(ticker: str, period_days: int = 365, use_adj: bool = False) -> pd.DataFrame:
    """
    从 QLib 加载 K 线数据，自动适配不同数据源的复权格式
    
    Args:
        ticker: 股票代码
        period_days: 数据周期天数
        use_adj: 是否使用复权数据（默认 False，使用原始价格）
    """
```

### 5.2 核心处理逻辑

```python
# ================================================================
# 不同区域数据源的复权处理差异
# ================================================================
# 
# | 区域 | 数据源 | close 存储 | 未复权计算 | 后复权计算 |
# |------|--------|-----------|------------|------------|
# | CN   | investment_data | 复权后价格 | close / factor | 直接使用 |
# | HK   | yfinance        | 原始价格   | 直接使用    | close * factor |
# | US   | yfinance        | 原始价格   | 直接使用    | close * factor |
# ================================================================

if reg == "cn":
    # CN 区域: investment_data 数据源
    # close 存储的是复权后价格，factor 是还原因子
    if use_adj:
        # 后复权：QLib 的 close 已经是复权价格，直接使用
        pass
    else:
        # 未复权：需要除以 factor 还原为原始价格
        valid_factor = df["$factor"].replace(0, 1.0)
        df["$open"] = df["$open"] / valid_factor
        df["$high"] = df["$high"] / valid_factor
        df["$low"] = df["$low"] / valid_factor
        df["$close"] = df["$close"] / valid_factor
else:
    # HK/US 区域: yfinance 数据源
    # close 存储的是原始价格，factor 是复权因子
    if use_adj:
        # 后复权：需要乘以 factor 计算复权后价格
        df["$open"] = df["$open"] * df["$factor"]
        df["$high"] = df["$high"] * df["$factor"]
        df["$low"] = df["$low"] * df["$factor"]
        df["$close"] = df["$close"] * df["$factor"]
    else:
        # 未复权：QLib 存储的就是原始价格，直接使用
        pass
### 4.3 使用示例

```python
# 获取原始价格（默认行为）
df_original = _get_qlib_ohlcv("600123.SS")  # use_adj=False

# 获取复权价格
df_adjusted = _get_qlib_ohlcv("600123.SS", use_adj=True)
```

### 5.4 调试信息

函数会输出调试信息帮助追踪数据状态：

```
[DEBUG] Calculating original prices (close / factor), factor range: 1.0417 ~ 1.0417
[DEBUG] Current close (before restore) - first: 7.14, last: 7.14
[DEBUG] Original close (after restore) - first: 6.85, last: 6.85
```

---

## 五、数据验证示例

### 5.1 验证复权处理是否正确

```python
import pandas as pd

# 模拟 investment_data 的 QLib 数据（600123 5月29日）
df = pd.DataFrame({
    "$close": [7.1357],   # QLib存储的复权后价格
    "$factor": [1.041704],  # 还原因子
})

# 未复权处理
df["$close"] = df["$close"] / df["$factor"]
print(f"还原后的原始价格: {df['$close'].iloc[0]:.2f}")  # 应为 6.85
```

### 5.2 验证结果

| 股票 | 期望收盘价 | 计算结果 | 匹配度 |
|------|-----------|----------|--------|
| 600123.SH | 6.85 | 6.85 | ✅ 完美匹配 |
| 600666.SH | 4.56 | 4.56 | ✅ 完美匹配 |
| 000002.SZ | 3.55 | 3.55 | ✅ 完美匹配 |

---

## 七、注意事项

### 7.1 数据一致性

- **跨平台对比**：与其他平台对比时，务必确保两边使用相同的复权方式
- **数据源确认**：明确当前使用的是 yfinance 采集数据还是 investment_data 导出数据

### 6.2 指标计算

- **使用复权数据**：计算技术指标（如 MA、MACD、RSI）时，建议使用复权数据以保证连续性
- **使用原始数据**：计算收益率、波动率等统计指标时，建议使用原始价格

### 6.3 回测注意

在进行策略回测时：
- **因子计算**：使用复权数据
- **交易信号**：使用原始价格（实际交易价格）
- **收益统计**：使用复权数据（反映真实收益）

### 6.4 数据质量检查

定期检查数据文件是否存在异常值：

```python
# 检查异常大值（QLib 默认填充值约为 2.247e+307）
for col in ["open", "high", "low", "close"]:
    if col in df.columns:
        df.loc[df[col] > 1e300, col] = pd.NA  # 将异常值设为 NaN

# 删除价格为 NaN 的行
df = df.dropna(subset=["close", "open", "high", "low"])
```

---

## 七、常见问题

### Q1：为什么 QLib 返回的价格与其他平台不一致？

**原因**：取决于数据源的复权处理方式。investment_data 导出的数据中，`close` 字段存储的是复权后价格，而其他平台可能显示原始价格。

**解决方案**：使用 `use_adj=False` 参数获取原始价格（本项目已自动处理）。

### Q2：如何判断当前使用的是哪种数据源？

```python
# 检查 factor 值的范围
min_factor = df["$factor"].min()
max_factor = df["$factor"].max()

if max_factor > 1.1:
    print("可能是 yfinance 采集数据（factor > 1）")
elif min_factor < 0.9:
    print("可能是 investment_data 数据（factor < 1）")
else:
    print("因子接近 1，无法确定数据源")
```

### Q3：复权因子在哪里查看？

```python
# 查看复权因子
print(df["$factor"].describe())

# 查看特定日期的因子
print(df.loc["2026-05-29", "$factor"])
```

### Q4：如何验证复权处理是否正确？

```python
# 验证：复权后价格 / 因子 ≈ 原始价格（investment_data）
df["calc_original"] = df["$close"] / df["$factor"]
print(df[["$close", "$factor", "calc_original"]].head())
```

---

## 九、参考资料

1. QLib 官方文档：[https://qlib.readthedocs.io](https://qlib.readthedocs.io)
2. A股复权规则：上海证券交易所、深圳证券交易所官方说明
3. investment_data 项目：[https://github.com/chenditc/investment_data](https://github.com/chenditc/investment_data)
4. 本项目数据差异说明：`docs/09_各交易市场特征数据差异.md`

---

**版本**：v3.0  
**更新日期**：2026年6月  
**适用范围**：QuantByQlib 项目及所有使用 QLib 进行 A股数据分析的场景  
**重要更新**：
1. 新增 QLib 数据归一化机制说明（第三章）
2. 修正 investment_data 数据源的复权处理逻辑
3. 明确 investment_data 是已归一化的标准 QLib bin 格式文件
4. 区分 yfinance（需归一化）和 investment_data（已归一化）的处理差异
