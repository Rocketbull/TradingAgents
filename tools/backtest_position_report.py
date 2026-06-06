from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def resolve_backtest_root() -> Path:
    for candidate in (Path("eval_results/backtest"), Path("../eval_results/backtest")):
        if candidate.exists():
            return candidate
    return Path("eval_results/backtest")


def is_run_dir(path: Path) -> bool:
    return path.is_dir() and (path / "summary.json").exists() and (path / "weights_history.csv").exists()


def latest_trade_date(run_dir: Path) -> pd.Timestamp:
    weights = pd.read_csv(run_dir / "weights_history.csv", usecols=["trade_date"])
    return pd.to_datetime(weights["trade_date"]).max()


def collect_runs(root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if root.exists():
        for p in root.iterdir():
            if p.name == "ab_pairs":
                continue
            if is_run_dir(p):
                runs.append({"run_dir": p, "source": "single", "pair": None})

    pair_root = root / "ab_pairs"
    if pair_root.exists():
        for pair in pair_root.iterdir():
            if not pair.is_dir():
                continue
            for child in ("run_a", "run_b"):
                rp = pair / child
                if is_run_dir(rp):
                    runs.append({"run_dir": rp, "source": f"ab_{child}", "pair": pair.name})

    for run in runs:
        summary = json.loads((run["run_dir"] / "summary.json").read_text(encoding="utf-8"))
        run["summary_end_date"] = pd.to_datetime(summary.get("end_date"), errors="coerce")
        run["latest_trade_date"] = latest_trade_date(run["run_dir"])
        run["mtime"] = max(
            (run["run_dir"] / "summary.json").stat().st_mtime,
            (run["run_dir"] / "weights_history.csv").stat().st_mtime,
        )

    runs.sort(
        key=lambda run: (
            run["latest_trade_date"] if pd.notna(run["latest_trade_date"]) else pd.Timestamp.min,
            run["summary_end_date"] if pd.notna(run["summary_end_date"]) else pd.Timestamp.min,
            run["mtime"],
        ),
        reverse=True,
    )
    return runs


def resolve_run_dir(run_dir: str | None, backtest_root: str) -> Path:
    if run_dir:
        path = Path(run_dir)
        if not is_run_dir(path):
            raise FileNotFoundError(f"Run directory is not valid: {path}")
        return path
    runs = collect_runs(Path(backtest_root))
    if not runs:
        raise FileNotFoundError(f"No valid backtest runs found under {Path(backtest_root).resolve()}")
    return Path(runs[0]["run_dir"])


def load_weight_frame(run_dir: Path) -> pd.DataFrame:
    weights = pd.read_csv(run_dir / "weights_history.csv")
    weights["trade_date"] = pd.to_datetime(weights["trade_date"])
    return weights


def build_position_report(weights: pd.DataFrame, sector_map: pd.DataFrame) -> dict[str, Any]:
    weights = weights.copy()
    weights["trade_date"] = pd.to_datetime(weights["trade_date"])
    all_dates = sorted(weights["trade_date"].dropna().unique())
    if len(all_dates) < 2:
        raise ValueError("Need at least two rebalance rows for month-over-month comparison.")
    latest = pd.Timestamp(all_dates[-1])
    prev = pd.Timestamp(all_dates[-2])

    latest_s = weights.loc[weights["trade_date"] == latest].drop(columns=["trade_date"]).iloc[0]
    prev_s = weights.loc[weights["trade_date"] == prev].drop(columns=["trade_date"]).iloc[0]

    positions = pd.DataFrame(
        {
            "symbol": latest_s.index,
            "latest_weight": latest_s.values.astype(float),
            "prev_weight": prev_s.reindex(latest_s.index).values.astype(float),
        }
    )
    positions["delta"] = positions["latest_weight"] - positions["prev_weight"]
    positions = positions.merge(sector_map[["symbol", "sector"]], on="symbol", how="left")
    positions["sector"] = positions["sector"].fillna("Unknown")

    latest_top20 = (
        positions.sort_values("latest_weight", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )
    increases = (
        positions.sort_values("delta", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )
    decreases = (
        positions.sort_values("delta", ascending=True)
        .head(20)
        .reset_index(drop=True)
    )

    sector_rollup = (
        positions.groupby("sector", dropna=False)[["latest_weight", "prev_weight"]]
        .sum()
        .reset_index()
    )
    sector_rollup["delta"] = sector_rollup["latest_weight"] - sector_rollup["prev_weight"]
    sector_rollup = sector_rollup.sort_values("latest_weight", ascending=False).reset_index(drop=True)

    return {
        "latest_trade_date": latest,
        "prev_trade_date": prev,
        "latest_top20": latest_top20,
        "top_increases": increases,
        "top_decreases": decreases,
        "sector_rollup": sector_rollup,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize latest backtest positions versus the previous rebalance."
    )
    parser.add_argument("--run-dir", default=None, help="Optional backtest run directory.")
    parser.add_argument(
        "--backtest-root",
        default=str(resolve_backtest_root()),
        help="Backtest root used when --run-dir is omitted.",
    )
    parser.add_argument(
        "--sector-cache",
        default="data/market/metadata/yfinance_classification.csv",
        help="CSV containing symbol->sector mapping.",
    )
    parser.add_argument("--top-n", type=int, default=20, help="Number of rows to print for each table.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = resolve_run_dir(args.run_dir, args.backtest_root)
    weights = load_weight_frame(run_dir)
    sector_map = pd.read_csv(args.sector_cache)
    report = build_position_report(weights, sector_map)

    top_n = int(args.top_n)
    print(f"[ok] run_dir: {run_dir}")
    print(f"[ok] latest_trade_date: {report['latest_trade_date'].date().isoformat()}")
    print(f"[ok] prev_trade_date: {report['prev_trade_date'].date().isoformat()}")

    print("\n## latest_top20")
    print(report["latest_top20"].head(top_n).to_csv(index=False))

    print("## top_increases")
    print(report["top_increases"].head(top_n).to_csv(index=False))

    print("## top_decreases")
    print(report["top_decreases"].head(top_n).to_csv(index=False))

    print("## sector_rollup")
    print(report["sector_rollup"].to_csv(index=False))


if __name__ == "__main__":
    main()
