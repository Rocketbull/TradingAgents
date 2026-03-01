from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Literal

import pandas as pd
import requests

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


def _parse_snapshot_date_from_name(path: Path) -> datetime | None:
    stem = path.stem  # sp500_membership_YYYY-MM-DD
    prefix = "sp500_membership_"
    if not stem.startswith(prefix):
        return None
    try:
        return datetime.strptime(stem[len(prefix) :], "%Y-%m-%d")
    except ValueError:
        return None


def find_latest_snapshot(snapshot_dir: Path) -> Path:
    candidates: list[tuple[datetime, Path]] = []
    for p in snapshot_dir.glob("sp500_membership_*.csv"):
        dt = _parse_snapshot_date_from_name(p)
        if dt is not None:
            candidates.append((dt, p))
    if not candidates:
        raise FileNotFoundError(
            f"No snapshot files found under {snapshot_dir} (need sp500_membership_YYYY-MM-DD.csv)"
        )
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def read_symbols(path: Path) -> list[str]:
    df = pd.read_csv(path)
    if df.empty:
        return []
    raw = df["symbol"].astype(str).tolist() if "symbol" in df.columns else df.iloc[:, 0].astype(str).tolist()
    out: list[str] = []
    seen: set[str] = set()
    for v in raw:
        s = str(v).strip().upper().replace(".", "-")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fetch_recent_changes_from_wikipedia() -> pd.DataFrame:
    response = requests.get(SP500_WIKI_URL, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    for t in tables:
        df = t.copy()
        if isinstance(df.columns, pd.MultiIndex):
            flat_cols = []
            for col in df.columns:
                parts = [str(x).strip().lower() for x in col if str(x).strip()]
                flat_cols.append(" ".join(parts))
            df.columns = flat_cols
        else:
            df.columns = [str(c).strip().lower() for c in df.columns]

        cols = list(df.columns)
        joined = " ".join(cols)
        date_col = next((c for c in cols if "effective date" in c or c == "date"), None)
        added_col = next((c for c in cols if "added" in c and "ticker" in c), None)
        removed_col = next((c for c in cols if "removed" in c and "ticker" in c), None)
        if not date_col or not added_col or not removed_col:
            continue
        if "added" not in joined or "removed" not in joined:
            continue

        rows: list[dict[str, str]] = []
        for _, r in df.iterrows():
            dt = pd.to_datetime(r.get(date_col), errors="coerce")
            if pd.isna(dt):
                continue
            date_str = dt.strftime("%Y-%m-%d")
            add_sym = str(r.get(added_col, "")).strip().upper().replace(".", "-")
            rem_sym = str(r.get(removed_col, "")).strip().upper().replace(".", "-")
            if add_sym and add_sym != "NAN":
                rows.append(
                    {"effective_date": date_str, "symbol": add_sym, "action": "add"}
                )
            if rem_sym and rem_sym != "NAN":
                rows.append(
                    {"effective_date": date_str, "symbol": rem_sym, "action": "remove"}
                )
        out = pd.DataFrame(rows)
        if not out.empty:
            return out
    raise RuntimeError("Could not find usable recent-changes table on Wikipedia")


def normalize_events(events: pd.DataFrame) -> pd.DataFrame:
    required = {"effective_date", "symbol", "action"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing required event columns: {sorted(missing)}")
    out = events.copy()
    out["effective_date"] = pd.to_datetime(out["effective_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper().str.replace(".", "-", regex=False)
    out["action"] = out["action"].astype(str).str.strip().str.lower()
    out = out[out["effective_date"].notna()]
    out = out[out["symbol"] != ""]
    out = out[out["action"].isin(["add", "remove"])]
    out = out.sort_values(["effective_date", "symbol", "action"]).reset_index(drop=True)
    return out


def apply_events(base_symbols: list[str], events: pd.DataFrame, asof_date: str) -> list[str]:
    members: set[str] = set(base_symbols)
    due = events[events["effective_date"] <= asof_date]
    for _, r in due.iterrows():
        sym = str(r["symbol"])
        action = str(r["action"])
        if action == "add":
            members.add(sym)
        elif action == "remove":
            members.discard(sym)
    return sorted(members)


def write_snapshot(path: Path, symbols: list[str], asof_date: str, source: str, method: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    df = pd.DataFrame(
        {
            "symbol": symbols,
            "asof_date": asof_date,
            "source": source,
            "generated_at_utc": stamp,
            "method": method,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build dated SP500 membership snapshots from a base snapshot and membership-change events."
    )
    p.add_argument(
        "--snapshot-dir",
        default="data/universe/sp500/snapshots",
        help="Directory with existing and output snapshot CSV files.",
    )
    p.add_argument(
        "--base-snapshot",
        default=None,
        help="Base snapshot CSV path. If omitted, uses latest file under --snapshot-dir.",
    )
    p.add_argument(
        "--base-date",
        default=None,
        help="Base snapshot date (YYYY-MM-DD). Defaults to date parsed from base snapshot filename.",
    )
    p.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD for generated snapshots.")
    p.add_argument("--end-date", required=True, help="End date YYYY-MM-DD for generated snapshots.")
    p.add_argument(
        "--freq",
        default="W-FRI",
        help="Snapshot frequency, pandas-compatible (e.g., W-FRI, M, MS).",
    )
    p.add_argument(
        "--events-source",
        choices=["none", "csv", "wikipedia_recent"],
        default="none",
        help="Where to load membership-change events from.",
    )
    p.add_argument(
        "--events-csv",
        default=None,
        help="CSV path with columns: effective_date,symbol,action. Required when --events-source=csv.",
    )
    p.add_argument(
        "--write-manifest",
        action="store_true",
        help="Write snapshot build manifest JSON into --snapshot-dir.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    base_path = Path(args.base_snapshot) if args.base_snapshot else find_latest_snapshot(snapshot_dir)
    if not base_path.exists():
        raise FileNotFoundError(f"Base snapshot not found: {base_path}")
    base_symbols = read_symbols(base_path)
    if len(base_symbols) < 100:
        raise ValueError(f"Base snapshot has too few symbols ({len(base_symbols)}): {base_path}")

    if args.base_date:
        base_date = datetime.strptime(args.base_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    else:
        parsed = _parse_snapshot_date_from_name(base_path)
        if parsed is None:
            raise ValueError("Could not parse base date from filename; pass --base-date")
        base_date = parsed.strftime("%Y-%m-%d")

    events = pd.DataFrame(columns=["effective_date", "symbol", "action"])
    source_detail: str = str(base_path)
    method: Literal["constant_latest", "event_replayed"] = "constant_latest"
    if args.events_source == "csv":
        if not args.events_csv:
            raise ValueError("--events-csv is required when --events-source=csv")
        source_detail = str(Path(args.events_csv))
        events = normalize_events(pd.read_csv(args.events_csv))
        method = "event_replayed"
    elif args.events_source == "wikipedia_recent":
        source_detail = SP500_WIKI_URL
        events = normalize_events(fetch_recent_changes_from_wikipedia())
        method = "event_replayed"

    start = pd.Timestamp(args.start_date)
    end = pd.Timestamp(args.end_date)
    if start > end:
        raise ValueError("start-date must be <= end-date")
    if start < pd.Timestamp(base_date):
        print(
            f"[warn] start-date {start.date()} is earlier than base-date {base_date}; "
            "snapshots before base-date use the base membership unchanged."
        )

    dates = pd.date_range(start=start, end=end, freq=args.freq)
    if len(dates) == 0:
        dates = pd.DatetimeIndex([start, end]).unique().sort_values()

    created: list[str] = []
    for d in dates:
        asof = d.strftime("%Y-%m-%d")
        symbols = apply_events(base_symbols=base_symbols, events=events, asof_date=asof)
        out = snapshot_dir / f"sp500_membership_{asof}.csv"
        write_snapshot(out, symbols=symbols, asof_date=asof, source=source_detail, method=method)
        created.append(str(out))

    print(f"[ok] base snapshot: {base_path} ({len(base_symbols)} symbols)")
    print(f"[ok] generated {len(created)} snapshots under {snapshot_dir}")
    if events.empty:
        print("[info] no events loaded -> constant latest membership across generated dates")
    else:
        print(f"[ok] applied {len(events)} membership events from {source_detail}")
    print(f"[ok] first: {created[0]}")
    print(f"[ok] last:  {created[-1]}")

    if args.write_manifest:
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "base_snapshot": str(base_path),
            "base_date": base_date,
            "events_source": args.events_source,
            "events_count": int(len(events)),
            "source_detail": source_detail,
            "method": method,
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "freq": args.freq,
            "output_count": len(created),
        }
        manifest_path = snapshot_dir / "sp500_snapshot_build_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"[ok] manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
