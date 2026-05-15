#!/usr/bin/env python3
import pandas as pd
import numpy as np
import requests
from typing import Union, List, Optional, Dict, Any, Tuple
import time
from datetime import datetime, timedelta
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class BinanceDownloader:
    """
    Binance 数据下载器，模仿 yfinance.download() 接口
    支持单个 symbol、多个 symbol 以及数组形式的下载
    """
    
    def __init__(self, proxy: Optional[Dict] = None, max_workers: int = 5):
        """
        初始化 Binance 下载器
        
        Args:
            proxy: 代理设置
            max_workers: 并发下载的最大线程数
        """
        self.base_url = "https://api.binance.com/api/v3"
        self.session = requests.Session()
        if proxy:
            self.session.proxies.update(proxy)
        self.max_workers = max_workers
        
        # 时间间隔映射
        self.interval_mapping = {
            '1m': '1m', '2m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
            '60m': '1h', '90m': '1h', '1h': '1h', '1d': '1d', '5d': '1d',
            '1wk': '1w', '1mo': '1M', '3mo': '1M'
        }
        
        # yfinance 标准列名
        self.standard_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        # Binance K线列名映射
        self.binance_columns = [
            ('Open', 'open_time'),
            ('Open', 'open'),
            ('High', 'high'),
            ('Low', 'low'),
            ('Close', 'close'),
            ('Volume', 'volume'),
            ('Close', 'close_time'),
            ('Quote_Asset_Volume', 'quote_asset_volume'),
            ('Number_of_Trades', 'number_of_trades'),
            ('Taker_Buy_Base_Volume', 'taker_buy_base_volume'),
            ('Taker_Buy_Quote_Volume', 'taker_buy_quote_volume'),
            ('Ignore', 'ignore')
        ]
    
    def download(self,
                 tickers: Union[str, List[str]],
                 start: Optional[str] = None,
                 end: Optional[str] = None,
                 period: str = "1mo",
                 interval: str = "1d",
                 auto_adjust: bool = False,
                 prepost: bool = False,
                 threads: bool = True,
                 proxy: Optional[Dict] = None,
                 group_by: str = 'ticker',
                 progress: bool = True,
                 keep_all_columns: bool = True,
                 **kwargs) -> pd.DataFrame:
        """
        下载 Binance 数据，模仿 yfinance.download() 签名
        
        Args:
            tickers: 交易对符号，支持单个字符串、列表或空格分隔的字符串
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            period: 数据期间 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: 数据间隔 (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            auto_adjust: 保留参数（Binance 不适用）
            prepost: 保留参数（Binance 不适用）
            threads: 是否使用多线程
            proxy: 代理设置
            group_by: 分组方式 ('ticker' 或 'column')
            progress: 是否显示进度
            keep_all_columns: 是否保留所有列（包括额外K线数据），默认为True
            **kwargs: 其他参数
            
        Returns:
            pd.DataFrame: 包含历史数据的 DataFrame，结构与 yfinance.download() 完全兼容
        """
        # 1. 解析 tickers
        symbols = self._parse_tickers(tickers)
        
        # 2. 计算实际的时间范围
        start_dt, end_dt, binance_interval = self._calculate_time_range(
            start, end, period, interval
        )
        
        # 3. 下载数据
        if len(symbols) == 1:
            # 单个 symbol
            df = self._download_single_symbol(
                symbols[0], start_dt, end_dt, binance_interval, keep_all_columns
            )
            
            # 单个 symbol 时不需要 MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(0)
                
        else:
            # 多个 symbol
            if threads and len(symbols) > 1:
                data_dict = self._download_multiple_symbols_concurrent(
                    symbols, start_dt, end_dt, binance_interval, keep_all_columns, progress
                )
            else:
                data_dict = self._download_multiple_symbols_sequential(
                    symbols, start_dt, end_dt, binance_interval, keep_all_columns, progress
                )
            
            # 4. 合并数据
            if data_dict:
                df = self._merge_data(data_dict, group_by)
            else:
                return pd.DataFrame()
        
        return df
    
    def _parse_tickers(self, tickers: Union[str, List[str]]) -> List[str]:
        """
        解析 tickers 参数
        """
        if isinstance(tickers, str):
            # 处理空格分隔的字符串
            if ' ' in tickers:
                symbols = [s.strip() for s in tickers.split() if s.strip()]
            else:
                symbols = [tickers]
        elif isinstance(tickers, list):
            symbols = tickers
        else:
            raise ValueError(f"不支持的 tickers 类型: {type(tickers)}")
        
        # 确保所有符号都包含计价货币
        processed_symbols = []
        for symbol in symbols:
            if not symbol.endswith(('USDT', 'BTC', 'ETH', 'BNB', 'BUSD')) or (len(symbol) > 0 and len(symbol) < 5):
                # 默认添加 USDT
                processed_symbols.append(f"{symbol}USDT")
            else:
                processed_symbols.append(symbol)
        
        return processed_symbols
    
    def _calculate_time_range(self,
                             start: Optional[str],
                             end: Optional[str],
                             period: str,
                             interval: str) -> tuple[datetime, datetime, str]:
        """
        计算时间范围和对应的 Binance 间隔
        """
        # 映射间隔到 Binance 格式
        binance_interval = self.interval_mapping.get(interval, interval)
        
        # 处理结束时间
        if end:
            end_dt = pd.to_datetime(end)
        else:
            end_dt = datetime.now()
        
        # 处理开始时间
        if start:
            start_dt = pd.to_datetime(start)
        else:
            # 基于 period 计算
            period_map = {
                '1d': timedelta(days=1),
                '5d': timedelta(days=5),
                '1mo': timedelta(days=30),
                '3mo': timedelta(days=90),
                '6mo': timedelta(days=180),
                '1y': timedelta(days=365),
                '2y': timedelta(days=730),
                '5y': timedelta(days=1825),
                '10y': timedelta(days=3650),
                'ytd': timedelta(days=(end_dt - datetime(end_dt.year, 1, 1)).days),
                'max': timedelta(days=365 * 20)  # 20年
            }
            delta = period_map.get(period, timedelta(days=30))
            start_dt = end_dt - delta
        
        # 确保开始时间不晚于结束时间
        if start_dt >= end_dt:
            start_dt = end_dt - timedelta(days=30)
        
        return start_dt, end_dt, binance_interval
    
    def _download_single_symbol(self,
                               symbol: str,
                               start_dt: datetime,
                               end_dt: datetime,
                               interval: str,
                               keep_all_columns: bool = True) -> pd.DataFrame:
        """
        下载单个 symbol 的数据
        """
        try:
            logger.info(f"下载 {symbol} 数据: {start_dt.date()} 到 {end_dt.date()}, 间隔 {interval}")
            
            # 获取所有K线数据
            all_klines = self._fetch_all_klines(symbol, start_dt, end_dt, interval)
            
            if not all_klines:
                logger.warning(f"未获取到 {symbol} 的数据")
                return pd.DataFrame()
            
            # 转换为 DataFrame
            df = self._klines_to_dataframe(all_klines, symbol, keep_all_columns)
            
            logger.info(f"成功下载 {symbol}: {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"下载 {symbol} 失败: {e}")
            return pd.DataFrame()
    
    def _fetch_all_klines(self,
                          symbol: str,
                          start_dt: datetime,
                          end_dt: datetime,
                          interval: str,
                          limit: int = 1000) -> List[List]:
        """
        获取所有K线数据（处理分页）
        """
        all_klines = []
        current_start = int(start_dt.timestamp() * 1000)
        end_timestamp = int(end_dt.timestamp() * 1000)
        
        # 间隔对应的毫秒数
        interval_ms = {
            '1m': 60000, '3m': 180000, '5m': 300000, '15m': 900000,
            '30m': 1800000, '1h': 3600000, '2h': 7200000, '4h': 14400000,
            '6h': 21600000, '8h': 28800000, '12h': 43200000,
            '1d': 86400000, '3d': 259200000, '1w': 604800000,
            '1M': 2592000000
        }.get(interval, 86400000)
        
        while current_start < end_timestamp:
            try:
                # 计算本次请求的结束时间
                current_end = min(current_start + limit * interval_ms, end_timestamp)
                
                params = {
                    'symbol': symbol,
                    'interval': interval,
                    'startTime': current_start,
                    'endTime': current_end,
                    'limit': limit
                }
                
                response = self.session.get(f"{self.base_url}/klines", params=params)
                response.raise_for_status()
                klines = response.json()
                
                if not klines:
                    break
                
                all_klines.extend(klines)
                
                # 更新开始时间（最后一条数据的时间 + 1个间隔）
                last_time = klines[-1][0]
                current_start = last_time + interval_ms
                
                # 防止频繁请求
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"获取 {symbol} K线数据失败: {e}")
                break
        
        return all_klines
    
    def _klines_to_dataframe(self, klines: List[List], symbol: str, keep_all_columns: bool = True) -> pd.DataFrame:
        """
        将K线数据转换为 DataFrame
        
        Args:
            klines: Binance K线数据
            symbol: 交易对符号
            keep_all_columns: 是否保留所有列
            
        Returns:
            pd.DataFrame: 转换后的 DataFrame
        """
        if not klines:
            return pd.DataFrame()
        
        # 解析K线数据
        data = []
        for k in klines:
            try:
                row = {
                    'open_time': pd.to_datetime(k[0], unit='ms'),
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5]),
                    'close_time': pd.to_datetime(k[6], unit='ms'),
                    'quote_asset_volume': float(k[7]),
                    'number_of_trades': int(k[8]),
                    'taker_buy_base_volume': float(k[9]),
                    'taker_buy_quote_volume': float(k[10]),
                }
                data.append(row)
            except (IndexError, ValueError) as e:
                logger.warning(f"解析K线数据失败: {e}")
                continue
        
        df = pd.DataFrame(data)
        
        if df.empty:
            return df
        
        # 设置索引为 open_time
        df.set_index('open_time', inplace=True)
        
        # 重命名列为标准名称
        rename_map = {
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume',
            'close_time': 'Close_time',
            'quote_asset_volume': 'Quote_Asset_Volume',
            'number_of_trades': 'Number_of_Trades',
            'taker_buy_base_volume': 'Taker_Buy_Base_Volume',
            'taker_buy_quote_volume': 'Taker_Buy_Quote_Volume',
        }
        
        # 选择要保留的列
        if keep_all_columns:
            # 保留所有列
            df = df.rename(columns=rename_map)
        else:
            # 只保留标准列
            standard_columns_map = {k: v for k, v in rename_map.items() 
                                   if v in self.standard_columns}
            df = df[list(standard_columns_map.keys())].rename(columns=standard_columns_map)
        
        # 添加 MultiIndex 列
        columns = []
        for col in df.columns:
            columns.append((symbol, col))
        
        df.columns = pd.MultiIndex.from_tuples(columns)
        
        return df
    
    def _download_multiple_symbols_concurrent(self,
                                             symbols: List[str],
                                             start_dt: datetime,
                                             end_dt: datetime,
                                             interval: str,
                                             keep_all_columns: bool,
                                             progress: bool) -> Dict[str, pd.DataFrame]:
        """
        并发下载多个 symbol
        """
        data_dict = {}
        
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(symbols))) as executor:
            # 提交所有任务
            future_to_symbol = {
                executor.submit(
                    self._download_single_symbol, symbol, start_dt, end_dt, interval, keep_all_columns
                ): symbol
                for symbol in symbols
            }
            
            # 收集结果
            completed = 0
            total = len(symbols)
            
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    df = future.result()
                    if not df.empty:
                        data_dict[symbol] = df
                    
                    completed += 1
                    if progress:
                        logger.info(f"进度: {completed}/{total} ({symbol} 完成)")
                        
                except Exception as e:
                    logger.error(f"下载 {symbol} 时出错: {e}")
        
        return data_dict
    
    def _download_multiple_symbols_sequential(self,
                                             symbols: List[str],
                                             start_dt: datetime,
                                             end_dt: datetime,
                                             interval: str,
                                             keep_all_columns: bool,
                                             progress: bool) -> Dict[str, pd.DataFrame]:
        """
        顺序下载多个 symbol
        """
        data_dict = {}
        
        for i, symbol in enumerate(symbols, 1):
            if progress:
                logger.info(f"下载进度: {i}/{len(symbols)} ({symbol})")
            
            df = self._download_single_symbol(symbol, start_dt, end_dt, interval, keep_all_columns)
            if not df.empty:
                data_dict[symbol] = df
        
        return data_dict
    
    def _merge_data(self, data_dict: Dict[str, pd.DataFrame], group_by: str) -> pd.DataFrame:
        """
        合并多个 symbol 的数据，确保与 yfinance 兼容
        
        Args:
            data_dict: 包含各个 symbol 数据的字典
            group_by: 分组方式
            
        Returns:
            pd.DataFrame: 合并后的 DataFrame
        """
        if not data_dict:
            return pd.DataFrame()
        
        # 获取所有时间点
        all_indices = []
        for df in data_dict.values():
            all_indices.extend(df.index)
        
        # 去重并排序
        all_indices = pd.DatetimeIndex(sorted(set(all_indices)))
        
        # 重新索引每个 DataFrame
        aligned_dfs = []
        for symbol, df in data_dict.items():
            # 重新索引以对齐时间
            df_aligned = df.reindex(all_indices)
            aligned_dfs.append(df_aligned)
        
        # 合并所有 DataFrame
        result = pd.concat(aligned_dfs, axis=1)
        
        # 根据 group_by 参数排序列
        if group_by == 'ticker':
            # 按 ticker 分组，这是默认的 yfinance 行为
            # 列已经是 (symbol, metric) 格式，保持原样
            result = result.sort_index(axis=1, level=0)
        elif group_by == 'column':
            # 按列分组，交换层级
            result = result.swaplevel(0, 1, axis=1)
            result = result.sort_index(axis=1, level=0)
        elif group_by is None:
            # 保持原样
            pass
        else:
            logger.warning(f"未知的 group_by 参数: {group_by}，使用默认分组方式")
        
        return result


