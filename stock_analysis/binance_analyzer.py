"""
加密货币基本面分析器
通过 Binance API 获取加密资产数据
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import logging
import requests
import time
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class CryptoFundamentalData:
    """加密资产基本面数据结构（与股票结构对应）"""
    # 资产概况
    name:           Optional[str]   = None
    sector:         Optional[str]   = None
    industry:       Optional[str]   = None
    market_cap:     Optional[float] = None
    employees:      Optional[float] = None
    description:    Optional[str]   = None
    website:        Optional[str]   = None
    exchange:       Optional[str]   = None

    # 估值指标
    pe_ratio:       Optional[float] = None
    pb_ratio:       Optional[float] = None
    ps_ratio:       Optional[float] = None
    ev_ebitda:      Optional[float] = None

    # 盈利能力
    roe:            Optional[float] = None
    roa:            Optional[float] = None
    gross_margin:   Optional[float] = None
    operating_margin:Optional[float]= None
    net_margin:     Optional[float] = None

    # 增长指标
    revenue_growth: Optional[float] = None
    eps_growth:     Optional[float] = None

    # 财务健康
    debt_to_equity: Optional[float] = None
    current_ratio:  Optional[float] = None

    # 分析师评级
    analyst_target: Optional[float] = None
    analyst_rating: Optional[str]   = None

    # EPS 历史（最近 4-8 季度）- 对应价格历史
    earnings_history: list[dict] = field(default_factory=list)
    
    # 加密资产特有字段
    # 基础信息
    symbol:         Optional[str]   = None
    base_asset:     Optional[str]   = None
    quote_asset:    Optional[str]   = None
    
    # 价格与市场
    current_price:  Optional[float] = None
    price_change_24h: Optional[float] = None
    price_change_percent_24h: Optional[float] = None
    high_24h:       Optional[float] = None
    low_24h:        Optional[float] = None
    volume_24h:     Optional[float] = None
    quote_volume_24h: Optional[float] = None
    
    # 链上指标
    circulating_supply: Optional[float] = None
    total_supply:     Optional[float] = None
    max_supply:       Optional[float] = None
    network_hashrate: Optional[float] = None
    active_addresses: Optional[int]   = None
    transaction_count_24h: Optional[int] = None
    
    # 交易指标
    vwap_24h:       Optional[float] = None
    weighted_avg_price: Optional[float] = None
    number_of_trades: Optional[int] = None
    taker_buy_ratio: Optional[float] = None
    bid_ask_spread: Optional[float] = None
    order_book_depth: Optional[float] = None
    
    # 历史数据
    price_history_7d: list[dict] = field(default_factory=list)
    price_history_30d: list[dict] = field(default_factory=list)
    
    def analyst_signal(self) -> Optional[str]:
        """根据分析师目标价与当前价的偏差推断信号"""
        return self.analyst_rating


class BinanceAnalyzer:
    """Binance 加密资产数据获取与分析"""
    
    def __init__(self, proxy: Optional[Dict] = None):
        self.base_url = "https://api.binance.com/api/v3"
        self.session = requests.Session()
        if proxy:
            self.session.proxies.update(proxy)
        
        # 映射传统财务指标到加密指标
        self.metric_mapping = {
            'pe_ratio': 'nvt_ratio',        # 网络价值与交易比率
            'pb_ratio': 'market_cap_supply_ratio',  # 市值供应比
            'roe': 'network_growth',        # 网络增长率
            'net_margin': 'fee_to_reward_ratio',  # 手续费与奖励比
            'revenue_growth': 'price_growth_30d',  # 价格增长
            'debt_to_equity': 'volatility_ratio',  # 波动率比率
        }

    def analyze(self, ticker: str, current_price: Optional[float] = None, quote_asset: str = "USDT") -> CryptoFundamentalData:
        """
        获取加密资产的完整基本面数据
        结构设计为与股票 analyze 方法完全一致
        """
        ticker = ticker.upper().strip()
        full_symbol = ticker if ticker.index(quote_asset) > 0 else f"{ticker}{quote_asset}"
        data = CryptoFundamentalData()
        
        try:
            # 1. 获取基础资产信息
            data = self._get_asset_profile(full_symbol, data)
            
            # 2. 获取24小时行情统计
            data = self._get_market_metrics(full_symbol, data)
            
            # 3. 获取订单簿和流动性信息
            data = self._get_liquidity_metrics(full_symbol, data)
            
            # 4. 获取历史K线数据
            data.price_history_7d = self._get_historical_klines(full_symbol, "1h", limit=168)
            data.price_history_30d = self._get_historical_klines(full_symbol, "1d", limit=30)
            
            # 5. 模拟"EPS历史"（价格历史）
            data.earnings_history = self._simulate_earnings_history(data.price_history_30d)
            
            # 6. 计算衍生加密指标
            data = self._calculate_crypto_metrics(data)
            
            # 7. 填充传统财务指标（用加密指标映射）
            data = self._map_to_traditional_metrics(data)
            
            # 8. 尝试从外部API获取链上数据
            data = self._get_external_onchain_data(ticker, data)
            
            self._sanitize(data, ticker)
            logger.debug(f"加密资产分析完成：{full_symbol} — 价格=${data.current_price} 24h涨跌幅={data.price_change_percent_24h}%")
            
        except Exception as e:
            logger.error(f"Binance 数据分析失败 {full_symbol}: {e}")
            # 即使部分失败也返回已有数据
        
        return data

    # ── 核心数据获取方法 ──────────────────────────────────────

    def _get_asset_profile(self, symbol: str, data: CryptoFundamentalData) -> CryptoFundamentalData:
        """获取资产基础信息（对应股票的公司概况）"""
        try:
            # 从 Binance exchangeInfo 获取交易对信息
            response = self.session.get(f"{self.base_url}/exchangeInfo", params={"symbol": symbol})
            response.raise_for_status()
            exchange_info = response.json()
            
            if exchange_info.get("symbols"):
                symbol_info = exchange_info["symbols"][0]
                data.symbol = symbol
                data.base_asset = symbol_info.get("baseAsset", "")
                data.quote_asset = symbol_info.get("quoteAsset", "")
                data.name = f"{data.base_asset}/{data.quote_asset}"
                data.exchange = "Binance"
                
                # 设置默认描述
                asset_descriptions = {
                    "BTC": "比特币 - 首个去中心化数字货币，数字黄金",
                    "ETH": "以太坊 - 智能合约平台，DeFi和NFT的基础",
                    "BNB": "币安币 - 币安交易所生态代币",
                    "SOL": "Solana - 高性能区块链，高TPS智能合约平台",
                }
                data.description = asset_descriptions.get(data.base_asset, 
                    f"{data.base_asset} - 加密货币资产")
                    
                # 设置行业分类
                crypto_sectors = {
                    "BTC": "Store of Value",  # 价值存储
                    "ETH": "Smart Contract",  # 智能合约
                    "BNB": "Exchange Token",  # 交易所代币
                    "SOL": "Layer 1",         # 一层网络
                }
                data.industry = crypto_sectors.get(data.base_asset, "Cryptocurrency")
                data.sector = "Blockchain & Cryptocurrency"
                
        except Exception as e:
            logger.warning(f"获取资产信息失败 {symbol}: {e}")
        
        return data

    def _get_market_metrics(self, symbol: str, data: CryptoFundamentalData) -> CryptoFundamentalData:
        """获取市场指标（对应股票的财务指标）"""
        try:
            # 24小时行情统计
            response = self.session.get(f"{self.base_url}/ticker/24hr", params={"symbol": symbol})
            response.raise_for_status()
            ticker = response.json()
            
            data.current_price = float(ticker.get("lastPrice", 0))
            data.price_change_24h = float(ticker.get("priceChange", 0))
            data.price_change_percent_24h = float(ticker.get("priceChangePercent", 0))
            data.high_24h = float(ticker.get("highPrice", 0))
            data.low_24h = float(ticker.get("lowPrice", 0))
            data.volume_24h = float(ticker.get("volume", 0))
            data.quote_volume_24h = float(ticker.get("quoteVolume", 0))
            data.number_of_trades = ticker.get("count", 0)
            data.weighted_avg_price = float(ticker.get("weightedAvgPrice", 0))
            
            # 计算VWAP
            if data.volume_24h > 0:
                data.vwap_24h = data.quote_volume_24h / data.volume_24h
            else:
                data.vwap_24h = data.weighted_avg_price
                
        except Exception as e:
            logger.warning(f"获取市场指标失败 {symbol}: {e}")
        
        return data

    def _get_liquidity_metrics(self, symbol: str, data: CryptoFundamentalData) -> CryptoFundamentalData:
        """获取流动性指标（对应股票的财务健康指标）"""
        try:
            # 订单簿深度
            response = self.session.get(f"{self.base_url}/depth", params={"symbol": symbol, "limit": 10})
            response.raise_for_status()
            order_book = response.json()
            
            if order_book.get("bids") and order_book.get("asks"):
                # 计算买卖价差
                best_bid = float(order_book["bids"][0][0])
                best_ask = float(order_book["asks"][0][0])
                if best_ask > 0:
                    data.bid_ask_spread = (best_ask - best_bid) / best_ask * 100
                
                # 计算订单簿深度（前5档的累计量）
                bid_depth = sum(float(bid[1]) for bid in order_book["bids"][:5])
                ask_depth = sum(float(ask[1]) for ask in order_book["asks"][:5])
                data.order_book_depth = min(bid_depth, ask_depth) * data.current_price if data.current_price else 0
                
        except Exception as e:
            logger.warning(f"获取流动性指标失败 {symbol}: {e}")
        
        return data

    def _get_historical_klines(self, symbol: str, interval: str = "1d", limit: int = 30) -> List[Dict]:
        """获取历史K线数据"""
        klines = []
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            response = self.session.get(f"{self.base_url}/klines", params=params)
            response.raise_for_status()
            
            for kline in response.json():
                kline_dict = {
                    "timestamp": kline[0],
                    "date": datetime.fromtimestamp(kline[0]/1000).strftime('%Y-%m-%d'),
                    "open": float(kline[1]),
                    "high": float(kline[2]),
                    "low": float(kline[3]),
                    "close": float(kline[4]),
                    "volume": float(kline[5]),
                    "quote_volume": float(kline[7]),
                    "taker_buy_volume": float(kline[9]),
                }
                klines.append(kline_dict)
                
        except Exception as e:
            logger.warning(f"获取历史K线失败 {symbol} {interval}: {e}")
        
        return klines

    def _simulate_earnings_history(self, price_history: List[Dict]) -> List[Dict]:
        """模拟EPS历史（用价格变化替代）"""
        earnings = []
        try:
            for i, kline in enumerate(price_history[-8:]):  # 最近8个周期
                if i > 0:
                    prev_close = price_history[i-1]["close"]
                    current_close = kline["close"]
                    eps_change = (current_close - prev_close) / prev_close if prev_close > 0 else 0
                    
                    earnings.append({
                        "date": kline.get("date", ""),
                        "eps": current_close,
                        "eps_estimated": prev_close * 1.02,  # 简单估计
                        "eps_surprise": eps_change * 100,  # 惊喜百分比
                        "period": f"Q{i+1}"
                    })
        except Exception as e:
            logger.warning(f"模拟EPS历史失败: {e}")
        
        return earnings

    def _calculate_crypto_metrics(self, data: CryptoFundamentalData) -> CryptoFundamentalData:
        """计算加密资产特有指标"""
        try:
            # 1. 计算主动买入比例
            if hasattr(data, 'price_history_7d') and data.price_history_7d:
                total_volume = sum(k.get("volume", 0) for k in data.price_history_7d)
                taker_buy_volume = sum(k.get("taker_buy_volume", 0) for k in data.price_history_7d)
                if total_volume > 0:
                    data.taker_buy_ratio = taker_buy_volume / total_volume * 100
            
            # 2. 计算7日和30日价格变化（增长指标）
            if hasattr(data, 'price_history_7d') and len(data.price_history_7d) >= 2:
                oldest = data.price_history_7d[0]["close"]
                newest = data.price_history_7d[-1]["close"]
                if oldest > 0:
                    data.revenue_growth = (newest - oldest) / oldest
            
            # 3. 计算波动率（风险指标）
            if hasattr(data, 'price_history_30d') and len(data.price_history_30d) >= 5:
                closes = [k["close"] for k in data.price_history_30d if k["close"] > 0]
                if len(closes) >= 5:
                    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
                    if returns:
                        volatility = np.std(returns) * np.sqrt(365)  # 年化波动率
                        data.debt_to_equity = volatility  # 用波动率映射负债率
            
            # 4. 计算网络价值与交易比率（NVT Ratio）- 对应PE
            if data.market_cap and data.quote_volume_24h:
                # NVT = 市值 / 链上交易额，这里用交易量近似
                nvt_ratio = data.market_cap / (data.quote_volume_24h * 365)  # 年化
                data.pe_ratio = nvt_ratio
            
            # 5. 计算ROE（网络增长率）- 用价格增长和网络活动
            if data.price_history_30d and len(data.price_history_30d) >= 30:
                price_growth_30d = (data.price_history_30d[-1]["close"] - 
                                   data.price_history_30d[0]["close"]) / data.price_history_30d[0]["close"]
                # 结合交易活跃度
                volume_growth = data.volume_24h / (sum(k["volume"] for k in data.price_history_30d) / 30) if data.price_history_30d else 1
                data.roe = price_growth_30d * 0.7 + (volume_growth - 1) * 0.3
            
            # 6. 计算净利率（费用与奖励比）- 用交易费估算
            if data.vwap_24h and data.current_price:
                # 简单估算：价差与费用的比率
                if data.bid_ask_spread:
                    data.net_margin = 1 - (data.bid_ask_spread / 100)  # 价差越小，利润率越高
            
        except Exception as e:
            logger.warning(f"计算加密指标失败: {e}")
        
        return data

    def _map_to_traditional_metrics(self, data: CryptoFundamentalData) -> CryptoFundamentalData:
        """将加密指标映射到传统财务指标结构"""
        # 已经在前面的方法中直接设置了映射的指标
        # 这里确保所有必需字段都有值
        if data.pe_ratio is None and data.current_price and data.quote_volume_24h:
            # 简单PE估计：价格/交易量比率
            data.pe_ratio = data.current_price / (data.quote_volume_24h / 1e6) if data.quote_volume_24h > 0 else None
        
        if data.pb_ratio is None and data.market_cap and data.circulating_supply:
            # PB估计：市值/流通量比率
            data.pb_ratio = data.market_cap / (data.circulating_supply * data.current_price) if data.circulating_supply and data.current_price else None
        
        return data

    def _get_external_onchain_data(self, ticker: str, data: CryptoFundamentalData) -> CryptoFundamentalData:
        """从外部API获取链上数据（需要实现）"""
        # 这里可以集成Glassnode, CoinMetrics, CoinGecko等
        # 示例：从CoinGecko获取市值和供应量
        try:
            # 如果需要实现，可以在这里调用外部API
            # response = requests.get(f"https://api.coingecko.com/api/v3/coins/{ticker.lower()}")
            # 解析响应并设置 data.market_cap, data.circulating_supply 等
            pass
        except Exception as e:
            logger.debug(f"外部链上数据获取失败 {ticker}: {e}")
        
        return data

    # ── 数据清洗 ──────────────────────────────────────────────

    @staticmethod
    def _sanitize(data: CryptoFundamentalData, ticker: str) -> None:
        """
        修正/过滤基本面指标的合理性
        """
        # 价格相关检查
        if data.current_price and data.current_price < 0:
            logger.warning(f"[Crypto] {ticker} 当前价为负: {data.current_price}，已重置")
            data.current_price = None
        
        # 增长率范围检查
        for attr in ("revenue_growth", "eps_growth"):
            val = getattr(data, attr, None)
            if val is not None and abs(val) > 10.0:  # 超过1000%
                logger.warning(f"[Crypto] {ticker}.{attr}={val*100:.0f}% 超出合理范围，已丢弃")
                setattr(data, attr, None)
        
        # 比率范围检查
        for attr, lo, hi in [
            ("pe_ratio", -1000, 1000),
            ("pb_ratio", 0, 100),
            ("roe", -5, 5),  # -500% 到 500%
            ("net_margin", -2, 2),  # -200% 到 200%
        ]:
            val = getattr(data, attr, None)
            if val is not None and not (lo <= val <= hi):
                logger.warning(f"[Crypto] {ticker}.{attr}={val:.2f} 超出合理范围，已丢弃")
                setattr(data, attr, None)
        
        # 确保必要的基础字段
        if not data.name and data.base_asset and data.quote_asset:
            data.name = f"{data.base_asset}/{data.quote_asset}"
        elif not data.name:
            data.name = ticker

    def get_valuation_signals(self, data: CryptoFundamentalData) -> list[dict]:
        """
        将加密资产数据转化为买卖信号列表
        返回 [{label, value_str, signal_text, signal_type}]
        """
        signals = []
        
        # 价格动量信号
        if data.price_change_percent_24h is not None:
            change = data.price_change_percent_24h
            if change > 5:
                sig, stype = "强势上涨", "bullish"
            elif change > 2:
                sig, stype = "上涨", "bullish"
            elif change < -5:
                sig, stype = "大幅下跌", "bearish"
            elif change < -2:
                sig, stype = "下跌", "bearish"
            else:
                sig, stype = "盘整", "neutral"
            signals.append({"label": "24h涨跌幅", "value_str": f"{change:+.1f}%",
                           "signal_text": sig, "signal_type": stype})
        
        # 成交量信号
        if data.quote_volume_24h and data.current_price:
            # 简单估算交易活跃度
            avg_price = data.vwap_24h or data.current_price
            volume_ratio = data.quote_volume_24h / (avg_price * 1e6)  # 百万美元标准化
            if volume_ratio > 10:
                sig, stype = "高度活跃", "bullish"
            elif volume_ratio > 3:
                sig, stype = "活跃", "neutral"
            else:
                sig, stype = "清淡", "bearish"
            signals.append({"label": "交易活跃度", "value_str": f"${data.quote_volume_24h/1e6:.1f}M",
                           "signal_text": sig, "signal_type": stype})
        
        # 主动买入比例信号
        if data.taker_buy_ratio is not None:
            ratio = data.taker_buy_ratio
            if ratio > 60:
                sig, stype = "买盘强劲", "bullish"
            elif ratio > 40:
                sig, stype = "买卖均衡", "neutral"
            else:
                sig, stype = "卖压较大", "bearish"
            signals.append({"label": "主动买入占比", "value_str": f"{ratio:.1f}%",
                           "signal_text": sig, "signal_type": stype})
        
        # 流动性信号（价差）
        if data.bid_ask_spread is not None:
            spread = data.bid_ask_spread
            if spread < 0.1:
                sig, stype = "高流动性", "bullish"
            elif spread < 0.5:
                sig, stype = "良好流动性", "neutral"
            else:
                sig, stype = "低流动性", "bearish"
            signals.append({"label": "买卖价差", "value_str": f"{spread:.3f}%",
                           "signal_text": sig, "signal_type": stype})
        
        # 波动率信号
        if data.debt_to_equity is not None:  # 这里存储的是波动率
            vol = data.debt_to_equity * 100  # 转换为百分比
            if vol < 30:
                sig, stype = "低波动", "neutral"
            elif vol < 80:
                sig, stype = "正常波动", "neutral"
            else:
                sig, stype = "高波动", "bearish"
            signals.append({"label": "年化波动率", "value_str": f"{vol:.1f}%",
                           "signal_text": sig, "signal_type": stype})
        
        return signals


# 使用示例
if __name__ == "__main__":
    analyzer = BinanceAnalyzer()
    
    # 分析BTC
    btc_data = analyzer.analyze("BTC", quote_asset="USDT")
    print(f"资产: {btc_data.name}")
    print(f"当前价格: ${btc_data.current_price}")
    print(f"24h变化: {btc_data.price_change_percent_24h}%")
    print(f"24h交易量: ${btc_data.quote_volume_24h:,.0f}")
    
    # 获取交易信号
    signals = analyzer.get_valuation_signals(btc_data)
    for signal in signals:
        print(f"{signal['label']}: {signal['value_str']} - {signal['signal_text']} ({signal['signal_type']})")