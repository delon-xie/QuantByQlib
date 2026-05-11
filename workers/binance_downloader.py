#!/usr/bin/env python3
"""
Binance Spot 历史K线数据管理脚本
1. 下载
2. 检查 & 修复缺失
3. 下载 + 修复

时间范围：2017-01 ~ 2026-04
支持多个交易对 & 多周期

Usage:
# safe
python binance_downloader.py --mode repair

# safe check and repair all symbols's 1d Dataframe files
python binance_downloader.py  --intervals 1d --mode repair

python binance_downloader.py

python binance_downloader.py \
  --mode download \
  --symbols BTCUSDT ETHUSDT \
  --intervals 1d 4h

python binance_downloader.py \
  --mode repair \
  --symbols SOLUSDT \
  --intervals 1m

python binance_downloader.py \
  --mode both \
  --symbols BTCUSDT
"""
import os
import requests
import time
from tqdm import tqdm
from urllib.parse import urljoin
from datetime import datetime
import argparse

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT",
    "TRXUSDT", "DOGEUSDT", "ADAUSDT", "WBTCUSDT", "ZECUSDT",
    "BCHUSDT", "WBETHUSDT", "XLMUSDT", "LINKUSDT", "TONUSDT",
    "HBARUSDT", "LTCUSDT", "AVAXUSDT", "SUIUSDT", "SHIBUSDT",
    "TAOUSDT", "UNIUSDT", "XAUTUSDT", "PAXGUSDT", "DOTUSDT",
    "WLFIUSDT", "NEARUSDT", "SKYUSDT", "ASTERUSDT", "PEPEUSDT",
    "ONDOUSDT", "ICPUSDT", "TRUMPUSDT", "AAVEUSDT", "ETCUSDT",
    "FILUSDT",
]

DEFAULT_SYMBOLS_START = {
    # 老币（Binance 上线早）
    "BTCUSDT": ("2017", "08"),
    "ETHUSDT": ("2017", "08"),
    "LTCUSDT": ("2017", "12"),
    "BNBUSDT": ("2017", "11"),

    # 主流
    "XRPUSDT": ("2018", "05"),
    "ADAUSDT": ("2018", "04"),
    "TRXUSDT": ("2018", "06"),
    "DOGEUSDT": ("2019", "07"),

    # DeFi / Layer1
    "SOLUSDT": ("2020", "08"),
    "AVAXUSDT": ("2020", "09"),
    "DOTUSDT": ("2020", "08"),
    "LINKUSDT": ("2019", "01"),

    # 稳定 / 资产类
    "WBTCUSDT": ("2023", "04"),
    "WBETHUSDT": ("2023", "07"),
    "XAUTUSDT": ("2026", "03"),
    "PAXGUSDT": ("2020", "08"),

    # 其它
    "ZECUSDT": ("2019", "03"),
    "BCHUSDT": ("2019", "11"),
    "XLMUSDT": ("2018", "05"),
    "TONUSDT": ("2024", "08"),
    "HBARUSDT": ("2019", "09"),
    "SUIUSDT": ("2023", "05"),
    "SHIBUSDT": ("2021", "05"),
    "TAOUSDT": ("2024", "04"),
    "UNIUSDT": ("2020", "09"),
    "NEARUSDT": ("2020", "10"),
    "SKYUSDT": ("2025", "09"),
    "ASTERUSDT": ("2025", "10"),
    "PEPEUSDT": ("2023", "05"),
    "ONDOUSDT": ("2025", "04"),
    "ICPUSDT": ("2021", "05"),
    "TRUMPUSDT": ("2025", "01"),
    "AAVEUSDT": ("2020", "10"),
    "ETCUSDT": ("2018", "06"),
    "FILUSDT": ("2020", "10"),
    "WLFIUSDT": ("2025", "09"),
}


DEFAULT_INTERVALS = ["1d", "4h", "1h", "15m", "5m", "1m"]

