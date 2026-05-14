#!/usr/bin/env python3
"""
Binance数据转QLib格式 - 带进度条版本
修复了JSON序列化和微秒时间戳问题
"""

import pandas as pd
import numpy as np
import zipfile
import io
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple, Any, Optional
import os
import json
import time
from tqdm import tqdm
import sys
from workers.qlib_downloader import DownloadSignals


_signals:DownloadSignals = DownloadSignals()

# ====================== 进度条样式 ======================
class CustomProgressBar:
    """自定义进度条样式"""
    
    @staticmethod
    def create_file_progress(total: int, desc: str = "处理文件"):
        """创建文件处理进度条"""
        return tqdm(
            total=total,
            desc=desc,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            ncols=100,
            file=sys.stdout
        )
    
    @staticmethod
    def create_feature_progress(total: int, desc: str = "处理特征"):
        """创建特征处理进度条"""
        return tqdm(
            total=total,
            desc=desc,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            ncols=80,
            file=sys.stdout
        )

# ====================== 自定义JSON编码器 ======================
class NumpyEncoder(json.JSONEncoder):
    """自定义JSON编码器，支持NumPy类型"""
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int8, np.int16, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Path):
            return str(obj)
        else:
            return super().default(obj)

# ====================== 工具函数 ======================
def timestamp_to_qlib_date(timestamp: int) -> int:
    """
    将Binance时间戳转换为QLib日期格式 (YYYYMMDD)
    处理毫秒级和微秒级时间戳
    """
    try:
        # 确保是整数
        timestamp = int(float(timestamp))
        
        # 判断是毫秒还是微秒
        if timestamp > 1e15:  # 大于 1e15 是微秒级
            # 微秒转换为秒
            timestamp_seconds = timestamp / 1_000_000.0
        elif timestamp > 1e12:  # 大于 1e12 是毫秒级
            # 毫秒转换为秒
            timestamp_seconds = timestamp / 1000.0
        else:
            # 可能已经是秒级
            timestamp_seconds = timestamp
        
        # 转换为datetime (UTC时间)
        dt = datetime.utcfromtimestamp(timestamp_seconds)
        
        # 转换为YYYYMMDD格式
        return int(dt.strftime('%Y%m%d'))
    except Exception as e:
        return 0

def detect_timestamp_unit(timestamp: int) -> str:
    """检测时间戳单位"""
    timestamp = int(float(timestamp))
    
    if timestamp > 1e15:  # 大于 1e15
        return "microsecond"  # 微秒
    elif timestamp > 1e12:  # 大于 1e12
        return "millisecond"  # 毫秒
    else:
        return "second"  # 秒

