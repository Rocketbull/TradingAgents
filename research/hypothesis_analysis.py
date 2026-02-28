from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.market_data_store import load_history_parquet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run parameterized SPY/TSLA hypothesis analysis.")
    parser.add_argument("--data-dir", default="data/market", help="Parquet root directory")
    parser.add_argument("--output-dir", default="research/output", help="Analysis output directory")
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


def _safe_num(value: float) -> str:
    return str(value).replace("-", "m").replace(".", "p")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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

    suffix = (
        f"spy{args.spy_symbol}_lead{args.lead_symbol}_"
        f"s{_safe_num(args.spy_threshold_pct)}_"
        f"l{_safe_num(args.lead_threshold_pct)}_"
        f"n{_safe_num(args.next_spy_drop_pct)}_"
        f"{args.start_date}_{args.end_date}"
    )
    signal_path = output_dir / f"hypothesis_signal_days_{suffix}.csv"
    summary_path = output_dir / f"hypothesis_summary_{suffix}.csv"

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

    print(f"Signal days saved: {signal_path}")
    print(f"Summary saved: {summary_path}")
    print(
        "Metrics: "
        f"sample_days={int(valid.shape[0])}, signal_days={signal_count}, "
        f"hit_days={hit_count}, hit_rate={hit_rate}, base_rate={base_rate}, lift={lift}"
    )


if __name__ == "__main__":
    main()
