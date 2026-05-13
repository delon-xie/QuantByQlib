"""
脚本模块
"""
from .migrate_cli import main as migrate_main
from .update_cli import main as update_main
from .export_cli import main as export_main
from .admin_cli import main as admin_main

__all__ = [
    'migrate_main',
    'update_main', 
    'export_main',
    'admin_main',
]