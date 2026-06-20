from __future__ import annotations

import pandas as pd

from research.common.regime_viewer import (
    build_rule_v2_config,
    compute_rule_v2_regimes,
    normalize_prices,
)


def test_normalize_prices_starts_at_100() -> None:
    prices = pd.DataFrame(
        {
            "SPY": [100.0, 110.0],
            "TLT": [200.0, 210.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    normalized = normalize_prices(prices)
    assert float(normalized.iloc[0]["SPY"]) == 100.0
    assert float(normalized.iloc[0]["TLT"]) == 100.0
    assert abs(float(normalized.iloc[1]["SPY"]) - 110.0) < 1e-12


def test_compute_rule_v2_regimes_returns_labels_and_scores() -> None:
    idx = pd.date_range("2024-01-01", periods=120, freq="D")
    t = pd.Series(range(len(idx)), index=idx, dtype=float)
    prices = pd.DataFrame(
        {
            "SPY": 100.0 + 0.25 * t,
            "TLT": 150.0 + 0.01 * t,
            "GLD": 140.0 + 0.02 * t,
            "XLK": 120.0 + 0.30 * t,
            "XLE": 110.0 + 0.05 * t,
            "BTC-USD": 200.0 + 0.50 * t,
            "ETH-USD": 180.0 + 0.55 * t,
        },
        index=idx,
    )
    regimes = compute_rule_v2_regimes(prices, config=build_rule_v2_config())
    assert not regimes.empty
    assert set(["date", "label", "score", "prob_risk_on", "prob_neutral", "prob_risk_off"]).issubset(regimes.columns)
    assert regimes.iloc[-1]["label"] in {"risk_on", "neutral", "risk_off"}
