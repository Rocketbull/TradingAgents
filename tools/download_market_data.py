from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import List

from tradingagents.dataflows.market_data_store import (
    download_history,
    parquet_path_for_symbol,
    save_history_parquet,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Yahoo Finance history and store as parquet."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="Ticker symbols, e.g. SPY TSLA AAPL",
    )
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date YYYY-MM-DD (inclusive from user perspective)",
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
    datetime.strptime(args.start_date, "%Y-%m-%d")
    end_inclusive = datetime.strptime(args.end_date, "%Y-%m-%d")
    download_end = (end_inclusive + timedelta(days=1)).strftime("%Y-%m-%d")
    symbols = normalize_symbols(args.symbols)

    if not symbols:
        raise SystemExit("No valid symbols provided.")

    print(
        f"Downloading {len(symbols)} symbols from {args.start_date} to {args.end_date} "
        f"(Yahoo end={download_end}, exclusive)."
    )

    for symbol in symbols:
        target = parquet_path_for_symbol(
            symbol=symbol,
            start_date=args.start_date,
            end_date=args.end_date,
            root_dir=args.out_dir,
        )
        if target.exists() and not args.overwrite:
            print(f"[skip] {symbol}: {target}")
            continue

        df = download_history(symbol, args.start_date, download_end)
        output_path = save_history_parquet(
            df=df,
            symbol=symbol,
            start_date=args.start_date,
            end_date=args.end_date,
            root_dir=args.out_dir,
        )
        print(f"[ok] {symbol}: rows={len(df)} -> {output_path}")


if __name__ == "__main__":
    main()
