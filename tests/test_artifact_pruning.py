from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from research.common.artifact_pruning import find_prune_candidates


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _set_age_days(path: Path, days: float) -> None:
    when = datetime.now(tz=timezone.utc) - timedelta(days=days)
    ts = when.timestamp()
    for child in [path, *path.rglob("*")]:
        child.touch(exist_ok=True)
        os.utime(child, (ts, ts))


def test_find_prune_candidates_respects_decisions_and_manifest_status(tmp_path: Path) -> None:
    eval_root = tmp_path / "eval_results"
    research_output_root = tmp_path / "research" / "output"
    decisions_path = tmp_path / "research" / "configs" / "backtest_decisions.json"

    keep_run = eval_root / "backtest" / "current_baseline" 
    _write_json(keep_run / "summary.json", {"total_return": 1.0})
    _write_json(decisions_path, {"configs": {"current_baseline": {"status": "keep"}}})

    scratch_run = eval_root / "backtest" / "scratch_trial"
    _write_json(scratch_run / "summary.json", {"total_return": 0.5})
    _write_json(scratch_run / "manifest.json", {"status": "scratch", "keep": False})

    bad_pair = eval_root / "backtest" / "ab_pairs" / "20260620T000000Z_bad_pair"
    _write_json(bad_pair / "comparison.json", {"pair_name": "bad_pair"})
    _write_json(bad_pair / "manifest.json", {"status": "bad_test", "keep": False})

    research_run = research_output_root / "obsolete_run"
    _write_json(research_run / "manifest.json", {"status": "obsolete", "keep": False})

    for path in (keep_run, scratch_run, bad_pair, research_run):
        _set_age_days(path, days=30)

    candidates = find_prune_candidates(
        eval_root=eval_root,
        research_output_root=research_output_root,
        decisions_path=decisions_path,
        min_age_days=14,
    )

    paths = {candidate.path.name for candidate in candidates}
    assert "current_baseline" not in paths
    assert "scratch_trial" in paths
    assert "20260620T000000Z_bad_pair" in paths
    assert "obsolete_run" in paths


def test_find_prune_candidates_can_optionally_remove_unknown(tmp_path: Path) -> None:
    eval_root = tmp_path / "eval_results"
    research_output_root = tmp_path / "research" / "output"
    decisions_path = tmp_path / "research" / "configs" / "backtest_decisions.json"
    _write_json(decisions_path, {})

    unknown_run = eval_root / "backtest" / "mystery_variant"
    _write_json(unknown_run / "summary.json", {"total_return": 0.2})
    _set_age_days(unknown_run, days=45)

    without_unknown = find_prune_candidates(
        eval_root=eval_root,
        research_output_root=research_output_root,
        decisions_path=decisions_path,
        min_age_days=14,
        remove_unknown=False,
    )
    assert not without_unknown

    with_unknown = find_prune_candidates(
        eval_root=eval_root,
        research_output_root=research_output_root,
        decisions_path=decisions_path,
        min_age_days=14,
        remove_unknown=True,
    )
    assert [candidate.path.name for candidate in with_unknown] == ["mystery_variant"]