def binance_download(tickers: Union[str, List[str]],
                     start: Optional[str] = None,
                     end: Optional[str] = None,
                     period: str = "1mo",
                     interval: str = "1d",
                     auto_adjust: bool = False,
                     prepost: bool = False,
                     threads: bool = True,
                     proxy: Optional[Dict] = None,
                     group_by: str = 'ticker',
                     progress: bool = True,
                     keep_all_columns: bool = True,
                     **kwargs) -> pd.DataFrame:
    """
    Binance 数据下载函数，模仿 yfinance.download() 接口
    
    Args:
        tickers: 交易对符号，支持单个字符串、列表或空格分隔的字符串
        start: 开始日期 (YYYY-MM-DD)
        end: 结束日期 (YYYY-MM-DD)
        period: 数据期间
        interval: 数据间隔
        auto_adjust: 保留参数
        prepost: 保留参数
        threads: 是否使用多线程
        proxy: 代理设置
        group_by: 分组方式 ('ticker' 或 'column')
        progress: 是否显示进度
        keep_all_columns: 是否保留所有列（包括额外K线数据），默认为True
        **kwargs: 其他参数
        
    Returns:
        pd.DataFrame: 包含历史数据的 DataFrame，结构与 yfinance.download() 完全兼容
        
    Example:
        >>> # 单个 symbol，保留所有列
        >>> btc_data = binance_download("BTCUSDT", period="7d", interval="1d", keep_all_columns=True)
        >>> print(btc_data.columns)
        >>> # Index(['Open', 'High', 'Low', 'Close', 'Volume', 'Close_time', 
        >>> #        'Quote_Asset_Volume', 'Number_of_Trades', 
        >>> #        'Taker_Buy_Base_Volume', 'Taker_Buy_Quote_Volume'], dtype='object')
        >>>
        >>> # 单个 symbol，只保留标准列
        >>> btc_simple = binance_download("BTCUSDT", period="7d", interval="1d", keep_all_columns=False)
        >>> print(btc_simple.columns)
        >>> # Index(['Open', 'High', 'Low', 'Close', 'Volume'], dtype='object')
        >>>
        >>> # 多个 symbol，保留所有列
        >>> data = binance_download(["BTCUSDT", "ETHUSDT"], period="7d", interval="1d", keep_all_columns=True)
        >>> print(data.columns[:15])  # 显示前15列
        >>> # MultiIndex([('BTCUSDT', 'Open'),
        >>> #             ('BTCUSDT', 'High'),
        >>> #             ('BTCUSDT', 'Low'),
        >>> #             ('BTCUSDT', 'Close'),
        >>> #             ('BTCUSDT', 'Volume'),
        >>> #             ('BTCUSDT', 'Close_time'),
        >>> #             ('BTCUSDT', 'Quote_Asset_Volume'),
        >>> #             ('BTCUSDT', 'Number_of_Trades'),
        >>> #             ('BTCUSDT', 'Taker_Buy_Base_Volume'),
        >>> #             ('BTCUSDT', 'Taker_Buy_Quote_Volume'),
        >>> #             ('ETHUSDT', 'Open'),
        >>> #             ('ETHUSDT', 'High'),
        >>> #             ('ETHUSDT', 'Low'),
        >>> #             ('ETHUSDT', 'Close'),
        >>> #             ('ETHUSDT', 'Volume')])
    """
    downloader = BinanceDownloader(proxy=proxy)
    return downloader.download(
        tickers=tickers,
        start=start,
        end=end,
        period=period,
        interval=interval,
        auto_adjust=auto_adjust,
        prepost=prepost,
        threads=threads,
        proxy=proxy,
        group_by=group_by,
        progress=progress,
        keep_all_columns=keep_all_columns,
        **kwargs
    )
    
