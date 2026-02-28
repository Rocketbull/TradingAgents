from __future__ import annotations

from pathlib import Path

import pandas as pd

from tradingagents.backtest import BacktestEngine
from tradingagents.default_config import DEFAULT_CONFIG


def _close_frame() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=420, freq="D")
    n = len(idx)
    return pd.DataFrame(
        {
            "AAA": pd.Series(range(100, 100 + n), index=idx, dtype=float),
            "BBB": pd.Series(range(120, 120 + n), index=idx, dtype=float),
            "SPY": pd.Series(range(110, 110 + n), index=idx, dtype=float),
        }
    )


def test_backtest_engine_run_with_injected_prices(tmp_path: Path):
    config = DEFAULT_CONFIG.copy()
    config.update(
            {
            "backtest_start_date": "2024-01-01",
            "backtest_end_date": "2025-02-28",
            "rebalance_frequency": "weekly",
            "benchmark_symbol": "SPY",
            "backtest_output_dir": str(tmp_path / "run"),
            "max_weight": 0.6,
            "turnover_limit": 0.25,
        }
    )
    engine = BacktestEngine(config)
    result = engine.run(close_prices=_close_frame())

    summary = result["summary"]
    assert summary["rebalance_points"] > 1
    assert "total_return" in summary
    assert "implied_information_ratio" in summary
    assert "realized_active_information_ratio" in summary
    assert "average_raw_turnover" in summary
    assert "h1_average_ic" in summary
    assert Path(result["output_dir"]).exists()
    assert (Path(result["output_dir"]) / "equity_curve.csv").exists()
    assert (Path(result["output_dir"]) / "rebalance_log.jsonl").exists()
    assert (Path(result["output_dir"]) / "weights_history.csv").exists()
    assert (Path(result["output_dir"]) / "orders_history.csv").exists()
    assert "alpha_weights" in result["rebalance_log"][0]
    assert "signal_ic" in result["rebalance_log"][0]
