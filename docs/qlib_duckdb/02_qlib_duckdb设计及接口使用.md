# 一、核心设计

## 设计原则（为什么按 freq 分表更好）

| 方案                | 结论                         |
| ----------------- | -------------------------- |
| 单表 + freq 字段      | ❌ 大表后性能下降                  |
| 单表 + partition    | ✅ 但 DuckDB partition 管理略繁琐 |
| ✅ **每个 freq 一张表** | ✅ 最简单、最快、最稳定               |

✅ **不同 freq 的 calendar 完全不同**  
✅ 不同 freq 的索引 / 压缩策略可独立调优  
✅ 导出 Qlib bin 时天然对齐

## 核心设计
- ✅ 多市场：`reg` 参数切换
- ✅ 多频率：按 freq 分表
- ✅ 三个 Storage (DuckDBFeatureStorage, DuckDBCalendarStorage, DuckDBInstrumentStorage) 全部实现
- ✅ 支持指数聚类

---

# 二、DuckDB 表结构（按 freq 分表）

## 1️⃣ 通用特征表模板

### 表结构总览

```sql
-- feature
feature_day
feature_5m
feature_1h

-- calendar
calendar_day
calendar_day_future

-- instrument
instrument

-- index
index_def
index_member
```

表结构sql实现
```sql
-- calendar
CREATE TABLE calendar_day (
    datetime TIMESTAMP PRIMARY KEY
);

CREATE TABLE calendar_day_future (
    datetime TIMESTAMP PRIMARY KEY
);

-- other freq calendar
--...

-- instrument
CREATE TABLE instrument (
    symbol       VARCHAR PRIMARY KEY,
    start_date   DATE,
    end_date     DATE
);

-- index
CREATE TABLE IF NOT EXISTS index_def (
	index_name    VARCHAR PRIMARY KEY, 
	index_type    VARCHAR,
	description   VARCHAR
);

-- indexMember
CREATE TABLE IF NOT EXISTS index_member (
	index_name   VARCHAR,
	symbol       VARCHAR,
	weight       DOUBLE,
	start_date   DATE,
	end_date     DATE
	PRIMARY KEY (index_name, symbol)
);

-- day
CREATE TABLE feature_day (
    symbol      VARCHAR,
    datetime    TIMESTAMP,
    open        DOUBLE, 
    high        DOUBLE, 
    low         DOUBLE, 
    close       DOUBLE, 
    volume      DOUBLE,
    PRIMARY KEY (symbol, datetime)
);

-- 5m
CREATE TABLE feature_5m (
    symbol      VARCHAR,
    datetime    TIMESTAMP,
    open        DOUBLE, 
    high        DOUBLE, 
    low         DOUBLE, 
    close       DOUBLE, 
    volume      DOUBLE,
    PRIMARY KEY (symbol, datetime)
);

-- 15m
CREATE TABLE feature_15m (
    symbol      VARCHAR,
    datetime    TIMESTAMP,
    open        DOUBLE, 
    high        DOUBLE, 
    low         DOUBLE, 
    close       DOUBLE, 
    volume      DOUBLE,
    PRIMARY KEY (symbol, datetime)
);

-- 1h
CREATE TABLE feature_1h (
    symbol      VARCHAR,
    datetime    TIMESTAMP,
    open        DOUBLE, 
    high        DOUBLE, 
    low         DOUBLE, 
    close       DOUBLE, 
    volume      DOUBLE,
    PRIMARY KEY (symbol, datetime)
);

-- 4h
CREATE TABLE feature_4h (
    symbol      VARCHAR,
    datetime    TIMESTAMP,
    open        DOUBLE, 
    high        DOUBLE, 
    low         DOUBLE, 
    close       DOUBLE, 
    volume      DOUBLE,
    PRIMARY KEY (symbol, datetime)
);

-- week
CREATE TABLE feature_week (
    symbol      VARCHAR,
    datetime    TIMESTAMP,
    open        DOUBLE, 
    high        DOUBLE, 
    low         DOUBLE, 
    close       DOUBLE, 
    volume      DOUBLE,
    PRIMARY KEY (symbol, datetime)
);
--...
-- other freq
```

---

## 接口使用方式

```python
D.set_provider(DuckDBFeatureProvider(reg="cn"))
```

---

# 三、Qlib → DuckDB 迁移脚本（按 freq）

```python
def migrate_freq(freq):

```

✅ 每个 freq 写入自己的表  
✅ 不混数据、不混 calendar

---

# 四、DuckDBFeatureStorage（按 freq 自动路由）

```python
class DuckDBFeatureStorage(FeatureStorage):
```

✅ **freq 自动映射到表**
✅ Qlib Dataset 完全无感知

---

迁移时同步写入：

```python
def migrate_calendar(freq):
```

---

# 六、增量更新（按 freq）

```python
def incremental_update(symbol, freq):
```

---

# 七、导出 Qlib bin（按 freq）

```python
from qlib.scripts.dump_bin import DumpDataAll

# 初始化转换器实例
dumper = DumpDataAll(
    csv_path="./export/5m",    # 源 CSV 数据目录
    qlib_dir="./qlib_5m",      # 输出的 Qlib 二进制数据目录
    freq="5m",                 # 数据频率
    # 可选：指定字段（若不指定则转换所有数值列）
    # include_fields="open,close,high,low,volume",
    # 可选：排除字段（如排除日期和代码列）
    # exclude_fields="date,symbol",
)

# 执行转换（dump_all 模式会处理 features 和 calendars）
dumper.dump()
```

✅ 完美符合 Qlib 的 freq 体系

---

# 八、性能调优建议（按 freq）

| freq | 数据量 | 建议 |
|---|---|---|
| day | 小 | threads=4 |
| week | 很小 | threads=2 |
| 1h / 4h | 中 | threads=6 |
| 5m / 15m | 大 | threads=8–16 |
| 内存 | 大 | SET memory_limit='32GB' |

---

# 九、最终目录结构（推荐）

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