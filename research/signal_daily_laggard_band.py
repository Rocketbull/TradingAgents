from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common import GrinoldDiagnostics, ResearchRunManager
from tradingagents.backtest.data_loader import LocalParquetDataLoader


@dataclass(frozen=True)
class VariantSpec:
    outer_n: int
    skip_n: int

    @property
    def hold_n(self) -> int:
        return int(self.outer_n - self.skip_n)

    @property
    def name(self) -> str:
        return f"laggard_{self.outer_n}_skip_{self.skip_n}"


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
        description=(
            "Signal research for a laggard band strategy: rank by YTD or trailing return, "
            "take worst N, exclude the most extreme losers, and study the remaining band."
        )
    )
    parser.add_argument("--config-json", default=pre_args.config_json, help="Optional JSON config file.")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
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
    parser.add_argument(
        "--snapshot-schedule-enabled",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use the latest snapshot as of each evaluation date when universe_source=sp500_snapshot.",
    )
    parser.add_argument(
        "--signal-return-mode",
        default="ytd",
        choices=["ytd", "trailing"],
        help="Cross-sectional return definition used to rank laggards.",
    )
    parser.add_argument(
        "--signal-lookback-days",
        type=int,
        default=1,
        help="Trailing return lookback used when --signal-return-mode=trailing.",
    )
    parser.add_argument("--outer-n", type=int, default=60, help="Take the worst N names by trailing return.")
    parser.add_argument("--skip-n", type=int, default=10, help="Exclude the worst K names from that bucket.")
    parser.add_argument(
        "--comparison-specs",
        default="50:0,70:20,80:30",
        help="Optional comparison variants as OUTER:SKIP pairs, comma-separated.",
    )
    parser.add_argument(
        "--forward-days",
        default="1,5,20",
        help="Forward horizons in trading days for repo diagnostics.",
    )
    parser.add_argument("--transaction-cost-bps", type=float, default=5.0)
    parser.add_argument("--out-dir", default="research/output")
    parser.add_argument("--run-tag", default=None)
    parser.add_argument("--save-selections", action="store_true")

    parser.set_defaults(**config_defaults)
    args = parser.parse_args(remaining)
    if not args.start_date or not args.end_date:
        parser.error("--start-date and --end-date are required (via CLI or --config-json).")
    if int(args.signal_lookback_days) < 1:
        parser.error("--signal-lookback-days must be >= 1.")
    if int(args.outer_n) < 2:
        parser.error("--outer-n must be >= 2.")
    if int(args.skip_n) < 0:
        parser.error("--skip-n must be >= 0.")
    if int(args.skip_n) >= int(args.outer_n):
        parser.error("--skip-n must be smaller than --outer-n.")
    return args


def _parse_variant_specs(raw: str) -> list[VariantSpec]:
    if not str(raw).strip():
        return []
    out: list[VariantSpec] = []
    seen: set[tuple[int, int]] = set()
    for token in str(raw).split(","):
        item = token.strip()
        if not item:
            continue
        outer_raw, skip_raw = item.split(":", maxsplit=1)
        spec = VariantSpec(outer_n=int(outer_raw), skip_n=int(skip_raw))
        if spec.skip_n < 0 or spec.skip_n >= spec.outer_n:
            raise ValueError(f"Invalid variant spec '{item}'. Expected OUTER:SKIP with 0 <= SKIP < OUTER.")
        key = (spec.outer_n, spec.skip_n)
        if key not in seen:
            out.append(spec)
            seen.add(key)
    return out


def _max_drawdown(nav: pd.Series) -> float:
    running_max = nav.cummax()
    drawdown = nav / running_max - 1.0
    return float(drawdown.min()) if len(drawdown) else 0.0


def _quarter_label(dt: pd.Timestamp) -> str:
    return f"{dt.year}Q{dt.quarter}"


