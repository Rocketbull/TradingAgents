from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.run_backtest import build_config, build_run_manifest, load_config_json


def test_load_config_json_requires_object(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('["not", "an", "object"]', encoding="utf-8")
    try:
        load_config_json(str(path))
    except ValueError as exc:
        assert "Config JSON must be an object" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-object config JSON")


def test_build_config_uses_config_json_defaults(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "backtest_start_date": "2021-05-23",
                "backtest_end_date": "2026-02-28",
                "rebalance_frequency": "monthly",
                "portfolio_universe_size": 500,
                "dynamic_liquidity_filter": True,
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        config_json=str(path),
        start_date=None,
        end_date=None,
        rebalance_frequency=None,
        universe_source=None,
        universe_size=None,
        symbol_file=None,
        snapshot_dir=None,
        benchmark_symbol=None,
        max_weight=None,
        turnover_limit=None,
        risk_aversion=None,
        transaction_cost_bps=None,
        out_dir=None,
        alpha_signal=[],
        dynamic_liquidity_filter=None,
        liquidity_top_n=None,
        liquidity_lookback_days=None,
        monthly_rebalance_offset_days=None,
    )

    config = build_config(args)
    assert config["portfolio_mode"] is True
    assert config["backtest_start_date"] == "2021-05-23"
    assert config["backtest_end_date"] == "2026-02-28"
    assert config["rebalance_frequency"] == "monthly"
    assert config["portfolio_universe_size"] == 500
    assert config["dynamic_liquidity_filter"] is True
    assert config["monthly_rebalance_offset_days"] == 0


def test_build_config_cli_overrides_json(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "backtest_start_date": "2021-05-23",
                "backtest_end_date": "2026-02-28",
                "max_weight": 0.08,
                "alpha_signals": ["mom_3m", "mom_6m"],
                "dynamic_liquidity_filter": True,
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        config_json=str(path),
        start_date="2022-01-01",
        end_date=None,
        rebalance_frequency=None,
        universe_source=None,
        universe_size=None,
        symbol_file=None,
        snapshot_dir=None,
        benchmark_symbol="spy",
        max_weight=0.06,
        turnover_limit=None,
        risk_aversion=None,
        transaction_cost_bps=None,
        out_dir="eval_results/backtest/test_override",
        alpha_signal=["breakout_52w"],
        dynamic_liquidity_filter=False,
        liquidity_top_n=None,
        liquidity_lookback_days=None,
        monthly_rebalance_offset_days=-2,
    )

    config = build_config(args)
    assert config["backtest_start_date"] == "2022-01-01"
    assert config["backtest_end_date"] == "2026-02-28"
    assert config["max_weight"] == 0.06
    assert config["benchmark_symbol"] == "SPY"
    assert config["backtest_output_dir"] == "eval_results/backtest/test_override"
    assert config["alpha_signals"] == ["breakout_52w"]
    assert config["dynamic_liquidity_filter"] is False
    assert config["monthly_rebalance_offset_days"] == -2


def test_build_run_manifest_captures_lifecycle_and_artifacts(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_results" / "backtest" / "sample_run"
    out_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "backtest_start_date": "2021-05-23",
        "backtest_end_date": "2026-06-20",
        "benchmark_symbol": "SPY",
    }
    summary = {
        "total_return": 1.23,
        "sharpe": 1.11,
        "rebalance_points": 42,
        "final_nav": 1234567.0,
    }

    manifest = build_run_manifest(
        out_dir=out_dir,
        config=config,
        config_json="research/configs/backtest_current_baseline.json",
        summary=summary,
        run_status="candidate",
        keep_run=True,
    )

    assert manifest["mode"] == "backtest"
    assert manifest["run_name"] == "sample_run"
    assert manifest["status"] == "candidate"
    assert manifest["keep"] is True
    assert manifest["config_json"] == "research/configs/backtest_current_baseline.json"
    assert manifest["start_date"] == "2021-05-23"
    assert manifest["end_date"] == "2026-06-20"
    assert manifest["artifacts"]["summary_json"].endswith("summary.json")
    assert manifest["summary"]["total_return"] == 1.23
