# services/stock_spot_csv_exporter.py
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from loguru import logger
from typing import Optional, List, Dict

class StockSpotCSVExporter:
    """A股实时行情数据导出为CSV"""
    
    def __init__(self, output_dir: str = "data/spot_data"):
        """
        初始化导出器
        :param output_dir: CSV输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 定义完整的字段映射
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
            '更新时间': 'update_time'  # 新增列
        }
        
        # 数据类型定义
        self.dtype_mapping = {
            '序号': 'int64',
            '代码': 'object',
            '名称': 'object',
            '最新价': 'float64',
            '涨跌幅': 'float64',
            '涨跌额': 'float64',
            '成交量': 'float64',
            '成交额': 'float64',
            '振幅': 'float64',
            '最高': 'float64',
            '最低': 'float64',
            '今开': 'float64',
            '昨收': 'float64',
            '量比': 'float64',
            '换手率': 'float64',
            '市盈率-动态': 'float64',
            '市净率': 'float64',
            '总市值': 'float64',
            '流通市值': 'float64',
            '涨速': 'float64',
            '5分钟涨跌': 'float64',
            '60日涨跌幅': 'float64',
            '年初至今涨跌幅': 'float64',
            '更新时间': 'object'  # 时间字符串
        }
        
        # 字段说明（单位标注）
        self.field_descriptions = {
            '涨跌幅': '单位: %',
            '振幅': '单位: %',
            '成交量': '单位: 手',
            '成交额': '单位: 元',
            '换手率': '单位: %',
            '总市值': '单位: 元',
            '流通市值': '单位: 元',
            '5分钟涨跌': '单位: %',
            '60日涨跌幅': '单位: %',
            '年初至今涨跌幅': '单位: %',
            '更新时间': '数据采集时间'
        }
    
    def fetch_stock_spot_data(self) -> pd.DataFrame:
        """
        从AKShare获取A股实时行情数据
        """
        logger.info("开始获取A股实时行情数据...")
        
        try:
            from services.akshare_pro import AKSharePro
            ak = AKSharePro(patch_requests=True)
            df = ak.stock_zh_a_spot_em()
            logger.info(f"获取成功，共 {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"获取实时行情数据失败: {e}")
            raise
    
    def standardize_data(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化数据格式
        """
        df = raw_df.copy()
        
        # 获取当前更新时间
        current_time = datetime.now()
        update_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. 确保列名一致性
        column_rename = {}
        for cn_name, en_name in self.field_mapping.items():
            if cn_name in df.columns:
                column_rename[cn_name] = en_name
        
        if column_rename:
            df = df.rename(columns=column_rename)
        
        # 2. 数据类型转换
        for col, dtype in self.dtype_mapping.items():
            en_name = self.field_mapping.get(col)
            if en_name in df.columns:
                try:
                    if dtype == 'int64':
                        df[en_name] = pd.to_numeric(df[en_name], errors='coerce').fillna(0).astype('int64')
                    elif dtype == 'float64':
                        df[en_name] = pd.to_numeric(df[en_name], errors='coerce')
                    elif dtype == 'object':
                        df[en_name] = df[en_name].astype(str)
                except Exception as e:
                    logger.warning(f"转换列 {en_name} 数据类型失败: {e}")
        
        # 3. 添加QLib instrument格式
        df['instrument'] = df['symbol'].apply(
            lambda x: f"sh{x}" if x.startswith('6') else f"sz{x}"
        )
        
        # 4. 添加时间戳列
        df['fetch_time'] = update_time_str
        df['trade_date'] = current_time.strftime("%Y%m%d")
        
        # 5. 添加"更新时间"列到行尾
        df['update_time'] = update_time_str
        
        return df
    
    def export_to_csv(self, 
                     df: pd.DataFrame, 
                     filename: Optional[str] = None,
                     include_descriptions: bool = True,
                     include_update_time: bool = True) -> Path:
        """
        导出DataFrame到CSV文件
        :param include_update_time: 是否包含更新时间列
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"stock_spot_{timestamp}.csv"
        
        filepath = self.output_dir / filename
        
        # 导出数据的副本
        export_df = df.copy()
        
        # 确保更新时间列存在
        if 'update_time' not in export_df.columns and include_update_time:
            export_df['update_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 如果需要重新排序列，将更新时间列放到最后
        if include_update_time and 'update_time' in export_df.columns:
            # 将其他列移到前面，更新时间列放到最后
            cols = [col for col in export_df.columns if col != 'update_time'] + ['update_time']
            export_df = export_df[cols]
        
        logger.info(f"导出CSV文件: {filepath}")
        logger.info(f"包含 {len(export_df.columns)} 列，其中更新时间: {export_df['update_time'].iloc[0] if 'update_time' in export_df.columns else '无'}")
        
        # 写入数据
        export_df.to_csv(filepath, index=False, encoding='utf-8-sig')
        
        # 如果需要，创建字段说明文件
        if include_descriptions:
            desc_file = filepath.with_suffix(".desc.txt")
            self._create_field_description_file(desc_file, export_df.columns.tolist())
        
        logger.info(f"导出完成: {len(export_df)} 行数据")
        return filepath
    
    def _create_field_description_file(self, filepath: Path, columns: List[str]):
        """创建字段说明文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("A股实时行情数据字段说明\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            f.write("数据列说明:\n")
            f.write("-" * 60 + "\n")
            
            for col in columns:
                # 查找对应的中文名
                cn_name = None
                for cn, en in self.field_mapping.items():
                    if en == col:
                        cn_name = cn
                        break
                
                if cn_name:
                    description = self.field_descriptions.get(cn_name, "")
                    f.write(f"{col} ({cn_name})")
                    if description:
                        f.write(f" - {description}")
                else:
                    f.write(f"{col}")
                f.write("\n")
    
    def export_full_spot_data(self, 
                             filters: Optional[Dict] = None,
                             sort_by: str = "total_market_value",
                             descending: bool = True) -> Path:
        """
        完整导出流程
        """
        # 1. 获取数据
        raw_df = self.fetch_stock_spot_data()
        
        # 2. 标准化
        df = self.standardize_data(raw_df)
        
        # 3. 应用过滤器
        if filters:
            df = self._apply_filters(df, filters)
        
        # 4. 排序
        if sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=not descending)
        
        # 5. 导出CSV
        filename = f"a_share_spot_{datetime.now().strftime('%Y%m%d')}.csv"
        return self.export_to_csv(df, filename, include_update_time=True)
    
    def _apply_filters(self, df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
        """应用过滤器"""
        filtered_df = df.copy()
        
        for field, condition in filters.items():
            if field in filtered_df.columns:
                if isinstance(condition, tuple) and len(condition) == 2:
                    # 范围过滤
                    col_name, (min_val, max_val) = condition
                    filtered_df = filtered_df[
                        (filtered_df[col_name] >= min_val) & 
                        (filtered_df[col_name] <= max_val)
                    ]
                elif isinstance(condition, list):
                    # 列表过滤
                    filtered_df = filtered_df[filtered_df[field].isin(condition)]
                elif callable(condition):
                    # 函数过滤
                    filtered_df = filtered_df[condition(filtered_df[field])]
        
        return filtered_df
    
    def export_for_qlib(self, 
                       min_mv: float = 1e8,  # 最小市值1亿
                       max_pe: float = 200,
                       exclude_st: bool = True) -> Path:
        """
        导出适合QLib使用的股票列表
        """
        raw_df = self.fetch_stock_spot_data()
        df = self.standardize_data(raw_df)
        
        # 应用QLib常用过滤器
        if exclude_st:
            # 通过名称判断ST股票
            df = df[~df['name'].str.contains('ST|\*ST|退', na=False)]
        
        if min_mv > 0:
            df = df[df['total_market_value'] >= min_mv]
        
        if max_pe > 0:
            df = df[(df['pe_dynamic'].isna()) | (df['pe_dynamic'] <= max_pe)]
        
        # 生成QLib Instruments格式
        qlib_df = pd.DataFrame({
            'instrument': df['instrument'],
            'symbol': df['symbol'],
            'name': df['name'],
            'industry': '',  # 需要另外补充
            'list_date': '',  # 需要另外补充
            'end_date': '20991231',
            'pe': df['pe_dynamic'],
            'pb': df['pb'],
            'total_mv': df['total_market_value'],
            'circ_mv': df['circ_market_value'],
            'update_time': df['update_time'] if 'update_time' in df.columns else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        filename = f"qlib_instruments_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = self.output_dir / filename
        
        qlib_df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.info(f"导出QLib Instruments: {len(qlib_df)} 支股票，更新时间: {qlib_df['update_time'].iloc[0]}")
        
        return filepath
    
    def export_with_custom_format(self, 
                                 include_fields: List[str] = None,
                                 output_format: str = "csv") -> Path:
        """
        自定义格式导出
        :param include_fields: 包含的字段列表
        :param output_format: 输出格式，支持csv, excel, parquet
        """
        raw_df = self.fetch_stock_spot_data()
        df = self.standardize_data(raw_df)
        
        # 添加更新时间
        update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df['update_time'] = update_time
        
        # 字段选择
        if include_fields:
            # 确保包含更新时间
            if 'update_time' not in include_fields:
                include_fields.append('update_time')
            df = df[include_fields]
        
        # 文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if output_format.lower() == "csv":
            filename = f"stock_spot_{timestamp}.csv"
            filepath = self.output_dir / filename
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
        elif output_format.lower() == "excel":
            filename = f"stock_spot_{timestamp}.xlsx"
            filepath = self.output_dir / filename
            df.to_excel(filepath, index=False)
            
        elif output_format.lower() == "parquet":
            filename = f"stock_spot_{timestamp}.parquet"
            filepath = self.output_dir / filename
            df.to_parquet(filepath, index=False)
            
        else:
            raise ValueError(f"不支持的格式: {output_format}")
        
        logger.info(f"导出{output_format.upper()}文件: {filepath}")
        logger.info(f"更新时间: {update_time}")
        
        return filepath


# 使用示例
if __name__ == "__main__":
    # 1. 初始化导出器
    exporter = StockSpotCSVExporter()
    
    # 2. 完整导出（包含更新时间列）
    print("开始导出A股实时行情数据（包含更新时间）...")
    csv_file = exporter.export_full_spot_data(
        filters={
            'total_market_value': (1e9, 1e12),  # 市值在10亿到1000亿之间
            'pe_dynamic': (0, 100)  # PE在0-100之间
        },
        sort_by='total_market_value',
        descending=True
    )
    
    print(f"导出完成: {csv_file}")
    
    # 3. 自定义字段导出
    print("\n自定义字段导出示例...")
    custom_fields = ['symbol', 'name', 'latest_price', 'change_pct', 'total_market_value', 'update_time']
    custom_file = exporter.export_with_custom_format(
        include_fields=custom_fields,
        output_format="csv"
    )
    print(f"自定义导出完成: {custom_file}")