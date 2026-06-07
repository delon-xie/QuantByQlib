# services/akshare_plus.py
"""
AKShare Pro 包装器（重构版）

架构变更:
- 移除猴子补丁方式 (_BrowserSession)
- 浏览器伪装、Cookie 注入、限频等能力已迁移到 akshare 核心库
- AKSharePro 简化为配置包装器，通过 ak.set_cookies() / ak.set_session() 等新 API 配置
- fetch_paginated_data_with_resume 使用核心库的 request_with_retry
"""

import json
import math
import os
import pickle
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Callable

import pandas as pd
import requests
from loguru import logger

# ── 核心库新 API ─────────────────────────────────────────────────
import akshare as ak
from akshare.utils.request import request_with_retry
from akshare.utils.request import request_with_retry


# ──────────────────────────────────────────────
# AKShare 包装器（配置驱动，无猴子补丁）
# ──────────────────────────────────────────────
class AKSharePro:
    """
    AKShare 全方法包装器 —— 通过核心库 API 配置浏览器伪装

    架构改进:
    - 不再使用猴子补丁替换 requests.Session
    - 通过 ak.set_session() / ak.set_cookies() / ak.set_rate_limit() 配置全局请求行为
    - 所有 akshare 接口自动继承配置，无需额外代码

    用法:
        akp = AKSharePro()
        df = akp.stock_zh_a_spot_em()

        # 高级用法：注入 Cookie
        akp = AKSharePro(cookies={"xq_a_token": "xxx"}, cookie_host="xueqiu.com")

        # 高级用法：自定义 Session
        import requests
        s = requests.Session()
        s.headers.update({"Authorization": "Bearer xxx"})
        akp = AKSharePro(session=s)
    """

    def __init__(
        self,
        cookies: Optional[Dict] = None,
        cookie_host: Optional[str] = None,
        session: Optional[requests.Session] = None,
        progress_callback: Optional[Callable] = None,
        rate_limits: Optional[Dict] = None,
        checkpoint_enabled: bool = False,
        checkpoint_dir: str = "./akshare_checkpoints",
        debug: bool = False,
    ):
        """
        初始化 AKShare

        :param cookies: 全局或 per-host Cookie 字典
        :param cookie_host: Cookie 对应的 host（None 表示全局）
        :param session: 自定义 requests.Session 实例
        :param progress_callback: 全局进度回调 Callable[[int, str], None]
        :param rate_limits: per-host 限频配置 {"host": (min_delay, max_delay)}
        :param checkpoint_enabled: 是否启用断点续传
        :param checkpoint_dir: 断点状态保存目录
        :param debug: 调试模式（保留兼容，暂不使用）
        """
        self._debug = debug

        # 注入 Cookie
        if cookies:
            ak.set_cookies(cookies, host=cookie_host)
            logger.debug(f"Cookie 已注入 (host={cookie_host})")

        # 注入 Session
        if session:
            ak.set_session(session)
            logger.debug("自定义 Session 已注入")

        # 注入进度回调
        if progress_callback:
            ak.set_progress_callback(progress_callback)
            logger.debug("进度回调已注入")

        # 注入限频配置
        if rate_limits:
            for host, (min_d, max_d) in rate_limits.items():
                ak.set_rate_limit(host, min_d, max_d)
            logger.debug(f"限频配置已注入: {rate_limits}")

        # 断点续传
        if checkpoint_enabled:
            ak.set_checkpoint(True, checkpoint_dir)
            logger.debug(f"断点续传已启用: {checkpoint_dir}")

    def stock_zh_a_spot_em(self, progress_callback=None) -> pd.DataFrame:
        """沪深京 A 股实时行情（委托给模块级函数）"""
        return stock_zh_a_spot_em(progress_callback=progress_callback)


