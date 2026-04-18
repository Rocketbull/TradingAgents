from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

SUMMARY_NAME = "summary.csv"
BY_DATE_NAME = "by_date.csv"
BY_TRADE_NAME = "by_trade.csv"


@dataclass
class ResearchRunArtifacts:
    summary: pd.DataFrame
    by_date: pd.DataFrame | None
    by_trade: pd.DataFrame | None
    params: dict
    manifest: dict


def first_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def discover_run_dirs(runs_root: Path, summary_name: str = SUMMARY_NAME) -> list[Path]:
    if not runs_root.exists():
        return []
    return sorted(
        [path for path in runs_root.iterdir() if path.is_dir() and (path / summary_name).exists()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _read_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_csv(path: Path, parse_dates: list[str]) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    for column in parse_dates:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column])
    return df


def load_run_artifacts(
    run_dir: Path,
    summary_name: str = SUMMARY_NAME,
    by_date_name: str = BY_DATE_NAME,
    by_trade_name: str = BY_TRADE_NAME,
) -> ResearchRunArtifacts:
    summary = pd.read_csv(run_dir / summary_name)
    by_date = _read_optional_csv(run_dir / by_date_name, parse_dates=["date"])
    by_trade = _read_optional_csv(run_dir / by_trade_name, parse_dates=["trade_date", "exit_date"])
    params = _read_optional_json(run_dir / "params.json")
    manifest = _read_optional_json(run_dir / "manifest.json")
    return ResearchRunArtifacts(
        summary=summary,
        by_date=by_date,
        by_trade=by_trade,
        params=params,
        manifest=manifest,
    )


def is_single_row_summary(summary: pd.DataFrame) -> bool:
    return int(summary.shape[0]) == 1


def single_row_metric_groups(summary: pd.DataFrame) -> dict[str, list[str]]:
    groups = {
        "Returns": [
            "gross_total_return",
            "net_total_return",
            "net_annualized_return",
            "buy_and_hold_return_same_window",
            "open_to_close_total_return_same_days",
        ],
        "Risk / Quality": [
            "net_sharpe",
            "net_max_drawdown",
            "net_win_rate",
            "net_annualized_volatility",
            "mean_net_return",
            "median_net_return",
        ],
        "Trade Stats": [
            "trade_count",
            "mean_holding_calendar_days",
            "mean_next_day_intraday_return",
            "overnight_minus_intraday_mean_return",
            "transaction_cost_bps_per_side",
        ],
    }
    return {
        title: [column for column in candidates if column in summary.columns]
        for title, candidates in groups.items()
    }


def multi_row_metric_groups(summary: pd.DataFrame) -> dict[str, list[str]]:
    groups = {
        "Performance / IR": [
            "implied_ir",
            "realized_active_ir",
            "implied_information_ratio",
            "realized_active_information_ratio",
            "sharpe",
            "net_sharpe",
            "total_return",
            "net_total_return",
            "gross_total_return",
        ],
        "IC Diagnostics": [
            "avg_rank_ic",
            "ic_ir",
            "ic_std",
            "average_ic",
            "h1_average_ic",
            "h2_average_ic",
            "h4_average_ic",
        ],
        "Implementation / Breadth": [
            "avg_tc_proxy",
            "avg_breadth_proxy",
            "signal_coverage",
            "average_transfer_coefficient",
            "average_breadth_proxy",
            "trade_count",
            "net_win_rate",
        ],
    }
    return {
        title: [column for column in candidates if column in summary.columns]
        for title, candidates in groups.items()
    }
