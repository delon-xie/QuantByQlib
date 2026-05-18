"""
Qlib 策略实现
直接复用 Qlib 内置模型：LGBModel、LSTM、GRU、Transformer、MLP
使用 Qlib Alpha158/Alpha360 因子作为特征

数据适应策略：
  - 自动检测 Qlib 数据实际可用日期范围，以该范围为训练/预测锚点
  - 若 Qlib 数据不足（少于 252 天），切换为 yfinance 规则打分 fallback
"""
from __future__ import annotations

from typing import Optional
from datetime import date, timedelta, datetime as dt_cls
import pandas as pd
from loguru import logger

from strategies.base_strategy import BaseStrategy, StrategyResult

from core.model_helper import get_model
from pathlib import Path
from typing import Optional, Literal
from core.qlibhelper import _is_valid_stock_code
import torch
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ── Qlib 数据日期范围检测 ──────────────────────────────────────

def _get_qlib_data_end_date(market: Literal["us", "cn", "hk", "tw", "jp", "kr", "bt"]) -> Optional[date]:
    """
    检测 Qlib 股票市场数据中最新可用交易日。
    直接读 calendars/day.txt 末尾行，不依赖 D.features 也不依赖 app_state。
    使用 qlib_manager._find_data_dir() 自动定位正确的美股数据目录。
    """
    try:
        from data.qlib_manager import _find_data_dir
        data_dir = _find_data_dir()
    except Exception:
        data_dir = Path.home() / ".qlib" / "qlib_data"

    features_dir = data_dir / "features"
    if not features_dir.exists():
        logger.debug(f"Qlib features/ 目录不存在：{features_dir}")
        return None

    # ---------- 2. 按市场筛选股票目录 ----------
    def is_us_code(name: str) -> bool:
        name = name.replace("-", "").replace(".", "")
        return (
            name.isalpha()
            and not any(name.lower().startswith(pfx) for pfx in ("sh", "sz", "bj"))
        )

    def is_cn_code(name: str) -> bool:
        return name.lower().startswith(("sh", "sz", "bj"))

    #if market == "us":
    #    target_dirs = [d for d in features_dir.iterdir() if d.is_dir() and is_us_code(d.name)]
    #else:  # cn
    #    target_dirs = [d for d in features_dir.iterdir() if d.is_dir() and is_cn_code(d.name)]

    target_dirs = [d for d in features_dir.iterdir() if d.is_dir()]
    
    if not target_dirs:
        logger.debug(f"Qlib features/ 下未发现 {market.upper()} 数据，目录：{data_dir}")
        return None

    # ---------- 3. 读取日历 ----------
    cal_file = data_dir / "calendars" / "day.txt"
    if not cal_file.exists():
        logger.debug(f"Qlib 日历文件不存在：{cal_file}")
        return None

    try:
        lines = cal_file.read_text().strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    latest = dt_cls.strptime(line, "%Y-%m-%d").date()
                    logger.debug(
                        f"Qlib {market.upper()} 数据最新交易日：{latest} "
                        f"（数据目录：{data_dir}，{len(target_dirs)} 只标的）"
                    )
                    return latest
                except ValueError:
                    continue
    except Exception as e:
        logger.debug(f"Qlib 日历文件读取失败：{e}")

    return None


def _qlib_init_check():
    """
    确认 Qlib 已初始化，否则自动尝试初始化。
    Worker 线程中 app_state 可能为 False，因此先尝试 init 再检查。
    """
    try:
        from core.app_state import get_state
        if get_state().qlib_initialized:
            return
    except Exception:
        pass
    # 尝试自动初始化
    try:
        from data.qlib_manager import init_qlib
        ok = init_qlib()
        if ok:
            return
    except Exception as e:
        pass
    raise RuntimeError("Qlib 尚未初始化，请先在「参数配置」页下载数据")


