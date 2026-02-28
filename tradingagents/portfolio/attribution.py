from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class AttributionEngine:
    """Compute Grinold-style diagnostics from portfolio cycle outputs."""

    def diagnostics(
        self,
        alpha_scores: pd.Series,
        realized_returns: Optional[pd.Series],
        target_weights: Dict[str, float],
        pre_constraint_scores: Optional[pd.Series] = None,
    ) -> Dict[str, float]:
        ic = self._ic(alpha_scores, realized_returns)
        breadth = self._breadth_proxy(target_weights)
        tc = self._transfer_coefficient(alpha_scores, pre_constraint_scores, target_weights)
        realized_ir = self._information_ratio(realized_returns, target_weights)
        return {
            "information_coefficient": ic,
            "breadth_proxy": breadth,
            "transfer_coefficient_proxy": tc,
            "realized_information_ratio": realized_ir,
        }

    def cross_sectional_ic(
        self, alpha_scores: pd.Series, realized_returns: Optional[pd.Series]
    ) -> float:
        return self._ic(alpha_scores, realized_returns)

    @staticmethod
    def top_bottom_spread(
        alpha_scores: pd.Series,
        realized_returns: Optional[pd.Series],
        quantiles: int = 5,
    ) -> float:
        if realized_returns is None:
            return float("nan")
        aligned = pd.concat([alpha_scores, realized_returns], axis=1).dropna()
        if aligned.shape[0] < quantiles:
            return float("nan")
        aligned.columns = ["alpha", "ret"]
        bins = pd.qcut(aligned["alpha"], q=quantiles, labels=False, duplicates="drop")
        if bins.nunique() < 2:
            return float("nan")
        top_bucket = aligned.loc[bins == bins.max(), "ret"].mean()
        bottom_bucket = aligned.loc[bins == bins.min(), "ret"].mean()
        return float(top_bucket - bottom_bucket)

    def top_bottom_hit(
        self,
        alpha_scores: pd.Series,
        realized_returns: Optional[pd.Series],
        quantiles: int = 5,
    ) -> float:
        spread = self.top_bottom_spread(alpha_scores, realized_returns, quantiles=quantiles)
        if pd.isna(spread):
            return float("nan")
        return 1.0 if spread > 0 else 0.0

    @staticmethod
    def _ic(alpha_scores: pd.Series, realized_returns: Optional[pd.Series]) -> float:
        if realized_returns is None:
            return float("nan")
        aligned = pd.concat([alpha_scores, realized_returns], axis=1).dropna()
        if aligned.shape[0] < 3:
            return float("nan")
        # Spearman proxy without scipy dependency: correlate rank-transformed series.
        ranked_alpha = aligned.iloc[:, 0].rank()
        ranked_realized = aligned.iloc[:, 1].rank()
        return float(ranked_alpha.corr(ranked_realized))

    @staticmethod
    def _breadth_proxy(target_weights: Dict[str, float]) -> float:
        w = np.array([abs(v) for v in target_weights.values()], dtype=float)
        if w.size == 0:
            return 0.0
        denom = np.sum(w ** 2)
        if denom <= 0:
            return 0.0
        return float(1.0 / denom)

    @staticmethod
    def _transfer_coefficient(
        alpha_scores: pd.Series,
        pre_constraint_scores: Optional[pd.Series],
        target_weights: Dict[str, float],
    ) -> float:
        constrained = pd.Series(target_weights).reindex(alpha_scores.index).fillna(0.0)
        source = pre_constraint_scores if pre_constraint_scores is not None else alpha_scores
        aligned = pd.concat([source, constrained], axis=1).dropna()
        if aligned.shape[0] < 3:
            return float("nan")
        return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))

    @staticmethod
    def _information_ratio(
        realized_returns: Optional[pd.Series], target_weights: Dict[str, float]
    ) -> float:
        if realized_returns is None:
            return float("nan")
        w = pd.Series(target_weights)
        aligned = realized_returns.reindex(w.index).fillna(0.0)
        contrib = aligned * w
        mean = float(contrib.mean())
        std = float(contrib.std(ddof=0))
        if std <= 0:
            return float("nan")
        return mean / std