"""
Binance Spot 历史K线数据管理脚本
1. 下载
2. 检查 & 修复缺失
3. 下载 + 修复

时间范围：2017-01 ~ 2026-04
支持多个交易对 & 多周期

Usage:
# safe
python binance_downloader.py --mode repair

# safe check and repair all symbols's 1d Dataframe files
python binance_downloader.py  --intervals 1d --mode repair

python binance_downloader.py

python binance_downloader.py \
  --mode download \
  --symbols BTCUSDT ETHUSDT \
  --intervals 1d 4h

python binance_downloader.py \
  --mode repair \
  --symbols SOLUSDT \
  --intervals 1m

python binance_downloader.py \
  --mode both \
  --symbols BTCUSDT
"""
import os
import requests
import time
from tqdm import tqdm
from urllib.parse import urljoin
from datetime import datetime
from typing import List
import argparse

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT",
    "TRXUSDT", "DOGEUSDT", "ADAUSDT", "WBTCUSDT", "ZECUSDT",
    "BCHUSDT", "WBETHUSDT", "XLMUSDT", "LINKUSDT", "TONUSDT",
    "HBARUSDT", "LTCUSDT", "AVAXUSDT", "SUIUSDT", "SHIBUSDT",
    "TAOUSDT", "UNIUSDT", "XAUTUSDT", "PAXGUSDT", "DOTUSDT",
    "WLFIUSDT", "NEARUSDT", "SKYUSDT", "ASTERUSDT", "PEPEUSDT",
    "ONDOUSDT", "ICPUSDT", "TRUMPUSDT", "AAVEUSDT", "ETCUSDT",
    "FILUSDT",
]

