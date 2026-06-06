# services/akshare_pro.py
import sys
import types
from typing import Optional, Dict, Any, Union, List
from loguru import logger

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import logging

import time
import random
# import brotli
import gzip
import io
import zlib

import os
import pickle
import json
import pandas as pd
import math
from datetime import datetime
from pathlib import Path

# ── Per-host 请求头模板 ──────────────────────────────────────────
HOST_HEADERS = {
    "push2.eastmoney.com": {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
        ),
        "Referer": "https://quote.eastmoney.com/",
        "Origin": "https://quote.eastmoney.com",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Accept-Encoding": "",
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "Host": "82.push2delay.eastmoney.com",
    },
    "datacenter-web.eastmoney.com": {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
        ),
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Accept-Encoding": "",
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
    },
    "hq.sinajs.cn": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
        "Accept-Encoding": "",  # 新浪常返回 GBK 明文
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
    },
    "xueqiu.com": {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
        ),
        "Referer": "https://xueqiu.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9.8,en-.8,en-GB;q=0.7,en-US;q=0.6",
        "Accept-Encoding": "",
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
    },
    "default": {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Accept-Encoding": "",
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
    },
}


def _match_host_headers(url: str) -> dict:
    """根据 URL host 匹配最合适的请求头"""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    for key in HOST_HEADERS:
        if key in host:
            return HOST_HEADERS[key]
    return HOST_HEADERS["default"]

# ──────────────────────────────────────────────
# 伪装浏览器 Session
# ──────────────────────────────────────────────
class _BrowserSession(requests.Session):
    """
    按 Host 自适应伪装浏览器 Session + 详细调试日志
    - 东财：UA + Referer + gzip
    - 新浪：UA + 无压缩(GBK)
    - 雪球：UA + Referer + Cookie 预留
    - 其他：默认浏览器 UA + gzip
    - 设 DEBUG_AKSHARE_SESSION=True 环境变量开启
    - 打印：请求 URL / 实际发送 Headers / 响应 Status / Response 前 200 字节
    """

    def __init__(self, debug: bool = False):
        super().__init__()
        self._dbg = debug or __import__("os").getenv("DEBUG_AKSHARE_SESSION", "0") == "1"

        retry = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=10,
            pool_maxsize=10,
        )
        self.mount("https://", adapter)
        self.mount("http://", adapter)

    # ── 覆写 send，拦截所有请求/响应 ──────────────────────────
    def send(self, request, **kwargs):
        # ── 按 Host 注入 Header ────────────────────────────────────
        hdrs = _match_host_headers(request.url)
        for k, v in hdrs.items():
            # 不覆盖已经显式设置的（极少情况）
            request.headers.setdefault(k, v)

        if self._dbg:
            self._dbg_request(request)
        
        # ── 限频（东财特别容易封）─────────────────────────────────
        if "eastmoney.com" in request.url:
            time.sleep(random.uniform(1.5, 3.0))
        
        # 让 requests 自动处理解压
        resp = super().send(request, **kwargs)
        
        # 检查是否需要手动处理
        if resp.headers.get("Content-Encoding"):
            if self._dbg:
                print(f"   [WARN] Response is encoded: {resp.headers.get('Content-Encoding')}")
                print(f"   [INFO] Response text preview: {resp.text[:200]}")
        
        if self._dbg:
            self._dbg_response(resp)
        
        return resp

    def _decompress_response(self, resp):
        """手动解压响应数据"""
        import gzip
        import io
        
        content_encoding = resp.headers.get("Content-Encoding", "").lower()
        
        if content_encoding == "gzip":
            # 处理 gzip 压缩
            buffer = io.BytesIO(resp.content)
            with gzip.GzipFile(fileobj=buffer) as f:
                decompressed = f.read()
            resp._content = decompressed
            resp.headers["Content-Encoding"] = ""
            resp.headers["Content-Length"] = str(len(decompressed))
        
        elif content_encoding == "deflate":
            # 处理 deflate 压缩
            import zlib
            try:
                decompressed = zlib.decompress(resp.content, -zlib.MAX_WBITS)
            except zlib.error:
                decompressed = zlib.decompress(resp.content)
            resp._content = decompressed
            resp.headers["Content-Encoding"] = ""
            resp.headers["Content-Length"] = str(len(decompressed))
        
        return resp
    # noinspection PyBroadException
    def _dbg_request(self, req):
        try:
            from urllib.parse import urlparse
            host = urlparse(req.url).hostname
            head_str = " | ".join(f"{k}: {v}" for k, v in req.headers.items())
            print(
                f"\n▶ AKShare REQ  {req.method} {req.url[:120]}"
                f"\n   HOST: {host}"
                f"\n   HEADERS: {head_str[:300]}"
            )
        except Exception:
            pass

    def _dbg_response(self, resp):
        try:
            snippet = resp.text[:200] if hasattr(resp, "text") else ""
            print(
                f"◀ AKShare RESP {resp.status_code} {resp.reason}"
                f"  Len={len(resp.content)}"
                f"\n   SNIPPET: {snippet!r}"
            )
        except Exception:
            pass

