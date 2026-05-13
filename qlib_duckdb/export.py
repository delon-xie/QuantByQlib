# qlib_duckdb/export.py

import pandas as pd
import duckdb
from pathlib import Path
from .duckdb_connection import connect


def export_freq(reg, freq, out_dir):
    conn = connect(reg)
    df = conn.query(f"""
    SELECT symbol, datetime, open, high, low, close, volume
    FROM feature_{freq}
    ORDER BY symbol, datetime
    """).df()

    pivot = df.pivot(
        index="datetime",
        columns=["open", "high", "low", "close", "volume"],
        values="value"
    )

    out_dir = Path(out_dir) / freq
    out_dir.mkdir(parents=True, exist_ok=True)

    for symbol, g in pivot.groupby(level=0):
        g.to_csv(out_dir / f"{symbol}_{freq}.bin")