DEFAULT_SYMBOLS_START = {
    # 老币（Binance 上线早）
    "BTCUSDT": ("2017", "08"),
    "ETHUSDT": ("2017", "08"),
    "LTCUSDT": ("2017", "12"),
    "BNBUSDT": ("2017", "11"),

    # 主流
    "XRPUSDT": ("2018", "05"),
    "ADAUSDT": ("2018", "04"),
    "TRXUSDT": ("2018", "06"),
    "DOGEUSDT": ("2019", "07"),

    # DeFi / Layer1
    "SOLUSDT": ("2020", "08"),
    "AVAXUSDT": ("2020", "09"),
    "DOTUSDT": ("2020", "08"),
    "LINKUSDT": ("2019", "01"),

    # 稳定 / 资产类
    "WBTCUSDT": ("2023", "04"),
    "WBETHUSDT": ("2023", "07"),
    "XAUTUSDT": ("2026", "03"),
    "PAXGUSDT": ("2020", "08"),

    # 其它
    "ZECUSDT": ("2019", "03"),
    "BCHUSDT": ("2019", "11"),
    "XLMUSDT": ("2018", "05"),
    "TONUSDT": ("2024", "08"),
    "HBARUSDT": ("2019", "09"),
    "SUIUSDT": ("2023", "05"),
    "SHIBUSDT": ("2021", "05"),
    "TAOUSDT": ("2024", "04"),
    "UNIUSDT": ("2020", "09"),
    "NEARUSDT": ("2020", "10"),
    "SKYUSDT": ("2025", "09"),
    "ASTERUSDT": ("2025", "10"),
    "PEPEUSDT": ("2023", "05"),
    "ONDOUSDT": ("2025", "04"),
    "ICPUSDT": ("2021", "05"),
    "TRUMPUSDT": ("2025", "01"),
    "AAVEUSDT": ("2020", "10"),
    "ETCUSDT": ("2018", "06"),
    "FILUSDT": ("2020", "10"),
    "WLFIUSDT": ("2025", "09"),
}


