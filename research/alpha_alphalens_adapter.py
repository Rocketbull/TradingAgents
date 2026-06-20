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

from research.common import ResearchRunManager
from activeportfolio.alpha import AlphaModel, apply_alpha_profile
from activeportfolio.backtest.data_loader import LocalParquetDataLoader
from activeportfolio.default_config import DEFAULT_CONFIG

try:
    from alphalens import performance, utils
except Exception as exc:  # pragma: no cover - explicit runtime dependency error.
    raise RuntimeError(
        "alphalens-reloaded is required. Install with: "
        "conda run -n activepm python -m pip install alphalens-reloaded"
    ) from exc


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
        description="Adapter: run Alphalens diagnostics for one factor from Active Portfolio alpha profiles."
    )
    parser.add_argument("--config-json", default=pre_args.config_json, help="Optional JSON config file.")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--alpha-profile", default="diversified_sp500_v2_tilt")
    parser.add_argument("--factor-name", default="mom_3m", help="Signal name in alpha profile/registry.")
    parser.add_argument(
        "--periods",
        default="5,20",
        help="Forward return periods in trading days, comma-separated (for example: 1,5,20).",
    )
    parser.add_argument("--quantiles", type=int, default=5)
    parser.add_argument("--max-loss", type=float, default=0.35)
    parser.add_argument("--date-step", type=int, default=1, help="Use every Nth trading date for factor scoring.")
    parser.add_argument(
        "--universe-source",
        default="sp500_snapshot",
        choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"],
    )
    parser.add_argument("--universe-size", type=int, default=200)
    parser.add_argument("--symbol-file", default="data/universe/sp500/current/sp500_symbols.txt")
    parser.add_argument("--snapshot-dir", default="data/universe/sp500/snapshots")
    parser.add_argument("--data-root", default="data/market")
    parser.add_argument("--benchmark-symbol", default="SPY")
    parser.add_argument("--fallback-symbol", default="SPY")
    parser.add_argument("--out-dir", default="research/output")
    parser.add_argument("--run-tag", default=None)
    parser.add_argument("--save-factor-data", action="store_true")

    parser.set_defaults(**config_defaults)
    args = parser.parse_args(remaining)
    if not args.start_date or not args.end_date:
        parser.error("--start-date and --end-date are required (via CLI or --config-json).")
    if int(args.quantiles) < 2:
        parser.error("--quantiles must be >= 2.")
    if int(args.date_step) < 1:
        parser.error("--date-step must be >= 1.")
    if not (0.0 <= float(args.max_loss) <= 1.0):
        parser.error("--max-loss must be in [0, 1].")
    return args


def parse_periods(raw: str) -> tuple[int, ...]:
    vals: list[int] = []
    for token in str(raw).split(","):
        t = token.strip()
        if not t:
            continue
        v = int(t)
        if v < 1:
            raise ValueError("All periods must be >= 1.")
        vals.append(v)
    if not vals:
        raise ValueError("periods cannot be empty.")
    return tuple(sorted(set(vals)))


def build_factor_wide(
    model: AlphaModel,
    factor_name: str,
    closes: pd.DataFrame,
    volumes: pd.DataFrame | None,
    start_date: str,
    end_date: str,
    date_step: int,
) -> pd.DataFrame:
    eval_idx = closes.index[(closes.index >= pd.Timestamp(start_date)) & (closes.index <= pd.Timestamp(end_date))]
    eval_idx = eval_idx[:: int(date_step)]
    rows: list[pd.Series] = []
    for dt in eval_idx:
        hist_close = closes.loc[:dt]
        hist_volume = volumes.loc[:dt] if volumes is not None else None
        comps = model.component_scores(hist_close, volumes=hist_volume, signals=[factor_name])
        s = comps[factor_name].copy()
        s.name = dt
        rows.append(s)
    if not rows:
        raise ValueError("No factor rows were generated for requested window.")
    out = pd.DataFrame(rows).sort_index().replace([float("inf"), float("-inf")], pd.NA).fillna(0.0)
    out.index.name = "date"
    return out


