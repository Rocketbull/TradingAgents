from __future__ import annotations

from pathlib import Path

import pandas as pd

from activeportfolio.backtest import BacktestEngine
from activeportfolio.default_config import DEFAULT_CONFIG


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


def _close_frame_business_days(start: str, end: str) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
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
    assert "average_transfer_coefficient" in summary
    assert "average_transfer_coefficient_legacy_proxy" in summary
    assert "h1_average_ic" in summary
    assert Path(result["output_dir"]).exists()
    assert (Path(result["output_dir"]) / "equity_curve.csv").exists()
    assert (Path(result["output_dir"]) / "rebalance_log.jsonl").exists()
    assert (Path(result["output_dir"]) / "weights_history.csv").exists()
    assert (Path(result["output_dir"]) / "orders_history.csv").exists()
    assert "alpha_weights" in result["rebalance_log"][0]
    assert "signal_ic" in result["rebalance_log"][0]
    assert "benchmark_weights" in result["rebalance_log"][0]
    assert "unconstrained_active_weights" in result["rebalance_log"][0]
    assert "constrained_active_weights" in result["rebalance_log"][0]
    assert "transfer_coefficient" in result["rebalance_log"][0]["portfolio_metrics"]


def test_backtest_engine_persists_terminal_monthly_rebalance(tmp_path: Path):
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "backtest_start_date": "2024-01-01",
            "backtest_end_date": "2025-05-30",
            "rebalance_frequency": "monthly",
            "benchmark_symbol": "SPY",
            "backtest_output_dir": str(tmp_path / "run_terminal_monthly"),
            "max_weight": 0.6,
            "turnover_limit": 0.25,
            "fetch_missing_sector_data": False,
            "auto_refresh_sector_cache_on_low_coverage": False,
            "alpha_signal_registry": [
                {"type": "momentum", "name": "mom_1m", "window": 5},
            ],
            "alpha_signals": ["mom_1m"],
            "liquidity_top_n": 3,
            "liquidity_lookback_days": 5,
        }
    )
    engine = BacktestEngine(config)
    result = engine.run(close_prices=_close_frame_business_days("2024-01-01", "2025-05-30"))

    equity_curve = result["equity_curve"]
    daily_market_value = result["daily_market_value"]
    commentary_path = Path(result["output_dir"]) / "monthly_commentary.md"
    assert equity_curve.iloc[-1]["trade_date"] == "2025-05-30"
    assert equity_curve.iloc[-1]["next_date"] == "2025-05-30"
    assert int(equity_curve.iloc[-1]["terminal_snapshot"]) == 1
    assert float(equity_curve.iloc[-1]["portfolio_return"]) == 0.0
    assert result["rebalance_log"][-1]["trade_date"] == "2025-05-30"
    assert (Path(result["output_dir"]) / "daily_market_value.csv").exists()
    assert len(daily_market_value) > len(equity_curve)
    assert daily_market_value.iloc[0]["trade_date"] == equity_curve.iloc[0]["trade_date"]
    assert daily_market_value.iloc[-1]["trade_date"] == "2025-05-30"
    assert abs(float(daily_market_value.iloc[-1]["portfolio_value"]) - float(result["summary"]["final_nav"])) < 1e-6
    assert daily_market_value["is_rebalance"].sum() == len(result["rebalance_log"])
    assert commentary_path.exists()
    commentary = commentary_path.read_text(encoding="utf-8")
    assert "# Monthly Rebalance Commentary" in commentary
    assert "### MoM Benchmark Performance" in commentary
    assert "### Portfolio Performance" in commentary
    assert "### Rebalance Decisions" in commentary
    assert "`SPY` returned" in commentary


def test_monthly_rebalance_offset_days_shifts_from_month_end() -> None:
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "rebalance_frequency": "monthly",
            "monthly_rebalance_offset_days": -2,
        }
    )
    engine = BacktestEngine(config)
    idx = pd.bdate_range("2024-01-01", "2024-03-31")
    dates = engine._rebalance_dates(idx)
    assert [d.strftime("%Y-%m-%d") for d in dates] == [
        "2024-01-29",
        "2024-02-27",
        "2024-03-27",
    ]


