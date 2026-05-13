"""
Qlib 版本兼容性模块
"""

import importlib
import warnings
import sys
import logging
import inspect

logger = logging.getLogger(__name__)


def get_qlib_class(class_name):
    """
    获取 Qlib 类，支持不同版本
    
    Args:
        class_name: 类名
    
    Returns:
        对应的类
    """
    # 特殊处理 DataProvider
    if class_name == "DataProvider":
        return _get_data_provider_class()
    
    # 其他类的处理逻辑保持不变
    logger.debug(f"Looking for {class_name} in qlib modules...")
    
    import_paths = [
        f"qlib.data.storage.{class_name}",
        f"qlib.data.data.{class_name}",
        f"qlib.data.{class_name}",
    ]
    
    for import_path in import_paths:
        try:
            module_path, class_name_only = import_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            
            if hasattr(module, class_name_only):
                logger.info(f"Found {class_name} at {module_path}")
                return getattr(module, class_name_only)
        except (ImportError, AttributeError) as e:
            logger.debug(f"Not found at {import_path}: {e}")
            continue
    
    raise ImportError(f"Cannot import {class_name} from qlib modules")


def _get_data_provider_class():
    """
    专门处理 DataProvider 类的导入
    Qlib 中 DataProvider 可能有不同的实现
    """
    logger.debug("Looking for DataProvider in qlib...")
    
    try:
        import qlib
        
        # 方法1：尝试从 qlib.data 导入
        try:
            from qlib.data import DataProvider
            logger.info("Found DataProvider in qlib.data")
            return DataProvider
        except ImportError:
            pass
        
        # 方法2：尝试从 qlib.data.base 导入
        try:
            from qlib.data.base import DataProvider
            logger.info("Found DataProvider in qlib.data.base")
            return DataProvider
        except ImportError:
            pass
        
        # 方法3：尝试从 qlib.data.handler 导入
        try:
            from qlib.data.handler import DataProvider
            logger.info("Found DataProvider in qlib.data.handler")
            return DataProvider
        except ImportError:
            pass
        
        # 方法4：查找 qlib.data 模块中所有以 Provider 结尾的类
        import qlib.data
        for attr_name in dir(qlib.data):
            if attr_name.endswith('Provider') and attr_name != 'DataProvider':
                attr = getattr(qlib.data, attr_name)
                if inspect.isclass(attr):
                    logger.info(f"Found provider class: {attr_name} in qlib.data")
                    return attr
        
        # 方法5：检查 qlib 的注册表
        if hasattr(qlib.data, 'provider'):
            provider = qlib.data.provider
            if hasattr(provider, '__class__'):
                logger.info(f"Found provider instance: {provider.__class__}")
                return provider.__class__
        
        # 方法6：如果以上都失败，查看是否有默认的 provider
        if hasattr(qlib, 'provider'):
            provider = qlib.provider
            if hasattr(provider, '__class__'):
                logger.info(f"Found qlib.provider instance: {provider.__class__}")
                return provider.__class__
    
    except Exception as e:
        logger.debug(f"Error while searching for DataProvider: {e}")
    
    # 如果都找不到，返回一个基本的抽象类
    logger.warning("Could not find DataProvider in qlib. Using abstract base class.")
    
    class AbstractDataProvider:
        """DataProvider 抽象基类（兼容性回退）"""
        def feature(self, feature_field: str = None):
            raise NotImplementedError("Feature storage not implemented")
        
        def calendar(self):
            raise NotImplementedError("Calendar storage not implemented")
        
        def instrument(self):
            raise NotImplementedError("Instrument storage not implemented")
        
        def get_config(self) -> dict:
            return {}
        
        def set_config(self, **kwargs):
            pass
        
        def instruments(self, market: str = "all", filter_pipe=None) -> list:
            return []
        
        def list_instruments(self, instruments, start_time=None, end_time=None, freq="day", as_list=False):
            if as_list:
                return []
            return None
        
        def features(self, instruments, fields, start_time, end_time, freq):
            import pandas as pd
            return pd.DataFrame()
        
        def get_calendar(self, freq, future=False, start_time=None, end_time=None) -> list:
            return []
    
    return AbstractDataProvider


# 常用类的快捷方式
try:
    FeatureStorage = get_qlib_class('FeatureStorage')
    CalendarStorage = get_qlib_class('CalendarStorage')
    InstrumentStorage = get_qlib_class('InstrumentStorage')
    DataProvider = _get_data_provider_class()  # 使用专门的方法
except ImportError as e:
    logger.warning(f"Failed to import some Qlib classes: {e}")
    # 设置占位符
    FeatureStorage = CalendarStorage = InstrumentStorage = None
    DataProvider = _get_data_provider_class()  # 这个方法总会返回一个类