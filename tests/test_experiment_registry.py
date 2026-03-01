from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.common.experiment_registry import build_registry


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_registry_extracts_rank_and_summary_fields(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "sample_run"
    run.mkdir(parents=True, exist_ok=True)
    summary = run / "summary.csv"
    params = run / "params.json"
    manifest = run / "manifest.json"

    pd.DataFrame(
        [
            {"horizon_days": 1, "realized_active_ir": 0.05, "lift_vs_baseline": 0.01, "factor": "composite"},
            {"horizon_days": 5, "realized_active_ir": 0.22, "lift_vs_baseline": 0.03, "factor": "composite"},
        ]
    ).to_csv(summary, index=False)
    _write_json(
        params,
        {
            "script": "alpha_profile_sp500",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
    )
    _write_json(
        manifest,
        {
            "run_tag": "sample_run",
            "created_at_utc": "2026-03-01T00:00:00+00:00",
            "artifacts": {
                "summary_csv": str(summary),
                "params_json": str(params),
            },
        },
    )

    result = build_registry(tmp_path / "runs")
    assert len(result.registry) == 1
    row = result.registry.iloc[0].to_dict()
    assert row["run_tag"] == "sample_run"
    assert row["script"] == "alpha_profile_sp500"
    assert row["summary_rows"] == 2
    assert row["summary_horizon_days"] == 5
    assert row["summary_realized_active_ir"] == 0.22
    assert row["rank_metric"] == "summary_realized_active_ir"
    assert row["rank_value"] == 0.22
    assert len(result.comparison) == 1


def test_build_registry_handles_nonstandard_manifest_without_summary(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "custom_manifest"
    manifest = run / "manifest.json"
    _write_json(
        manifest,
        {
            "mode": "log",
            "created_at_utc": "20260301T041602Z",
            "log_analysis": {
                "meta": {"rows": 10},
                "csv": "missing.csv",
            },
        },
    )

    result = build_registry(tmp_path / "runs")
    assert len(result.registry) == 1
    row = result.registry.iloc[0].to_dict()
    assert row["run_tag"] == "custom_manifest"
    assert row["has_summary"] is False
    assert pd.isna(row["rank_metric"])
    assert pd.isna(row["rank_value"])
    assert result.comparison.empty


def test_build_registry_prefers_realized_active_information_ratio_for_ranking(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    for tag, ra_ir, sharpe in (
        ("run_a", 0.10, 2.0),
        ("run_b", 0.25, 1.0),
    ):
        run = runs_root / tag
        run.mkdir(parents=True, exist_ok=True)
        summary = run / "summary.csv"
        manifest = run / "manifest.json"
        pd.DataFrame(
            [
                {
                    "realized_active_information_ratio": ra_ir,
                    "sharpe": sharpe,
                }
            ]
        ).to_csv(summary, index=False)
        _write_json(
            manifest,
            {
                "run_tag": tag,
                "created_at_utc": "2026-03-01T00:00:00+00:00",
                "artifacts": {"summary_csv": str(summary)},
            },
        )

    result = build_registry(runs_root)
    assert list(result.comparison["run_tag"]) == ["run_b", "run_a"]


def test_build_registry_sorts_by_metric_priority_before_value(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    # Run A only has lower-priority rank metric.
    run_a = runs_root / "run_a"
    run_a.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"avg_rank_ic": 0.9}]).to_csv(run_a / "summary.csv", index=False)
    _write_json(
        run_a / "manifest.json",
        {"run_tag": "run_a", "artifacts": {"summary_csv": str(run_a / "summary.csv")}},
    )

    # Run B has higher-priority metric even with smaller numeric value.
    run_b = runs_root / "run_b"
    run_b.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"realized_active_ir": 0.1}]).to_csv(run_b / "summary.csv", index=False)
    _write_json(
        run_b / "manifest.json",
        {"run_tag": "run_b", "artifacts": {"summary_csv": str(run_b / "summary.csv")}},
    )

    result = build_registry(runs_root)
    assert list(result.comparison["run_tag"]) == ["run_b", "run_a"]
