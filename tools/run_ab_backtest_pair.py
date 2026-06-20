from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from activeportfolio.alpha import AlphaModel, apply_alpha_profile
from activeportfolio.backtest import BacktestEngine
from activeportfolio.default_config import DEFAULT_CONFIG


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run and save an A/B backtest pair in one folder.")
    p.add_argument("--pair-name", required=True, help="Short pair name (e.g. regime_on_vs_off).")
    p.add_argument("--start-date", required=True, help="Requested backtest start date (YYYY-MM-DD).")
    p.add_argument("--end-date", required=True, help="Backtest end date (YYYY-MM-DD).")
    p.add_argument("--base-profile", default="momentum_heavy", help="Optional alpha profile to apply first.")
    p.add_argument("--config-a-json", default=None, help="JSON overrides for run A.")
    p.add_argument("--config-b-json", default=None, help="JSON overrides for run B.")
    p.add_argument("--label-a", default="A", help="Run A label.")
    p.add_argument("--label-b", default="B", help="Run B label.")
    p.add_argument("--out-root", default="eval_results/backtest/ab_pairs", help="Pair output root.")
    p.add_argument("--data-root", default="data/market", help="Market data root.")
    p.add_argument(
        "--auto-adjust-start-for-warmup",
        action="store_true",
        help="Auto-shift start date forward if anchor data + warmup require it.",
    )
    p.add_argument(
        "--no-auto-adjust-start-for-warmup",
        action="store_true",
        help="Disable auto-adjustment; keep requested start date.",
    )
    p.add_argument(
        "--run-status",
        default="scratch",
        help="Lifecycle status to record in the pair manifest (e.g. scratch, candidate, bad_test).",
    )
    p.add_argument(
        "--keep-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Whether to mark this pair run as retained in manifest.json.",
    )
    return p.parse_args()


def load_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config JSON must be object: {p}")
    return payload


def alpha_context_symbols_from_config(config: dict[str, Any]) -> list[str]:
    out: list[str] = []
    reg = config.get("alpha_signal_registry", [])
    if not isinstance(reg, list):
        return out
    for spec in reg:
        if not isinstance(spec, dict):
            continue
        if not bool(spec.get("enabled", True)):
            continue
        typ = str(spec.get("type", "")).strip().lower()
        if typ == "btc_gld_corr":
            risk = str(spec.get("risk_symbol", "BTC-USD")).upper()
            defensive = str(spec.get("defensive_symbol", "GLD")).upper()
            if risk:
                out.append(risk)
            if defensive:
                out.append(defensive)
    dedup: list[str] = []
    seen: set[str] = set()
    for s in out:
        if s not in seen:
            dedup.append(s)
            seen.add(s)
    return dedup


def parse_history_name(path: Path) -> tuple[datetime, datetime] | None:
    stem = path.stem
    if not stem.startswith("history_"):
        return None
    parts = stem.split("_")
    if len(parts) != 3:
        return None
    try:
        return (
            datetime.strptime(parts[1], "%Y-%m-%d"),
            datetime.strptime(parts[2], "%Y-%m-%d"),
        )
    except ValueError:
        return None


def symbol_date_bounds(data_root: Path, symbol: str) -> tuple[datetime, datetime] | None:
    symbol_dir = data_root / symbol.upper()
    if not symbol_dir.exists():
        return None
    starts: list[datetime] = []
    ends: list[datetime] = []
    for p in symbol_dir.glob("history_*.parquet"):
        parsed = parse_history_name(p)
        if parsed is None:
            continue
        starts.append(parsed[0])
        ends.append(parsed[1])
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def required_warmup_days(config: dict[str, Any]) -> int:
    model = AlphaModel.from_config(config)
    risk_lookback = int(config.get("alpha_lookback_days", 252)) + 1
    long_lb = int(model.long_lookback) + 1
    vol_lb = int(model.vol_lookback) + 2
    return max(risk_lookback, long_lb, vol_lb) * 2


