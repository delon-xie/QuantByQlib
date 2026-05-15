"""
F3：HMM 市场政体识别
使用 4 状态高斯 HMM，基于 SPY 的对数收益率和波动率特征识别市场政体。

政体定义（4状态）：
  recovery    — 复苏期（低增长，低波动，上行）
  expansion   — 扩张期（高增长，低波动，上行）
  overheating — 过热期（高增长，高波动，震荡）
  recession   — 衰退期（负增长，高波动，下行）

输出文件：美股交易日记/regime/hmm_regime_{YYYYMMDD}.json
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


# ── 政体标签映射 ────────────────────────────────────────────────────────────

_REGIME_LABELS_EN = ["recovery", "expansion", "overheating", "recession"]
_REGIME_LABELS_CN = {
    "recovery":    "复苏期",
    "expansion":   "扩张期",
    "overheating": "过热期",
    "recession":   "衰退期",
}

N_STATES = 4
MODEL_VERSION = "hmm_v2.2"


def run_regime_detection(
    trade_date: Optional[date] = None,
    lookback_years: int = 3,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    运行 HMM 政体识别，写入 JSON 文件并返回路径。

    Parameters
    ----------
    trade_date      : 输出文件日期标签（默认今日）
    lookback_years  : 训练 HMM 使用的历史年数
    output_dir      : 输出目录（默认 services.output_paths.get_regime_dir()）
    """
    from services.output_paths import get_regime_dir, regime_filename
    from services.manifest_writer import ManifestBuilder

    d = trade_date or date.today()

    logger.info(f"[HMM] 开始市场政体识别，日期锚点：{d}")

    # 1. 获取数据
    spy_df = _fetch_spy_data(d, lookback_years)
    if spy_df is None or spy_df.empty:
        raise RuntimeError("[HMM] 无法获取 SPY 历史数据")

    # 2. 特征工程
    features, dates = _build_features(spy_df)

    # 3. 拟合 HMM
    model, labels = _fit_hmm(features)

    # 4. 政体语义标注
    labeled_states = _label_states(model, features, labels)

    # 5. 当前政体
    current_state_idx = labels[-1]
    current_regime    = labeled_states[current_state_idx]
    current_prob      = float(
        model.predict_proba(features)[-1, current_state_idx]
    )

    # 6. 近30天历史（周粒度：取每周最后一天，含真实后验概率）
    regime_history = _build_regime_history(
        dates, labels, labeled_states, model, features, weeks=30
    )

    # 7. SPY 短期收益预测（Bootstrap 分布预测 + 置信区间）
    forecasts = _forecast(spy_df, labels, labeled_states, current_regime)

    # 8. 构建 JSON
    training_end = spy_df.index[-1].date().isoformat()
    payload = {
        "date":                   d.isoformat(),
        "regime":                 current_regime,
        "regime_label_cn":        _REGIME_LABELS_CN.get(current_regime, current_regime),
        "regime_probability":     round(current_prob, 4),
        "regime_history_30d":      regime_history,
        "spy_return_forecast_5d":  forecasts["spy_return_forecast_5d"],
        "spy_return_forecast_20d": forecasts["spy_return_forecast_20d"],
        "volatility_forecast_20d": forecasts["volatility_forecast_20d"],
        "forecast_detail":         forecasts["forecast_detail"],
        "hmm_n_states":           N_STATES,
        "model_version":          MODEL_VERSION,
        "training_end_date":      training_end,
    }

    # 9. 写文件
    out_dir = output_dir or get_regime_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / regime_filename(d)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        f"[HMM] 政体识别完成：{current_regime}（{_REGIME_LABELS_CN[current_regime]}），"
        f"概率={current_prob:.2%}  → {out_path}"
    )
    return out_path


# ── 数据获取 ────────────────────────────────────────────────────────────────

