from __future__ import annotations

from pathlib import Path

import pandas as pd

from activeportfolio.dataflows.yfinance_classification import (
    build_symbol_maps,
    load_classification_cache,
    save_classification_cache,
    update_classification_cache,
)


def test_classification_cache_roundtrip(tmp_path: Path):
    path = tmp_path / "classification.csv"
    df = pd.DataFrame(
        [
            {"symbol": "aaa", "sector": "Technology", "industry": "Software", "beta": 1.1, "source": "test", "downloaded_at_utc": "2026-02-28T00:00:00Z"},
            {"symbol": "BBB", "sector": "Utilities", "industry": "Electric", "beta": 0.7, "source": "test", "downloaded_at_utc": "2026-02-28T00:00:00Z"},
        ]
    )
    save_classification_cache(df, path)
    loaded = load_classification_cache(path)
    assert set(loaded["symbol"]) == {"AAA", "BBB"}


def test_build_symbol_maps_from_cache(tmp_path: Path):
    path = tmp_path / "classification.csv"
    df = pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software", "beta": 1.2, "source": "test", "downloaded_at_utc": "2026-02-28T00:00:00Z"},
            {"symbol": "BBB", "sector": "Utilities", "industry": "Electric", "beta": 0.8, "source": "test", "downloaded_at_utc": "2026-02-28T00:00:00Z"},
        ]
    )
    save_classification_cache(df, path)

    sector_map, beta_map = build_symbol_maps(["AAA", "CCC"], path=path, fetch_missing=False)
    assert sector_map == {"AAA": "Technology"}
    assert beta_map == {"AAA": 1.2}


def test_update_classification_cache_no_symbols(tmp_path: Path):
    path = tmp_path / "classification.csv"
    out = update_classification_cache([], path=path)
    assert out.empty
