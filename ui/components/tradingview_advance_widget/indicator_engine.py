"""
PythonIndicatorEngine - Python 端指标计算引擎。
只处理 lightweight-charts-indicators 无法处理的自定义指标。

增强:
- 更多自定义指标 (ZigZag, KDJ_custom, VolumeProfile 增强版)
- 动态方法查找 (_calc_{key} 约定)
- 双引擎支持 (JS/Python/auto)
"""
from typing import Callable, Optional
import pandas as pd
import numpy as np


class PythonIndicatorEngine:
    """
    Python 端指标计算引擎。
    注册自定义指标计算函数，供 JS 端通过 bridge 请求。
    """

    def __init__(self):
        self._custom_indicators: dict[str, Callable] = {}
        self._custom_descriptions: dict[str, dict] = {}
        self._register_builtin_customs()

    def _register_builtin_customs(self):
        """注册内置自定义指标"""
        self.register(
            'Yearly_Profile',
            self._calc_yearly_profile,
            {
                'description': '年度成交量分布图 (Yearly Price Profile)',
                'params': {
                    'period': {'type': 'int', 'default': 252, 'min': 20, 'max': 1000}
                }
            }
        )

        self.register(
            'ZigZag',
            self._calc_zigzag,
            {
                'description': 'ZigZag 之字转向指标 (Python 版)',
                'params': {
                    'percent_change': {'type': 'float', 'default': 5.0, 'min': 0.1, 'max': 50.0}
                }
            }
        )

        self.register(
            'KDJ_Custom',
            self._calc_kdj_custom,
            {
                'description': 'KDJ 自定义版 (带 KDJ 信号线)',
                'params': {
                    'k_length': {'type': 'int', 'default': 9, 'min': 2, 'max': 50},
                    'd_length': {'type': 'int', 'default': 3, 'min': 2, 'max': 30},
                    'j_length': {'type': 'int', 'default': 3, 'min': 1, 'max': 30},
                }
            }
        )

        self.register(
            'VolumeProfile',
            self._calc_volume_profile,
            {
                'description': '成交量剖面 (Volume Profile POC)',
                'params': {
                    'num_bins': {'type': 'int', 'default': 20, 'min': 5, 'max': 100}
                }
            }
        )

        self.register(
            'PivotPoints',
            self._calc_pivot_points,
            {
                'description': '枢轴点 (Pivot Points, 支持 Floor/Camarilla/Woodie)',
                'params': {
                    'type': {'type': 'string', 'default': 'floor', 'options': ['floor', 'camarilla', 'woodie']}
                }
            }
        )

    def register(self, key: str, fn: Callable,
                 description: Optional[dict] = None):
        self._custom_indicators[key] = fn
        if description:
            self._custom_descriptions[key] = description

    def can_handle(self, key: str) -> bool:
        return key in self._custom_indicators

    def calculate(self, key: str, df: pd.DataFrame,
                  params: Optional[dict] = None) -> dict:
        """通过注册的函数计算指标"""
        if key not in self._custom_indicators:
            raise ValueError(f"Unknown custom indicator: {key}")
        return self._custom_indicators[key](df, params or {})

    def dynamic_calculate(self, key: str, df: pd.DataFrame,
                          params: Optional[dict] = None) -> dict:
        """
        动态方法查找
        通过 _calc_{key.lower()} 方法名约定自动查找
        """
        method_name = f'_calc_{key.lower()}'
        method = getattr(self, method_name, None)
        if method and callable(method):
            print(f"  [Dynamic] Found method: {method_name}")
            try:
                result = method(df, params or {})
                if result:
                    return result
            except Exception as e:
                print(f"  [Dynamic] Method {method_name} failed: {e}")

        # 第二级 fallback: _calc_ 前缀 + 各种变体
        for attr_name in dir(self):
            if attr_name.startswith('_calc_') and key.lower() in attr_name.lower():
                method = getattr(self, attr_name)
                if callable(method):
                    try:
                        return method(df, params or {})
                    except Exception:
                        continue
        return {}

    def list_custom(self) -> list[dict]:
        return [
            {'key': k, 'description': self._custom_descriptions.get(k, {})}
            for k in self._custom_indicators
        ]

    # ==================== 内置指标计算函数 ====================

    def _map_columns(self, df: pd.DataFrame) -> dict:
        """标准化列名映射"""
        targets = ['open', 'high', 'low', 'close', 'volume', 'date']
        result = {}
        lower_cols = {str(c).lower(): c for c in df.columns}
        for t in targets:
            if t in lower_cols:
                result[t] = lower_cols[t]
            elif t == 'date' and 'datetime' in lower_cols:
                result[t] = lower_cols['datetime']
            else:
                for col in lower_cols:
                    if t in col:
                        result[t] = lower_cols[col]
                        break
                else:
                    result[t] = None
        return result

    def _calc_yearly_profile(self, df: pd.DataFrame,
                             params: dict) -> dict:
        """年度成交量分布图"""
        period = params.get('period', 252)
        cols = self._map_columns(df)
        if not all([cols['high'], cols['low'], cols['close']]):
            return {}

        high_252 = df[cols['high']].rolling(window=period, min_periods=1).max()
        low_252 = df[cols['low']].rolling(window=period, min_periods=1).min()
        denom = (high_252 - low_252).replace(0, float('nan'))
        pct = (df[cols['close']] - low_252) / denom * 100

        dates = pd.to_datetime(
            df[cols['date']]).dt.strftime('%Y-%m-%d').values

        data = [
            {'time': dates[i], 'value': float(pct.iloc[i])}
            for i in range(len(df)) if not pd.isna(pct.iloc[i])
        ]
        mid = [{'time': dates[i], 'value': 50.0}
               for i in range(len(df))]

        return {'Yearly_Profile': data, 'Yearly_Profile_MID': mid}

    def _calc_zigzag(self, df: pd.DataFrame, params: dict) -> dict:
        """ZigZag 之字转向指标 (Python 版)"""
        percent_change = params.get('percent_change', 5.0)
        cols = self._map_columns(df)
        if not all([cols['date'], cols['high'], cols['low']]):
            return {}

        dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
        highs = df[cols['high']].values
        lows = df[cols['low']].values
        threshold = percent_change / 100.0

        pivot_indices = [0]
        pivot_prices = [(highs[0] + lows[0]) / 2]
        current_extreme_idx = 0
        current_extreme_price = (highs[0] + lows[0]) / 2
        current_direction = None

        for i in range(1, len(highs)):
            mid_price = (highs[i] + lows[i]) / 2

            if current_direction is None:
                if mid_price > current_extreme_price * (1 + threshold):
                    current_direction = 'up'
                elif mid_price < current_extreme_price * (1 - threshold):
                    current_direction = 'down'

                if current_direction:
                    pivot_indices.append(i)
                    pivot_prices.append(mid_price)
                    current_extreme_idx = i
                    current_extreme_price = mid_price
            elif current_direction == 'up':
                if mid_price > current_extreme_price:
                    current_extreme_idx = i
                    current_extreme_price = mid_price
                    pivot_indices[-1] = i
                    pivot_prices[-1] = mid_price
                elif mid_price < current_extreme_price * (1 - threshold):
                    current_direction = 'down'
                    pivot_indices.append(i)
                    pivot_prices.append(mid_price)
                    current_extreme_idx = i
                    current_extreme_price = mid_price
            else:
                if mid_price < current_extreme_price:
                    current_extreme_idx = i
                    current_extreme_price = mid_price
                    pivot_indices[-1] = i
                    pivot_prices[-1] = mid_price
                elif mid_price > current_extreme_price * (1 + threshold):
                    current_direction = 'up'
                    pivot_indices.append(i)
                    pivot_prices.append(mid_price)
                    current_extreme_idx = i
                    current_extreme_price = mid_price

        zigzag_points = []
        for idx, pivot_idx in enumerate(pivot_indices):
            if idx == 0:
                value = lows[pivot_idx] if len(pivot_indices) > 1 and pivot_prices[1] > pivot_prices[0] else highs[pivot_idx]
            elif idx == len(pivot_indices) - 1:
                value = highs[pivot_idx] if pivot_prices[idx] > pivot_prices[idx - 1] else lows[pivot_idx]
            else:
                if pivot_prices[idx] > pivot_prices[idx - 1] and pivot_prices[idx] > pivot_prices[idx + 1]:
                    value = highs[pivot_idx]
                else:
                    value = lows[pivot_idx]

            zigzag_points.append({
                'time': dates[pivot_idx],
                'value': float(value)
            })

        return {'ZigZag': zigzag_points} if zigzag_points else {}

    def _calc_kdj_custom(self, df: pd.DataFrame, params: dict) -> dict:
        """KDJ 自定义版 (带 J 线)"""
        k_length = params.get('k_length', 9)
        d_length = params.get('d_length', 3)
        j_length = params.get('j_length', 3)

        cols = self._map_columns(df)
        if not all([cols['close'], cols['high'], cols['low'], cols['date']]):
            return {}

        dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
        low_min = df[cols['low']].rolling(window=k_length, min_periods=1).min()
        high_max = df[cols['high']].rolling(window=k_length, min_periods=1).max()
        rsv = (df[cols['close']] - low_min) / (high_max - low_min).replace(0, float('nan')) * 100

        k_line = rsv.ewm(span=d_length, adjust=False).mean()
        d_line = k_line.ewm(span=d_length, adjust=False).mean()
        j_line = 3 * k_line - 2 * d_line

        def build_series(series):
            return [
                {'time': dates[i], 'value': float(series.iloc[i])}
                for i in range(len(df)) if not pd.isna(series.iloc[i])
            ]

        return {
            'K': build_series(k_line),
            'D': build_series(d_line),
            'J': build_series(j_line),
        }

    def _calc_volume_profile(self, df: pd.DataFrame, params: dict) -> dict:
        """成交量剖面 (Volume Profile POC)"""
        num_bins = params.get('num_bins', 20)
        cols = self._map_columns(df)
        if not all([cols['close'], cols['volume'], cols['date']]):
            return {}

        dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
        closes = df[cols['close']].values
        volumes = df[cols['volume']].values

        price_min, price_max = np.nanmin(closes), np.nanmax(closes)
        if price_min == price_max:
            return {}
        bin_edges = np.linspace(price_min, price_max, num_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        profile = np.zeros(num_bins)
        for i in range(len(closes)):
            if pd.isna(closes[i]) or pd.isna(volumes[i]):
                continue
            bin_idx = np.digitize(closes[i], bin_edges) - 1
            if 0 <= bin_idx < num_bins:
                profile[bin_idx] += volumes[i]

        poc_idx = np.argmax(profile) if np.max(profile) > 0 else num_bins // 2

        # 返回 POC 价格和成交量分布
        data = [
            {'time': dates[-1], 'value': float(bin_centers[i])}
            for i in range(num_bins) if profile[i] > 0
        ]
        poc_line = [{'time': dates[0], 'value': float(bin_centers[poc_idx])},
                     {'time': dates[-1], 'value': float(bin_centers[poc_idx])}]

        return {'VolumeProfile': data, 'POC': poc_line}

    def _calc_pivot_points(self, df: pd.DataFrame, params: dict) -> dict:
        """枢轴点 (Pivot Points)"""
        pivot_type = params.get('type', 'floor')
        cols = self._map_columns(df)
        if not all([cols['date'], cols['high'], cols['low'], cols['close']]):
            return {}

        dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
        high = df[cols['high']].values[-1] if len(df) > 0 else 0
        low = df[cols['low']].values[-1] if len(df) > 0 else 0
        close = df[cols['close']].values[-1] if len(df) > 0 else 0

        if pivot_type == 'floor':
            pp = (high + low + close) / 3
            r1 = 2 * pp - low
            r2 = pp + (high - low)
            r3 = r2 + (high - low)
            s1 = 2 * pp - high
            s2 = pp - (high - low)
            s3 = s2 - (high - low)
        elif pivot_type == 'camarilla':
            r1 = close + (high - low) * 1.1 / 12
            r2 = close + (high - low) * 1.1 / 6
            r3 = close + (high - low) * 1.1 / 4
            s1 = close - (high - low) * 1.1 / 12
            s2 = close - (high - low) * 1.1 / 6
            s3 = close - (high - low) * 1.1 / 4
            pp = (high + low + close) / 3
        else:  # woodie
            pp = (high + low + 2 * close) / 4
            r1 = 2 * pp - low
            r2 = pp + (high - low)
            s1 = 2 * pp - high
            s2 = pp - (high - low)
            r3 = r2 + (high - low) if 'r3' not in locals() else r2
            s3 = s2 - (high - low) if 's3' not in locals() else s2

        points = [('Pivot', pp), ('R1', r1), ('R2', r2), ('R3', r3),
                  ('S1', s1), ('S2', s2), ('S3', s3)]

        result = {}
        for name, val in points:
            result[name] = [
                {'time': dates[0], 'value': round(float(val), 2)},
                {'time': dates[-1], 'value': round(float(val), 2)},
            ]

        return result