# ✅ 关键：基于当前 config.py 所在目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))

DATA_DIR = os.path.join(PROJECT_ROOT, "binance_data")

# ── 初始化日志系统 ───────────────────────────────────────────
from utils.logger import setup_logger, logger
setup_logger()

#from logger import logger

# ======================
# 工具函数
# ======================
def generate_months(start_year, start_month, end_year=2026, end_month=4):
    months = []
    for year in range(int(start_year), end_year + 1):
        first_month = int(start_month) if year == int(start_year) else 1
        last_month = 12 if year != end_year else end_month

        for month in range(first_month, last_month + 1):
            months.append((year, f"{month:02d}"))
    return months

# ======================
# Klines 主下载逻辑
# ======================
def download_klines(symbols, intervals):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for symbol in symbols:
        if symbol not in DEFAULT_SYMBOLS_START:
            logger.warning(f"未配置起始时间，跳过 {symbol}")
            continue

        start_year, start_month = DEFAULT_SYMBOLS_START[symbol]
        months = generate_months(start_year, start_month)

        for interval in intervals:
            for year, month in tqdm(months, desc=f"{symbol}-{interval}"):
                filename = f"{symbol}-{interval}-{year}-{month}.zip"
                url = urljoin(BASE_URL + "/", f"{symbol}/{interval}/{filename}")
                dir_path = os.path.join(DATA_DIR, symbol, interval)
                os.makedirs(dir_path, exist_ok=True)
                path = os.path.join(dir_path, filename)

                if os.path.exists(path):
                    continue

                try:
                    r = session.get(url, timeout=30)
                    if r.status_code == 200:
                        with open(path, "wb") as f:
                            f.write(r.content)
                        logger.info(f"Downloaded {filename}")
                except Exception as e:
                    logger.error(f"Error {filename}: {e}")

                time.sleep(0.2)
                
# ======================
# 检查与修复下载核心逻辑
# ======================
def check_and_repair(symbols, intervals):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for symbol in symbols:
        if symbol not in DEFAULT_SYMBOLS_START:
            logger.warning(f"未配置起始时间，跳过 {symbol}")
            continue

        start_year, start_month = DEFAULT_SYMBOLS_START[symbol]
        months = generate_months(start_year, start_month)

        for interval in intervals:
            for year, month in tqdm(months, desc=f"{symbol}-{interval}"):
                filename = f"{symbol}-{interval}-{year}-{month}.zip"
                dir_path = os.path.join(DATA_DIR, symbol, interval)
                os.makedirs(dir_path, exist_ok=True)
                path = os.path.join(DATA_DIR, symbol, interval, filename)

                if os.path.exists(path):
                    continue

                url = urljoin(BASE_URL + "/", f"{symbol}/{interval}/{filename}")

                try:
                    r = session.get(url, timeout=30)
                    if r.status_code == 200:
                        with open(path, "wb") as f:
                            f.write(r.content)
                        logger.info(f"Repaired {filename}")
                except Exception as e:
                    logger.error(f"Error {filename}: {e}")

                time.sleep(0.2)


def parse_args():
    parser = argparse.ArgumentParser(description="Binance Kline Data Tool")

    parser.add_argument(
        "--mode",
        choices=["download", "repair", "both"],
        default="both",
        help="运行模式"
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="币种列表，如 BTCUSDT ETHUSDT"
    )

    parser.add_argument(
        "--intervals",
        nargs="+",
        default=DEFAULT_INTERVALS,
        help="时间周期，如 1d 1h 5m"
    )

    return parser.parse_args()

def main():
    args = parse_args()

    print(f"模式: {args.mode}")
    print(f"币种: {args.symbols}")
    print(f"周期: {args.intervals}")

    if args.mode in ("download", "both"):
        download_klines(args.symbols, args.intervals)

    if args.mode in ("repair", "both"):
        check_and_repair(args.symbols, args.intervals)

if __name__ == "__main__":
    main()
