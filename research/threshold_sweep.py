from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from itertools import product

import pandas as pd

from tradingagents.dataflows.market_data_store import load_history_parquet


def parse_float_list(value: str) -> list[float]:
    values = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(float(token))
    if not values:
        raise argparse.ArgumentTypeError("List must contain at least one numeric value.")
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run threshold sweeps for SPY/lead hypothesis.")
    parser.add_argument("--data-dir", default="data/market", help="Parquet root directory")
    parser.add_argument("--output-dir", default="research/output", help="Sweep output directory")
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--spy-symbol", default="SPY", help="SPY-like index symbol")
    parser.add_argument("--lead-symbol", default="TSLA", help="Lead symbol")
    parser.add_argument(
        "--spy-thresholds-pct",
        type=parse_float_list,
        required=True,
        help="Comma-separated values for SPY signal threshold (<=), in percent",
    )
    parser.add_argument(
        "--lead-thresholds-pct",
        type=parse_float_list,
        required=True,
        help="Comma-separated values for lead signal threshold (>), in percent",
    )
    parser.add_argument(
        "--next-spy-drop-thresholds-pct",
        type=parse_float_list,
        required=True,
        help="Comma-separated values for next-day SPY drop threshold (<), in percent",
    )
    parser.add_argument(
        "--min-signal-days",
        type=int,
        default=20,
        help="Minimum number of signal days required to keep a row",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    spy = load_history_parquet(
        symbol=args.spy_symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        root_dir=args.data_dir,
    )[["Date", "Close"]].copy()
    lead = load_history_parquet(
        symbol=args.lead_symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        root_dir=args.data_dir,
    )[["Date", "Close"]].copy()

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
    valid = merged.dropna(subset=["spy_ret", "lead_ret", "next_day_spy_ret"]).copy()

    rows = []
    for spy_t, lead_t, next_t in product(
        args.spy_thresholds_pct,
        args.lead_thresholds_pct,
        args.next_spy_drop_thresholds_pct,
    ):
        spy_thresh = spy_t / 100.0
        lead_thresh = lead_t / 100.0
        next_thresh = next_t / 100.0

        signal = (valid["spy_ret"] <= spy_thresh) & (valid["lead_ret"] > lead_thresh)
        outcome = valid["next_day_spy_ret"] < next_thresh

        signal_days = int(signal.sum())
        if signal_days < args.min_signal_days:
            continue

        hit_days = int((signal & outcome).sum())
        hit_rate = hit_days / signal_days if signal_days else float("nan")
        base_rate = float(outcome.mean()) if not valid.empty else float("nan")
        lift = hit_rate / base_rate if base_rate > 0 else float("nan")

        rows.append(
            {
                "spy_threshold_pct": spy_t,
                "lead_threshold_pct": lead_t,
                "next_spy_drop_threshold_pct": next_t,
                "sample_days": int(valid.shape[0]),
                "signal_days": signal_days,
                "hit_days": hit_days,
                "hit_rate": hit_rate,
                "base_rate": base_rate,
                "lift_vs_base_rate": lift,
            }
        )

    if not rows:
        raise SystemExit("No combinations met min-signal-days criteria.")

    result = pd.DataFrame(rows).sort_values(
        by=["lift_vs_base_rate", "hit_rate", "signal_days"], ascending=[False, False, False]
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / (
        f"threshold_sweep_{args.spy_symbol}_{args.lead_symbol}_"
        f"{args.start_date}_{args.end_date}_{timestamp}.csv"
    )
    result.to_csv(output_path, index=False)

    print(f"Sweep rows: {len(result)}")
    print(f"Saved: {output_path}")
    print("Top 5:")
    print(result.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
