from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run demo workflows for hypothesis analysis and threshold sweep research scripts."
    )
    p.add_argument("--start-date", default="2024-01-01", help="Start date YYYY-MM-DD.")
    p.add_argument("--end-date", default="2025-12-31", help="End date YYYY-MM-DD.")
    p.add_argument("--spy-symbol", default="SPY", help="Index symbol for hypothesis checks.")
    p.add_argument("--lead-symbol", default="TSLA", help="Lead symbol for hypothesis checks.")
    p.add_argument("--data-dir", default="data/market", help="Parquet root directory.")
    p.add_argument("--output-dir", default="research/output", help="Root output directory.")
    p.add_argument("--config-json", default=None, help="Optional config JSON path recorded in manifests.")
    p.add_argument(
        "--run-tag-prefix",
        default="demo_hypothesis_threshold",
        help="Prefix used for generated run tags.",
    )
    p.add_argument(
        "--spy-threshold-pct",
        type=float,
        default=-0.25,
        help="Hypothesis condition: SPY daily return <= this percent.",
    )
    p.add_argument(
        "--lead-threshold-pct",
        type=float,
        default=1.5,
        help="Hypothesis condition: lead symbol daily return > this percent.",
    )
    p.add_argument(
        "--next-spy-drop-pct",
        type=float,
        default=-1.0,
        help="Hypothesis outcome: next-day SPY return < this percent.",
    )
    p.add_argument(
        "--spy-thresholds-pct",
        default="-0.50,-0.25,0.00",
        help="Sweep values for SPY signal threshold (percent list).",
    )
    p.add_argument(
        "--lead-thresholds-pct",
        default="0.50,1.00,1.50",
        help="Sweep values for lead signal threshold (percent list).",
    )
    p.add_argument(
        "--next-spy-drop-thresholds-pct",
        default="-1.50,-1.00,-0.50",
        help="Sweep values for next-day SPY drop threshold (percent list).",
    )
    p.add_argument(
        "--min-signal-days",
        type=int,
        default=20,
        help="Minimum signal days retained in threshold sweep rows.",
    )
    p.add_argument(
        "--build-registry",
        action="store_true",
        help="Also rebuild cross-run registry/comparison tables after demo runs.",
    )
    p.add_argument(
        "--no-auto-resolve-date-range",
        action="store_true",
        help="Disable automatic fallback to latest common history_<start>_<end>.parquet pair.",
    )
    return p.parse_args()


def _maybe_add_config(cmd: list[str], config_json: str | None) -> list[str]:
    if config_json:
        cmd.extend(["--config-json", config_json])
    return cmd


def _run(cmd: list[str]) -> None:
    print(f"[run] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _parse_history_range(path: Path) -> tuple[str, str] | None:
    stem = path.stem
    prefix = "history_"
    if not stem.startswith(prefix):
        return None
    payload = stem[len(prefix) :]
    parts = payload.split("_")
    if len(parts) != 2:
        return None
    start, end = parts
    try:
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        return None
    return start, end


def _available_ranges(data_dir: Path, symbol: str) -> set[tuple[str, str]]:
    root = data_dir / symbol.upper()
    if not root.is_dir():
        return set()
    out: set[tuple[str, str]] = set()
    for p in root.glob("history_*.parquet"):
        parsed = _parse_history_range(p)
        if parsed is not None:
            out.add(parsed)
    return out


def _resolve_dates(
    data_dir: Path,
    spy_symbol: str,
    lead_symbol: str,
    requested_start: str,
    requested_end: str,
    auto_resolve: bool,
) -> tuple[str, str]:
    requested = (requested_start, requested_end)
    spy_ranges = _available_ranges(data_dir, spy_symbol)
    lead_ranges = _available_ranges(data_dir, lead_symbol)
    common = spy_ranges.intersection(lead_ranges)
    if requested in common:
        return requested
    if not auto_resolve:
        raise FileNotFoundError(
            f"Missing exact range for both symbols: {spy_symbol},{lead_symbol} with {requested_start}..{requested_end}"
        )
    if not common:
        raise FileNotFoundError(
            f"No common history_<start>_<end>.parquet ranges found for {spy_symbol} and {lead_symbol} under {data_dir}"
        )
    # Prefer latest end date, then latest start date for deterministic fallback.
    chosen = sorted(common, key=lambda x: (x[1], x[0]), reverse=True)[0]
    print(
        f"[warn] requested range {requested_start}..{requested_end} unavailable; "
        f"using available common range {chosen[0]}..{chosen[1]}"
    )
    return chosen


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = Path(args.data_dir)
    resolved_start, resolved_end = _resolve_dates(
        data_dir=data_dir,
        spy_symbol=str(args.spy_symbol),
        lead_symbol=str(args.lead_symbol),
        requested_start=str(args.start_date),
        requested_end=str(args.end_date),
        auto_resolve=not bool(args.no_auto_resolve_date_range),
    )

    hypothesis_tag = f"{args.run_tag_prefix}_hypothesis"
    sweep_tag = f"{args.run_tag_prefix}_sweep"

    hypothesis_cmd = [
        sys.executable,
        "research/hypothesis_analysis.py",
        "--data-dir",
        str(data_dir),
        "--output-dir",
        str(output_dir),
        "--start-date",
        resolved_start,
        "--end-date",
        resolved_end,
        "--spy-symbol",
        str(args.spy_symbol),
        "--lead-symbol",
        str(args.lead_symbol),
        "--spy-threshold-pct",
        str(args.spy_threshold_pct),
        "--lead-threshold-pct",
        str(args.lead_threshold_pct),
        "--next-spy-drop-pct",
        str(args.next_spy_drop_pct),
        "--run-tag",
        hypothesis_tag,
    ]
    hypothesis_cmd = _maybe_add_config(hypothesis_cmd, args.config_json)

    sweep_cmd = [
        sys.executable,
        "research/threshold_sweep.py",
        "--data-dir",
        str(data_dir),
        "--output-dir",
        str(output_dir),
        "--start-date",
        resolved_start,
        "--end-date",
        resolved_end,
        "--spy-symbol",
        str(args.spy_symbol),
        "--lead-symbol",
        str(args.lead_symbol),
        f"--spy-thresholds-pct={args.spy_thresholds_pct}",
        f"--lead-thresholds-pct={args.lead_thresholds_pct}",
        f"--next-spy-drop-thresholds-pct={args.next_spy_drop_thresholds_pct}",
        "--min-signal-days",
        str(args.min_signal_days),
        "--run-tag",
        sweep_tag,
    ]
    sweep_cmd = _maybe_add_config(sweep_cmd, args.config_json)

    _run(hypothesis_cmd)
    _run(sweep_cmd)

    if args.build_registry:
        registry_cmd = [
            sys.executable,
            "research/build_experiment_registry.py",
            "--runs-root",
            str(output_dir),
            "--registry-csv",
            str(output_dir / "experiment_registry.csv"),
            "--comparison-csv",
            str(output_dir / "experiment_comparison.csv"),
        ]
        _run(registry_cmd)

    print("[ok] demo completed")
    print(f"[ok] date range: {resolved_start}..{resolved_end}")
    print(f"[ok] hypothesis run dir: {output_dir / hypothesis_tag}")
    print(f"[ok] sweep run dir: {output_dir / sweep_tag}")
    if args.build_registry:
        print(f"[ok] registry: {output_dir / 'experiment_registry.csv'}")
        print(f"[ok] comparison: {output_dir / 'experiment_comparison.csv'}")


if __name__ == "__main__":
    main()
