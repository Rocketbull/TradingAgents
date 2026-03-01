from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tradingagents.alpha import AlphaModel
from tradingagents.backtest import BacktestEngine
from tradingagents.default_config import DEFAULT_CONFIG


def _default_registry_specs() -> list[dict[str, Any]]:
    return [
        {"type": "momentum", "name": "mom_1m", "window": 21},
        {"type": "momentum", "name": "mom_3m", "window": 63},
        {"type": "momentum", "name": "mom_6m", "window": 126},
        {"type": "momentum", "name": "mom_12m", "window": 252},
        {"type": "reversal", "name": "rev_1w", "window": 5},
        {"type": "reversal", "name": "rev_1m", "window": 21},
        {"type": "low_vol", "name": "low_vol", "window": 60},
        {"type": "downside_vol", "name": "downside_vol", "window": 60},
        {"type": "trend", "name": "trend_12m_1m", "long_window": 252, "short_window": 21},
        {"type": "breakout", "name": "breakout_52w", "window": 252},
    ]


def _find_latest_valid_run(backtest_root: Path) -> Path:
    runs = [
        p
        for p in backtest_root.iterdir()
        if p.is_dir()
        and (p / "summary.json").exists()
        and (p / "rebalance_log.jsonl").exists()
    ]
    if not runs:
        raise FileNotFoundError(f"No valid backtest run folders under {backtest_root}")
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0]


def _safe_div(a: float, b: float) -> float:
    if not np.isfinite(a) or not np.isfinite(b) or b == 0:
        return float("nan")
    return float(a / b)


def analyze_run_signal_behavior(run_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    log_path = run_dir / "rebalance_log.jsonl"
    if not log_path.exists():
        raise FileNotFoundError(f"Missing rebalance log: {log_path}")
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"No rows in rebalance log: {log_path}")

    signal_names: set[str] = set()
    for r in rows:
        signal_names.update((r.get("alpha_weights") or {}).keys())
        signal_names.update((r.get("signal_ic") or {}).keys())
    signals = sorted(signal_names)
    if not signals:
        raise ValueError("No signal fields found in rebalance log.")

    records: list[dict[str, Any]] = []
    for s in signals:
        w = np.asarray([float((r.get("alpha_weights") or {}).get(s, np.nan)) for r in rows], dtype=float)
        ic = np.asarray([float((r.get("signal_ic") or {}).get(s, np.nan)) for r in rows], dtype=float)
        w_f = w[np.isfinite(w)]
        ic_f = ic[np.isfinite(ic)]

        mean_w = float(np.nanmean(w)) if np.isfinite(w).any() else float("nan")
        mean_abs_w = float(np.nanmean(np.abs(w))) if np.isfinite(w).any() else float("nan")
        nz_rate = float(np.nanmean(np.abs(w) > 1e-10)) if np.isfinite(w).any() else float("nan")

        mean_ic = float(np.nanmean(ic)) if np.isfinite(ic).any() else float("nan")
        std_ic = float(np.nanstd(ic, ddof=0)) if np.isfinite(ic).any() else float("nan")
        ic_ir = _safe_div(mean_ic, std_ic)
        pos_ic_rate = float(np.nanmean(ic > 0.0)) if np.isfinite(ic).any() else float("nan")

        weighted_ic_proxy = (
            float(np.nanmean(w * ic))
            if np.isfinite(w).any() and np.isfinite(ic).any()
            else float("nan")
        )
        corr_w_ic = (
            float(np.corrcoef(w_f, ic_f)[0, 1])
            if len(w_f) > 2 and len(ic_f) > 2 and len(w_f) == len(ic_f)
            else float("nan")
        )

        records.append(
            {
                "signal": s,
                "obs_rows": int(len(rows)),
                "mean_weight": mean_w,
                "mean_abs_weight": mean_abs_w,
                "weight_nonzero_rate": nz_rate,
                "mean_signal_ic": mean_ic,
                "signal_ic_std": std_ic,
                "signal_ic_ir": ic_ir,
                "signal_ic_positive_rate": pos_ic_rate,
                "weighted_ic_proxy": weighted_ic_proxy,
                "corr_weight_vs_ic": corr_w_ic,
            }
        )

    df = pd.DataFrame(records).sort_values("weighted_ic_proxy", ascending=False).reset_index(drop=True)
    meta = {
        "run_dir": str(run_dir),
        "rows": len(rows),
        "signals_found": len(signals),
    }
    return df, meta


