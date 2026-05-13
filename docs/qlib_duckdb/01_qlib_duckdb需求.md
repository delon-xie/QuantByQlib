## 一、总体目标

构建一个 **Qlib 的 DuckDB 后端数据系统**，实现：

- ✅ **替代 Qlib 默认文件系统（bin）**
- ✅ **统一承载多市场、多频率数据**
- ✅ **高性能分析 + 兼容 Qlib 上层 API**
- ✅ **支持双向数据流动（Qlib ↔ DuckDB）**
- ✅ **可工程化、可发布为 pip 包**

---

## 二、数据范围与频率需求

### ✅ 市场
- A 股
- 美股
- 港股
- 台股
- 日股
- 韩股
- 加密货币（Crypto）

### ✅ 频率（freq）
| 类型  | 频率                           |
| --- | ---------------------------- |
| 基准  | day (1d)                     |
| 低频  | week(1w) / 3day(3d)          |
| 中频  | 12h / 8h / 6h / 4h / 2h / 1h |
| 高频  | 30m / 15m / 5m / 3m / 1m     |
| 超高频 | 1s                           |

✅ **freq 是核心维度，不是附加字段**

---

## 三、存储设计需求（核心）

### ✅ 表组织方式
- ✅ **按 市场(reg) 分库（强烈优选）**
- ✅ **按 频率(freq) 分表（强烈优选）**
- ❌ 不采用单表 + freq 字段
- ✅ 每张表对应一个 freq

**库**示例：
```
cn_data.duckdb
us_data.duckdb
bt_data.duckdb
```

**feature表**示例：
```
feature_day
feature_3d
feature_week
...
feature_4h
feature_1h
feature_15m
feature_5m
```

### ✅ 表结构（统一）

```sql
(symbol, datetime, open, high, low, close, volume)
```

✅ 长表设计  
✅ 便于扩展新特征  
✅ 非常适合 DuckDB 的向量化执行

---

## 四、Qlib 集成需求

### ✅ 兼容性目标
- ✅ 实现 `CalendarStorage`
- ✅ 实现 `InstrumentStorage`
- ✅ 实现 `FeatureStorage`
- ✅ 支持 `D.features()` / `Dataset`
- ✅ 支持 Qlib 的 **Calendar（交易日历）**​ 和 **Instrument（标的池）**
- ✅ 严格遵循 Qlib 0.97 库

### ✅ 接口要求
- 按 `symbol + freq + time range` 组合过滤读取
- 行为与原生 Qlib Storage 一致
- 对上层代码 **零侵入**

### ✅ 外部依赖
- tqdm 
- qlib 0.97+
- duckdb
- loguru

---

### 五、指数 / 自定义指数支持（新增）

- ✅ `instruments/*.txt`
  - 文件名 = index_id
  - 每行第一个 `\t` 字段 = symbol
- ✅ 导入 `index_def` / `index_member`
- ✅ 支持 csi300 / csi500 / 自定义指数

---

### 六、Calendar 双向同步（新增）

- ✅ `{freq}.txt`：历史日历
- ✅ `{freq}_future.txt`：未来日历（可选）
- ✅ DuckDB 表：
  - `calendar_{freq}`
  - `calendar_{freq}_future`

---

## 七、数据迁移需求

### ✅ 初始迁移
- ✅ 从 Qlib 原始 bin 文件导入
- ✅ 支持多 freq 批量迁移
- ✅ 自动对齐 Qlib calendar
- ✅ 从 Qlib 原始 `instruments/*.txt` 双向同步 `index_member`
- - ✅ 从 Qlib 原始 `calendars/*.txt` 双向同步 `calendars` 支持 future 未来日历

### ✅ 增量更新
- ✅ 按 symbol / freq 增量补数
- ✅ 支持分钟级更新
- ✅ 可定时任务调度

---

## 八、导出与互操作性需求

### ✅ DuckDB → Qlib bin
- ✅ 按 freq 导出 CSV
- ✅ 调用 `qlib.data.dump_bin`
- ✅ 生成标准 Qlib 离线数据目录

### ✅ 用途
- 回测
- 实盘
- 分发数据

---

## 九、性能与规模需求

### ✅ 数据规模预期
| freq     | 规模  |
| -------- | --- |
| day      | 百万级 |
| 1h / 4h  | 千万级 |
| 5m / 15m | 亿级  |

### ✅ 性能目标
- 单因子读取：< 20ms
- 多因子 join：< 100ms
- 全市场回测明显快于 bin

### ✅ 调优手段
- DuckDB `threads`
- `memory_limit`
- 分区 / 索引
- 批量写入

---

## 十、工程化与交付形态

### ✅ 项目形态
- ✅ Python package
- ✅ pip installable
- ✅ 命名为 `qlib-duckdb`

### ✅ 模块划分
```
qlib_duckdb/
├── __init__.py       # 包管理
├── constants.py      # 常量管理
├── connection.py     # duckdb 连接及连接池管理
├── calendar.py       # calendar 管理
├── instrument.py     # 股票池管理
├── index_import.py   # 指数及自定义管理
├── storage.py        # FeatureStorage、CalendarStorage、InstrumentStorage 实现
├── provider.py       # Qlib Provider
├── migrate.py        # Qlib → DuckDB
├── incremental.py    # 增量更新
└── export.py         # DuckDB → Qlib bin
```

---

## 十一、非功能性需求

| 维度   | 要求                   |
| ---- | -------------------- |
| 稳定性  | 支持长期运行               |
| 可维护性 | 表结构清晰                |
| 可扩展性 | 新增 freq / market 低成本 |
| 可观测性 | 日志 + 统计              |
| 可测试性 | 单元测试 + benchmark     |

---

## 十二、一句话总结

> **qlib‑duckdb 是一个面向多市场、多频率、分析型量化场景的 Qlib 数据后端，用 DuckDB 替代 bin 文件，实现高性能、可扩展、可双向导出的量化数据基础设施。**