from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from activeportfolio.dataflows.fred_macro import FREDMacroStore
from activeportfolio.default_config import DEFAULT_CONFIG
from activeportfolio.regime import (
    FREDMacroRegimeModel,
    RuleBasedRegimeModelV2,
    regime_stage_title,
    summarize_regime,
)


def load_config_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config JSON must be an object: {path}")
    return payload


def build_regime_config(config_json: str | None) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config.update(load_config_json(config_json))
    return config


def build_macro_model(config: dict[str, Any]) -> FREDMacroRegimeModel:
    return FREDMacroRegimeModel(
        macro_store=FREDMacroStore(
            root_dir=str(config.get("regime_macro_data_root", "data/macro/fred")),
            auto_download=bool(config.get("regime_macro_auto_download", True)),
        ),
        macro_lookback_days=int(config.get("regime_macro_lookback_days", 800)),
        unemployment_series_id=str(config.get("regime_macro_unemployment_series_id", "UNRATE")).upper(),
        inflation_series_id=str(config.get("regime_macro_inflation_series_id", "CPIAUCSL")).upper(),
        growth_series_id=str(config.get("regime_macro_growth_series_id", "INDPRO")).upper(),
        curve_series_id=str(config.get("regime_macro_curve_series_id", "T10Y2Y")).upper(),
        policy_series_id=str(config.get("regime_macro_policy_series_id", "FEDFUNDS")).upper(),
        stress_series_id=str(config.get("regime_macro_stress_series_id", "VIXCLS")).upper(),
        unemployment_lag_days=int(config.get("regime_macro_unemployment_lag_days", 35)),
        inflation_lag_days=int(config.get("regime_macro_inflation_lag_days", 35)),
        growth_lag_days=int(config.get("regime_macro_growth_lag_days", 35)),
        curve_lag_days=int(config.get("regime_macro_curve_lag_days", 1)),
        policy_lag_days=int(config.get("regime_macro_policy_lag_days", 35)),
        stress_lag_days=int(config.get("regime_macro_stress_lag_days", 1)),
        risk_on_threshold=float(config.get("regime_risk_on_threshold", 0.15)),
        risk_off_threshold=float(config.get("regime_risk_off_threshold", -0.15)),
        temperature=float(config.get("regime_temperature", 0.20)),
        growth_weight=float(config.get("regime_macro_growth_weight", 0.25)),
        labor_weight=float(config.get("regime_macro_labor_weight", 0.20)),
        inflation_weight=float(config.get("regime_macro_inflation_weight", 0.15)),
        curve_weight=float(config.get("regime_macro_curve_weight", 0.15)),
        policy_weight=float(config.get("regime_macro_policy_weight", 0.10)),
        stress_weight=float(config.get("regime_macro_stress_weight", 0.15)),
    )


def build_rule_v2_model(config: dict[str, Any]) -> RuleBasedRegimeModelV2:
    speculative_symbols = tuple(
        str(s).upper()
        for s in config.get("regime_v2_speculative_symbols", ["BTC-USD", "ETH-USD"])
        if str(s).strip()
    )
    return RuleBasedRegimeModelV2(
        benchmark_symbol=str(config.get("regime_benchmark_symbol", config.get("benchmark_symbol", "SPY"))).upper(),
        duration_symbol=str(config.get("regime_v2_duration_symbol", "TLT")).upper(),
        defensive_symbol=str(config.get("regime_v2_defensive_symbol", "GLD")).upper(),
        growth_symbol=str(config.get("regime_v2_growth_symbol", "XLK")).upper(),
        inflation_symbol=str(config.get("regime_v2_inflation_symbol", "XLE")).upper(),
        speculative_symbols=speculative_symbols,
        short_window=int(config.get("regime_short_window", 21)),
        long_window=int(config.get("regime_long_window", 63)),
        relative_window=int(config.get("regime_relative_window", 63)),
        risk_on_threshold=float(config.get("regime_risk_on_threshold", 0.15)),
        risk_off_threshold=float(config.get("regime_risk_off_threshold", -0.15)),
        temperature=float(config.get("regime_temperature", 0.20)),
    )


def evaluate_macro_regime(asof_date: str, config: dict[str, Any]) -> dict[str, Any]:
    ts = pd.Timestamp(datetime.strptime(asof_date, "%Y-%m-%d"))
    close_history = pd.DataFrame({"SPY": [1.0, 1.0]}, index=[ts - pd.Timedelta(days=1), ts])
    decision = build_macro_model(config).detect(close_history)
    regime = {
        "asof_date": asof_date,
        "label": decision.label,
        "title": regime_stage_title(decision.label),
        "score": float(decision.score),
        "probabilities": dict(decision.probabilities),
        "diagnostics": dict(decision.diagnostics),
    }
    regime["summary"] = summarize_regime(regime)
    return regime


