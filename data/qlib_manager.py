"""
Qlib 数据管理器
- 检测初始化状态
- 触发 Yahoo Finance 数据采集器（subprocess）
- 增量更新
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from loguru import logger
from core.qlibhelper import _find_data_dir
QLIB_DATA_DIR = _find_data_dir()


def is_initialized() -> bool:
    """检测 Qlib 美股数据是否已初始化"""
    if not QLIB_DATA_DIR.exists():
        return False
    # 检查关键子目录（features/ calendars/）
    features_dir = QLIB_DATA_DIR / "features"
    calendars_dir = QLIB_DATA_DIR / "calendars"
    return features_dir.exists() and any(features_dir.iterdir()) and calendars_dir.exists()


def init_qlib(provider_uri: Optional[str] = None) -> bool:
    """
    初始化 Qlib（仅当数据已存在时）
    成功返回 True，否则 False；同时更新 AppState.qlib_initialized
    """
    QLIB_DATA_DIR = _find_data_dir()
    uri = provider_uri or str(QLIB_DATA_DIR)
    try:
        from core.qlibhelper import qlib_safeinit
        qlib_safeinit(uri)
        #logger.info(f"Qlib 初始化成功：{uri}")
    except Exception as e:
        msg = str(e)
        logger.error(f"Qlib 初始化失败：{e}")
        # Qlib 已经初始化过（QlibRecorder 激活状态下不允许重复 init），视为成功
        if "reinitialize" in msg or "QlibRecorder" in msg:
            logger.info(f"Qlib 已初始化，跳过重复 init（{uri}）")
        else:
            logger.error(f"Qlib 初始化失败：{e}")
            return False
    try:
        from core.app_state import get_state
        get_state().qlib_initialized = True
    except Exception as ex:
        logger.error(f"Qlib 初始化失败：{e}")
        pass
    #logger.info(f"Qlib 初始化成功：{uri}")
    return True


def auto_init_if_data_ready() -> bool:
    """
    若 Qlib 数据目录已存在且包含美股数据（features/ 下有纯字母目录如 AAPL），
    则自动调用 init_qlib()。供应用启动时调用（后台线程中执行，不阻塞 UI）。
    返回是否初始化成功。
    """
    if not is_initialized():
        logger.debug("Qlib 数据未就绪，跳过自动初始化")
        return False

    # 检测是否为美股数据：features/ 下有纯字母目录（大写 AAPL 或小写 aapl）
    # SunsetWolf 数据使用小写（aapl），A 股使用 sh/sz/bj 前缀（非纯字母）
    features_dir = QLIB_DATA_DIR / "features"
    if features_dir.exists():
        us_stock_dirs = [
            d for d in features_dir.iterdir()
            if d.is_dir() and d.name.replace("-", "").isalpha()
            and not any(d.name.startswith(pfx) for pfx in ("sh", "sz", "bj"))
        ]
        if not us_stock_dirs:
            logger.warning(
                "Qlib features/ 目录下未发现美股代码（如 aapl/AAPL），"
                "当前数据可能是 A 股，跳过自动初始化"
            )
            return False

    logger.info(f"检测到美股 Qlib 数据，自动初始化...")
    return init_qlib()


def get_data_stats() -> dict:
    """
    获取已下载数据的统计信息
    返回：{stock_count, date_range, size_gb, last_modified}
    """
    stats = {
        "stock_count": 0,
        "date_range": "--",
        "size_gb": 0.0,
        "last_modified": "--",
    }
    if not QLIB_DATA_DIR.exists():
        return stats

    # 股票数量：features/ 目录下的子目录数
    features_dir = QLIB_DATA_DIR / "features"
    if features_dir.exists():
        stocks = [d for d in features_dir.iterdir() if d.is_dir()]
        stats["stock_count"] = len(stocks)

    # 日历范围
    calendars_dir = QLIB_DATA_DIR / "calendars"
    cal_file = calendars_dir / "day.txt"
    if cal_file.exists():
        lines = cal_file.read_text().strip().split("\n")
        if len(lines) >= 2:
            stats["date_range"] = f"{lines[0].strip()} ~ {lines[-1].strip()}"

    # 目录大小
    try:
        total = sum(f.stat().st_size for f in QLIB_DATA_DIR.rglob("*") if f.is_file())
        stats["size_gb"] = round(total / 1e9, 2)
    except Exception:
        pass

    # 最后修改时间
    try:
        mtime = QLIB_DATA_DIR.stat().st_mtime
        from datetime import datetime
        stats["last_modified"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass

    return stats


CHENDITC_DATA_URL = (
    "https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz"
)


def get_latest_chenditc_url() -> tuple[str, str]:
    """
    从 GitHub API 获取 chenditc investment_data 最新 release URL 和日期
    返回 (url, tag_name)，失败时返回默认 URL
    """
    import urllib.request, json
    api_url = "https://api.github.com/repos/chenditc/investment_data/releases/latest"
    try:
        with urllib.request.urlopen(api_url, timeout=10) as resp:
            data = json.loads(resp.read())
            tag = data.get("tag_name", "unknown")
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".tar.gz"):
                    return asset["browser_download_url"], tag
    except Exception as e:
        logger.debug(f"获取最新 release URL 失败：{e}")
    return CHENDITC_DATA_URL, "latest"


def build_download_command(scope: str = "sp500", start_date: str = "2015-01-01") -> list[str]:
    """
    构建 Qlib Yahoo Finance 数据采集器的命令
    scope: "sp500" | "nasdaq100" | "all"
    返回 subprocess 命令列表
    """
    # 找到 qlib 安装目录中的采集器脚本
    try:
        import qlib
        qlib_root = Path(qlib.__file__).parent
    except ImportError:
        raise RuntimeError("Qlib 未安装")

    collector_script = qlib_root / "contrib" / "data" / "collector" / "yahoo_cn_minutes" / "collector.py"
    # 美股采集器路径
    us_collector = qlib_root / "contrib" / "data" / "collector" / "yahoo" / "collector.py"

    if not us_collector.exists():
        # 尝试更新路径
        for candidate in qlib_root.rglob("collector.py"):
            if "yahoo" in str(candidate) and "cn" not in str(candidate):
                us_collector = candidate
                break

    if not us_collector.exists():
        raise FileNotFoundError(f"未找到 Qlib Yahoo 采集器脚本，已查找路径：{qlib_root}")

    # 股票池映射
    instruments_map = {
        "sp500":     "sp500",
        "nasdaq100": "nasdaq100",
        "all":       "all",
    }
    instruments = instruments_map.get(scope, "sp500")

    cmd = [
        sys.executable,
        str(us_collector),
        "download_data",
        "--source_dir", str(QLIB_DATA_DIR / "source"),
        "--normalize_dir", str(QLIB_DATA_DIR),
        "--start", start_date,
        "--end",   "today",
        "--delay", "0.5",
        "--max_workers", "8",
        "--interval", "1d",
        "--region", "us",
        "--trading_date_field_name", "date",
    ]

    logger.info(f"下载命令构建完成，stock pool: {instruments}")
    return cmd


def build_normalize_command(source_dir: Optional[str] = None) -> list[str]:
    """构建数据标准化命令（下载完成后执行）"""
    try:
        import qlib
        qlib_root = Path(qlib.__file__).parent
    except ImportError:
        raise RuntimeError("Qlib 未安装")

    normalizer = None
    for candidate in qlib_root.rglob("*.py"):
        if "normalize" in candidate.name and "yahoo" in str(candidate.parent):
            normalizer = candidate
            break

    src = source_dir or str(QLIB_DATA_DIR / "source")
    if normalizer and normalizer.exists():
        return [
            sys.executable,
            str(normalizer),
            "--source_dir", src,
            "--normalize_dir", str(QLIB_DATA_DIR),
            "--max_workers", "4",
            "--region", "us",
        ]
    return []


def find_collector_script() -> Optional[Path]:
    """找到 Qlib Yahoo 美股采集器脚本路径"""
    try:
        import qlib
        qlib_root = Path(qlib.__file__).parent
        for candidate in qlib_root.rglob("collector.py"):
            p = str(candidate)
            if "yahoo" in p and "cn_minutes" not in p and "cn" not in p:
                return candidate
    except Exception:
        pass
    return None
