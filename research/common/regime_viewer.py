from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from activeportfolio.default_config import DEFAULT_CONFIG
from activeportfolio.regime import RuleBasedRegimeModelV2
from activeportfolio.dataflows.market_data_store import load_history_window


@dataclass
class RuleV2RegimeArtifacts:
    prices: pd.DataFrame
    normalized_prices: pd.DataFrame
    regimes: pd.DataFrame
    config: dict[str, Any]


def _rule_v2_symbols(config: dict[str, Any]) -> list[str]:
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
    dedup: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if symbol and symbol not in seen:
            dedup.append(symbol)
            seen.add(symbol)
    return dedup


def build_rule_v2_config(config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "regime_model_type": "rule_v2",
            "regime_benchmark_symbol": "SPY",
            "regime_v2_duration_symbol": "TLT",
            "regime_v2_defensive_symbol": "GLD",
            "regime_v2_growth_symbol": "XLK",
            "regime_v2_inflation_symbol": "XLE",
            "regime_v2_speculative_symbols": ["BTC-USD", "ETH-USD"],
            "regime_short_window": 21,
            "regime_long_window": 63,
            "regime_relative_window": 63,
            "regime_risk_on_threshold": 0.15,
            "regime_risk_off_threshold": -0.15,
            "regime_temperature": 0.20,
        }
    )
    if config_overrides:
        config.update(config_overrides)
    return config


def load_rule_v2_price_history(
    *,
    data_root: str | Path = "data/market",
    start_date: str = "2022-01-01",
    end_date: str | None = None,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    cfg = build_rule_v2_config(config)
    symbols = _rule_v2_symbols(cfg)
    end = end_date or pd.Timestamp.today().strftime("%Y-%m-%d")

    per_symbol: dict[str, pd.Series] = {}
    for symbol in symbols:
        df = load_history_window(symbol, start_date=start_date, end_date=end, root_dir=str(data_root))
        col = "Adj Close" if "Adj Close" in df.columns else "Close"
        s = (
            df[["Date", col]]
            .rename(columns={col: symbol})
            .assign(Date=lambda x: pd.to_datetime(x["Date"]))
            .set_index("Date")[symbol]
            .sort_index()
        )
        per_symbol[symbol] = pd.to_numeric(s, errors="coerce")

    prices = pd.concat(per_symbol.values(), axis=1).sort_index().ffill().dropna()
    prices.columns = list(per_symbol.keys())
    return prices


def normalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return prices.copy()
    base = prices.iloc[0].replace(0.0, pd.NA)
    return prices.divide(base).multiply(100.0)


def compute_rule_v2_regimes(prices: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = build_rule_v2_config(config)
    model = RuleBasedRegimeModelV2(
        benchmark_symbol=str(cfg.get("regime_benchmark_symbol", cfg.get("benchmark_symbol", "SPY"))).upper(),
        duration_symbol=str(cfg.get("regime_v2_duration_symbol", "TLT")).upper(),
        defensive_symbol=str(cfg.get("regime_v2_defensive_symbol", "GLD")).upper(),
        growth_symbol=str(cfg.get("regime_v2_growth_symbol", "XLK")).upper(),
        inflation_symbol=str(cfg.get("regime_v2_inflation_symbol", "XLE")).upper(),
        speculative_symbols=tuple(_rule_v2_symbols(cfg)[5:]),
        short_window=int(cfg.get("regime_short_window", 21)),
        long_window=int(cfg.get("regime_long_window", 63)),
        relative_window=int(cfg.get("regime_relative_window", 63)),
        risk_on_threshold=float(cfg.get("regime_risk_on_threshold", 0.15)),
        risk_off_threshold=float(cfg.get("regime_risk_off_threshold", -0.15)),
        temperature=float(cfg.get("regime_temperature", 0.20)),
    )
    warmup = max(
        int(cfg.get("regime_long_window", 63)),
        int(cfg.get("regime_relative_window", 63)),
    ) + 1
    rows: list[dict[str, Any]] = []
    for i, date in enumerate(prices.index):
        if i < warmup:
            continue
        decision = model.detect(prices.iloc[: i + 1])
        rows.append(
            {
                "date": pd.Timestamp(date),
                "label": decision.label,
                "score": float(decision.score),
                "prob_risk_on": float(decision.probabilities.get("risk_on", 0.0)),
                "prob_neutral": float(decision.probabilities.get("neutral", 0.0)),
                "prob_risk_off": float(decision.probabilities.get("risk_off", 0.0)),
            }
        )
    return pd.DataFrame(rows)


def build_rule_v2_regime_artifacts(
    *,
    data_root: str | Path = "data/market",
    start_date: str = "2022-01-01",
    end_date: str | None = None,
    config: dict[str, Any] | None = None,
) -> RuleV2RegimeArtifacts:
    cfg = build_rule_v2_config(config)
    prices = load_rule_v2_price_history(
        data_root=data_root,
        start_date=start_date,
        end_date=end_date,
        config=cfg,
    )
    normalized = normalize_prices(prices)
    regimes = compute_rule_v2_regimes(prices, config=cfg)
    return RuleV2RegimeArtifacts(
        prices=prices,
        normalized_prices=normalized,
        regimes=regimes,
        config=cfg,
    )
