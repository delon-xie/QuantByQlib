"""
数据库表结构管理
"""
from typing import List, Optional
from .duckdb_connection import get_connection
from .constants import (
    SUPPORTED_FREQS, FEATURE_TABLE_PREFIX, CALENDAR_TABLE_PREFIX,
    CALENDAR_FUTURE_SUFFIX, CREATE_FEATURE_TABLE_SQL, CREATE_CALENDAR_TABLE_SQL,
    CREATE_INSTRUMENT_TABLE_SQL, CREATE_INDEX_DEF_TABLE_SQL, CREATE_INDEX_MEMBER_TABLE_SQL
)
from .exceptions import UnsupportedFrequencyError
import logging

logger = logging.getLogger(__name__)


class SchemaManager:
    """表结构管理类"""
    
    @staticmethod
    def create_feature_table(reg: str, freq: str):
        """创建特征表"""
        if freq not in SUPPORTED_FREQS:
            raise UnsupportedFrequencyError(f"Unsupported frequency: {freq}")
        
        table_name = f"{FEATURE_TABLE_PREFIX}{freq}"
        sql = CREATE_FEATURE_TABLE_SQL.format(table_name=table_name)
        
        with get_connection(reg) as conn:
            conn.execute(sql, fetch=False)
            
            # 在 datetime 上创建索引优化时间范围查询
            #index_sql = f"CREATE INDEX IF NOT EXISTS idx_{table_name}_datetime ON {table_name}(datetime)"
            #conn.execute(index_sql, fetch=False)
            
        logger.info(f"Created feature table: {table_name} in {reg}")
    
    @staticmethod
    def create_calendar_table(reg: str, freq: str, future: bool = False):
        """创建日历表"""
        if freq not in SUPPORTED_FREQS:
            raise UnsupportedFrequencyError(f"Unsupported frequency: {freq}")
        
        suffix = CALENDAR_FUTURE_SUFFIX if future else ""
        table_name = f"{CALENDAR_TABLE_PREFIX}{freq}{suffix}"
        sql = CREATE_CALENDAR_TABLE_SQL.format(table_name=table_name)
        
        with get_connection(reg) as conn:
            conn.execute(sql, fetch=False)
        
        logger.info(f"Created calendar table: {table_name} in {reg}")
    
    @staticmethod
    def create_instrument_table(reg: str):
        """创建标的表"""
        with get_connection(reg) as conn:
            conn.execute(CREATE_INSTRUMENT_TABLE_SQL, fetch=False)
        logger.info(f"Created instrument table in {reg}")
    
    @staticmethod
    def create_index_tables(reg: str):
        """创建指数表"""
        with get_connection(reg) as conn:
            # 尝试执行创建表语句
                print(f"Creating index_def table in {reg}...")
                conn.execute(CREATE_INDEX_DEF_TABLE_SQL, fetch=False)
                
                print(f"Creating index_member table in {reg}...")
                conn.execute(CREATE_INDEX_MEMBER_TABLE_SQL, fetch=False)
        logger.info(f"Created index tables in {reg}")
    
    @staticmethod
    def create_all_tables_for_freq(reg: str, freq: str):
        """为指定频率创建所有相关表"""
        SchemaManager.create_feature_table(reg, freq)
        SchemaManager.create_calendar_table(reg, freq, future=False)
        SchemaManager.create_calendar_table(reg, freq, future=True)
    
    @staticmethod
    def create_all_tables(reg: str):
        """创建所有表"""
        SchemaManager.create_instrument_table(reg)
        SchemaManager.create_index_tables(reg)
        
        for freq in SUPPORTED_FREQS:
            SchemaManager.create_all_tables_for_freq(reg, freq)
    
    @staticmethod
    def table_exists(reg: str, table_name: str) -> bool:
        """检查表是否存在"""
        with get_connection(reg, read_only=False) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                (table_name,)
            )
            return result[0][0] > 0
    
    @staticmethod
    def get_table_info(reg: str) -> List[dict]:
        """获取表信息"""
        with get_connection(reg, read_only=False) as conn:
            result = conn.execute("""
                SELECT table_name, column_count, estimated_size 
                FROM duckdb_tables() 
                ORDER BY table_name
            """)
            return [
                {"table_name": row[0], "column_count": row[1], "estimated_size": row[2]}
                for row in result
            ]