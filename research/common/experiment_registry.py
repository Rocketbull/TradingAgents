from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


RANK_METRIC_PRIORITY = [
    "summary_realized_active_information_ratio",
    "summary_realized_active_ir",
    "summary_sharpe",
    "summary_implied_ir",
    "summary_lift_vs_baseline",
    "summary_lift_vs_base_rate",
    "summary_signal_hit_rate",
    "summary_hit_rate",
    "summary_avg_rank_ic",
]

SUMMARY_VALUE_COLUMNS = [
    "horizon_days",
    "factor",
    "realized_active_information_ratio",
    "realized_active_ir",
    "sharpe",
    "implied_ir",
    "lift_vs_baseline",
    "lift_vs_base_rate",
    "signal_hit_rate",
    "hit_rate",
    "avg_rank_ic",
    "ic_ir",
    "signal_coverage",
    "sample_points",
    "signal_points",
    "total_return",
    "max_drawdown",
    "tracking_error",
]

SUMMARY_SELECT_PRIORITY = [
    "realized_active_information_ratio",
    "realized_active_ir",
    "sharpe",
    "implied_ir",
    "lift_vs_baseline",
    "lift_vs_base_rate",
    "signal_hit_rate",
    "hit_rate",
    "avg_rank_ic",
]


@dataclass
class RegistryBuildResult:
    registry: pd.DataFrame
    comparison: pd.DataFrame


def find_manifest_paths(runs_root: Path) -> list[Path]:
    return sorted(p for p in runs_root.rglob("manifest.json") if p.is_file())


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_artifact_path(path_value: Any, manifest_path: Path) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    raw = Path(path_value)
    if raw.is_absolute():
        return raw if raw.exists() else None
    # Most manifests store paths relative to repo root; keep a fallback relative to manifest dir.
    repo_relative = Path(path_value)
    if repo_relative.exists():
        return repo_relative
    from_manifest = manifest_path.parent / path_value
    if from_manifest.exists():
        return from_manifest
    return None


def _summary_from_manifest(manifest: dict[str, Any], manifest_path: Path) -> Path | None:
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict):
        for key in ("summary_csv", "csv", "summary_json"):
            p = _resolve_artifact_path(artifacts.get(key), manifest_path)
            if p is not None:
                return p

    for section_key in ("single_signal_sweep", "log_analysis"):
        section = manifest.get(section_key)
        if isinstance(section, dict):
            p = _resolve_artifact_path(section.get("csv"), manifest_path)
            if p is not None:
                return p
    return None


def _params_from_manifest(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return {}
    params_path = _resolve_artifact_path(artifacts.get("params_json"), manifest_path)
    if params_path is None:
        return {}
    return _safe_read_json(params_path)


def _pick_summary_row(df: pd.DataFrame) -> tuple[pd.Series | None, str | None]:
    if df.empty:
        return None, None
    work = df.copy()
    if "factor" in work.columns and (work["factor"] == "composite").any():
        work = work[work["factor"] == "composite"].copy()
    if "horizon_days" in work.columns and (work["horizon_days"] == 5).any():
        work = work[work["horizon_days"] == 5].copy()

    for col in SUMMARY_SELECT_PRIORITY:
        if col not in work.columns:
            continue
        series = pd.to_numeric(work[col], errors="coerce")
        if series.notna().any():
            idx = series.idxmax()
            return work.loc[idx], col

    return work.iloc[0], None


def _extract_summary_fields(df: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {
        "summary_rows": int(len(df)),
        "summary_cols": int(len(df.columns)),
    }
    row, metric = _pick_summary_row(df)
    out["summary_selection_metric"] = metric
    if row is None:
        return out
    for col in SUMMARY_VALUE_COLUMNS:
        if col in row.index:
            value = row[col]
            if pd.isna(value):
                out[f"summary_{col}"] = None
            else:
                out[f"summary_{col}"] = value.item() if hasattr(value, "item") else value
    return out


def _rank_info(record: dict[str, Any]) -> tuple[str | None, float | None]:
    for metric in RANK_METRIC_PRIORITY:
        value = record.get(metric)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if pd.isna(parsed):
            continue
        return metric, parsed
    return None, None


def build_registry(runs_root: Path) -> RegistryBuildResult:
    records: list[dict[str, Any]] = []
    for manifest_path in find_manifest_paths(runs_root):
        manifest = _safe_read_json(manifest_path)
        params = _params_from_manifest(manifest, manifest_path)

        run_tag = manifest.get("run_tag")
        if not isinstance(run_tag, str) or not run_tag.strip():
            run_tag = manifest_path.parent.name

        record: dict[str, Any] = {
            "run_tag": run_tag,
            "manifest_path": str(manifest_path),
            "run_dir": str(manifest_path.parent),
            "created_at_utc": manifest.get("created_at_utc"),
            "command": manifest.get("command"),
            "git_head": manifest.get("git_head"),
            "config_json": manifest.get("config_json"),
            "mode": manifest.get("mode"),
            "script": params.get("script"),
            "start_date": params.get("start_date"),
            "end_date": params.get("end_date"),
        }

        summary_path = _summary_from_manifest(manifest, manifest_path)
        record["summary_path"] = str(summary_path) if summary_path is not None else None
        record["has_summary"] = bool(summary_path and summary_path.exists())

        if summary_path is not None and summary_path.exists():
            try:
                if summary_path.suffix.lower() == ".json":
                    payload = _safe_read_json(summary_path)
                    summary_df = pd.DataFrame([payload]) if payload else pd.DataFrame()
                else:
                    summary_df = pd.read_csv(summary_path)
                record.update(_extract_summary_fields(summary_df))
            except Exception as exc:
                record["summary_error"] = str(exc)

        rank_metric, rank_value = _rank_info(record)
        record["rank_metric"] = rank_metric
        record["rank_value"] = rank_value
        record["rank_priority"] = (
            RANK_METRIC_PRIORITY.index(rank_metric)
            if isinstance(rank_metric, str) and rank_metric in RANK_METRIC_PRIORITY
            else len(RANK_METRIC_PRIORITY)
        )
        records.append(record)

    registry = pd.DataFrame(records).sort_values(["created_at_utc", "run_tag"], ascending=[False, True])
    comparison = (
        registry[registry["rank_value"].notna()]
        .sort_values(["rank_priority", "rank_value"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return RegistryBuildResult(registry=registry, comparison=comparison)
