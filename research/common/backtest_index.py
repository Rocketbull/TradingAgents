from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


BENEFICIAL_POSITIVE_DELTAS = (
    "total_return",
    "cagr",
    "sharpe",
    "max_drawdown",
    "realized_active_information_ratio",
)
BENEFICIAL_NEGATIVE_DELTAS = ("tracking_error",)


@dataclass
class BacktestIndexBuildResult:
    pair_runs: pd.DataFrame
    latest_pairs: pd.DataFrame
    single_runs: pd.DataFrame
    configs: pd.DataFrame


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return pd.NaT
    return ts


def _coerce_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(out):
        return None
    return out


def _score_pair_deltas(delta: dict[str, Any]) -> int:
    score = 0
    for key in BENEFICIAL_POSITIVE_DELTAS:
        value = _coerce_float(delta.get(key))
        if value is None:
            continue
        if value > 0:
            score += 1
        elif value < 0:
            score -= 1
    for key in BENEFICIAL_NEGATIVE_DELTAS:
        value = _coerce_float(delta.get(key))
        if value is None:
            continue
        if value < 0:
            score += 1
        elif value > 0:
            score -= 1
    return score


def _format_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.3f}"


def _pair_brief_result(labels: dict[str, str], delta: dict[str, Any]) -> tuple[str, str]:
    label_a = str(labels.get("a", "A"))
    label_b = str(labels.get("b", "B"))
    score = _score_pair_deltas(delta)
    if score > 0:
        verdict = f"{label_b} beat {label_a}"
    elif score < 0:
        verdict = f"{label_b} lagged {label_a}"
    else:
        verdict = f"{label_b} mixed vs {label_a}"

    pieces = []
    for key, label in (
        ("total_return", "ret"),
        ("sharpe", "sharpe"),
        ("max_drawdown", "mdd"),
        ("tracking_error", "te"),
    ):
        pieces.append(f"{label} {_format_delta(_coerce_float(delta.get(key)))}")
    return verdict, ", ".join(pieces)