def _fetch_spy_data(anchor: date, lookback_years: int) -> Optional[pd.DataFrame]:
    start = anchor - timedelta(days=int(lookback_years * 365.25) + 30)
    logger.info(f"[HMM] 获取 SPY 数据：{start} → {anchor}")

    from core.app_state import get_state
    reg = get_state().reg
    # 优先长桥
    try:
        from data.longport_client import is_configured
        if is_configured() and reg != "bt":
            df = _fetch_longport_spy(anchor)
            if df is not None and len(df) > 100:
                logger.info(f"[HMM] 长桥数据 OK，{len(df)} 条")
                return _enrich(df)
    except Exception as e:
        logger.debug(f"[HMM] 长桥获取失败：{e}")

    # Fallback yfinance
    try:
        from core.app_state import get_state
        from workers.binance_downloader import binance_download
        reg = get_state().reg
        if reg == "bt":
            raw = binance_download(
                "BTCUSDT", 
                start=start.isoformat(), 
                end=anchor.isoformat(),
                progress=False, 
                auto_adjust=True,
                threads=True,
            )
        else:
            import yfinance as yf
            # yfinance 一次下载所有 ticker，速度远快于逐一下载
            # tickers_str = " ".join(tickers)
            raw = yf.download(
                "SPY", 
                start=start.isoformat(), 
                end=anchor.isoformat(),
                progress=False, 
                auto_adjust=True,
                threads=True,
            )
        
        if raw is not None and not raw.empty:
            if hasattr(raw.columns, "levels"):
                raw.columns = raw.columns.get_level_values(0)
            raw.index = pd.to_datetime(raw.index)
            logger.info(f"[HMM] yfinance SPY 数据 OK，{len(raw)} 条")
            return _enrich(raw)
    except Exception as e:
        logger.error(f"[HMM] yfinance 获取失败：{e}")
    return None


def _fetch_longport_spy(anchor: date) -> Optional[pd.DataFrame]:
    from longport.openapi import QuoteContext, Config, Period, AdjustType
    cfg = Config.from_env()
    ctx = QuoteContext(cfg)
    rows = []
    for bar in ctx.candlesticks("SPY.US", Period.Day, 800, AdjustType.ForwardAdj):
        rows.append({
            "Date":  pd.Timestamp(bar.timestamp),
            "Open":  float(bar.open),
            "High":  float(bar.high),
            "Low":   float(bar.low),
            "Close": float(bar.close),
            "Volume":int(bar.volume),
        })
    if not rows:
        return None
    df = pd.DataFrame(rows).set_index("Date").sort_index()
    return df


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    """计算 log_ret 和 rolling_vol"""
    df = df.copy()
    df["log_ret"]     = np.log(df["Close"] / df["Close"].shift(1))
    df["rolling_vol"] = df["log_ret"].rolling(20).std()
    df = df.dropna()
    return df


# ── 特征工程 ────────────────────────────────────────────────────────────────

def _build_features(df: pd.DataFrame):
    """返回 (features_array_standardized, dates_list)"""
    raw = np.column_stack([
        df["log_ret"].values,
        df["rolling_vol"].values,
    ])
    # 标准化（零均值单位方差），避免协方差矩阵数值病态
    mean = raw.mean(axis=0)
    std  = raw.std(axis=0)
    std[std == 0] = 1.0
    feat = (raw - mean) / std
    return feat, list(df.index)


# ── HMM 拟合 ────────────────────────────────────────────────────────────────

def _fit_hmm(features: np.ndarray):
    """拟合 GaussianHMM，返回 (model, state_labels)"""
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        raise RuntimeError(
            "hmmlearn 未安装。请执行：pip install hmmlearn"
        )
    model = GaussianHMM(
        n_components=N_STATES,
        covariance_type="diag",   # 对角协方差，数值更稳定
        n_iter=200,
        random_state=42,
        verbose=False,
    )
    model.fit(features)
    labels = model.predict(features)
    return model, labels


# ── 语义标注：按均收益率高低将状态映射到政体名 ─────────────────────────────

