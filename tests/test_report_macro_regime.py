from __future__ import annotations

from dataclasses import dataclass

from tools.report_macro_regime import (
    build_regime_config,
    evaluate_macro_regime,
    evaluate_rule_v2_regime,
)


@dataclass
class _FakeDecision:
    label: str
    score: float
    probabilities: dict[str, float]
    diagnostics: dict[str, float]


class _FakeModel:
    def detect(self, close_history):
        return _FakeDecision(
            label="risk_on",
            score=0.23,
            probabilities={"risk_on": 0.7, "neutral": 0.2, "risk_off": 0.1},
            diagnostics={
                "growth_6m_return": 0.02,
                "unemployment_6m_change": -0.1,
                "inflation_yoy": 0.04,
                "yield_curve_level": 0.3,
                "policy_12m_change": -0.5,
                "vix_level": 18.0,
            },
        )


def test_build_regime_config_uses_defaults_without_json() -> None:
    config = build_regime_config(None)
    assert config["regime_macro_unemployment_series_id"] == "UNRATE"
    assert config["regime_macro_stress_series_id"] == "VIXCLS"


def test_evaluate_macro_regime_adds_title_and_summary(monkeypatch) -> None:
    monkeypatch.setattr("tools.report_macro_regime.build_macro_model", lambda config: _FakeModel())
    regime = evaluate_macro_regime(asof_date="2026-06-20", config={})

    assert regime["label"] == "risk_on"
    assert regime["title"] == "Risk-On"
    assert regime["score"] == 0.23
    assert "soft-landing risk-on" in regime["summary"] or "moderate risk-on expansion" in regime["summary"]


def test_evaluate_rule_v2_regime_adds_market_asof_and_summary(monkeypatch) -> None:
    monkeypatch.setattr("tools.report_macro_regime.build_rule_v2_model", lambda config: _FakeModel())
    monkeypatch.setattr(
        "tools.report_macro_regime.load_live_market_history",
        lambda symbols, asof_date, lookback_days=180: __import__("pandas").DataFrame(
            {"SPY": [1.0, 1.1], "TLT": [1.0, 0.9]},
            index=__import__("pandas").to_datetime(["2026-06-18", "2026-06-20"]),
        ),
    )
    regime = evaluate_rule_v2_regime(asof_date="2026-06-20", config={})

    assert regime["label"] == "risk_on"
    assert regime["title"] == "Risk-On"
    assert regime["market_asof_date"] == "2026-06-20"
    assert "risk-on" in regime["summary"]
