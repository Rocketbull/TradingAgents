from __future__ import annotations

from pathlib import Path

import pandas as pd

from tradingagents.backtest.data_loader import LocalParquetDataLoader


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