# ──────────────────────────────────────────────
# 沪深京 A 股实时行情
# ──────────────────────────────────────────────
def stock_zh_a_spot_em(progress_callback=None) -> pd.DataFrame:
    """
    东方财富网-沪深京 A 股-实时行情

    :param progress_callback: 进度回调函数，接受 (pct: int, msg: str) 参数
    :return: 实时行情 DataFrame
    """
    url = "https://82.push2delay.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
        "fields": (
            "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,"
            "f20,f21,f22,f23,f24,f25,f38,f39,f62,f100,f115,f116,f128,f136,f140,f141,f152"
        ),
    }

    try:
        temp_df = fetch_paginated_data_with_resume(
            url=url,
            base_params=params,
            timeout=15,
            resume_key="stock_zh_a_spot_em",
            progress_callback=progress_callback,
        )
    except Exception as e:
        logger.error(f"获取沪深京 A 股实时行情失败: {e}")
        raise

    # 清理过期的状态文件
    cleanup_old_states()

    # 字段映射
    field_to_chinese = {
        "index": "序号",
        "f1": "保留",
        "f2": "最新价",
        "f3": "涨跌幅",
        "f4": "涨跌额",
        "f5": "成交量",
        "f6": "成交额",
        "f7": "振幅",
        "f8": "换手率",
        "f9": "市盈率-动态",
        "f10": "量比",
        "f11": "5分钟涨跌",
        "f12": "代码",
        "f13": "市场标识",
        "f14": "名称",
        "f15": "最高",
        "f16": "最低",
        "f17": "今开",
        "f18": "昨收",
        "f20": "总市值",
        "f21": "流通市值",
        "f22": "涨速",
        "f23": "市净率",
        "f24": "60日涨跌幅",
        "f25": "年初至今涨跌幅",
        "f38": "总股本",
        "f39": "流通股本",
        "f62": "主力净流入",
        "f100": "行业名称",
        "f115": "市盈率",
        "f116": "未知116",
        "f128": "未知指标128",
        "f136": "未知指标136",
        "f140": "未知指标140",
        "f141": "未知指标141",
        "f152": "状态标志",
    }

    temp_df.rename(columns=field_to_chinese, inplace=True)

    keep_columns = [
        "序号", "保留", "代码", "名称", "最新价", "涨跌幅", "涨跌额",
        "成交量", "成交额", "振幅", "最高", "最低", "今开", "昨收",
        "量比", "换手率", "市盈率-动态", "市净率", "总市值", "流通市值",
        "涨速", "5分钟涨跌", "60日涨跌幅", "年初至今涨跌幅", "行业名称",
        "状态标志", "市盈率", "主力净流入", "市场标识", "总股本", "流通股本",
    ]
    temp_df = temp_df[[c for c in keep_columns if c in temp_df.columns]]

    # 数值列转换
    numeric_cols = [
        "最新价", "涨跌幅", "涨跌额", "成交量", "成交额", "振幅",
        "最高", "最低", "今开", "昨收", "量比", "换手率", "市盈率-动态",
        "市净率", "总市值", "流通市值", "涨速", "5分钟涨跌",
        "60日涨跌幅", "年初至今涨跌幅",
    ]
    for col in numeric_cols:
        if col in temp_df.columns:
            temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce")

    return temp_df


