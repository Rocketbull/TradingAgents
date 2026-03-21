from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common import GrinoldDiagnostics, ResearchRunManager
from research.sector_momentum_top2_sector import (
    _find_latest_fundamentals_csv,
    _load_sector_map_from_fundamentals,
)
from tradingagents.backtest.data_loader import LocalParquetDataLoader
from tradingagents.dataflows.yfinance_classification import (
    DEFAULT_CLASSIFICATION_CACHE,
    build_symbol_maps,
)

try:
    from alphalens import performance, utils
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "alphalens-reloaded is required. Install with: "
        ".conda/tradingagents/bin/pip install alphalens-reloaded"
    ) from exc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Signal research for sector-relative 3M momentum: long top-K per sector monthly, "
            "with both Grinold diagnostics and Alphalens diagnostics."
        )
    )
    p.add_argument("--start-date", default="2021-03-01", help="YYYY-MM-DD")
    p.add_argument("--end-date", default="2026-02-28", help="YYYY-MM-DD")
    p.add_argument(
        "--universe-source",
        default="sp500_snapshot",
        choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"],
    )
    p.add_argument("--universe-size", type=int, default=500)
    p.add_argument("--symbol-file", default="data/universe/sp500/current/sp500_symbols.txt")
    p.add_argument("--snapshot-dir", default="data/universe/sp500/snapshots")
    p.add_argument("--data-root", default="data/market")
    p.add_argument("--benchmark-symbol", default="SPY")
    p.add_argument("--fallback-symbol", default="SPY")
    p.add_argument("--fundamentals-dir", default="data/fundamentals/sp500")
    p.add_argument("--classification-cache", default=str(DEFAULT_CLASSIFICATION_CACHE))
    p.add_argument("--min-sector-coverage", type=float, default=0.70)
    p.add_argument("--momentum-lookback-days", type=int, default=63)
    p.add_argument("--top-k-per-sector", type=int, default=2)
    p.add_argument("--forward-steps", default="1,2,4", help="Forward horizons in rebalance steps for Grinold.")
    p.add_argument("--alphalens-periods", default="21,63", help="Forward periods in trading days for Alphalens.")
    p.add_argument("--alphalens-quantiles", type=int, default=5)
    p.add_argument("--alphalens-max-loss", type=float, default=0.35)
    p.add_argument("--out-dir", default="research/output")
    p.add_argument("--run-tag", default=None)
    p.add_argument("--save-factor-data", action="store_true")
    return p.parse_args()


def _parse_int_list(raw: str) -> list[int]:
    out: list[int] = []
    for token in str(raw).split(","):
        t = token.strip()
        if not t:
            continue
        val = int(t)
        if val < 1:
            raise ValueError("periods must be >= 1")
        out.append(val)
    if not out:
        raise ValueError("period list cannot be empty")
    return sorted(set(out))


def _monthly_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    keys = index.to_series().dt.to_period("M")
    return [group.iloc[-1] for _, group in index.to_series().groupby(keys)]


def _sector_relative_scores_and_signal(
    momentum_row: pd.Series,
    sector_map: dict[str, str],
    top_k_per_sector: int,
) -> tuple[pd.Series, pd.Series]:
    scores = pd.Series(0.0, index=momentum_row.index, dtype=float)
    signal = pd.Series(0.0, index=momentum_row.index, dtype=float)
    by_sector: dict[str, list[tuple[str, float]]] = {}
    for sym, val in momentum_row.dropna().items():
        s = sector_map.get(str(sym).upper())
        if isinstance(s, str) and s.strip():
            by_sector.setdefault(s.strip(), []).append((str(sym).upper(), float(val)))

    for _, pairs in by_sector.items():
        ranked = sorted(pairs, key=lambda x: x[1], reverse=True)
        n = len(ranked)
        if n == 0:
            continue
        for i, (sym, _) in enumerate(ranked, start=1):
            # Sector-relative score in [0, 1], highest for best momentum in sector.
            sc = 1.0 if n == 1 else float(1.0 - ((i - 1) / (n - 1)))
            scores.loc[sym] = sc
        for sym, _ in ranked[: max(1, int(top_k_per_sector))]:
            signal.loc[sym] = 1.0
    return scores, signal