def _build_dataset(universe: list[str], handler_class_name: str = "Alpha158",
                   train_days: int = 252 * 2, pred_days: int = 20):
    """
    构建 Qlib DatasetH（训练 + 预测数据集）
    自动以 Qlib 数据实际最新日期为锚点，而非今天

    日期段布局（从早到晚，不重叠）：
      train_start ─── train_end ─── valid_end ─── pred_end(=anchor)
                       │                │
                       └── valid ────── ┘
                                        └── test ── pred_end

    train_days: 训练窗口交易日数（约 2 年）
    pred_days:  验证+测试总窗口（各占一半）
    """
    from qlib.data.dataset import DatasetH
    from core.app_state import get_state
    reg = get_state().reg

    # 以 Qlib 数据实际结尾日期为基准
    data_end = _get_qlib_data_end_date(reg)
    if data_end is None:
        raise RuntimeError("无法获取 Qlib 数据日期范围，数据可能为空")

    anchor = data_end

    # 日期段：确保 train < valid < test，且时间递增
    # 以交易日数估算，1 交易日 ≈ 1.5 自然日
    valid_days = max(pred_days, 20)       # 验证集：至少 20 个交易日
    test_days  = max(pred_days, 10)       # 测试集：至少 10 个交易日

    pred_end    = anchor
    test_start  = anchor - timedelta(days=int(test_days * 1.5))
    valid_start = test_start - timedelta(days=int(valid_days * 1.5))
    train_end   = valid_start
    train_start = valid_start - timedelta(days=int(train_days * 1.5))

    # 转为字符串
    train_start_s = train_start.isoformat()
    train_end_s   = train_end.isoformat()
    valid_start_s = valid_start.isoformat()
    test_start_s  = test_start.isoformat()
    pred_end_s    = pred_end.isoformat()

    logger.info(
        f"DatasetH 日期锚点：data_end={anchor}  "
        f"train=[{train_start_s} → {train_end_s}]  "
        f"valid=[{valid_start_s} → {test_start_s}]  "
        f"test=[{test_start_s} → {pred_end_s}]"
    )

    # 动态导入 Alpha158 或 Alpha360
    if handler_class_name == "Alpha360":
        from qlib.contrib.data.handler import Alpha360 as HandlerClass
    else:
        from qlib.contrib.data.handler import Alpha158 as HandlerClass

    # SunsetWolf 数据使用小写 ticker（aapl），统一转小写
    universe_qlib = [t.lower() for t in universe]

    handler = HandlerClass(
        instruments=universe_qlib,
        start_time=train_start_s,
        end_time=pred_end_s,
        fit_start_time=train_start_s,
        fit_end_time=train_end_s,
    )
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (train_start_s, train_end_s),
            "valid": (valid_start_s, test_start_s),
            "test":  (test_start_s,  pred_end_s),
        },
    )
    return dataset


def _scores_to_result(scores_series: pd.Series, strategy_key: str,
                      strategy_name: str, model_name: str,
                      universe: list[str], topk: int) -> StrategyResult:
    """将预测分数 Series 转化为 StrategyResult"""
    import numpy as np

    # scores_series index 可能是 MultiIndex，取最后一日
    # 兼容 (datetime, instrument) 和 (instrument, datetime) 两种顺序
    if isinstance(scores_series.index, pd.MultiIndex):
        idx_names = scores_series.index.names
        if "datetime" in idx_names:
            dt_level = idx_names.index("datetime")
            latest_date = scores_series.index.get_level_values(dt_level).max()
            scores_series = scores_series.xs(latest_date, level=dt_level)
        else:
            latest_date = scores_series.index.get_level_values(0).max()
            scores_series = scores_series.xs(latest_date, level=0)

    # 统一 index 为大写（Qlib 存储小写 aapl，UI 显示大写 AAPL）
    scores_series.index = scores_series.index.str.upper()

    # 去除 NaN 分数（LSTM 输入含 NaN 时预测结果为 NaN）
    valid_mask = scores_series.notna() & np.isfinite(scores_series)
    if valid_mask.sum() == 0:
        logger.warning(f"[{strategy_key}] 所有预测分数为 NaN，用 0 填充")
        scores_series = scores_series.fillna(0.0)
    else:
        scores_series = scores_series[valid_mask]

    # 降序排序，取 Top-K
    scores_series = scores_series.sort_values(ascending=False)
    topk_list = scores_series.index[:topk].tolist()

    return StrategyResult(
        strategy_key=strategy_key,
        strategy_name=strategy_name,
        scores=scores_series,
        topk_tickers=topk_list,
        model_name=model_name,
        universe_size=len(universe),
    )


# ── yfinance 规则打分 fallback ──────────────────────────────────
def download_or_get_local_data(chunk, cb, progress_info=""):
    """
    尝试从 yfinance 下载数据，失败时从 qlib 获取本地数据
    
    Args:
        chunk: 股票代码列表
        cb: 回调函数，用于显示进度
        progress_info: 进度信息
        
    Returns:
        下载的数据 DataFrame
    """
    df_all = None
    
    try:
        # 尝试从 yfinance 下载数据
        cb(f"{progress_info}尝试下载 {chunk}...")
        
        from core.app_state import get_state
        from workers.binance_downloader import binance_download
        reg = get_state().reg
        if reg == "bt":
            df_all = binance_download(
                chunk,
                period="3mo",
                progress=False,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
            )
        else:
            import yfinance as yf
            from core.qlibhelper import normalize_cn_tickers
            if reg == "cn":
                chunk = normalize_cn_tickers(chunk)
            # yfinance 一次下载所有 ticker，速度远快于逐一下载
            # tickers_str = " ".join(tickers)
            df_all = yf.download(
                chunk,
                period="3mo",
                progress=False,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
            )

        if df_all is not None and not df_all.empty:
            cb(f"{progress_info}下载成功")
            return df_all
            
    except Exception as e:
        cb(f"{progress_info}yfinance 下载失败: {str(e)[:50]}...")
    
    # 如果 yfinance 下载失败，尝试从 qlib 获取本地数据
    cb(f"{progress_info}尝试从 qlib 本地数据获取...")
    try:
        df_all = get_qlib_local_data(chunk, days=90)  # 获取最近3个月数据
        if df_all is not None and not df_all.empty:
            cb(f"{progress_info}qlib 本地数据获取成功")
        else:
            cb(f"{progress_info}qlib 本地数据为空")
    except Exception as e:
        cb(f"{progress_info}qlib 本地数据获取失败: {str(e)[:50]}...")
    
    return df_all

