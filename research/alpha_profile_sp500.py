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
from activeportfolio.alpha import AlphaModel, apply_alpha_profile
from activeportfolio.backtest.data_loader import LocalParquetDataLoader
from activeportfolio.default_config import DEFAULT_CONFIG


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
        description="Evaluate alpha profile signals on SP500 universe using Grinold diagnostics."
    )
    parser.add_argument("--config-json", default=pre_args.config_json, help="Optional JSON config file.")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--alpha-profile", default="diversified_sp500_v1")
    parser.add_argument(
        "--universe-source",
        default="sp500_snapshot",
        choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"],
    )
    parser.add_argument("--universe-size", type=int, default=500)
    parser.add_argument("--symbol-file", default="data/universe/sp500/current/sp500_symbols.txt")
    parser.add_argument("--snapshot-dir", default="data/universe/sp500/snapshots")
    parser.add_argument("--data-root", default="data/market")
    parser.add_argument("--benchmark-symbol", default="SPY")
    parser.add_argument("--fallback-symbol", default="SPY")
    parser.add_argument("--date-step", type=int, default=5, help="Use every Nth trading date for scoring.")
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
    )
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--out-dir", default="research/output")
    parser.add_argument("--run-tag", default=None)
    parser.add_argument("--save-by-date", action="store_true")

    parser.set_defaults(**config_defaults)
    args = parser.parse_args(remaining)
    if not args.start_date or not args.end_date:
        parser.error("--start-date and --end-date are required (via CLI or --config-json).")
    if int(args.date_step) < 1:
        parser.error("--date-step must be >= 1.")
    if not (0.0 < float(args.top_quantile) <= 1.0):
        parser.error("--top-quantile must be in (0, 1].")
    return args


def _build_score_panels(
    model: AlphaModel,
    closes: pd.DataFrame,
    volumes: pd.DataFrame | None,
    signals: list[str],
    start_date: str,
    end_date: str,
    date_step: int,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    eval_idx = closes.index[(closes.index >= pd.Timestamp(start_date)) & (closes.index <= pd.Timestamp(end_date))]
    eval_idx = eval_idx[:: int(date_step)]

    factor_rows: dict[str, list[pd.Series]] = {name: [] for name in signals}
    combo_rows: list[pd.Series] = []
    used_dates: list[pd.Timestamp] = []

    for dt in eval_idx:
        hist_close = closes.loc[:dt]
        hist_volume = volumes.loc[:dt] if volumes is not None else None
        components = model.component_scores(hist_close, volumes=hist_volume, signals=signals)
        combo = model.score(hist_close, volumes=hist_volume, signals=signals)

        for name in signals:
            row = components[name].copy()
            row.name = dt
            factor_rows[name].append(row)
        combo = combo.copy()
        combo.name = dt
        combo_rows.append(combo)
        used_dates.append(dt)

    score_panels = {
        name: pd.DataFrame(rows).reindex(index=used_dates).sort_index().fillna(0.0)
        for name, rows in factor_rows.items()
    }
    combo_df = pd.DataFrame(combo_rows).reindex(index=used_dates).sort_index().fillna(0.0)
    close_eval = closes.reindex(index=used_dates).sort_index().ffill()
    return score_panels, combo_df, close_eval


def _signal_mask_from_quantile(scores: pd.DataFrame, top_quantile: float) -> pd.DataFrame:
    threshold = scores.quantile(1.0 - float(top_quantile), axis=1)
    return scores.ge(threshold, axis=0).astype(float)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    forward_days = GrinoldDiagnostics.parse_forward_days(args.forward_days)

    cfg = DEFAULT_CONFIG.copy()
    cfg = apply_alpha_profile(cfg, str(args.alpha_profile), overwrite=True)
    model = AlphaModel.from_config(cfg)
    signals = list(cfg.get("alpha_signals", model.available_signals()))

    params = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "alpha_profile": str(args.alpha_profile),
        "signals": signals,
        "universe_source": args.universe_source,
        "universe_size": int(args.universe_size),
        "benchmark_symbol": str(args.benchmark_symbol).upper(),
        "date_step": int(args.date_step),
        "top_quantile": float(args.top_quantile),
        "forward_days": forward_days,
        "weighting_mode": str(args.weighting_mode),
        "top_k": int(args.top_k),
    }
    run_manager = ResearchRunManager(
        out_dir=out_dir,
        params=params,
        run_tag=args.run_tag,
        tag_prefix="alpha_profile_sp500",
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
    benchmark = str(args.benchmark_symbol).upper()
    symbols = [s for s in symbols if s.upper() != benchmark]

    warmup = int(max(model.long_lookback + 5, model.vol_lookback + 5) + max(forward_days))
    load_start = (pd.Timestamp(args.start_date) - pd.Timedelta(days=warmup)).strftime("%Y-%m-%d")
    close = loader.load_close_matrix(symbols, load_start, args.end_date).sort_index()
    close = close.drop(columns=[benchmark], errors="ignore")
    try:
        volume = loader.load_volume_matrix(symbols, load_start, args.end_date).sort_index()
        volume = volume.reindex(columns=close.columns)
    except Exception:
        volume = None

    score_panels, combo_scores, close_eval = _build_score_panels(
        model=model,
        closes=close,
        volumes=volume,
        signals=signals,
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        date_step=int(args.date_step),
    )

    diagnostics = GrinoldDiagnostics(
        weighting_mode=str(args.weighting_mode),
        top_k=int(args.top_k),
    )

    summary_rows: list[dict[str, Any]] = []
    by_date_frames: list[pd.DataFrame] = []
    for factor_name, scores in list(score_panels.items()) + [("composite", combo_scores)]:
        signal = _signal_mask_from_quantile(scores, float(args.top_quantile))
        for h in forward_days:
            fwd_ret = (close_eval.shift(-h) / close_eval) - 1.0
            row, by_date = diagnostics.evaluate_horizon(
                signal=signal,
                score=scores,
                fwd_ret=fwd_ret,
                horizon_days=h,
            )
            row["factor"] = factor_name
            summary_rows.append(row)
            if not by_date.empty:
                by_date = by_date.copy()
                by_date["factor"] = factor_name
                by_date_frames.append(by_date)

    summary_df = pd.DataFrame(summary_rows).sort_values(["factor", "horizon_days"])
    by_date_df = pd.concat(by_date_frames, ignore_index=True) if by_date_frames else pd.DataFrame()

    summary_path = run_dir / "summary.csv"
    by_date_path = run_dir / "by_date.csv"
    summary_df.to_csv(summary_path, index=False)
    if bool(args.save_by_date):
        by_date_df.to_csv(by_date_path, index=False)

    params_path = run_manager.write_params(
        extra={
            "symbols_used": int(close.shape[1]),
            "dates_evaluated": int(close_eval.shape[0]),
            "load_start": load_start,
            "volume_available": bool(volume is not None),
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
    print(f"[ok] alpha_profile: {args.alpha_profile}")
    print(f"[ok] signals: {signals}")
    print(f"[ok] symbols used: {close.shape[1]}")
    print(f"[ok] dates evaluated: {close_eval.shape[0]}")
    print(f"[ok] summary: {summary_path}")
    if bool(args.save_by_date):
        print(f"[ok] by-date: {by_date_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
