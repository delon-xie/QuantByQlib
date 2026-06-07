# services/qlib_instruments_updater.py
import pandas as pd
import numpy as np
from pathlib import Path
import re
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from loguru import logger
import warnings
        
import time
import random
from requests.exceptions import ConnectionError, ReadTimeout
from services.akshare_pro import AKSharePro
warnings.filterwarnings('ignore')


class QLibInstrumentsUpdater:
    """QLib Instruments更新器 - 包含完整的股票基础信息"""
    
    def __init__(self, qlib_root: str = "~/.qlib/qlib_data/cn_data"):
        """
        初始化
        :param qlib_root: QLib数据根目录
        """
        self.qlib_root = Path(qlib_root).expanduser()
        self.instruments_dir = self.qlib_root / "instruments"
        self.cache_dir = self.qlib_root / "cache"
        # ★ 全局配置 —— 通过核心库 API 配置浏览器伪装
        self._akp = AKSharePro(debug=False)
        
        # 确保目录存在
        self.instruments_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 完整的字段映射（来自StockSpotCSVExporter）
        self.field_mapping = {
            '序号': 'index',
            '代码': 'symbol',
            '名称': 'name', 
            '最新价': 'latest_price',
            '涨跌幅': 'change_pct',
            '涨跌额': 'change_amount',
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude',
            '最高': 'high',
            '最低': 'low',
            '今开': 'open',
            '昨收': 'prev_close',
            '量比': 'volume_ratio',
            '换手率': 'turnover_rate',
            '市盈率-动态': 'pe_dynamic',
            '市净率': 'pb',
            '总市值': 'total_market_value',
            '流通市值': 'circ_market_value',
            '涨速': 'rise_speed',
            '5分钟涨跌': 'change_5min',
            '60日涨跌幅': 'change_60d',
            '年初至今涨跌幅': 'change_ytd',
            '更新时间': 'update_time',
            '所属行业代码': 'industry_code',
            '行业名称': 'industry_name',
        }
        
        # QLib Instruments 必须列
        self.qlib_required_columns = [
            'instrument', 'symbol', 'name', 'industry', 
            'list_date', 'end_date', 'market'
        ]
        
        # 缓存文件路径
        self.full_data_cache = self.cache_dir / "full_a_share_data.parquet"
        self.is_fetched = False

    def fetch_full_a_share_data(self, force_refresh: bool = False, max_retries: int = 3, progress_callback=None) -> pd.DataFrame:
        """
        获取完整的A股数据（带重试机制）
        
        :param force_refresh: 是否强制刷新（跳过缓存）
        :param max_retries: 最大重试次数
        :param progress_callback: 进度回调函数，接受 (pct: int, msg: str) 参数
        """
        if not force_refresh and self.full_data_cache.exists():
            logger.info(f"从缓存加载完整A股数据: {self.full_data_cache}")
            df = pd.read_parquet(self.full_data_cache)
            
            # 检查缓存是否过期（超过2小时）
            cache_time = datetime.fromtimestamp(self.full_data_cache.stat().st_mtime)
            if (datetime.now() - cache_time).seconds < 7200:  # 2小时
                self.is_fetched = True
                return df
            else:
                logger.info("缓存已过期，重新获取数据")
        
        logger.info("从AKShare获取完整A股数据...")
        
        for attempt in range(max_retries):
            try:
                # 添加随机延迟，避免被识别为爬虫
                if attempt > 0:
                    delay = random.uniform(5, 15)  # 5-15秒延迟
                    logger.info(f"第{attempt+1}次重试，等待{delay:.1f}秒...")
                    time.sleep(delay)
                
                # 设置更长的超时时间
                raw_df = self._akp.stock_zh_a_spot_em(progress_callback=progress_callback)
                logger.info(f"获取成功，共 {len(raw_df)} 条记录")
                
                # 标准化处理
                df = self._standardize_full_data(raw_df)
                
                # 缓存数据
                df.to_parquet(self.full_data_cache, index=False)
                logger.info(f"已缓存完整数据: {self.full_data_cache}")
                self.is_fetched = True
                return df
                
            except (ConnectionError, ReadTimeout, Exception) as e:
                logger.warning(f"第{attempt+1}次获取失败: {e}")
                
                if attempt == max_retries - 1:  # 最后一次尝试也失败
                    logger.error(f"所有{max_retries}次尝试都失败")
                    if self.full_data_cache.exists():
                        logger.info("使用缓存数据")
                        return pd.read_parquet(self.full_data_cache)
                    raise
        
        self.is_fetched = False
        # 如果所有重试都失败，返回空DataFrame
        return pd.DataFrame()    
    def _standardize_full_data(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化完整数据格式
        """
        df = raw_df.copy()
        
        # 获取当前更新时间
        update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. 重命名列（中文->英文）
        column_rename = {}
        for cn_name, en_name in self.field_mapping.items():
            if cn_name in df.columns:
                column_rename[cn_name] = en_name
        
        if column_rename:
            df = df.rename(columns=column_rename)
        
        # 2. 添加QLib instrument格式
        def to_instrument(symbol: str) -> str:
            if not isinstance(symbol, str):
                symbol = str(symbol)
            symbol = symbol.zfill(6)
            
            if symbol.startswith('6'):
                return f"sh{symbol}"
            elif symbol.startswith('0'):
                return f"sz{symbol}"
            elif symbol.startswith('3'):
                return f"sz{symbol}"
            elif symbol.startswith('4') or symbol.startswith('8'):
                return f"bj{symbol}"
            return symbol
        
        df['instrument'] = df['symbol'].apply(to_instrument)
        
        # 3. 数据类型转换
        numeric_cols = [
            'latest_price', 'change_pct', 'change_amount', 'volume', 'amount',
            'amplitude', 'high', 'low', 'open', 'prev_close', 'volume_ratio',
            'turnover_rate', 'pe_dynamic', 'pb', 'total_market_value',
            'circ_market_value', 'rise_speed', 'change_5min', 'change_60d', 'change_ytd'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        if 'index' in df.columns:
            df['index'] = pd.to_numeric(df['index'], errors='coerce').fillna(0).astype('int64')
        
        # 4. 添加QLib所需列
        df['update_time'] = update_time
        df['trade_date'] = datetime.now().strftime("%Y%m%d")
        
        # 5. 添加行业信息（从名称推断，可后续补充）
        if 'industry' not in df.columns:
            df['industry'] = ''
        
        # 6. 添加上市日期（占位，可后续从其他数据源补充）
        if 'list_date' not in df.columns:
            df['list_date'] = ''
        
        # 7. 设置结束日期
        df['end_date'] = '20991231'
        
        # 8. 添加市场类型
        df['market'] = df['instrument'].apply(
            lambda x: 'SH' if x.startswith('sh') else ('CYB' if x[2:3] in ['3'] else 'SZ' if x.startswith('sz') else 'BJ')
        )
        
        # 9. ST标记
        df['is_st'] = df['name'].astype(str).str.contains(r'ST|\*ST|退', na=False)
        
        # 10. 清理和去重
        df = df[df['instrument'].notna()]
        df = df.drop_duplicates(subset=['instrument'], keep='first')
        
        # 重新排序列
        all_columns = self.qlib_required_columns + [
            'pe_dynamic', 'pb', 'total_market_value', 'circ_market_value',
            'latest_price', 'change_pct', 'volume', 'amount', 'turnover_rate',
            'update_time', 'is_st', 'trade_date', 'industry_code', 'industry_name',
        ]
        
        # 只保留存在的列
        available_columns = [col for col in all_columns if col in df.columns]
        df = df[available_columns]
        
        return df
    
    def parse_txt_instruments(self, txt_path: Path) -> List[str]:
        """
        解析TXT文件，提取股票代码
        格式：tab分隔，第一个字段为股票代码
        """
        if not txt_path.exists():
            logger.warning(f"TXT文件不存在: {txt_path}")
            return []
        
        instruments = []
        seen = set()
        
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split('\t')
                    if not parts:
                        continue
                    
                    code = parts[0].strip().lower()
                    
                    if self._is_valid_instrument(code):
                        if code not in seen:
                            seen.add(code)
                            instruments.append(code)
                    
            logger.info(f"从 {txt_path.name} 解析出 {len(instruments)} 个代码")
            return instruments
            
        except Exception as e:
            logger.error(f"解析文件失败: {e}")
            return []
    
    def _is_valid_instrument(self, code: str) -> bool:
        """验证instrument格式"""
        pattern = r'^(sh|sz|bj)\d{6}$'
        return bool(re.match(pattern, str(code).lower()))
    
    def batch_update_instruments_csv(self, 
                                    use_full_data: bool = True,
                                    export_details: bool = True,
                                    progress_callback  = None) -> Dict[str, Dict]:
        """
        批量更新所有TXT对应的CSV文件
        返回: {文件名: {股票数: int, 文件路径: str}}
        """
        # 获取数据
        if use_full_data and self.is_fetched == False:
            df = self.fetch_full_a_share_data(progress_callback=progress_callback)
        elif self.is_fetched == False:
            # 只获取基础信息
            df = self._get_basic_info_only(progress_callback=progress_callback)
        
        results = {}
        
        # 查找所有TXT文件
        txt_files = list(self.instruments_dir.glob("*.txt"))
        logger.info(f"找到 {len(txt_files)} 个TXT文件")
        
        for txt_file in txt_files:
            if txt_file.name.endswith("_backup.txt") or txt_file.name.endswith("bak.txt") or txt_file.name.endswith(".fields.txt"):
                continue
            
            # 解析TXT获取代码列表
            instruments = self.parse_txt_instruments(txt_file)
            if not instruments:
                logger.warning(f"{txt_file.name}: 无有效代码")
                continue
            
            # 生成CSV文件名
            csv_name = txt_file.stem + ".csv"
            csv_path = self.instruments_dir / csv_name
            
            # 过滤并生成CSV
            csv_info = self._generate_integrated_csv(
                instruments, df, csv_path, txt_file.name, export_details
            )
            
            results[csv_name] = csv_info
        
        results['golobal_total'] = {
            '股票数': len(df),
            '文件路径': '',
            '更新时间': 'N/A'
        }
        
        return results
    
    def _generate_integrated_csv(self, 
                               instruments: List[str], 
                               full_df: pd.DataFrame,
                               csv_path: Path,
                               source_name: str,
                               export_details: bool = True) -> Dict:
        """
        生成集成的CSV文件
        """
        # 过滤数据
        df_filtered = full_df[full_df['instrument'].isin(instruments)].copy()
        
        if df_filtered.empty:
            logger.warning(f"无匹配数据 for {source_name}")
            return {'股票数': 0, '文件路径': str(csv_path)}
        
        # 重新排序以匹配原始TXT顺序
        instrument_order = {inst: i for i, inst in enumerate(instruments)}
        df_filtered['order'] = df_filtered['instrument'].map(instrument_order)
        df_filtered = df_filtered.sort_values('order').drop(columns=['order'])
        
        if(len(df_filtered) == 0):
            logger.warning(f"无匹配数据 for {source_name}")
            return {'股票数': 0, '文件路径': str(csv_path)}
        
        # 1. 备份原文件
        if csv_path.exists():
            backup_path = csv_path.with_suffix(f".csv.bak_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            csv_path.rename(backup_path)
            logger.info(f"已备份原文件: {backup_path}")
        
        # 生成CSV文件
        if export_details:
            # 导出完整详情
            self._export_full_details_csv(df_filtered, csv_path, source_name)
            
            # 同时生成精简版（QLib标准格式）
            simple_csv_path = csv_path.with_name(f"{csv_path.stem}_simple.csv")
            self._export_qlib_standard_csv(df_filtered, simple_csv_path, source_name)
        else:
            # 只生成QLib标准格式
            self._export_qlib_standard_csv(df_filtered, csv_path, source_name)
        
        count = len(df_filtered)
        logger.info(f"生成 {csv_path.name}: {count} 支股票")
        
        return {
            '股票数': count,
            '文件路径': str(csv_path),
            '更新时间': df_filtered['update_time'].iloc[0] if 'update_time' in df_filtered.columns else 'N/A'
        }
    
    def _export_full_details_csv(self, df: pd.DataFrame, csv_path: Path, source_name: str):
        """导出完整详情CSV"""
        # 定义导出的列顺序
        detail_columns = [
            'instrument', 'symbol', 'name', 'industry', 'market',
            'list_date', 'end_date', 'update_time',
            'latest_price', 'change_pct', 'change_amount',
            'volume', 'amount', 'turnover_rate',
            'pe_dynamic', 'pb', 
            'total_market_value', 'circ_market_value',
            'is_st', 'industry_code', 'industry_name',
        ]
        
        # 只保留存在的列
        available_cols = [col for col in detail_columns if col in df.columns]
        df_output = df[available_cols].copy()
        
        # 保存CSV
        df_output.to_csv(csv_path, index=False, encoding='utf-8')
        
        # 创建字段说明文件
        desc_path = csv_path.with_suffix(".fields.txt")
        self._create_field_description(desc_path, available_cols, source_name)
    
    def _export_qlib_standard_csv(self, df: pd.DataFrame, csv_path: Path, source_name: str):
        """导出QLib标准格式CSV"""
        # QLib标准列
        qlib_columns = [
            'instrument', 'symbol', 'name', 'industry',
            'list_date', 'end_date', 'market'
        ]
        
        # 添加可选指标
        optional_cols = ['pe_dynamic', 'pb', 'total_market_value', 'circ_market_value', 'is_st', 'industry_code', 'industry_name']
        for col in optional_cols:
            if col in df.columns and col not in qlib_columns:
                qlib_columns.append(col)
        
        df_output = df[qlib_columns].copy()
        df_output.to_csv(csv_path, index=False, encoding='utf-8')
    
    def _create_field_description(self, desc_path: Path, columns: List[str], source_name: str):
        """创建字段说明文件"""
        with open(desc_path, 'w', encoding='utf-8') as f:
            f.write(f"={'='*60}\n")
            f.write(f"QLib Instruments文件字段说明\n")
            f.write(f"来源: {source_name}\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"={'='*60}\n\n")
            
            f.write("字段说明:\n")
            f.write("-"*50 + "\n")
            
            field_descriptions = {
                'instrument': 'QLib股票代码 (sh/sz/bj+6位数字)',
                'symbol': '6位纯数字代码',
                'name': '股票简称',
                'industry': '行业分类',
                'list_date': '上市日期 (YYYYMMDD)',
                'end_date': '结束日期 (默认20991231)',
                'market': '市场类型 (SH/SZ/CYB/BJ)',
                'update_time': '数据更新时间',
                'latest_price': '最新价',
                'change_pct': '涨跌幅 (%)',
                'change_amount': '涨跌额',
                'volume': '成交量 (手)',
                'amount': '成交额 (元)',
                'turnover_rate': '换手率 (%)',
                'pe_dynamic': '动态市盈率',
                'pb': '市净率',
                'total_market_value': '总市值 (元)',
                'circ_market_value': '流通市值 (元)',
                'is_st': '是否ST股票 (True/False)',
                'industry_code': '所属行业代码',
                'industry_name': '行业名称',
            }
            
            for col in columns:
                desc = field_descriptions.get(col, '')
                f.write(f"{col:<20} - {desc}\n")
    
    def _get_basic_info_only(self) -> pd.DataFrame:
        """获取基础信息（轻量级）"""
        logger.info("获取A股基础信息...")
        
        try:
            df = self._akp.stock_zh_a_spot_em()
            
            # 简化处理
            result = pd.DataFrame()
            result['instrument'] = df['代码'].apply(
                lambda x: f"sh{x}" if str(x).zfill(6).startswith('6') else f"sz{x}"
            )
            result['symbol'] = df['代码'].astype(str).str.zfill(6)
            result['name'] = df['名称']
            result['industry'] = df['行业'].fillna('')
            result['market'] = result['instrument'].apply(
                lambda x: 'SH' if x.startswith('sh') else 'SZ'
            )
            result['list_date'] = ''
            result['end_date'] = '20991231'
            result['is_st'] = df['名称'].str.contains(r'ST|\*ST|退', na=False)
            result['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            return result
            
        except Exception as e:
            logger.error(f"获取基础信息失败: {e}")
            return pd.DataFrame()
    
    def create_market_index_csvs(self) -> Dict[str, int]:
        """
        创建市场指数成分CSV文件
        """
        df = self.fetch_full_a_share_data()
        
        indices = {
            'sh': df[df['market'] == 'SH']['instrument'].tolist(),
            'sz': df[df['market'] == 'SZ']['instrument'].tolist(),
            'cyb': df[df['market'] == 'CYB']['instrument'].tolist(),
            'bj': df[df['market'] == 'BJ']['instrument'].tolist()
        }
        
        results = {}
        
        for index_name, instruments in indices.items():
            if instruments:
                csv_path = self.instruments_dir / f"{index_name}_index.csv"
                df_index = df[df['instrument'].isin(instruments)].copy()
                
                # 导出标准格式
                standard_cols = ['instrument', 'symbol', 'name', 'industry', 
                                'list_date', 'end_date', 'market']
                df_index[standard_cols].to_csv(csv_path, index=False, encoding='utf-8')
                
                results[index_name] = len(df_index)
                logger.info(f"创建 {index_name}_index.csv: {len(df_index)} 支股票")
        
        return results
    
    def export_custom_portfolio(self, 
                               instruments: List[str],
                               portfolio_name: str,
                               include_full_data: bool = True) -> Path:
        """
        导出自定义投资组合
        """
        df = self.fetch_full_a_share_data()
        df_portfolio = df[df['instrument'].isin(instruments)].copy()
        
        if df_portfolio.empty:
            logger.warning(f"投资组合 {portfolio_name} 无匹配股票")
            return None
        
        # 排序
        instrument_order = {inst: i for i, inst in enumerate(instruments)}
        df_portfolio['order'] = df_portfolio['instrument'].map(instrument_order)
        df_portfolio = df_portfolio.sort_values('order').drop(columns=['order'])
        
        # 导出文件
        csv_path = self.instruments_dir / f"{portfolio_name}.csv"
        
        if include_full_data:
            self._export_full_details_csv(df_portfolio, csv_path, portfolio_name)
        else:
            self._export_qlib_standard_csv(df_portfolio, csv_path, portfolio_name)
        
        logger.info(f"导出投资组合 {portfolio_name}: {len(df_portfolio)} 支股票")
        return csv_path

def update_instruments_csv(progress_callback=None):
    # 1. 初始化
    updater = QLibInstrumentsUpdater()
    
    # 2. 获取基础信息并批量更新所有TXT对应的CSV
    results = updater.batch_update_instruments_csv(progress_callback=progress_callback)
    
    print("更新结果:")
    for csv_name, count in results.items():
        print(f"  {csv_name}: {count} 支股票")