def get_qlib_local_data(symbols, days=90):
    """
    从 qlib 本地数据获取历史数据
    
    Args:
        symbols: 股票代码列表
        days: 获取最近多少天的数据
        
    Returns:
        与 yfinance 格式兼容的 DataFrame
    """
    try:
        from qlib.data import D
        from qlib.data.data import Cal
        
        # 获取日历
        cal_client = Cal()
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # 获取交易日历
        trade_days = cal_client.get_calendar(start_date, end_date)
        if len(trade_days) == 0:
            return pd.DataFrame()
        
        # 获取数据
        fields = ["$close", "$volume", "$open", "$high", "$low"]
        
        all_data = []
        for symbol in symbols:
            try:
                # 获取单个股票的数据
                df = D.features([symbol], fields, start_time=start_date, end_time=end_date)
                if df is not None and not df.empty:
                    # 重命名列以匹配 yfinance 格式
                    df = df.rename(columns={
                        "$close": "Close",
                        "$volume": "Volume",
                        "$open": "Open",
                        "$high": "High",
                        "$low": "Low"
                    })
                    
                    # 添加 Adj Close 列（qlib 没有复权价格，用收盘价代替）
                    df["Adj Close"] = df["Close"]
                    
                    # 设置多级列索引以匹配 yfinance 格式
                    df_columns = pd.MultiIndex.from_product([[symbol], 
                        ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
                    
                    # 重新组织数据
                    df_multi = pd.DataFrame(index=df.index)
                    for col in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
                        if col in df.columns:
                            df_multi[(symbol, col)] = df[col]
                    
                    all_data.append(df_multi)
            except Exception as e:
                print(f"获取 {symbol} 数据失败: {e}")
                continue
        
        if not all_data:
            return pd.DataFrame()
        
        # 合并所有股票数据
        df_all = pd.concat(all_data, axis=1)
        
        # 如果只有一只股票，调整格式
        if len(symbols) == 1:
            symbol = symbols[0]
            if (symbol, "Close") in df_all.columns:
                # 已经是正确的格式
                pass
        
        return df_all
        
    except ImportError as e:
        print(f"导入 qlib 失败: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"获取 qlib 数据失败: {e}")
        return pd.DataFrame()
def _yfinance_score_universe(
    universe: list[str],
    strategy_key: str,
    strategy_name: str,
    topk: int,
    progress_cb=None,
) -> StrategyResult:
    """
    当 Qlib 模型无法运行时，用 yfinance 实时价格数据进行规则打分：
      - 动量因子（20日/60日涨幅）
      - 成交量趋势（OBV 方向）
      - 均线排列（5/20日均线位置）
    完全基于真实市场数据，无 Mock。
    """
    import numpy as np
    import yfinance as yf

    def cb(pct, msg):
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass
        logger.debug(f"[{strategy_key}] {pct}% - {msg}")

    cb(10, f"yfinance 模式：对 {len(universe)} 支股票打分...")

    scores: dict[str, float] = {}
    batch = 50   # 每批下载避免请求过多
    total = len(universe)

    for i in range(0, total, batch):
        chunk = universe[i: i + batch]
        pct = 10 + int((i / total) * 70)
        cb(pct, f"下载价格数据 {i+1}-{min(i+batch, total)}/{total}...")
        # 创建进度信息
        progress_info = f"下载价格数据 {i+1}-{min(i+batch, total)}/{total} "
    
        try:
            #tickers_str = " ".join(chunk)
            from core.app_state import get_state
            reg = get_state().reg
            
            if reg == "bt":
                # 需要处理binance的下载数据
                cb(f"{progress_info}BTC行情，使用 qlib 本地数据...")
                print(f"{progress_info}BTC行情，使用 qlib 本地数据...")
                df_all = get_qlib_local_data(chunk, days=90)
            else:
                # 使用 yfinance 下载，失败时自动回退到 qlib
                print("yfinace")
                df_all = download_or_get_local_data(chunk, cb, progress_info)
            
            if df_all is None or df_all.empty:
                cb(f"{progress_info}数据为空，跳过")
                continue
            if df_all is None or df_all.empty:
                continue

            for ticker in chunk:
                try:
                    # 多股票时 df_all 有 MultiIndex 列
                    if isinstance(df_all.columns, pd.MultiIndex):
                        if ticker not in df_all.columns.get_level_values(0):
                            continue
                        df = df_all[ticker].dropna()
                    else:
                        # 单股票时列为扁平
                        df = df_all.dropna()

                    if df.empty or len(df) < 10:
                        continue

                    close = df["Close"] if "Close" in df.columns else df["close"]
                    volume = df["Volume"] if "Volume" in df.columns else df.get("volume")

                    sub_scores = []

                    # 1. 动量（20日涨幅）
                    if len(close) >= 20:
                        mom20 = float(close.iloc[-1] / close.iloc[-20] - 1)
                        sub_scores.append(np.clip(mom20 * 5 + 0.5, 0, 1))

                    # 2. 动量（60日涨幅，若有）
                    if len(close) >= 60:
                        mom60 = float(close.iloc[-1] / close.iloc[-60] - 1)
                        sub_scores.append(np.clip(mom60 * 3 + 0.5, 0, 1))

                    # 3. 均线排列（价格在 MA20 上方 → 高分）
                    if len(close) >= 20:
                        ma20 = float(close.rolling(20).mean().iloc[-1])
                        price = float(close.iloc[-1])
                        diff = (price / ma20 - 1)
                        sub_scores.append(np.clip(diff * 10 + 0.5, 0, 1))

                    # 4. 量价配合（OBV 趋势）
                    if volume is not None and len(close) >= 10:
                        import numpy as np2
                        sign = np2.sign(close.diff().fillna(0))
                        obv = (sign * volume).cumsum()
                        obv_chg = float(obv.iloc[-1] - obv.iloc[-10]) / (float(abs(obv).mean()) + 1e-9)
                        sub_scores.append(np.clip(obv_chg * 2 + 0.5, 0, 1))

                    if sub_scores:
                        scores[ticker] = float(np.mean(sub_scores))

                except Exception as e:
                    logger.debug(f"yfinance 打分失败 {ticker}：{e}")
        except Exception as e:
            logger.debug(f"yfinance 批量下载失败：{e}")

    cb(85, f"打分完成，{len(scores)} 支有效，排名 Top-{topk}...")

    if not scores:
        raise RuntimeError("所有股票价格数据获取失败，无法生成选股结果")

    scores_series = pd.Series(scores).sort_values(ascending=False)
    topk_list = [str(t).upper() for t in scores_series.index[:topk].tolist()]

    logger.info(
        f"yfinance 规则打分完成：{len(scores)} 支有效，"
        f"Top-{topk}：{topk_list[:5]}..."
    )

    return StrategyResult(
        strategy_key=strategy_key,
        strategy_name=strategy_name + "（价格动量）",
        scores=scores_series,
        topk_tickers=topk_list,
        model_name="yfinance 规则打分",
        universe_size=len(universe),
    )


def _patch_pytorch_model_best_param(model) -> None:
    """
    修复 Qlib 0.9.7 LSTM/GRU 两个 bug：
    1. fit() 中 best_param 未赋值：当第一个 epoch val_score=nan 时
       if val_score > best_score 条件为 False，best_param 永远不被赋值，
       导致 fit 结束时 load_state_dict(best_param) 抛 UnboundLocalError。
    2. predict() 中 NaN 传播：x_test 含 NaN 特征（Alpha158 边界行），
       送入 LSTM 后输出全为 NaN；通过 fillna(0) 预处理解决。
    """
    import copy, types, numpy as np_

    # 只对 PyTorch 模型（LSTM/GRU/MLP）打补丁，LightGBM 等非 PyTorch 模型直接跳过
    _pytorch_model_names = ("LSTM", "GRU", "MLP", "Net", "Transformer", "ALSTM")
    if not any(name in type(model).__name__ for name in _pytorch_model_names):
        return

    #import torch

    original_fit = model.fit.__func__ if hasattr(model.fit, '__func__') else None
    if original_fit is None:
        return  # 无法 patch，跳过

    def patched_fit(self, dataset, evals_result=dict(), save_path=None):
        #import torch
        from qlib.data.dataset.handler import DataHandlerLP
        from qlib.utils import get_or_create_path

        df_train, df_valid, df_test = dataset.prepare(
            ["train", "valid", "test"],
            col_set=["feature", "label"],
            data_key=DataHandlerLP.DK_L,
        )
        if df_train.empty or df_valid.empty:
            raise ValueError("Empty data from dataset, please check your dataset config.")

        # fillna 防止 NaN 传播到 PyTorch 损失计算（导致 loss=nan，val_score=nan）
        feat_train = df_train["feature"].fillna(df_train["feature"].mean()).fillna(0.0)
        feat_valid = df_valid["feature"].fillna(df_valid["feature"].mean()).fillna(0.0)
        label_train = df_train["label"].fillna(0.0)
        label_valid = df_valid["label"].fillna(0.0)

        x_train, y_train = feat_train, label_train
        x_valid, y_valid = feat_valid, label_valid

        # 动态限制 batch_size：Qlib train_epoch/test_epoch 当 batch_size > 样本数时
        # 整个循环不执行，scores=[]，np.mean([])=nan，导致 val_score 全为 nan。
        # 将 batch_size 限制为 min(原设定, 验证集大小, 训练集大小)
        min_samples = min(len(x_train), len(x_valid))
        if self.batch_size > min_samples:
            self.batch_size = max(1, min_samples)

        save_path = get_or_create_path(save_path)
        stop_steps = 0
        best_score = -np_.inf
        best_epoch = 0
        evals_result["train"] = []
        evals_result["valid"] = []

        self.fitted = True
        # ★ 预先初始化 best_param，避免第一个 epoch val_score=nan 时未赋值
        best_param = copy.deepcopy(self.lstm_model.state_dict()
                                   if hasattr(self, 'lstm_model')
                                   else self.gru_model.state_dict())

        for step in range(self.n_epochs):
            self.train_epoch(x_train, y_train)
            train_loss, train_score = self.test_epoch(x_train, y_train)
            val_loss, val_score = self.test_epoch(x_valid, y_valid)
            self.logger.info("train %.6f, valid %.6f" % (train_score, val_score))
            evals_result["train"].append(train_score)
            evals_result["valid"].append(val_score)

            # 用 nan-safe 比较
            if np_.isfinite(val_score) and val_score > best_score:
                best_score = val_score
                stop_steps = 0
                best_epoch = step
                best_param = copy.deepcopy(self.lstm_model.state_dict()
                                           if hasattr(self, 'lstm_model')
                                           else self.gru_model.state_dict())
            else:
                stop_steps += 1
                if stop_steps >= self.early_stop:
                    self.logger.info("early stop")
                    break

        self.logger.info("best score: %.6lf @ %d" % (best_score, best_epoch))
        if hasattr(self, 'lstm_model'):
            self.lstm_model.load_state_dict(best_param)
        else:
            self.gru_model.load_state_dict(best_param)
        torch.save(best_param, save_path)

    model.fit = types.MethodType(patched_fit, model)

    # ── patch predict：在 x_values 送入网络前 fillna(0) ──────
    original_predict = model.predict.__func__ if hasattr(model.predict, '__func__') else None
    if original_predict is None:
        return

    def patched_predict(self, dataset, segment="test"):
        import pandas as pd_
        import numpy as np_
        from qlib.data.dataset.handler import DataHandlerLP

        x_test = dataset.prepare(segment, col_set="feature", data_key=DataHandlerLP.DK_I)
        index = x_test.index

        # 用列均值填充 NaN，避免 NaN 在 LSTM 中传播导致输出全为 NaN
        x_filled = x_test.fillna(x_test.mean()).fillna(0.0)
        x_values = x_filled.values

        nn_model = self.lstm_model if hasattr(self, 'lstm_model') else self.gru_model
        nn_model.eval()
        sample_num = x_values.shape[0]
        preds = []

        #import torch
        for begin in range(0, sample_num, self.batch_size):
            end = min(begin + self.batch_size, sample_num)
            x_batch = torch.from_numpy(x_values[begin:end]).float().to(self.device)
            with torch.no_grad():
                pred = nn_model(x_batch).detach().cpu().numpy()
            preds.append(pred)

        return pd_.Series(np_.concatenate(preds), index=index)

    model.predict = types.MethodType(patched_predict, model)


def _fit_with_extra_factors(model, dataset, extra_exprs: list[str],
                            universe_qlib: list[str],
                            train_start_s: str, pred_end_s: str):
    """
    将 RD-Agent 发现的自定义因子注入 LGBModel 训练（仅支持 LightGBM）。
    通过 D.features() 计算自定义因子 DataFrame，与 Alpha158 输出 concat 后
    直接调用 model.fit()（LGBModel.fit 接受 dataset，通过 prepare() 获取数据）。

    实现策略：
      1. 调用 model.fit(dataset) 使用标准 Alpha158 特征（原有路径）
      2. 同时用 D.features() 加载自定义因子，追加到 LGB 的 train_x 中
      3. 由于 LGBModel.fit() 内部调用 dataset.prepare()，
         此处通过 monkey-patch dataset 的 prepare 方法在返回数据时追加列。

    Returns
    -------
    callable or None
        patched_prepare 函数（供 predict 阶段继续使用），失败时返回 None。
    """
    from qlib.data import D
    import numpy as np

    # 加载自定义因子数据
    try:
        custom_df = D.features(
            universe_qlib, extra_exprs,
            start_time=train_start_s, end_time=pred_end_s,
            freq="day",
        )
    except Exception as e:
        logger.warning(f"[因子注入] D.features 加载自定义因子失败：{e}，跳过注入")
        model.fit(dataset)
        return None

    if custom_df is None or custom_df.empty:
        logger.warning("[因子注入] 自定义因子数据为空，跳过注入")
        model.fit(dataset)
        return None

    # 重命名列，避免与 Alpha158 特征名冲突
    custom_df.columns = [f"_extra_{i}" for i in range(len(custom_df.columns))]
    logger.info(f"[因子注入] 加载 {len(extra_exprs)} 个自定义因子，"
                f"shape={custom_df.shape}，追加到 LGBModel 训练特征")

    # Monkey-patch dataset.prepare，在返回 feature 数据时追加自定义因子列
    original_prepare = dataset.prepare

    def patched_prepare(segments, col_set=None, data_key=None, **kwargs):
        result = original_prepare(segments, col_set=col_set, data_key=data_key, **kwargs)
        # 只对 feature 数据追加列
        should_concat = False
        if col_set is None or col_set == "feature":
            should_concat = True
        if isinstance(col_set, list) and "feature" in col_set:
            should_concat = True

        if not should_concat or result is None:
            return result

        try:
            if isinstance(result, dict):
                # segments 是 list（如 ["train","valid","test"]）
                new_result = {}
                for seg, df in result.items():
                    try:
                        feat_df = df["feature"] if "feature" in df.columns.get_level_values(0) else df
                        extra_aligned = custom_df.reindex(feat_df.index)
                        extra_aligned.columns = pd.MultiIndex.from_tuples(
                            [("feature", c) for c in extra_aligned.columns]
                        )
                        new_result[seg] = pd.concat([df, extra_aligned], axis=1)
                    except Exception:
                        new_result[seg] = df
                return new_result
            elif isinstance(result, pd.DataFrame):
                # 单个 segment
                try:
                    if isinstance(result.columns, pd.MultiIndex):
                        extra_aligned = custom_df.reindex(result.index)
                        extra_aligned.columns = pd.MultiIndex.from_tuples(
                            [("feature", c) for c in extra_aligned.columns]
                        )
                        return pd.concat([result, extra_aligned], axis=1)
                    else:
                        extra_aligned = custom_df.reindex(result.index)
                        return pd.concat([result, extra_aligned], axis=1)
                except Exception:
                    return result
        except Exception as e:
            logger.debug(f"[因子注入] concat 失败：{e}，返回原始数据")
        return result

    dataset.prepare = patched_prepare

    try:
        model.fit(dataset)
    except Exception:
        # fit 失败时恢复，再向上抛
        dataset.prepare = original_prepare
        raise

    # 注意：不在此处恢复 prepare，调用方需在 predict 结束后再恢复
    return patched_prepare


def _run_with_qlib_or_fallback(
    strategy_key: str,
    strategy_name: str,
    handler_class_name: str,
    model_factory,           # callable() → Qlib model instance
    universe: list[str],
    topk: int,
    progress_cb,
    train_days: int = 252 * 2,
    pred_days: int = 20,
) -> StrategyResult:
    """
    先尝试 Qlib 模型，若数据不足自动切换为 yfinance 规则打分
    训练结果缓存 24 小时，避免重复训练
    自动加载 RD-Agent 发现的自定义因子（~/.quantbyqlib/valid_factors.json），
    注入 LightGBM 训练特征，并将因子 hash 纳入缓存键。
    """
    from strategies.model_cache import cache_key, load_scores, save_scores

    def cb(pct, msg):
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    from core.app_state import get_state
    reg = get_state().reg
    # 检测 Qlib 数据是否足够
    data_end = _get_qlib_data_end_date(reg)
    days_since_data = (date.today() - data_end).days if data_end else 9999

    if data_end is None or days_since_data > 3650:
        # Qlib 数据过旧（超过 10 年前），直接用 yfinance
        # 即使数据截止到几年前，只要包含足够历史（>2年训练窗口），模型仍可训练并预测
        logger.info(
            f"[{strategy_key}] Qlib 数据过旧（末端={data_end}，"
            f"距今 {days_since_data} 天），切换 yfinance 规则打分"
        )
        cb(5, "Qlib 数据过旧，切换价格动量模式...")
        return _yfinance_score_universe(
            universe, strategy_key, strategy_name, topk, progress_cb
        )

    # 加载 RD-Agent 发现的自定义因子（LightGBM only）
    extra_exprs: list[str] = []
    is_lgb = "lgb" in strategy_key.lower() or strategy_key in ("growth_stocks", "market_adaptive")
    if is_lgb:
        try:
            from strategies.factor_injector import load_valid_factors
            extra_exprs = load_valid_factors()
            if extra_exprs:
                logger.info(f"[{strategy_key}] 加载 {len(extra_exprs)} 个自定义因子")
                cb(5, f"已加载 {len(extra_exprs)} 个 RD-Agent 自定义因子...")
        except Exception as e:
            logger.debug(f"[{strategy_key}] 加载自定义因子失败（忽略）：{e}")

    # 检查缓存（缓存键含自定义因子 hash，确保因子变化时自动失效）
    key = cache_key(strategy_key, universe, data_end, extra_exprs or None)
    cached = load_scores(key)
    if cached is not None:
        cb(95, f"命中缓存（{strategy_name}），直接返回结果...")
        logger.info(f"[{strategy_key}] 命中预测缓存，跳过训练")
        return _scores_to_result(
            cached, strategy_key, strategy_name,
            "缓存（< 24h）", universe, topk
        )

    # Qlib 数据足够，尝试模型训练
    try:
        cb(10, "构建 Qlib 数据集...")
        dataset = _build_dataset(
            universe, handler_class_name, train_days, pred_days
        )
        cb(30, "训练模型...")
        model = model_factory()
        # 应用 Qlib 0.9.7 best_param bug 修复
        _patch_pytorch_model_best_param(model)

        from core.app_state import get_state
        reg = get_state().reg
        # LightGBM：若有自定义因子则注入训练特征
        _patched_prepare = None
        _original_prepare = dataset.prepare  # 保留原始引用，用于后续恢复
        if extra_exprs and is_lgb:
            cb(32, f"注入 {len(extra_exprs)} 个自定义因子到训练特征...")
            universe_qlib = [t.lower() for t in universe]
            data_end_obj = _get_qlib_data_end_date(reg)
            anchor = data_end_obj
            valid_days = max(pred_days, 20)
            test_days  = max(pred_days, 10)
            from datetime import timedelta as _td
            pred_end    = anchor
            test_start  = anchor - _td(days=int(test_days * 1.5))
            valid_start = test_start - _td(days=int(valid_days * 1.5))
            train_start = valid_start - _td(days=int(train_days * 1.5))
            _patched_prepare = _fit_with_extra_factors(
                model, dataset, extra_exprs,
                universe_qlib,
                train_start.isoformat(), pred_end.isoformat(),
            )
            # _fit_with_extra_factors 成功时 dataset.prepare 仍是 patched 版本，
            # 保持不变让 predict 也能看到额外因子列
        else:
            model.fit(dataset)

        cb(75, "生成预测分数...")
        try:
            pred = model.predict(dataset, segment="test")
        finally:
            # predict 完成后无论成功/失败，都恢复原始 prepare
            if _patched_prepare is not None:
                dataset.prepare = _original_prepare

        # LSTM/GRU 在输入含 NaN 特征时输出为 NaN；
        # 对每支股票取其最近非 NaN 预测，或用该批均值填充
        if isinstance(pred.index, pd.MultiIndex):
            # 按 instrument 分组，各取最后一条非 NaN
            valid_pred = (
                pred.groupby(level="instrument")
                    .last()
                    .dropna()
            )
            if valid_pred.empty:
                # 退回到每日均值填充
                valid_pred = pred.groupby(level="instrument").mean()
        else:
            valid_pred = pred.dropna()

        if valid_pred.empty:
            raise RuntimeError("LSTM 预测结果全为 NaN，无法生成选股分数")

        pred = valid_pred
        logger.info(f"[{strategy_key}] 预测有效股票数：{len(pred)}")
        cb(90, "排名筛选 Top-K...")
        # 保存到缓存
        save_scores(key, pred)
        return _scores_to_result(
            pred, strategy_key, strategy_name,
            model.__class__.__name__, universe, topk
        )
    except Exception as e:
        logger.warning(
            f"[{strategy_key}] Qlib 模型失败（{e}），切换 yfinance 规则打分"
        )
        cb(5, "模型训练失败，切换价格动量模式...")
        return _yfinance_score_universe(
            universe, strategy_key, strategy_name, topk, progress_cb
        )


# ── 策略实现 ──────────────────────────────────────────────────

class GrowthStocksStrategy(BaseStrategy):
    """
    成长股选股：LightGBM + Alpha158
    LGBModel 是 Qlib 内置，直接实例化
    """
    KEY  = "growth_stocks"
    NAME = "成长股选股"
    TOPK = 50

    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        _qlib_init_check()

        def model_factory():
            return get_model("growth_stocks")

            # 废弃，旧版本固定参数，改为直接使用 Qlib 内置 LGBModel 默认参数，避免过拟合和不适用问题
            from qlib.contrib.model.gbdt import LGBModel
            return LGBModel(
                loss="mse",
                colsample_bytree=0.8879,
                learning_rate=0.0421,
                subsample=0.8789,
                lambda_l1=205.6999,
                lambda_l2=580.9768,
                max_depth=8,
                num_leaves=210,
                num_threads=4,
            )

        return _run_with_qlib_or_fallback(
            self.KEY, self.NAME, "Alpha158",
            model_factory, universe, self.topk, progress_cb,
        )


class MarketAdaptiveStrategy(BaseStrategy):
    """
    市场自适应：LightGBM + Alpha158
    （HMM 政体切换复杂度高，此处以 LightGBM 实现核心逻辑，政体检测作为权重调整）
    """
    KEY  = "market_adaptive"
    NAME = "市场自适应"
    TOPK = 50

    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        _qlib_init_check()
        regime = self._detect_regime()

        def model_factory():
            return get_model("market_adaptive_bull") if regime == "bull" else get_model("market_adaptive_bear")
        
            # 废弃，旧版本固定参数，改为直接使用 Qlib 内置 LGBModel 默认参数，避免过拟合和不适用问题
            from qlib.contrib.model.gbdt import LGBModel
            lr = 0.05 if regime == "bull" else 0.03
            return LGBModel(learning_rate=lr, num_leaves=128, num_threads=4)

        return _run_with_qlib_or_fallback(
            self.KEY, self.NAME, "Alpha158",
            model_factory, universe, self.topk, progress_cb,
        )

    def _detect_regime(self) -> str:
        """用市场宽度简单近似政体检测"""
        try:
            from data.market_data_client import get_ohlcv
            from core.app_state import get_state
            reg = get_state().reg
            tiker = "SPY" if reg != "bt" else "BTCUSDT"
            df = get_ohlcv(
                tiker,
                (date.today() - timedelta(days=60)).isoformat(),
                date.today().isoformat(),
            )
            if df is not None and "close" in df.columns and not df.empty:
                latest = float(df["close"].iloc[-1])
                prev   = float(df["close"].iloc[0])
                return "bull" if latest > prev else "bear"
        except Exception:
            pass
        return "neutral"


class DeepLearningStrategy(BaseStrategy):
    """
    深度学习集成：Qlib LSTM + Alpha158
    Transformer 训练耗时较长，散户场景用 LSTM 更实用
    """
    KEY  = "deep_learning"
    NAME = "深度学习集成"
    TOPK = 50
    # LSTM 对内存敏感，限制股票池规模防止 OOM 崩溃
    MAX_UNIVERSE = 500

    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        _qlib_init_check()

        # 限制 universe 大小，优先保留靠前的（经过字典序排序的蓝筹股）
        if len(universe) > self.MAX_UNIVERSE:
            logger.info(
                f"[{self.KEY}] universe {len(universe)} 支 → 截断至 {self.MAX_UNIVERSE} 支（防 OOM）"
            )
            universe = universe[: self.MAX_UNIVERSE]

        def model_factory():
            return get_model("deep_learning")
            
            # 废弃，旧版本固定参数，改为直接使用 Qlib 内置 LSTM 默认参数，避免过拟合和不适用问题
            from qlib.contrib.model.pytorch_lstm import LSTM
            return LSTM(
                d_feat=158,       # Alpha158 输出 158 个特征
                hidden_size=64,
                num_layers=2,
                dropout=0.0,
                n_epochs=10,      # 降低 epoch 数，避免训练时间过长导致假死
                lr=1e-3,
                early_stop=10,    # 须 >= n_epochs，避免 Qlib 0.9.7 best_param 未赋值 bug
                batch_size=512,   # 降低 batch_size 减少显存/内存峰值
                metric="",        # Qlib 0.9.7 LSTM 只支持 "" 或 "loss"
                GPU=-1,           # 强制 CPU，避免 MPS/CUDA 兼容性问题
            )

        return _run_with_qlib_or_fallback(
            self.KEY, self.NAME, "Alpha158",
            model_factory, universe, self.topk, progress_cb,
        )


class IntradayProfitStrategy(BaseStrategy):
    """
    短线获利：Qlib GRU + Alpha158（短序列）
    """
    KEY  = "intraday_profit"
    NAME = "短线获利"
    TOPK = 30
    MAX_UNIVERSE = 500

    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        _qlib_init_check()

        if len(universe) > self.MAX_UNIVERSE:
            logger.info(
                f"[{self.KEY}] universe {len(universe)} 支 → 截断至 {self.MAX_UNIVERSE} 支（防 OOM）"
            )
            universe = universe[: self.MAX_UNIVERSE]

        def model_factory():
            return get_model("intraday_profit")
        
            # 废弃，旧版本固定参数，改为直接使用 Qlib 内置 GRU 默认参数，避免过拟合和不适用问题
            from qlib.contrib.model.pytorch_gru import GRU
            return GRU(
                d_feat=158,       # Alpha158 输出 158 个特征
                hidden_size=64,
                num_layers=2,
                dropout=0.0,
                n_epochs=10,
                lr=1e-3,
                early_stop=10,    # >= n_epochs，避免 best_param 未赋值 bug
                batch_size=512,
                metric="",        # Qlib 0.9.7 GRU 只支持 "" 或 "loss"
                GPU=-1,           # 强制 CPU
            )

        return _run_with_qlib_or_fallback(
            self.KEY, self.NAME, "Alpha158",
            model_factory, universe, self.topk, progress_cb,
            train_days=126, pred_days=10,
        )


class PyTorchFullMarketStrategy(BaseStrategy):
    """
    全市场深度学习：PyTorch LSTM + Alpha360
    覆盖 NYSE+NASDAQ 全市场（5000+ 股票）
    """
    KEY  = "pytorch_full_market"
    NAME = "全市场深度学习"
    TOPK = 50
    MAX_UNIVERSE = 500   # Alpha360 特征更多，内存开销更大，适当限制

    def run(self, universe: list[str], progress_cb=None) -> StrategyResult:
        _qlib_init_check()

        if len(universe) > self.MAX_UNIVERSE:
            logger.info(
                f"[{self.KEY}] universe {len(universe)} 支 → 截断至 {self.MAX_UNIVERSE} 支（防 OOM）"
            )
            universe = universe[: self.MAX_UNIVERSE]

        def model_factory():
            return get_model("pytorch_full_market")
        
            # 废弃，旧版本固定参数，改为直接使用 Qlib 内置 LSTM 默认参数，避免过拟合和不适用问题
            from qlib.contrib.model.pytorch_lstm import LSTM
            return LSTM(
                d_feat=360,       # Alpha360 输出 360 个特征
                hidden_size=128,
                num_layers=1,
                dropout=0.0,
                n_epochs=8,
                lr=1e-3,
                early_stop=8,     # >= n_epochs，避免 best_param 未赋值 bug
                batch_size=512,   # 降低 batch_size
                metric="",        # Qlib 0.9.7 只支持 "" 或 "loss"
                GPU=-1,           # 强制 CPU
            )

        return _run_with_qlib_or_fallback(
            self.KEY, self.NAME, "Alpha360",
            model_factory, universe, self.topk, progress_cb,
        )


# ── 策略注册表 ────────────────────────────────────────────────

STRATEGY_REGISTRY: dict[str, type] = {
    "growth_stocks":       GrowthStocksStrategy,
    "market_adaptive":     MarketAdaptiveStrategy,
    "deep_learning":       DeepLearningStrategy,
    "intraday_profit":     IntradayProfitStrategy,
    "pytorch_full_market": PyTorchFullMarketStrategy,
}


def get_strategy(key: str, topk: Optional[int] = None) -> BaseStrategy:
    """根据 key 获取策略实例"""
    cls = STRATEGY_REGISTRY.get(key)
    if cls is None:
        raise ValueError(f"未知策略：{key}，可选：{list(STRATEGY_REGISTRY.keys())}")
    return cls(topk=topk)
