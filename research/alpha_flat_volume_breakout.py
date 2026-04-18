from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.common import GrinoldDiagnostics, ResearchRunManager
from activeportfolio.backtest.data_loader import LocalParquetDataLoader


def parse_args() -> argparse.Namespace:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config-json", default=None, help="Optional JSON config file.")
    pre_args, remaining = pre.parse_known_args()

    config_defaults: dict[str, Any] = {}
    if pre_args.config_json:
        cfg_path = Path(pre_args.config_json)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Config not found: {cfg_path}")
        loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Config JSON must be an object.")
        config_defaults = loaded

    parser = argparse.ArgumentParser(
        description="Research signal: flat regime + volume surge + price breakout."
    )
    parser.add_argument("--config-json", default=pre_args.config_json, help="Optional JSON config file.")

    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument(
        "--universe-source",
        default="sp500_snapshot",
        choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"],
    )
    parser.add_argument("--universe-size", type=int, default=2000)
    parser.add_argument("--symbol-file", default="data/market/sp500_symbols.txt")
    parser.add_argument("--snapshot-dir", default="data/market/universe")
    parser.add_argument("--data-root", default="data/market")
    parser.add_argument("--benchmark-symbol", default="SPY")
    parser.add_argument("--fallback-symbol", default="SPY")

    parser.add_argument("--flat-lookback-days", type=int, default=60)
    parser.add_argument("--flat-max-abs-return", type=float, default=0.15)
    parser.add_argument("--price-lookback-days", type=int, default=20)
    parser.add_argument("--price-ratio-min", type=float, default=1.10)
    parser.add_argument("--vol-short-days", type=int, default=5)
    parser.add_argument("--vol-long-days", type=int, default=20)
    parser.add_argument("--vol-ratio-min", type=float, default=1.50)

    parser.add_argument("--forward-days", default="5,20")
    parser.add_argument(
        "--weighting-mode",
        default="long_short",
        choices=["long_short", "long_only"],
        help="Portfolio construction for TC/BR/IR diagnostics.",
    )
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--out-dir", default="research/output")
    parser.add_argument("--run-tag", default=None, help="Optional deterministic run tag override.")
    parser.add_argument("--save-by-date", action="store_true", help="Persist per-date diagnostics CSV.")

    parser.set_defaults(**config_defaults)
    args = parser.parse_args(remaining)
    if not args.start_date or not args.end_date:
        parser.error("--start-date and --end-date are required (via CLI or --config-json).")
    return args


