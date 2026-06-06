from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd


def _resolve_existing_path(*candidates: str) -> Path | None:
    for raw in candidates:
        path = Path(raw)
        if path.exists():
            return path
    return None


@lru_cache(maxsize=1)
def load_symbol_name_table() -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    csi300_path = _resolve_existing_path(
        "data/universe/csi300/current/csi300_weights.csv",
        "../data/universe/csi300/current/csi300_weights.csv",
    )
    if csi300_path is not None:
        csi300 = pd.read_csv(csi300_path)
        required = {"symbol", "constituent_name", "constituent_name_eng"}
        if required.issubset(csi300.columns):
            subset = csi300.loc[:, ["symbol", "constituent_name", "constituent_name_eng"]].copy()
            subset["symbol"] = subset["symbol"].astype(str).str.upper()
            subset["stock_name"] = subset["constituent_name"].astype(str).str.strip()
            subset["stock_name_eng"] = subset["constituent_name_eng"].astype(str).str.strip()
            subset["source"] = "csi300_weights"
            rows.extend(
                subset.loc[:, ["symbol", "stock_name", "stock_name_eng", "source"]]
                .to_dict(orient="records")
            )

    table = pd.DataFrame(rows)
    if table.empty:
        return pd.DataFrame(columns=["symbol", "stock_name", "stock_name_eng", "source"])

    table = table.drop_duplicates(subset=["symbol"], keep="first").reset_index(drop=True)
    return table


def map_symbols_to_stock_names(
    symbols: Iterable[str],
    *,
    prefer_english: bool = False,
    fallback_to_symbol: bool = True,
) -> dict[str, str]:
    table = load_symbol_name_table()
    key_col = "stock_name_eng" if prefer_english else "stock_name"
    lookup = {
        str(row["symbol"]).upper(): str(row[key_col]).strip()
        for _, row in table.iterrows()
        if str(row.get(key_col, "")).strip()
    }

    result: dict[str, str] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol).upper()
        name = lookup.get(symbol)
        if name:
            result[symbol] = name
        elif fallback_to_symbol:
            result[symbol] = symbol
    return result


def get_stock_name(
    symbol: str,
    *,
    prefer_english: bool = False,
    fallback_to_symbol: bool = True,
) -> str | None:
    mapped = map_symbols_to_stock_names(
        [symbol],
        prefer_english=prefer_english,
        fallback_to_symbol=fallback_to_symbol,
    )
    return mapped.get(str(symbol).upper())
