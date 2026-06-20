from __future__ import annotations

import json
from pathlib import Path

from research.common.backtest_index import build_backtest_index, render_backtest_index_markdown


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_backtest_index_tracks_latest_pair_and_config_decisions(tmp_path: Path) -> None:
    backtest_root = tmp_path / "eval_results" / "backtest"
    config_root = tmp_path / "research" / "configs"
    decisions_path = config_root / "backtest_decisions.json"

    _write_json(
        backtest_root / "ab_pairs" / "20260613T143642Z_baseline_vs_defensive_sleeve_v2" / "comparison.json",
        {
            "pair_name": "baseline_vs_defensive_sleeve_v2",
            "created_at_utc": "20260613T143642Z",
            "labels": {"a": "baseline", "b": "defensive_sleeve_v2"},
            "actual_window": {"start": "2021-05-23", "end": "2026-04-24"},
            "requested_window": {"start": "2021-05-23", "end": "2026-04-24"},
            "run_a": {"summary": {"total_return": 2.45, "sharpe": 1.58}},
            "run_b": {"summary": {"total_return": 2.47, "sharpe": 1.64}},
            "delta_b_minus_a": {
                "total_return": 0.02,
                "sharpe": 0.06,
                "max_drawdown": 0.002,
                "tracking_error": -0.004,
                "realized_active_information_ratio": 0.05,
            },
        },
    )
    _write_json(
        backtest_root / "ab_pairs" / "20260613T150757Z_baseline_vs_defensive_sleeve_v2" / "comparison.json",
        {
            "pair_name": "baseline_vs_defensive_sleeve_v2",
            "created_at_utc": "20260613T150757Z",
            "labels": {"a": "baseline", "b": "defensive_sleeve_v2"},
            "actual_window": {"start": "2021-05-23", "end": "2026-06-10"},
            "requested_window": {"start": "2021-05-23", "end": "2026-06-10"},
            "run_a": {"summary": {"total_return": 2.81, "sharpe": 1.55}},
            "run_b": {"summary": {"total_return": 2.84, "sharpe": 1.63}},
            "delta_b_minus_a": {
                "total_return": 0.031,
                "sharpe": 0.08,
                "max_drawdown": 0.002,
                "tracking_error": -0.009,
                "realized_active_information_ratio": 0.088,
            },
        },
    )
    _write_json(
        backtest_root / "current_baseline" / "summary.json",
        {
            "start_date": "2021-05-23",
            "end_date": "2026-04-24",
            "total_return": 2.45,
            "sharpe": 1.58,
        },
    )
    _write_json(
        backtest_root / "current_baseline_20260610" / "summary.json",
        {
            "start_date": "2021-05-23",
            "end_date": "2026-06-10",
            "total_return": 2.81,
            "sharpe": 1.55,
        },
    )
    _write_json(
        config_root / "backtest_current_baseline.json",
        {
            "backtest_start_date": "2021-05-23",
            "backtest_end_date": "2026-06-10",
            "backtest_output_dir": "eval_results/backtest/current_baseline",
            "alpha_signals": ["mom_1m", "mom_3m"],
        },
    )
    _write_json(
        config_root / "backtest_current_baseline_defensive_sleeve_v2.json",
        {
            "backtest_start_date": "2021-05-23",
            "backtest_end_date": "2026-06-10",
            "backtest_output_dir": "eval_results/backtest/current_baseline_defensive_sleeve_v2",
            "alpha_signals": ["mom_3m", "low_vol"],
        },
    )
    _write_json(
        decisions_path,
        {
            "configs": {
                "current_baseline": {"status": "keep", "note": "canonical baseline"},
                "current_baseline_defensive_sleeve_v2": {"status": "candidate", "note": "under review"},
            },
            "pairs": {
                "baseline_vs_defensive_sleeve_v2": {"status": "candidate", "note": "latest beats baseline"}
            },
        },
    )

    result = build_backtest_index(backtest_root=backtest_root, config_root=config_root, decisions_path=decisions_path)

    assert len(result.pair_runs) == 2
    assert len(result.latest_pairs) == 1
    latest_pair = result.latest_pairs.iloc[0]
    assert latest_pair["actual_end"] == "2026-06-10"
    assert latest_pair["decision_status"] == "candidate"
    assert "defensive_sleeve_v2 beat baseline" in latest_pair["brief_result"]

    configs = result.configs.set_index("config_key")
    assert configs.loc["current_baseline", "decision_status"] == "keep"
    assert configs.loc["current_baseline", "latest_run_end_date"] == "2026-06-10"
    assert configs.loc["current_baseline_defensive_sleeve_v2", "decision_status"] == "candidate"

    markdown = render_backtest_index_markdown(result)
    assert "baseline_vs_defensive_sleeve_v2" in markdown
    assert "current_baseline_defensive_sleeve_v2" in markdown


