from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SECTOR_SYMBOLS = ["XLF", "XLK", "XLY", "XLP", "XLU", "XLV", "XLE", "XLI", "XLB", "XLRE"]
BASE_SYMBOLS = ["SPY", "RSP", "QQQ", "IWM", "HYG", "LQD", "TLT", "SHY", "UUP", "^VIX", "^VIX9D", "^VIX3M"]
SYMBOLS = BASE_SYMBOLS + SECTOR_SYMBOLS

FORWARD_TAIL_THRESHOLDS = {
    1: -0.015,
    3: -0.020,
    5: -0.030,
    10: -0.040,
}
PRIMARY_TAIL_HORIZON = 5
MAX_FORWARD_HORIZON = max(FORWARD_TAIL_THRESHOLDS)

BREADTH_Z_THRESHOLD = 1.0
SECTOR_DOWN_PCT_THRESHOLD = 0.70
CREDIT_STRESS_Z_THRESHOLD = 1.0
VOL_SHOCK_Z_THRESHOLD = 1.5
LATE_LIQUIDATION_THRESHOLD = -0.008
MACRO_FLAG_Z_THRESHOLD = 1.0
MACRO_WATCH_SCORE = 2
MACRO_RISK_OFF_SCORE = 3
FRAGILITY_EVENT_CONFIRMATION_SCORE = 1
ROLL_LONG = 252
ROLL_MED = 126


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the SPY fragility dashboard signal table from local market data."
    )
    parser.add_argument("--start-date", default="2021-01-01", help="Signal window start date.")
    parser.add_argument("--end-date", default=None, help="Optional signal window end date.")
    parser.add_argument("--data-root", default="data/market", help="Local market data root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text tables.")
    return parser.parse_args()