# ====================== Binance数据处理器 ======================
class BinanceDataProcessor:
    """Binance数据处理器（支持微秒时间戳）"""
    
    # 特征映射
    FEATURE_MAPPING = {
        'open': 'open',
        'high': 'high', 
        'low': 'low',
        'close': 'close',
        'volume': 'volume',
        'quote_volume': 'quote_volume',
        'count': 'trade_count',
        'taker_buy_base_volume': 'taker_buy_base',
        'taker_buy_quote_volume': 'taker_buy_quote'
    }
    
    @staticmethod
    def parse_csv(csv_content: bytes, symbol: str, filename: str = "", 
                  pbar: Optional[tqdm] = None) -> Dict[str, pd.DataFrame]:
        """
        解析Binance CSV文件，支持微秒时间戳
        """
        try:
            # 读取CSV
            df = pd.read_csv(io.BytesIO(csv_content), header=None)
            
            if pbar:
                pbar.set_postfix_str(f"解析 {symbol}: {df.shape[0]}行 {df.shape[1]}列")
            
            # 确保至少有11列
            if df.shape[1] < 11:
                if pbar:
                    pbar.set_postfix_str(f"跳过 {symbol}: 列数不足 {df.shape[1]}")
                return {}
            
            # 提取时间戳和基本数据
            data = {}
            
            # 获取日期
            dates = []
            timestamps = []
            for ts in df.iloc[:, 0]:
                try:
                    date = timestamp_to_qlib_date(ts)
                    dates.append(int(date))
                    timestamps.append(int(ts))
                except:
                    dates.append(0)
                    timestamps.append(0)
            
            data['date'] = dates
            data['timestamp'] = timestamps
            data['symbol'] = [symbol] * len(dates)
            
            # 提取特征
            feature_columns = {
                1: 'open',
                2: 'high',
                3: 'low', 
                4: 'close',
                5: 'volume',
                7: 'quote_volume',
                8: 'count',
                9: 'taker_buy_base_volume',
                10: 'taker_buy_quote_volume'
            }
            
            for col_idx, feature_name in feature_columns.items():
                if col_idx < df.shape[1]:
                    values = []
                    for val in df.iloc[:, col_idx]:
                        try:
                            values.append(float(val))
                        except:
                            values.append(np.nan)
                    data[feature_name] = values
            
            # 创建DataFrame
            result_df = pd.DataFrame(data)
            
            # 移除无效日期
            result_df = result_df[result_df['date'] > 0]
            
            if len(result_df) == 0:
                if pbar:
                    pbar.set_postfix_str(f"跳过 {symbol}: 无有效数据")
                return {}
            
            # 创建特征DataFrame
            features = {}
            
            for raw_name, feature_name in BinanceDataProcessor.FEATURE_MAPPING.items():
                if raw_name in result_df.columns:
                    # 移除NaN值
                    valid_mask = ~result_df[raw_name].isna()
                    if valid_mask.any():
                        feature_df = pd.DataFrame({
                            'date': result_df.loc[valid_mask, 'date'].astype(int),
                            'symbol': result_df.loc[valid_mask, 'symbol'],
                            'value': result_df.loc[valid_mask, raw_name].astype(float)
                        })
                        features[feature_name] = feature_df
            
            # 计算衍生特征
            BinanceDataProcessor._add_derived_features(result_df, features, pbar)
            
            if pbar:
                pbar.set_postfix_str(f"完成 {symbol}: {len(features)}特征")
            
            return features
            
        except Exception as e:
            if pbar:
                pbar.set_postfix_str(f"错误 {symbol}: {str(e)[:30]}")
            return {}
    
    @staticmethod
    def _add_derived_features(df: pd.DataFrame, features: Dict[str, pd.DataFrame], 
                            pbar: Optional[tqdm] = None):
        """添加衍生特征"""
        try:
            # vwap
            valid_mask = (~df['quote_volume'].isna()) & (~df['volume'].isna()) & (df['volume'] > 0)
            if valid_mask.any():
                vwap_values = df.loc[valid_mask, 'quote_volume'] / df.loc[valid_mask, 'volume']
                features['vwap'] = pd.DataFrame({
                    'date': df.loc[valid_mask, 'date'].astype(int),
                    'symbol': df.loc[valid_mask, 'symbol'],
                    'value': vwap_values.astype(float)
                })
        except:
            pass
        
        try:
            # range
            valid_mask = (~df['high'].isna()) & (~df['low'].isna())
            if valid_mask.any():
                range_values = df.loc[valid_mask, 'high'] - df.loc[valid_mask, 'low']
                features['range'] = pd.DataFrame({
                    'date': df.loc[valid_mask, 'date'].astype(int),
                    'symbol': df.loc[valid_mask, 'symbol'],
                    'value': range_values.astype(float)
                })
        except:
            pass
        
        try:
            # body (close - open)
            valid_mask = (~df['close'].isna()) & (~df['open'].isna())
            if valid_mask.any():
                body_values = df.loc[valid_mask, 'close'] - df.loc[valid_mask, 'open']
                features['body'] = pd.DataFrame({
                    'date': df.loc[valid_mask, 'date'].astype(int),
                    'symbol': df.loc[valid_mask, 'symbol'],
                    'value': body_values.astype(float)
                })
        except:
            pass

# ====================== QLib二进制文件处理器 ======================
class QLibBinProcessor:
    """QLib二进制文件处理器"""
    
    @staticmethod
    def get_dtype():
        """获取二进制文件的数据类型"""
        return np.dtype([
            ('date', 'i8'),      # 日期 (YYYYMMDD)
            ('instrument', 'i8'), # 标的索引
            ('value', 'f8')      # 特征值
        ])
    
    @staticmethod
    def write_feature_to_bin(feature_df: pd.DataFrame, symbol_idx: int, 
                           output_file: Path, feature_name: str,
                           pbar: Optional[tqdm] = None) -> bool:
        """
        将特征数据写入二进制文件
        """
        try:
            if len(feature_df) == 0:
                return False
            
            # 创建结构化数组
            dtype = QLibBinProcessor.get_dtype()
            n_samples = len(feature_df)
            feature_array = np.zeros(n_samples, dtype=dtype)
            
            # 填充数据
            for i, (_, row) in enumerate(feature_df.iterrows()):
                date_val = int(row['date'])
                value_val = float(row['value'])
                feature_array[i] = (date_val, symbol_idx, value_val)
            
            # 按日期排序
            feature_array = feature_array[np.argsort(feature_array['date'])]
            
            # 写入文件
            feature_array.tofile(output_file)
            return True
            
        except Exception as e:
            if pbar:
                pbar.set_postfix_str(f"写入错误: {str(e)[:30]}")
            return False