def test_build_backtest_index_defaults_to_unreviewed_without_decisions(tmp_path: Path) -> None:
    backtest_root = tmp_path / "eval_results" / "backtest"
    config_root = tmp_path / "research" / "configs"
    decisions_path = config_root / "backtest_decisions.json"

    _write_json(
        backtest_root / "ab_pairs" / "20260613T150757Z_baseline_vs_new_variant" / "comparison.json",
        {
            "pair_name": "baseline_vs_new_variant",
            "created_at_utc": "20260613T150757Z",
            "labels": {"a": "baseline", "b": "new_variant"},
            "actual_window": {"start": "2021-05-23", "end": "2026-06-10"},
            "requested_window": {"start": "2021-05-23", "end": "2026-06-10"},
            "run_a": {"summary": {"total_return": 2.81, "sharpe": 1.55}},
            "run_b": {"summary": {"total_return": 2.70, "sharpe": 1.40}},
            "delta_b_minus_a": {"total_return": -0.11, "sharpe": -0.15, "tracking_error": 0.01},
        },
    )
    _write_json(
        config_root / "backtest_current_baseline_new_variant.json",
        {
            "backtest_start_date": "2021-05-23",
            "backtest_end_date": "2026-06-10",
            "backtest_output_dir": "eval_results/backtest/current_baseline_new_variant",
            "alpha_signals": ["mom_6m"],
        },
    )
    _write_json(decisions_path, {})

    result = build_backtest_index(backtest_root=backtest_root, config_root=config_root, decisions_path=decisions_path)

    assert result.latest_pairs.iloc[0]["decision_status"] == "unreviewed"
    assert "lagged baseline" in result.latest_pairs.iloc[0]["brief_result"]
    assert result.configs.iloc[0]["decision_status"] == "unreviewed"


def test_build_backtest_index_scans_nested_config_dirs(tmp_path: Path) -> None:
    backtest_root = tmp_path / "eval_results" / "backtest"
    config_root = tmp_path / "research" / "configs"
    decisions_path = config_root / "backtest_decisions.json"

    _write_json(
        backtest_root / "current_baseline" / "summary.json",
        {
            "start_date": "2021-05-23",
            "end_date": "2026-06-20",
            "total_return": 3.3,
            "sharpe": 1.68,
        },
    )
    _write_json(
        config_root / "baselines" / "backtest_current_baseline.json",
        {
            "backtest_start_date": "2021-05-23",
            "backtest_end_date": "2026-06-20",
            "backtest_output_dir": "eval_results/backtest/current_baseline",
            "alpha_signals": ["mom_1m", "mom_3m"],
        },
    )
    _write_json(
        config_root / "archive" / "backtest_old_baseline.json",
        {
            "backtest_output_dir": "eval_results/backtest/old_baseline",
        },
    )
    _write_json(decisions_path, {})

    result = build_backtest_index(
        backtest_root=backtest_root,
        config_root=config_root,
        decisions_path=decisions_path,
    )

    assert list(result.configs["config_key"]) == ["current_baseline"]
    assert result.configs.iloc[0]["config_group"] == "baselines"
