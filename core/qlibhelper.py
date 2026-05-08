from pathlib import Path
from loguru import logger
from typing import List, Pattern
from qlib.config import _default_region_config
from .app_state import get_state
import re

REG_CN = "cn"
REG_US = "us"
REG_TW = "tw"
REG_HK = "hk"
REG_JP = "jp"
REG_KR = "kr"
REG_CN_NAME = "A股"
REG_US_NAME = "美股"
REG_TW_NAME = "台股"
REG_HK_NAME = "港股"
REG_JP_NAME = "日股"
REG_KR_NAME = "韩股"

# ---------- 市场规则 ----------
MARKET_RULES: dict[str, Pattern] = {
    "cn": re.compile(r"^(sh|sz|bj)\d{6}$"),           # A 股
    "hk": re.compile(r"^\d{4,5}\.HK$"),               # 港股
    "tw": re.compile(r"^tw\d{4,6}$"),                 # 台股
    "jp": re.compile(r"^jp\d{4}$"),                   # 日股
    "kr": re.compile(r"^kr\d{6}$"),                   # 韩股
    "us": re.compile(r"^[A-Z]+([-.][A-Z0-9]+)?$"),    # 美股
}


def _normalize_ticker(ticker: str, reg: str) -> str:
    """标准化 ticker：将 Qlib 格式（BRK.B）转换为 yfinance 格式（BRK-B）"""
    match = MARKET_RULES.get(reg)
    if match and match.match(ticker):
        return ticker
    else:
        return ticker.replace(".", "-")
def _is_valid_stock_code(name: str, reg: str) -> bool:
    """
    判断是否为合法的股票代码
    """
    name = name.lower()
    reg = reg.lower()
    if reg in MARKET_RULES:
        return bool(MARKET_RULES[reg].match(name))
    return False

def _find_data_dir() -> Path:
    """
    自动探测 Qlib 数据目录。
    优先顺序：
      1. ~/.qlib/qlib_data/{reg}_data/   （旧配置路径）
      2. ~/.qlib/qlib_data/              （SunsetWolf 原始下载位置）
    判断依据：features/ 下有纯字母子目录（如 aapl）且不含 sh/sz/bj 前缀
    """
    reg = get_state().reg
    logger.info(f"当前市场：{reg}")
    candidates = [
        Path.home() / ".qlib" / "qlib_data" / f"{reg}_data",
        Path.home() / ".qlib" / "qlib_data",
    ]
    for path in candidates:
        features = path / "features"
        if not features.exists():
            continue
        for d in features.iterdir():
            if d.is_dir() and _is_valid_stock_code(d.name, reg):
                logger.info(f"返回 Qlib 数据目录：{path}")
                return path
    # 默认返回根目录（即使暂时为空）
    logger.info(f"返回 Qlib 默认数据目录：{candidates[0]}")
    return candidates[0]

CALENDAR_REF_TICKER_US = "^GSPC"
CALENDAR_REF_TICKER_CN = "SH600300"
CALENDAR_REF_TICKER_HK = "^HSI"
CALENDAR_REF_TICKER_TW = "^TWII"
CALENDAR_REF_TICKER_JP = "^N225"
CALENDAR_REF_TICKER_KR = "^KS11"
CALENDAR_REF_TICKER_BT = "BTCUSDT"

def _get_accepted_region(reg: str) -> str:
    match reg.lower():
        case "cn" | "hk" | "sz" | "sh" | "bj" | "china" | "中国" | "A股":
            return "cn"
        case "us" | "usa" | "america" | "美股":
            return "us"
        case "tw" | "taiwan" | "台湾":
            return "tw"
        case _:
            return "us"
        
def _get_accepted_region(reg: str) -> str:
    match reg.lower():
        case "cn" | "hk" | "sz" | "sh" | "bj" | "china" | "中国" | "A股":
            return "cn"
        case "us" | "usa" | "america" | "美股":
            return "us"
        case "tw" | "taiwan" | "台湾":
            return "tw"
        case _:
            return "us"

def _check_qlib_init(bus) -> None:
    """检测 Qlib 数据是否已初始化，并更新全局状态"""
    state = get_state()

    qlib_data = Path.home() / ".qlib" / "qlib_data" / f"{state.reg}_data"
    if qlib_data.exists() and any(qlib_data.iterdir()):
        try:
            import qlib
            # from core.constant import REG_US
            from qlib.config import C
            #C.set({"joblib_backend", "sequential"})
            C["joblib_backend"] = "sequential"
            _default_region_config[REG_HK] = {
                "trade_unit": 100,
                "limit_threshold": None,
                "deal_price": "close",
            }
            
            qlib.init(provider_uri=str(qlib_data), region=state.reg)
            state.qlib_initialized = True
            state.qlib_data_path = str(qlib_data)
            logger.info(f"Qlib 初始化成功：{qlib_data}")
            bus.qlib_initialized.emit()
        except Exception as e:
            logger.warning(f"Qlib 初始化失败：{e}")
            state.qlib_initialized = False
    else:
        logger.info("Qlib 数据未找到，请前往「参数配置」下载数据")
        state.qlib_initialized = False