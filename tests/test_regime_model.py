from __future__ import annotations

import pandas as pd

from activeportfolio.regime import RuleBasedRegimeModel


def _frame(spy_slope: float, btc_slope: float, gld_slope: float) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=220, freq="D")
    t = pd.Series(range(len(idx)), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "SPY": 100.0 + spy_slope * t,
            "BTC-USD": 200.0 + btc_slope * t,
            "GLD": 150.0 + gld_slope * t,
        },
        index=idx,
    )


def test_rule_based_regime_detects_risk_on():
    model = RuleBasedRegimeModel()
    decision = model.detect(_frame(spy_slope=0.25, btc_slope=0.50, gld_slope=0.03))
    assert decision.label == "risk_on"
    assert decision.probabilities["risk_on"] >= decision.probabilities["risk_off"]


def test_rule_based_regime_detects_risk_off():
    model = RuleBasedRegimeModel()
    decision = model.detect(_frame(spy_slope=-0.08, btc_slope=-0.20, gld_slope=0.10))
    assert decision.label == "risk_off"
    assert decision.probabilities["risk_off"] >= decision.probabilities["risk_on"]