def latest_history_file(symbol: str, data_root: str) -> Path:
    symbol_dir = Path(data_root) / symbol
    files = sorted(symbol_dir.glob("history_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet history files found for {symbol} under {symbol_dir}")
    return files[-1]


def load_symbol(symbol: str, data_root: str) -> pd.DataFrame:
    path = latest_history_file(symbol, data_root)
    df = pd.read_parquet(path).copy()
    if "Date" not in df.columns:
        raise ValueError(f"Unexpected schema for {symbol}: missing Date column")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").drop_duplicates("Date").set_index("Date")
    return df[["Open", "High", "Low", "Close", "Adj Close", "Volume"]].rename(
        columns={
            "Open": f"{symbol}_open",
            "High": f"{symbol}_high",
            "Low": f"{symbol}_low",
            "Close": f"{symbol}_close",
            "Adj Close": f"{symbol}_adj_close",
            "Volume": f"{symbol}_volume",
        }
    )


def rolling_z(series: pd.Series, window: int) -> pd.Series:
    prior_mean = series.rolling(window, min_periods=max(20, window // 4)).mean().shift(1)
    prior_std = series.rolling(window, min_periods=max(20, window // 4)).std().shift(1)
    return (series - prior_mean) / prior_std.replace(0, np.nan)


def classify_fragility_regime(rule_stress_score: pd.Series, macro_stress_score: pd.Series) -> pd.Series:
    risk_off = (macro_stress_score >= MACRO_WATCH_SCORE) | (rule_stress_score >= 3)
    watch = ~risk_off & ((macro_stress_score == 1) | rule_stress_score.between(1, 2))
    return pd.Series(
        np.select([risk_off, watch], ["risk_off", "watch"], default="normal"),
        index=rule_stress_score.index,
    )


def build_signals(
    start_date: str = "2021-01-01",
    end_date: str | None = None,
    data_root: str = "data/market",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.concat([load_symbol(symbol, data_root) for symbol in SYMBOLS], axis=1).sort_index()
    raw = raw.loc[pd.Timestamp(start_date) :]
    if end_date:
        raw = raw.loc[: pd.Timestamp(end_date)]

    df = raw.dropna(subset=["SPY_adj_close", "RSP_adj_close", "^VIX_adj_close"]).copy()
    for symbol in SYMBOLS:
        close_col = f"{symbol}_adj_close"
        if close_col in df:
            df[f"{symbol}_ret"] = df[close_col].pct_change(fill_method=None)

    df["spy_ret"] = df["SPY_ret"]
    spy_price = df["SPY_adj_close"]
    forward_path_returns = pd.concat(
        {step: spy_price.shift(-step) / spy_price - 1 for step in range(1, MAX_FORWARD_HORIZON + 1)},
        axis=1,
    )
    for horizon, threshold in FORWARD_TAIL_THRESHOLDS.items():
        horizon_path = forward_path_returns.loc[:, 1:horizon]
        has_full_horizon = forward_path_returns[horizon].notna()
        df[f"fwd_{horizon}d_ret"] = forward_path_returns[horizon]
        df[f"fwd_{horizon}d_min_ret"] = horizon_path.min(axis=1).where(has_full_horizon)
        df[f"fwd_{horizon}d_tail"] = (df[f"fwd_{horizon}d_min_ret"] <= threshold).where(has_full_horizon)
    df["spy_next_ret"] = df["fwd_1d_ret"]
    df["spy_next_tail"] = df["fwd_1d_tail"]

    df["breadth_gap"] = df["RSP_ret"] - df["SPY_ret"]
    df["breadth_stress"] = -df["breadth_gap"]
    df["breadth_z"] = rolling_z(df["breadth_stress"], ROLL_LONG)
    sector_ret_cols = [f"{symbol}_ret" for symbol in SECTOR_SYMBOLS if f"{symbol}_ret" in df]
    df["sector_count"] = df[sector_ret_cols].notna().sum(axis=1)
    df["sector_down_count"] = (df[sector_ret_cols] < 0).sum(axis=1)
    df["sector_down_pct"] = df["sector_down_count"] / df["sector_count"].replace(0, np.nan)
    df["breadth_break"] = (
        (df["spy_ret"] < 0)
        & (df["breadth_z"] >= BREADTH_Z_THRESHOLD)
        & (df["sector_down_pct"] >= SECTOR_DOWN_PCT_THRESHOLD)
    )

    df["credit_stress"] = -(df["HYG_ret"] - df["LQD_ret"])
    df["credit_z"] = rolling_z(df["credit_stress"], ROLL_MED)
    df["vix_ret"] = df["^VIX_adj_close"].pct_change(fill_method=None)
    df["vix_shock_z"] = rolling_z(df["vix_ret"], ROLL_MED)
    df["spy_intraday_ret"] = df["SPY_close"] / df["SPY_open"] - 1
    df["late_liquidation"] = (df["spy_ret"] < 0) & (df["spy_intraday_ret"] <= LATE_LIQUIDATION_THRESHOLD)
    df["credit_stress_flag"] = (df["spy_ret"] < 0) & (df["credit_z"] >= CREDIT_STRESS_Z_THRESHOLD)
    df["vol_shock_flag"] = (df["spy_ret"] < 0) & (df["vix_shock_z"] >= VOL_SHOCK_Z_THRESHOLD)
    rule_flags = ["breadth_break", "credit_stress_flag", "vol_shock_flag", "late_liquidation"]
    df["rule_stress_score"] = df[rule_flags].sum(axis=1)
    df["rule_regime"] = np.select(
        [df["rule_stress_score"] >= 3, df["rule_stress_score"] >= 1],
        ["risk_off", "watch"],
        default="normal",
    )

    df["vix_level_z"] = rolling_z(df["^VIX_adj_close"], ROLL_LONG)
    df["vix_backwardation"] = df["^VIX9D_adj_close"] > df["^VIX3M_adj_close"]
    df["credit_ratio"] = df["HYG_adj_close"] / df["LQD_adj_close"]
    df["credit_ratio_stress_z"] = rolling_z(-df["credit_ratio"].pct_change(20, fill_method=None), ROLL_LONG)
    df["duration_stress_z"] = rolling_z(-(df["TLT_ret"] - df["SHY_ret"]), ROLL_MED)
    df["dollar_strength_z"] = rolling_z(df["UUP_adj_close"].pct_change(20, fill_method=None), ROLL_LONG)

    macro_flag_cols = macro_flags()
    df["macro_elevated_vix"] = df["vix_level_z"] >= MACRO_FLAG_Z_THRESHOLD
    df["macro_vix_backwardation"] = df["vix_backwardation"]
    df["macro_weak_credit"] = df["credit_ratio_stress_z"] >= MACRO_FLAG_Z_THRESHOLD
    df["macro_duration_pressure"] = df["duration_stress_z"] >= MACRO_FLAG_Z_THRESHOLD
    df["macro_dollar_strength"] = df["dollar_strength_z"] >= MACRO_FLAG_Z_THRESHOLD
    df["macro_stress_score"] = df[macro_flag_cols].sum(axis=1)
    df["macro_regime"] = np.select(
        [df["macro_stress_score"] >= MACRO_RISK_OFF_SCORE, df["macro_stress_score"] == MACRO_WATCH_SCORE],
        ["risk_off", "watch"],
        default="normal",
    )

    df["fragility_risk_off_v1"] = (
        (df["macro_stress_score"] >= MACRO_RISK_OFF_SCORE)
        | (
            (df["macro_stress_score"] >= MACRO_WATCH_SCORE)
            & (df["rule_stress_score"] >= FRAGILITY_EVENT_CONFIRMATION_SCORE)
        )
    )
    df["fragility_watch_v1"] = (
        ~df["fragility_risk_off_v1"]
        & (
            (df["macro_stress_score"] >= MACRO_WATCH_SCORE)
            | (df["rule_stress_score"] >= FRAGILITY_EVENT_CONFIRMATION_SCORE)
            | df["breadth_break"]
        )
    )
    df["fragility_regime_v1"] = np.select(
        [df["fragility_risk_off_v1"], df["fragility_watch_v1"]],
        ["risk_off", "watch"],
        default="normal",
    )

    df["fragility_regime"] = classify_fragility_regime(df["rule_stress_score"], df["macro_stress_score"])
    df["fragility_risk_off"] = df["fragility_regime"] == "risk_off"
    df["fragility_watch"] = df["fragility_regime"] == "watch"

    dashboard_cols = dashboard_columns()
    signals = df[dashboard_cols].dropna(subset=["spy_ret"]).copy()
    return df, signals


def macro_flags() -> list[str]:
    return [
        "macro_elevated_vix",
        "macro_vix_backwardation",
        "macro_weak_credit",
        "macro_duration_pressure",
        "macro_dollar_strength",
    ]


def dashboard_columns() -> list[str]:
    forward_cols: list[str] = []
    for horizon in FORWARD_TAIL_THRESHOLDS:
        forward_cols.extend([f"fwd_{horizon}d_ret", f"fwd_{horizon}d_min_ret", f"fwd_{horizon}d_tail"])
    return [
        "spy_ret",
        "spy_next_ret",
        "breadth_gap",
        "breadth_z",
        "sector_down_count",
        "sector_count",
        "sector_down_pct",
        "breadth_break",
        "credit_z",
        "vix_shock_z",
        "credit_stress_flag",
        "vol_shock_flag",
        "late_liquidation",
        "rule_stress_score",
        "rule_regime",
        "macro_stress_score",
        "macro_regime",
        "fragility_regime_v1",
        "fragility_regime",
        "spy_next_tail",
        *forward_cols,
        *macro_flags(),
    ]


def summarize_signal(evaluation_signals: pd.DataFrame, mask: pd.Series, label: str) -> dict[str, Any]:
    sample = evaluation_signals.loc[mask.reindex(evaluation_signals.index).fillna(False)]
    row: dict[str, Any] = {"signal": label, "days": int(len(sample))}
    for horizon, threshold in FORWARD_TAIL_THRESHOLDS.items():
        tail_col = f"fwd_{horizon}d_tail"
        min_ret_col = f"fwd_{horizon}d_min_ret"
        final_ret_col = f"fwd_{horizon}d_ret"
        row[f"{horizon}d_path_tail_rate"] = float(sample[tail_col].mean()) if len(sample) else np.nan
        row[f"{horizon}d_avg_min_ret"] = float(sample[min_ret_col].mean()) if len(sample) else np.nan
        row[f"{horizon}d_median_min_ret"] = float(sample[min_ret_col].median()) if len(sample) else np.nan
        row[f"{horizon}d_avg_final_ret"] = float(sample[final_ret_col].mean()) if len(sample) else np.nan
        row[f"{horizon}d_tail_threshold"] = float(threshold)
    return row


def build_summary(signals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    evaluation_signals = signals.dropna(subset=[f"fwd_{MAX_FORWARD_HORIZON}d_min_ret"]).copy()
    baseline_all = summarize_signal(evaluation_signals, pd.Series(True, index=evaluation_signals.index), "all_days")
    baseline_spy_down = summarize_signal(
        evaluation_signals,
        evaluation_signals["spy_ret"] < 0,
        "spy_down_days",
    )
    rows = [
        baseline_all,
        baseline_spy_down,
        summarize_signal(evaluation_signals, evaluation_signals["breadth_z"] >= BREADTH_Z_THRESHOLD, "breadth_z_only"),
        summarize_signal(evaluation_signals, evaluation_signals["breadth_break"], "breadth_break"),
        summarize_signal(evaluation_signals, evaluation_signals["rule_regime"] == "watch", "event_watch"),
        summarize_signal(evaluation_signals, evaluation_signals["rule_regime"] == "risk_off", "event_risk_off"),
        summarize_signal(evaluation_signals, evaluation_signals["macro_regime"] == "watch", "macro_watch"),
        summarize_signal(evaluation_signals, evaluation_signals["macro_regime"] == "risk_off", "macro_risk_off"),
        summarize_signal(evaluation_signals, evaluation_signals["fragility_regime_v1"] == "watch", "fragility_watch_v1"),
        summarize_signal(
            evaluation_signals,
            evaluation_signals["fragility_regime_v1"] == "risk_off",
            "fragility_risk_off_v1",
        ),
        summarize_signal(evaluation_signals, evaluation_signals["fragility_regime"] == "watch", "fragility_watch"),
        summarize_signal(evaluation_signals, evaluation_signals["fragility_regime"] == "risk_off", "fragility_risk_off"),
        summarize_signal(
            evaluation_signals,
            (evaluation_signals["rule_stress_score"] >= FRAGILITY_EVENT_CONFIRMATION_SCORE)
            & (evaluation_signals["macro_stress_score"] >= MACRO_WATCH_SCORE),
            "event_confirmed_by_macro_watch_or_worse",
        ),
    ]
    summary = pd.DataFrame(rows)
    primary_tail_col = f"{PRIMARY_TAIL_HORIZON}d_path_tail_rate"
    summary[f"{PRIMARY_TAIL_HORIZON}d_tail_lift_vs_all"] = summary[primary_tail_col] / baseline_all[primary_tail_col]
    summary[f"{PRIMARY_TAIL_HORIZON}d_tail_lift_vs_spy_down"] = (
        summary[primary_tail_col] / baseline_spy_down[primary_tail_col]
    )

    score_rows: list[dict[str, Any]] = []
    for score in sorted(evaluation_signals["rule_stress_score"].dropna().unique()):
        score_rows.append(
            summarize_signal(evaluation_signals, evaluation_signals["rule_stress_score"] == score, f"event_score_{int(score)}")
        )
    for score in sorted(evaluation_signals["macro_stress_score"].dropna().unique()):
        score_rows.append(
            summarize_signal(evaluation_signals, evaluation_signals["macro_stress_score"] == score, f"macro_score_{int(score)}")
        )
    score_buckets = pd.DataFrame(score_rows)
    score_buckets[f"{PRIMARY_TAIL_HORIZON}d_tail_lift_vs_all"] = (
        score_buckets[primary_tail_col] / baseline_all[primary_tail_col]
    )
    return summary, score_buckets


def latest_snapshot(df: pd.DataFrame, signals: pd.DataFrame) -> dict[str, Any]:
    latest = signals.iloc[-1]
    dt = signals.index[-1]
    return {
        "date": str(dt.date()),
        "spy_close": float(df.loc[dt, "SPY_adj_close"]),
        "spy_ret": float(latest["spy_ret"]),
        "rule_regime": str(latest["rule_regime"]),
        "rule_stress_score": int(latest["rule_stress_score"]),
        "macro_regime": str(latest["macro_regime"]),
        "macro_stress_score": int(latest["macro_stress_score"]),
        "fragility_regime_v1": str(latest["fragility_regime_v1"]),
        "fragility_regime": str(latest["fragility_regime"]),
        "breadth_break": bool(latest["breadth_break"]),
        "breadth_z": float(latest["breadth_z"]),
        "sector_down_pct": float(latest["sector_down_pct"]),
        "credit_z": float(latest["credit_z"]),
        "vix_shock_z": float(latest["vix_shock_z"]),
        "macro_flags": {col: bool(latest[col]) for col in macro_flags()},
    }


def _jsonable_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.replace({np.nan: None}).to_json(orient="records"))


def main() -> None:
    args = parse_args()
    df, signals = build_signals(start_date=args.start_date, end_date=args.end_date, data_root=args.data_root)
    summary, score_buckets = build_summary(signals)
    summary_cols = [
        "signal",
        "days",
        "1d_path_tail_rate",
        "3d_path_tail_rate",
        "5d_path_tail_rate",
        "10d_path_tail_rate",
        "5d_tail_lift_vs_all",
        "5d_tail_lift_vs_spy_down",
        "5d_avg_min_ret",
        "10d_avg_min_ret",
    ]
    bucket_cols = [
        "signal",
        "days",
        "5d_path_tail_rate",
        "10d_path_tail_rate",
        "5d_tail_lift_vs_all",
        "5d_avg_min_ret",
        "10d_avg_min_ret",
    ]
    payload = {
        "window": {
            "start": str(signals.index.min().date()),
            "end": str(signals.index.max().date()),
            "rows": int(len(signals)),
            "evaluation_rows": int(signals[f"fwd_{MAX_FORWARD_HORIZON}d_min_ret"].notna().sum()),
        },
        "latest": latest_snapshot(df, signals),
        "summary": _jsonable_frame(summary[summary_cols]),
        "score_buckets": _jsonable_frame(score_buckets[bucket_cols]),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(f"Window: {payload['window']['start']} -> {payload['window']['end']} rows={payload['window']['rows']}")
    print("Latest:", json.dumps(payload["latest"], sort_keys=True))
    print("\nSignal summary:")
    print(summary[summary_cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("\nScore buckets:")
    print(score_buckets[bucket_cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
