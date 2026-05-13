"""
自定义异常类
"""


class QlibDuckDBError(Exception):
    """基础异常类"""
    pass


class ConnectionError(QlibDuckDBError):
    """连接相关异常"""
    pass


class MigrationError(QlibDuckDBError):
    """数据迁移异常"""
    pass


class ValidationError(QlibDuckDBError):
    """数据验证异常"""
    pass


class TableNotFoundError(QlibDuckDBError):
    """表不存在异常"""
    pass


class DataConflictError(QlibDuckDBError):
    """数据冲突异常"""
    pass


class ConfigError(QlibDuckDBError):
    """配置异常"""
    pass


class UnsupportedFrequencyError(QlibDuckDBError):
    """不支持的频率异常"""
    pass