def _label_states(model, features, labels) -> dict[int, str]:
    """
    按各状态的平均对数收益率 × 波动率分布，分配 4 个政体标签：
      - 高收益低波动 → expansion
      - 高收益高波动 → overheating
      - 低收益低波动 → recovery
      - 低收益高波动 → recession
    """
    means = model.means_  # shape (n_states, n_features)
    ret_means = means[:, 0]
    vol_means = means[:, 1]

    ret_median = np.median(ret_means)
    vol_median = np.median(vol_means)

    result: dict[int, str] = {}
    for i in range(N_STATES):
        high_ret = ret_means[i] >= ret_median
        high_vol = vol_means[i] >= vol_median
        if high_ret and not high_vol:
            result[i] = "expansion"
        elif high_ret and high_vol:
            result[i] = "overheating"
        elif not high_ret and not high_vol:
            result[i] = "recovery"
        else:
            result[i] = "recession"

    # 若出现重复（均值很接近），用 ret 排名消除重复
    used = list(result.values())
    if len(set(used)) < N_STATES:
        # 按 ret 降序、vol 升序重新排列
        order = sorted(range(N_STATES),
                       key=lambda i: (-ret_means[i], vol_means[i]))
        labels_seq = ["expansion", "overheating", "recovery", "recession"]
        result = {order[j]: labels_seq[j] for j in range(N_STATES)}

    logger.debug(f"[HMM] 状态→政体映射：{result}")
    return result


# ── 近30天历史 ────────────────────────────────────────────────────────────

def _build_regime_history(
    dates, labels, labeled_states: dict[int, str],
    model, features: np.ndarray,
    weeks: int = 30,
) -> list[dict]:
    """
    每周取最后一个交易日，返回最近 weeks 周的政体序列。

    修复技术债：通过 model.predict_proba() 计算每个历史点的
    真实后验概率，不再使用固定占位值 0.75。
    """
    # ── 计算全序列后验概率矩阵 (n_days, n_states) ───────────────────────────
    posteriors = model.predict_proba(features)   # shape: (n_days, n_states)

    # ── 建立 date → features 行索引的快速查找表 ─────────────────────────────
    date_to_idx: dict = {}
    for i, d in enumerate(dates):
        key = d.date() if hasattr(d, "date") else d
        date_to_idx[key] = i

    # ── 按周分组，取每周最后一个交易日 ──────────────────────────────────────
    df_tmp = pd.DataFrame({
        "date":  [d.date() if hasattr(d, "date") else d for d in dates],
        "state": labels,
    })
    df_tmp["regime"]   = df_tmp["state"].map(labeled_states)
    df_tmp["week_end"] = pd.to_datetime(df_tmp["date"]).dt.to_period("W").dt.end_time.dt.date

    weekly = (
        df_tmp.groupby("week_end")
        .agg({"regime": "last", "state": "last", "date": "last"})
        .reset_index(drop=True)
        .tail(weeks)
    )

    # ── 构建历史记录，含真实后验概率 ─────────────────────────────────────────
    history = []
    for _, row in weekly.iterrows():
        row_date  = row["date"].date() if hasattr(row["date"], "date") else row["date"]
        row_state = int(row["state"])

        feat_idx = date_to_idx.get(row_date)
        if feat_idx is not None:
            # 该时间步被预测为当前状态的后验概率（Viterbi 后验）
            prob = round(float(posteriors[feat_idx, row_state]), 4)
        else:
            # 极少数情况：周末对齐导致日期偏移，用相邻最近交易日
            logger.warning(f"[HMM] 历史概率：找不到日期 {row_date}，跳过该周")
            continue

        history.append({
            "date":        row_date.isoformat() if hasattr(row_date, "isoformat") else str(row_date),
            "regime":      row["regime"],
            "probability": prob,   # ✅ 真实后验概率，非占位值
        })
    return history


# ── 短期预测 ────────────────────────────────────────────────────────────────

