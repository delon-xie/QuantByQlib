#!/usr/bin/env python3
"""
从DuckDB提取股票日期范围并为每个指数更新QLib的instruments文件
"""

import duckdb
import pandas as pd
import os
from pathlib import Path
from datetime import datetime
import logging
from typing import List, Dict, Any

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class IndexInstrumentsUpdater:
    """指数instruments文件批量更新器"""
    
    def __init__(self, reg: str = "hk"):
        """
        初始化更新器
        
        Args:
            reg: 地区标识，如 "hk", "cn", "us"
        """
        self.reg = reg
        
        # 数据库路径
        self.db_path = Path.home() / ".qlib" / "duckdb" / f"{reg}_data.duckdb"
        
        # instruments目录路径
        self.instruments_dir = Path.home() / ".qlib" / "qlib_data" / f"{reg}_data" / "instruments"
        
        # 确保目录存在
        self.instruments_dir.mkdir(parents=True, exist_ok=True)
        
        # 连接对象
        self.conn = None
        
        # 处理结果
        self.results = {}
    
    def connect(self) -> bool:
        """连接到数据库"""
        if not self.db_path.exists():
            logger.error(f"❌ 数据库文件不存在: {self.db_path}")
            return False
        
        try:
            self.conn = duckdb.connect(str(self.db_path))
            logger.info(f"✅ 已连接到数据库: {self.db_path}")
            return True
        except Exception as e:
            logger.error(f"❌ 连接数据库失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("✅ 数据库连接已关闭")
    
    def get_all_index_names(self) -> List[str]:
        """
        从index_def表获取所有指数名称
        
        Returns:
            指数名称列表
        """
        try:
            query = "SELECT DISTINCT index_name FROM index_def ORDER BY index_name"
            result = self.conn.execute(query).fetchall()
            
            index_names = [row[0] for row in result]
            
            if index_names:
                logger.info(f"📊 从index_def表读取到 {len(index_names)} 个指数")
                logger.info(f"📄 指数列表: {', '.join(index_names[:10])}")
                if len(index_names) > 10:
                    logger.info(f"  ... 共 {len(index_names)} 个指数")
            else:
                logger.warning("⚠️ index_def表为空，没有找到任何指数")
            
            return index_names
            
        except Exception as e:
            logger.error(f"❌ 获取指数名称失败: {e}")
            return []
    
    def get_index_info(self, index_name: str) -> Dict[str, Any]:
        """获取指数的详细信息"""
        try:
            query = """
            SELECT index_name, index_type, description
            FROM index_def
            WHERE index_name = ?
            """
            result = self.conn.execute(query, (index_name,)).fetchone()
            
            if result:
                return {
                    'index_name': result[0],
                    'index_type': result[1],
                    'description': result[2]
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取指数信息失败: {e}")
            return None
    
    def get_index_member_count(self, index_name: str) -> int:
        """获取指数的成员数量"""
        try:
            query = """
            SELECT COUNT(DISTINCT symbol) as member_count
            FROM index_member
            WHERE index_name = ?
            """
            result = self.conn.execute(query, (index_name,)).fetchone()
            
            return result[0] if result else 0
            
        except Exception as e:
            logger.error(f"❌ 获取指数成员数量失败: {e}")
            return 0
    
    def get_symbol_date_ranges(self, index_name: str) -> pd.DataFrame:
        """
        获取指定指数中所有股票的实际交易日期范围
        
        Args:
            index_name: 指数名称
        
        Returns:
            包含股票代码、开始日期、结束日期的DataFrame
        """
        try:
            # 使用参数化查询避免SQL注入
            query = """
            SELECT 
                symbol, 
                CAST(MIN(datetime) AS DATE) as start_date, 
                CAST(MAX(datetime) AS DATE) as end_date
            FROM feature_day 
            WHERE symbol IS NOT NULL
            AND symbol IN (
                SELECT DISTINCT symbol 
                FROM index_member 
                WHERE index_name = ?
            )
            GROUP BY symbol
            ORDER BY symbol
            """
            
            logger.debug(f"执行查询: {query}")
            df = self.conn.execute(query, (index_name,)).fetchdf()
            
            if df.empty:
                logger.warning(f"⚠️ 指数 {index_name} 的成员在feature_day表中没有数据")
                return df
            
            # 格式转换
            df['start_date'] = pd.to_datetime(df['start_date']).dt.strftime('%Y-%m-%d')
            df['end_date'] = pd.to_datetime(df['end_date']).dt.strftime('%Y-%m-%d')
            
            return df
            
        except Exception as e:
            logger.error(f"❌ 获取股票日期范围失败: {e}")
            return pd.DataFrame()
    
    def save_instruments_file(self, index_name: str, df: pd.DataFrame) -> bool:
        """
        保存instruments文件
        
        Args:
            index_name: 指数名称
            df: 包含股票数据的DataFrame
        
        Returns:
            保存是否成功
        """
        try:
            # 构建输出文件路径
            if index_name.lower() == 'all':
                output_path = self.instruments_dir / f"all.txt"
            else:
                output_path = self.instruments_dir / f"{index_name.lower()}.txt"
            
            # 备份原文件
            backup_path = output_path.with_suffix('.txt.bak')
            if output_path.exists():
                import shutil
                shutil.copy2(output_path, backup_path)
                logger.debug(f"已备份原文件到: {backup_path}")
            
            # 保存文件
            df.to_csv(output_path, sep='\t', header=False, index=False)
            
            # 验证文件
            file_size = output_path.stat().st_size
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存文件失败: {e}")
            return False
    
    def validate_instruments_file(self, index_name: str) -> Dict[str, Any]:
        """验证instruments文件"""
        try:
            # 构建文件路径
            if index_name.lower() == 'all':
                file_path = self.instruments_dir / f"all.txt"
            else:
                file_path = self.instruments_dir / f"{index_name.lower()}.txt"
            
            if not file_path.exists():
                return {'status': 'error', 'message': f'文件不存在: {file_path}'}
            
            # 读取文件
            df = pd.read_csv(
                file_path, 
                sep='\t', 
                header=None, 
                names=['symbol', 'start_date', 'end_date']
            )
            
            # 检查数据质量
            issues = []
            for i, row in df.iterrows():
                if not row['symbol'] or pd.isna(row['symbol']):
                    issues.append(f"第{i+1}行: 股票代码为空")
                if not row['start_date'] or pd.isna(row['start_date']):
                    issues.append(f"第{i+1}行: 开始日期为空")
                if not row['end_date'] or pd.isna(row['end_date']):
                    issues.append(f"第{i+1}行: 结束日期为空")
            
            return {
                'status': 'success' if not issues else 'warning',
                'row_count': len(df),
                'unique_symbols': df['symbol'].nunique(),
                'start_date_min': df['start_date'].min() if len(df) > 0 else None,
                'end_date_max': df['end_date'].max() if len(df) > 0 else None,
                'issues': issues,
                'issue_count': len(issues)
            }
            
        except Exception as e:
            return {'status': 'error', 'message': f'验证文件失败: {e}'}
    
    def process_single_index(self, index_name: str) -> Dict[str, Any]:
        """处理单个指数"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 开始处理指数: {index_name}")
        logger.info(f"{'='*60}")
        
        # 获取指数信息
        index_info = self.get_index_info(index_name)
        if index_info:
            logger.info(f"📄 指数信息: {index_info}")
        
        # 获取指数成员数量
        member_count = self.get_index_member_count(index_name)
        logger.info(f"📈 指数成员数量: {member_count}")
        
        if member_count == 0:
            logger.warning(f"⚠️ 指数 {index_name} 没有成员，跳过")
            return {'status': 'skipped', 'reason': '没有成员', 'index_name': index_name}
        
        # 获取实际交易日期范围
        logger.info("📊 获取股票日期范围...")
        date_ranges_df = self.get_symbol_date_ranges(index_name)
        
        if date_ranges_df.empty:
            logger.warning(f"⚠️ 指数 {index_name} 的成员没有交易数据，跳过")
            return {'status': 'skipped', 'reason': '没有交易数据', 'index_name': index_name}
        
        logger.info(f"✅ 获取到 {len(date_ranges_df)} 个有交易数据的股票")
        
        # 显示统计信息
        if len(date_ranges_df) > 0:
            logger.info("📅 日期范围统计:")
            logger.info(f"  最早开始日期: {date_ranges_df['start_date'].min()}")
            logger.info(f"  最晚结束日期: {date_ranges_df['end_date'].max()}")
            
            # 按年份统计
            date_ranges_df['start_year'] = pd.to_datetime(date_ranges_df['start_date']).dt.year
            year_stats = date_ranges_df['start_year'].value_counts().sort_index()
            
            logger.info("  股票按上市年份统计:")
            for year, count in year_stats.head(5).items():
                logger.info(f"    {year}: {count} 个股票")
            
            if len(year_stats) > 5:
                logger.info(f"    ... 共 {len(year_stats)} 个年份")
        
        # 保存文件前，确保只保留必要的三列
        required_columns = ['symbol', 'start_date', 'end_date']
        
        # 检查DataFrame是否包含所有必需的列
        missing_columns = [col for col in required_columns if col not in date_ranges_df.columns]
        if missing_columns:
            logger.error(f"❌ DataFrame缺少必需的列: {missing_columns}")
            logger.error(f"   当前列: {list(date_ranges_df.columns)}")
            return {'status': 'failed', 'reason': f'缺少必需的列: {missing_columns}', 'index_name': index_name}
        
        # 只保留必要的列
        file_data_df = date_ranges_df[required_columns].copy()
        
        # 验证列的顺序
        logger.info(f"🔍 文件列顺序: {list(file_data_df.columns)}")
        
        # 保存文件
        logger.info(f"💾 保存文件...")
        if self.save_instruments_file(index_name, file_data_df):
            # 验证文件
            validation_result = self.validate_instruments_file(index_name)
            
            if validation_result['status'] == 'success':
                logger.info(f"✅ 文件保存成功: {len(file_data_df)} 行")
                logger.info(f"🔍 验证结果: 无问题")
            elif validation_result['status'] == 'warning':
                logger.warning(f"⚠️ 文件保存成功，但发现 {validation_result['issue_count']} 个问题")
                for issue in validation_result['issues'][:3]:
                    logger.warning(f"  {issue}")
                if validation_result['issue_count'] > 3:
                    logger.warning(f"  ... 共 {validation_result['issue_count']} 个问题")
            else:
                logger.error(f"❌ 文件验证失败: {validation_result['message']}")
                return {
                    'status': 'failed', 
                    'reason': '验证失败', 
                    'index_name': index_name,
                    'details': validation_result
                }
            
            return {
                'status': 'success',
                'index_name': index_name,
                'row_count': len(file_data_df),
                'validation_result': validation_result
            }
        else:
            logger.error(f"❌ 文件保存失败")
            return {'status': 'failed', 'reason': '保存失败', 'index_name': index_name}
    
    def update_all_indexes(self) -> Dict[str, Any]:
        """更新所有指数的instruments文件"""
        logger.info(f"🚀 开始更新 {self.reg.upper()} 地区所有指数的instruments文件")
        logger.info(f"📁 数据库: {self.db_path}")
        logger.info(f"📁 输出目录: {self.instruments_dir}")
        
        if not self.connect():
            return {'status': 'error', 'error': '数据库连接失败'}
        
        try:
            # 获取所有指数名称
            index_names = self.get_all_index_names()
            
            if not index_names:
                logger.error("❌ 没有找到任何指数，请检查index_def表")
                return {'status': 'error', 'error': '没有找到任何指数'}
            
            results = {}
            total_start_time = datetime.now()
            
            for index_name in index_names:
                start_time = datetime.now()
                
                # 处理单个指数
                result = self.process_single_index(index_name)
                results[index_name] = result
                
                # 记录处理时间
                elapsed_time = (datetime.now() - start_time).total_seconds()
                result['processing_time_seconds'] = elapsed_time
            
            # 统计结果
            total_time = (datetime.now() - total_start_time).total_seconds()
            
            success_count = sum(1 for r in results.values() if r.get('status') == 'success')
            failed_count = sum(1 for r in results.values() if r.get('status') == 'failed')
            skipped_count = sum(1 for r in results.values() if r.get('status') == 'skipped')
            
            # 输出汇总报告
            logger.info(f"\n{'='*60}")
            logger.info("📊 处理结果汇总")
            logger.info(f"{'='*60}")
            logger.info(f"  总耗时: {total_time:.2f} 秒")
            logger.info(f"  总指数数: {len(results)}")
            logger.info(f"  成功: {success_count}")
            logger.info(f"  失败: {failed_count}")
            logger.info(f"  跳过: {skipped_count}")
            
            # 详细结果
            for index_name, result in results.items():
                status = result.get('status')
                processing_time = result.get('processing_time_seconds', 0)
                
                if status == 'success':
                    row_count = result.get('row_count', 0)
                    logger.info(f"  ✅ {index_name:<20} 成功 ({row_count:>4} 行, {processing_time:.1f}秒)")
                elif status == 'failed':
                    reason = result.get('reason', '未知原因')
                    logger.info(f"  ❌ {index_name:<20} 失败 ({reason}, {processing_time:.1f}秒)")
                elif status == 'skipped':
                    reason = result.get('reason', '未知原因')
                    logger.info(f"  ⏭️  {index_name:<20} 跳过 ({reason}, {processing_time:.1f}秒)")
            
            # 保存处理结果到文件
            self.save_results_to_file(results, total_time)
            
            return {
                'status': 'completed',
                'results': results,
                'summary': {
                    'total': len(results),
                    'success': success_count,
                    'failed': failed_count,
                    'skipped': skipped_count,
                    'total_time_seconds': total_time
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 更新过程中发生异常: {e}")
            return {'status': 'error', 'error': str(e)}
        
        finally:
            self.disconnect()
    
    def save_results_to_file(self, results: Dict[str, Any], total_time: float) -> None:
        """保存处理结果到文件"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            result_file = self.instruments_dir / f"update_results_{timestamp}.json"
            
            import json
            
            # 将NumPy类型转换为Python原生类型
            def convert_to_serializable(obj):
                if hasattr(obj, 'item'):  # 处理NumPy类型
                    return obj.item()
                elif isinstance(obj, dict):
                    return {k: convert_to_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_to_serializable(item) for item in obj]
                else:
                    return obj
            
            # 序列化前转换数据类型
            serializable_results = convert_to_serializable(results)
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'region': self.reg,
                    'timestamp': timestamp,
                    'total_time_seconds': total_time,
                    'results': serializable_results
                }, f, ensure_ascii=False, indent=2)
            
            logger.info(f"📄 处理结果已保存到: {result_file}")
            
        except Exception as e:
            logger.error(f"❌ 保存结果文件失败: {e}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='为所有指数更新QLib的instruments文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --reg hk      # 更新港股所有指数
  %(prog)s --reg cn      # 更新A股所有指数
  %(prog)s --reg us      # 更新美股所有指数
  %(prog)s --reg hk --index hsi  # 只更新恒生指数
        """
    )
    
    parser.add_argument('--reg', type=str, default='hk', 
                       help='地区: hk(港股), cn(A股), us(美股)')
    parser.add_argument('--index', type=str, default=None,
                       help='指定单个指数名称，如果不指定则处理所有指数')
    parser.add_argument('--loglevel', type=str, default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='日志级别')
    
    args = parser.parse_args()
    
    # 设置日志级别
    logger.setLevel(getattr(logging, args.loglevel))
    
    # 创建更新器
    updater = IndexInstrumentsUpdater(reg=args.reg)
    
    if args.index:
        # 处理单个指数
        logger.info(f"🔧 开始处理单个指数: {args.index}")
        
        if updater.connect():
            result = updater.process_single_index(args.index)
            updater.disconnect()
            
            if result.get('status') == 'success':
                logger.info(f"✅ 指数 {args.index} 处理完成")
                return 0
            else:
                logger.error(f"❌ 指数 {args.index} 处理失败")
                return 1
        else:
            logger.error("❌ 数据库连接失败")
            return 1
    else:
        # 处理所有指数
        result = updater.update_all_indexes()
        
        if result.get('status') in ['completed', 'success']:
            summary = result.get('summary', {})
            logger.info(f"🎉 所有指数文件更新完成! "
                       f"成功: {summary.get('success', 0)}/{summary.get('total', 0)}, "
                       f"耗时: {summary.get('total_time_seconds', 0):.1f}秒")
            return 0
        else:
            logger.error(f"❌ 指数文件更新失败: {result.get('error', '未知错误')}")
            return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)