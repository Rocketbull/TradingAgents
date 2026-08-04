from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from tools.monthly_commentary_context import resolve_latest_default_baseline_run


DEFAULT_BASELINE_CONFIG_RELATIVE_PATHS = (
    Path("research/configs/baselines/backtest_current_baseline.json"),
    Path("research/configs/backtest_current_baseline.json"),
)


@dataclass(frozen=True)
class BacktestRunArtifacts:
    run_dir: Path
    summary: dict[str, Any]
    equity_curve: pd.DataFrame
    daily_market_value: pd.DataFrame | None
    weights_history: pd.DataFrame | None
    orders_history: pd.DataFrame | None


@dataclass(frozen=True)
class BacktestViewerContext:
    repo_root: Path
    backtest_root: Path
    baseline_config_path: Path
    runs: list[dict[str, Any]]
    run_selection_mode: str
    latest_run_dir: Path
    latest_current_baseline_dir: Path
    default_run_dir: Path
    run_table: pd.DataFrame
    artifacts: BacktestRunArtifacts


def resolve_repo_root(cwd: Path | None = None) -> Path:
    cwd = (cwd or Path.cwd()).resolve()
    for candidate in (cwd, cwd.parent):
        if any((candidate / rel).exists() for rel in DEFAULT_BASELINE_CONFIG_RELATIVE_PATHS):
            return candidate
    return cwd


def resolve_backtest_root(repo_root: Path) -> Path:
    for candidate in (
        repo_root / "eval_results/backtest",
        Path("eval_results/backtest"),
        Path("../eval_results/backtest"),
    ):
        if candidate.exists():
            return candidate.resolve()
    return (repo_root / "eval_results/backtest").resolve()


def resolve_baseline_config_path(repo_root: Path) -> Path:
    for relative in DEFAULT_BASELINE_CONFIG_RELATIVE_PATHS:
        candidate = repo_root / relative
        if candidate.exists():
            return candidate.resolve()
    return (repo_root / DEFAULT_BASELINE_CONFIG_RELATIVE_PATHS[0]).resolve()


def is_run_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "summary.json").exists()
        and (path / "equity_curve.csv").exists()
    )


def has_daily_market_value(run_dir: Path) -> bool:
    return (run_dir / "daily_market_value.csv").exists()


def completed_at(run_dir: Path) -> pd.Timestamp:
    candidates = [
        run_dir / "summary.json",
        run_dir / "equity_curve.csv",
        run_dir / "daily_market_value.csv",
        run_dir / "weights_history.csv",
        run_dir / "orders_history.csv",
        run_dir / "rebalance_log.jsonl",
    ]
    mtimes = [path.stat().st_mtime for path in candidates if path.exists()]
    return pd.to_datetime(max(mtimes), unit="s") if mtimes else pd.Timestamp.min


def latest_trade_date(run_dir: Path) -> pd.Timestamp:
    try:
        equity_curve = pd.read_csv(run_dir / "equity_curve.csv", usecols=["trade_date"])
    except Exception:
        return pd.NaT
    return pd.to_datetime(equity_curve["trade_date"]).max()


def collect_runs(backtest_root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if backtest_root.exists():
        for path in backtest_root.iterdir():
            if path.name == "ab_pairs":
                continue
            if is_run_dir(path):
                runs.append({"run_dir": path.resolve(), "source": "single", "pair": None})

    pair_root = backtest_root / "ab_pairs"
    if pair_root.exists():
        for pair in pair_root.iterdir():
            if not pair.is_dir():
                continue
            for child in ("run_a", "run_b"):
                run_dir = pair / child
                if is_run_dir(run_dir):
                    runs.append(
                        {
                            "run_dir": run_dir.resolve(),
                            "source": f"ab_{child}",
                            "pair": pair.name,
                        }
                    )

    for run in runs:
        summary = json.loads((run["run_dir"] / "summary.json").read_text())
        run["completed_at"] = completed_at(run["run_dir"])
        run["summary_end_date"] = pd.to_datetime(summary.get("end_date"), errors="coerce")
        run["latest_trade_date"] = latest_trade_date(run["run_dir"])
        run["has_daily_market_value"] = has_daily_market_value(run["run_dir"])

    runs.sort(
        key=lambda row: (
            row["completed_at"],
            row["latest_trade_date"]
            if pd.notna(row["latest_trade_date"])
            else pd.Timestamp.min,
            row["summary_end_date"]
            if pd.notna(row["summary_end_date"])
            else pd.Timestamp.min,
            row["has_daily_market_value"],
        ),
        reverse=True,
    )
    return runs


def run_table(runs: list[dict[str, Any]], limit: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rank": index + 1,
                "run_dir": str(run["run_dir"]),
                "source": run["source"],
                "pair": run["pair"],
                "has_daily_market_value": run["has_daily_market_value"],
                "summary_end_date": run["summary_end_date"],
                "latest_trade_date": run["latest_trade_date"],
                "completed_at": run["completed_at"],
            }
            for index, run in enumerate(runs[:limit])
        ]
    )


