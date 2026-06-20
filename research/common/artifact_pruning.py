from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRUNE_STATUSES = {"scratch", "bad_test", "rejected", "superseded", "obsolete"}
KEEP_STATUSES = {"keep", "active", "candidate"}


@dataclass
class ArtifactCandidate:
    path: Path
    kind: str
    status: str
    keep: bool
    age_days: float
    reason: str


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_mtime(path: Path) -> float:
    if path.is_file():
        return path.stat().st_mtime
    latest = path.stat().st_mtime
    for child in path.rglob("*"):
        try:
            latest = max(latest, child.stat().st_mtime)
        except FileNotFoundError:
            continue
    return latest


def _age_days(path: Path, now: datetime) -> float:
    modified = datetime.fromtimestamp(_latest_mtime(path), tz=timezone.utc)
    return (now - modified).total_seconds() / 86400.0


def _single_run_name(path: Path) -> str:
    return path.name


def _matching_config_key(
    run_name: str, config_decisions: dict[str, dict[str, Any]]
) -> str | None:
    matches = [key for key in config_decisions if run_name == key or run_name.startswith(f"{key}_")]
    if not matches:
        return None
    return max(matches, key=len)


def _status_from_manifest(manifest: dict[str, Any]) -> tuple[str, bool]:
    status = str(manifest.get("status") or "unknown").strip().lower() or "unknown"
    keep = bool(manifest.get("keep", False))
    return status, keep


def classify_backtest_run(
    run_dir: Path,
    *,
    now: datetime,
    config_decisions: dict[str, dict[str, Any]] | None = None,
) -> ArtifactCandidate | None:
    if not run_dir.is_dir() or not (run_dir / "summary.json").exists():
        return None
    manifest = _read_json_dict(run_dir / "manifest.json")
    status, keep = _status_from_manifest(manifest)
    reason = "manifest"

    if status == "unknown":
        config_key = _matching_config_key(_single_run_name(run_dir), config_decisions or {})
        if config_key:
            decision = (config_decisions or {}).get(config_key, {})
            decision_status = str(decision.get("status") or "").strip().lower()
            if decision_status:
                status = decision_status
                keep = keep or status in KEEP_STATUSES
                reason = f"config_decision:{config_key}"

    return ArtifactCandidate(
        path=run_dir,
        kind="backtest_run",
        status=status,
        keep=keep,
        age_days=_age_days(run_dir, now),
        reason=reason,
    )


def classify_pair_run(
    pair_dir: Path,
    *,
    now: datetime,
    pair_decisions: dict[str, dict[str, Any]] | None = None,
) -> ArtifactCandidate | None:
    if not pair_dir.is_dir() or not (pair_dir / "comparison.json").exists():
        return None
    manifest = _read_json_dict(pair_dir / "manifest.json")
    comparison = _read_json_dict(pair_dir / "comparison.json")
    status, keep = _status_from_manifest(manifest)
    reason = "manifest"

    if status == "unknown":
        pair_name = str(comparison.get("pair_name") or pair_dir.name)
        decision = (pair_decisions or {}).get(pair_name, {})
        decision_status = str(decision.get("status") or "").strip().lower()
        if decision_status:
            status = decision_status
            keep = keep or status in KEEP_STATUSES
            reason = f"pair_decision:{pair_name}"

    return ArtifactCandidate(
        path=pair_dir,
        kind="backtest_pair",
        status=status,
        keep=keep,
        age_days=_age_days(pair_dir, now),
        reason=reason,
    )


def classify_research_output(run_dir: Path, *, now: datetime) -> ArtifactCandidate | None:
    if not run_dir.is_dir() or not (run_dir / "manifest.json").exists():
        return None
    manifest = _read_json_dict(run_dir / "manifest.json")
    status, keep = _status_from_manifest(manifest)
    return ArtifactCandidate(
        path=run_dir,
        kind="research_output",
        status=status,
        keep=keep,
        age_days=_age_days(run_dir, now),
        reason="manifest",
    )


def load_decisions(decisions_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = _read_json_dict(decisions_path)
    configs = payload.get("configs")
    pairs = payload.get("pairs")
    return (
        configs if isinstance(configs, dict) else {},
        pairs if isinstance(pairs, dict) else {},
    )


def find_prune_candidates(
    *,
    eval_root: Path,
    research_output_root: Path,
    decisions_path: Path,
    min_age_days: float,
    remove_unknown: bool = False,
    now: datetime | None = None,
) -> list[ArtifactCandidate]:
    current_time = now or datetime.now(tz=timezone.utc)
    config_decisions, pair_decisions = load_decisions(decisions_path)
    candidates: list[ArtifactCandidate] = []

    backtest_root = eval_root / "backtest"
    for run_dir in sorted(backtest_root.iterdir()) if backtest_root.exists() else []:
        if run_dir.name == "ab_pairs":
            continue
        candidate = classify_backtest_run(
            run_dir, now=current_time, config_decisions=config_decisions
        )
        if candidate is None:
            continue
        if candidate.keep or candidate.age_days < min_age_days:
            continue
        if candidate.status in PRUNE_STATUSES or (remove_unknown and candidate.status == "unknown"):
            candidates.append(candidate)

    pairs_root = backtest_root / "ab_pairs"
    for pair_dir in sorted(pairs_root.iterdir()) if pairs_root.exists() else []:
        candidate = classify_pair_run(pair_dir, now=current_time, pair_decisions=pair_decisions)
        if candidate is None:
            continue
        if candidate.keep or candidate.age_days < min_age_days:
            continue
        if candidate.status in PRUNE_STATUSES or (remove_unknown and candidate.status == "unknown"):
            candidates.append(candidate)

    for manifest_path in sorted(research_output_root.rglob("manifest.json")) if research_output_root.exists() else []:
        run_dir = manifest_path.parent
        candidate = classify_research_output(run_dir, now=current_time)
        if candidate is None:
            continue
        if candidate.keep or candidate.age_days < min_age_days:
            continue
        if candidate.status in PRUNE_STATUSES or (remove_unknown and candidate.status == "unknown"):
            candidates.append(candidate)

    return sorted(candidates, key=lambda item: (item.kind, item.path.as_posix()))
