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
    source: str = "yfinance",
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
        "source": source,
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


def parse_history_path(path: str | Path) -> tuple[datetime, datetime] | None:
    candidate = Path(path)
    stem = candidate.stem
    if not stem.startswith("history_"):
        return None
    parts = stem.split("_")
    if len(parts) != 3:
        return None
    try:
        return (
            datetime.strptime(parts[1], "%Y-%m-%d"),
            datetime.strptime(parts[2], "%Y-%m-%d"),
        )
    except ValueError:
        return None


def find_history_parquet(
    symbol: str,
    start_date: str,
    end_date: str,
    root_dir: str = "data/market",
) -> Path:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    symbol_dir = Path(root_dir) / symbol.upper()
    if not symbol_dir.exists():
        raise FileNotFoundError(f"Symbol directory not found for {symbol.upper()}: {symbol_dir}")

    candidates: list[tuple[int, datetime, datetime, Path]] = []
    for path in symbol_dir.glob("history_*.parquet"):
        parsed = parse_history_path(path)
        if parsed is None:
            continue
        file_start, file_end = parsed
        covers_range = 1 if (file_start <= start_dt and file_end >= end_dt) else 0
        candidates.append((covers_range, file_end, file_start, path))

    if not candidates:
        raise FileNotFoundError(f"No parquet history found for {symbol.upper()} in {symbol_dir}")

    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return candidates[0][3]


def load_history_window(
    symbol: str,
    start_date: str,
    end_date: str,
    root_dir: str = "data/market",
) -> pd.DataFrame:
    path = find_history_parquet(symbol, start_date, end_date, root_dir=root_dir)
    df = pd.read_parquet(path)
    if "Date" not in df.columns:
        raise ValueError(f"Unexpected schema for {symbol.upper()}: missing Date column")

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    result = df.copy()
    result["Date"] = pd.to_datetime(result["Date"])
    result = result[(result["Date"] >= start_ts) & (result["Date"] < end_ts)]
    if result.empty:
        raise ValueError(f"No rows for {symbol.upper()} in range {start_date}..{end_date}")
    return result.sort_values("Date").reset_index(drop=True)
