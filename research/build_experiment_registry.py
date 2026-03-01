from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common.experiment_registry import build_registry


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build cross-run experiment registry and ranked comparison table."
    )
    p.add_argument(
        "--runs-root",
        default="research/output",
        help="Root directory containing run folders with manifest.json files.",
    )
    p.add_argument(
        "--registry-csv",
        default="research/output/experiment_registry.csv",
        help="Output path for full registry table CSV.",
    )
    p.add_argument(
        "--comparison-csv",
        default="research/output/experiment_comparison.csv",
        help="Output path for ranked comparison table CSV.",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Rows to print from ranked comparison table.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    runs_root = Path(args.runs_root)
    registry_csv = Path(args.registry_csv)
    comparison_csv = Path(args.comparison_csv)
    registry_csv.parent.mkdir(parents=True, exist_ok=True)
    comparison_csv.parent.mkdir(parents=True, exist_ok=True)

    result = build_registry(runs_root=runs_root)
    result.registry.to_csv(registry_csv, index=False)
    result.comparison.to_csv(comparison_csv, index=False)

    print(f"[ok] manifests scanned: {len(result.registry)}")
    print(f"[ok] registry: {registry_csv}")
    print(f"[ok] comparison: {comparison_csv}")
    if not result.comparison.empty:
        cols = [
            c
            for c in (
                "run_tag",
                "rank_metric",
                "rank_value",
                "summary_horizon_days",
                "summary_factor",
                "start_date",
                "end_date",
            )
            if c in result.comparison.columns
        ]
        print(f"[ok] top {min(int(args.top_k), len(result.comparison))}:")
        print(result.comparison.loc[:, cols].head(int(args.top_k)).to_string(index=False))
    else:
        print("[warn] no rankable runs found (missing ranking metrics).")


if __name__ == "__main__":
    main()
