from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.monthly_commentary_context import (
    build_monthly_commentary_context,
    default_baseline_family,
    resolve_latest_default_baseline_run,
)


def test_build_monthly_commentary_context_extracts_latest_period(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "benchmark_symbol": "SPY",
        "initial_capital": 1_000_000.0,
        "total_return": 1.25,
        "sharpe": 1.4,
        "max_drawdown": -0.12,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    rows = [
        {
            "trade_date": "2026-03-31",
            "next_date": "2026-04-30",
            "nav_after_costs": 1_050_000.0,
            "nav_after_period": 1_100_000.0,
            "portfolio_return": 0.05,
            "benchmark_return": 0.03,
            "active_return": 0.02,
            "target_weights": {"AAA": 0.40, "BBB": 0.35, "CCC": 0.25},
        },
        {
            "trade_date": "2026-04-30",
            "next_date": "2026-04-30",
            "nav_before": 1_100_000.0,
            "nav_after_costs": 1_099_000.0,
            "cost": 1_000.0,
            "turnover": 0.20,
            "orders_count": 12,
            "target_weights": {"AAA": 0.30, "BBB": 0.20, "CCC": 0.50},
            "alpha_weights": {"mom_3m": 0.50, "mom_1m": 0.30, "mom_6m": 0.20},
            "regime": {"label": "static", "switch_reason": "same_label"},
            "portfolio_metrics": {"realized_information_ratio": 1.1},
        },
    ]
    with open(run_dir / "rebalance_log.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    context = build_monthly_commentary_context(run_dir)

    assert context["analysis_date"] == "2026-04-30"
    assert context["period_start"] == "2026-03-31"
    assert context["period_end"] == "2026-04-30"
    assert context["performance"]["portfolio_return"] == pytest.approx(0.05)
    assert context["performance"]["benchmark_return"] == pytest.approx(0.03)
    assert context["performance"]["active_return"] == pytest.approx(0.02)
    assert context["rebalance"]["orders_count"] == 12
    assert context["rebalance"]["top_adds"][0]["symbol"] == "CCC"
    assert context["rebalance"]["top_trims"][0]["symbol"] == "BBB"
    assert context["rebalance"]["top_holdings_after_rebalance"][0]["symbol"] == "CCC"
    assert context["rebalance"]["signal_emphasis"][0]["symbol"] == "mom_3m"
    assert context["regime"]["title"] == "Static"
    assert "static allocation backdrop" in context["regime"]["summary"]


def test_build_monthly_commentary_context_uses_terminal_row_for_holdings_only(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_terminal"
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "benchmark_symbol": "SPY",
        "initial_capital": 1_000_000.0,
        "total_return": 1.5,
        "sharpe": 1.6,
        "max_drawdown": -0.10,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    rows = [
        {
            "trade_date": "2026-04-30",
            "next_date": "2026-05-29",
            "nav_after_costs": 1_050_000.0,
            "nav_after_period": 1_100_000.0,
            "portfolio_return": 0.08,
            "benchmark_return": 0.03,
            "active_return": 0.05,
            "target_weights": {"AAA": 0.40, "BBB": 0.35, "CCC": 0.25},
        },
        {
            "trade_date": "2026-05-29",
            "next_date": "2026-05-29",
            "nav_before": 1_100_000.0,
            "nav_after_costs": 1_099_000.0,
            "cost": 1_000.0,
            "turnover": 0.25,
            "orders_count": 8,
            "terminal_snapshot": 1,
            "target_weights": {"AAA": 0.20, "BBB": 0.30, "CCC": 0.50},
            "alpha_weights": {"mom_12m": 0.60, "mom_3m": 0.40},
            "regime": {"label": "static", "switch_reason": "same_label"},
            "portfolio_metrics": {"realized_information_ratio": None},
        },
    ]
    with open(run_dir / "rebalance_log.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    context = build_monthly_commentary_context(run_dir)

    assert context["period_start"] == "2026-04-30"
    assert context["period_end"] == "2026-05-29"
    assert context["performance"]["portfolio_return"] == pytest.approx(0.08)
    assert context["performance"]["benchmark_return"] == pytest.approx(0.03)
    assert context["rebalance"]["top_holdings_after_rebalance"][0]["symbol"] == "CCC"


def test_build_monthly_commentary_context_falls_back_to_equity_curve_returns(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_legacy"
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "benchmark_symbol": "SPY",
        "initial_capital": 1_000_000.0,
        "total_return": 1.5,
        "sharpe": 1.6,
        "max_drawdown": -0.10,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    rows = [
        {
            "trade_date": "2026-04-30",
            "next_date": "2026-05-29",
            "nav_after_costs": 1_050_000.0,
            "target_weights": {"AAA": 0.40, "BBB": 0.35, "CCC": 0.25},
        },
        {
            "trade_date": "2026-05-29",
            "next_date": "2026-05-29",
            "nav_before": 1_100_000.0,
            "nav_after_costs": 1_099_000.0,
            "cost": 1_000.0,
            "turnover": 0.25,
            "orders_count": 8,
            "terminal_snapshot": 1,
            "target_weights": {"AAA": 0.20, "BBB": 0.30, "CCC": 0.50},
            "alpha_weights": {"mom_12m": 0.60, "mom_3m": 0.40},
        },
    ]
    with open(run_dir / "rebalance_log.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    (run_dir / "equity_curve.csv").write_text(
        "\n".join(
            [
                "start_date,end_date,portfolio_return,benchmark_return,terminal_snapshot",
                "2026-04-30,2026-05-29,0.1508709432275519,0.05262573224822242,0",
                "2026-05-29,2026-05-29,0.0,0.0,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    context = build_monthly_commentary_context(run_dir)

    assert context["period_start"] == "2026-04-30"
    assert context["period_end"] == "2026-05-29"
    assert context["performance"]["portfolio_return"] == pytest.approx(0.1508709432275519)
    assert context["performance"]["benchmark_return"] == pytest.approx(0.05262573224822242)
    assert context["performance"]["active_return"] == pytest.approx(0.09824521097932948)


def test_resolve_latest_default_baseline_run_prefers_dated_family_snapshot(tmp_path: Path) -> None:
    backtest_root = tmp_path / "backtest"
    backtest_root.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "baseline.json"
    config_path.write_text(
        json.dumps({"backtest_output_dir": "eval_results/backtest/current_baseline"}),
        encoding="utf-8",
    )

    family = default_baseline_family(config_path)
    assert family == "current_baseline"

    runs = {
        "current_baseline": ("2026-05-15", "2026-05-15", True),
        "current_baseline_20260531_terminal": ("2026-05-31", "2026-05-29", False),
        "current_baseline_20260531": ("2026-05-31", "2026-05-29", True),
        "current_baseline_vol_confirmed_swap": ("2026-05-31", "2026-05-29", True),
    }
    for name, (end_date, trade_date, with_daily_market_value) in runs.items():
        run_dir = backtest_root / name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(
            json.dumps({"end_date": end_date, "benchmark_symbol": "SPY", "initial_capital": 1_000_000.0}),
            encoding="utf-8",
        )
        (run_dir / "weights_history.csv").write_text(
            f"trade_date,AAA\n{trade_date},1.0\n",
            encoding="utf-8",
        )
        (run_dir / "rebalance_log.jsonl").write_text(
            json.dumps({"trade_date": trade_date, "next_date": trade_date}) + "\n",
            encoding="utf-8",
        )
        if with_daily_market_value:
            (run_dir / "daily_market_value.csv").write_text(
                "trade_date,portfolio_value\n",
                encoding="utf-8",
            )

    selected = resolve_latest_default_baseline_run(backtest_root, config_path)
    assert selected.name == "current_baseline_20260531"


def test_resolve_latest_default_baseline_run_accepts_refresh_suffixes(tmp_path: Path) -> None:
    backtest_root = tmp_path / "backtest"
    backtest_root.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "baseline.json"
    config_path.write_text(
        json.dumps({"backtest_output_dir": "eval_results/backtest/current_baseline"}),
        encoding="utf-8",
    )

    runs = {
        "current_baseline": ("2026-06-19", "2026-06-19"),
        "current_baseline_2026-06-20_refresh": ("2026-06-20", "2026-06-20"),
        "current_baseline_2026-06-20_full_refresh": ("2026-06-20", "2026-06-20"),
        "current_baseline_vol_confirmed_swap": ("2026-06-20", "2026-06-20"),
    }
    for name, (end_date, trade_date) in runs.items():
        run_dir = backtest_root / name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(
            json.dumps({"end_date": end_date, "benchmark_symbol": "SPY", "initial_capital": 1_000_000.0}),
            encoding="utf-8",
        )
        (run_dir / "weights_history.csv").write_text(
            f"trade_date,AAA\n{trade_date},1.0\n",
            encoding="utf-8",
        )
        (run_dir / "rebalance_log.jsonl").write_text(
            json.dumps({"trade_date": trade_date, "next_date": trade_date}) + "\n",
            encoding="utf-8",
        )
        (run_dir / "daily_market_value.csv").write_text(
            "trade_date,portfolio_value\n",
            encoding="utf-8",
        )

    selected = resolve_latest_default_baseline_run(backtest_root, config_path)
    assert selected.name in {
        "current_baseline_2026-06-20_refresh",
        "current_baseline_2026-06-20_full_refresh",
    }