def test_monthly_rebalance_positive_offset_clamps_within_month() -> None:
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "rebalance_frequency": "monthly",
            "monthly_rebalance_offset_days": 3,
        }
    )
    engine = BacktestEngine(config)
    idx = pd.bdate_range("2024-01-01", "2024-01-31")
    dates = engine._rebalance_dates(idx)
    assert [d.strftime("%Y-%m-%d") for d in dates] == ["2024-01-31"]


def test_backtest_engine_honors_single_alpha_selection(tmp_path: Path):
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "backtest_start_date": "2024-01-01",
            "backtest_end_date": "2025-02-28",
            "rebalance_frequency": "weekly",
            "benchmark_symbol": "SPY",
            "backtest_output_dir": str(tmp_path / "run_single_alpha"),
            "max_weight": 0.6,
            "turnover_limit": 0.25,
            "fetch_missing_sector_data": False,
            "auto_refresh_sector_cache_on_low_coverage": False,
            "alpha_signal_registry": [
                {"type": "momentum", "name": "mom_1m", "window": 21},
                {"type": "reversal", "name": "rev_1w", "window": 5},
            ],
            "alpha_signals": ["mom_1m"],
        }
    )
    engine = BacktestEngine(config)
    result = engine.run(close_prices=_close_frame())

    first = result["rebalance_log"][0]
    assert set(first["alpha_weights"].keys()) == {"mom_1m"}
    assert set(first["signal_ic"].keys()) == {"mom_1m"}


def test_backtest_engine_applies_named_alpha_profile():
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "alpha_profile": "csi300_hybrid_v1",
        }
    )
    engine = BacktestEngine(config)
    assert engine.config["alpha_profile"] == "csi300_hybrid_v1"
    assert engine.alpha_model.available_signals() == [
        "rev_1w",
        "rev_1m",
        "low_vol",
        "downside_vol",
        "mom_1m",
        "mom_3m",
        "vol_adj_mom_3m",
        "vol_confirmed_mom_1m",
        "volume_shock_1w",
    ]


def test_backtest_engine_equal_weight_mode_and_benchmark_hedge(tmp_path: Path):
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "backtest_start_date": "2024-01-01",
            "backtest_end_date": "2025-02-28",
            "rebalance_frequency": "weekly",
            "benchmark_symbol": "SPY",
            "backtest_output_dir": str(tmp_path / "run_equal_weight_hedged"),
            "portfolio_construction_mode": "equal_weight",
            "benchmark_hedge_ratio": 0.5,
            "dynamic_liquidity_filter": False,
            "max_weight": 0.6,
            "turnover_limit": 0.25,
            "fetch_missing_sector_data": False,
            "auto_refresh_sector_cache_on_low_coverage": False,
        }
    )
    engine = BacktestEngine(config)
    result = engine.run(close_prices=_close_frame())

    first = result["rebalance_log"][0]
    assert first["construction_mode"] == "equal_weight"
    assert first["benchmark_hedge_ratio"] == 0.5
    assert first["target_weights"]["AAA"] == 0.5
    assert first["target_weights"]["BBB"] == 0.5


def test_backtest_engine_benchmark_hedge_reduces_period_return(tmp_path: Path):
    base_config = DEFAULT_CONFIG.copy()
    base_config.update(
        {
            "backtest_start_date": "2024-01-01",
            "backtest_end_date": "2025-02-28",
            "rebalance_frequency": "weekly",
            "benchmark_symbol": "SPY",
            "portfolio_construction_mode": "equal_weight",
            "dynamic_liquidity_filter": False,
            "max_weight": 0.6,
            "turnover_limit": 0.25,
            "fetch_missing_sector_data": False,
            "auto_refresh_sector_cache_on_low_coverage": False,
        }
    )
    unhedged = dict(base_config)
    unhedged["backtest_output_dir"] = str(tmp_path / "run_equal_weight_unhedged")
    hedged = dict(base_config)
    hedged["backtest_output_dir"] = str(tmp_path / "run_equal_weight_hedged")
    hedged["benchmark_hedge_ratio"] = 0.5

    unhedged_result = BacktestEngine(unhedged).run(close_prices=_close_frame())
    hedged_result = BacktestEngine(hedged).run(close_prices=_close_frame())

    first_unhedged = unhedged_result["equity_curve"].iloc[0]
    first_hedged = hedged_result["equity_curve"].iloc[0]
    expected_hedged_return = float(first_unhedged["portfolio_return"]) - 0.5 * float(
        first_unhedged["benchmark_return"]
    )
    assert abs(float(first_hedged["portfolio_return"]) - expected_hedged_return) < 1e-12


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


