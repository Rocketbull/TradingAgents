from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests


CSI300_DETAIL_URL = (
    "https://www.csindex.com.cn/zh-CN/indices/index-detail/000300"
)
CSI300_WEIGHT_XLS_URL = (
    "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
    "autofile/closeweight/000300closeweight.xls"
)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
EXPECTED_COLUMNS = [
    "日期Date",
    "指数代码 Index Code",
    "指数名称 Index Name",
    "指数英文名称Index Name(Eng)",
    "成份券代码Constituent Code",
    "成份券名称Constituent Name",
    "成份券英文名称Constituent Name(Eng)",
    "交易所Exchange",
    "交易所英文名称Exchange(Eng)",
    "权重(%)weight",
]


def normalize_csi300_symbol(code: str | int, exchange: str) -> str:
    code_digits = "".join(ch for ch in str(code) if ch.isdigit()).zfill(6)
    exchange_text = str(exchange or "").strip().lower()
    if "shenzhen" in exchange_text or "深圳" in exchange_text:
        return f"SZ{code_digits}"
    if "shanghai" in exchange_text or "上海" in exchange_text:
        return f"SH{code_digits}"
    raise ValueError(f"Unsupported exchange value: {exchange!r}")


def normalize_csi300_weights(raw: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in EXPECTED_COLUMNS if column not in raw.columns]
    if missing:
        raise RuntimeError(f"Unexpected CSI300 schema. Missing columns: {missing}")

    frame = raw[EXPECTED_COLUMNS].copy().rename(
        columns={
            "日期Date": "asof_date",
            "指数代码 Index Code": "index_code",
            "指数名称 Index Name": "index_name",
            "指数英文名称Index Name(Eng)": "index_name_eng",
            "成份券代码Constituent Code": "constituent_code",
            "成份券名称Constituent Name": "constituent_name",
            "成份券英文名称Constituent Name(Eng)": "constituent_name_eng",
            "交易所Exchange": "exchange",
            "交易所英文名称Exchange(Eng)": "exchange_eng",
            "权重(%)weight": "weight_pct",
        }
    )

    frame["asof_date"] = pd.to_datetime(
        frame["asof_date"].astype(str), format="%Y%m%d"
    ).dt.strftime("%Y-%m-%d")
    frame["index_code"] = frame["index_code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    frame["constituent_code"] = (
        frame["constituent_code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
    )
    frame["exchange"] = frame["exchange"].astype(str).str.strip()
    frame["exchange_eng"] = frame["exchange_eng"].astype(str).str.strip()
    frame["symbol"] = [
        normalize_csi300_symbol(code, exchange)
        for code, exchange in zip(frame["constituent_code"], frame["exchange"])
    ]
    frame["weight_pct"] = pd.to_numeric(frame["weight_pct"], errors="coerce")
    frame["source"] = CSI300_WEIGHT_XLS_URL
    frame["detail_page"] = CSI300_DETAIL_URL

    if frame["symbol"].duplicated().any():
        duplicates = frame.loc[frame["symbol"].duplicated(), "symbol"].tolist()
        raise RuntimeError(f"Duplicate CSI300 symbols found: {duplicates}")

    return frame[
        [
            "asof_date",
            "index_code",
            "index_name",
            "index_name_eng",
            "symbol",
            "constituent_code",
            "constituent_name",
            "constituent_name_eng",
            "exchange",
            "exchange_eng",
            "weight_pct",
            "source",
            "detail_page",
        ]
    ].reset_index(drop=True)


def fetch_csi300_weights() -> pd.DataFrame:
    response = requests.get(CSI300_WEIGHT_XLS_URL, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    raw = pd.read_excel(BytesIO(response.content))
    normalized = normalize_csi300_weights(raw)
    if normalized.empty:
        raise RuntimeError("Official CSI300 workbook returned no constituent rows.")
    return normalized


def fetch_csi300_symbols() -> list[str]:
    return fetch_csi300_weights()["symbol"].tolist()


def write_csi300_outputs(
    weights: pd.DataFrame,
    out: str = "data/universe/csi300/current/csi300_symbols.txt",
    weights_out: str = "data/universe/csi300/current/csi300_weights.csv",
    snapshot_dir: str = "data/universe/csi300/snapshots",
    weights_snapshot_dir: str = "data/universe/csi300/weights",
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
            f'  "detail_page": "{CSI300_DETAIL_URL}",\n'
            f'  "source": "{CSI300_WEIGHT_XLS_URL}",\n'
            f'  "symbol_count": {len(symbols)}\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    weights_out_path = Path(weights_out)
    weights_out_path.parent.mkdir(parents=True, exist_ok=True)
    weights.to_csv(weights_out_path, index=False)

    snapshot_path = Path(snapshot_dir) / f"csi300_membership_{resolved_snapshot_date}.csv"
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
        Path(weights_snapshot_dir) / f"csi300_weights_{resolved_snapshot_date}.csv"
    )
    weights_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    weights.to_csv(weights_snapshot_path, index=False)

    print(
        f"[ok] fetched {len(symbols)} CSI300 constituents for {resolved_snapshot_date} "
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
        description="Fetch latest CSI300 constituents and weights from CSIndex."
    )
    parser.add_argument(
        "--out",
        default="data/universe/csi300/current/csi300_symbols.txt",
        help="Output text file path (one symbol per line).",
    )
    parser.add_argument(
        "--weights-out",
        default="data/universe/csi300/current/csi300_weights.csv",
        help="Output CSV path for current constituent weights.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="data/universe/csi300/snapshots",
        help="Directory to also save dated membership snapshots.",
    )
    parser.add_argument(
        "--weights-snapshot-dir",
        default="data/universe/csi300/weights",
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
    weights = fetch_csi300_weights()
    write_csi300_outputs(
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
