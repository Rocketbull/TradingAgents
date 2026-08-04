from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from research.common.backtest_viewer import build_viewer_context, collect_runs


def _write_run(
    run_dir: Path,
    *,
    start_date: str,
    end_date: str,
    trade_date: str,
    mtime: int,
    daily_market_value: bool = True,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"start_date": start_date, "end_date": end_date, "total_return": 0.1}),
        encoding="utf-8",
    )
    (run_dir / "equity_curve.csv").write_text(
        "\n".join(
            [
                "trade_date,portfolio_value,benchmark_value,cost",
                f"{trade_date},110.0,105.0,0.1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "weights_history.csv").write_text(
        "trade_date,AAA\n" f"{trade_date},1.0\n",
        encoding="utf-8",
    )
    (run_dir / "orders_history.csv").write_text(
        "trade_date,symbol,quantity\n" f"{trade_date},AAA,1\n",
        encoding="utf-8",
    )
    (run_dir / "rebalance_log.jsonl").write_text(
        json.dumps({"trade_date": trade_date, "target_weights": {"AAA": 1.0}}) + "\n",
        encoding="utf-8",
    )
    if daily_market_value:
        (run_dir / "daily_market_value.csv").write_text(
            "trade_date,portfolio_value\n" f"{trade_date},110.0\n",
            encoding="utf-8",
        )
    for path in run_dir.iterdir():
        os.utime(path, (mtime, mtime))


def _write_repo_config(repo_root: Path) -> None:
    config_dir = repo_root / "research/configs/baselines"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "backtest_current_baseline.json").write_text(
        json.dumps({"backtest_output_dir": "eval_results/backtest/current_baseline"}),
        encoding="utf-8",
    )


def test_collect_runs_orders_by_completion_time(tmp_path: Path) -> None:
    backtest_root = tmp_path / "eval_results/backtest"
    _write_run(
        backtest_root / "older",
        start_date="2021-01-01",
        end_date="2026-06-01",
        trade_date="2026-05-29",
        mtime=100,
    )
    _write_run(
        backtest_root / "newer",
        start_date="2021-01-01",
        end_date="2026-07-17",
        trade_date="2026-06-30",
        mtime=200,
    )

    runs = collect_runs(backtest_root)

    assert [Path(run["run_dir"]).name for run in runs[:2]] == ["newer", "older"]
    assert runs[0]["latest_trade_date"] == pd.Timestamp("2026-06-30")
    assert runs[0]["has_daily_market_value"] is True


def test_build_viewer_context_selects_latest_run_or_baseline(tmp_path: Path) -> None:
    _write_repo_config(tmp_path)
    backtest_root = tmp_path / "eval_results/backtest"
    _write_run(
        backtest_root / "current_baseline",
        start_date="2021-05-23",
        end_date="2026-07-17",
        trade_date="2026-06-30",
        mtime=100,
    )
    _write_run(
        backtest_root / "scratch_experiment",
        start_date="2021-05-23",
        end_date="2026-07-17",
        trade_date="2026-06-30",
        mtime=200,
    )

    dev_context = build_viewer_context(run_selection_mode="latest_run", repo_root=tmp_path)
    baseline_context = build_viewer_context(
        run_selection_mode="current_baseline_family",
        repo_root=tmp_path,
    )

    assert dev_context.default_run_dir.name == "scratch_experiment"
    assert baseline_context.default_run_dir.name == "current_baseline"
    assert baseline_context.artifacts.summary["end_date"] == "2026-07-17"
    assert list(baseline_context.artifacts.equity_curve["trade_date"]) == [
        pd.Timestamp("2026-06-30")
    ]
