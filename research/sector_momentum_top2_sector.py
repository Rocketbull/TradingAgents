from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common import ResearchRunManager
from tradingagents.backtest.data_loader import LocalParquetDataLoader
from tradingagents.dataflows.yfinance_classification import (
    DEFAULT_CLASSIFICATION_CACHE,
    build_symbol_maps,
)


def parse_args() -> argparse.Namespace:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config-json", default=None, help="Optional JSON config file.")
    pre_args, _ = pre.parse_known_args()

    cfg: dict[str, Any] = {}
    if pre_args.config_json:
        cfg_path = Path(pre_args.config_json)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Config not found: {cfg_path}")
        loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Config JSON must be an object.")
        cfg = loaded

    p = argparse.ArgumentParser(
        description="Sector momentum research: long top-K names per sector by 3M momentum, monthly rebalance."
    )
    p.add_argument("--config-json", default=pre_args.config_json, help="Optional JSON config file.")
    p.add_argument("--start-date", default=cfg.get("start_date", "2021-03-01"), help="YYYY-MM-DD")
    p.add_argument("--end-date", default=cfg.get("end_date", "2026-02-28"), help="YYYY-MM-DD")
    p.add_argument(
        "--universe-source",
        default=cfg.get("universe_source", "sp500_snapshot"),
        choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"],
    )
    p.add_argument("--symbol-file", default=cfg.get("symbol_file", "data/universe/sp500/current/sp500_symbols.txt"))
    p.add_argument("--snapshot-dir", default=cfg.get("snapshot_dir", "data/universe/sp500/snapshots"))
    p.add_argument("--data-root", default=cfg.get("data_root", "data/market"))
    p.add_argument("--benchmark-symbol", default=cfg.get("benchmark_symbol", "SPY"))
    p.add_argument("--fallback-symbol", default=cfg.get("fallback_symbol", "SPY"))
    p.add_argument("--universe-size", type=int, default=int(cfg.get("universe_size", 500)))
    p.add_argument(
        "--momentum-lookback-days",
        type=int,
        default=int(cfg.get("momentum_lookback_days", 63)),
        help="Trading-day lookback for momentum (63 ~= 3 months).",
    )
    p.add_argument(
        "--top-k-per-sector",
        type=int,
        default=int(cfg.get("top_k_per_sector", 2)),
        help="Number of names to long within each sector.",
    )
    p.add_argument(
        "--rebalance-frequency",
        default=str(cfg.get("rebalance_frequency", "monthly")),
        choices=["weekly", "biweekly", "monthly"],
        help="Rebalance schedule frequency.",
    )
    p.add_argument("--transaction-cost-bps", type=float, default=float(cfg.get("transaction_cost_bps", 5.0)))
    p.add_argument("--out-dir", default=cfg.get("out_dir", "research/output"))
    p.add_argument("--run-tag", default=cfg.get("run_tag", None))
    p.add_argument(
        "--fundamentals-dir",
        default=cfg.get("fundamentals_dir", "data/fundamentals/sp500"),
        help="Directory containing sp500_fundamentals_latest.csv.",
    )
    p.add_argument(
        "--classification-cache",
        default=cfg.get("classification_cache", str(DEFAULT_CLASSIFICATION_CACHE)),
        help="Fallback sector classification cache path.",
    )
    p.add_argument(
        "--min-sector-coverage",
        type=float,
        default=float(cfg.get("min_sector_coverage", 0.70)),
        help="Minimum sector coverage ratio required from fundamentals before fallback to classification cache.",
    )
    p.add_argument(
        "--download-fundamentals",
        action="store_true",
        default=bool(cfg.get("download_fundamentals", False)),
        help="Refresh fundamentals using tools/download_fundamentals.py before research run.",
    )
    p.add_argument("--sp500-fetch", action="store_true", default=bool(cfg.get("sp500_fetch", False)))
    p.add_argument("--sleep-seconds", type=float, default=float(cfg.get("sleep_seconds", 0.05)))
    p.add_argument(
        "--fundamentals-limit",
        type=int,
        default=int(cfg.get("fundamentals_limit", 0)),
        help="Optional max symbols for fundamentals refresh (0 = full list).",
    )
    return p.parse_args()