def _read_pair_runs(backtest_root: Path, pair_decisions: dict[str, dict[str, Any]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for comparison_path in sorted((backtest_root / "ab_pairs").rglob("comparison.json")):
        payload = _safe_read_json(comparison_path)
        if not payload:
            continue

        pair_name = str(payload.get("pair_name") or comparison_path.parent.name)
        labels = payload.get("labels")
        if not isinstance(labels, dict):
            labels = {}
        delta = payload.get("delta_b_minus_a")
        if not isinstance(delta, dict):
            delta = {}
        verdict, brief = _pair_brief_result(labels, delta)
        decision = pair_decisions.get(pair_name, {})
        record: dict[str, Any] = {
            "pair_name": pair_name,
            "pair_dir": str(comparison_path.parent),
            "comparison_path": str(comparison_path),
            "created_at_utc": payload.get("created_at_utc"),
            "created_at_ts": _coerce_timestamp(payload.get("created_at_utc")),
            "label_a": labels.get("a"),
            "label_b": labels.get("b"),
            "requested_start": (payload.get("requested_window") or {}).get("start"),
            "requested_end": (payload.get("requested_window") or {}).get("end"),
            "actual_start": (payload.get("actual_window") or {}).get("start"),
            "actual_end": (payload.get("actual_window") or {}).get("end"),
            "decision_status": decision.get("status", "unreviewed"),
            "decision_note": decision.get("note"),
            "outcome_hint": verdict,
            "brief_result": f"{verdict}: {brief}",
        }
        for side in ("a", "b"):
            summary = (payload.get(f"run_{side}") or {}).get("summary")
            if not isinstance(summary, dict):
                summary = {}
            for key, value in summary.items():
                record[f"run_{side}_{key}"] = value
        for key, value in delta.items():
            record[f"delta_{key}"] = value
        records.append(record)

    if not records:
        return pd.DataFrame(
            columns=[
                "pair_name",
                "pair_dir",
                "comparison_path",
                "created_at_utc",
                "created_at_ts",
                "decision_status",
                "decision_note",
                "outcome_hint",
                "brief_result",
            ]
        )
    return pd.DataFrame(records).sort_values(
        ["created_at_ts", "pair_name"], ascending=[False, True]
    ).reset_index(drop=True)


def _read_single_runs(backtest_root: Path) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for summary_path in sorted(backtest_root.glob("*/summary.json")):
        payload = _safe_read_json(summary_path)
        if not payload:
            continue
        run_name = summary_path.parent.name
        record = {
            "run_name": run_name,
            "run_dir": str(summary_path.parent),
            "summary_path": str(summary_path),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "end_date_ts": pd.to_datetime(payload.get("end_date"), errors="coerce"),
            "total_return": payload.get("total_return"),
            "cagr": payload.get("cagr"),
            "sharpe": payload.get("sharpe"),
            "max_drawdown": payload.get("max_drawdown"),
            "tracking_error": payload.get("tracking_error"),
            "realized_active_information_ratio": payload.get("realized_active_information_ratio"),
            "rebalance_points": payload.get("rebalance_points"),
            "final_nav": payload.get("final_nav"),
        }
        records.append(record)
    if not records:
        return pd.DataFrame(
            columns=[
                "run_name",
                "run_dir",
                "summary_path",
                "start_date",
                "end_date",
                "end_date_ts",
            ]
        )
    return pd.DataFrame(records).sort_values(
        ["end_date_ts", "run_name"], ascending=[False, True]
    ).reset_index(drop=True)


def _build_config_catalog(
    config_root: Path,
    single_runs: pd.DataFrame,
    latest_pairs: pd.DataFrame,
    config_decisions: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for config_path in sorted(config_root.rglob("backtest_*.json")):
        if config_path.name == "backtest_decisions.json":
            continue
        payload = _safe_read_json(config_path)
        relative_parent = config_path.relative_to(config_root).parent
        if any(part == "archive" for part in relative_parent.parts):
            continue
        config_key = config_path.stem.removeprefix("backtest_")
        output_dir = str(payload.get("backtest_output_dir") or "")
        canonical_run_name = Path(output_dir).name if output_dir else None
        alpha_signals = payload.get("alpha_signals")
        if isinstance(alpha_signals, list):
            alpha_signals_str = ",".join(str(x) for x in alpha_signals)
        else:
            alpha_signals_str = None

        related_runs = pd.DataFrame()
        if canonical_run_name and not single_runs.empty:
            related_runs = single_runs[
                single_runs["run_name"].eq(canonical_run_name)
                | single_runs["run_name"].str.startswith(f"{canonical_run_name}_", na=False)
            ]
        latest_run = related_runs.iloc[0] if not related_runs.empty else None

        aliases = {config_key}
        if config_key == "current_baseline":
            aliases.add("baseline")
        for prefix in ("current_baseline_", "csi300_"):
            if config_key.startswith(prefix):
                aliases.add(config_key[len(prefix) :])

        related_pairs = pd.DataFrame()
        if not latest_pairs.empty:
            mask = pd.Series(False, index=latest_pairs.index)
            for alias in aliases:
                mask = mask | latest_pairs["pair_name"].str.contains(alias, regex=False, na=False)
            related_pairs = latest_pairs[mask]
        latest_pair = related_pairs.iloc[0] if not related_pairs.empty else None

        decision = config_decisions.get(config_key, {})
        records.append(
            {
                "config_key": config_key,
                "config_path": str(config_path),
                "config_group": "." if str(relative_parent) == "." else str(relative_parent),
                "canonical_run_name": canonical_run_name,
                "decision_status": decision.get("status", "unreviewed"),
                "decision_note": decision.get("note"),
                "backtest_start_date": payload.get("backtest_start_date"),
                "backtest_end_date": payload.get("backtest_end_date"),
                "alpha_signals": alpha_signals_str,
                "latest_run_name": latest_run["run_name"] if latest_run is not None else None,
                "latest_run_end_date": latest_run["end_date"] if latest_run is not None else None,
                "latest_run_total_return": latest_run["total_return"] if latest_run is not None else None,
                "latest_run_sharpe": latest_run["sharpe"] if latest_run is not None else None,
                "latest_pair_name": latest_pair["pair_name"] if latest_pair is not None else None,
                "latest_pair_end_date": latest_pair["actual_end"] if latest_pair is not None else None,
                "latest_pair_brief_result": latest_pair["brief_result"] if latest_pair is not None else None,
            }
        )
    if not records:
        return pd.DataFrame(
            columns=[
                "config_key",
                "config_path",
                "canonical_run_name",
                "decision_status",
                "decision_note",
            ]
        )
    return pd.DataFrame(records).sort_values(
        ["decision_status", "config_key"], ascending=[True, True]
    ).reset_index(drop=True)


def _latest_pair_runs(pair_runs: pd.DataFrame) -> pd.DataFrame:
    if pair_runs.empty:
        return pair_runs.copy()
    latest = pair_runs.sort_values(["created_at_ts"], ascending=[False]).drop_duplicates(
        subset=["pair_name"], keep="first"
    )
    return latest.sort_values(["created_at_ts", "pair_name"], ascending=[False, True]).reset_index(
        drop=True
    )


def render_backtest_index_markdown(result: BacktestIndexBuildResult) -> str:
    lines: list[str] = ["# Backtest Index", ""]

    lines.extend(
        [
            "## Latest Pair Runs",
            "",
            "| Pair | Status | End | Result | Note |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if result.latest_pairs.empty:
        lines.append("| none | - | - | - | - |")
    else:
        for row in result.latest_pairs.itertuples(index=False):
            note = row.decision_note if isinstance(row.decision_note, str) and row.decision_note else ""
            lines.append(
                f"| {row.pair_name} | {row.decision_status} | {row.actual_end or ''} | "
                f"{row.brief_result} | {note} |"
            )

    lines.extend(
        [
            "",
            "## Config Catalog",
            "",
            "| Config | Status | Latest Run End | Latest Pair End | Note |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if result.configs.empty:
        lines.append("| none | - | - | - | - |")
    else:
        for row in result.configs.itertuples(index=False):
            note = row.decision_note if isinstance(row.decision_note, str) and row.decision_note else ""
            lines.append(
                f"| {row.config_key} | {row.decision_status} | {row.latest_run_end_date or ''} | "
                f"{row.latest_pair_end_date or ''} | {note} |"
            )

    return "\n".join(lines) + "\n"


def build_backtest_index(
    backtest_root: Path,
    config_root: Path,
    decisions_path: Path,
) -> BacktestIndexBuildResult:
    decisions = _safe_read_json(decisions_path)
    pair_decisions = decisions.get("pairs")
    if not isinstance(pair_decisions, dict):
        pair_decisions = {}
    config_decisions = decisions.get("configs")
    if not isinstance(config_decisions, dict):
        config_decisions = {}

    pair_runs = _read_pair_runs(backtest_root=backtest_root, pair_decisions=pair_decisions)
    latest_pairs = _latest_pair_runs(pair_runs)
    single_runs = _read_single_runs(backtest_root=backtest_root)
    configs = _build_config_catalog(
        config_root=config_root,
        single_runs=single_runs,
        latest_pairs=latest_pairs,
        config_decisions=config_decisions,
    )
    return BacktestIndexBuildResult(
        pair_runs=pair_runs,
        latest_pairs=latest_pairs,
        single_runs=single_runs,
        configs=configs,
    )
