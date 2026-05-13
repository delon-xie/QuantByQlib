"""
常量定义
"""

# 支持的市场
SUPPORTED_MARKETS = ["cn", "us", "hk", "tw", "jp", "kr", "bt"]

# 支持的频率
SUPPORTED_FREQS = [
    "day", "week", "3day",  # 低频
    "1h", "4h", "2h", "6h", "8h", "12h",  # 中频
    "1m", "3m", "5m", "15m", "30m",  # 高频
    "1s"  # 超高频
]

# 表名前缀
FEATURE_TABLE_PREFIX = "feature_"
CALENDAR_TABLE_PREFIX = "calendar_"
CALENDAR_FUTURE_SUFFIX = "_future"

# 基础特征字段
BASE_FIELDS = ["open", "high", "low", "close", "volume"]
BASE_FIELD_TYPES = {
    "symbol": "VARCHAR",
    "datetime": "TIMESTAMP",
    "open": "DOUBLE",
    "high": "DOUBLE", 
    "low": "DOUBLE",
    "close": "DOUBLE",
    "volume": "DOUBLE"
}

# SQL 模板
CREATE_FEATURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table_name} (
    symbol      VARCHAR,
    datetime    TIMESTAMP,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      DOUBLE,
    PRIMARY KEY (symbol, datetime)
)
"""

CREATE_CALENDAR_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table_name} (
    datetime TIMESTAMP PRIMARY KEY
)
"""

CREATE_INSTRUMENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS instrument (
    symbol       VARCHAR PRIMARY KEY,
    start_date   DATE,
    end_date     DATE
)
"""

CREATE_INDEX_DEF_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS index_def (
    index_name VARCHAR PRIMARY KEY,
    index_type VARCHAR,
    description VARCHAR
)
"""

CREATE_INDEX_MEMBER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS index_member (
    index_name   VARCHAR,
    symbol       VARCHAR,
    weight       DOUBLE,
    start_date   DATE,
    end_date     DATE,
    PRIMARY KEY (index_name, symbol)
)
"""