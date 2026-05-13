"""
日志配置
"""
import logging
import sys
from loguru import logger
from ..config import config


def setup_logging(level: str = None):
    """配置日志"""
    if level is None:
        level = config.log_level
    
    # 移除默认处理器
    logger.remove()
    
    # 添加控制台处理器
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True
    )
    
    # 添加文件处理器
    logger.add(
        f"qlib_duckdb_{config.default_reg}.log",
        rotation="10 MB",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO"
    )
    
    # 配置标准 logging 模块
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    
    return logger


class _InterceptHandler(logging.Handler):
    """拦截标准 logging 到 loguru"""
    
    def emit(self, record):
        # 获取对应的 Loguru 级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        
        # 找到调用者
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )