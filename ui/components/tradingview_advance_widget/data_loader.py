"""
DataLoader - 行情数据加载器，支持可插拔数据源。

核心概念：
- DataLoader 通过 DataSource 接口获取数据，不绑定具体数据源
- 内置 YFinanceSource（默认），可选 QLibSource 等
- 数据源返回标准化 OHLCV DataFrame: date, open, high, low, close, volume
- 支持日线/周线/月线，由调用方决定缓存策略

快速开始:
    loader = DataLoader()
    df = loader.download('AAPL')  # 使用默认 yfinance
    loader.push_to_widget(widget, df)

QLib 集成:
    loader = DataLoader(source=QLibSource(qlib_dir='/path/to/qlib_data'))
    df = loader.download('AAPL')  # 使用 qlib
"""
from datetime import datetime, timedelta
from typing import Optional, Protocol, List

import pandas as pd


# ==================== 数据源接口 ====================

class DataSource(Protocol):
    """数据源协议。实现此接口可接入任意数据源。"""

    def fetch(self, symbol: str, period: str = '2y',
              interval: str = '1d') -> pd.DataFrame:
        """获取行情数据

        Args:
            symbol: 标的代码 (如 'AAPL', '000300.SH')
            period: 时间范围 ('1mo', '1y', '2y', '5y', 'max')
            interval: K线周期 ('1d', '1wk', '1mo')

        Returns:
            标准化 OHLCV DataFrame (列: date, open, high, low, close, volume)
        """
        ...

    def name(self) -> str:
        """数据源名称"""
        ...


# ==================== 内置数据源: yfinance ====================

class YFinanceSource:
    """yfinance 数据源"""

    def name(self) -> str:
        return 'yfinance'

    def fetch(self, symbol: str, period: str = '2y',
              interval: str = '1d') -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("请安装 yfinance: pip install yfinance")

        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            raise ValueError(f"未获取到 {symbol} 的数据 "
                             f"(period={period}, interval={interval})")

        df.reset_index(inplace=True)
        return self._normalize(df)

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        rename = {
            'Date': 'date', 'Datetime': 'date',
            'Open': 'open', 'High': 'high', 'Low': 'low',
            'Close': 'close', 'Volume': 'volume',
            'Adj Close': 'close',
        }
        rename = {k: v for k, v in rename.items() if k in df.columns}
        df = df.rename(columns=rename)
        keep = [c for c in ['date', 'open', 'high', 'low', 'close', 'volume']
                if c in df.columns]
        return df[keep]


# ==================== QLib 集成示例 ====================

class QLibSource:
    """QLib 数据源 — 从 qlib 的 bin 文件读取 OHLCV 数据

    安装: pip install qlib

    使用前需准备 qlib 数据目录（支持在线下载或本地预处理）:
        python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn

    示例:
        source = QLibSource(
            qlib_dir='~/.qlib/qlib_data/cn_data',
            market='csi300',
        )
        loader = DataLoader(source=source)
        df = loader.download('000300.SH')
        loader.push_to_widget(widget, df)
    """

    def __init__(self, qlib_dir: str = None, market: str = 'csi300',
                 freq: str = 'day'):
        self._qlib_dir = qlib_dir
        self._market = market
        self._freq = freq

    def name(self) -> str:
        return f'qlib({self._market})'

    def fetch(self, symbol: str, period: str = '2y',
              interval: str = '1d') -> pd.DataFrame:
        try:
            from qlib.data import D
            from qlib.config import REG_CN
            from qlib.constant import REG_CN as REGION
        except ImportError:
            raise ImportError("请安装 qlib: pip install qlib")

        if self._qlib_dir:
            from qlib.config import QlibConfig
            from qlib.data import init as qlib_init
            provider_uri = self._qlib_dir
            qlib_init(provider_uri=provider_uri, region=REGION)

        # 解析时间范围
        end = pd.Timestamp.now()
        start = self._parse_period(period, end)

        # 拼接 qlib 格式的标的代码
        qlib_symbol = self._to_qlib_symbol(symbol)

        # 获取日线数据
        df = D.features(
            [qlib_symbol],
            fields=['$open', '$high', '$low', '$close', '$volume'],
            start_time=start,
            end_time=end,
            freq=self._freq,
        )

        if df.empty:
            raise ValueError(f"QLib 未获取到 {symbol} 的数据")

        # 标准化列名
        df = df.reset_index()
        df = df.rename(columns={
            'datetime': 'date',
            '$open': 'open', '$high': 'high',
            '$low': 'low', '$close': 'close',
            '$volume': 'volume',
        })
        if 'symbol' in df.columns:
            df = df.drop(columns=['symbol'])
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

        # 如有周线/月线需求，调用方自行 resample
        return df[['date', 'open', 'high', 'low', 'close', 'volume']]

    def get_daily(self, symbol: str) -> pd.DataFrame:
        """获取日线数据"""
        return self.fetch(symbol, interval='1d')

    def get_weekly(self, symbol: str) -> pd.DataFrame:
        """获取周线数据（QLib 原生周频）"""
        return self.fetch(symbol, interval='1wk')

    def get_monthly(self, symbol: str) -> pd.DataFrame:
        """获取月线数据（QLib 原生月频）"""
        return self.fetch(symbol, interval='1mo')

    @staticmethod
    def _to_qlib_symbol(symbol: str) -> str:
        """将通用标的代码转为 qlib 格式"""
        # 示例: '000300.SH' → 'SH000300'
        #       'AAPL' → 'AAPL' (美股 qlib 直接用)
        if symbol.endswith('.SH'):
            return 'SH' + symbol.replace('.SH', '')
        if symbol.endswith('.SZ'):
            return 'SZ' + symbol.replace('.SZ', '')
        return symbol

    @staticmethod
    def _parse_period(period: str, end: pd.Timestamp) -> pd.Timestamp:
        mapping = {
            '1mo': 30, '3mo': 90, '6mo': 180,
            '1y': 365, '2y': 730, '5y': 1825, '10y': 3650, 'max': 7300,
        }
        days = mapping.get(period, 730)
        return end - pd.Timestamp(days=days)


# ==================== DataLoader ====================

class DataLoader:
    """数据加载器。支持可插拔数据源。"""

    PRESETS = [
        {'symbol': '0700.HK', 'name': 'Tencent', 'type': 'stock'},
        {'symbol': 'SPX', 'name': 'SPX', 'type': 'stock'},
        {'symbol': 'AAPL', 'name': 'Apple', 'type': 'stock'},
        {'symbol': 'GOOGL', 'name': 'Alphabet', 'type': 'stock'},
        {'symbol': 'MSFT', 'name': 'Microsoft', 'type': 'stock'},
        {'symbol': 'AMZN', 'name': 'Amazon', 'type': 'stock'},
        {'symbol': 'TSLA', 'name': 'Tesla', 'type': 'stock'},
        {'symbol': 'NVDA', 'name': 'NVIDIA', 'type': 'stock'},
        {'symbol': 'META', 'name': 'Meta', 'type': 'stock'},
        {'symbol': 'SPY', 'name': 'SPDR S&P 500 ETF', 'type': 'etf'},
        {'symbol': 'QQQ', 'name': 'Invesco QQQ Trust', 'type': 'etf'},
        {'symbol': 'BTC-USD', 'name': 'Bitcoin USD', 'type': 'crypto'},
        {'symbol': 'ETH-USD', 'name': 'Ethereum USD', 'type': 'crypto'},
        {'symbol': 'SOL-USD', 'name': 'Solana USD', 'type': 'crypto'},
        {'symbol': '^GSPC', 'name': 'S&P 500 Index', 'type': 'index'},
        {'symbol': '^IXIC', 'name': 'NASDAQ Composite', 'type': 'index'},
        {'symbol': '^DJI', 'name': 'Dow Jones Industrial', 'type': 'index'},
        {'symbol': 'EURUSD=X', 'name': 'EUR/USD', 'type': 'forex'},
        {'symbol': 'GBPUSD=X', 'name': 'GBP/USD', 'type': 'forex'},
        {'symbol': 'GC=F', 'name': 'Gold Futures', 'type': 'commodity'},
        {'symbol': 'CL=F', 'name': 'Crude Oil', 'type': 'commodity'},
    ]

    def __init__(self, source=None):
        self._source = source or YFinanceSource()
        self._last_df: Optional[pd.DataFrame] = None
        self._last_symbol: Optional[str] = None

    def download(self, symbol: str, period: str = '2y',
                 interval: str = '1d') -> pd.DataFrame:
        """下载行情数据。委托给当前数据源的 fetch 方法。

        Args:
            symbol: 标的代码
            period: 时间范围 ('1mo', '1y', '2y', '5y', 'max')
            interval: K线周期 ('1d', '1wk', '1mo')

        Returns:
            标准化 OHLCV DataFrame
        """
        df = self._source.fetch(symbol, period=period, interval=interval)
        if df.empty:
            raise ValueError(f"未获取到 {symbol} 的数据")
        self._last_df = df.copy()
        self._last_symbol = symbol
        print(f"✅ [{self._source.name()}] {symbol} | "
              f"{len(df)} 根K线 | {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
        return df

    def push_to_widget(self, widget, df: Optional[pd.DataFrame] = None):
        if df is None:
            df = self._last_df
        if df is None:
            raise ValueError("无数据可推送，请先调用 download()")
        required = ['date', 'open', 'high', 'low', 'close']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"数据缺少必要列: {missing}")
        widget.update_chart_data(df)
        print(f"📊 已推送 {len(df)} 根K线 ({self._last_symbol})")

    def get_last_data(self) -> Optional[pd.DataFrame]:
        return self._last_df.copy() if self._last_df is not None else None

    def get_last_symbol(self) -> Optional[str]:
        return self._last_symbol


def test_download():
    loader = DataLoader()
    print(f"数据源: {loader._source.name()}")
    df = loader.download('AAPL', period='1mo')
    assert len(df) > 0
    assert 'date' in df.columns
    assert 'close' in df.columns
    print(f"  列: {list(df.columns)}")
    print(f"  样本:\n{df.head(3)}")
    print("✅ 数据下载测试通过")


if __name__ == '__main__':
    test_download()