# ──────────────────────────────────────────────
# 带断点续传的分页数据获取
# ──────────────────────────────────────────────
def fetch_paginated_data_with_resume(
    url: str,
    base_params: Dict,
    timeout: int = 15,
    resume_key: Optional[str] = None,
    state_dir: str = "./resume_states",
    max_retries: int = 3,
    progress_callback=None,
):
    """
    带断点续传的分页数据获取函数

    使用核心库的 request_with_retry，自动获得浏览器伪装、Cookie 注入、限频等能力。

    :param url: 请求 URL
    :param base_params: 基础请求参数
    :param timeout: 请求超时时间
    :param resume_key: 断点续传的唯一标识
    :param state_dir: 状态文件保存目录
    :param max_retries: 单页最大重试次数
    :param progress_callback: 进度回调 Callable[[int, str], None]
    :return: 合并后的 DataFrame
    """
    # 自动生成 resume_key
    if resume_key is None:
        import hashlib
        key_str = f"{url}_{json.dumps(base_params, sort_keys=True)}"
        resume_key = hashlib.md5(key_str.encode()).hexdigest()[:16]

    state_dir_path = Path(state_dir)
    state_dir_path.mkdir(exist_ok=True)

    state_file = state_dir_path / f"{resume_key}.state"
    data_file = state_dir_path / f"{resume_key}.data.pkl"

    # ── 检查恢复状态 ─────────────────────────────────────────────
    all_pages_data = []
    start_page = 1
    total_page = 0
    per_page_num = 0
    recovered = False

    if state_file.exists():
        try:
            with open(state_file, "rb") as f:
                state = pickle.load(f)
            if "timestamp" in state:
                state_age = time.time() - state["timestamp"]
                if state_age > 86400:  # 24 小时过期
                    logger.info(f"状态文件已过期（{state_age/3600:.1f}h），重新开始")
                else:
                    saved_data = state.get("data", [])
                    if isinstance(saved_data, list):
                        all_pages_data = saved_data
                        start_page = state.get("current_page", 1)
                        total_page = state.get("total_page", 0)
                        per_page_num = state.get("per_page_num", 0)
                        recovered = True
                        logger.info(f"恢复进度: 从第 {start_page} 页继续")
        except Exception as e:
            logger.warning(f"加载状态文件失败: {e}")

    params = base_params.copy()

    # ── 获取第一页（非恢复状态）─────────────────────────────────
    if not recovered or not all_pages_data:
        logger.info("开始新的数据获取...")
        if progress_callback:
            progress_callback(5, "开始获取第一页...")

        retry_count = 0
        while retry_count < max_retries:
            try:
                r = request_with_retry(url, params=params, timeout=timeout)
                data_json = r.json()

                per_page_num = len(data_json["data"]["diff"])
                total_page = math.ceil(data_json["data"]["total"] / per_page_num)

                first_page_df = pd.DataFrame(data_json["data"]["diff"])
                all_pages_data.append(first_page_df)

                logger.info(f"总页数: {total_page}, 每页: {per_page_num}")
                if progress_callback:
                    progress_callback(10, f"第一页完成，共 {total_page} 页")
                break

            except Exception as e:
                retry_count += 1
                logger.warning(f"获取第一页失败 ({retry_count}/{max_retries}): {e}")
                if retry_count == max_retries:
                    raise
                time.sleep(2 ** retry_count)
    else:
        logger.info(f"恢复状态: 总页数 {total_page}, 从第 {start_page} 页继续")
        if progress_callback:
            progress_callback(10, f"恢复进度，从第 {start_page} 页继续")

    # ── 获取剩余页面 ─────────────────────────────────────────────
    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = lambda x, **kw: x  # fallback

    completed_pages = len(all_pages_data) if all_pages_data else 0

    for page in tqdm(range(start_page, total_page + 1), leave=False, desc="分页获取"):
        if page < start_page:
            continue
        if page == 1 and (recovered or all_pages_data):
            continue

        retry_count = 0
        while retry_count <= max_retries:
            try:
                if page > 1:
                    params.update({"pn": page})
                    time.sleep(random.uniform(0.5, 1.5))

                if progress_callback and total_page > 0:
                    progress_callback(
                        10 + int(85 * completed_pages / total_page),
                        f"正在获取第 {page}/{total_page} 页...",
                    )

                r = request_with_retry(url, params=params, timeout=timeout)
                data_json = r.json()

                inner_temp_df = pd.DataFrame(data_json["data"]["diff"])
                all_pages_data.append(inner_temp_df)
                completed_pages += 1

                if progress_callback and total_page > 0:
                    pct = 10 + int(85 * completed_pages / total_page)
                    progress_callback(
                        pct,
                        f"已获取第 {page}/{total_page} 页，共 {len(all_pages_data) * per_page_num} 条",
                    )

                # 保存断点状态
                with open(state_file, "wb") as f:
                    pickle.dump({
                        "current_page": page,
                        "total_page": total_page,
                        "per_page_num": per_page_num,
                        "data": all_pages_data,
                        "timestamp": time.time(),
                        "url": url,
                        "params": base_params,
                        "resume_key": resume_key,
                    }, f)

                # 定期持久化数据快照
                if page % 10 == 0 or page == total_page:
                    temp_df = pd.concat(all_pages_data, ignore_index=True)
                    temp_df.to_pickle(data_file)

                break

            except Exception as e:
                retry_count += 1
                if retry_count <= max_retries:
                    time.sleep(2 ** retry_count)
                else:
                    # 保存失败时的进度
                    with open(state_file, "wb") as f:
                        pickle.dump({
                            "current_page": page - 1,
                            "total_page": total_page,
                            "per_page_num": per_page_num,
                            "data": all_pages_data[:-1] if all_pages_data else [],
                            "timestamp": time.time(),
                            "error": str(e),
                            "url": url,
                            "params": base_params,
                            "resume_key": resume_key,
                        }, f)

                    if all_pages_data:
                        temp_df = pd.concat(all_pages_data, ignore_index=True)
                        temp_df.to_pickle(data_file)

                    raise RuntimeError(f"获取第 {page} 页失败: {e}")

    # ── 合并与后处理 ─────────────────────────────────────────────
    if not all_pages_data:
        return pd.DataFrame()

    temp_df = pd.concat(all_pages_data, ignore_index=True)

    if "f3" in temp_df.columns:
        temp_df["f3"] = pd.to_numeric(temp_df["f3"], errors="coerce")
        temp_df.sort_values(by=["f3"], ascending=False, inplace=True, ignore_index=True)

    temp_df.reset_index(inplace=True)
    if "index" in temp_df.columns:
        temp_df["index"] = temp_df["index"].astype(int) + 1

    # 清理断点文件
    if state_file.exists():
        os.remove(state_file)
    if data_file.exists():
        os.remove(data_file)

    logger.info(f"数据获取完成，共 {len(temp_df)} 条记录")
    return temp_df


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────
def cleanup_old_states(state_dir: str = "./resume_states", max_age_hours: int = 24):
    """清理过期的断点续传状态文件"""
    state_dir_path = Path(state_dir)
    if not state_dir_path.exists():
        return

    current_time = time.time()
    deleted_count = 0

    for state_file in state_dir_path.glob("*.state"):
        try:
            with open(state_file, "rb") as f:
                state = pickle.load(f)
            if "timestamp" in state:
                state_age = current_time - state["timestamp"]
                if state_age > max_age_hours * 3600:
                    data_file = state_dir_path / f"{state_file.stem}.data.pkl"
                    if data_file.exists():
                        os.remove(data_file)
                    os.remove(state_file)
                    deleted_count += 1
        except Exception as e:
            logger.warning(f"清理状态文件 {state_file} 失败: {e}")

    if deleted_count > 0:
        logger.info(f"已清理 {deleted_count} 个过期的状态文件")


