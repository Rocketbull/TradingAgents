from __future__ import annotations

from typing import Any, Mapping


def regime_stage_title(label: str) -> str:
    key = str(label or "unknown").strip().lower()
    mapping = {
        "risk_on": "Risk-On",
        "neutral": "Neutral",
        "risk_off": "Risk-Off",
        "static": "Static",
    }
    return mapping.get(key, key.replace("_", " ").title() or "Unknown")


def regime_stage_interpretation(label: str, score: float) -> str:
    key = str(label or "unknown").strip().lower()
    strength = abs(float(score))
    if key == "risk_on":
        if strength >= 0.35:
            return "broad risk-on expansion"
        if strength >= 0.20:
            return "moderate risk-on expansion"
        return "late-cycle or soft-landing risk-on"
    if key == "risk_off":
        if strength >= 0.35:
            return "broad risk-off contraction"
        if strength >= 0.20:
            return "moderate risk-off slowdown"
        return "early defensive slowdown"
    if key == "neutral":
        return "mixed or transition regime"
    return "static allocation backdrop"


def summarize_regime(regime: Mapping[str, Any]) -> str:
    label = str(regime.get("label", "unknown"))
    score = float(regime.get("score", 0.0) or 0.0)
    diagnostics = regime.get("diagnostics", {})
    if not isinstance(diagnostics, Mapping):
        diagnostics = {}

    positives: list[str] = []
    negatives: list[str] = []

    if float(diagnostics.get("unemployment_6m_change", 0.0) or 0.0) < 0:
        positives.append("labor conditions have improved over the past six months")
    elif float(diagnostics.get("unemployment_6m_change", 0.0) or 0.0) > 0:
        negatives.append("labor conditions have softened over the past six months")

    if float(diagnostics.get("growth_6m_return", 0.0) or 0.0) > 0:
        positives.append("industrial production is still trending higher")
    elif float(diagnostics.get("growth_6m_return", 0.0) or 0.0) < 0:
        negatives.append("industrial production is rolling over")

    if float(diagnostics.get("yield_curve_level", 0.0) or 0.0) > 0:
        positives.append("the yield curve is positively sloped")
    elif float(diagnostics.get("yield_curve_level", 0.0) or 0.0) < 0:
        negatives.append("the yield curve remains inverted")

    if float(diagnostics.get("policy_12m_change", 0.0) or 0.0) < 0:
        positives.append("Fed policy is easier than a year ago")
    elif float(diagnostics.get("policy_12m_change", 0.0) or 0.0) > 0:
        negatives.append("Fed policy is tighter than a year ago")

    if float(diagnostics.get("vix_level", 0.0) or 0.0) <= 20.0:
        positives.append("market volatility is contained")
    else:
        negatives.append("market volatility is elevated")

    if float(diagnostics.get("inflation_yoy", 0.0) or 0.0) > 0.03:
        negatives.append("inflation is still running above the model's comfort zone")
    else:
        positives.append("inflation is closer to the model's comfort zone")

    reasons = positives[:3] + negatives[:2]
    if not reasons:
        return regime_stage_interpretation(label, score)
    return f"{regime_stage_interpretation(label, score)} because " + "; ".join(reasons) + "."