def resolve_config(base_config: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    config = dict(base_config)
    config.update(overrides)
    alpha_profile = str(config.get("alpha_profile") or "").strip()
    if alpha_profile:
        config = apply_alpha_profile(config, alpha_profile, overwrite=True)
    return config


def _git_head() -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
    except Exception:
        return None
    return out.decode("utf-8").strip()


def main() -> None:
    args = parse_args()
    auto_adjust = bool(args.auto_adjust_start_for_warmup) and not bool(
        args.no_auto_adjust_start_for_warmup
    )
    requested_start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

    base = DEFAULT_CONFIG.copy()
    if args.base_profile:
        base = apply_alpha_profile(base, args.base_profile)

    cfg_a = resolve_config(base, load_json(args.config_a_json))
    cfg_b = resolve_config(base, load_json(args.config_b_json))

    # Warmup requirement from both sides (take worst case).
    warmup_days = max(required_warmup_days(cfg_a), required_warmup_days(cfg_b))

    # Anchor symbols for start-date feasibility.
    anchors = {
        str(cfg_a.get("benchmark_symbol", "SPY")).upper(),
        str(cfg_b.get("benchmark_symbol", "SPY")).upper(),
    }
    for c in [cfg_a, cfg_b]:
        anchors.update(alpha_context_symbols_from_config(c))
        if bool(c.get("regime_switch_enabled", False)):
            anchors.add(str(c.get("regime_risk_symbol", "BTC-USD")).upper())
            anchors.add(str(c.get("regime_defensive_symbol", "GLD")).upper())
    anchors = {s for s in anchors if s}

    data_root = Path(args.data_root)
    bounds = {s: symbol_date_bounds(data_root, s) for s in sorted(anchors)}
    bounds = {s: v for s, v in bounds.items() if v is not None}
    if bounds:
        common_anchor_start = max(v[0] for v in bounds.values())
        common_anchor_end = min(v[1] for v in bounds.values())
    else:
        common_anchor_start = requested_start
        common_anchor_end = end_date

    feasible_start = common_anchor_start + timedelta(days=warmup_days)
    actual_start = max(requested_start, feasible_start) if auto_adjust else requested_start
    if actual_start > end_date:
        raise ValueError(
            f"Start date after end date after warmup adjustment: start={actual_start.date()} end={end_date.date()}"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pair_dir = Path(args.out_root) / f"{stamp}_{args.pair_name}"
    pair_dir.mkdir(parents=True, exist_ok=True)

    run_a_dir = pair_dir / "run_a"
    run_b_dir = pair_dir / "run_b"
    cfg_a["backtest_start_date"] = actual_start.strftime("%Y-%m-%d")
    cfg_a["backtest_end_date"] = end_date.strftime("%Y-%m-%d")
    cfg_a["backtest_output_dir"] = str(run_a_dir)
    cfg_b["backtest_start_date"] = actual_start.strftime("%Y-%m-%d")
    cfg_b["backtest_end_date"] = end_date.strftime("%Y-%m-%d")
    cfg_b["backtest_output_dir"] = str(run_b_dir)

    res_a = BacktestEngine(cfg_a).run(fallback_symbol=str(cfg_a.get("benchmark_symbol", "SPY")).upper())
    res_b = BacktestEngine(cfg_b).run(fallback_symbol=str(cfg_b.get("benchmark_symbol", "SPY")).upper())

    keys = [
        "total_return",
        "cagr",
        "sharpe",
        "max_drawdown",
        "tracking_error",
        "realized_active_information_ratio",
        "average_transfer_coefficient",
        "average_transfer_coefficient_legacy_proxy",
        "average_executed_turnover",
        "average_raw_turnover",
        "average_turnover_constraint_drag",
        "average_ic",
    ]
    sa = res_a["summary"]
    sb = res_b["summary"]
    delta = {}
    for k in keys:
        a = sa.get(k)
        b = sb.get(k)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a == a and b == b:
            delta[k] = b - a
        else:
            delta[k] = None

    pair_payload = {
        "pair_name": args.pair_name,
        "created_at_utc": stamp,
        "labels": {"a": args.label_a, "b": args.label_b},
        "requested_window": {"start": args.start_date, "end": args.end_date},
        "actual_window": {
            "start": actual_start.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "warmup": {
            "required_days": warmup_days,
            "auto_adjust_start_for_warmup": auto_adjust,
            "common_anchor_start": common_anchor_start.strftime("%Y-%m-%d"),
            "common_anchor_end": common_anchor_end.strftime("%Y-%m-%d"),
            "feasible_start_from_anchors": feasible_start.strftime("%Y-%m-%d"),
            "anchors": sorted(anchors),
        },
        "run_a": {"dir": str(run_a_dir), "summary": {k: sa.get(k) for k in keys}},
        "run_b": {"dir": str(run_b_dir), "summary": {k: sb.get(k) for k in keys}},
        "delta_b_minus_a": delta,
    }
    (pair_dir / "comparison.json").write_text(
        json.dumps(pair_payload, indent=2), encoding="utf-8"
    )
    (pair_dir / "config_a.json").write_text(json.dumps(cfg_a, indent=2), encoding="utf-8")
    (pair_dir / "config_b.json").write_text(json.dumps(cfg_b, indent=2), encoding="utf-8")
    (pair_dir / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "backtest_pair",
                "pair_name": args.pair_name,
                "created_at_utc": datetime.now(tz=timezone.utc).isoformat(),
                "command": " ".join(sys.argv),
                "python_version": platform.python_version(),
                "git_head": _git_head(),
                "status": str(args.run_status).strip() or "scratch",
                "keep": bool(args.keep_run),
                "artifacts": {
                    "comparison_json": str(pair_dir / "comparison.json"),
                    "config_a_json": str(pair_dir / "config_a.json"),
                    "config_b_json": str(pair_dir / "config_b.json"),
                    "run_a_dir": str(run_a_dir),
                    "run_b_dir": str(run_b_dir),
                },
                "requested_window": pair_payload["requested_window"],
                "actual_window": pair_payload["actual_window"],
                "labels": pair_payload["labels"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[ok] pair_dir: {pair_dir}")
    print(
        f"[ok] window requested={args.start_date}..{args.end_date} "
        f"actual={actual_start.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    )
    print(f"[ok] warmup_days={warmup_days}")
    print(f"[ok] run_a: {run_a_dir}")
    print(f"[ok] run_b: {run_b_dir}")
    print(f"[ok] comparison: {pair_dir / 'comparison.json'}")
    print(json.dumps(pair_payload["delta_b_minus_a"], indent=2))


if __name__ == "__main__":
    main()
