from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common.backtest_index import build_backtest_index, render_backtest_index_markdown


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a searchable index of backtest runs, A/B tests, and config decisions."
    )
    p.add_argument(
        "--backtest-root",
        default="eval_results/backtest",
        help="Root directory containing saved backtest artifacts.",
    )
    p.add_argument(
        "--config-root",
        default="research/configs",
        help="Directory containing backtest config JSON files.",
    )
    p.add_argument(
        "--decisions-json",
        default="research/configs/backtest_decisions.json",
        help="Manual keep/reject/candidate decisions for configs and pair tests.",
    )
    p.add_argument(
        "--pairs-csv",
        default="eval_results/backtest/index_pair_runs.csv",
        help="Output CSV for all A/B pair runs.",
    )
    p.add_argument(
        "--latest-pairs-csv",
        default="eval_results/backtest/index_latest_pairs.csv",
        help="Output CSV for latest run per pair.",
    )
    p.add_argument(
        "--single-runs-csv",
        default="eval_results/backtest/index_single_runs.csv",
        help="Output CSV for single backtest runs.",
    )
    p.add_argument(
        "--configs-csv",
        default="eval_results/backtest/index_configs.csv",
        help="Output CSV for config catalog and decisions.",
    )
    p.add_argument(
        "--markdown",
        default="eval_results/backtest/INDEX.md",
        help="Output Markdown summary.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result = build_backtest_index(
        backtest_root=Path(args.backtest_root),
        config_root=Path(args.config_root),
        decisions_path=Path(args.decisions_json),
    )

    for output in (
        Path(args.pairs_csv),
        Path(args.latest_pairs_csv),
        Path(args.single_runs_csv),
        Path(args.configs_csv),
        Path(args.markdown),
    ):
        output.parent.mkdir(parents=True, exist_ok=True)

    result.pair_runs.to_csv(Path(args.pairs_csv), index=False)
    result.latest_pairs.to_csv(Path(args.latest_pairs_csv), index=False)
    result.single_runs.to_csv(Path(args.single_runs_csv), index=False)
    result.configs.to_csv(Path(args.configs_csv), index=False)
    Path(args.markdown).write_text(render_backtest_index_markdown(result), encoding="utf-8")

    print(f"[ok] pair runs: {len(result.pair_runs)} -> {args.pairs_csv}")
    print(f"[ok] latest pairs: {len(result.latest_pairs)} -> {args.latest_pairs_csv}")
    print(f"[ok] single runs: {len(result.single_runs)} -> {args.single_runs_csv}")
    print(f"[ok] configs: {len(result.configs)} -> {args.configs_csv}")
    print(f"[ok] markdown: {args.markdown}")


if __name__ == "__main__":
    main()
