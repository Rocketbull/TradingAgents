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
            "fetch_missing_sector_data": False,
            "auto_refresh_sector_cache_on_low_coverage": False,
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
    assert "benchmark_weights" in result["rebalance_log"][0]


def test_backtest_engine_regime_switch_logs_state(tmp_path: Path):
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "backtest_start_date": "2024-01-01",
            "backtest_end_date": "2025-02-28",
            "rebalance_frequency": "weekly",
            "benchmark_symbol": "SPY",
            "backtest_output_dir": str(tmp_path / "run_regime"),
            "max_weight": 0.6,
            "turnover_limit": 0.25,
            "fetch_missing_sector_data": False,
            "auto_refresh_sector_cache_on_low_coverage": False,
            "regime_switch_enabled": True,
            "regime_alpha_profiles": {
                "risk_on": "momentum_heavy",
                "neutral": "conservative",
                "risk_off": "mean_reversion_heavy",
            },
        }
    )
    engine = BacktestEngine(config)
    result = engine.run(close_prices=_close_frame())

    assert result["rebalance_log"], "Expected non-empty rebalance log"
    first = result["rebalance_log"][0]
    assert "regime" in first
    assert first["regime"]["label"] in {"risk_on", "neutral", "risk_off"}
    assert "raw_label" in first["regime"]
    assert "switch_reason" in first["regime"]
    assert "hold_count" in first["regime"]
    assert "regime_profile" in first


def test_regime_stability_blocks_switch_until_min_hold():
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "regime_switch_enabled": True,
            "regime_min_hold_rebalances": 3,
            "regime_switch_confidence_buffer": 0.10,
        }
    )
    engine = BacktestEngine(config)
    raw = {
        "label": "risk_off",
        "probabilities": {"risk_on": 0.05, "neutral": 0.05, "risk_off": 0.90},
    }
    label, switched, reason = engine._apply_regime_stability(
        raw_regime=raw,
        current_label="risk_on",
        current_hold_count=1,
    )
    assert label == "risk_on"
    assert switched is False
    assert reason == "min_hold_block"


def test_liquidity_selector_prefers_high_dollar_volume():
    idx = pd.date_range("2025-01-01", periods=80, freq="D")
    close = pd.DataFrame(
        {
            "AAA": 10.0,
            "BBB": 20.0,
            "CCC": 30.0,
        },
        index=idx,
    )
    vol = pd.DataFrame(
        {
            "AAA": 1_000_000.0,  # highest dollar volume
            "BBB": 100_000.0,
            "CCC": 50_000.0,
        },
        index=idx,
    )
    selected = BacktestEngine._select_liquid_symbols(
        close_history=close,
        volume_history=vol,
        top_n=2,
        lookback_days=60,
        enabled=True,
    )
    assert "AAA" in selected
    assert len(selected) == 2
