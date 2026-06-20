from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common.artifact_pruning import find_prune_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prune stale scratch/rejected backtest and research artifacts."
    )
    parser.add_argument("--eval-root", default="eval_results", help="Evaluation artifacts root.")
    parser.add_argument(
        "--research-output-root",
        default="research/output",
        help="Research output root containing run directories with manifest.json files.",
    )
    parser.add_argument(
        "--decisions-json",
        default="research/configs/backtest_decisions.json",
        help="Decision registry used to protect keep/candidate runs.",
    )
    parser.add_argument(
        "--min-age-days",
        type=float,
        default=14.0,
        help="Only consider artifacts older than this many days.",
    )
    parser.add_argument(
        "--remove-unknown",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Also prune unknown-status artifacts older than the threshold.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print prune candidates without deleting them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidates = find_prune_candidates(
        eval_root=Path(args.eval_root),
        research_output_root=Path(args.research_output_root),
        decisions_path=Path(args.decisions_json),
        min_age_days=args.min_age_days,
        remove_unknown=args.remove_unknown,
    )

    if not candidates:
        print("[ok] no prune candidates found")
        return

    for candidate in candidates:
        print(
            f"[candidate] kind={candidate.kind} status={candidate.status} "
            f"age_days={candidate.age_days:.1f} reason={candidate.reason} path={candidate.path}"
        )
        if not args.dry_run:
            shutil.rmtree(candidate.path)
            print(f"[deleted] {candidate.path}")

    print(
        f"[ok] {'listed' if args.dry_run else 'deleted'} {len(candidates)} artifact candidate(s)"
    )


if __name__ == "__main__":
    main()