# ====================== 主转换器 ======================
class BinanceToQLibConverter:
    """Binance到QLib转换器（支持微秒时间戳）"""
    def __init__(self, output_dir: str = "~/.qlib/qlib_data/bt_data", verbose: bool = True):
        self.output_base = Path(output_dir)
        self.features_dir = self.output_base / "features"
        self.calendars_dir = self.output_base / "calendars"
        self.instruments_dir = self.output_base / "instruments"
        self.features_dir.mkdir(parents=True, exist_ok=True)
        self.calendars_dir.mkdir(parents=True, exist_ok=True)
        self.instruments_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建目录
        for d in [self.features_dir, self.calendars_dir, self.instruments_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # 全局索引
        self.all_dates: Set[int] = set()
        self.all_symbols: Set[str] = set()
        self.symbol_to_idx: Dict[str, int] = {}
        self.next_symbol_idx = 0
        
        # 统计信息
        self.stats = {
            'total_files': 0,
            'success_files': 0,
            'failed_files': 0,
            'total_rows': 0,
            'features_count': 0
        }
        
        # 控制台输出
        self.verbose = verbose
    
    def get_symbol_index(self, symbol: str) -> int:
        """获取或创建symbol索引"""
        if symbol not in self.symbol_to_idx:
            self.symbol_to_idx[symbol] = int(self.next_symbol_idx)
            self.next_symbol_idx += 1
            self.all_symbols.add(symbol)
        return self.symbol_to_idx[symbol]
    
    def process_zip_file(self, zip_path: Path, pbar: Optional[tqdm] = None):
        """处理单个ZIP文件"""
        if pbar:
            pbar.set_postfix_str(f"处理: {zip_path.name[:20]}")
        
        self.stats['total_files'] += 1
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                
                for csv_file in csv_files:
                    start_time = time.time()
                    
                    # 解析文件名
                    stem = Path(csv_file).stem
                    parts = stem.split('-')
                    
                    if len(parts) < 3:
                        continue
                    
                    symbol = parts[0]
                    interval = parts[1]
                    
                    # 确定频率
                    freq_map = {
                        '1d': 'day',
                        '4h': '240min',
                        '1h': '60min',
                        '15m': '15min',
                        '5m': '5min',
                        '1m': '1min'
                    }
                    freq = freq_map.get(interval, 'day')
                    
                    # 解析CSV
                    csv_content = zf.read(csv_file)
                    features = BinanceDataProcessor.parse_csv(csv_content, symbol, csv_file, pbar)
                    
                    if not features:
                        self.stats['failed_files'] += 1
                        continue
                    
                    # 获取symbol索引
                    symbol_idx = self.get_symbol_index(symbol)
                    
                    # 创建symbol目录
                    symbol_dir = self.features_dir / symbol
                    symbol_dir.mkdir(parents=True, exist_ok=True)
                    
                    # 保存每个特征
                    features_saved = 0
                    for feature_name, feature_df in features.items():
                        # 收集日期
                        dates = set(int(d) for d in feature_df['date'].unique())
                        self.all_dates.update(dates)
                        
                        # 更新统计
                        self.stats['total_rows'] += int(len(feature_df))
                        
                        # 保存二进制文件
                        bin_file = symbol_dir / f"{feature_name}.{freq}.bin"
                        
                        # 如果文件已存在，合并数据
                        if bin_file.exists():
                            try:
                                dtype = np.dtype([('date', 'i8'), ('instrument', 'i8'), ('value', 'f8')])
                                existing_data = np.fromfile(bin_file, dtype=dtype)
                                
                                # 创建新数据数组
                                new_data = np.zeros(len(feature_df), dtype=dtype)
                                for i, (_, row) in enumerate(feature_df.iterrows()):
                                    new_data[i] = (int(row['date']), symbol_idx, float(row['value']))
                                
                                # 合并并去重
                                combined_data = np.concatenate([existing_data, new_data])
                                unique_dates = {}
                                for record in combined_data:
                                    date = int(record['date'])
                                    if date not in unique_dates:
                                        unique_dates[date] = record
                                
                                # 转换为数组并排序
                                final_data = np.array(list(unique_dates.values()), dtype=dtype)
                                final_data = final_data[np.argsort(final_data['date'])]
                                
                                # 写入文件
                                final_data.tofile(bin_file)
                                features_saved += 1
                                
                            except:
                                # 直接写入新文件
                                success = QLibBinProcessor.write_feature_to_bin(
                                    feature_df, symbol_idx, bin_file, feature_name, pbar
                                )
                                if success:
                                    features_saved += 1
                        else:
                            os.makedirs(bin_file.parent, exist_ok=True)
                            # 新文件
                            success = QLibBinProcessor.write_feature_to_bin(
                                feature_df, symbol_idx, bin_file, feature_name, pbar
                            )
                            if success:
                                features_saved += 1
                    
                    self.stats['features_count'] += features_saved
                    elapsed = time.time() - start_time
                    
                    if features_saved > 0:
                        self.stats['success_files'] += 1
                    else:
                        self.stats['failed_files'] += 1
                    
        except Exception as e:
            self.stats['failed_files'] += 1
            if pbar:
                pbar.set_postfix_str(f"错误: {str(e)[:20]}")
    
    def process_Files(self, input_files: List[str], pattern: str = "*.zip"):
        """处理目录中的所有文件"""
        
        zip_files = input_files
        
        if not zip_files:
            print(f"\n没有符合要求的文件，处理完成!")
        
        total_files = len(zip_files)
        print(f"找到 {total_files} 个ZIP文件")
        print(f"开始转换...")
        
        # 创建主进度条
        with CustomProgressBar.create_file_progress(total_files, "📦 处理ZIP文件") as pbar:
            for i, zip_file in enumerate(zip_files, 1):
                self.process_zip_file(zip_file, pbar)
                pbar.update(1)
                
                # 更新进度条描述
                pbar.set_postfix_str(f"{i}/{total_files} 完成")
                
                percentage = 78 + int(0.17 * i/total_files)
                
                if _signals :
                    _signals.progress.emit(percentage, f"{i}/{total_files} 完成")
        
        print(f"\n处理完成!")
        
    def process_directory(self, input_dir: str, pattern: str = "*.zip"):
        """处理目录中的所有文件"""
        input_path = Path(input_dir)
        
        if not input_path.exists():
            print(f"错误: 目录不存在: {input_dir}")
            return
        
        zip_files = list(input_path.glob(pattern))
        
        if not zip_files:
            zip_files = list(input_path.glob("**/*.zip"))
        
        total_files = len(zip_files)
        print(f"找到 {total_files} 个ZIP文件")
        print(f"开始转换...")
        
        # 创建主进度条
        with CustomProgressBar.create_file_progress(total_files, "📦 处理ZIP文件") as pbar:
            for i, zip_file in enumerate(zip_files, 1):
                self.process_zip_file(zip_file, pbar)
                pbar.update(1)
                
                # 更新进度条描述
                pbar.set_postfix_str(f"{i}/{total_files} 完成")
                
                percentage = 78 + int(0.17 * i/total_files)
                
                if _signals :
                    _signals.progress.emit(percentage, f"{i}/{total_files} 完成")
        
        print(f"\n处理完成!")
    
    def save_indices(self):
        """保存索引文件"""
        print("\n💾 保存索引文件...")
        
        # 获取全局的起止日期
        global_start_date = int(min(self.all_dates)) if self.all_dates else 0
        global_end_date = int(max(self.all_dates)) if self.all_dates else 0
        
        # 获取当前处理的频率（从之前的处理中获取）
        # 假设我们在类中有一个属性存储当前处理的数据频率
        if not hasattr(self, 'current_freq'):
            self.current_freq = 'day'  # 默认频率
        
        freq = self.current_freq
        
        # 创建进度条
        with tqdm(total=4, desc="📁 保存文件", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
            # 1. 保存所有日期的文件
            if self.all_dates:
                sorted_dates = sorted(self.all_dates)
                dates_file = self.output_base / "dates.txt"
                with open(dates_file, 'w') as f:
                    for date in sorted_dates:
                        f.write(f"{date}\n")
            pbar.update(1)
            pbar.set_postfix_str("dates.txt")
            
            # 2. 保存交易日历文件（按频率，格式化为日期时间字符串）
            if self.all_dates:
                calendar_file = self.calendars_dir / f"{freq}.txt"
                with open(calendar_file, 'w') as f:
                    for date in sorted_dates:
                        # 根据频率格式化日期
                        date_str = self._format_date_by_freq(date, freq)
                        f.write(f"{date_str}\n")
            pbar.update(1)
            pbar.set_postfix_str(f"calendars/{freq}.txt")
            
            # 3. 保存标的列表 (格式: symbol\tstart_date\tend_date)
            if self.all_symbols:
                sorted_symbols = sorted(self.all_symbols)
                instruments_file = self.instruments_dir / "all.txt"
                
                with open(instruments_file, 'w') as f:
                    for symbol in sorted_symbols:
                        # 获取这个symbol的实际日期范围
                        start_date, end_date = self._get_symbol_date_range(symbol)
                        
                        # 如果日期范围无效，使用全局范围
                        if start_date == 0 or end_date == 0:
                            start_date, end_date = global_start_date, global_end_date
                        
                        # 根据频率格式化日期
                        start_date_str = self._format_date_by_freq(start_date, freq)
                        end_date_str = self._format_date_by_freq(end_date, freq)
                        
                        # 写入格式: symbol\tstart_date\tend_date
                        f.write(f"{symbol}\t{start_date_str}\t{end_date_str}\n")
            pbar.update(1)
            pbar.set_postfix_str("instruments/all.txt")
            
            # 4. 保存JSON文件
            if self.all_symbols:
                instruments_json = {}
                for symbol, idx in self.symbol_to_idx.items():
                    # 获取这个symbol的日期范围
                    start_date, end_date = self._get_symbol_date_range(symbol)
                    if start_date == 0 or end_date == 0:
                        start_date, end_date = global_start_date, global_end_date
                    
                    # JSON中保持整数格式
                    instruments_json[symbol] = {
                        "index": int(idx),
                        "type": "crypto",
                        "market": "BINANCE",
                        "start_date": start_date,  # 保持整数
                        "end_date": end_date,      # 保持整数
                        "start_date_str": self._format_date_by_freq(start_date, freq),  # 添加字符串版本
                        "end_date_str": self._format_date_by_freq(end_date, freq)      # 添加字符串版本
                    }
                
                json_file = self.instruments_dir / "instruments.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(instruments_json, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)
            pbar.update(1)
            pbar.set_postfix_str("instruments.json")
        
        print("✅ 索引文件保存完成!")

    def _format_date_by_freq(self, date_int: int, freq: str) -> str:
        """
        根据频率格式化日期
        规则与{freq}.txt中的时间处理规则一致
        """
        if date_int <= 0:
            return "0000-00-00"  # 无效日期的占位符
        
        date_str = str(date_int)
        
        try:
            if freq == 'day':
                # 日线: yyyy-MM-dd
                if len(date_str) == 8:  # YYYYMMDD
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                elif len(date_str) == 10:  # YYYYMMDDHH
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                elif len(date_str) == 12:  # YYYYMMDDHHMM
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            
            elif freq in ['240min', '120min', '60min']:
                # 小时级: yyyy-MM-dd HH:00:00
                if len(date_str) == 8:  # YYYYMMDD
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} 00:00:00"
                elif len(date_str) == 10:  # YYYYMMDDHH
                    year = int(date_str[:4])
                    month = int(date_str[4:6])
                    day = int(date_str[6:8])
                    hour = int(date_str[8:10])
                    dt = datetime(year, month, day, hour)
                    return dt.strftime("%Y-%m-%d %H:00:00")
                elif len(date_str) == 12:  # YYYYMMDDHHMM
                    year = int(date_str[:4])
                    month = int(date_str[4:6])
                    day = int(date_str[6:8])
                    hour = int(date_str[8:10])
                    minute = int(date_str[10:12])
                    dt = datetime(year, month, day, hour, minute)
                    return dt.strftime("%Y-%m-%d %H:%M:00")
            
            elif freq in ['30min', '15min', '5min', '1min']:
                # 分钟级: yyyy-MM-dd HH:mm:00
                if len(date_str) == 8:  # YYYYMMDD
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} 00:00:00"
                elif len(date_str) == 10:  # YYYYMMDDHH
                    year = int(date_str[:4])
                    month = int(date_str[4:6])
                    day = int(date_str[6:8])
                    hour = int(date_str[8:10])
                    dt = datetime(year, month, day, hour)
                    return dt.strftime("%Y-%m-%d %H:00:00")
                elif len(date_str) == 12:  # YYYYMMDDHHMM
                    year = int(date_str[:4])
                    month = int(date_str[4:6])
                    day = int(date_str[6:8])
                    hour = int(date_str[8:10])
                    minute = int(date_str[10:12])
                    dt = datetime(year, month, day, hour, minute)
                    return dt.strftime("%Y-%m-%d %H:%M:00")
            
        except Exception as e:
            # 如果解析失败，返回原始字符串
            return date_str
        
        # 默认返回日线格式
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        elif len(date_str) == 10:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {date_str[8:10]}:00:00"
        else:
            return date_str

    def _get_symbol_date_range(self, symbol: str) -> Tuple[int, int]:
        """获取symbol的实际日期范围"""
        # 检查是否有这个symbol的目录
        symbol_dir = self.features_dir / symbol
        if not symbol_dir.exists():
            return 0, 0
        
        symbol_dates = set()
        
        # 遍历这个symbol的所有bin文件
        for bin_file in symbol_dir.glob("*.bin"):
            try:
                dtype = np.dtype([
                    ('date', 'i8'),
                    ('instrument', 'i8'),
                    ('value', 'f8')
                ])
                data = np.fromfile(bin_file, dtype=dtype)
                
                if len(data) > 0:
                    dates = data['date']
                    valid_dates = dates[dates > 0]
                    if len(valid_dates) > 0:
                        symbol_dates.update(valid_dates)
            except Exception as e:
                continue
        
        if symbol_dates:
            return int(min(symbol_dates)), int(max(symbol_dates))
        else:
            return 0, 0
    
    def save_metadata(self, description: str = "Binance加密货币数据"):
        """保存元数据文件"""
        print("📄 保存元数据...")
        
        start_date = int(min(self.all_dates)) if self.all_dates else None
        end_date = int(max(self.all_dates)) if self.all_dates else None
        
        metadata = {
            "name": "Binance Crypto Data",
            "description": description,
            "source": "Binance Vision API",
            "format": "qlib_bin",
            "created_at": datetime.now().isoformat(),
            "version": "1.0.0",
            "symbols_count": int(len(self.all_symbols)),
            "dates_count": int(len(self.all_dates)),
            "date_range": [start_date, end_date],
            "features": list(BinanceDataProcessor.FEATURE_MAPPING.values()) + ['vwap', 'range', 'body'],
            "stats": {
                'total_files': int(self.stats['total_files']),
                'success_files': int(self.stats['success_files']),
                'failed_files': int(self.stats['failed_files']),
                'total_rows': int(self.stats['total_rows']),
                'features_count': int(self.stats['features_count'])
            }
        }
        
        metadata_file = self.output_base / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)
        
        print("✅ 元数据保存完成!")
    
    def print_summary(self):
        """打印转换摘要"""
        print("\n" + "="*60)
        print("转换摘要".center(60))
        print("="*60)
        
        # 创建表格样式
        summary_data = [
            ["📁 总文件数", f"{self.stats['total_files']:>6}"],
            ["✅ 成功文件", f"{self.stats['success_files']:>6}"],
            ["❌ 失败文件", f"{self.stats['failed_files']:>6}"],
            ["📊 总数据行", f"{self.stats['total_rows']:>6}"],
            ["🏷️  特征数量", f"{self.stats['features_count']:>6}"],
            ["💰 交易对数", f"{len(self.all_symbols):>6}"],
            ["📅 日期数量", f"{len(self.all_dates):>6}"],
        ]
        
        for label, value in summary_data:
            print(f"{label:15} {value}")
        
        if self.all_dates:
            start_date = min(self.all_dates)
            end_date = max(self.all_dates)
            print(f"{'📅 日期范围':15} {start_date} - {end_date}")
        
        print("="*60)
        print(f"数据目录: {self.output_base}")
        print(f"特征目录: {self.features_dir}")
        print("="*60)