def _find_latest_fundamentals_csv(root: Path) -> Path | None:
    preferred = root / "sp500_fundamentals_latest.csv"
    if preferred.exists():
        return preferred
    candidates = sorted(root.glob("sp500_fundamentals_*.csv"), reverse=True)
    return candidates[0] if candidates else None


def _load_sector_map_from_fundamentals(csv_path: Path, symbols: list[str]) -> dict[str, str]:
    df = pd.read_csv(csv_path)
    if df.empty or "symbol" not in df.columns or "sector" not in df.columns:
        return {}
    d = df[["symbol", "sector"]].copy()
    d["symbol"] = d["symbol"].astype(str).str.upper()
    d["sector"] = d["sector"].astype(str).str.strip()
    d = d[d["symbol"].isin(symbols)]
    d = d[(d["sector"] != "") & (d["sector"].str.lower() != "nan")]
    return {str(r["symbol"]).upper(): str(r["sector"]) for _, r in d.iterrows()}


def _monthly_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    if len(index) == 0:
        return []
    keys = index.to_series().dt.to_period("M")
    return [group.iloc[-1] for _, group in index.to_series().groupby(keys)]


def _rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> list[pd.Timestamp]:
    if len(index) == 0:
        return []
    freq = str(frequency).lower()
    if freq == "monthly":
        return _monthly_rebalance_dates(index)
    if freq == "weekly":
        keys = index.to_series().dt.to_period("W-FRI")
        return [group.iloc[-1] for _, group in index.to_series().groupby(keys)]
    if freq == "biweekly":
        keys = index.to_series().dt.to_period("2W-FRI")
        return [group.iloc[-1] for _, group in index.to_series().groupby(keys)]
    raise ValueError(f"Unsupported rebalance frequency: {frequency}")


