"""
数据迁移命令行工具
"""
import argparse
import sys
from pathlib import Path
from ..managers.data_migrate import DataMigrateManager
from ..utils.logging_setup import setup_logging
import logging

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Migrate Qlib data to DuckDB")
    parser.add_argument("--reg", type=str, default="cn", help="Market region (cn, us, hk, etc.)")
    parser.add_argument("--qlib-dir", type=str, help="Qlib data directory")
    parser.add_argument("--freq", type=str, nargs="+", help="Frequencies to migrate")
    parser.add_argument("--all", action="store_true", help="Migrate all frequencies")
    parser.add_argument("--list-freqs", action="store_true", help="List all supported frequencies")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging()
    
    if args.list_freqs:
        from ..constants import SUPPORTED_FREQS
        print("Supported frequencies:")
        for freq in SUPPORTED_FREQS:
            print(f"  - {freq}")
        return
    
    # 确定要迁移的频率
    if args.all:
        freqs = None  # None 表示所有频率
    elif args.freq:
        freqs = args.freq
    else:
        print("Please specify frequencies with --freq or use --all for all frequencies")
        sys.exit(1)
    
    try:
        # 创建迁移管理器
        manager = DataMigrateManager(reg=args.reg, qlib_dir=args.qlib_dir)
        
        # 执行迁移
        results = manager.migrate_all_freqs(freqs)
        
        # 检查结果
        success = all(result.get("status") == "success" for result in results.values())
        
        if success:
            logger.info("Migration completed successfully!")
            sys.exit(0)
        else:
            logger.error("Migration completed with errors")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()