def _read_snapshot_schedule(
    loader: LocalParquetDataLoader,
    eval_dates: pd.DatetimeIndex,
    universe_size: int,
    benchmark_symbol: str,
) -> dict[pd.Timestamp, list[str]]:
    root = loader.universe_snapshot_dir
    if root is None or not root.exists():
        raise FileNotFoundError(f"Snapshot directory not found: {root}")

    snapshot_paths = sorted(root.glob("sp500_membership_*.csv"))
    if not snapshot_paths:
        raise FileNotFoundError(f"No snapshot files found under: {root}")

    parsed: list[tuple[pd.Timestamp, Path]] = []
    for path in snapshot_paths:
        dt = loader._parse_snapshot_date(path)
        if dt is None:
            continue
        parsed.append((pd.Timestamp(dt), path))
    parsed.sort(key=lambda x: x[0])
    if not parsed:
        raise FileNotFoundError(f"No parseable snapshot files found under: {root}")

    schedule: dict[pd.Timestamp, list[str]] = {}
    snap_idx = 0
    active_symbols: list[str] = []
    active_path: Path | None = None
    benchmark = str(benchmark_symbol).upper()

    for dt in eval_dates:
        while snap_idx + 1 < len(parsed) and parsed[snap_idx + 1][0] <= dt:
            snap_idx += 1
        if parsed[snap_idx][0] > dt:
            raise ValueError(f"No snapshot available on or before evaluation date {dt.strftime('%Y-%m-%d')}.")
        path = parsed[snap_idx][1]
        if active_path != path:
            syms = loader._read_snapshot_symbols(path)[: int(universe_size)]
            if benchmark not in syms:
                syms = [benchmark] + syms
            active_symbols = list(dict.fromkeys(syms))
            active_path = path
        schedule[pd.Timestamp(dt)] = list(active_symbols)
    return schedule


def _resolve_universe_schedule(
    loader: LocalParquetDataLoader,
    eval_dates: pd.DatetimeIndex,
    args: argparse.Namespace,
) -> dict[pd.Timestamp, list[str]]:
    if str(args.universe_source).lower() == "sp500_snapshot" and bool(args.snapshot_schedule_enabled):
        return _read_snapshot_schedule(
            loader=loader,
            eval_dates=eval_dates,
            universe_size=int(args.universe_size),
            benchmark_symbol=str(args.benchmark_symbol).upper(),
        )

    symbols = loader.load_symbols(
        universe_source=str(args.universe_source),
        portfolio_universe=[],
        portfolio_universe_size=int(args.universe_size),
        benchmark_symbol=str(args.benchmark_symbol).upper(),
        fallback_symbol=str(args.fallback_symbol).upper(),
        asof_date=str(args.end_date),
    )
    return {pd.Timestamp(dt): list(symbols) for dt in eval_dates}