# ──────────────────────────────────────────────
# AKShare 包装器
# ──────────────────────────────────────────────
class AKSharePro:
    """
    AKShare 全方法包装器 —— 注入 _BrowserSession 后调用 AKShare

    用法:
        akp = AKSharePro()
        df = stock_zh_a_spot_em()
        df_hk = stock_hk_spot_em()
        hist = stock_zh_a_hist(symbol="600036", period="daily", adjust="qfq")
    """

    def __init__(self, patch_requests: bool = True, debug: bool = False):
        self._debug = debug
        self._original_session_cls = None
        self._patched = False

        if patch_requests:
            self._patch_requests(debug=self._debug)
            self._patched = True
    def _patch_requests(self, debug: bool = False):
        """猴子补丁：让 requests.Session() 返回 _BrowserSession"""
        import requests
        
        # 保存原始类
        self._original_session_cls = requests.Session
        
        # 动态创建带 debug 的 BrowserSession
        def create_session(*args, **kwargs):
            return _BrowserSession(debug=debug)
        
        requests.Session = create_session
        logger.debug(f"requests.Session → _BrowserSession(debug={debug})")
    
    def stock_zh_a_spot_em(self, progress_callback=None) -> pd.DataFrame:
        return stock_zh_a_spot_em(progress_callback=progress_callback)
    def restore(self):
        """恢复原始 requests.Session"""
        if self._patched and self._original_session_cls:
            import requests
            requests.Session = self._original_session_cls
            logger.debug("requests.Session restored")

import pandas as pd
import requests