def _select_weights_for_date(
    momentum_row: pd.Series,
    sector_map: dict[str, str],
    top_k_per_sector: int,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    by_sector: dict[str, list[tuple[str, float]]] = {}
    for symbol, score in momentum_row.dropna().items():
        sector = sector_map.get(str(symbol).upper())
        if not isinstance(sector, str) or not sector.strip():
            continue
        by_sector.setdefault(sector.strip(), []).append((str(symbol).upper(), float(score)))

    selected: list[dict[str, Any]] = []
    for sector, pairs in by_sector.items():
        ranked = sorted(pairs, key=lambda x: x[1], reverse=True)[: max(1, int(top_k_per_sector))]
        for symbol, score in ranked:
            selected.append({"symbol": symbol, "sector": sector, "mom_3m": float(score)})

    if not selected:
        return {}, []
    w = 1.0 / float(len(selected))
    weights = {row["symbol"]: w for row in selected}
    return weights, selected


def _portfolio_returns_from_weights(
    close_eval: pd.DataFrame,
    rebalance_weights: dict[pd.Timestamp, dict[str, float]],
) -> tuple[pd.Series, pd.DataFrame]:
    daily_ret = close_eval.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    out = pd.Series(0.0, index=daily_ret.index, dtype=float)
    turn_rows: list[dict[str, Any]] = []

    reb_dates = sorted(rebalance_weights.keys())
    prev_w = pd.Series(dtype=float)
    for i, dt in enumerate(reb_dates):
        w = pd.Series(rebalance_weights[dt], dtype=float)
        if w.empty:
            continue
        nxt = reb_dates[i + 1] if i + 1 < len(reb_dates) else daily_ret.index[-1]
        seg_mask = (daily_ret.index > dt) & (daily_ret.index <= nxt)
        if not seg_mask.any():
            continue
        aligned = daily_ret.loc[seg_mask].reindex(columns=w.index).fillna(0.0)
        out.loc[seg_mask] = aligned.mul(w, axis=1).sum(axis=1)

        curr = w.reindex(sorted(set(prev_w.index).union(set(w.index)))).fillna(0.0)
        prev = prev_w.reindex(curr.index).fillna(0.0)
        turnover = float((curr - prev).abs().sum())
        turn_rows.append(
            {
                "rebalance_date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                "selected_names": int((w > 0).sum()),
                "turnover": turnover,
            }
        )
        prev_w = w

    turnover_df = pd.DataFrame(turn_rows)
    return out, turnover_df


def _max_drawdown(nav: pd.Series) -> float:
    running_max = nav.cummax()
    dd = (nav / running_max) - 1.0
    return float(dd.min()) if len(dd) else 0.0


def _run_fundamentals_refresh(args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        "tools/download_fundamentals.py",
        "--symbols-file",
        str(args.symbol_file),
        "--out-dir",
        str(args.fundamentals_dir),
        "--sleep-seconds",
        str(args.sleep_seconds),
        "--overwrite",
    ]
    if bool(args.sp500_fetch):
        cmd.append("--sp500-fetch")
    if int(args.fundamentals_limit) > 0:
        cmd.extend(["--limit", str(int(args.fundamentals_limit))])
    print(f"[run] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    args = parse_args()
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    if bool(args.download_fundamentals):
        _run_fundamentals_refresh(args)

    params = {
        "script": "sector_momentum_top2_sector",
        "start_date": str(args.start_date),
        "end_date": str(args.end_date),
        "universe_source": str(args.universe_source),
        "universe_size": int(args.universe_size),
        "momentum_lookback_days": int(args.momentum_lookback_days),
        "top_k_per_sector": int(args.top_k_per_sector),
        "rebalance_frequency": str(args.rebalance_frequency),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "fundamentals_dir": str(args.fundamentals_dir),
        "min_sector_coverage": float(args.min_sector_coverage),
    }
    run_manager = ResearchRunManager(
        out_dir=out_root,
        params=params,
        run_tag=args.run_tag,
        tag_prefix="sector_mom_top2",
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
    load_start = (pd.Timestamp(args.start_date) - pd.Timedelta(days=int(mom_lb * 2))).strftime("%Y-%m-%d")
    close = loader.load_close_matrix(symbols, load_start, str(args.end_date)).sort_index()
    close_eval = close[(close.index >= pd.Timestamp(args.start_date)) & (close.index <= pd.Timestamp(args.end_date))]
    if close_eval.empty:
        raise ValueError("No close data in evaluation window.")

    symbols_eval = [c for c in close_eval.columns]
    fundamentals_csv = _find_latest_fundamentals_csv(Path(args.fundamentals_dir))
    sector_map: dict[str, str] = {}
    sector_source = "none"
    fundamentals_coverage = 0.0
    if fundamentals_csv is not None:
        sector_map = _load_sector_map_from_fundamentals(fundamentals_csv, symbols_eval)
        fundamentals_coverage = float(len(sector_map)) / float(max(len(symbols_eval), 1))
        if sector_map and fundamentals_coverage >= float(args.min_sector_coverage):
            sector_source = str(fundamentals_csv)
        else:
            sector_map = {}
    if not sector_map:
        sector_map, _ = build_symbol_maps(
            symbols_eval,
            path=Path(args.classification_cache),
            fetch_missing=False,
        )
        sector_source = str(args.classification_cache)
    if not sector_map:
        raise ValueError("No sector mapping available from fundamentals or classification cache.")

    momentum = (close_eval / close_eval.shift(mom_lb)) - 1.0
    rebalance_dates = _rebalance_dates(close_eval.index, str(args.rebalance_frequency))
    if len(rebalance_dates) < 2:
        raise ValueError("Need at least 2 rebalance dates.")

    weights_by_date: dict[pd.Timestamp, dict[str, float]] = {}
    rebalance_rows: list[dict[str, Any]] = []
    for dt in rebalance_dates:
        row = momentum.loc[dt]
        weights, selected = _select_weights_for_date(
            momentum_row=row,
            sector_map=sector_map,
            top_k_per_sector=int(args.top_k_per_sector),
        )
        if not weights:
            continue
        weights_by_date[pd.Timestamp(dt)] = weights
        for r in selected:
            rebalance_rows.append(
                {
                    "rebalance_date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                    "symbol": r["symbol"],
                    "sector": r["sector"],
                    "mom_3m": float(r["mom_3m"]),
                    "weight": float(weights[r["symbol"]]),
                }
            )

    if not weights_by_date:
        raise ValueError("No valid rebalance selections were generated.")

    strat_ret, turnover_df = _portfolio_returns_from_weights(close_eval, weights_by_date)
    cost_rate = float(args.transaction_cost_bps) / 10000.0
    if not turnover_df.empty:
        cost_by_date = pd.Series(0.0, index=strat_ret.index)
        for _, row in turnover_df.iterrows():
            dt = pd.Timestamp(row["rebalance_date"])
            next_idx = strat_ret.index[strat_ret.index > dt]
            if len(next_idx) > 0:
                cost_by_date.loc[next_idx[0]] += float(row["turnover"]) * cost_rate
        net_ret = strat_ret - cost_by_date
    else:
        net_ret = strat_ret

    nav = (1.0 + net_ret).cumprod()
    years = max(len(net_ret) / 252.0, 1e-9)
    total_return = float(nav.iloc[-1] - 1.0)
    cagr = float(nav.iloc[-1] ** (1.0 / years) - 1.0)
    vol = float(net_ret.std(ddof=0) * np.sqrt(252.0))
    sharpe = float((net_ret.mean() / max(net_ret.std(ddof=0), 1e-12)) * np.sqrt(252.0))
    max_dd = _max_drawdown(nav)
    avg_turnover = float(turnover_df["turnover"].mean()) if not turnover_df.empty else 0.0

    summary_df = pd.DataFrame(
        [
            {
                "start_date": str(args.start_date),
                "end_date": str(args.end_date),
                "rebalance_frequency": str(args.rebalance_frequency),
                "momentum_lookback_days": int(mom_lb),
                "top_k_per_sector": int(args.top_k_per_sector),
                "symbols_with_prices": int(close_eval.shape[1]),
                "symbols_with_sector": int(len(set(sector_map.keys()).intersection(set(close_eval.columns)))),
                "sectors_used": int(len(set(sector_map.get(s) for s in close_eval.columns if s in sector_map))),
                "rebalance_points": int(len(weights_by_date)),
                "avg_selected_names": float(
                    np.mean([len(w) for w in weights_by_date.values()]) if weights_by_date else 0.0
                ),
                "average_turnover": avg_turnover,
                "transaction_cost_bps": float(args.transaction_cost_bps),
                "total_return": total_return,
                "cagr": cagr,
                "annualized_volatility": vol,
                "sharpe": sharpe,
                "max_drawdown": max_dd,
                "sector_source": sector_source,
                "fundamentals_coverage": fundamentals_coverage,
            }
        ]
    )

    rebalance_df = pd.DataFrame(rebalance_rows).sort_values(["rebalance_date", "sector", "mom_3m"], ascending=[True, True, False])
    equity_df = pd.DataFrame(
        {
            "date": net_ret.index.strftime("%Y-%m-%d"),
            "daily_return": net_ret.values,
            "nav": nav.values,
        }
    )

    coverage_df = pd.DataFrame(
        [
            {"symbol": s, "sector": sector_map.get(s)}
            for s in sorted(close_eval.columns)
        ]
    )
    coverage_df["has_sector"] = coverage_df["sector"].astype(str).str.strip().replace("nan", "").ne("")

    summary_path = run_dir / "summary.csv"
    rebalance_path = run_dir / "rebalance_weights.csv"
    turnover_path = run_dir / "turnover.csv"
    equity_path = run_dir / "equity_curve.csv"
    coverage_path = run_dir / "sector_coverage.csv"
    summary_df.to_csv(summary_path, index=False)
    rebalance_df.to_csv(rebalance_path, index=False)
    turnover_df.to_csv(turnover_path, index=False)
    equity_df.to_csv(equity_path, index=False)
    coverage_df.to_csv(coverage_path, index=False)

    params_path = run_manager.write_params(
        extra={
            "run_dir": str(run_dir),
            "load_start": load_start,
            "sector_source": sector_source,
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "summary_csv": str(summary_path),
            "rebalance_weights_csv": str(rebalance_path),
            "turnover_csv": str(turnover_path),
            "equity_curve_csv": str(equity_path),
            "sector_coverage_csv": str(coverage_path),
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] summary: {summary_path}")
    print(f"[ok] rebalance: {rebalance_path}")
    print(f"[ok] turnover: {turnover_path}")
    print(f"[ok] equity: {equity_path}")
    print(f"[ok] sector coverage: {coverage_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
