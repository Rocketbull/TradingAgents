from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import pandas as pd
import yfinance as yf


def download_history(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download OHLCV history from Yahoo Finance for [start_date, end_date)."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    df = yf.download(
        symbol.upper(),
        start=start_date,
        end=end_date,
        progress=False,
        auto_adjust=False,
        multi_level_index=False,
    )

    if df.empty:
        raise ValueError(
            f"No data returned for symbol '{symbol}' in range {start_date}..{end_date}"
        )

    df = df.reset_index()
    if "Date" not in df.columns:
        raise ValueError(f"Unexpected Yahoo Finance schema for symbol '{symbol}'")

    return df


def parquet_path_for_symbol(
    symbol: str, start_date: str, end_date: str, root_dir: str = "data/market"
) -> Path:
    symbol_dir = Path(root_dir) / symbol.upper()
    return symbol_dir / f"history_{start_date}_{end_date}.parquet"


def save_history_parquet(
    df: pd.DataFrame,
    symbol: str,
    start_date: str,
    end_date: str,
    root_dir: str = "data/market",
) -> Path:
    path = parquet_path_for_symbol(symbol, start_date, end_date, root_dir=root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)

    metadata = {
        "symbol": symbol.upper(),
        "start_date": start_date,
        "end_date": end_date,
        "rows": int(df.shape[0]),
        "columns": list(df.columns),
        "saved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yfinance",
    }
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path


def load_history_parquet(
    symbol: str, start_date: str, end_date: str, root_dir: str = "data/market"
) -> pd.DataFrame:
    path = parquet_path_for_symbol(symbol, start_date, end_date, root_dir=root_dir)
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")
    return pd.read_parquet(path)
