from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


def fetch_sp500_symbols() -> list[str]:
    response = requests.get(SP500_WIKI_URL, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise RuntimeError("No tables found on the S&P 500 source page.")

    constituents = tables[0]
    if "Symbol" not in constituents.columns:
        raise RuntimeError("Unexpected S&P 500 schema: missing 'Symbol' column.")

    symbols = []
    seen = set()
    for raw in constituents["Symbol"].astype(str):
        symbol = raw.strip().upper().replace(".", "-")
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch latest S&P 500 ticker symbols from Wikipedia."
    )
    parser.add_argument(
        "--out",
        default="data/universe/sp500/current/sp500_symbols.txt",
        help="Output text file path (one symbol per line).",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print symbols to stdout in addition to writing the file.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="data/universe/sp500/snapshots",
        help="Directory to also save dated membership snapshots.",
    )
    parser.add_argument(
        "--snapshot-date",
        default=None,
        help="Snapshot date YYYY-MM-DD; defaults to current UTC date.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = fetch_sp500_symbols()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.snapshot_date:
        snapshot_date = datetime.strptime(args.snapshot_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    else:
        snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(symbols) + "\n", encoding="utf-8")
    metadata_path = output.with_suffix(".metadata.json")
    metadata_path.write_text(
        (
            "{\n"
            f'  "downloaded_at_utc": "{stamp}",\n'
            f'  "source": "{SP500_WIKI_URL}",\n'
            f'  "symbol_count": {len(symbols)}\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    print(
        f"[ok] fetched {len(symbols)} symbols at {stamp} -> {output} "
        f"(metadata: {metadata_path})"
    )

    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"sp500_membership_{snapshot_date}.csv"
    snapshot_df = pd.DataFrame(
        {
            "symbol": symbols,
            "source": SP500_WIKI_URL,
            "downloaded_at_utc": stamp,
        }
    )
    snapshot_df.to_csv(snapshot_path, index=False)
    print(f"[ok] snapshot saved -> {snapshot_path}")

    if args.stdout:
        print(" ".join(symbols))


if __name__ == "__main__":
    main()