from akshare.utils.func import fetch_paginated_data
def stock_zh_a_spot_em(progress_callback=None) -> pd.DataFrame:
    """
    东方财富网-沪深京 A 股-实时行情
    https://quote.eastmoney.com/center/gridlist.html#hs_a_board
    
    :param progress_callback: 进度回调函数，接受 (pct: int, msg: str) 参数
    :return: 实时行情
    :rtype: pandas.DataFrame
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
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,"
        "f20,f21,f22,f23,f24,f25,f38,f39,f62,f100,f115,f116,f128,f136,f140,f141,f152",
    }
    
    """
    {"f1":2,"f2":13.32,"f3":4.96,"f4":0.63,"f5":13679,"f6":18062960.11,"f7":5.99,"f8":2.79,"f9":53.24,"f10":2.23,
    "f11":-0.45,"f12":"920992","f13":0,"f14":"中科美菱","f15":13.42,"f16":12.66,"f17":12.67,"f18":12.69,"f20":1288456041,
    "f21":652910210,"f22":-0.3,"f23":2.07,"f24":-16.44,"f25":-23.01,"f62":-780820.0,
    "f100":"医疗器械","f115":64.11,"f116":"-","f128":"-","f140":"-","f141":"-","f136":"-","f152":2},

    """
    try:
        # 第一次运行（会保存状态）
        temp_df = fetch_paginated_data_with_resume(
            url=url,
            base_params=params,
            timeout=15,
            resume_key="stock_zh_a_spot_em",  # 指定恢复键
            progress_callback=progress_callback
        )
    except Exception as e:
        logger.error(f"获取沪深京 A 股实时行情失败: {e}")
        print("程序可以在稍后恢复")
        
        # 手动查看恢复状态
        resume_info = manual_resume("my_task_001")
        print(f"恢复信息: {resume_info}")

    # 清理过期的状态文件
    cleanup_old_states()
    
    #print_first_row(temp_df)
    
    # 字段映射：原始字段名 -> 中文列名
    field_to_chinese = {
        "index": "序号",
        "f1": "保留",                # f1
        "f2": "最新价",            # f2
        "f3": "涨跌幅",            # f3
        "f4": "涨跌额",            # f4
        "f5": "成交量",            # f5
        "f6": "成交额",            # f6
        "f7": "振幅",              # f7
        "f8": "换手率",            # f8
        "f9": "市盈率-动态",        # f9
        "f10": "量比",              # f10
        "f11": "5分钟涨跌",          # f11
        "f12": "代码",              # f12
        "f13": "市场标识",           # f13 (0=深市, 1=沪市, 90=板块)
        "f14": "名称",              # f14
        "f15": "最高",              # f15
        "f16": "最低",              # f16
        "f17": "今开",              # f17
        "f18": "昨收",              # f18
        "f20": "总市值",            # f20
        "f21": "流通市值",          # f21
        "f22": "涨速",              # f22
        "f23": "市净率",            # f23
        "f24": "60日涨跌幅",        # f24
        "f25": "年初至今涨跌幅",    # f25
        "f38": "总股本",          # f38
        "f39": "流通股本",          # f39
        "f62": "主力净流入",       # f62
        "f100": "行业名称",      # f100
        "f115": "市盈率",       # f115
        "f116": "未知116",          # f116
        "f128": "未知指标128",       # f128    
        "f136": "未知指标136",       # f136
        "f140": "未知指标140",       # f140
        "f141": "未知指标141",       # f141
        "f152": "状态标志",       # f152
    }
    
    # 重命名列：将 f1, f2... 映射为中文列名
    temp_df.rename(columns=field_to_chinese, inplace=True)
    
    temp_df = temp_df[
        [
            "序号",
            "保留",
            "代码",
            "名称",
            "最新价",
            "涨跌幅",
            "涨跌额",
            "成交量",
            "成交额",
            "振幅",
            "最高",
            "最低",
            "今开",
            "昨收",
            "量比",
            "换手率",
            "市盈率-动态",
            "市净率",
            "总市值",
            "流通市值",
            "涨速",
            "5分钟涨跌",
            "60日涨跌幅",
            "年初至今涨跌幅",
            "行业名称",
            "状态标志",
            "市盈率",
            "主力净流入",
            "市场标识",
            "总股本",
            "流通股本",
        ]
    ]
    temp_df["最新价"] = pd.to_numeric(temp_df["最新价"], errors="coerce")
    temp_df["涨跌幅"] = pd.to_numeric(temp_df["涨跌幅"], errors="coerce")
    temp_df["涨跌额"] = pd.to_numeric(temp_df["涨跌额"], errors="coerce")
    temp_df["成交量"] = pd.to_numeric(temp_df["成交量"], errors="coerce")
    temp_df["成交额"] = pd.to_numeric(temp_df["成交额"], errors="coerce")
    temp_df["振幅"] = pd.to_numeric(temp_df["振幅"], errors="coerce")
    temp_df["最高"] = pd.to_numeric(temp_df["最高"], errors="coerce")
    temp_df["最低"] = pd.to_numeric(temp_df["最低"], errors="coerce")
    temp_df["今开"] = pd.to_numeric(temp_df["今开"], errors="coerce")
    temp_df["昨收"] = pd.to_numeric(temp_df["昨收"], errors="coerce")
    temp_df["量比"] = pd.to_numeric(temp_df["量比"], errors="coerce")
    temp_df["换手率"] = pd.to_numeric(temp_df["换手率"], errors="coerce")
    temp_df["市盈率-动态"] = pd.to_numeric(temp_df["市盈率-动态"], errors="coerce")
    temp_df["市净率"] = pd.to_numeric(temp_df["市净率"], errors="coerce")
    temp_df["总市值"] = pd.to_numeric(temp_df["总市值"], errors="coerce")
    temp_df["流通市值"] = pd.to_numeric(temp_df["流通市值"], errors="coerce")
    temp_df["涨速"] = pd.to_numeric(temp_df["涨速"], errors="coerce")
    temp_df["5分钟涨跌"] = pd.to_numeric(temp_df["5分钟涨跌"], errors="coerce")
    temp_df["60日涨跌幅"] = pd.to_numeric(temp_df["60日涨跌幅"], errors="coerce")
    temp_df["年初至今涨跌幅"] = pd.to_numeric(
        temp_df["年初至今涨跌幅"], errors="coerce"
    )
    print("处理后的数据预览:")
    print("="*100)
    #print_first_row(temp_df)
    return temp_df

def fetch_paginated_data_with_resume(
    url: str, 
    base_params: Dict, 
    timeout: int = 15,
    resume_key: Optional[str] = None,
    state_dir: str = "./resume_states",
    max_retries: int = 3,
    progress_callback=None
):
    """
    带断点续传的分页数据获取函数
    
    :param url: 请求URL
    :param base_params: 基础请求参数
    :param timeout: 请求超时时间
    :param resume_key: 断点续传的唯一标识，不指定则自动生成
    :param state_dir: 状态文件保存目录
    :param max_retries: 单页最大重试次数
    :param progress_callback: 进度回调函数，接受 (pct: int, msg: str) 参数
    :return: 合并后的数据
    """
    # 1. 设置断点续传标识
    if resume_key is None:
        # 基于URL和参数生成唯一标识
        import hashlib
        key_str = f"{url}_{json.dumps(base_params, sort_keys=True)}"
        resume_key = hashlib.md5(key_str.encode()).hexdigest()[:16]
    
    # 2. 创建状态目录
    state_dir_path = Path(state_dir)
    state_dir_path.mkdir(exist_ok=True)
    
    # 状态文件路径
    state_file = state_dir_path / f"{resume_key}.state"
    data_file = state_dir_path / f"{resume_key}.data.pkl"
    
    # 3. 检查是否有可恢复的状态
    all_pages_data = []
    start_page = 1
    total_page = 0
    per_page_num = 0
    recovered = False
    
    if state_file.exists():
        try:
            with open(state_file, 'rb') as f:
                state = pickle.load(f)
            
            # 验证状态文件是否过期（比如超过24小时）
            if 'timestamp' in state:
                state_age = time.time() - state['timestamp']
                if state_age > 24 * 3600:  # 24小时
                    print(f"状态文件已过期（{state_age/3600:.1f}小时），重新开始")
                else:
                    # 验证数据格式是否正确
                    saved_data = state.get('data', [])
                    if isinstance(saved_data, list):
                        all_pages_data = saved_data
                        start_page = state.get('current_page', 1)
                        total_page = state.get('total_page', 0)
                        per_page_num = state.get('per_page_num', 0)
                        recovered = True
                        
                        print(f"恢复进度: 从第 {start_page} 页继续")
                        if all_pages_data:
                            print(f"已恢复 {len(all_pages_data)} 页数据，共 {sum(len(df) for df in all_pages_data)} 条记录")
                    else:
                        print("状态文件数据格式错误，重新开始")
                        
        except Exception as e:
            print(f"加载状态文件失败: {e}")
    
    # 4. 复制参数以避免修改原始参数
    params = base_params.copy()
    
    # 5. 获取第一页数据（如果不是恢复状态）
    if not recovered or not all_pages_data:
        print("开始新的数据获取...")
        if progress_callback:
            progress_callback(5, "开始获取第一页...")
        
        retry_count = 0
        while retry_count < max_retries:
            try:
                r = request_with_retry(url, params=params, timeout=timeout)
                data_json = r.json()
                
                # 计算分页信息
                per_page_num = len(data_json["data"]["diff"])
                total_page = math.ceil(data_json["data"]["total"] / per_page_num)
                
                # 添加第一页数据
                first_page_df = pd.DataFrame(data_json["data"]["diff"])
                all_pages_data.append(first_page_df)
                
                print(f"总页数: {total_page}, 每页记录数: {per_page_num}")
                if progress_callback:
                    progress_callback(10, f"第一页完成，共 {total_page} 页待获取")
                break
                
            except Exception as e:
                retry_count += 1
                print(f"获取第一页失败，重试 {retry_count}/{max_retries}: {e}")
                if retry_count == max_retries:
                    raise
                time.sleep(2 ** retry_count)  # 指数退避
    else:
        print(f"恢复状态: 总页数 {total_page}, 从第 {start_page} 页继续")
        if progress_callback:
            progress_callback(10, f"恢复进度，从第 {start_page} 页继续")
    
    from tqdm import tqdm
    # 6. 获取剩余页面数据
    # tqdm = get_tqdm()
    
    # 计算已完成的页数（用于进度计算）
    completed_pages = len(all_pages_data) if all_pages_data else 0
    
    for page in tqdm(range(start_page, total_page + 1), leave=False, desc="分页获取"):
        # 跳过已完成的页面
        if page < start_page:
            continue
            
        # 第一页已处理
        if page == 1 and (recovered or all_pages_data):
            continue
            
        retry_count = 0
        while retry_count <= max_retries:
            try:
                if page > 1:
                    params.update({"pn": page})
                    time.sleep(random.uniform(0.5, 1.5))
                
                # 在发起请求前显示"正在获取"状态
                if progress_callback and total_page > 0:
                    progress_callback(
                        10 + int(85 * completed_pages / total_page), 
                        f"正在获取第 {page}/{total_page} 页..."
                    )
                
                r = request_with_retry(url, params=params, timeout=timeout)
                data_json = r.json()
                
                inner_temp_df = pd.DataFrame(data_json["data"]["diff"])
                all_pages_data.append(inner_temp_df)
                completed_pages += 1
                
                # 获取成功后更新进度
                if progress_callback and total_page > 0:
                    pct = 10 + int(85 * completed_pages / total_page)
                    progress_callback(pct, f"已获取第 {page}/{total_page} 页，共 {len(all_pages_data) * per_page_num} 条记录")
                
                # 保存当前状态
                with open(state_file, 'wb') as f:
                    pickle.dump({
                        'current_page': page,
                        'total_page': total_page,
                        'per_page_num': per_page_num,
                        'data': all_pages_data,
                        'timestamp': time.time(),
                        'url': url,
                        'params': base_params,
                        'resume_key': resume_key
                    }, f)
                
                # 定期保存数据到文件
                if page % 10 == 0 or page == total_page:
                    temp_df = pd.concat(all_pages_data, ignore_index=True)
                    temp_df.to_pickle(data_file)
                    #print(f"已保存第 {page}/{total_page} 页的数据快照")
                
                break
                
            except Exception as e:
                retry_count += 1
                if retry_count <= max_retries:
                    #print(f"第 {page} 页获取失败，{retry_count}/{max_retries} 重试: {e}")
                    time.sleep(2 ** retry_count)  # 指数退避
                else:
                    #print(f"第 {page} 页获取失败，已达最大重试次数")
                    
                    # 保存当前进度以便恢复
                    with open(state_file, 'wb') as f:
                        pickle.dump({
                            'current_page': page - 1,  # 回到上一页
                            'total_page': total_page,
                            'per_page_num': per_page_num,
                            'data': all_pages_data[:-1] if all_pages_data else [],  # 移除失败的一页
                            'timestamp': time.time(),
                            'error': str(e),
                            'url': url,
                            'params': base_params,
                            'resume_key': resume_key
                        }, f)
                    
                    if all_pages_data:
                        temp_df = pd.concat(all_pages_data, ignore_index=True)
                        temp_df.to_pickle(data_file)
                    
                    raise RuntimeError(f"获取第 {page} 页失败: {e}")
    
    # 7. 合并所有数据并进行处理
    if not all_pages_data:
        return pd.DataFrame()
    
    temp_df = pd.concat(all_pages_data, ignore_index=True)
    
    # 8. 数据处理
    if "f3" in temp_df.columns:
        temp_df["f3"] = pd.to_numeric(temp_df["f3"], errors="coerce")
        temp_df.sort_values(by=["f3"], ascending=False, inplace=True, ignore_index=True)
    
    temp_df.reset_index(inplace=True)
    if "index" in temp_df.columns:
        temp_df["index"] = temp_df["index"].astype(int) + 1
    
    # 9. 清理状态文件
    if state_file.exists():
        os.remove(state_file)
    if data_file.exists():
        os.remove(data_file)
    
    print(f"数据获取完成，共获取 {len(temp_df)} 条记录")
    return temp_df


# 添加一个清理过期状态文件的函数
def cleanup_old_states(state_dir: str = "./resume_states", max_age_hours: int = 24):
    """
    清理过期的状态文件
    
    :param state_dir: 状态文件目录
    :param max_age_hours: 最大保留小时数
    """
    state_dir_path = Path(state_dir)
    if not state_dir_path.exists():
        return
    
    current_time = time.time()
    deleted_count = 0
    
    for state_file in state_dir_path.glob("*.state"):
        try:
            with open(state_file, 'rb') as f:
                state = pickle.load(f)
            
            if 'timestamp' in state:
                state_age = current_time - state['timestamp']
                if state_age > max_age_hours * 3600:
                    # 删除对应的数据文件
                    data_file = state_dir_path / f"{state_file.stem}.data.pkl"
                    if data_file.exists():
                        os.remove(data_file)
                    os.remove(state_file)
                    deleted_count += 1
                    
        except Exception as e:
            print(f"清理状态文件 {state_file} 失败: {e}")
    
    if deleted_count > 0:
        print(f"已清理 {deleted_count} 个过期的状态文件")


# 提供一个手动恢复数据的函数
def manual_resume(resume_key: str, state_dir: str = "./resume_states"):
    """
    手动恢复指定任务
    
    :param resume_key: 恢复键
    :param state_dir: 状态文件目录
    :return: 恢复任务所需参数
    """
    state_file = Path(state_dir) / f"{resume_key}.state"
    
    if not state_file.exists():
        raise FileNotFoundError(f"未找到恢复键为 {resume_key} 的状态文件")
    
    with open(state_file, 'rb') as f:
        state = pickle.load(f)
    
    print(f"恢复任务信息:")
    print(f"  URL: {state.get('url')}")
    print(f"  当前页码: {state.get('current_page', 1)}/{state.get('total_page', '未知')}")
    print(f"  已获取页数: {len(state.get('data', []))}")
    print(f"  创建时间: {datetime.fromtimestamp(state.get('timestamp', 0))}")
    
    if 'error' in state:
        print(f"  上次错误: {state.get('error')}")
    
    return {
        'url': state.get('url'),
        'params': state.get('params', {}),
        'resume_key': resume_key
    }
    
def print_first_row(temp_df: pd.DataFrame):
    # 在数据处理后添加日志输出
    if not temp_df.empty:
        # 重命名列
        temp_df.rename(columns={"index": "序号"}, inplace=True)
        
        # 输出一行完整数据用于测试
        if len(temp_df) > 0:
            print("\n" + "="*100)
            print("测试数据 - 第一行完整信息:")
            print("="*100)
            
            # 获取第一行数据
            sample_row = temp_df.iloc[0]
            
            # 按列逐行输出，确保显示完整
            for column in temp_df.columns:
                value = sample_row[column]
                # 格式化输出，限制过长的值
                if isinstance(value, str) and len(value) > 50:
                    value_display = f"{value[:50]}..."
                else:
                    value_display = value
                print(f"{column:20}: {value_display}")
            
            # 输出数据类型和形状信息
            print("-"*100)
            print(f"数据类型: {type(sample_row)}")
            print(f"总行数: {len(temp_df)}")
            print(f"总列数: {len(temp_df.columns)}")
            print("列名列表:", list(temp_df.columns))
            print("="*100)
            
            # 可选：输出DataFrame的头部信息
            print("\n前5行预览:")
            print(temp_df.head().to_string())
            
            # 可选：输出DataFrame的统计信息
            print("\n数据形状:", temp_df.shape)
            print("列信息:")
            print(temp_df.dtypes)
        
        return temp_df
    else:
        print("警告: 获取到的数据为空")
        return pd.DataFrame()

def request_with_retry(
    url: str,
    method: str = "GET",
    params: Optional[Dict] = None,
    data: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    timeout: int = 15,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: tuple = (500, 502, 503, 504),
    session: Optional[requests.Session] = None,
    proxies: Optional[Dict] = None,
    verify: bool = True,
    **kwargs
) -> requests.Response:
    """
    带重试机制的HTTP请求
    
    :param url: 请求URL
    :param method: HTTP方法
    :param params: 查询参数
    :param data: 请求体数据
    :param headers: 请求头
    :param timeout: 超时时间（秒）
    :param max_retries: 最大重试次数
    :param backoff_factor: 退避因子
    :param status_forcelist: 强制重试的HTTP状态码
    :param session: 可重用的Session对象
    :param proxies: 代理设置
    :param verify: SSL验证
    :return: Response对象
    """
    # 默认请求头
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "",
        "Connection": "keep-alive",
    }
    
    # 合并请求头
    if headers:
        default_headers.update(headers)
    headers = default_headers
    
    # 创建或使用现有Session
    if session is None:
        session = requests.Session()
    
    # 配置重试策略
    retry_strategy = Retry(
        total=max_retries,
        read=max_retries,
        connect=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "TRACE"],
        raise_on_status=False  # 不根据状态码抛出异常
    )
    
    # 创建适配器
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    
    # 挂载适配器
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # 请求尝试
    last_exception = None
    
    for attempt in range(max_retries + 1):  # 初始尝试 + 重试次数
        try:
            response = session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=data if method.upper() in ["POST", "PUT", "PATCH"] else None,
                data=data if method.upper() not in ["GET", "DELETE"] else None,
                headers=headers,
                timeout=timeout,
                proxies=proxies,
                verify=verify,
                **kwargs
            )
            
            # 检查HTTP状态码
            response.raise_for_status()
            
            # 验证响应内容
            if response.status_code == 200:
                # 检查响应是否是有效的JSON
                if "application/json" in response.headers.get("Content-Type", ""):
                    try:
                        response.json()  # 验证JSON格式
                    except ValueError as e:
                        raise ValueError(f"无效的JSON响应: {e}")
                
                return response
            else:
                print(f"HTTP {response.status_code}: {response.reason}")
                
        except requests.exceptions.HTTPError as e:
            last_exception = e
            status_code = e.response.status_code if e.response else None
            
            if status_code == 429:  # 请求过多
                wait_time = 5 + attempt * 2
                print(f"请求过多 (429)，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            elif status_code in [403, 404]:
                # 403/404通常不需要重试
                print(f"请求失败: HTTP {status_code} - 可能被阻止或资源不存在")
                raise
            elif attempt < max_retries:
                wait_time = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                print(f"HTTP错误: {e}，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"HTTP错误: {e}，已达最大重试次数")
                raise
                
        except requests.exceptions.ConnectionError as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                print(f"连接错误: {e}，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"连接错误: {e}，已达最大重试次数")
                raise
                
        except requests.exceptions.Timeout as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                print(f"请求超时: {e}，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"请求超时: {e}，已达最大重试次数")
                raise
                
        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                print(f"请求异常: {e}，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"请求异常: {e}，已达最大重试次数")
                raise
                
        except Exception as e:
            last_exception = e
            print(f"未知错误: {e}")
            raise
    
    # 如果所有重试都失败
    raise Exception(f"请求失败，已达最大重试次数: {last_exception}")


# 简单版本的request_with_retry（如果不需要复杂功能）
def simple_request_with_retry(
    url: str,
    params: Optional[Dict] = None,
    timeout: int = 15,
    max_retries: int = 3
) -> requests.Response:
    """
    简化版的带重试请求
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                url=url,
                params=params,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait_time = 1 + attempt * 2
                print(f"请求失败: {e}，{wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                raise Exception(f"请求失败，已达最大重试次数: {e}")
    
    raise Exception("请求失败")

from typing import Callable, Optional
import sys
import time


def get_tqdm():
    """
    获取进度条函数
    如果安装了tqdm库，则使用tqdm，否则使用简易进度条
    """
    try:
        # 尝试导入tqdm
        from tqdm import tqdm
        from tqdm.notebook import tqdm as tqdm_notebook
        
        def is_notebook() -> bool:
            """检查是否在Jupyter notebook环境中运行"""
            try:
                from IPython import get_ipython
                if 'IPKernelApp' not in get_ipython().config:  # 不在notebook中
                    return False
            except:
                return False
            return True
        
        # 根据环境返回合适的tqdm
        if is_notebook():
            return tqdm_notebook
        else:
            return tqdm
            
    except ImportError:
        # 如果没有安装tqdm，使用简易进度条
        class SimpleProgressBar:
            """简易进度条实现"""
            
            def __init__(self, iterable=None, total=None, desc=None, leave=True, 
                        ncols=None, mininterval=0.1, maxinterval=10.0, 
                        miniters=None, ascii=None, disable=False, 
                        unit='it', unit_scale=False, dynamic_ncols=False, 
                        smoothing=0.3, bar_format=None, initial=0, 
                        position=None, postfix=None, unit_divisor=1000, 
                        write_bytes=False, lock_args=None, nrows=None, 
                        colour=None, delay=0, gui=False, **kwargs):
                
                self.iterable = iterable
                self.total = total if total is not None else (len(iterable) if iterable else None)
                self.desc = desc
                self.leave = leave
                self.disable = disable
                self.unit = unit
                self.unit_scale = unit_scale
                self.initial = initial
                self.postfix = postfix
                
                self.n = initial
                self.start_time = time.time()
                self.last_print_time = 0
                self.mininterval = mininterval
                
                if not disable and self.total is not None:
                    self._print_progress()
            
            def _print_progress(self):
                """打印进度信息"""
                if self.disable:
                    return
                    
                current_time = time.time()
                if current_time - self.last_print_time < self.mininterval and self.n != self.total:
                    return
                
                self.last_print_time = current_time
                elapsed = current_time - self.start_time
                
                if self.total:
                    percentage = (self.n / self.total) * 100
                    bar_length = 30
                    filled_length = int(bar_length * self.n // self.total)
                    bar = '█' * filled_length + '─' * (bar_length - filled_length)
                    
                    if elapsed > 0 and self.n > self.initial:
                        speed = (self.n - self.initial) / elapsed
                        eta = (self.total - self.n) / speed if speed > 0 else 0
                        
                        eta_str = f'{eta:.1f}s'
                        if eta > 60:
                            eta_str = f'{eta/60:.1f}m'
                        if eta > 3600:
                            eta_str = f'{eta/3600:.1f}h'
                            
                        speed_str = f'{speed:.2f} {self.unit}/s'
                        if self.unit_scale and speed > 1000:
                            speed_str = f'{speed/1000:.2f}k {self.unit}/s'
                    else:
                        eta_str = '?'
                        speed_str = '?'
                    
                    info = f'{self.desc}: ' if self.desc else ''
                    info += f'{percentage:3.0f}%|{bar}| {self.n}/{self.total} '
                    info += f'[{elapsed:.0f}s<{eta_str}, {speed_str}]'
                    
                    if self.postfix:
                        info += f' {self.postfix}'
                        
                    sys.stdout.write('\r' + info)
                    sys.stdout.flush()
                    
                    if self.n == self.total and self.leave:
                        sys.stdout.write('\n')
                else:
                    # 未知总数的情况
                    info = f'{self.desc}: ' if self.desc else ''
                    info += f'{self.n} {self.unit} [{elapsed:.0f}s, {self.n/elapsed:.2f} {self.unit}/s]'
                    
                    sys.stdout.write('\r' + info)
                    sys.stdout.flush()
            
            def update(self, n=1):
                """更新进度"""
                self.n += n
                self._print_progress()
                return True
            
            def set_postfix(self, **kwargs):
                """设置后缀信息"""
                if kwargs:
                    self.postfix = ', '.join([f'{k}={v}' for k, v in kwargs.items()])
                self._print_progress()
            
            def set_description(self, desc=None, refresh=True):
                """设置描述信息"""
                self.desc = desc
                if refresh:
                    self._print_progress()
            
            def close(self):
                """关闭进度条"""
                if not self.disable and self.leave and self.n == self.total:
                    sys.stdout.write('\n')
                    sys.stdout.flush()
            
            def __iter__(self):
                """迭代支持"""
                if self.iterable is None:
                    raise ValueError("iterable must be provided")
                
                self.n = self.initial
                self.start_time = time.time()
                self.last_print_time = 0
                
                if not self.disable and self.total is not None:
                    self._print_progress()
                
                for obj in self.iterable:
                    yield obj
                    self.n += 1
                    self._print_progress()
                
                if not self.disable and self.leave:
                    sys.stdout.write('\n')
                    sys.stdout.flush()
            
            def __enter__(self):
                return self
            
            def __exit__(self, *args):
                self.close()
        
        return SimpleProgressBar