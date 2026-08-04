from __future__ import annotations

from pathlib import Path

import pandas as pd

from activeportfolio.backtest.data_loader import LocalParquetDataLoader


def test_load_symbols_from_sp500_snapshot(tmp_path: Path):
    snapshot_dir = tmp_path / "universe"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame({"symbol": ["AAA", "BBB"]}).to_csv(
        snapshot_dir / "sp500_membership_2024-01-01.csv", index=False
    )
    pd.DataFrame({"symbol": ["CCC", "DDD"]}).to_csv(
        snapshot_dir / "sp500_membership_2025-01-01.csv", index=False
    )

    loader = LocalParquetDataLoader(
        data_root=tmp_path / "market",
        symbol_file=tmp_path / "sp500_symbols.txt",
        universe_snapshot_dir=snapshot_dir,
    )

    syms_2024 = loader.load_symbols(
        universe_source="sp500_snapshot",
        portfolio_universe=[],
        portfolio_universe_size=10,
        benchmark_symbol="SPY",
        fallback_symbol="SPY",
        asof_date="2024-06-01",
    )
    assert syms_2024 == ["SPY", "AAA", "BBB"]

    syms_2025 = loader.load_symbols(
        universe_source="sp500_snapshot",
        portfolio_universe=[],
        portfolio_universe_size=10,
        benchmark_symbol="SPY",
        fallback_symbol="SPY",
        asof_date="2025-06-01",
    )
    assert syms_2025 == ["SPY", "CCC", "DDD"]


def test_pick_parquet_prefers_wider_window_when_end_dates_tie(tmp_path: Path) -> None:
    symbol_dir = tmp_path / "market" / "SPY"
    symbol_dir.mkdir(parents=True, exist_ok=True)
    older_rolling = symbol_dir / "history_2021-07-17_2026-07-17.parquet"
    wider_refresh = symbol_dir / "history_2021-06-27_2026-07-17.parquet"
    pd.DataFrame({"Date": pd.to_datetime(["2026-07-16"]), "Adj Close": [100.0]}).to_parquet(
        older_rolling,
        index=False,
    )
    pd.DataFrame({"Date": pd.to_datetime(["2026-07-17"]), "Adj Close": [101.0]}).to_parquet(
        wider_refresh,
        index=False,
    )

    loader = LocalParquetDataLoader(data_root=tmp_path / "market")
    selected = loader._pick_parquet(
        symbol_dir,
        pd.Timestamp("2025-06-27").to_pydatetime(),
        pd.Timestamp("2026-07-17").to_pydatetime(),
    )

    assert selected == wider_refresh