def test_resolve_universe_schedule_rebalances_snapshot_asof():
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "universe_source": "sp500_snapshot",
            "benchmark_symbol": "SPY",
            "portfolio_universe_size": 50,
            "snapshot_schedule_enabled": True,
        }
    )
    engine = BacktestEngine(config)
    dates = [pd.Timestamp("2024-05-31"), pd.Timestamp("2024-06-07")]
    calls: list[str] = []

    def fake_load_symbols(
        universe_source: str,
        portfolio_universe: list[str],
        portfolio_universe_size: int,
        benchmark_symbol: str,
        fallback_symbol: str,
        asof_date: str | None = None,
    ) -> list[str]:
        calls.append(str(asof_date))
        if str(asof_date) < "2024-06-01":
            return ["SPY", "AAA", "BBB"]
        return ["SPY", "CCC", "DDD"]

    engine.data_loader.load_symbols = fake_load_symbols  # type: ignore[method-assign]
    sched = engine._resolve_universe_schedule(dates, fallback_symbol="SPY")
    assert sched[dates[0]] == ["SPY", "AAA", "BBB"]
    assert sched[dates[1]] == ["SPY", "CCC", "DDD"]
    assert calls == ["2024-05-31", "2024-06-07"]


def test_resolve_universe_schedule_snapshot_latest_mode():
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "universe_source": "sp500_snapshot",
            "benchmark_symbol": "SPY",
            "portfolio_universe_size": 50,
            "snapshot_schedule_enabled": False,
        }
    )
    engine = BacktestEngine(config)
    dates = [pd.Timestamp("2024-05-31"), pd.Timestamp("2024-06-07")]
    calls: list[str | None] = []

    def fake_load_symbols(
        universe_source: str,
        portfolio_universe: list[str],
        portfolio_universe_size: int,
        benchmark_symbol: str,
        fallback_symbol: str,
        asof_date: str | None = None,
    ) -> list[str]:
        calls.append(asof_date)
        return ["SPY", "AAA", "BBB"]

    engine.data_loader.load_symbols = fake_load_symbols  # type: ignore[method-assign]
    sched = engine._resolve_universe_schedule(dates, fallback_symbol="SPY")
    assert sched[dates[0]] == ["SPY", "AAA", "BBB"]
    assert sched[dates[1]] == ["SPY", "AAA", "BBB"]
    assert calls == [None]


def test_engine_prefers_legacy_symbol_and_snapshot_paths(tmp_path: Path):
    legacy_symbol_file = tmp_path / "legacy_symbols.txt"
    legacy_symbol_file.write_text("SPY\nAAA\n", encoding="utf-8")
    legacy_snapshot_dir = tmp_path / "legacy_snapshots"
    legacy_snapshot_dir.mkdir(parents=True, exist_ok=True)

    cfg = DEFAULT_CONFIG.copy()
    cfg.update(
        {
            "symbol_file": str(tmp_path / "new_symbols_missing.txt"),
            "universe_snapshot_dir": str(tmp_path / "new_snapshots_missing"),
        }
    )
    engine = BacktestEngine(cfg)
    resolved_symbol = engine._resolve_path_with_legacy(
        Path(cfg["symbol_file"]),
        legacy_path=legacy_symbol_file,
        expect_dir=False,
    )
    resolved_snapshot = engine._resolve_path_with_legacy(
        Path(cfg["universe_snapshot_dir"]),
        legacy_path=legacy_snapshot_dir,
        expect_dir=True,
    )
    assert resolved_symbol == legacy_symbol_file
    assert resolved_snapshot == legacy_snapshot_dir


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