def run_single_signal_sweep(
    start_date: str,
    end_date: str,
    out_dir: Path,
    universe_source: str,
    universe_size: int,
    symbol_file: str,
    snapshot_dir: str,
    dynamic_liquidity_filter: bool,
    liquidity_top_n: int,
    liquidity_lookback_days: int,
    max_signals: int | None,
) -> pd.DataFrame:
    specs = _default_registry_specs()
    if max_signals is not None and max_signals > 0:
        specs = specs[: int(max_signals)]

    rows: list[dict[str, Any]] = []
    for spec in specs:
        name = str(spec["name"])
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(
            {
                "backtest_start_date": start_date,
                "backtest_end_date": end_date,
                "universe_source": universe_source,
                "portfolio_universe_size": int(universe_size),
                "symbol_file": symbol_file,
                "universe_snapshot_dir": snapshot_dir,
                "snapshot_schedule_enabled": False,
                "dynamic_liquidity_filter": bool(dynamic_liquidity_filter),
                "liquidity_top_n": int(liquidity_top_n),
                "liquidity_lookback_days": int(liquidity_lookback_days),
                "alpha_signal_registry": [spec],
                "alpha_signals": [name],
                "backtest_output_dir": str(out_dir / f"single_{name}"),
            }
        )
        result = BacktestEngine(cfg).run(fallback_symbol=str(cfg.get("benchmark_symbol", "SPY")).upper())
        s = result["summary"]
        rows.append(
            {
                "signal": name,
                "type": spec["type"],
                "total_return": s.get("total_return"),
                "cagr": s.get("cagr"),
                "sharpe": s.get("sharpe"),
                "max_drawdown": s.get("max_drawdown"),
                "tracking_error": s.get("tracking_error"),
                "realized_active_information_ratio": s.get("realized_active_information_ratio"),
                "average_executed_turnover": s.get("average_executed_turnover"),
                "h1_average_ic": s.get("h1_average_ic"),
                "h2_average_ic": s.get("h2_average_ic"),
                "h4_average_ic": s.get("h4_average_ic"),
                "output_dir": result["output_dir"],
            }
        )
    df = pd.DataFrame(rows).sort_values("sharpe", ascending=False).reset_index(drop=True)
    return df


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit alpha signals from backtest logs and/or single-signal sweeps.")
    p.add_argument("--mode", choices=["log", "single", "both"], default="log")
    p.add_argument("--backtest-root", default="eval_results/backtest")
    p.add_argument("--run-dir", default=None, help="Backtest run directory for --mode log.")
    p.add_argument("--start-date", default="2024-01-01", help="Used for --mode single|both.")
    p.add_argument("--end-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"), help="Used for --mode single|both.")
    p.add_argument("--universe-source", default="sp500_snapshot", choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"])
    p.add_argument("--universe-size", type=int, default=500)
    p.add_argument("--symbol-file", default="data/universe/sp500/current/sp500_symbols.txt")
    p.add_argument("--snapshot-dir", default="data/universe/sp500/snapshots")
    p.add_argument("--dynamic-liquidity-filter", action="store_true")
    p.add_argument("--liquidity-top-n", type=int, default=100)
    p.add_argument("--liquidity-lookback-days", type=int, default=60)
    p.add_argument("--max-signals", type=int, default=None, help="Limit single-signal runs for quick checks.")
    p.add_argument("--out-dir", default="research/output/alpha_signal_audit")
    p.add_argument("--tag", default=None)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = args.tag or stamp
    out_dir = Path(args.out_dir) / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "mode": args.mode,
        "created_at_utc": stamp,
    }

    if args.mode in {"log", "both"}:
        run_dir = Path(args.run_dir) if args.run_dir else _find_latest_valid_run(Path(args.backtest_root))
        signal_df, meta = analyze_run_signal_behavior(run_dir=run_dir)
        signal_path = out_dir / "signal_behavior_from_log.csv"
        signal_df.to_csv(signal_path, index=False)
        payload["log_analysis"] = {"meta": meta, "csv": str(signal_path)}
        print(f"[ok] log signal behavior -> {signal_path}")
        print(signal_df.head(15).to_string(index=False))

    if args.mode in {"single", "both"}:
        single_df = run_single_signal_sweep(
            start_date=args.start_date,
            end_date=args.end_date,
            out_dir=out_dir / "single_signal_runs",
            universe_source=args.universe_source,
            universe_size=args.universe_size,
            symbol_file=args.symbol_file,
            snapshot_dir=args.snapshot_dir,
            dynamic_liquidity_filter=bool(args.dynamic_liquidity_filter),
            liquidity_top_n=int(args.liquidity_top_n),
            liquidity_lookback_days=int(args.liquidity_lookback_days),
            max_signals=args.max_signals,
        )
        single_path = out_dir / "single_signal_backtest_summary.csv"
        single_df.to_csv(single_path, index=False)
        payload["single_signal_sweep"] = {"csv": str(single_path), "rows": int(len(single_df))}
        print(f"[ok] single-signal sweep -> {single_path}")
        print(single_df.head(15).to_string(index=False))

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[ok] manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
