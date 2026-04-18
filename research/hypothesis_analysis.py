from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common.run_manager import ResearchRunManager
from activeportfolio.dataflows.market_data_store import load_history_parquet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run parameterized SPY/TSLA hypothesis analysis.")
    parser.add_argument("--data-dir", default="data/market", help="Parquet root directory")
    parser.add_argument("--output-dir", default="research/output", help="Analysis output directory")
    parser.add_argument("--run-tag", default=None, help="Optional run tag. Defaults to deterministic hash tag.")
    parser.add_argument(
        "--config-json",
        default=None,
        help="Optional config JSON path recorded in manifest for reproducibility.",
    )
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--spy-symbol", default="SPY", help="Index symbol (default: SPY)")
    parser.add_argument("--lead-symbol", default="TSLA", help="Lead symbol (default: TSLA)")
    parser.add_argument(
        "--spy-threshold-pct",
        type=float,
        default=-0.25,
        help="Signal condition for SPY daily return <= this percent",
    )
    parser.add_argument(
        "--lead-threshold-pct",
        type=float,
        default=1.5,
        help="Signal condition for lead symbol daily return > this percent",
    )
    parser.add_argument(
        "--next-spy-drop-pct",
        type=float,
        default=-1.0,
        help="Outcome condition for next-day SPY return < this percent",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    params = {
        "script": "hypothesis_analysis",
        "start_date": args.start_date,
        "end_date": args.end_date,
        "spy_symbol": str(args.spy_symbol).upper(),
        "lead_symbol": str(args.lead_symbol).upper(),
        "spy_threshold_pct": float(args.spy_threshold_pct),
        "lead_threshold_pct": float(args.lead_threshold_pct),
        "next_spy_drop_pct": float(args.next_spy_drop_pct),
    }
    run_manager = ResearchRunManager(
        out_dir=output_dir,
        params=params,
        run_tag=args.run_tag,
        tag_prefix="hypothesis",
    )
    run_dir = run_manager.run_dir()

    spy = load_history_parquet(
        symbol=args.spy_symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        root_dir=args.data_dir,
    )
    lead = load_history_parquet(
        symbol=args.lead_symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        root_dir=args.data_dir,
    )

    spy = spy[["Date", "Close"]].copy()
    lead = lead[["Date", "Close"]].copy()
    spy["Date"] = pd.to_datetime(spy["Date"])
    lead["Date"] = pd.to_datetime(lead["Date"])
    spy = spy.sort_values("Date")
    lead = lead.sort_values("Date")

    spy["spy_ret"] = spy["Close"].pct_change()
    lead["lead_ret"] = lead["Close"].pct_change()

    merged = pd.merge(
        spy[["Date", "spy_ret"]],
        lead[["Date", "lead_ret"]],
        on="Date",
        how="inner",
    ).sort_values("Date")

    merged["next_day_spy_ret"] = merged["spy_ret"].shift(-1)

    spy_thresh = args.spy_threshold_pct / 100.0
    lead_thresh = args.lead_threshold_pct / 100.0
    next_spy_drop = args.next_spy_drop_pct / 100.0

    merged["signal"] = (merged["spy_ret"] <= spy_thresh) & (merged["lead_ret"] > lead_thresh)
    merged["outcome"] = merged["next_day_spy_ret"] < next_spy_drop

    valid = merged.dropna(subset=["spy_ret", "lead_ret", "next_day_spy_ret"]).copy()
    signal_days = valid[valid["signal"]].copy()

    signal_count = int(signal_days.shape[0])
    hit_count = int(signal_days["outcome"].sum()) if signal_count else 0
    hit_rate = (hit_count / signal_count) if signal_count else float("nan")
    base_rate = float((valid["next_day_spy_ret"] < next_spy_drop).mean()) if not valid.empty else float("nan")
    lift = (hit_rate / base_rate) if signal_count and base_rate > 0 else float("nan")

    signal_path = run_dir / "signal_days.csv"
    summary_path = run_dir / "summary.csv"

    signal_days.to_csv(signal_path, index=False)
    pd.DataFrame(
        [
            {
                "hypothesis": f"{args.spy_symbol}<= {args.spy_threshold_pct}% and "
                f"{args.lead_symbol}> {args.lead_threshold_pct}% today -> "
                f"{args.spy_symbol}< {args.next_spy_drop_pct}% next day",
                "start_date": args.start_date,
                "end_date": args.end_date,
                "sample_days": int(valid.shape[0]),
                "signal_days": signal_count,
                "hit_days": hit_count,
                "hit_rate": hit_rate,
                "base_rate": base_rate,
                "lift_vs_base_rate": lift,
            }
        ]
    ).to_csv(summary_path, index=False)

    params_path = run_manager.write_params(
        extra={
            "sample_days": int(valid.shape[0]),
            "signal_days": signal_count,
            "hit_days": hit_count,
            "hit_rate": hit_rate,
            "base_rate": base_rate,
            "lift_vs_base_rate": lift,
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "summary_csv": str(summary_path),
            "signal_days_csv": str(signal_path),
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] signal days: {signal_path}")
    print(f"[ok] summary: {summary_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(
        "Metrics: "
        f"sample_days={int(valid.shape[0])}, signal_days={signal_count}, "
        f"hit_days={hit_count}, hit_rate={hit_rate}, base_rate={base_rate}, lift={lift}"
    )


if __name__ == "__main__":
    main()
