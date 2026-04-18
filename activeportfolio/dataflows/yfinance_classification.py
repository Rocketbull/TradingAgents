from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_CLASSIFICATION_CACHE = Path("data/market/metadata/yfinance_classification.csv")


def load_classification_cache(path: Path = DEFAULT_CLASSIFICATION_CACHE) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=["symbol", "sector", "industry", "beta", "source", "downloaded_at_utc"]
        )
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(
            columns=["symbol", "sector", "industry", "beta", "source", "downloaded_at_utc"]
        )
    return df


def save_classification_cache(df: pd.DataFrame, path: Path = DEFAULT_CLASSIFICATION_CACHE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    if "symbol" in out.columns:
        out["symbol"] = out["symbol"].astype(str).str.upper()
    out.to_csv(path, index=False)
    return path


def fetch_symbol_classification(symbol: str) -> dict:
    import yfinance as yf

    ticker = yf.Ticker(symbol.upper())
    info = ticker.info or {}
    return {
        "symbol": symbol.upper(),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "beta": info.get("beta"),
        "source": "yfinance",
        "downloaded_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def update_classification_cache(
    symbols: Iterable[str],
    path: Path = DEFAULT_CLASSIFICATION_CACHE,
    only_missing: bool = True,
) -> pd.DataFrame:
    symbols = [str(s).upper() for s in symbols if str(s).strip()]
    if not symbols:
        return load_classification_cache(path)

    cached = load_classification_cache(path)
    cached_syms = set(cached.get("symbol", pd.Series(dtype=str)).astype(str).str.upper())
    to_fetch = [s for s in symbols if (not only_missing or s not in cached_syms)]

    rows = []
    for symbol in to_fetch:
        try:
            rows.append(fetch_symbol_classification(symbol))
        except Exception:
            rows.append(
                {
                    "symbol": symbol,
                    "sector": None,
                    "industry": None,
                    "beta": None,
                    "source": "yfinance",
                    "downloaded_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )

    if rows:
        fetched = pd.DataFrame(rows)
        merged = pd.concat([cached, fetched], ignore_index=True)
        merged = merged.drop_duplicates(subset=["symbol"], keep="last")
        save_classification_cache(merged, path)
        cached = merged
    return cached


def build_symbol_maps(
    symbols: Iterable[str],
    path: Path = DEFAULT_CLASSIFICATION_CACHE,
    fetch_missing: bool = False,
) -> tuple[dict[str, str], dict[str, float]]:
    symbols = [str(s).upper() for s in symbols if str(s).strip()]
    if fetch_missing:
        df = update_classification_cache(symbols, path=path, only_missing=True)
    else:
        df = load_classification_cache(path)

    subset = df[df["symbol"].astype(str).str.upper().isin(symbols)].copy()
    subset["symbol"] = subset["symbol"].astype(str).str.upper()
    sector_map: dict[str, str] = {}
    beta_map: dict[str, float] = {}
    for _, row in subset.iterrows():
        symbol = str(row["symbol"]).upper()
        sector = row.get("sector")
        beta = row.get("beta")
        if isinstance(sector, str) and sector.strip():
            sector_map[symbol] = sector.strip()
        if beta is not None and pd.notna(beta):
            try:
                beta_map[symbol] = float(beta)
            except Exception:
                pass
    return sector_map, beta_map