def main() -> None:
    args = parse_args()
    periods = parse_periods(args.periods)

    cfg = DEFAULT_CONFIG.copy()
    cfg = apply_alpha_profile(cfg, str(args.alpha_profile), overwrite=True)
    model = AlphaModel.from_config(cfg)
    factor_name = str(args.factor_name)
    available = model.available_signals()
    if factor_name not in available:
        raise ValueError(f"Unknown factor '{factor_name}'. Available: {available}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    params = {
        "start_date": str(args.start_date),
        "end_date": str(args.end_date),
        "alpha_profile": str(args.alpha_profile),
        "factor_name": factor_name,
        "periods": list(periods),
        "quantiles": int(args.quantiles),
        "max_loss": float(args.max_loss),
        "date_step": int(args.date_step),
        "universe_source": str(args.universe_source),
        "universe_size": int(args.universe_size),
        "benchmark_symbol": str(args.benchmark_symbol).upper(),
    }
    run_manager = ResearchRunManager(
        out_dir=out_dir,
        params=params,
        run_tag=args.run_tag,
        tag_prefix="alphalens",
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

    warmup = int(max(model.long_lookback + 5, model.vol_lookback + 5) + max(periods))
    load_start = (pd.Timestamp(args.start_date) - pd.Timedelta(days=warmup)).strftime("%Y-%m-%d")

    close = loader.load_close_matrix(symbols, load_start, args.end_date).sort_index()
    close = close.drop(columns=[benchmark], errors="ignore")
    try:
        volume = loader.load_volume_matrix(symbols, load_start, args.end_date).sort_index()
        volume = volume.reindex(columns=close.columns)
    except Exception:
        volume = None

    factor_wide = build_factor_wide(
        model=model,
        factor_name=factor_name,
        closes=close,
        volumes=volume,
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        date_step=int(args.date_step),
    )

    prices = close.reindex(columns=factor_wide.columns).sort_index().ffill()
    factor_series = factor_wide.stack().rename("factor")
    factor_series.index = factor_series.index.set_names(["date", "asset"])

    try:
        factor_data = utils.get_clean_factor_and_forward_returns(
            factor=factor_series,
            prices=prices,
            quantiles=int(args.quantiles),
            periods=periods,
            max_loss=float(args.max_loss),
        )
    except ValueError as exc:
        msg = str(exc)
        if "does not conform to passed frequency" in msg:
            raise ValueError(
                "Alphalens frequency validation failed. "
                "Use --date-step 1 (daily factor observations) for reliable forward-return alignment."
            ) from exc
        raise

    period_cols = [c for c in factor_data.columns if c.endswith("D")]
    if not period_cols:
        raise ValueError("Alphalens factor_data had no forward-return period columns.")

    ic_by_date = performance.factor_information_coefficient(factor_data)
    ic_mean = ic_by_date.mean()
    ic_std = ic_by_date.std(ddof=0)
    ic_ir = ic_mean / ic_std.replace(0.0, pd.NA)

    mean_ret_q, std_err_q = performance.mean_return_by_quantile(
        factor_data=factor_data,
        by_date=False,
        by_group=False,
        demeaned=True,
        group_adjust=False,
    )

    turnover_rows: list[dict[str, Any]] = []
    q_top = int(args.quantiles)
    for p in periods:
        top_turn = performance.quantile_turnover(factor_data["factor_quantile"], quantile=q_top, period=int(p))
        bot_turn = performance.quantile_turnover(factor_data["factor_quantile"], quantile=1, period=int(p))
        rank_auto = performance.factor_rank_autocorrelation(factor_data, period=int(p))
        turnover_rows.append(
            {
                "period_days": int(p),
                "avg_top_quantile_turnover": float(pd.to_numeric(top_turn, errors="coerce").dropna().mean()),
                "avg_bottom_quantile_turnover": float(pd.to_numeric(bot_turn, errors="coerce").dropna().mean()),
                "avg_factor_rank_autocorrelation": float(pd.to_numeric(rank_auto, errors="coerce").dropna().mean()),
            }
        )
    turnover_df = pd.DataFrame(turnover_rows).sort_values("period_days")

    summary_rows: list[dict[str, Any]] = []
    for col in period_cols:
        summary_rows.append(
            {
                "period": col,
                "avg_rank_ic": float(ic_mean.get(col, pd.NA)),
                "ic_std": float(ic_std.get(col, pd.NA)),
                "ic_ir": float(ic_ir.get(col, pd.NA)),
                "factor_points_clean": int(len(factor_data)),
                "factor_points_raw": int(len(factor_series)),
                "retained_ratio": float(len(factor_data) / max(1, len(factor_series))),
            }
        )
    summary_df = pd.DataFrame(summary_rows)

    summary_path = run_dir / "summary.csv"
    ic_by_date_path = run_dir / "ic_by_date.csv"
    mean_ret_q_path = run_dir / "mean_return_by_quantile.csv"
    std_err_q_path = run_dir / "std_error_by_quantile.csv"
    turnover_path = run_dir / "turnover_autocorr.csv"
    summary_df.to_csv(summary_path, index=False)
    ic_by_date.to_csv(ic_by_date_path, index=True)
    mean_ret_q.to_csv(mean_ret_q_path, index=True)
    std_err_q.to_csv(std_err_q_path, index=True)
    turnover_df.to_csv(turnover_path, index=False)

    factor_data_path = run_dir / "factor_data.parquet"
    if bool(args.save_factor_data):
        factor_data.to_parquet(factor_data_path, index=True)

    params_path = run_manager.write_params(
        extra={
            "symbols_used": int(close.shape[1]),
            "factor_dates": int(factor_wide.shape[0]),
            "load_start": load_start,
            "volume_available": bool(volume is not None),
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "summary_csv": str(summary_path),
            "ic_by_date_csv": str(ic_by_date_path),
            "mean_return_by_quantile_csv": str(mean_ret_q_path),
            "std_error_by_quantile_csv": str(std_err_q_path),
            "turnover_autocorr_csv": str(turnover_path),
            "factor_data_parquet": str(factor_data_path) if bool(args.save_factor_data) else None,
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] alpha_profile: {args.alpha_profile}")
    print(f"[ok] factor: {factor_name}")
    print(f"[ok] symbols used: {close.shape[1]}")
    print(f"[ok] factor dates: {factor_wide.shape[0]}")
    print(f"[ok] summary: {summary_path}")
    print(f"[ok] ic_by_date: {ic_by_date_path}")
    print(f"[ok] quantile mean return: {mean_ret_q_path}")
    print(f"[ok] turnover/autocorr: {turnover_path}")
    if bool(args.save_factor_data):
        print(f"[ok] factor_data: {factor_data_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