def _select_laggard_band(
    trailing_return_row: pd.Series,
    outer_n: int,
    skip_n: int,
) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    scores = pd.Series(np.nan, index=trailing_return_row.index, dtype=float)
    signal = pd.Series(np.nan, index=trailing_return_row.index, dtype=float)

    clean = pd.to_numeric(trailing_return_row, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return scores, signal, {"available_symbols": 0, "selected_count": 0}

    ordered = clean.sort_values(ascending=True, kind="mergesort")
    signal.loc[ordered.index] = 0.0
    scores.loc[ordered.index] = 0.0

    losers = ordered.iloc[: min(int(outer_n), int(ordered.shape[0]))]
    selected = losers.iloc[int(skip_n) :]
    excluded = losers.iloc[: int(skip_n)]
    if selected.empty:
        return scores, signal, {"available_symbols": int(ordered.shape[0]), "selected_count": 0}

    signal.loc[selected.index] = 1.0
    descending_rank = pd.Series(
        np.arange(selected.shape[0], 0, -1, dtype=float),
        index=selected.index,
    )
    scores.loc[selected.index] = descending_rank

    return (
        scores,
        signal,
        {
            "available_symbols": int(ordered.shape[0]),
            "selected_count": int(selected.shape[0]),
            "selected_symbols": list(selected.index),
            "excluded_symbols": list(excluded.index),
            "selected_signal_return_mean": float(selected.mean()),
            "selected_signal_return_median": float(selected.median()),
            "excluded_signal_return_mean": float(excluded.mean()) if not excluded.empty else float("nan"),
            "full_bucket_signal_return_mean": float(losers.mean()) if not losers.empty else float("nan"),
            "selected_signal_return_min": float(selected.min()),
            "selected_signal_return_max": float(selected.max()),
        },
    )


def _safe_mean(row: pd.Series, symbols: list[str]) -> float:
    if not symbols:
        return float("nan")
    vals = pd.to_numeric(row.reindex(symbols), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if vals.empty:
        return float("nan")
    return float(vals.mean())


def _build_signal_return_panel(
    close_tradable: pd.DataFrame,
    signal_return_mode: str,
    signal_lookback_days: int,
) -> pd.DataFrame:
    mode = str(signal_return_mode).lower()
    if mode == "trailing":
        return close_tradable.pct_change(int(signal_lookback_days))
    if mode != "ytd":
        raise ValueError(f"Unsupported signal_return_mode: {signal_return_mode}")

    year_open = close_tradable.groupby(close_tradable.index.year).transform("first")
    ytd = close_tradable / year_open - 1.0
    return ytd.replace([np.inf, -np.inf], np.nan)


def _build_variant_panels(
    close_eval: pd.DataFrame,
    universe_schedule: dict[pd.Timestamp, list[str]],
    signal_return_mode: str,
    signal_lookback_days: int,
    variants: list[VariantSpec],
    benchmark_symbol: str,
) -> tuple[dict[str, dict[str, Any]], pd.DataFrame]:
    benchmark = str(benchmark_symbol).upper()
    close_tradable = close_eval.drop(columns=[benchmark], errors="ignore")
    signal_ret = _build_signal_return_panel(
        close_tradable=close_tradable,
        signal_return_mode=signal_return_mode,
        signal_lookback_days=int(signal_lookback_days),
    )
    next_day_ret = close_tradable.shift(-1) / close_tradable - 1.0

    variant_rows: dict[str, dict[str, list[pd.Series] | list[dict[str, Any]]]] = {}
    for spec in variants:
        variant_rows[spec.name] = {
            "score_rows": [],
            "signal_rows": [],
            "detail_rows": [],
        }

    selection_rows: list[dict[str, Any]] = []
    eval_dates = signal_ret.index[:-1]
    for dt in eval_dates:
        universe_today = [
            s
            for s in universe_schedule.get(pd.Timestamp(dt), [])
            if s != benchmark and s in close_tradable.columns
        ]
        if len(universe_today) < 2:
            continue
        signal_row = signal_ret.loc[dt].reindex(universe_today)
        next_row = next_day_ret.loc[dt].reindex(universe_today)
        universe_next_day_mean = _safe_mean(next_row, universe_today)

        for spec in variants:
            score, signal, meta = _select_laggard_band(
                trailing_return_row=signal_row,
                outer_n=int(spec.outer_n),
                skip_n=int(spec.skip_n),
            )
            if int(meta.get("selected_count", 0)) <= 0:
                continue

            score.name = dt
            signal.name = dt
            variant_rows[spec.name]["score_rows"].append(score)
            variant_rows[spec.name]["signal_rows"].append(signal)

            selected_symbols = [str(s) for s in meta.get("selected_symbols", [])]
            excluded_symbols = [str(s) for s in meta.get("excluded_symbols", [])]
            detail = {
                "date": dt,
                "quarter": _quarter_label(pd.Timestamp(dt)),
                "variant": spec.name,
                "outer_n": int(spec.outer_n),
                "skip_n": int(spec.skip_n),
                "hold_n": int(spec.hold_n),
                "available_symbols": int(meta.get("available_symbols", 0)),
                "selected_count": int(meta.get("selected_count", 0)),
                "selected_signal_return_mean": float(meta.get("selected_signal_return_mean", float("nan"))),
                "selected_signal_return_median": float(meta.get("selected_signal_return_median", float("nan"))),
                "excluded_signal_return_mean": float(meta.get("excluded_signal_return_mean", float("nan"))),
                "full_bucket_signal_return_mean": float(meta.get("full_bucket_signal_return_mean", float("nan"))),
                "selected_next_day_return_mean": _safe_mean(next_row, selected_symbols),
                "excluded_next_day_return_mean": _safe_mean(next_row, excluded_symbols),
                "universe_next_day_return_mean": universe_next_day_mean,
            }
            variant_rows[spec.name]["detail_rows"].append(detail)

            if spec == variants[0]:
                for rank, sym in enumerate(selected_symbols, start=1):
                    selection_rows.append(
                        {
                            "date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                            "quarter": _quarter_label(pd.Timestamp(dt)),
                            "variant": spec.name,
                            "rank_within_selected_band": int(rank),
                            "symbol": sym,
                            "signal_return": float(signal_row.get(sym, np.nan)),
                            "next_day_return": float(next_row.get(sym, np.nan)),
                        }
                    )
                for rank, sym in enumerate(excluded_symbols, start=1):
                    selection_rows.append(
                        {
                            "date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                            "quarter": _quarter_label(pd.Timestamp(dt)),
                            "variant": spec.name,
                            "rank_within_selected_band": -int(rank),
                            "symbol": sym,
                            "signal_return": float(signal_row.get(sym, np.nan)),
                            "next_day_return": float(next_row.get(sym, np.nan)),
                        }
                    )

    variant_panels: dict[str, dict[str, Any]] = {}
    for spec in variants:
        rows = variant_rows[spec.name]
        score_rows = rows["score_rows"]
        signal_rows = rows["signal_rows"]
        if not score_rows or not signal_rows:
            continue
        score_df = pd.DataFrame(score_rows).sort_index()
        signal_df = pd.DataFrame(signal_rows).sort_index()
        detail_df = pd.DataFrame(rows["detail_rows"]).sort_values("date")
        variant_panels[spec.name] = {
            "spec": spec,
            "score": score_df,
            "signal": signal_df,
            "details": detail_df,
        }

    selections_df = pd.DataFrame(selection_rows).sort_values(["date", "rank_within_selected_band", "symbol"])
    return variant_panels, selections_df


def _portfolio_backtest_for_variant(
    variant_name: str,
    signal_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    close_eval: pd.DataFrame,
    benchmark_series: pd.Series,
    universe_schedule: dict[pd.Timestamp, list[str]],
    benchmark_symbol: str,
    transaction_cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    benchmark = str(benchmark_symbol).upper()
    close_tradable = close_eval.drop(columns=[benchmark], errors="ignore")
    next_day_ret = close_tradable.shift(-1) / close_tradable - 1.0
    benchmark_next = benchmark_series.shift(-1) / benchmark_series - 1.0
    cost_rate = float(transaction_cost_bps) / 10000.0

    records: list[dict[str, Any]] = []
    prev_w = pd.Series(dtype=float)
    for dt in signal_df.index:
        if dt not in next_day_ret.index:
            continue
        selected_mask = signal_df.loc[dt].fillna(0.0) > 0.0
        selected_symbols = [str(s) for s in signal_df.columns[selected_mask]]
        if not selected_symbols:
            continue
        weight = 1.0 / float(len(selected_symbols))
        w = pd.Series(weight, index=selected_symbols, dtype=float)

        curr_index = sorted(set(prev_w.index).union(set(w.index)))
        curr = w.reindex(curr_index).fillna(0.0)
        prev = prev_w.reindex(curr_index).fillna(0.0)
        turnover = float((curr - prev).abs().sum())

        realized_date = next_day_ret.index[next_day_ret.index.get_loc(dt) + 1]
        next_row = next_day_ret.loc[dt].reindex(selected_symbols).fillna(0.0)
        portfolio_return_gross = float((w * next_row).sum())
        portfolio_return = float(portfolio_return_gross - turnover * cost_rate)

        universe_today = [
            s
            for s in universe_schedule.get(pd.Timestamp(dt), [])
            if s != benchmark and s in close_tradable.columns
        ]
        universe_row = next_day_ret.loc[dt].reindex(universe_today)
        universe_eq_return = float(
            pd.to_numeric(universe_row, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().mean()
        )
        benchmark_return = float(benchmark_next.loc[dt]) if dt in benchmark_next.index else float("nan")

        records.append(
            {
                "date": pd.Timestamp(realized_date),
                "signal_date": pd.Timestamp(dt),
                "quarter": _quarter_label(pd.Timestamp(dt)),
                "variant": variant_name,
                "selected_count": int(len(selected_symbols)),
                "turnover": turnover,
                "gross_return": portfolio_return_gross,
                "daily_return": portfolio_return,
                "universe_eq_return": universe_eq_return,
                "benchmark_return": benchmark_return,
                "active_return_vs_universe": float(portfolio_return - universe_eq_return),
                "active_return_vs_benchmark": float(portfolio_return - benchmark_return),
            }
        )
        prev_w = w

    if not records:
        raise ValueError(f"No portfolio records generated for variant {variant_name}.")

    perf_df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    perf_df["nav"] = (1.0 + perf_df["daily_return"]).cumprod()
    perf_df["universe_eq_nav"] = (1.0 + perf_df["universe_eq_return"]).cumprod()
    perf_df["benchmark_nav"] = (1.0 + perf_df["benchmark_return"]).cumprod()

    ret = perf_df["daily_return"]
    active_universe = perf_df["active_return_vs_universe"]
    active_benchmark = perf_df["active_return_vs_benchmark"]
    years = max(len(ret) / 252.0, 1e-9)
    ret_std = float(ret.std(ddof=0))
    active_univ_std = float(active_universe.std(ddof=0))
    active_bm_std = float(active_benchmark.std(ddof=0))
    nav = perf_df["nav"]

    detail_aligned = detail_df.copy()
    detail_aligned["date"] = pd.to_datetime(detail_aligned["date"])
    summary = {
        "variant": variant_name,
        "outer_n": int(detail_df["outer_n"].iloc[0]),
        "skip_n": int(detail_df["skip_n"].iloc[0]),
        "hold_n": int(detail_df["hold_n"].iloc[0]),
        "signal_days": int(signal_df.shape[0]),
        "portfolio_days": int(len(perf_df)),
        "average_selected_names": float(perf_df["selected_count"].mean()),
        "average_turnover": float(perf_df["turnover"].mean()),
        "transaction_cost_bps": float(transaction_cost_bps),
        "total_return": float(nav.iloc[-1] - 1.0),
        "cagr": float(nav.iloc[-1] ** (1.0 / years) - 1.0),
        "annualized_volatility": float(ret_std * np.sqrt(252.0)),
        "sharpe": float((ret.mean() / ret_std) * np.sqrt(252.0)) if ret_std > 0 else float("nan"),
        "max_drawdown": _max_drawdown(nav),
        "hit_rate": float((ret > 0.0).mean()),
        "average_active_return_vs_universe": float(active_universe.mean()),
        "active_ir_vs_universe": (
            float((active_universe.mean() / active_univ_std) * np.sqrt(252.0))
            if active_univ_std > 0
            else float("nan")
        ),
        "average_active_return_vs_benchmark": float(active_benchmark.mean()),
        "active_ir_vs_benchmark": (
            float((active_benchmark.mean() / active_bm_std) * np.sqrt(252.0))
            if active_bm_std > 0
            else float("nan")
        ),
        "average_selected_signal_return_mean": float(detail_aligned["selected_signal_return_mean"].mean()),
        "average_selected_next_day_return_mean": float(detail_aligned["selected_next_day_return_mean"].mean()),
        "average_excluded_next_day_return_mean": float(detail_aligned["excluded_next_day_return_mean"].mean()),
        "average_universe_next_day_return_mean": float(detail_aligned["universe_next_day_return_mean"].mean()),
    }
    return perf_df, summary


def _baseline_summary(
    name: str,
    ret: pd.Series,
    universe_eq: pd.Series,
    benchmark: pd.Series,
) -> dict[str, Any]:
    perf = pd.DataFrame(
        {
            "daily_return": ret.values,
            "universe_eq_return": universe_eq.values,
            "benchmark_return": benchmark.values,
        },
        index=pd.Index(ret.index, name="date"),
    ).dropna(how="any")
    perf["nav"] = (1.0 + perf["daily_return"]).cumprod()
    perf["active_return_vs_universe"] = perf["daily_return"] - perf["universe_eq_return"]
    perf["active_return_vs_benchmark"] = perf["daily_return"] - perf["benchmark_return"]
    years = max(len(perf) / 252.0, 1e-9)
    ret_std = float(perf["daily_return"].std(ddof=0))
    active_univ_std = float(perf["active_return_vs_universe"].std(ddof=0))
    active_bm_std = float(perf["active_return_vs_benchmark"].std(ddof=0))
    return {
        "variant": name,
        "outer_n": np.nan,
        "skip_n": np.nan,
        "hold_n": np.nan,
        "signal_days": int(len(perf)),
        "portfolio_days": int(len(perf)),
        "average_selected_names": np.nan,
        "average_turnover": np.nan,
        "transaction_cost_bps": 0.0,
        "total_return": float(perf["nav"].iloc[-1] - 1.0),
        "cagr": float(perf["nav"].iloc[-1] ** (1.0 / years) - 1.0),
        "annualized_volatility": float(ret_std * np.sqrt(252.0)),
        "sharpe": (
            float((perf["daily_return"].mean() / ret_std) * np.sqrt(252.0))
            if ret_std > 0
            else float("nan")
        ),
        "max_drawdown": _max_drawdown(perf["nav"]),
        "hit_rate": float((perf["daily_return"] > 0.0).mean()),
        "average_active_return_vs_universe": float(perf["active_return_vs_universe"].mean()),
        "active_ir_vs_universe": (
            float((perf["active_return_vs_universe"].mean() / active_univ_std) * np.sqrt(252.0))
            if active_univ_std > 0
            else float("nan")
        ),
        "average_active_return_vs_benchmark": float(perf["active_return_vs_benchmark"].mean()),
        "active_ir_vs_benchmark": (
            float((perf["active_return_vs_benchmark"].mean() / active_bm_std) * np.sqrt(252.0))
            if active_bm_std > 0
            else float("nan")
        ),
        "average_selected_signal_return_mean": np.nan,
        "average_selected_next_day_return_mean": np.nan,
        "average_excluded_next_day_return_mean": np.nan,
        "average_universe_next_day_return_mean": float(perf["universe_eq_return"].mean()),
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    target_spec = VariantSpec(outer_n=int(args.outer_n), skip_n=int(args.skip_n))
    variants = [target_spec]
    for spec in _parse_variant_specs(args.comparison_specs):
        if spec != target_spec:
            variants.append(spec)
    forward_days = GrinoldDiagnostics.parse_forward_days(args.forward_days)

    params = {
        "script": "signal_daily_laggard_band",
        "start_date": str(args.start_date),
        "end_date": str(args.end_date),
        "universe_source": str(args.universe_source),
        "universe_size": int(args.universe_size),
        "signal_return_mode": str(args.signal_return_mode),
        "signal_lookback_days": int(args.signal_lookback_days),
        "target_outer_n": int(target_spec.outer_n),
        "target_skip_n": int(target_spec.skip_n),
        "comparison_specs": [spec.name for spec in variants[1:]],
        "forward_days": list(forward_days),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "snapshot_schedule_enabled": bool(args.snapshot_schedule_enabled),
    }
    run_manager = ResearchRunManager(
        out_dir=out_dir,
        params=params,
        run_tag=args.run_tag,
        tag_prefix="sig_daily_laggard_band",
    )
    run_dir = run_manager.run_dir()

    loader = LocalParquetDataLoader(
        data_root=Path(args.data_root),
        symbol_file=Path(args.symbol_file),
        universe_snapshot_dir=Path(args.snapshot_dir),
    )
    benchmark_symbol = str(args.benchmark_symbol).upper()
    max_forward = max(forward_days)
    start_ts = pd.Timestamp(args.start_date)
    if str(args.signal_return_mode).lower() == "ytd":
        load_start_ts = min(start_ts - pd.Timedelta(days=max_forward + 5), pd.Timestamp(year=start_ts.year, month=1, day=1))
    else:
        warmup_days = int(max(args.signal_lookback_days, max_forward) * 3 + 10)
        load_start_ts = start_ts - pd.Timedelta(days=warmup_days)
    load_start = load_start_ts.strftime("%Y-%m-%d")

    benchmark_series = loader.load_symbol_series(
        symbol=benchmark_symbol,
        start_date=load_start,
        end_date=str(args.end_date),
        field_candidates=["Adj Close", "Close"],
    ).sort_index()
    eval_dates = benchmark_series.index[
        (benchmark_series.index >= pd.Timestamp(args.start_date))
        & (benchmark_series.index <= pd.Timestamp(args.end_date))
    ]
    if len(eval_dates) < max_forward + 2:
        raise ValueError("Evaluation window does not contain enough trading dates.")

    universe_schedule = _resolve_universe_schedule(loader=loader, eval_dates=eval_dates, args=args)
    symbols_union = sorted(
        {
            s
            for syms in universe_schedule.values()
            for s in syms
            if str(s).strip()
        }
    )
    if benchmark_symbol not in symbols_union:
        symbols_union = [benchmark_symbol] + symbols_union
    close = loader.load_close_matrix(symbols_union, load_start, str(args.end_date)).sort_index().ffill()
    close_eval = close.reindex(eval_dates).ffill()

    variant_panels, selections_df = _build_variant_panels(
        close_eval=close_eval,
        universe_schedule=universe_schedule,
        signal_return_mode=str(args.signal_return_mode),
        signal_lookback_days=int(args.signal_lookback_days),
        variants=variants,
        benchmark_symbol=benchmark_symbol,
    )
    if not variant_panels:
        raise ValueError("No variant produced valid signal rows. Check data coverage or reduce bucket sizes.")

    repo_summary_rows: list[dict[str, Any]] = []
    repo_by_date_rows: list[pd.DataFrame] = []
    portfolio_summary_rows: list[dict[str, Any]] = []
    portfolio_by_date_frames: list[pd.DataFrame] = []
    yearly_rows: list[dict[str, Any]] = []

    target_perf: pd.DataFrame | None = None
    for variant_name, payload in variant_panels.items():
        spec = payload["spec"]
        signal_df = payload["signal"]
        score_df = payload["score"]
        detail_df = payload["details"]

        diagnostics = GrinoldDiagnostics(weighting_mode="long_only", top_k=int(spec.hold_n))
        for h in forward_days:
            fwd_ret = close_eval.drop(columns=[benchmark_symbol], errors="ignore").shift(-h) / close_eval.drop(
                columns=[benchmark_symbol], errors="ignore"
            ) - 1.0
            fwd_ret = fwd_ret.reindex(index=signal_df.index, columns=signal_df.columns)
            row, by_date = diagnostics.evaluate_horizon(
                signal=signal_df,
                score=score_df,
                fwd_ret=fwd_ret,
                horizon_days=int(h),
            )
            row.update(
                {
                    "variant": variant_name,
                    "outer_n": int(spec.outer_n),
                    "skip_n": int(spec.skip_n),
                    "hold_n": int(spec.hold_n),
                }
            )
            repo_summary_rows.append(row)
            if not by_date.empty:
                by_date = by_date.copy()
                by_date["variant"] = variant_name
                by_date["outer_n"] = int(spec.outer_n)
                by_date["skip_n"] = int(spec.skip_n)
                by_date["hold_n"] = int(spec.hold_n)
                repo_by_date_rows.append(by_date)

        perf_df, perf_summary = _portfolio_backtest_for_variant(
            variant_name=variant_name,
            signal_df=signal_df,
            detail_df=detail_df,
            close_eval=close_eval,
            benchmark_series=benchmark_series.reindex(close_eval.index).ffill(),
            universe_schedule=universe_schedule,
            benchmark_symbol=benchmark_symbol,
            transaction_cost_bps=float(args.transaction_cost_bps),
        )
        portfolio_summary_rows.append(perf_summary)
        portfolio_by_date_frames.append(perf_df)
        if variant_name == target_spec.name:
            target_perf = perf_df.copy()

        yearly = perf_df.copy()
        yearly["year"] = pd.to_datetime(yearly["date"]).dt.year
        for year, grp in yearly.groupby("year"):
            yearly_rows.append(
                {
                    "variant": variant_name,
                    "year": int(year),
                    "return": float((1.0 + grp["daily_return"]).prod() - 1.0),
                    "active_return_vs_universe": float((1.0 + grp["active_return_vs_universe"]).prod() - 1.0),
                    "active_return_vs_benchmark": float((1.0 + grp["active_return_vs_benchmark"]).prod() - 1.0),
                }
            )

    if target_perf is None:
        raise ValueError("Target variant did not produce a portfolio time series.")

    baseline_summary_rows = [
        _baseline_summary(
            name="universe_equal_weight",
            ret=target_perf.set_index("date")["universe_eq_return"],
            universe_eq=target_perf.set_index("date")["universe_eq_return"],
            benchmark=target_perf.set_index("date")["benchmark_return"],
        ),
        _baseline_summary(
            name=f"benchmark_{benchmark_symbol}",
            ret=target_perf.set_index("date")["benchmark_return"],
            universe_eq=target_perf.set_index("date")["universe_eq_return"],
            benchmark=target_perf.set_index("date")["benchmark_return"],
        ),
    ]

    repo_summary_df = pd.DataFrame(repo_summary_rows).sort_values(["variant", "horizon_days"])
    repo_by_date_df = pd.concat(repo_by_date_rows, ignore_index=True) if repo_by_date_rows else pd.DataFrame()
    portfolio_summary_df = pd.DataFrame(portfolio_summary_rows + baseline_summary_rows).sort_values("variant")
    portfolio_by_date_df = pd.concat(portfolio_by_date_frames, ignore_index=True).sort_values(["variant", "date"])
    yearly_df = pd.DataFrame(yearly_rows).sort_values(["variant", "year"])

    repo_summary_path = run_dir / "repo_summary.csv"
    repo_by_date_path = run_dir / "repo_by_date.csv"
    summary_path = run_dir / "summary.csv"
    by_date_path = run_dir / "by_date.csv"
    yearly_path = run_dir / "yearly_returns.csv"
    selections_path = run_dir / "target_selections.csv"

    repo_summary_df.to_csv(repo_summary_path, index=False)
    repo_by_date_df.to_csv(repo_by_date_path, index=False)
    portfolio_summary_df.to_csv(summary_path, index=False)
    portfolio_by_date_df.to_csv(by_date_path, index=False)
    yearly_df.to_csv(yearly_path, index=False)
    if bool(args.save_selections):
        selections_df.to_csv(selections_path, index=False)

    params_path = run_manager.write_params(
        extra={
            "symbols_union_size": int(len(symbols_union)),
            "eval_dates": int(len(eval_dates)),
            "load_start": load_start,
            "variants": [
                {
                    "variant": spec.name,
                    "outer_n": int(spec.outer_n),
                    "skip_n": int(spec.skip_n),
                    "hold_n": int(spec.hold_n),
                }
                for spec in variants
            ],
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "repo_summary_csv": str(repo_summary_path),
            "repo_by_date_csv": str(repo_by_date_path),
            "summary_csv": str(summary_path),
            "by_date_csv": str(by_date_path),
            "yearly_returns_csv": str(yearly_path),
            "target_selections_csv": str(selections_path) if bool(args.save_selections) else None,
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] target_variant: {target_spec.name}")
    print(f"[ok] variants: {[spec.name for spec in variants]}")
    print(f"[ok] symbols_union_size: {len(symbols_union)}")
    print(f"[ok] evaluation_days: {len(eval_dates)}")
    print(f"[ok] repo_summary: {repo_summary_path}")
    print(f"[ok] summary: {summary_path}")
    print(f"[ok] by_date: {by_date_path}")
    if bool(args.save_selections):
        print(f"[ok] target_selections: {selections_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(portfolio_summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
