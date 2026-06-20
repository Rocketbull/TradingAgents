from __future__ import annotations

import pandas as pd

from activeportfolio.dataflows.fred_macro import FREDMacroStore
from activeportfolio.regime import FREDMacroRegimeModel, RuleBasedRegimeModel, RuleBasedRegimeModelV2


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


def _macro_history_anchor() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=430, freq="D")
    base = pd.Series(range(len(idx)), index=idx, dtype=float)
    return pd.DataFrame({"SPY": 100.0 + base}, index=idx)


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


def test_rule_based_regime_v2_detects_risk_on():
    idx = pd.date_range("2024-01-01", periods=220, freq="D")
    t = pd.Series(range(len(idx)), index=idx, dtype=float)
    frame = pd.DataFrame(
        {
            "SPY": 100.0 + 0.28 * t,
            "TLT": 150.0 + 0.02 * t,
            "GLD": 140.0 + 0.03 * t,
            "XLK": 120.0 + 0.35 * t,
            "XLE": 110.0 + 0.05 * t,
            "BTC-USD": 200.0 + 0.55 * t,
            "ETH-USD": 180.0 + 0.60 * t,
        },
        index=idx,
    )
    model = RuleBasedRegimeModelV2()
    decision = model.detect(frame)
    assert decision.label == "risk_on"
    assert decision.probabilities["risk_on"] >= decision.probabilities["risk_off"]


def test_rule_based_regime_v2_detects_risk_off():
    idx = pd.date_range("2024-01-01", periods=220, freq="D")
    t = pd.Series(range(len(idx)), index=idx, dtype=float)
    frame = pd.DataFrame(
        {
            "SPY": 100.0 - 0.08 * t,
            "TLT": 150.0 + 0.18 * t,
            "GLD": 140.0 + 0.10 * t,
            "XLK": 120.0 - 0.15 * t,
            "XLE": 110.0 + 0.12 * t,
            "BTC-USD": 200.0 - 0.30 * t,
            "ETH-USD": 180.0 - 0.32 * t,
        },
        index=idx,
    )
    model = RuleBasedRegimeModelV2()
    decision = model.detect(frame)
    assert decision.label == "risk_off"
    assert decision.probabilities["risk_off"] >= decision.probabilities["risk_on"]


class _FakeMacroStore(FREDMacroStore):
    def __init__(self, series_map: dict[str, pd.Series]):
        super().__init__(root_dir="unused", auto_download=False)
        self.series_map = series_map

    def load_series_window(self, series_id: str, start_date: str, end_date: str) -> pd.Series:
        return self.series_map[series_id]


def _macro_series(values: list[tuple[str, float]]) -> pd.Series:
    idx = pd.to_datetime([d for d, _ in values])
    data = [v for _, v in values]
    return pd.Series(data, index=idx, dtype=float)


def test_fred_macro_regime_detects_risk_on():
    store = _FakeMacroStore(
        {
            "UNRATE": _macro_series([("2024-06-30", 4.6), ("2024-12-31", 4.0)]),
            "CPIAUCSL": _macro_series([("2023-12-31", 100.0), ("2024-12-31", 102.0)]),
            "INDPRO": _macro_series([("2024-06-30", 100.0), ("2024-12-31", 104.0)]),
            "T10Y2Y": _macro_series([("2024-12-30", 0.5)]),
            "FEDFUNDS": _macro_series([("2023-12-31", 5.5), ("2024-12-31", 4.5)]),
            "VIXCLS": _macro_series([("2024-12-30", 16.0)]),
        }
    )
    model = FREDMacroRegimeModel(macro_store=store)

    decision = model.detect(_macro_history_anchor())

    assert decision.label == "risk_on"
    assert decision.probabilities["risk_on"] >= decision.probabilities["risk_off"]


def test_fred_macro_regime_detects_risk_off():
    store = _FakeMacroStore(
        {
            "UNRATE": _macro_series([("2024-06-30", 3.8), ("2024-12-31", 4.8)]),
            "CPIAUCSL": _macro_series([("2023-12-31", 100.0), ("2024-12-31", 106.0)]),
            "INDPRO": _macro_series([("2024-06-30", 100.0), ("2024-12-31", 96.0)]),
            "T10Y2Y": _macro_series([("2024-12-30", -0.7)]),
            "FEDFUNDS": _macro_series([("2023-12-31", 3.0), ("2024-12-31", 5.0)]),
            "VIXCLS": _macro_series([("2024-12-30", 32.0)]),
        }
    )
    model = FREDMacroRegimeModel(macro_store=store)

    decision = model.detect(_macro_history_anchor())

    assert decision.label == "risk_off"
    assert decision.probabilities["risk_off"] >= decision.probabilities["risk_on"]
