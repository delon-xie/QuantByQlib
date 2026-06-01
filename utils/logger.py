"""
QuantByQlib 日志系统
基于 loguru，同时输出到文件和 Qt 事件总线（供 UI 日志页面展示）
"""
from __future__ import annotations
import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_dir: str | Path | None = None, level: str = "INFO") -> None:
    """
    初始化日志系统
    - 控制台输出（彩色）
    - 文件输出（按大小轮转，保留30天）
    - 同时将日志推送到 Qt 事件总线（如果已初始化）
    """
    # 移除默认处理器
    logger.remove()

    # 控制台处理器（彩色）
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True,
    )

    # 文件处理器
    if log_dir is None:
        # 使用项目目录内的 logs 目录，避免权限问题
        log_dir = Path(__file__).parent.parent / "logs"
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "app.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        level=level,
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
    )

    # Qt 事件总线处理器（延迟绑定，避免循环导入）
    logger.add(
        _qt_sink,
        format="{time:HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG",
        catch=True,
    )

    logger.info("日志系统初始化完成")


def _qt_sink(message) -> None:
    """将日志推送到 Qt 事件总线（如果已可用）"""
    try:
        from core.event_bus import get_event_bus
        record = message.record
        level = record["level"].name
        text = record["message"]
        get_event_bus().log_message.emit(level, text)
    except Exception:
        pass  # Qt 未初始化时忽略


# 导出 logger 供其他模块直接使用
__all__ = ["logger", "setup_logger"]