def load_live_market_history(symbols: list[str], asof_date: str, lookback_days: int = 180) -> pd.DataFrame:
    end_dt = datetime.strptime(asof_date, "%Y-%m-%d")
    start_dt = end_dt - pd.Timedelta(days=int(lookback_days))
    df = yf.download(
        symbols,
        start=start_dt.strftime("%Y-%m-%d"),
        end=(end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        group_by="ticker",
        multi_level_index=True,
    )
    per_symbol: dict[str, pd.Series] = {}
    for symbol in symbols:
        try:
            if isinstance(df.columns, pd.MultiIndex):
                sub = df[symbol]
                col = "Adj Close" if "Adj Close" in sub.columns else "Close"
                s = pd.to_numeric(sub[col], errors="coerce")
            else:
                col = "Adj Close" if "Adj Close" in df.columns else "Close"
                s = pd.to_numeric(df[col], errors="coerce")
            per_symbol[symbol] = s.rename(symbol)
        except Exception:
            continue
    if len(per_symbol) < 2:
        raise ValueError("Need at least two live market series for rule_v2 report.")
    frame = pd.concat(per_symbol.values(), axis=1).sort_index().ffill()
    frame = frame.dropna(axis=1, how="all")
    return frame


def evaluate_rule_v2_regime(asof_date: str, config: dict[str, Any]) -> dict[str, Any]:
    symbols = [
        str(config.get("regime_benchmark_symbol", config.get("benchmark_symbol", "SPY"))).upper(),
        str(config.get("regime_v2_duration_symbol", "TLT")).upper(),
        str(config.get("regime_v2_defensive_symbol", "GLD")).upper(),
        str(config.get("regime_v2_growth_symbol", "XLK")).upper(),
        str(config.get("regime_v2_inflation_symbol", "XLE")).upper(),
    ]
    symbols.extend(
        str(s).upper()
        for s in config.get("regime_v2_speculative_symbols", ["BTC-USD", "ETH-USD"])
        if str(s).strip()
    )
    dedup_symbols = list(dict.fromkeys(symbols))
    market_history = load_live_market_history(dedup_symbols, asof_date=asof_date, lookback_days=220)
    decision = build_rule_v2_model(config).detect(market_history)
    effective_asof = pd.Timestamp(market_history.index.max()).strftime("%Y-%m-%d")
    regime = {
        "asof_date": asof_date,
        "market_asof_date": effective_asof,
        "label": decision.label,
        "title": regime_stage_title(decision.label),
        "score": float(decision.score),
        "probabilities": dict(decision.probabilities),
        "diagnostics": dict(decision.diagnostics),
    }
    regime["summary"] = summarize_regime(regime)
    return regime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report macro and rule_v2 market regimes.")
    parser.add_argument("--config-json", default=None, help="Optional JSON file with regime config overrides.")
    parser.add_argument("--asof-date", default=None, help="As-of date YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a markdown-style summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asof_date = args.asof_date or datetime.today().strftime("%Y-%m-%d")
    config = build_regime_config(args.config_json)
    macro_regime = evaluate_macro_regime(asof_date=asof_date, config=config)
    rule_v2_regime = evaluate_rule_v2_regime(asof_date=asof_date, config=config)
    if args.json:
        print(json.dumps({"macro_v1": macro_regime, "rule_v2": rule_v2_regime}, indent=2, sort_keys=True))
        return

    print(f"# Regime Report")
    print("")
    print("## Macro V1")
    print(f"As of {macro_regime['asof_date']}, the model is in `{macro_regime['label']}` ({macro_regime['title']}).")
    print(f"Score: {macro_regime['score']:.3f}")
    probs = macro_regime["probabilities"]
    print(
        "Probabilities: "
        f"risk_on={probs.get('risk_on', 0.0):.3f}, "
        f"neutral={probs.get('neutral', 0.0):.3f}, "
        f"risk_off={probs.get('risk_off', 0.0):.3f}"
    )
    print("")
    print(macro_regime["summary"])
    print("")
    print("## Rule V2")
    print(
        f"As of {rule_v2_regime['asof_date']}, the model is in "
        f"`{rule_v2_regime['label']}` ({rule_v2_regime['title']})."
    )
    print(f"Market data used through {rule_v2_regime['market_asof_date']}.")
    print(f"Score: {rule_v2_regime['score']:.3f}")
    probs = rule_v2_regime["probabilities"]
    print(
        "Probabilities: "
        f"risk_on={probs.get('risk_on', 0.0):.3f}, "
        f"neutral={probs.get('neutral', 0.0):.3f}, "
        f"risk_off={probs.get('risk_off', 0.0):.3f}"
    )
    print("")
    print(rule_v2_regime["summary"])


if __name__ == "__main__":
    main()
