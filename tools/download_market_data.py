from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import List

from tradingagents.dataflows.market_data_store import (
    download_history,
    parquet_path_for_symbol,
    save_history_parquet,
)
from tools.sp500_symbols import fetch_sp500_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Yahoo Finance history and store as parquet."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Ticker symbols, e.g. SPY TSLA AAPL",
    )
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD")
    parser.add_argument(
        "--end-date",
        help="End date YYYY-MM-DD (inclusive from user perspective)",
    )
    parser.add_argument(
        "--sp500",
        action="store_true",
        help="Download all current S&P 500 constituents from Wikipedia.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="When start/end are omitted, download this many years ending today (default: 5).",
    )
    parser.add_argument("--out-dir", default="data/market", help="Output root directory")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing parquet files if present",
    )
    return parser.parse_args()


def normalize_symbols(raw_symbols: List[str]) -> List[str]:
    seen = set()
    symbols = []
    for raw in raw_symbols:
        for token in raw.split(","):
            s = token.strip().upper()
            if s and s not in seen:
                symbols.append(s)
                seen.add(s)
    return symbols


def main() -> None:
    args = parse_args()
    if args.start_date and args.end_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").strftime("%Y-%m-%d")
        end_inclusive = datetime.strptime(args.end_date, "%Y-%m-%d")
        end_date = end_inclusive.strftime("%Y-%m-%d")
    elif args.start_date or args.end_date:
        raise SystemExit("Provide both --start-date and --end-date together, or omit both.")
    else:
        if args.years < 1:
            raise SystemExit("--years must be >= 1")
        end_inclusive = datetime.today()
        start_date = (end_inclusive - timedelta(days=365 * args.years)).strftime(
            "%Y-%m-%d"
        )
        end_date = end_inclusive.strftime("%Y-%m-%d")

    download_end = (end_inclusive + timedelta(days=1)).strftime("%Y-%m-%d")
    if args.sp500:
        sp500_symbols = fetch_sp500_symbols()
        symbols = normalize_symbols((args.symbols or []) + sp500_symbols)
    else:
        symbols = normalize_symbols(args.symbols or [])

    if not symbols:
        raise SystemExit("No valid symbols provided. Use --symbols and/or --sp500.")

    print(
        f"Downloading {len(symbols)} symbols from {start_date} to {end_date} "
        f"(Yahoo end={download_end}, exclusive)."
    )

    for symbol in symbols:
        target = parquet_path_for_symbol(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            root_dir=args.out_dir,
        )
        if target.exists() and not args.overwrite:
            print(f"[skip] {symbol}: {target}")
            continue

        df = download_history(symbol, start_date, download_end)
        output_path = save_history_parquet(
            df=df,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            root_dir=args.out_dir,
        )
        print(f"[ok] {symbol}: rows={len(df)} -> {output_path}")


if __name__ == "__main__":
    main()
