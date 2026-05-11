"""
RD-Agent 因子注入器（Phase A + B）
- 验证 RD-Agent 发现的因子是否具有足够的预测能力（IC ≥ 0.03）
- 将通过验证的因子持久化，供量化选股策略自动加载
- 存储路径：~/.quantbyqlib/valid_factors.json
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

VALID_FACTORS_FILE = Path.home() / ".quantbyqlib" / "valid_factors.json"
IC_THRESHOLD    = 0.03   # 业界通行：IC 均值 ≥ 0.03 视为有效因子
SHARPE_MAX      = 50.0   # Sharpe 绝对值 > 50 视为过拟合，拒绝注入
VALIDATE_DAYS   = 252    # 用最近 252 个交易日验证


def _precheck_expression(expr: str) -> tuple[bool, str]:
    """
    快速语法预检，拦截 Qlib 不支持的表达式模式。
    返回 (ok, reason)；ok=False 时 reason 说明原因。
    """
    # 所有滚动算子（Max/Min/Sum/Mean/Std/Ref）的窗口参数必须是纯整数常量。
    # 常见错误：Sum($v, 10+0.001) → 'float' object cannot be interpreted as an integer
    for m in re.finditer(r'\b(Max|Min|Sum|Mean|Std|Ref)\s*\(', expr):
        op = m.group(1)
        start = m.end()
        depth = 1
        i = start
        while i < len(expr) and depth > 0:
            if expr[i] == '(':
                depth += 1
            elif expr[i] == ')':
                depth -= 1
            elif expr[i] == ',' and depth == 1:
                second_arg = expr[i+1:].lstrip()
                if not re.match(r'^\d+\s*[\),]', second_arg):
                    return False, (
                        f"{op}() 窗口参数必须是纯整数，不能含运算式或小数"
                        f"（检测到: {expr[m.start():m.start()+60]}…）。"
                        f"防零除请加在结果上，如 Sum(...,10)+0.001"
                    )
                break
            i += 1

    # Abs() 内不能嵌套 Ref()
    if re.search(r'\bAbs\s*\([^)]*Ref\s*\(', expr):
        return False, "Abs() 内不能嵌套 Ref()，改用 Mean($high-$low, N)"

    # 一元负号 -(expr)：- 前面是数字、$变量、) 时均为合法减法，不拦截
    if re.search(r'(?<![0-9\$\w\)])-\s*\(', expr):
        return False, "不支持一元负号 -(expr)，改写为 0-(expr)"

    return True, ""


def validate_factor(expression: str, universe: list[str],
                    threshold_ic: float = IC_THRESHOLD,
                    return_metrics: bool = False):
    """
    用 Qlib D.features 计算因子在股票池上的截面 IC，判断是否有效。
    IC = 因子值与下一期收益率的 Spearman 相关系数均值。

    expression:     Qlib 表达式，如 "Ref($close,5)/$close-1"
    universe:       小写 ticker 列表（与 Qlib features/ 目录一致）
    return_metrics: True 时返回 (passed, ic_mean, ic_std, sharpe)；
                    False（默认）时仅返回 bool，保持向后兼容。
    """
    # 语法预检：拦截已知的不支持模式，避免晦涩运行时报错
    def _fail(msg: str = ""):
        if msg:
            logger.warning(msg) if "[因子验证]" in msg else logger.debug(msg)
        return (False, None, None, None) if return_metrics else False

    ok, reason = _precheck_expression(expression)
    if not ok:
        logger.warning(f"[因子验证] {expression[:50]} 语法预检失败：{reason}")
        return (False, None, None, None) if return_metrics else False

    try:
        from qlib.data import D
        from qlib import config as qlib_config
        from data.qlib_manager import _find_data_dir

        # 确定日期范围：以 Qlib 数据最新日期为基准往前 VALIDATE_DAYS 个交易日
        data_dir = _find_data_dir()
        cal_file = data_dir / "calendars" / "day.txt"
        if not cal_file.exists():
            logger.debug("validate_factor: 日历文件不存在，跳过验证")
            return (False, None, None, None) if return_metrics else False

        cal_dates = [l.strip() for l in cal_file.read_text().splitlines() if l.strip()]
        if len(cal_dates) < VALIDATE_DAYS + 5:
            logger.debug("validate_factor: 日历日期不足，跳过验证")
            return (False, None, None, None) if return_metrics else False

        end_date   = cal_dates[-1]
        start_date = cal_dates[-(VALIDATE_DAYS + 1)]

        # macOS + Python 3.9: D.features 使用 multiprocessing spawn 会在子线程里崩溃。
        # 强制 sequential（单进程）模式，避免 joblib MemmappingPool RuntimeError。
        orig_backend = qlib_config.C.get("joblib_backend", "loky")
        qlib_config.C["joblib_backend"] = "sequential"

        try:
            # 取因子值
            factor_df = D.features(
                universe, [expression],
                start_time=start_date, end_time=end_date, freq="day",
            )
            if factor_df is None or factor_df.empty:
                logger.debug(f"validate_factor: {expression} 因子数据为空")
                return (False, None, None, None) if return_metrics else False

            # 取下一期收益率
            ret_df = D.features(
                universe, ["$close/Ref($close,1)-1"],
                start_time=start_date, end_time=end_date, freq="day",
            )
            if ret_df is None or ret_df.empty:
                return (False, None, None, None) if return_metrics else False
        finally:
            qlib_config.C["joblib_backend"] = orig_backend

        # 对齐 index — 去重后再 intersection（防 non-unique multi-index）
        factor_s = factor_df.iloc[:, 0].dropna()
        ret_s    = ret_df.iloc[:, 0].dropna()
        if factor_s.index.duplicated().any():
            factor_s = factor_s[~factor_s.index.duplicated(keep="first")]
        if ret_s.index.duplicated().any():
            ret_s = ret_s[~ret_s.index.duplicated(keep="first")]

        common = factor_s.index.intersection(ret_s.index)
        if len(common) < 30:
            logger.debug(f"validate_factor: {expression} 公共样本不足（{len(common)}）")
            return (False, None, None, None) if return_metrics else False

        factor_s = factor_s.reindex(common)
        ret_s    = ret_s.reindex(common)

        # 截面 IC：按 datetime 分组，各截面计算 Spearman 相关
        from scipy.stats import spearmanr
        ic_list = []
        if hasattr(factor_s.index, "levels"):
            # MultiIndex (datetime, instrument)
            dates = factor_s.index.get_level_values(0).unique()
            for dt in dates:
                try:
                    f_cross = factor_s.xs(dt, level=0)
                    r_cross = ret_s.xs(dt, level=0)
                    idx = f_cross.index.intersection(r_cross.index)
                    if len(idx) < 5:
                        continue
                    corr, _ = spearmanr(f_cross.reindex(idx), r_cross.reindex(idx))
                    if corr == corr:   # not NaN
                        ic_list.append(corr)
                except Exception:
                    pass
        else:
            corr, _ = spearmanr(factor_s, ret_s)
            if corr == corr:
                ic_list.append(corr)

        if not ic_list:
            logger.debug(f"validate_factor: {expression} IC 列表为空")
            return (False, None, None, None) if return_metrics else False

        import numpy as np
        arr = np.array(ic_list)
        ic_mean = float(np.mean(arr))
        ic_std  = float(np.std(arr))
        sharpe  = float(ic_mean / ic_std * np.sqrt(252)) if ic_std > 1e-8 else 0.0
        passed  = ic_mean >= threshold_ic
        logger.info(f"[因子验证] {expression[:40]}  IC均值={ic_mean:.4f}  "
                    f"{'✅ 通过' if passed else '❌ 未通过'}")
        if return_metrics:
            return passed, ic_mean, ic_std, sharpe
        return passed

    except Exception as e:
        err_s = str(e)
        if "__init__() takes" in err_s and "positional arguments" in err_s:
            logger.warning(
                f"[因子验证] {expression[:40]} 表达式语法错误：Qlib 算子参数数量不匹配"
                f"（常见原因：Max/Min 只接受 2 个参数，三元 ATR 需改写为嵌套形式）"
            )
        else:
            logger.warning(f"[因子验证] {expression[:40]} 验证异常：{e}")
        if return_metrics:
            return False, None, None, None
        return False


def get_valid_factors(
    min_ic: float = IC_THRESHOLD,
    max_sharpe: float = SHARPE_MAX,
    progress_cb=None,
) -> list[dict]:
    """
    从最新 RD-Agent 会话中筛选通过 IC 验证的因子。

    流程：
    1. 读取 session_manager 最新会话
    2. 先用 DiscoveredFactor.ic_mean 快速预筛（无 Qlib 调用）
    3. 对预筛通过的因子调用 validate_factor() 做 Qlib 实测
    返回 list[dict]，每项含 {"expression": str, "name": str, "description": str}
    """
    def _cb(pct: int, msg: str):
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    _cb(5, "读取 RD-Agent 历史会话...")

    try:
        from rdagent_integration.session_manager import get_session_manager
        session = get_session_manager().get_latest()
    except Exception as e:
        logger.warning(f"get_valid_factors: 读取会话失败：{e}")
        return []

    if not session or not session.get("factors"):
        logger.info("get_valid_factors: 无历史因子会话")
        return []

    factors = session["factors"]
    logger.info(f"get_valid_factors: 会话共 {len(factors)} 个因子，开始预筛...")

    # 构建 expression → {name, description} 映射（供后续附加到结果）
    # 同时汇总所有历史会话的描述，保证库中旧因子也能查到
    _expr_meta: dict[str, dict] = {}
    try:
        from rdagent_integration.session_manager import get_session_manager as _gsm
        for s in _gsm().get_all():
            for f in s.get("factors", []):
                expr = f.get("expression", "").strip()
                if expr and expr not in _expr_meta:
                    _expr_meta[expr] = {
                        "name":        f.get("name", ""),
                        "description": f.get("description", ""),
                    }
    except Exception:
        pass

    # 第一步：IC 预筛（仅用 DiscoveredFactor 记录的 ic_mean，无 Qlib 调用）
    candidates = []
    for f in factors:
        expr = f.get("expression", "").strip()
        if not expr:
            continue
        ic_reported = f.get("ic_mean")
        # ic_mean 为 None 表示 RD-Agent 未报告，不过滤；有值则要求 >= min_ic
        if ic_reported is None or ic_reported >= min_ic:
            candidates.append(expr)

    logger.info(f"get_valid_factors: 预筛后 {len(candidates)} 个因子进入 Qlib 验证")
    _cb(15, f"预筛通过 {len(candidates)} 个因子，开始 Qlib IC 验证...")

    if not candidates:
        return []

    # 第二步：Qlib 实测 IC
    try:
        from strategies.qlib_strategy import _qlib_init_check, _get_qlib_data_end_date
        from data.qlib_manager import _find_data_dir
        _qlib_init_check()
    except Exception as e:
        logger.warning(f"get_valid_factors: Qlib 未就绪（{e}），跳过实测")
        # Qlib 不可用时，直接信任 RD-Agent 报告的 ic_mean
        result = []
        for f in factors:
            expr = f.get("expression", "").strip()
            if expr and (f.get("ic_mean") is None or f.get("ic_mean", 0) >= min_ic):
                meta = _expr_meta.get(expr, {})
                result.append({
                    "expression":  expr,
                    "name":        f.get("name", meta.get("name", "")),
                    "description": f.get("description", meta.get("description", "")),
                })
        return result

    # 构建验证用股票池（取蓝筹 30 支，够快）
    _VALIDATE_UNIVERSE = [t.lower() for t in [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM",
        "V", "UNH", "XOM", "JNJ", "MA", "PG", "HD", "COST", "NFLX",
        "AMD", "CRM", "ADBE", "QCOM", "TXN", "AVGO", "LLY", "PEP",
        "KO", "WMT", "MCD", "IBM", "GE",
    ]]

    # 合并已有因子库（对旧因子重验证：自动淘汰已失效的，保留仍有效的）
    existing = load_valid_factors(max_age_hours=float("inf"))  # 不受时效限制，强制重验
    existing_new = [e for e in existing if e not in candidates]
    if existing_new:
        logger.info(f"get_valid_factors: 合并历史因子库 {len(existing_new)} 个进行重验证")
    all_candidates = candidates + existing_new

    valid_factors_list: list[dict] = []
    total = len(all_candidates)
    for i, expr in enumerate(all_candidates):
        pct = 15 + int(80 * i / total)
        source = "历史" if expr in existing_new else "新发现"
        _cb(pct, f"[{source}] 验证因子 {i+1}/{total}：{expr[:30]}...")
        passed, ic_mean, ic_std, sharpe = validate_factor(
            expr, _VALIDATE_UNIVERSE, min_ic, return_metrics=True
        )
        if passed:
            # 过滤 Sharpe 异常高的因子（过拟合信号）
            if sharpe is not None and abs(sharpe) > max_sharpe:
                logger.warning(
                    f"[因子注入] 拒绝过拟合因子 {expr[:40]}"
                    f"  Sharpe={sharpe:.1f} > 阈值 {max_sharpe}"
                    f"  （IC={ic_mean:.4f} 看似优秀但不可信）"
                )
                continue
            meta = _expr_meta.get(expr, {})
            valid_factors_list.append({
                "expression":  expr,
                "name":        meta.get("name", ""),
                "description": meta.get("description", ""),
                "ic_mean":     ic_mean,
                "ic_std":      ic_std,
                "sharpe":      sharpe,
            })

    # 按表达式去重（忽略空格差异），保留先出现的版本
    seen_keys: set[str] = set()
    deduped: list[dict] = []
    for f in valid_factors_list:
        key = f["expression"].replace(" ", "")
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(f)
    if len(deduped) < len(valid_factors_list):
        logger.info(f"get_valid_factors: 去重 {len(valid_factors_list) - len(deduped)} 个重复因子")

    _cb(97, f"验证完成：{len(deduped)}/{total} 个因子通过（含历史重验）")
    logger.info(f"get_valid_factors: {len(deduped)} 个因子通过验证")
    return deduped


def save_valid_factors(factors: list) -> None:
    """
    将通过验证的因子持久化到 ~/.quantbyqlib/valid_factors.json。

    factors 可以是：
      - list[dict]：{"expression", "name", "description", ...}（推荐，来自 get_valid_factors）
      - list[str]：仅表达式字符串（向后兼容旧调用）
    """
    VALID_FACTORS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 统一转成 list[dict]
    factor_dicts: list[dict] = []
    for f in factors:
        if isinstance(f, str):
            factor_dicts.append({"expression": f, "name": "", "description": ""})
        else:
            d = f if isinstance(f, dict) else {}
            factor_dicts.append({
                "expression":  str(d.get("expression", f)),
                "name":        d.get("name", ""),
                "description": d.get("description", ""),
                "ic_mean":     d.get("ic_mean"),
                "ic_std":      d.get("ic_std"),
                "sharpe":      d.get("sharpe"),
            })

    data = {
        "updated_at":  datetime.now().isoformat(timespec="seconds"),
        "count":       len(factor_dicts),
        "expressions": [d["expression"] for d in factor_dicts],  # 向后兼容
        "factors":     factor_dicts,
    }
    try:
        VALID_FACTORS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"已保存 {len(factor_dicts)} 个有效因子到 {VALID_FACTORS_FILE}")
    except Exception as e:
        logger.warning(f"save_valid_factors 写入失败：{e}")


def load_valid_factors(max_age_hours: float = 24.0) -> list[str]:
    """
    从持久化文件加载有效因子表达式列表。
    若文件不存在或超过 max_age_hours，返回空列表（不强制重验证）。
    """
    if not VALID_FACTORS_FILE.exists():
        return []
    try:
        import time
        age_h = (time.time() - VALID_FACTORS_FILE.stat().st_mtime) / 3600
        if age_h > max_age_hours:
            logger.debug(f"valid_factors.json 已过期（{age_h:.1f}h），返回空列表")
            return []
        data = json.loads(VALID_FACTORS_FILE.read_text(encoding="utf-8"))
        exprs = data.get("expressions", [])
        if exprs:
            logger.info(f"加载 {len(exprs)} 个自定义因子（更新于 {data.get('updated_at', '?')}）")
        return [str(e) for e in exprs if e]
    except Exception as e:
        logger.debug(f"load_valid_factors 读取失败：{e}")
        return []


def clear_valid_factors() -> None:
    """清空有效因子文件（用于重置）"""
    try:
        if VALID_FACTORS_FILE.exists():
            VALID_FACTORS_FILE.unlink()
            logger.info("已清空 valid_factors.json")
    except Exception as e:
        logger.warning(f"clear_valid_factors 失败：{e}")


def get_inject_status() -> dict:
    """
    返回当前注入状态摘要，供 UI 展示。
    返回字段：
      injected, count, updated_at, age_hours,
      expressions: list[str]（向后兼容），
      factors: list[dict]（含 expression/name/description）
    """
    if not VALID_FACTORS_FILE.exists():
        return {"injected": False, "count": 0, "updated_at": None,
                "expressions": [], "factors": []}
    try:
        import time
        age_h = (time.time() - VALID_FACTORS_FILE.stat().st_mtime) / 3600
        data = json.loads(VALID_FACTORS_FILE.read_text(encoding="utf-8"))
        exprs = data.get("expressions", [])
        # 优先读新格式 factors 列表；若无则从 expressions 补全
        raw_factors = data.get("factors", [])
        if not raw_factors:
            raw_factors = [{"expression": e, "name": "", "description": ""}
                           for e in exprs]
        return {
            "injected":    True,
            "count":       data.get("count", len(exprs)),
            "updated_at":  data.get("updated_at"),
            "age_hours":   round(age_h, 1),
            "expressions": exprs,
            "factors":     raw_factors,
        }
    except Exception:
        return {"injected": False, "count": 0, "updated_at": None,
                "expressions": [], "factors": []}
