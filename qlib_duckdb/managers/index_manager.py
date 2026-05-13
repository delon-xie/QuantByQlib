"""
指数管理器 - 完整版本，包含所有方法
"""
import os
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import logging
from tqdm import tqdm
import sys
import numpy as np

from ..duckdb_connection import get_connection
from ..schema import SchemaManager
from ..exceptions import MigrationError, ValidationError
from ..config import config
from ..utils.validation import validate_instrument_df
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


class IndexManager:
    """指数管理器 - 完整版本"""
    
    def __init__(self, reg: str = None, batch_size: int = 10000):
        self.reg = reg or config.default_reg
        self.batch_size = batch_size  # 批处理大小
    
    def _parse_index_file(self, filepath: str) -> Tuple[str, pd.DataFrame]:
        """解析指数文件为 DataFrame，自动去重
        
        格式：文件名 = index_id, 每行第一个 \t 字段 = symbol
        可选的附加字段：start_date, end_date, weight
        """
        index_name = Path(filepath).stem
        
        records = []
        seen_symbols = set()  # 用于去重
        
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) < 1:
                    logger.warning(f"Invalid line {line_num} in {filepath}: {line}")
                    continue
                
                symbol = parts[0].strip()
                if not symbol:
                    logger.warning(f"Empty symbol in line {line_num} of {filepath}")
                    continue
                
                # 检查重复 symbol
                if symbol in seen_symbols:
                    logger.warning(f"Duplicate symbol '{symbol}' in {filepath}, line {line_num}")
                    continue
                seen_symbols.add(symbol)
                
                # 解析可选字段
                start_date = None
                end_date = None
                weight = None
                
                if len(parts) > 1 and parts[1].strip():
                    try:
                        val = parts[1].strip()
                        if '.' in val or any(c.isdigit() for c in val):
                            try:
                                weight = float(val)
                            except ValueError:
                                start_date = pd.Timestamp(val)
                    except:
                        logger.warning(f"Invalid value in line {line_num}: {parts[1]}")
                
                if len(parts) > 2 and parts[2].strip():
                    try:
                        val = parts[2].strip()
                        if not start_date and '.' not in val and any(c.isdigit() for c in val):
                            start_date = pd.Timestamp(val)
                        else:
                            end_date = pd.Timestamp(val)
                    except:
                        logger.warning(f"Invalid end_date in line {line_num}: {parts[2]}")
                
                if len(parts) > 3 and parts[3].strip():
                    try:
                        val = parts[3].strip()
                        if weight is None and ('.' in val or any(c.isdigit() for c in val)):
                            weight = float(val)
                        elif not end_date and '.' not in val and any(c.isdigit() for c in val):
                            end_date = pd.Timestamp(val)
                    except ValueError:
                        logger.warning(f"Invalid weight in line {line_num}: {parts[3]}")
                
                # 如果 start_date 和 end_date 都有值，确保 start_date <= end_date
                if start_date and end_date and start_date > end_date:
                    logger.warning(f"start_date {start_date} > end_date {end_date} for {symbol}, swapping")
                    start_date, end_date = end_date, start_date
                
                records.append({
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "weight": weight
                })
        
        df = pd.DataFrame(records)
        logger.info(f"Parsed index {index_name}: {len(df)} unique members")
        return index_name, df
    
    def _batch_insert_members(self, index_name: str, members_df: pd.DataFrame, on_conflict: str = "replace") -> int:
        """批量插入指数成分股到数据库，处理重复数据"""
        if members_df.empty:
            return 0
        
        # 1. 在插入前先对数据进行去重
        members_df = members_df.copy()
        original_count = len(members_df)
        
        # 按 symbol 去重，保留最后出现的记录
        members_df = members_df.drop_duplicates(subset=['symbol'], keep='last')
        
        duplicate_count = original_count - len(members_df)
        if duplicate_count > 0:
            logger.warning(f"Found {duplicate_count} duplicate symbols in {index_name}, keeping last occurrence")
        
        # 2. 添加 index_name 列
        members_df['index_name'] = index_name
        
        # 3. 重新排序列顺序
        cols = ['index_name', 'symbol', 'weight', 'start_date', 'end_date']
        members_df = members_df.reindex(columns=cols)
        
        with get_connection(self.reg, read_only=False) as conn:
            # 确保表存在
            SchemaManager.create_index_tables(self.reg)
            
            inserted = 0
            total_rows = len(members_df)
            
            # 根据冲突处理策略选择不同的 SQL
            if on_conflict == "replace":
                # 使用 UPSERT (INSERT OR REPLACE)
                for i in range(0, total_rows, self.batch_size):
                    batch_df = members_df.iloc[i:i + self.batch_size]
                    
                    data = []
                    for _, row in batch_df.iterrows():
                        data.append((
                            str(row['index_name']),
                            str(row['symbol']),
                            float(row['weight']) if pd.notna(row['weight']) else None,
                            row['start_date'] if pd.notna(row['start_date']) else None,
                            row['end_date'] if pd.notna(row['end_date']) else None
                        ))
                    
                    try:
                        conn.executemany("""
                            INSERT OR REPLACE INTO index_member (index_name, symbol, weight, start_date, end_date)
                            VALUES (?, ?, ?, ?, ?)
                        """, data)
                        inserted += len(data)
                        logger.debug(f"Batch {i//self.batch_size + 1}: inserted {len(data)} rows")
                    except Exception as e:
                        logger.error(f"Batch insert failed for batch {i//self.batch_size + 1}: {e}")
                        # 回退到逐行插入
                        for record in data:
                            try:
                                conn.execute("""
                                    INSERT OR REPLACE INTO index_member (index_name, symbol, weight, start_date, end_date)
                                    VALUES (?, ?, ?, ?, ?)
                                """, record)
                                inserted += 1
                            except Exception as e2:
                                logger.warning(f"Failed to insert {record[1]}: {e2}")
                
            else:  # ignore 或其他策略
                # 先删除现有数据
                conn.execute(
                    "DELETE FROM index_member WHERE index_name = ?",
                    (index_name,)
                )
                
                # 再批量插入
                for i in range(0, total_rows, self.batch_size):
                    batch_df = members_df.iloc[i:i + self.batch_size]
                    
                    data = []
                    for _, row in batch_df.iterrows():
                        data.append((
                            str(row['index_name']),
                            str(row['symbol']),
                            float(row['weight']) if pd.notna(row['weight']) else None,
                            row['start_date'] if pd.notna(row['start_date']) else None,
                            row['end_date'] if pd.notna(row['end_date']) else None
                        ))
                    
                    try:
                        conn.executemany("""
                            INSERT INTO index_member (index_name, symbol, weight, start_date, end_date)
                            VALUES (?, ?, ?, ?, ?)
                        """, data)
                        inserted += len(data)
                        logger.debug(f"Batch {i//self.batch_size + 1}: inserted {len(data)} rows")
                    except Exception as e:
                        logger.error(f"Batch insert failed for batch {i//self.batch_size + 1}: {e}")
                        # 回退到逐行插入
                        for record in data:
                            try:
                                conn.execute("""
                                    INSERT INTO index_member (index_name, symbol, weight, start_date, end_date)
                                    VALUES (?, ?, ?, ?, ?)
                                """, record)
                                inserted += 1
                            except Exception as e2:
                                logger.warning(f"Failed to insert {record[1]}: {e2}")
            
            logger.info(f"Inserted {inserted}/{total_rows} members for index {index_name}")
            return inserted
    
    def import_index_from_file(
        self, 
        filepath: str, 
        index_type: str = "custom",
        description: str = "",
        on_conflict: str = "replace"
    ) -> Dict[str, Any]:
        """从文件导入指数（修复重复记录问题）"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Index file not found: {filepath}")
        
        try:
            # 1. 解析文件（已包含去重）
            index_name, members_df = self._parse_index_file(filepath)
            
            if members_df.empty:
                logger.warning(f"No valid members found in {filepath}")
                return {"index_name": index_name, "members_imported": 0}
            
            # 2. 插入指数定义
            with get_connection(self.reg, read_only=False) as conn:
                SchemaManager.create_index_tables(self.reg)
                
                if on_conflict == "replace":
                    # 使用 upsert
                    conn.execute("""
                        INSERT OR REPLACE INTO index_def (index_name, index_type, description)
                        VALUES (?, ?, ?)
                    """, (index_name, index_type, description))
                else:
                    # 尝试插入，忽略冲突
                    conn.execute("""
                        INSERT OR IGNORE INTO index_def (index_name, index_type, description)
                        VALUES (?, ?, ?)
                    """, (index_name, index_type, description))
            
            # 3. 批量插入成分股（已处理重复）
            members_imported = self._batch_insert_members(index_name, members_df, on_conflict)
            
            logger.info(f"Imported index {index_name}: {members_imported} members")
            
            return {
                "index_name": index_name,
                "index_type": index_type,
                "description": description,
                "members_imported": members_imported,
                "total_members": len(members_df),
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Failed to import index from {filepath}: {e}", exc_info=True)
            raise MigrationError(f"Failed to import index: {e}")
    
    def import_multiple_indices(self, index_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """批量导入多个指数，处理重复数据
        
        Args:
            index_dict: {
                "index_name1": {
                    "type": "custom",
                    "description": "desc",
                    "members_df": DataFrame,  # 包含 symbol, weight, start_date, end_date
                },
                ...
            }
        """
        if not index_dict:
            return {}
        
        results = {}
        with get_connection(self.reg, read_only=False) as conn:
            # 确保表存在
            SchemaManager.create_index_tables(self.reg)
            
            # 1. 批量插入指数定义
            def_records = []
            for idx_name, idx_info in index_dict.items():
                def_records.append((
                    idx_name,
                    idx_info.get("type", "custom"),
                    idx_info.get("description", "")
                ))
            
            if def_records:
                try:
                    conn.executemany("""
                        INSERT OR REPLACE INTO index_def (index_name, index_type, description)
                        VALUES (?, ?, ?)
                    """, def_records)
                except Exception as e:
                    logger.error(f"Failed to insert index definitions: {e}")
                    raise
            
            # 2. 批量插入所有成分股，处理重复
            all_member_records = []
            for idx_name, idx_info in index_dict.items():
                members_df = idx_info.get("members_df")
                if members_df is not None and not members_df.empty:
                    # 对每个指数内的数据进行去重
                    members_df = members_df.drop_duplicates(subset=['symbol'], keep='last')
                    
                    for _, row in members_df.iterrows():
                        all_member_records.append((
                            idx_name,
                            str(row.get('symbol', '')).strip(),
                            float(row['weight']) if pd.notna(row.get('weight')) else None,
                            row.get('start_date') if pd.notna(row.get('start_date')) else None,
                            row.get('end_date') if pd.notna(row.get('end_date')) else None
                        ))
            
            if all_member_records:
                try:
                    # 使用 INSERT OR REPLACE 处理重复
                    conn.executemany("""
                        INSERT OR REPLACE INTO index_member (index_name, symbol, weight, start_date, end_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, all_member_records)
                    logger.info(f"Bulk inserted {len(all_member_records)} members for {len(index_dict)} indices")
                    
                except Exception as e:
                    logger.error(f"Batch insert failed: {e}")
                    
                    # 尝试更详细的错误处理
                    duplicate_info = {}
                    for i, record in enumerate(all_member_records):
                        try:
                            conn.execute("""
                                INSERT OR REPLACE INTO index_member (index_name, symbol, weight, start_date, end_date)
                                VALUES (?, ?, ?, ?, ?)
                            """, record)
                        except Exception as row_error:
                            duplicate_info.setdefault(str(row_error), []).append(record[1])
                    
                    if duplicate_info:
                        for error_msg, symbols in duplicate_info.items():
                            logger.error(f"Error: {error_msg}")
                            logger.error(f"  Affected symbols (sample): {symbols[:10]}")
                    
                    raise
        
        return results
    
    def import_indexes_from_directory(
        self, 
        directory: str, 
        index_type: str = "custom",
        description_suffix: str = "imported from file",
        on_conflict: str = "replace"
    ) -> Dict[str, Dict[str, Any]]:
        """从目录批量导入指数（优化版）"""
        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        # 查找所有txt文件
        txt_files = list(Path(directory).glob("*.txt"))
        
        if not txt_files:
            logger.warning(f"No .txt files found in {directory}")
            return {}
        
        logger.info(f"Found {len(txt_files)} index files in {directory}")
        
        # 先解析所有文件
        index_data = {}
        for filepath in tqdm(txt_files, desc="Parsing index files"):
            try:
                index_name, members_df = self._parse_index_file(str(filepath))
                if not members_df.empty:
                    index_data[index_name] = {
                        "type": index_type,
                        "description": f"{index_name} {description_suffix}",
                        "members_df": members_df
                    }
            except Exception as e:
                logger.error(f"Failed to parse {filepath.name}: {e}")
        
        # 批量导入
        if index_data:
            results = self.import_multiple_indices(index_data)
            self._print_import_summary(index_data, results)
            return results
        
        return {}
    
    def _print_import_summary(self, index_data: Dict, results: Dict):
        """打印导入摘要"""
        logger.info("=" * 50)
        logger.info("Index Import Summary")
        logger.info("=" * 50)
        
        total_members = 0
        for idx_name, idx_info in index_data.items():
            members_count = len(idx_info.get("members_df", pd.DataFrame()))
            total_members += members_count
            logger.info(f"{idx_name:<30} | {members_count:>6,d} members")
        
        logger.info("=" * 50)
        logger.info(f"Total indices: {len(index_data):,d}")
        logger.info(f"Total members: {total_members:,d}")
    
    def get_index_definition(self, index_name: str) -> Optional[Dict[str, Any]]:
        """获取指数定义"""
        with get_connection(self.reg) as conn:
            result = conn.execute("""
                SELECT index_name, index_type, description
                FROM index_def
                WHERE index_name = ?
            """, (index_name,)).fetchone()
            
            if result:
                return {
                    "index_name": result[0],
                    "index_type": result[1],
                    "description": result[2]
                }
        return None
    
    def get_index_members(
        self, 
        index_name: str,
        as_of_date: Optional[str] = None
    ) -> pd.DataFrame:
        """获取指数成分股（返回 DataFrame）"""
        query = """
            SELECT symbol, weight, start_date, end_date
            FROM index_member
            WHERE index_name = ?
        """
        params = [index_name]
        
        if as_of_date:
            query += " AND (start_date IS NULL OR start_date <= ?)"
            query += " AND (end_date IS NULL OR end_date >= ?)"
            params.extend([as_of_date, as_of_date])
        
        query += " ORDER BY COALESCE(weight, 0) DESC, symbol"
        
        with get_connection(self.reg) as conn:
            df = pd.read_sql_query(query, conn, params=tuple(params))
        
        return df if not df.empty else pd.DataFrame(
            columns=["symbol", "weight", "start_date", "end_date"]
        )
    
    def get_all_indexes(self) -> pd.DataFrame:
        """获取所有指数（返回 DataFrame）"""
        with get_connection(self.reg) as conn:
            df = pd.read_sql_query("""
                SELECT index_name, index_type, description
                FROM index_def
                ORDER BY index_name
            """, conn)
        
        return df if not df.empty else pd.DataFrame(
            columns=["index_name", "index_type", "description"]
        )
    
    def sync_from_qlib(self, qlib_dir: str = None) -> Dict[str, Any]:
        """从 Qlib 原始 instruments 目录同步指数（缺失的方法）
        
        这是你调用的方法，被遗漏了
        """
        if qlib_dir is None:
            # 尝试从环境变量或默认路径获取
            qlib_dir = os.environ.get("QLIB_DATA_DIR")
            if not qlib_dir:
                # 默认路径
                qlib_dir = f"~/.qlib/qlib_data/{self.reg}_data"
        
        qlib_dir = os.path.expanduser(qlib_dir)
        instruments_dir = os.path.join(qlib_dir, "instruments")
        
        if not os.path.exists(instruments_dir):
            logger.warning(f"Qlib instruments directory not found: {instruments_dir}")
            return {
                "status": "failed", 
                "reason": f"Directory not found: {instruments_dir}",
                "source_dir": instruments_dir
            }
        
        logger.info(f"Syncing indices from Qlib directory: {instruments_dir}")
        
        try:
            # 使用现有的批量导入方法
            results = self.import_indexes_from_directory(
                instruments_dir,
                index_type="qlib_standard",
                description_suffix="(synced from Qlib)",
                on_conflict="replace"
            )
            
            return {
                "status": "completed",
                "results": results,
                "source_dir": instruments_dir,
                "indices_synced": len(results)
            }
            
        except Exception as e:
            logger.error(f"Failed to sync from Qlib: {e}", exc_info=True)
            return {
                "status": "failed",
                "reason": str(e),
                "source_dir": instruments_dir
            }
    
    def export_to_qlib_format(
        self, 
        index_name: str, 
        output_dir: str
    ) -> str:
        """导出指数为 Qlib 格式"""
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{index_name}.txt")
        
        # 获取成分股 DataFrame
        members_df = self.get_index_members(index_name)
        
        if members_df.empty:
            logger.warning(f"No members found for index {index_name}")
            return ""
        
        # 使用 pandas 格式化输出
        def format_row(row):
            parts = [str(row['symbol'])]
            
            if pd.notna(row['weight']):
                parts.append(f"{row['weight']:.6f}")
            else:
                parts.append("")
            
            if pd.notna(row['start_date']):
                if hasattr(row['start_date'], 'strftime'):
                    parts.append(row['start_date'].strftime("%Y-%m-%d"))
                else:
                    parts.append(str(row['start_date']))
            else:
                parts.append("")
            
            if pd.notna(row['end_date']):
                if hasattr(row['end_date'], 'strftime'):
                    parts.append(row['end_date'].strftime("%Y-%m-%d"))
                else:
                    parts.append(str(row['end_date']))
            else:
                parts.append("")
            
            return "\t".join(parts)
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            for _, row in members_df.iterrows():
                f.write(format_row(row) + "\n")
        
        logger.info(f"Exported index {index_name} ({len(members_df)} members) to {output_path}")
        return output_path
    
    def export_all_to_qlib_format(self, output_dir: str) -> Dict[str, str]:
        """导出所有指数到 Qlib 格式"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取所有指数
        indexes_df = self.get_all_indexes()
        
        results = {}
        for index_name in tqdm(indexes_df['index_name'], desc="Exporting indexes"):
            try:
                path = self.export_to_qlib_format(index_name, output_dir)
                if path:
                    results[index_name] = path
            except Exception as e:
                logger.error(f"Failed to export {index_name}: {e}")
        
        logger.info(f"Exported {len(results)} indexes to {output_dir}")
        return results
    
    def clean_duplicate_members(self, index_name: str = None) -> Dict[str, int]:
        """清理重复的成分股记录
        
        Args:
            index_name: 指数名称，为 None 时清理所有指数
            
        Returns:
            包含清理数量的字典
        """
        with get_connection(self.reg, read_only=False) as conn:
            if index_name:
                # 清理指定指数的重复记录
                # 先找出重复记录
                duplicates = conn.execute("""
                    SELECT symbol, COUNT(*) as cnt
                    FROM index_member
                    WHERE index_name = ?
                    GROUP BY symbol
                    HAVING COUNT(*) > 1
                """, (index_name,)).fetchall()
                
                if not duplicates:
                    logger.info(f"No duplicates found for index {index_name}")
                    return {"cleaned": 0}
                
                # 为每个重复的 symbol 保留最新的记录（按 rowid）
                cleaned = 0
                for symbol, count in duplicates:
                    result = conn.execute("""
                        DELETE FROM index_member
                        WHERE index_name = ? AND symbol = ? 
                        AND rowid NOT IN (
                            SELECT MAX(rowid)
                            FROM index_member
                            WHERE index_name = ? AND symbol = ?
                        )
                    """, (index_name, symbol, index_name, symbol))
                    cleaned += result.rowcount if hasattr(result, 'rowcount') else 1
                
                logger.info(f"Cleaned {cleaned} duplicate records for index {index_name}")
                return {"index_name": index_name, "cleaned": cleaned}
            
            else:
                # 清理所有指数的重复记录
                cleaned_total = 0
                
                # 获取所有指数
                indexes = conn.execute("SELECT DISTINCT index_name FROM index_member").fetchall()
                
                for (idx_name,) in indexes:
                    cleaned = self.clean_duplicate_members(idx_name).get("cleaned", 0)
                    cleaned_total += cleaned
                
                logger.info(f"Cleaned {cleaned_total} duplicate records for all indices")
                return {"total_cleaned": cleaned_total}
    
    def validate_index_data(self, index_name: str = None) -> Dict[str, Any]:
        """验证指数数据完整性，包括重复记录检查
        
        Args:
            index_name: 指数名称，为 None 时检查所有指数
            
        Returns:
            验证结果字典
        """
        with get_connection(self.reg) as conn:
            if index_name:
                # 检查单个指数
                # 检查重复记录
                duplicates = conn.execute("""
                    SELECT symbol, COUNT(*) as cnt
                    FROM index_member
                    WHERE index_name = ?
                    GROUP BY symbol
                    HAVING COUNT(*) > 1
                """, (index_name,)).fetchall()
                
                # 检查空值
                null_counts = conn.execute("""
                    SELECT 
                        COUNT(CASE WHEN weight IS NULL THEN 1 END) as null_weight,
                        COUNT(CASE WHEN start_date IS NULL THEN 1 END) as null_start_date,
                        COUNT(CASE WHEN end_date IS NULL THEN 1 END) as null_end_date
                    FROM index_member
                    WHERE index_name = ?
                """, (index_name,)).fetchone()
                
                # 检查无效日期范围
                invalid_dates = conn.execute("""
                    SELECT COUNT(*)
                    FROM index_member
                    WHERE index_name = ?
                    AND start_date IS NOT NULL 
                    AND end_date IS NOT NULL
                    AND start_date > end_date
                """, (index_name,)).fetchone()
                
                return {
                    "index_name": index_name,
                    "has_duplicates": len(duplicates) > 0,
                    "duplicate_count": len(duplicates),
                    "duplicates": [(symbol, cnt) for symbol, cnt in duplicates],
                    "null_weight": null_counts[0],
                    "null_start_date": null_counts[1],
                    "null_end_date": null_counts[2],
                    "has_invalid_dates": invalid_dates[0] > 0,
                    "invalid_date_count": invalid_dates[0]
                }
            
            else:
                # 检查所有指数
                all_indexes = conn.execute("SELECT DISTINCT index_name FROM index_def").fetchall()
                results = {}
                
                for (idx_name,) in all_indexes:
                    results[idx_name] = self.validate_index_data(idx_name)
                
                # 汇总统计
                total_duplicates = sum(r["duplicate_count"] for r in results.values())
                total_invalid = sum(r["invalid_date_count"] for r in results.values())
                
                return {
                    "summary": {
                        "total_indexes": len(all_indexes),
                        "total_duplicates": total_duplicates,
                        "total_invalid_dates": total_invalid,
                        "indexes_with_duplicates": sum(1 for r in results.values() if r["has_duplicates"]),
                        "indexes_with_invalid_dates": sum(1 for r in results.values() if r["has_invalid_dates"]),
                    },
                    "details": results
                }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with get_connection(self.reg) as conn:
            # 指数数量
            idx_count = conn.execute(
                "SELECT COUNT(*) FROM index_def"
            ).fetchone()[0]
            
            # 成分股总数
            member_count = conn.execute(
                "SELECT COUNT(*) FROM index_member"
            ).fetchone()[0]
            
            # 平均每个指数的成分股数
            avg_members = member_count / idx_count if idx_count > 0 else 0
            
            # 有权重的指数数量
            weighted_idx = conn.execute("""
                SELECT COUNT(DISTINCT index_name) 
                FROM index_member 
                WHERE weight IS NOT NULL
            """).fetchone()[0]
            
            # 有日期范围的指数数量
            dated_idx = conn.execute("""
                SELECT COUNT(DISTINCT index_name) 
                FROM index_member 
                WHERE start_date IS NOT NULL OR end_date IS NOT NULL
            """).fetchone()[0]
        
        return {
            "total_indexes": idx_count,
            "total_members": member_count,
            "avg_members_per_index": round(avg_members, 2),
            "weighted_indexes": weighted_idx,
            "dated_indexes": dated_idx
        }
    
    def delete_index(self, index_name: str, cascade: bool = True) -> int:
        """删除指数"""
        with get_connection(self.reg, read_only=False) as conn:
            # 删除成分股
            members_deleted = 0
            if cascade:
                try:
                    # 先查询数量
                    result = conn.execute(
                        "SELECT COUNT(*) FROM index_member WHERE index_name = ?",
                        (index_name,)
                    ).fetchone()
                    members_deleted = result[0] if result else 0
                    
                    # 删除
                    conn.execute(
                        "DELETE FROM index_member WHERE index_name = ?",
                        (index_name,)
                    )
                except Exception as e:
                    logger.warning(f"Error deleting index members: {e}")
                    members_deleted = 0
            
            # 删除指数定义
            conn.execute(
                "DELETE FROM index_def WHERE index_name = ?",
                (index_name,)
            )
        
        logger.info(f"Deleted index {index_name} and {members_deleted} members")
        return members_deleted


# 使用示例
if __name__ == "__main__":
    # 初始化管理器
    manager = IndexManager(reg="cn", batch_size=5000)
    
    # 测试 sync_from_qlib 方法
    print("测试从 Qlib 同步指数...")
    result = manager.sync_from_qlib()
    print(f"同步结果: {result['status']}")
    
    if result['status'] == 'completed':
        print(f"同步了 {result.get('indices_synced', 0)} 个指数")
    
    # 获取统计信息
    stats = manager.get_statistics()
    print(f"统计信息: {stats}")