DEFAULT_INTERVALS = ["1d", "4h", "1h", "15m", "5m", "1m"]

# ✅ 关键：基于当前 config.py 所在目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))

DATA_DIR = os.path.join(PROJECT_ROOT, "binance_data")

# ── 初始化日志系统 ───────────────────────────────────────────
from utils.logger import setup_logger, logger
setup_logger()

#from logger import logger

# ======================
# 工具函数
# ======================
def generate_months(start_year, start_month, end_year=2026, end_month=4):
    months = []
    for year in range(int(start_year), end_year + 1):
        first_month = int(start_month) if year == int(start_year) else 1
        last_month = 12 if year != end_year else end_month

        for month in range(first_month, last_month + 1):
            months.append((year, f"{month:02d}"))
    return months

# ======================
# Klines 主下载逻辑
# ======================
def download_klines(symbols, intervals):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for symbol in symbols:
        if symbol not in DEFAULT_SYMBOLS_START:
            logger.warning(f"未配置起始时间，跳过 {symbol}")
            continue

        start_year, start_month = DEFAULT_SYMBOLS_START[symbol]
        months = generate_months(start_year, start_month)

        for interval in intervals:
            for year, month in tqdm(months, desc=f"{symbol}-{interval}"):
                filename = f"{symbol}-{interval}-{year}-{month}.zip"
                url = urljoin(BASE_URL + "/", f"{symbol}/{interval}/{filename}")
                dir_path = os.path.join(DATA_DIR, symbol, interval)
                os.makedirs(dir_path, exist_ok=True)
                path = os.path.join(dir_path, filename)

                if os.path.exists(path):
                    continue

                try:
                    r = session.get(url, timeout=30)
                    if r.status_code == 200:
                        with open(path, "wb") as f:
                            f.write(r.content)
                        logger.info(f"Downloaded {filename}")
                except Exception as e:
                    logger.error(f"Error {filename}: {e}")

                time.sleep(0.2)
                
