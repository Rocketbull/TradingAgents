from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common import GrinoldDiagnostics, ResearchRunManager
from tradingagents.backtest.data_loader import LocalParquetDataLoader


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
        description="Research signal: rank stocks by corr(GLD) - corr(BTC-USD)."
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
    parser.add_argument("--symbol-file", default="data/universe/sp500/current/sp500_symbols.txt")
    parser.add_argument("--snapshot-dir", default="data/universe/sp500/snapshots")
    parser.add_argument("--data-root", default="data/market")
    parser.add_argument("--benchmark-symbol", default="SPY")
    parser.add_argument("--fallback-symbol", default="SPY")

    parser.add_argument("--risk-symbol", default="BTC-USD", help="Risk proxy symbol.")
    parser.add_argument("--defensive-symbol", default="GLD", help="Defensive proxy symbol.")
    parser.add_argument("--corr-lookback-days", type=int, default=60, help="Rolling corr window.")
    parser.add_argument("--defensive-weight", type=float, default=1.0)
    parser.add_argument("--risk-weight", type=float, default=1.0)
    parser.add_argument(
        "--top-quantile",
        type=float,
        default=0.2,
        help="Signal mask threshold by per-date score quantile (0,1].",
    )

    parser.add_argument("--forward-days", default="5,20")
    parser.add_argument(
        "--weighting-mode",
        default="long_short",
        choices=["long_short", "long_only"],
        help="Portfolio construction for TC/BR/IR diagnostics.",
    )
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--ic-gate-lookback", type=int, default=26)
    parser.add_argument("--ic-gate-min-mean", type=float, default=None)
    parser.add_argument("--ic-gate-use-abs-mean", action="store_true")
    parser.add_argument("--ic-gate-min-tstat", type=float, default=None)
    parser.add_argument("--ic-gate-min-hit-rate", type=float, default=None)
    parser.add_argument("--ic-gate-min-samples", type=int, default=12)
    parser.add_argument("--out-dir", default="research/output")
    parser.add_argument("--run-tag", default=None, help="Optional deterministic run tag override.")
    parser.add_argument("--save-by-date", action="store_true", help="Persist per-date diagnostics CSV.")

    parser.set_defaults(**config_defaults)
    args = parser.parse_args(remaining)
    if not args.start_date or not args.end_date:
        parser.error("--start-date and --end-date are required (via CLI or --config-json).")
    if not (0.0 < float(args.top_quantile) <= 1.0):
        parser.error("--top-quantile must be in (0, 1].")
    if int(args.corr_lookback_days) < 5:
        parser.error("--corr-lookback-days must be >= 5.")
    return args


def build_signal_and_score(
    close: pd.DataFrame,
    risk_symbol: str,
    defensive_symbol: str,
    lookback: int,
    defensive_weight: float,
    risk_weight: float,
    top_quantile: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ret = close.pct_change()
    risk_ret = ret[risk_symbol]
    defensive_ret = ret[defensive_symbol]

    corr_risk = ret.rolling(lookback, min_periods=lookback).corr(risk_ret)
    corr_defensive = ret.rolling(lookback, min_periods=lookback).corr(defensive_ret)

    score = (defensive_weight * corr_defensive) - (risk_weight * corr_risk)
    threshold = score.quantile(1.0 - top_quantile, axis=1)
    signal = score.ge(threshold, axis=0).astype(float)

    score = score.drop(columns=[risk_symbol, defensive_symbol], errors="ignore")
    signal = signal.drop(columns=[risk_symbol, defensive_symbol], errors="ignore")
    return signal, score


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    forward_days = GrinoldDiagnostics.parse_forward_days(args.forward_days)
    risk_symbol = str(args.risk_symbol).upper()
    defensive_symbol = str(args.defensive_symbol).upper()
    params = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "universe_source": args.universe_source,
        "universe_size": int(args.universe_size),
        "benchmark_symbol": str(args.benchmark_symbol).upper(),
        "risk_symbol": risk_symbol,
        "defensive_symbol": defensive_symbol,
        "corr_lookback_days": int(args.corr_lookback_days),
        "defensive_weight": float(args.defensive_weight),
        "risk_weight": float(args.risk_weight),
        "top_quantile": float(args.top_quantile),
        "forward_days": forward_days,
        "weighting_mode": str(args.weighting_mode),
        "top_k": int(args.top_k),
        "ic_gate_lookback": int(args.ic_gate_lookback),
        "ic_gate_min_mean": args.ic_gate_min_mean,
        "ic_gate_use_abs_mean": bool(args.ic_gate_use_abs_mean),
        "ic_gate_min_tstat": args.ic_gate_min_tstat,
        "ic_gate_min_hit_rate": args.ic_gate_min_hit_rate,
        "ic_gate_min_samples": int(args.ic_gate_min_samples),
    }
    run_manager = ResearchRunManager(
        out_dir=out_dir,
        params=params,
        run_tag=args.run_tag,
        tag_prefix="btc_gld_corr",
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
    symbols = list(dict.fromkeys([risk_symbol, defensive_symbol] + symbols))

    max_forward = max(forward_days)
    warmup = int(args.corr_lookback_days + max_forward + 10)
    load_start = (pd.Timestamp(args.start_date) - pd.Timedelta(days=warmup)).strftime("%Y-%m-%d")

    close = loader.load_close_matrix(symbols, load_start, args.end_date).sort_index()
    if risk_symbol not in close.columns:
        raise ValueError(f"Missing {risk_symbol} local data under {args.data_root}.")
    if defensive_symbol not in close.columns:
        raise ValueError(f"Missing {defensive_symbol} local data under {args.data_root}.")

    signal, score = build_signal_and_score(
        close=close,
        risk_symbol=risk_symbol,
        defensive_symbol=defensive_symbol,
        lookback=int(args.corr_lookback_days),
        defensive_weight=float(args.defensive_weight),
        risk_weight=float(args.risk_weight),
        top_quantile=float(args.top_quantile),
    )

    mask_window = (close.index >= pd.Timestamp(args.start_date)) & (close.index <= pd.Timestamp(args.end_date))
    close_eval = close.loc[mask_window].drop(columns=[risk_symbol, defensive_symbol], errors="ignore")
    signal = signal.loc[mask_window].reindex(columns=close_eval.columns)
    score = score.loc[mask_window].reindex(columns=close_eval.columns)

    diagnostics = GrinoldDiagnostics(
        weighting_mode=str(args.weighting_mode),
        top_k=int(args.top_k),
        ic_gate_lookback=int(args.ic_gate_lookback),
        ic_gate_min_mean=args.ic_gate_min_mean,
        ic_gate_use_abs_mean=bool(args.ic_gate_use_abs_mean),
        ic_gate_min_tstat=args.ic_gate_min_tstat,
        ic_gate_min_hit_rate=args.ic_gate_min_hit_rate,
        ic_gate_min_samples=int(args.ic_gate_min_samples),
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

    params_path = run_manager.write_params(
        extra={
            "symbols_used_total": int(close.shape[1]),
            "symbols_used_spx_only": int(close_eval.shape[1]),
            "load_start": load_start,
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "summary_csv": str(summary_path),
            "by_date_csv": str(by_date_path) if bool(args.save_by_date) else None,
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] symbols used (incl. anchors): {close.shape[1]}")
    print(f"[ok] symbols scored (SPX): {close_eval.shape[1]}")
    print(f"[ok] summary: {summary_path}")
    if bool(args.save_by_date):
        print(f"[ok] by-date: {by_date_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
