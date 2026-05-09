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
REG_BT = "bt"
REG_CN_NAME = "A股"
REG_US_NAME = "美股"
REG_TW_NAME = "台股"
REG_HK_NAME = "港股"
REG_JP_NAME = "日股"
REG_KR_NAME = "韩股"
REG_BT_NAME  = "Crypto"

MARKETS = [
        (REG_US, REG_US_NAME),
        (REG_CN, REG_CN_NAME),
        (REG_HK, REG_HK_NAME),
        (REG_TW, REG_TW_NAME),
        (REG_JP, REG_JP_NAME),
        (REG_KR, REG_KR_NAME),
        (REG_BT, REG_BT_NAME),
    ]

# ---------- 市场规则 ----------
MARKET_RULES: dict[str, Pattern] = {
    "cn": re.compile(r"^(sh|sz|bj)\d{6}$"),           # A 股
    "hk": re.compile(r"^\d{4,5}\.HK$"),               # 港股
    "tw": re.compile(r"^tw\d{4,6}$"),                 # 台股
    "jp": re.compile(r"^jp\d{4}$"),                   # 日股
    "kr": re.compile(r"^kr\d{6}$"),                   # 韩股
    "us": re.compile(r"^[A-Z]+([-.][A-Z0-9]+)?$"),    # 美股
    "bt": re.compile(r"^[A-Z]+$"),                    # Crypto
}

# -------------专用于存储QLIB 初始化状态 -----------
QLIB_INIT_STATUS = {
    "provider_uri" :"",
    "region" : "",
    "inited" : "False"
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
            
            """
            为了防范程序交易错误或极端波动引发的“闪崩”，港股针对特定股票设有 市场波动调节机制（VCM，俗称冷静期），具体规则如下：
            适用范围：主要涵盖恒生综合大型股、中型股及小型股指数成份股、SPAC股份、部分ETF等。
            触发门槛：在持续交易时段内，当股份的潜在成交价偏离 5分钟前最后一次成交价​ 达到一定百分比时触发：
            恒生综合大型股指数成份股：±10%
            恒生综合中型股指数成份股：±15%
            恒生综合小型股指数成份股：±20%
            冷静期安排：触发后进入 5分钟冷静期。期间交易不会停止，但该股只能在被触发的限价范围内（如参考价的±10%）继续进行撮合。5分钟过后，恢复正常交易，价格限制解除，且同一只证券在同一节交易时段内最多只会触发一次。
            不适用时段：开市前时段、收市竞价交易时段，以及持续交易时段的首15分钟和尾盘（下午最后20分钟）不进行监测。
            此外，在开市前时段（集合竞价时段），股票的买卖盘价格一般不能偏离上日收市价超过 ±15%，超出此范围的挂单会被系统拒绝。
            """
            _default_region_config[REG_HK] = {
                "trade_unit": 1, #1股、50股、100股、1000股
                "limit_threshold": 0.4, #设置0.4匹配95%的情况，极端情况不考虑
                "deal_price": "close",
            }
            _default_region_config[REG_BT] = {
                "trade_unit": 0.00000001,
                "limit_threshold": None,
                "deal_price": "close",
            }
            _default_region_config[REG_TW] = {
                "trade_unit": 1000,
                "limit_threshold": 0.1,
                "deal_price": "close",
            }
            _default_region_config[REG_JP] = {
                "trade_unit": 100,
                "limit_threshold": None,
                "deal_price": "close",
            }
            _default_region_config[REG_KR] = {
                "trade_unit": 1,
                "limit_threshold": 0.15,
                "deal_price": "close",
            }
            
            qlib_safeinit(qlib_data)

            logger.info(f"Qlib 初始化成功：{qlib_data}")
            bus.qlib_initialized.emit()
        except Exception as e:
            logger.warning(f"Qlib 初始化失败：{e}")
            state.qlib_initialized = False
    else:
        logger.info("Qlib 数据未找到，请前往「参数配置」下载数据")
        state.qlib_initialized = False

def _get_calendar_ref_ticker() -> str:
        from core.app_state import get_state
        reg = get_state().reg
        match reg:
            case "us":
                return CALENDAR_REF_TICKER_US
            case "cn":
                return CALENDAR_REF_TICKER_CN
            case "hk":
                return CALENDAR_REF_TICKER_HK
            case "tw":
                return CALENDAR_REF_TICKER_TW
            case "jp":
                return CALENDAR_REF_TICKER_JP
            case "kr":
                return CALENDAR_REF_TICKER_KR
            case "bt":
                return CALENDAR_REF_TICKER_BT
            case _:
                return CALENDAR_REF_TICKER_US

def qlib_safeinit(qlib_data : str):
    import qlib
    state = get_state()
    if(
        str(qlib_data) == QLIB_INIT_STATUS["provider_uri"] 
        and state.reg == QLIB_INIT_STATUS["region"] 
        and True == state.qlib_initialized
    ) :
        return
            
    QLIB_INIT_STATUS["inited"] = False
    qlib.init(provider_uri=str(qlib_data), region=state.reg)
    state.qlib_initialized = True
    state.qlib_data_path = str(qlib_data)
    QLIB_INIT_STATUS["provider_uri"] = str(qlib_data)
    QLIB_INIT_STATUS["region"] = state.reg
    QLIB_INIT_STATUS["inited"] = True