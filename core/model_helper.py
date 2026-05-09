import multiprocessing as mp
mp.set_start_method("spawn", force=True)
import os
os.environ["JOBLIB_MULTIPROCESSING"] = "0"

import joblib
import os

joblib.parallel_backend("threading", n_jobs=1)

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["JOBLIB_MULTIPROCESSING"] = "0"

#import mlflow
#mlflow.set_tracking_uri("duckdb:////mlflow.duckdb")

# ✅ 提前 import，避免 fork 后再 import
from qlib.contrib.model.gbdt import LGBModel
from qlib.contrib.model.pytorch_lstm import LSTM
from qlib.contrib.model.pytorch_gru import GRU

MODEL_REGISTRY = {
    "growth_stocks": lambda: LGBModel(
        loss="mse",
        colsample_bytree=0.8879,
        learning_rate=0.0421,
        subsample=0.8789,
        lambda_l1=205.6999,
        lambda_l2=580.9768,
        max_depth=8,
        num_leaves=210,
        num_threads=1,
        force_col_wise=True,
    ),
    "market_adaptive_bull": lambda: LGBModel(
        learning_rate=0.05,
        num_leaves=128,
        num_threads=1,
        force_col_wise=True,
    ),
    "market_adaptive_bear": lambda: LGBModel(
        learning_rate=0.03,
        num_leaves=128,
        num_threads=1,
        force_col_wise=True,
    ),
    "market_adaptive": lambda: LGBModel(
        learning_rate=0.03,
        num_leaves=128,
        num_threads=1,
        force_col_wise=True,
    ),
    "deep_learning": lambda: LSTM(
        d_feat=158,
        hidden_size=64,
        num_layers=2,
        dropout=0.0,
        n_epochs=10,
        lr=1e-3,
        early_stop=10,
        batch_size=256,
        metric="",
        GPU=-1,
    ),
    "intraday_profit": lambda: GRU(
        d_feat=158,
        hidden_size=64,
        num_layers=2,
        dropout=0.0,
        n_epochs=10,
        lr=1e-3,
        early_stop=10,
        batch_size=256,
        metric="",
        GPU=-1,
    ),
    "pytorch_full_market": lambda: LSTM(
        d_feat=360,
        hidden_size=128,
        num_layers=2,
        dropout=0.1,
        n_epochs=8,
        lr=5e-4,
        early_stop=8,
        batch_size=256,
        metric="",
        GPU=-1,
    ),
}

def get_model(key: str):
    factory = MODEL_REGISTRY.get(key)
    if factory is None:
        factory = lambda: LGBModel(num_leaves=64, num_threads=1)
    return factory()