"""
StateManager - 状态持久化管理器。
序列化/反序列化图表完整状态为 JSON 文件。
"""
import json
from datetime import datetime
from typing import Optional


class StateManager:
    """
    状态持久化管理器。
    支持保存/加载/导出图表指标、绘图和参数状态。
    """

    SAVE_FORMAT_VERSION = 1

    @staticmethod
    def save(state: dict, path: str):
        state['version'] = StateManager.SAVE_FORMAT_VERSION
        state['timestamp'] = datetime.now().isoformat()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load(path: str) -> dict:
        with open(path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        version = state.get('version', 0)
        if version != StateManager.SAVE_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported state version: {version}, "
                f"expected {StateManager.SAVE_FORMAT_VERSION}"
            )
        return state

    @staticmethod
    def build_state(active_indicators: dict,
                    chart_range: Optional[dict] = None,
                    drawings: Optional[list] = None,
                    params: Optional[dict] = None) -> dict:
        return {
            'version': StateManager.SAVE_FORMAT_VERSION,
            'indicators': active_indicators or {},
            'chart_range': chart_range or {},
            'drawings': drawings or [],
            'params': params or {},
            'timestamp': datetime.now().isoformat(),
        }

    @staticmethod
    def export_config(state: dict) -> dict:
        return {
            'version': state.get('version'),
            'indicators': state.get('indicators', {}),
            'drawings': state.get('drawings', []),
            'params': state.get('params', {}),
        }