def resolve_default_run_dir(
    *,
    run_selection_mode: str,
    runs: list[dict[str, Any]],
    backtest_root: Path,
    baseline_config_path: Path,
) -> tuple[Path, Path, Path]:
    if not runs:
        raise FileNotFoundError(f"No valid backtest runs found under {backtest_root.resolve()}")

    latest_run_dir = Path(runs[0]["run_dir"])
    try:
        latest_current_baseline_dir = resolve_latest_default_baseline_run(
            backtest_root=backtest_root,
            baseline_config_path=baseline_config_path,
        ).resolve()
    except Exception:
        latest_current_baseline_dir = latest_run_dir

    if run_selection_mode == "current_baseline_family":
        default_run_dir = latest_current_baseline_dir
    elif run_selection_mode == "latest_run":
        default_run_dir = latest_run_dir
    else:
        raise ValueError(f"Unsupported run_selection_mode: {run_selection_mode}")

    return default_run_dir, latest_run_dir, latest_current_baseline_dir


def load_run_artifacts(run_dir: Path) -> BacktestRunArtifacts:
    summary = json.loads((run_dir / "summary.json").read_text())

    equity_curve = pd.read_csv(run_dir / "equity_curve.csv")
    equity_curve["trade_date"] = pd.to_datetime(equity_curve["trade_date"])

    daily_path = run_dir / "daily_market_value.csv"
    daily_market_value = pd.read_csv(daily_path) if daily_path.exists() else None
    if daily_market_value is not None and "trade_date" in daily_market_value.columns:
        daily_market_value["trade_date"] = pd.to_datetime(daily_market_value["trade_date"])

    weights_path = run_dir / "weights_history.csv"
    weights_history = pd.read_csv(weights_path) if weights_path.exists() else None
    if weights_history is not None and "trade_date" in weights_history.columns:
        weights_history["trade_date"] = pd.to_datetime(weights_history["trade_date"])

    orders_path = run_dir / "orders_history.csv"
    orders_history = pd.read_csv(orders_path) if orders_path.exists() else None
    if orders_history is not None and "trade_date" in orders_history.columns:
        orders_history["trade_date"] = pd.to_datetime(orders_history["trade_date"])

    return BacktestRunArtifacts(
        run_dir=run_dir,
        summary=summary,
        equity_curve=equity_curve,
        daily_market_value=daily_market_value,
        weights_history=weights_history,
        orders_history=orders_history,
    )


def build_viewer_context(
    *,
    run_selection_mode: str,
    manual_run_dir: str | Path | None = None,
    repo_root: Path | None = None,
    run_table_limit: int = 12,
) -> BacktestViewerContext:
    resolved_repo_root = (repo_root or resolve_repo_root()).resolve()
    backtest_root = resolve_backtest_root(resolved_repo_root)
    baseline_config_path = resolve_baseline_config_path(resolved_repo_root)
    runs = collect_runs(backtest_root)
    default_run_dir, latest_run_dir, latest_current_baseline_dir = resolve_default_run_dir(
        run_selection_mode=run_selection_mode,
        runs=runs,
        backtest_root=backtest_root,
        baseline_config_path=baseline_config_path,
    )
    run_dir = Path(manual_run_dir).expanduser() if manual_run_dir else default_run_dir
    if not run_dir.is_absolute():
        run_dir = (resolved_repo_root / run_dir).resolve()
    artifacts = load_run_artifacts(run_dir)

    return BacktestViewerContext(
        repo_root=resolved_repo_root,
        backtest_root=backtest_root,
        baseline_config_path=baseline_config_path,
        runs=runs,
        run_selection_mode=run_selection_mode,
        latest_run_dir=latest_run_dir,
        latest_current_baseline_dir=latest_current_baseline_dir,
        default_run_dir=run_dir,
        run_table=run_table(runs, limit=run_table_limit),
        artifacts=artifacts,
    )