def _build_signal_panels(
    close_eval: pd.DataFrame,
    sector_map: dict[str, str],
    mom_lb: int,
    top_k_per_sector: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    momentum = (close_eval / close_eval.shift(int(mom_lb))) - 1.0
    rebalance_dates = _monthly_rebalance_dates(close_eval.index)
    score_rows: list[pd.Series] = []
    signal_rows: list[pd.Series] = []
    close_rows: list[pd.Series] = []
    for dt in rebalance_dates:
        m_row = momentum.loc[dt]
        score_row, signal_row = _sector_relative_scores_and_signal(
            momentum_row=m_row,
            sector_map=sector_map,
            top_k_per_sector=int(top_k_per_sector),
        )
        if int(signal_row.sum()) <= 0:
            continue
        score_row.name = dt
        signal_row.name = dt
        close_row = close_eval.loc[dt].copy()
        close_row.name = dt
        score_rows.append(score_row)
        signal_rows.append(signal_row)
        close_rows.append(close_row)

    if not score_rows:
        raise ValueError("No rebalance rows with valid sector selections.")
    score_df = pd.DataFrame(score_rows).sort_index().fillna(0.0)
    signal_df = pd.DataFrame(signal_rows).sort_index().fillna(0.0)
    close_rebal = pd.DataFrame(close_rows).sort_index()
    return score_df, signal_df, close_rebal


def _build_daily_factor_scores(
    close_eval: pd.DataFrame,
    sector_map: dict[str, str],
    mom_lb: int,
    top_k_per_sector: int,
) -> pd.DataFrame:
    momentum = (close_eval / close_eval.shift(int(mom_lb))) - 1.0
    rows: list[pd.Series] = []
    for dt in momentum.index:
        m_row = momentum.loc[dt]
        if m_row.notna().sum() < 2:
            continue
        score_row, _ = _sector_relative_scores_and_signal(
            momentum_row=m_row,
            sector_map=sector_map,
            top_k_per_sector=int(top_k_per_sector),
        )
        score_row.name = dt
        rows.append(score_row)
    if not rows:
        raise ValueError("No daily factor rows generated for Alphalens.")
    return pd.DataFrame(rows).sort_index().fillna(0.0)


def _load_sector_map(symbols: list[str], args: argparse.Namespace) -> tuple[dict[str, str], str, float]:
    fundamentals_csv = _find_latest_fundamentals_csv(Path(args.fundamentals_dir))
    if fundamentals_csv is not None:
        sector_map = _load_sector_map_from_fundamentals(fundamentals_csv, symbols)
        coverage = float(len(sector_map)) / float(max(1, len(symbols)))
        if sector_map and coverage >= float(args.min_sector_coverage):
            return sector_map, str(fundamentals_csv), coverage
    sector_map, _ = build_symbol_maps(
        symbols=symbols,
        path=Path(args.classification_cache),
        fetch_missing=False,
    )
    coverage = float(len(sector_map)) / float(max(1, len(symbols)))
    return sector_map, str(args.classification_cache), coverage


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    forward_steps = _parse_int_list(args.forward_steps)
    alphalens_periods = tuple(_parse_int_list(args.alphalens_periods))

    params = {
        "script": "signal_sector_momentum_top2",
        "start_date": str(args.start_date),
        "end_date": str(args.end_date),
        "universe_source": str(args.universe_source),
        "universe_size": int(args.universe_size),
        "momentum_lookback_days": int(args.momentum_lookback_days),
        "top_k_per_sector": int(args.top_k_per_sector),
        "forward_steps": list(forward_steps),
        "alphalens_periods": list(alphalens_periods),
        "alphalens_quantiles": int(args.alphalens_quantiles),
        "alphalens_max_loss": float(args.alphalens_max_loss),
    }
    run_manager = ResearchRunManager(
        out_dir=out_dir,
        params=params,
        run_tag=args.run_tag,
        tag_prefix="sig_sector_mom_top2",
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
        benchmark_symbol=str(args.benchmark_symbol).upper(),
        fallback_symbol=str(args.fallback_symbol).upper(),
        asof_date=str(args.end_date),
    )
    benchmark = str(args.benchmark_symbol).upper()
    symbols = [s for s in symbols if s.upper() != benchmark]

    mom_lb = int(args.momentum_lookback_days)
    load_start = (pd.Timestamp(args.start_date) - pd.Timedelta(days=int(mom_lb * 2 + max(alphalens_periods) + 10))).strftime("%Y-%m-%d")
    close = loader.load_close_matrix(symbols, load_start, str(args.end_date)).sort_index()
    close_eval = close[(close.index >= pd.Timestamp(args.start_date)) & (close.index <= pd.Timestamp(args.end_date))]
    symbols_eval = list(close_eval.columns)

    sector_map, sector_source, sector_coverage = _load_sector_map(symbols_eval, args)
    if not sector_map:
        raise ValueError("No sector mapping available for evaluated symbols.")

    score_df, signal_df, close_rebal = _build_signal_panels(
        close_eval=close_eval,
        sector_map=sector_map,
        mom_lb=mom_lb,
        top_k_per_sector=int(args.top_k_per_sector),
    )

    # Repo Grinold diagnostics on rebalance-step horizons.
    grinold = GrinoldDiagnostics(weighting_mode="long_only", top_k=int(signal_df.sum(axis=1).median()))
    repo_summary_rows: list[dict[str, Any]] = []
    repo_by_date_rows: list[pd.DataFrame] = []
    for h in forward_steps:
        fwd_ret = (close_rebal.shift(-h) / close_rebal) - 1.0
        row, by_date = grinold.evaluate_horizon(
            signal=signal_df,
            score=score_df,
            fwd_ret=fwd_ret,
            horizon_days=h,
        )
        row["horizon_rebalance_steps"] = int(h)
        repo_summary_rows.append(row)
        repo_by_date_rows.append(by_date)
    repo_summary = pd.DataFrame(repo_summary_rows).sort_values("horizon_rebalance_steps")
    repo_by_date = pd.concat(repo_by_date_rows, ignore_index=True) if repo_by_date_rows else pd.DataFrame()

    # Alphalens diagnostics on daily sector-relative score as factor.
    factor_daily = _build_daily_factor_scores(
        close_eval=close_eval,
        sector_map=sector_map,
        mom_lb=mom_lb,
        top_k_per_sector=int(args.top_k_per_sector),
    )
    factor_series = factor_daily.stack().rename("factor")
    factor_series.index = factor_series.index.set_names(["date", "asset"])
    prices = close_eval.reindex(columns=factor_daily.columns).sort_index().ffill()
    factor_data = utils.get_clean_factor_and_forward_returns(
        factor=factor_series,
        prices=prices,
        quantiles=int(args.alphalens_quantiles),
        periods=alphalens_periods,
        max_loss=float(args.alphalens_max_loss),
    )
    period_cols = [c for c in factor_data.columns if c.endswith("D")]
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
    q_top = int(args.alphalens_quantiles)
    for p in alphalens_periods:
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
    alphalens_turnover = pd.DataFrame(turnover_rows).sort_values("period_days")
    alphalens_summary = pd.DataFrame(
        [
            {
                "period": col,
                "avg_rank_ic": float(ic_mean.get(col, pd.NA)),
                "ic_std": float(ic_std.get(col, pd.NA)),
                "ic_ir": float(ic_ir.get(col, pd.NA)),
                "factor_points_clean": int(len(factor_data)),
                "factor_points_raw": int(len(factor_series)),
                "retained_ratio": float(len(factor_data) / max(1, len(factor_series))),
            }
            for col in period_cols
        ]
    )

    repo_summary_path = run_dir / "repo_summary.csv"
    repo_by_date_path = run_dir / "repo_by_date.csv"
    alphalens_summary_path = run_dir / "alphalens_summary.csv"
    alphalens_ic_path = run_dir / "alphalens_ic_by_date.csv"
    alphalens_mean_ret_path = run_dir / "alphalens_mean_return_by_quantile.csv"
    alphalens_std_err_path = run_dir / "alphalens_std_error_by_quantile.csv"
    alphalens_turnover_path = run_dir / "alphalens_turnover_autocorr.csv"
    repo_summary.to_csv(repo_summary_path, index=False)
    if not repo_by_date.empty:
        repo_by_date.to_csv(repo_by_date_path, index=False)
    alphalens_summary.to_csv(alphalens_summary_path, index=False)
    ic_by_date.to_csv(alphalens_ic_path, index=True)
    mean_ret_q.to_csv(alphalens_mean_ret_path, index=True)
    std_err_q.to_csv(alphalens_std_err_path, index=True)
    alphalens_turnover.to_csv(alphalens_turnover_path, index=False)

    factor_data_path = run_dir / "factor_data.parquet"
    if bool(args.save_factor_data):
        factor_data.to_parquet(factor_data_path, index=True)

    params_path = run_manager.write_params(
        extra={
            "symbols_used": int(close_eval.shape[1]),
            "rebalance_points": int(score_df.shape[0]),
            "sector_source": sector_source,
            "sector_coverage": sector_coverage,
            "load_start": load_start,
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "repo_summary_csv": str(repo_summary_path),
            "repo_by_date_csv": str(repo_by_date_path) if not repo_by_date.empty else None,
            "alphalens_summary_csv": str(alphalens_summary_path),
            "alphalens_ic_by_date_csv": str(alphalens_ic_path),
            "alphalens_mean_return_by_quantile_csv": str(alphalens_mean_ret_path),
            "alphalens_std_error_by_quantile_csv": str(alphalens_std_err_path),
            "alphalens_turnover_autocorr_csv": str(alphalens_turnover_path),
            "factor_data_parquet": str(factor_data_path) if bool(args.save_factor_data) else None,
            "params_json": str(params_path),
        }
    )

    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] symbols used: {close_eval.shape[1]}")
    print(f"[ok] rebalance points: {score_df.shape[0]}")
    print(f"[ok] sector source: {sector_source} (coverage={sector_coverage:.3f})")
    print(f"[ok] repo summary: {repo_summary_path}")
    print(f"[ok] alphalens summary: {alphalens_summary_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print("[repo]")
    print(repo_summary.to_string(index=False))
    print("[alphalens]")
    print(alphalens_summary.to_string(index=False))


if __name__ == "__main__":
    main()
