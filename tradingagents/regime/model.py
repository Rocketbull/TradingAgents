from __future__ import annotations

from dataclasses import dataclass

import math
import pandas as pd


@dataclass(frozen=True)
class RegimeDecision:
    label: str
    score: float
    probabilities: dict[str, float]
    diagnostics: dict[str, float]


@dataclass(frozen=True)
class RuleBasedRegimeModel:
    benchmark_symbol: str = "SPY"
    risk_symbol: str = "BTC-USD"
    defensive_symbol: str = "GLD"
    short_window: int = 21
    long_window: int = 63
    relative_window: int = 63
    risk_on_threshold: float = 0.15
    risk_off_threshold: float = -0.15
    temperature: float = 0.20

    @staticmethod
    def _safe_return(series: pd.Series, window: int) -> float:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.shape[0] < window + 1:
            return 0.0
        prev = float(s.iloc[-(window + 1)])
        curr = float(s.iloc[-1])
        if prev <= 0.0:
            return 0.0
        return curr / prev - 1.0

    @staticmethod
    def _clip_scale(value: float, scale: float) -> float:
        if scale <= 0:
            return 0.0
        x = value / scale
        return max(-1.0, min(1.0, float(x)))

    def score(self, close_history: pd.DataFrame) -> tuple[float, dict[str, float]]:
        if close_history.empty:
            return 0.0, {}

        cols = {str(c).upper(): c for c in close_history.columns}
        benchmark_col = cols.get(self.benchmark_symbol.upper())
        risk_col = cols.get(self.risk_symbol.upper())
        defensive_col = cols.get(self.defensive_symbol.upper())

        spy_long = self._safe_return(close_history[benchmark_col], int(self.long_window)) if benchmark_col else 0.0
        spy_short = self._safe_return(close_history[benchmark_col], int(self.short_window)) if benchmark_col else 0.0
        risk_ret = self._safe_return(close_history[risk_col], int(self.relative_window)) if risk_col else 0.0
        defensive_ret = (
            self._safe_return(close_history[defensive_col], int(self.relative_window))
            if defensive_col
            else 0.0
        )
        rel_ret = risk_ret - defensive_ret

        # Weighted normalized score:
        # + benchmark trend (risk appetite in equities),
        # + BTC-vs-GLD relative trend (risk-on vs defensive cross-asset tilt).
        score = (
            0.45 * self._clip_scale(spy_long, 0.10)
            + 0.20 * self._clip_scale(spy_short, 0.05)
            + 0.35 * self._clip_scale(rel_ret, 0.20)
        )
        return float(score), {
            "spy_long_return": float(spy_long),
            "spy_short_return": float(spy_short),
            "risk_minus_defensive_return": float(rel_ret),
            "risk_return": float(risk_ret),
            "defensive_return": float(defensive_ret),
        }

    def classify(self, score: float) -> str:
        if score >= float(self.risk_on_threshold):
            return "risk_on"
        if score <= float(self.risk_off_threshold):
            return "risk_off"
        return "neutral"

    def probabilities(self, score: float) -> dict[str, float]:
        t = max(float(self.temperature), 1e-6)
        z_on = (float(score) - float(self.risk_on_threshold)) / t
        z_off = (float(self.risk_off_threshold) - float(score)) / t
        z_neutral = -abs(float(score)) / t
        m = max(z_on, z_off, z_neutral)
        exps = {
            "risk_on": math.exp(z_on - m),
            "risk_off": math.exp(z_off - m),
            "neutral": math.exp(z_neutral - m),
        }
        denom = sum(exps.values())
        if denom <= 0.0:
            return {"risk_on": 0.0, "risk_off": 0.0, "neutral": 1.0}
        return {k: float(v / denom) for k, v in exps.items()}

    def detect(self, close_history: pd.DataFrame) -> RegimeDecision:
        score, diagnostics = self.score(close_history)
        return RegimeDecision(
            label=self.classify(score),
            score=float(score),
            probabilities=self.probabilities(score),
            diagnostics=diagnostics,
        )
