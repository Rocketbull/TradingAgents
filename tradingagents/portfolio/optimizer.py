from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Any

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
    sector_cap: Optional[float] = None

    def optimize(
        self,
        alpha_scores: pd.Series,
        covariance: pd.DataFrame,
        current_weights: Optional[Dict[str, float]] = None,
        benchmark_weights: Optional[Dict[str, float]] = None,
        sector_map: Optional[Dict[str, str]] = None,
        return_details: bool = False,
    ) -> Dict[str, float] | tuple[Dict[str, float], Dict[str, Any]]:
        symbols = list(alpha_scores.index)
        if not symbols:
            raise ValueError("alpha_scores cannot be empty")

        current = self._align_weights(symbols, current_weights)
        benchmark = self._align_weights(symbols, benchmark_weights)

        details: Dict[str, Any] = {
            "backend": "pypfopt",
            "used_fallback": False,
        }
        try:
            target, raw_target = self._optimize_with_pypfopt(
                alpha_scores, covariance, current, benchmark, sector_map
            )
        except Exception:
            details["backend"] = "fallback"
            details["used_fallback"] = True
            target, raw_target = self._fallback_optimize(alpha_scores, current, benchmark, sector_map)

        details["raw_target_weights"] = raw_target
        details["target_weights"] = target
        if return_details:
            return target, details
        return target

    def _optimize_with_pypfopt(
        self,
        alpha_scores: pd.Series,
        covariance: pd.DataFrame,
        current: pd.Series,
        benchmark: pd.Series,
        sector_map: Optional[Dict[str, str]],
    ) -> tuple[Dict[str, float], Dict[str, float]]:
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
        weights = self._apply_sector_cap(weights, sector_map)
        raw_target = weights.copy()
        adjusted = self._apply_turnover(weights, current)
        adjusted = self._apply_sector_cap(adjusted, sector_map)
        return adjusted.to_dict(), raw_target.to_dict()

    def _fallback_optimize(
        self,
        alpha_scores: pd.Series,
        current: pd.Series,
        benchmark: pd.Series,
        sector_map: Optional[Dict[str, str]],
    ) -> tuple[Dict[str, float], Dict[str, float]]:
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
        target = self._apply_sector_cap(target, sector_map)
        raw_target = target.copy()
        adjusted = self._apply_turnover(target, current)
        adjusted = self._apply_sector_cap(adjusted, sector_map)
        return adjusted.to_dict(), raw_target.to_dict()

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

    def _apply_sector_cap(
        self,
        weights: pd.Series,
        sector_map: Optional[Dict[str, str]],
    ) -> pd.Series:
        if not sector_map or self.sector_cap is None:
            return self._normalize_clip(weights)
        cap = float(self.sector_cap)
        if cap <= 0:
            return self._normalize_clip(weights)

        w = self._normalize_clip(weights)
        sector_key = {
            s: (sector_map.get(s) if isinstance(sector_map.get(s), str) and sector_map.get(s) else f"Unknown::{s}")
            for s in w.index
        }

        for _ in range(8):
            sector_totals = w.groupby(pd.Series(sector_key)).sum()
            over = sector_totals[sector_totals > cap + 1e-12]
            if over.empty:
                return self._normalize_clip(w)

            for sector_name, total in over.items():
                if total <= 0:
                    continue
                scale = cap / float(total)
                members = [s for s in w.index if sector_key[s] == sector_name]
                w.loc[members] = w.loc[members] * scale

            deficit = 1.0 - float(w.sum())
            if deficit <= 1e-12:
                continue

            headroom = pd.Series(self.max_weight, index=w.index) - w
            eligible = headroom[headroom > 1e-12].index
            if len(eligible) == 0:
                break
            alloc = headroom.loc[eligible] / float(headroom.loc[eligible].sum())
            w.loc[eligible] = w.loc[eligible] + alloc * deficit
            w = self._normalize_clip(w)

        return self._normalize_clip(w)

    def _normalize_clip(self, weights: pd.Series) -> pd.Series:
        w = weights.astype(float).clip(lower=0.0, upper=self.max_weight)
        total = float(w.sum())
        if total <= 0:
            return pd.Series(1.0 / len(w), index=w.index)
        return w / total

    @staticmethod
    def _align_weights(symbols: list[str], raw: Optional[Dict[str, float]]) -> pd.Series:
        if not raw:
            return pd.Series(1.0 / len(symbols), index=symbols)
        s = pd.Series(raw, dtype=float).reindex(symbols).fillna(0.0)
        total = float(s.sum())
        if total <= 0:
            return pd.Series(1.0 / len(symbols), index=symbols)
        return s / total
