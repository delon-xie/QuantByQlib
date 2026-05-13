"""
数据导出命令行工具
"""
import argparse
import sys
from ..managers.bin_exporter import BinExportManager
from ..utils.logging_setup import setup_logging
import logging

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Export DuckDB data to Qlib bin format")
    parser.add_argument("--reg", type=str, default="cn", help="Market region")
    parser.add_argument("--output-dir", type=str, help="Output directory")
    parser.add_argument("--freq", type=str, nargs="+", help="Frequencies to export")
    parser.add_argument("--all", action="store_true", help="Export all frequencies")
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
    
    # 确定要导出的频率
    if args.all:
        freqs = None
    elif args.freq:
        freqs = args.freq
    else:
        print("Please specify frequencies with --freq or use --all for all frequencies")
        sys.exit(1)
    
    try:
        # 创建导出管理器
        manager = BinExportManager(reg=args.reg, output_dir=args.output_dir)
        
        # 执行导出
        results = manager.export_all_freqs(freqs)
        
        # 检查结果
        success = all("error" not in result for result in results.values())
        
        if success:
            logger.info("Export completed successfully!")
            sys.exit(0)
        else:
            logger.error("Export completed with errors")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Export failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()