# ======================
# 检查与修复下载核心逻辑
# ======================
def check_and_repair(symbols, intervals):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for symbol in symbols:
        if symbol not in DEFAULT_SYMBOLS_START:
            logger.warning(f"未配置起始时间，跳过 {symbol}")
            continue

        start_year, start_month = DEFAULT_SYMBOLS_START[symbol]
        months = generate_months(start_year, start_month)

        for interval in intervals:
            for year, month in tqdm(months, desc=f"{symbol}-{interval}"):
                filename = f"{symbol}-{interval}-{year}-{month}.zip"
                dir_path = os.path.join(DATA_DIR, symbol, interval)
                os.makedirs(dir_path, exist_ok=True)
                path = os.path.join(DATA_DIR, symbol, interval, filename)

                if os.path.exists(path):
                    continue

                url = urljoin(BASE_URL + "/", f"{symbol}/{interval}/{filename}")

                try:
                    r = session.get(url, timeout=30)
                    if r.status_code == 200:
                        with open(path, "wb") as f:
                            f.write(r.content)
                        logger.info(f"Repaired {filename}")
                except Exception as e:
                    logger.error(f"Error {filename}: {e}")

                time.sleep(0.2)
def _get_binance_data_urls(symbols:str = DEFAULT_SYMBOLS, intervals:str = DEFAULT_INTERVALS) -> List[str]:
    """
    根据 Binance 数据的下载 URL 列表，加密货币数据的下载
    """
    from core.app_state import get_state
    import os
    
    # 从应用状态获取配置
    #reg_name = get_state().reg_name
    #symbols = get_state().crypto_symbols  # 假设在状态中有这个字段
    #intervals = get_state().crypto_intervals  # 假设在状态中有这个字段
    
    # 如果没有配置，使用默认值
    if not symbols:
        symbols = DEFAULT_SYMBOLS
    
    if not intervals:
        intervals = DEFAULT_INTERVALS
    
    # 起始时间配置
    symbol_start_config = {
        "BTCUSDT": ("2017", "08"),
        "ETHUSDT": ("2017", "08"),
        "LTCUSDT": ("2017", "12"),
        "BNBUSDT": ("2017", "11"),
        "XRPUSDT": ("2018", "05"),
        "ADAUSDT": ("2018", "04"),
        "TRXUSDT": ("2018", "06"),
        "DOGEUSDT": ("2019", "07"),
        "SOLUSDT": ("2020", "08"),
        "AVAXUSDT": ("2020", "09"),
        "DOTUSDT": ("2020", "08"),
        "LINKUSDT": ("2019", "01"),
        "WBTCUSDT": ("2023", "04"),
        "WBETHUSDT": ("2023", "07"),
        "XAUTUSDT": ("2026", "03"),
        "PAXGUSDT": ("2020", "08"),
        "ZECUSDT": ("2019", "03"),
        "BCHUSDT": ("2019", "11"),
        "XLMUSDT": ("2018", "05"),
        "TONUSDT": ("2024", "08"),
        "HBARUSDT": ("2019", "09"),
        "SUIUSDT": ("2023", "05"),
        "SHIBUSDT": ("2021", "05"),
        "TAOUSDT": ("2024", "04"),
        "UNIUSDT": ("2020", "09"),
        "NEARUSDT": ("2020", "10"),
        "SKYUSDT": ("2025", "09"),
        "ASTERUSDT": ("2025", "10"),
        "PEPEUSDT": ("2023", "05"),
        "ONDOUSDT": ("2025", "04"),
        "ICPUSDT": ("2021", "05"),
        "TRUMPUSDT": ("2025", "01"),
        "AAVEUSDT": ("2020", "10"),
        "ETCUSDT": ("2018", "06"),
        "FILUSDT": ("2020", "10"),
        "WLFIUSDT": ("2025", "09"),
    }
    
    def generate_months(start_year, start_month, end_year=2026, end_month=4):
        """生成月份列表"""
        months = []
        for year in range(int(start_year), end_year + 1):
            first_month = int(start_month) if year == int(start_year) else 1
            last_month = 12 if year != end_year else end_month

            for month in range(first_month, last_month + 1):
                months.append((year, f"{month:02d}"))
        return months
    
    # 收集所有要下载的URL
    base_url = "https://data.binance.vision/data/spot/monthly/klines"
    all_urls = []
    
    for symbol in symbols:
        if symbol not in symbol_start_config:
            logger.warning(f"未配置起始时间，跳过 {symbol}")
            continue
        
        start_year, start_month = symbol_start_config[symbol]
        months = generate_months(start_year, start_month)
        
        for interval in intervals:
            for year, month in months:
                filename = f"{symbol}-{interval}-{year}-{month}.zip"
                url = f"{base_url}/{symbol}/{interval}/{filename}"
                all_urls.append(url)
    
    # 记录信息
    from utils.logger import logger
    logger.info(f"准备下载 {len(all_urls)} 个加密货币数据文件")
    logger.info(f"涉及 {len(symbols)} 个交易对: {', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}")
    logger.info(f"时间周期: {', '.join(intervals)}")
    
    return all_urls