# ====================== 测试时间戳转换 ======================
def test_timestamp_conversion():
    """测试时间戳转换"""
    test_cases = [
        (1530403200000, "millisecond", "2018-07-01"),
        (1583020800000, "millisecond", "2020-03-01"),
        (1748736000000000, "microsecond", "2025-06-01"),
        (1764547200000000, "microsecond", "2025-12-01"),
    ]
    
    print("🧪 测试时间戳转换:")
    for ts, expected_unit, expected_date in test_cases:
        unit = detect_timestamp_unit(ts)
        date_int = timestamp_to_qlib_date(ts)
        date_str = f"{date_int:08d}" if date_int > 0 else "无效"
        expected_date_int = int(expected_date.replace("-", ""))
        
        status = "✅" if unit == expected_unit and date_int == expected_date_int else "❌"
        
        print(f"  {status} {ts:20d} -> 单位: {unit:12s} 日期: {date_str}")

# ====================公用接口========================
def BinanceData_2_QlibData(input:str = "./binance_data", archive_paths:List[str] =[], ouput:str = "./qlib_data/bt_data", freq:str="day", pattern:str="*.zip", signals:DownloadSignals = None):
    
    _signals = signals
    signalsExists = "不存在" if not _signals else "存在"
    print(f"_signals : {signalsExists}")
    # 创建转换器
    converter = BinanceToQLibConverter(ouput, verbose=True)
    
    # 处理文件
    if archive_paths and len(archive_paths) > 0 :
        converter.process_Files(archive_paths, pattern)
    else :
        converter.process_directory(input, pattern)
    
    # 保存索引和元数据
    converter.save_indices()
    converter.save_metadata()
    
    # 打印摘要
    converter.print_summary()
    
