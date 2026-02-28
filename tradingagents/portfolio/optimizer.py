from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class PortfolioOptimizer:
    """
    Active portfolio optimizer with optional PyPortfolioOpt backend.

    Falls back to deterministic heuristic optimizer if PyPortfolioOpt is unavailable.
    """

    risk_aversion: float = 3.0
    max_weight: float = 0.05
    turnover_limit: float = 0.20

    def optimize(
        self,
        alpha_scores: pd.Series,
        covariance: pd.DataFrame,
        current_weights: Optional[Dict[str, float]] = None,
        benchmark_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        symbols = list(alpha_scores.index)
        if not symbols:
            raise ValueError("alpha_scores cannot be empty")

        current = self._align_weights(symbols, current_weights)
        benchmark = self._align_weights(symbols, benchmark_weights)

        try:
            return self._optimize_with_pypfopt(alpha_scores, covariance, current, benchmark)
        except Exception:
            # Stable fallback in case dependency or optimization fails.
            return self._fallback_optimize(alpha_scores, current, benchmark)

    def _optimize_with_pypfopt(
        self,
        alpha_scores: pd.Series,
        covariance: pd.DataFrame,
        current: pd.Series,
        benchmark: pd.Series,
    ) -> Dict[str, float]:
        from pypfopt import EfficientFrontier

        mu = (benchmark + alpha_scores).to_dict()
        cov = covariance.loc[alpha_scores.index, alpha_scores.index]

        ef = EfficientFrontier(
            expected_returns=pd.Series(mu),
            cov_matrix=cov,
            weight_bounds=(0.0, self.max_weight),
        )
        ef.max_quadratic_utility(risk_aversion=self.risk_aversion)
        weights = pd.Series(ef.clean_weights()).reindex(alpha_scores.index).fillna(0.0)
        return self._apply_turnover(weights, current).to_dict()

    def _fallback_optimize(
        self,
        alpha_scores: pd.Series,
        current: pd.Series,
        benchmark: pd.Series,
    ) -> Dict[str, float]:
        active = alpha_scores.clip(lower=0.0)
        if active.sum() <= 0:
            active = pd.Series(1.0, index=alpha_scores.index)
        active = active / active.sum()

        target = 0.5 * benchmark + 0.5 * active
        target = target.clip(lower=0.0, upper=self.max_weight)
        if target.sum() <= 0:
            target = pd.Series(1.0 / len(target), index=target.index)
        else:
            target = target / target.sum()
        return self._apply_turnover(target, current).to_dict()

    def _apply_turnover(self, target: pd.Series, current: pd.Series) -> pd.Series:
        turnover = float((target - current).abs().sum())
        if turnover <= self.turnover_limit:
            return target
        if turnover <= 0:
            return current
        scale = self.turnover_limit / turnover
        adjusted = current + scale * (target - current)
        adjusted = adjusted.clip(lower=0.0, upper=self.max_weight)
        if adjusted.sum() <= 0:
            return target
        return adjusted / adjusted.sum()

    @staticmethod
    def _align_weights(symbols: list[str], raw: Optional[Dict[str, float]]) -> pd.Series:
        if not raw:
            return pd.Series(1.0 / len(symbols), index=symbols)
        s = pd.Series(raw, dtype=float).reindex(symbols).fillna(0.0)
        total = float(s.sum())
        if total <= 0:
            return pd.Series(1.0 / len(symbols), index=symbols)
        return s / total