def parse_args():
    parser = argparse.ArgumentParser(description="Binance Kline Data Tool")

    parser.add_argument(
        "--mode",
        choices=["download", "repair", "both"],
        default="both",
        help="运行模式"
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="币种列表，如 BTCUSDT ETHUSDT"
    )

    parser.add_argument(
        "--intervals",
        nargs="+",
        default=DEFAULT_INTERVALS,
        help="时间周期，如 1d 1h 5m"
    )

    return parser.parse_args()

# -- binance 历史行情支持 ----------------
import pandas as pd
from binance.client import Client
from datetime import datetime, timedelta
import time

def get_crypto_data_binance(ticker: str, start_date: str, end_date: str, interval: str = "1d") -> pd.DataFrame:
    """
    通过 Binance API 获取加密货币数据
    """
    try:
        # 初始化客户端（公共API不需要密钥）
        client = Client("", "")
        
        # 转换时间格式
        start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)
        
        # 获取K线数据
        klines = client.get_historical_klines(
            symbol=ticker.replace("USDT", "USDT"),  # 确保格式正确
            interval=interval,
            start_str=start_ts,
            end_str=end_ts
        )
        
        if not klines:
            return None
        
        # 转换为DataFrame
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # 转换数据类型
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
        
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 
                       'quote_asset_volume', 'taker_buy_base_asset_volume', 
                       'taker_buy_quote_asset_volume']
        df[numeric_cols] = df[numeric_cols].astype(float)
        df[['number_of_trades']] = df[['number_of_trades']].astype(int)
        
        # 设置索引
        df.set_index('open_time', inplace=True)
        df.index.name = 'date'
        
        # 重命名列
        df = df[['open', 'high', 'low', 'close', 'volume']]
        df.columns = [c.lower() for c in df.columns]
        
        logger.debug(f"[MarketData] {ticker} via Binance API，{len(df)} 条")
        return df
        
    except Exception as e:
        logger.debug(f"[MarketData] Binance API 失败 {ticker}：{e}")
        return None

def main():
    args = parse_args()

    print(f"模式: {args.mode}")
    print(f"币种: {args.symbols}")
    print(f"周期: {args.intervals}")

    if args.mode in ("download", "both"):
        download_klines(args.symbols, args.intervals)

    if args.mode in ("repair", "both"):
        check_and_repair(args.symbols, args.intervals)

if __name__ == "__main__":
    main()