# ====================== 主函数 ======================
def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='转换Binance数据为QLib格式（支持微秒时间戳）')
    parser.add_argument('--input', type=str, default='./binance_data', 
                       help='输入路径（包含ZIP文件的目录）')
    parser.add_argument('--output', type=str, default='./qlib_data/bt_data',
                       help='输出目录')
    parser.add_argument('--pattern', type=str, default='*.zip',
                       help='文件匹配模式（默认: *.zip）')
    parser.add_argument('--description', type=str, default='Binance加密货币数据',
                       help='数据集描述')
    parser.add_argument('--test', action='store_true',
                       help='运行时间戳转换测试')
    parser.add_argument('--verbose', action='store_true',
                       help='显示详细输出')
    
    args = parser.parse_args()
    
    # 打印标题
    print("\n" + "="*60)
    print("Binance数据转QLib格式".center(60))
    print("="*60)
    
    # 创建转换器
    converter = BinanceToQLibConverter(args.output, verbose=args.verbose)
    
    # 处理文件
    converter.process_directory(args.input, args.pattern)
    
    # 保存索引和元数据
    converter.save_indices()
    converter.save_metadata(args.description)
    
    # 打印摘要
    converter.print_summary()
    
    print("\n🎉 转换完成！")

# ====================== 简易版本（最简进度条） ======================
def simple_main():
    """最简版本，只有一个进度条"""
    import argparse
    
    parser = argparse.ArgumentParser(description='转换Binance数据为QLib格式')
    parser.add_argument('--input', type=str, default='./binance_data', 
                       help='输入路径')
    parser.add_argument('--output', type=str, default='./qlib_data/bt_data',
                       help='输出目录')
    
    args = parser.parse_args()
    
    print(f"\n🚀 开始转换 Binance 数据...")
    
    # 查找文件
    input_path = Path(args.input)
    zip_files = list(input_path.glob("*.zip"))
    if not zip_files:
        zip_files = list(input_path.glob("**/*.zip"))
    
    total_files = len(zip_files)
    print(f"📁 找到 {total_files} 个文件")
    
    # 创建转换器
    converter = BinanceToQLibConverter(args.output, verbose=False)
    
    # 单个进度条处理
    with tqdm(total=total_files, desc="📦 处理文件", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
        for zip_file in zip_files:
            converter.process_zip_file(zip_file, pbar)
            pbar.update(1)
    
    # 保存结果
    print("💾 保存结果...")
    converter.save_indices()
    converter.save_metadata()
    
    # 显示结果
    converter.print_summary()

# ====================== 运行 ======================
if __name__ == "__main__":
    # 使用完整版本
    main()