def _forecast(
    df: pd.DataFrame,
    labels: np.ndarray,
    labeled_states: dict[int, str],
    current_regime: str,
    horizon_5: int = 5,
    horizon_20: int = 20,
    n_sim: int = 10_000,
) -> dict:
    """
    基于当前政体历史收益分布，用 Bootstrap 路径模拟计算预测收益。

    改进点（相比原始均值外推）：
      - Bootstrap 10,000 路径 → 输出 p10 / p50 / p90 三档置信区间
      - 稳健化：剔除 3σ 极端日再估计，避免黑天鹅拉偏分布
      - 波动率由政体内日收益标准差换算，非日均 rolling_vol 直接乘 √n
      - 新增 forecast_detail 扩展字段（不破坏原有接口字段）

    Returns
    -------
    dict，包含原接口兼容字段及 forecast_detail 扩展字段。
    """
    # ── 取当前政体的历史日收益 ────────────────────────────────────────────────
    cur_state_list = [k for k, v in labeled_states.items() if v == current_regime]
    sparse = False

    if cur_state_list:
        mask = (labels == cur_state_list[0])
        regime_rets = pd.Series(df["log_ret"].values[mask]).dropna()
        if len(regime_rets) < 10:
            logger.warning(
                f"[HMM] 政体 '{current_regime}' 样本仅 {len(regime_rets)} 条，"
                "回退到全市场分布估计"
            )
            regime_rets = df["log_ret"].dropna()
            sparse = True
    else:
        regime_rets = df["log_ret"].dropna()
        sparse = True

    # ── 稳健化：剔除 3σ 之外的极端日 ────────────────────────────────────────
    mu_raw  = regime_rets.mean()
    std_raw = regime_rets.std()
    regime_rets_clean = regime_rets[
        (regime_rets >= mu_raw - 3 * std_raw) &
        (regime_rets <= mu_raw + 3 * std_raw)
    ]
    n_clean = len(regime_rets_clean)
    std     = regime_rets_clean.std()

    # ── Bootstrap：模拟多路径累积收益 ───────────────────────────────────────
    rng = np.random.default_rng(seed=42)

    def _bootstrap_quantiles(horizon: int) -> dict:
        sampled  = rng.choice(regime_rets_clean.values,
                              size=(n_sim, horizon), replace=True)
        cum_rets = sampled.sum(axis=1)
        se       = float(std / np.sqrt(n_clean) * np.sqrt(horizon))
        return {
            "p10": round(float(np.percentile(cum_rets, 10)), 6),
            "p50": round(float(np.percentile(cum_rets, 50)), 6),
            "p90": round(float(np.percentile(cum_rets, 90)), 6),
            "se":  round(se, 6),
        }

    q5  = _bootstrap_quantiles(horizon_5)
    q20 = _bootstrap_quantiles(horizon_20)

    # 波动率：政体内日标准差 × √horizon（去掉对 rolling_vol 的依赖）
    vol_20d = round(float(std * np.sqrt(horizon_20)), 6)

    logger.debug(
        f"[HMM] 预测（{current_regime}，样本={n_clean}）"
        f"  5d p50={q5['p50']:+.4f}  20d p50={q20['p50']:+.4f}"
        f"  vol_20d={vol_20d:.4f}"
    )

    return {
        # ── 原接口兼容字段（p50 中位数替代原来的均值外推）───────────────────
        "spy_return_forecast_5d":  q5["p50"],
        "spy_return_forecast_20d": q20["p50"],
        "volatility_forecast_20d": vol_20d,
        # ── 扩展字段（新增，供 Claude 月度报告引用置信区间）────────────────
        "forecast_detail": {
            "5d": {
                "p10": q5["p10"],
                "p50": q5["p50"],
                "p90": q5["p90"],
                "se":  q5["se"],
            },
            "20d": {
                "p10": q20["p10"],
                "p50": q20["p50"],
                "p90": q20["p90"],
                "se":  q20["se"],
            },
            "regime_sample_size": n_clean,
            "used_fallback":      sparse,
        },
    }