def manual_resume(resume_key: str, state_dir: str = "./resume_states"):
    """
    手动恢复指定任务的断点信息

    :param resume_key: 恢复键
    :param state_dir: 状态文件目录
    :return: 恢复任务所需参数 dict
    """
    state_file = Path(state_dir) / f"{resume_key}.state"
    if not state_file.exists():
        raise FileNotFoundError(f"未找到恢复键为 {resume_key} 的状态文件")

    with open(state_file, "rb") as f:
        state = pickle.load(f)

    logger.info(
        f"恢复任务: URL={state.get('url')}, "
        f"页码={state.get('current_page', 1)}/{state.get('total_page', '?')}, "
        f"已获取={len(state.get('data', []))}页"
    )
    if "error" in state:
        logger.info(f"上次错误: {state.get('error')}")

    return {
        "url": state.get("url"),
        "params": state.get("params", {}),
        "resume_key": resume_key,
    }


def print_first_row(temp_df: pd.DataFrame):
    """调试用：输出 DataFrame 第一行完整数据"""
    if temp_df.empty:
        logger.warning("DataFrame 为空")
        return pd.DataFrame()

    temp_df.rename(columns={"index": "序号"}, inplace=True)
    if len(temp_df) > 0:
        print("\n" + "=" * 100)
        print("测试数据 - 第一行完整信息:")
        print("=" * 100)
        sample_row = temp_df.iloc[0]
        for column in temp_df.columns:
            value = sample_row[column]
            if isinstance(value, str) and len(value) > 50:
                value = f"{value[:50]}..."
            print(f"{column:20}: {value}")
        print("-" * 100)
        print(f"总行数: {len(temp_df)}, 总列数: {len(temp_df.columns)}")
        print("=" * 100)

    return temp_df


def get_tqdm():
    """获取进度条函数（兼容 tqdm 未安装的情况）"""
    try:
        from tqdm import tqdm
        return tqdm
    except ImportError:
        class SimpleProgressBar:
            def __init__(self, iterable=None, total=None, desc=None, leave=True, **kw):
                self.iterable = iterable
                self.total = total if total is not None else (len(iterable) if iterable else None)
                self.desc = desc
                self.n = 0
                self.start_time = time.time()

            def __iter__(self):
                for obj in (self.iterable or []):
                    yield obj
                    self.n += 1

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return SimpleProgressBar
