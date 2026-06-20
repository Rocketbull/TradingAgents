from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import sys

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.csi300_symbols import EXPECTED_COLUMNS, REQUEST_HEADERS, normalize_csi300_weights


CSI500_DETAIL_URL = "https://www.csindex.com.cn/zh-CN/indices/index-detail/000905"
CSI500_WEIGHT_XLS_URL = (
    "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
    "autofile/closeweight/000905closeweight.xls"
)


def fetch_csi500_weights() -> pd.DataFrame:
    response = requests.get(CSI500_WEIGHT_XLS_URL, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    raw = pd.read_excel(BytesIO(response.content))
    missing = [column for column in EXPECTED_COLUMNS if column not in raw.columns]
    if missing:
        raise RuntimeError(f"Unexpected CSI500 schema. Missing columns: {missing}")
    normalized = normalize_csi300_weights(raw)
    normalized["source"] = CSI500_WEIGHT_XLS_URL
    normalized["detail_page"] = CSI500_DETAIL_URL
    if normalized.empty:
        raise RuntimeError("Official CSI500 workbook returned no constituent rows.")
    return normalized


def fetch_csi500_symbols() -> list[str]:
    return fetch_csi500_weights()["symbol"].tolist()


def write_csi500_outputs(
    weights: pd.DataFrame,
    out: str = "data/universe/csi500/current/csi500_symbols.txt",
    weights_out: str = "data/universe/csi500/current/csi500_weights.csv",
    snapshot_dir: str = "data/universe/csi500/snapshots",
    weights_snapshot_dir: str = "data/universe/csi500/weights",
    snapshot_date: str | None = None,
    stdout: bool = False,
) -> dict[str, Path]:
    if weights.empty:
        raise ValueError("weights is empty")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    resolved_snapshot_date = snapshot_date or str(weights["asof_date"].iloc[0])
    symbols = weights["symbol"].astype(str).tolist()

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(symbols) + "\n", encoding="utf-8")

    metadata_path = out_path.with_suffix(".metadata.json")
    metadata_path.write_text(
        (
            "{\n"
            f'  "downloaded_at_utc": "{stamp}",\n'
            f'  "asof_date": "{resolved_snapshot_date}",\n'
            f'  "detail_page": "{CSI500_DETAIL_URL}",\n'
            f'  "source": "{CSI500_WEIGHT_XLS_URL}",\n'
            f'  "symbol_count": {len(symbols)}\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    weights_out_path = Path(weights_out)
    weights_out_path.parent.mkdir(parents=True, exist_ok=True)
    weights.to_csv(weights_out_path, index=False)

    snapshot_path = Path(snapshot_dir) / f"csi500_membership_{resolved_snapshot_date}.csv"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    weights[
        [
            "symbol",
            "constituent_code",
            "constituent_name",
            "exchange",
            "weight_pct",
            "asof_date",
            "source",
        ]
    ].to_csv(snapshot_path, index=False)

    weights_snapshot_path = (
        Path(weights_snapshot_dir) / f"csi500_weights_{resolved_snapshot_date}.csv"
    )
    weights_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    weights.to_csv(weights_snapshot_path, index=False)

    print(
        f"[ok] fetched {len(symbols)} CSI500 constituents for {resolved_snapshot_date} "
        f"-> {out_path}"
    )
    print(f"[ok] weights saved -> {weights_out_path}")
    print(f"[ok] membership snapshot saved -> {snapshot_path}")
    print(f"[ok] weights snapshot saved -> {weights_snapshot_path}")

    if stdout:
        print(" ".join(symbols))

    return {
        "symbols": out_path,
        "metadata": metadata_path,
        "weights": weights_out_path,
        "snapshot": snapshot_path,
        "weights_snapshot": weights_snapshot_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch latest CSI500 constituents and weights from CSIndex."
    )
    parser.add_argument(
        "--out",
        default="data/universe/csi500/current/csi500_symbols.txt",
        help="Output text file path (one symbol per line).",
    )
    parser.add_argument(
        "--weights-out",
        default="data/universe/csi500/current/csi500_weights.csv",
        help="Output CSV path for current constituent weights.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="data/universe/csi500/snapshots",
        help="Directory to also save dated membership snapshots.",
    )
    parser.add_argument(
        "--weights-snapshot-dir",
        default="data/universe/csi500/weights",
        help="Directory to also save dated weight snapshots.",
    )
    parser.add_argument(
        "--snapshot-date",
        default=None,
        help="Snapshot date YYYY-MM-DD; defaults to the official workbook date.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print symbols to stdout in addition to writing the files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    weights = fetch_csi500_weights()
    write_csi500_outputs(
        weights=weights,
        out=args.out,
        weights_out=args.weights_out,
        snapshot_dir=args.snapshot_dir,
        weights_snapshot_dir=args.weights_snapshot_dir,
        snapshot_date=args.snapshot_date,
        stdout=args.stdout,
    )


if __name__ == "__main__":
    main()
