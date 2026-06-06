# optimization/data_manager.py
"""数据管理模块 — 优先 qlib 本地数据 → yfinance → MarketDataClient"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import numpy as np
from loguru import logger


class DataManager:
    """统一数据管理：获取、清洗、切分、市场状态识别

    数据源降级链：
      1. Qlib 本地数据（D.features）      ← 最快，仅当 Qlib 已初始化时可用
      2. yfinance 批量下载                ← 有网
      3. 逐个 MarketDataClient            ← 最终保底

    重要：DataManager 不会主动初始化 Qlib（避免与策略内部的
    qlib_safeinit 冲突导致 segfault）。只检测 Qlib 是否已被外部初始化。
    """

    def __init__(self, universe: Optional[list[str]] = None):
        self.universe = universe

    # ── Qlib 可用性检测（只检查，不初始化）──────────────

    @staticmethod
    def _is_qlib_ready() -> bool:
        """检查 Qlib 是否已由外部初始化（不主动 init，避免双重初始化 segfault）"""
        try:
            from core.app_state import get_state
            if get_state().qlib_initialized:
                return True
        except Exception:
            pass
        return False

    # ── 数据获取主入口 ──────────────────────────────────

    def fetch_prices(
        self,
        tickers: list[str],
        start: str,
        end: str,
        field: str = "close",
    ) -> pd.DataFrame:
        """逐个获取价格数据（保底），返回 (date x ticker) DataFrame"""
        from data.market_data_client import get_ohlcv
        all_data = {}
        for ticker in tickers:
            df = get_ohlcv(ticker, start, end)
            if df is not None and not df.empty and field in df.columns:
                all_data[ticker] = df[field]
        if not all_data:
            return pd.DataFrame()
        prices = pd.DataFrame(all_data)
        prices.index = pd.to_datetime(prices.index)
        return prices.sort_index()

    def fetch_prices_batch(
        self,
        tickers: list[str],
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        批量获取收盘价，返回 (date x ticker) DataFrame。

        降级链：Qlib 本地 → yfinance 批量 → MarketDataClient 逐个
        """
        # ── 1. 优先 Qlib 本地数据（仅当已初始化）───────
        if self._is_qlib_ready():
            df = self._fetch_via_qlib(tickers, start, end)
            if df is not None and not df.empty:
                logger.info(
                    f"[DataManager] Qlib 本地: {len(df.columns)} 支 × {len(df)} 天"
                )
                return df
            logger.debug("[DataManager] Qlib 本地无数据，尝试 yfinance...")

        # ── 2. yfinance 批量下载（分块处理大数据集）───
        # yfinance 单次最多处理 ~500 ticker，超过则分块
        CHUNK_SIZE = 300
        if len(tickers) > CHUNK_SIZE:
            dfs = []
            for i in range(0, len(tickers), CHUNK_SIZE):
                chunk = tickers[i:i + CHUNK_SIZE]
                chunk_df = self._fetch_via_yfinance(chunk, start, end)
                if chunk_df is not None and not chunk_df.empty:
                    dfs.append(chunk_df)
            if dfs:
                result = pd.concat(dfs, axis=1)
                logger.info(
                    f"[DataManager] yfinance 分块: {len(result.columns)} 支 × {len(result)} 天"
                )
                return result
            df = None
        else:
            df = self._fetch_via_yfinance(tickers, start, end)
        if df is not None and not df.empty:
            logger.info(
                f"[DataManager] yfinance: {len(df.columns)} 支 × {len(df)} 天"
            )
            return df

        # ── 3. 逐个 MarketDataClient 保底（限制数量）─
        MAX_INDIVIDUAL = 200
        fetch_list = tickers[:MAX_INDIVIDUAL] if len(tickers) > MAX_INDIVIDUAL else tickers
        if len(tickers) > MAX_INDIVIDUAL:
            logger.warning(
                f"[DataManager] 股票数 {len(tickers)} 超过 {MAX_INDIVIDUAL}，"
                f"只获取前 {MAX_INDIVIDUAL} 支"
            )
        return self.fetch_prices(fetch_list, start, end, "close")

    # ── Qlib 本地数据获取 ──────────────────────────────

    @staticmethod
    def _fetch_via_qlib(
        tickers: list[str],
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """通过 Qlib D.features 批量获取收盘价（仅当 Qlib 已初始化时调用）"""
        try:
            from qlib.data import D
        except ImportError:
            return None

        qlib_tickers = [t.lower().strip() for t in tickers]

        try:
            raw = D.features(qlib_tickers, ["$close"], start_time=start, end_time=end)
        except Exception as e:
            logger.debug(f"[DataManager] Qlib D.features 失败：{e}")
            return None

        if raw is None or raw.empty:
            return None

        if isinstance(raw.index, pd.MultiIndex):
            df = raw.reset_index()
            dt_col = next(
                (c for c in df.columns if str(c).lower() in ("datetime", "date")),
                df.columns[0],
            )
            inst_col = next(
                (c for c in df.columns if str(c).lower() == "instrument"),
                df.columns[1] if len(df.columns) > 1 else None,
            )
            if inst_col is None:
                return None

            pivoted = df.pivot_table(
                index=dt_col, columns=inst_col, values="$close", aggfunc="last"
            )
            pivoted.index = pd.to_datetime(pivoted.index)
            pivoted = pivoted.sort_index()
            pivoted.columns = [str(c).upper() for c in pivoted.columns]
            return pivoted.dropna(axis=1, how="all")

        # 单标的
        raw.index = pd.to_datetime(raw.index)
        col_name = tickers[0].upper() if tickers else "CLOSE"
        return pd.DataFrame({col_name: raw["$close"]}).sort_index()

    # ── yfinance 批量下载 ──────────────────────────────

    @staticmethod
    def _fetch_via_yfinance(
        tickers: list[str],
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """yfinance 批量下载收盘价"""
        try:
            import yfinance as yf
            from core.app_state import get_state
            from core.qlibhelper import normalize_cn_tickers

            reg = get_state().reg
            yf_tickers = list(tickers)
            if reg == "cn":
                yf_tickers = normalize_cn_tickers(tickers)

            df_all = yf.download(
                yf_tickers, start=start, end=end,
                progress=False, auto_adjust=False, threads=True,
            )
            if df_all is None or df_all.empty:
                return None

            if isinstance(df_all.columns, pd.MultiIndex):
                if "Close" in df_all.columns.get_level_values(0):
                    close_df = df_all["Close"].copy()
                else:
                    level0 = df_all.columns.get_level_values(0)[0]
                    close_df = df_all[level0].copy()
            else:
                close_col = next(
                    (c for c in df_all.columns
                     if str(c).lower() in ("close", "adj close")),
                    df_all.columns[0],
                )
                close_df = df_all[[close_col]].copy()
                if len(tickers) == 1:
                    close_df.columns = [tickers[0]]

            close_df = close_df.dropna(how="all")
            close_df.index = pd.to_datetime(close_df.index)
            return close_df

        except Exception as e:
            logger.debug(f"[DataManager] yfinance 不可用：{e}")
            return None

    # ── 数据切分 ────────────────────────────────────────

    def split_data(
        self,
        data: pd.DataFrame,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
    ) -> dict[str, pd.DataFrame]:
        """按时间序列切分为 train/val/test"""
        n = len(data)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))
        return {
            "train": data.iloc[:train_end],
            "val": data.iloc[train_end:val_end],
            "test": data.iloc[val_end:],
        }

    # ── 市场状态识别（复用 HMM）─────────────────────────

    def get_market_regime(self, trade_date: Optional[date] = None) -> str:
        """获取市场状态，返回 recovery|expansion|overheating|recession"""
        try:
            from services.hmm_regime import run_regime_detection
            import json

            result_path = run_regime_detection(trade_date=trade_date)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            regime = payload.get("regime", "expansion")
            prob = payload.get("regime_probability", 0)
            logger.info(f"[DataManager] 市场状态: {regime} (prob={prob:.2%})")
            return regime
        except Exception as e:
            logger.warning(f"[DataManager] HMM 不可用，fallback expansion：{e}")
            return "expansion"

    # ── 数据质量检查 ────────────────────────────────────

    def validate_data(self, prices: pd.DataFrame) -> dict:
        """检查数据质量"""
        if prices.empty:
            return {"total_tickers": 0, "error": "empty"}
        return {
            "total_tickers": len(prices.columns),
            "total_days": len(prices),
            "missing_ratio": float(prices.isna().sum().sum() / prices.size),
            "min_data_points": int(prices.count().min()),
        }
