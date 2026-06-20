from __future__ import annotations

from dataclasses import dataclass

import math
import pandas as pd

from activeportfolio.dataflows.fred_macro import FREDMacroStore


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


@dataclass(frozen=True)
class RuleBasedRegimeModelV2:
    benchmark_symbol: str = "SPY"
    duration_symbol: str = "TLT"
    defensive_symbol: str = "GLD"
    growth_symbol: str = "XLK"
    inflation_symbol: str = "XLE"
    speculative_symbols: tuple[str, ...] = ("BTC-USD", "ETH-USD")
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

        def _ret(symbol: str, window: int) -> float:
            col = cols.get(symbol.upper())
            if col is None:
                return 0.0
            return self._safe_return(close_history[col], int(window))

        spy_long = _ret(self.benchmark_symbol, self.long_window)
        spy_short = _ret(self.benchmark_symbol, self.short_window)
        duration_ret = _ret(self.duration_symbol, self.relative_window)
        defensive_ret = _ret(self.defensive_symbol, self.relative_window)
        growth_ret = _ret(self.growth_symbol, self.relative_window)
        inflation_ret = _ret(self.inflation_symbol, self.relative_window)

        spec_vals = [_ret(symbol, self.relative_window) for symbol in self.speculative_symbols]
        spec_vals = [v for v in spec_vals if pd.notna(v)]
        speculative_avg = float(sum(spec_vals) / len(spec_vals)) if spec_vals else 0.0

        equity_trend = (
            0.65 * self._clip_scale(spy_long, 0.10)
            + 0.35 * self._clip_scale(spy_short, 0.05)
        )
        defensive_relative = (
            0.55 * self._clip_scale(spy_long - duration_ret, 0.12)
            + 0.45 * self._clip_scale(spy_long - defensive_ret, 0.12)
        )
        sector_leadership = self._clip_scale(growth_ret - inflation_ret, 0.15)
        speculative_risk = self._clip_scale(speculative_avg, 0.25)

        score = (
            0.40 * equity_trend
            + 0.25 * defensive_relative
            + 0.20 * sector_leadership
            + 0.15 * speculative_risk
        )
        return float(score), {
            "spy_long_return": float(spy_long),
            "spy_short_return": float(spy_short),
            "duration_return": float(duration_ret),
            "defensive_return": float(defensive_ret),
            "growth_return": float(growth_ret),
            "inflation_return": float(inflation_ret),
            "speculative_avg_return": float(speculative_avg),
            "equity_trend_component": float(equity_trend),
            "defensive_relative_component": float(defensive_relative),
            "sector_leadership_component": float(sector_leadership),
            "speculative_risk_component": float(speculative_risk),
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


@dataclass(frozen=True)
class FREDMacroRegimeModel:
    macro_store: FREDMacroStore
    macro_lookback_days: int = 800
    unemployment_series_id: str = "UNRATE"
    inflation_series_id: str = "CPIAUCSL"
    growth_series_id: str = "INDPRO"
    curve_series_id: str = "T10Y2Y"
    policy_series_id: str = "FEDFUNDS"
    stress_series_id: str = "VIXCLS"
    unemployment_lag_days: int = 35
    inflation_lag_days: int = 35
    growth_lag_days: int = 35
    curve_lag_days: int = 1
    policy_lag_days: int = 35
    stress_lag_days: int = 1
    risk_on_threshold: float = 0.15
    risk_off_threshold: float = -0.15
    temperature: float = 0.20
    growth_weight: float = 0.25
    labor_weight: float = 0.20
    inflation_weight: float = 0.15
    curve_weight: float = 0.15
    policy_weight: float = 0.10
    stress_weight: float = 0.15

    @staticmethod
    def _clip_scale(value: float, scale: float) -> float:
        if scale <= 0:
            return 0.0
        x = value / scale
        return max(-1.0, min(1.0, float(x)))

    @staticmethod
    def _asof_value(series: pd.Series, asof: pd.Timestamp) -> float | None:
        s = pd.to_numeric(series, errors="coerce").dropna().sort_index()
        if s.empty:
            return None
        subset = s.loc[s.index <= asof]
        if subset.empty:
            return None
        return float(subset.iloc[-1])

    def _series_value(
        self,
        series: pd.Series,
        asof_date: pd.Timestamp,
        lag_days: int,
        offset_days: int = 0,
    ) -> float | None:
        effective = asof_date - pd.Timedelta(days=int(lag_days + offset_days))
        return self._asof_value(series, effective)

    def _load_macro_series(self, asof_date: pd.Timestamp) -> dict[str, pd.Series]:
        start_date = (asof_date - pd.Timedelta(days=int(self.macro_lookback_days))).strftime("%Y-%m-%d")
        end_date = asof_date.strftime("%Y-%m-%d")
        series_specs = {
            "unemployment": self.unemployment_series_id,
            "inflation": self.inflation_series_id,
            "growth": self.growth_series_id,
            "curve": self.curve_series_id,
            "policy": self.policy_series_id,
            "stress": self.stress_series_id,
        }
        out: dict[str, pd.Series] = {}
        for name, series_id in series_specs.items():
            out[name] = self.macro_store.load_series_window(
                series_id=series_id,
                start_date=start_date,
                end_date=end_date,
            )
        return out

    def score(self, close_history: pd.DataFrame) -> tuple[float, dict[str, float]]:
        if close_history.empty:
            return 0.0, {}

        asof_date = pd.Timestamp(close_history.index.max()).normalize()
        macro = self._load_macro_series(asof_date)

        unrate_now = self._series_value(macro["unemployment"], asof_date, self.unemployment_lag_days, 0)
        unrate_6m = self._series_value(macro["unemployment"], asof_date, self.unemployment_lag_days, 183)
        cpi_now = self._series_value(macro["inflation"], asof_date, self.inflation_lag_days, 0)
        cpi_12m = self._series_value(macro["inflation"], asof_date, self.inflation_lag_days, 365)
        growth_now = self._series_value(macro["growth"], asof_date, self.growth_lag_days, 0)
        growth_6m = self._series_value(macro["growth"], asof_date, self.growth_lag_days, 183)
        curve_now = self._series_value(macro["curve"], asof_date, self.curve_lag_days, 0)
        policy_now = self._series_value(macro["policy"], asof_date, self.policy_lag_days, 0)
        policy_12m = self._series_value(macro["policy"], asof_date, self.policy_lag_days, 365)
        stress_now = self._series_value(macro["stress"], asof_date, self.stress_lag_days, 0)

        unrate_delta_6m = (
            float(unrate_now - unrate_6m) if unrate_now is not None and unrate_6m is not None else 0.0
        )
        cpi_yoy = (
            float(cpi_now / cpi_12m - 1.0) if cpi_now is not None and cpi_12m not in (None, 0.0) else 0.0
        )
        growth_6m_return = (
            float(growth_now / growth_6m - 1.0) if growth_now is not None and growth_6m not in (None, 0.0) else 0.0
        )
        policy_12m_change = (
            float(policy_now - policy_12m) if policy_now is not None and policy_12m is not None else 0.0
        )

        component_growth = self._clip_scale(growth_6m_return, 0.05)
        component_labor = self._clip_scale(-unrate_delta_6m, 0.75)
        component_inflation = self._clip_scale(0.03 - cpi_yoy, 0.03)
        component_curve = self._clip_scale(float(curve_now or 0.0), 1.0)
        component_policy = self._clip_scale(-policy_12m_change, 1.5)
        component_stress = self._clip_scale(20.0 - float(stress_now or 20.0), 10.0)

        score = (
            self.growth_weight * component_growth
            + self.labor_weight * component_labor
            + self.inflation_weight * component_inflation
            + self.curve_weight * component_curve
            + self.policy_weight * component_policy
            + self.stress_weight * component_stress
        )
        diagnostics = {
            "growth_6m_return": float(growth_6m_return),
            "unemployment_6m_change": float(unrate_delta_6m),
            "inflation_yoy": float(cpi_yoy),
            "yield_curve_level": float(curve_now or 0.0),
            "policy_12m_change": float(policy_12m_change),
            "vix_level": float(stress_now or 0.0),
            "component_growth": float(component_growth),
            "component_labor": float(component_labor),
            "component_inflation": float(component_inflation),
            "component_curve": float(component_curve),
            "component_policy": float(component_policy),
            "component_stress": float(component_stress),
        }
        return float(score), diagnostics

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