def build_signal_and_score(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    flat_lb: int,
    flat_cap: float,
    price_lb: int,
    price_min: float,
    vol_s: int,
    vol_l: int,
    vol_min: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prior_end = close.shift(price_lb)
    prior_start = close.shift(price_lb + flat_lb)
    flat_ret = (prior_end / prior_start) - 1.0
    flat_ok = flat_ret.abs() <= flat_cap

    price_ratio = close / close.shift(price_lb)
    price_ok = price_ratio >= price_min

    vol_short = volume.rolling(vol_s, min_periods=vol_s).mean()
    vol_long = volume.rolling(vol_l, min_periods=vol_l).mean()
    vol_ratio = vol_short / vol_long.replace(0.0, np.nan)
    vol_ok = vol_ratio >= vol_min

    signal = (flat_ok & price_ok & vol_ok).astype(float)

    flat_strength = ((flat_cap - flat_ret.abs()) / max(flat_cap, 1e-12)).clip(lower=0.0, upper=1.0)
    price_excess = (price_ratio / price_min - 1.0).clip(lower=0.0)
    vol_excess = (vol_ratio / vol_min - 1.0).clip(lower=0.0)
    score = flat_strength * price_excess * vol_excess
    return signal, score


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    forward_days = GrinoldDiagnostics.parse_forward_days(args.forward_days)
    params = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "universe_source": args.universe_source,
        "universe_size": int(args.universe_size),
        "benchmark_symbol": str(args.benchmark_symbol).upper(),
        "flat_lookback_days": int(args.flat_lookback_days),
        "flat_max_abs_return": float(args.flat_max_abs_return),
        "price_lookback_days": int(args.price_lookback_days),
        "price_ratio_min": float(args.price_ratio_min),
        "vol_short_days": int(args.vol_short_days),
        "vol_long_days": int(args.vol_long_days),
        "vol_ratio_min": float(args.vol_ratio_min),
        "forward_days": forward_days,
        "weighting_mode": str(args.weighting_mode),
        "top_k": int(args.top_k),
    }
    run_manager = ResearchRunManager(
        out_dir=out_dir,
        params=params,
        run_tag=args.run_tag,
        tag_prefix="fvb",
    )
    run_dir = run_manager.run_dir()

    loader = LocalParquetDataLoader(
        data_root=Path(args.data_root),
        symbol_file=Path(args.symbol_file),
        universe_snapshot_dir=Path(args.snapshot_dir),
    )
    symbols = loader.load_symbols(
        universe_source=args.universe_source,
        portfolio_universe=[],
        portfolio_universe_size=int(args.universe_size),
        benchmark_symbol=args.benchmark_symbol,
        fallback_symbol=args.fallback_symbol,
        asof_date=args.end_date,
    )
    symbols = [s for s in symbols if s.upper() != str(args.benchmark_symbol).upper()]

    max_forward = max(forward_days)
    warmup = int(args.flat_lookback_days + args.price_lookback_days + args.vol_long_days + max_forward + 5)
    load_start = (pd.Timestamp(args.start_date) - pd.Timedelta(days=warmup)).strftime("%Y-%m-%d")

    close = loader.load_close_matrix(symbols, load_start, args.end_date)
    volume = loader.load_volume_matrix(symbols, load_start, args.end_date)

    common_cols = [c for c in close.columns if c in volume.columns]
    close = close[common_cols].sort_index()
    volume = volume[common_cols].sort_index()

    signal, score = build_signal_and_score(
        close=close,
        volume=volume,
        flat_lb=int(args.flat_lookback_days),
        flat_cap=float(args.flat_max_abs_return),
        price_lb=int(args.price_lookback_days),
        price_min=float(args.price_ratio_min),
        vol_s=int(args.vol_short_days),
        vol_l=int(args.vol_long_days),
        vol_min=float(args.vol_ratio_min),
    )

    mask_window = (close.index >= pd.Timestamp(args.start_date)) & (close.index <= pd.Timestamp(args.end_date))
    signal = signal.loc[mask_window]
    score = score.loc[mask_window]
    close_eval = close.loc[mask_window]

    diagnostics = GrinoldDiagnostics(
        weighting_mode=str(args.weighting_mode),
        top_k=int(args.top_k),
    )
    summary_rows: list[dict[str, Any]] = []
    by_date_rows: list[pd.DataFrame] = []

    for h in forward_days:
        fwd_ret = (close_eval.shift(-h) / close_eval) - 1.0
        row, by_date = diagnostics.evaluate_horizon(
            signal=signal,
            score=score,
            fwd_ret=fwd_ret,
            horizon_days=h,
        )
        summary_rows.append(row)
        by_date_rows.append(by_date)

    summary_df = pd.DataFrame(summary_rows).sort_values("horizon_days")
    by_date_df = pd.concat(by_date_rows, ignore_index=True) if by_date_rows else pd.DataFrame()

    summary_path = run_dir / "summary.csv"
    by_date_path = run_dir / "by_date.csv"
    summary_df.to_csv(summary_path, index=False)
    if bool(args.save_by_date):
        by_date_df.to_csv(by_date_path, index=False)

    params_path = run_manager.write_params(extra={"symbols_used": int(close.shape[1]), "load_start": load_start})
    manifest_path = run_manager.write_manifest(
        artifacts={
            "summary_csv": str(summary_path),
            "by_date_csv": str(by_date_path) if bool(args.save_by_date) else None,
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] symbols used: {close.shape[1]}")
    print(f"[ok] summary: {summary_path}")
    if bool(args.save_by_date):
        print(f"[ok] by-date: {by_date_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
