from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RiskModel:
    """Estimate covariance matrix for optimizer inputs."""

    lookback_days: int = 252
    shrinkage: float = 0.1

    def covariance(self, close_prices: pd.DataFrame) -> pd.DataFrame:
        if close_prices.empty:
            raise ValueError("close_prices is empty")

        returns = close_prices.sort_index().ffill().pct_change().dropna()
        returns = returns.tail(self.lookback_days)
        if returns.empty:
            raise ValueError("Not enough history to compute covariance")

        sample_cov = returns.cov()
        diag_cov = pd.DataFrame(
            np.diag(np.diag(sample_cov.values)),
            index=sample_cov.index,
            columns=sample_cov.columns,
        )
        shrunk = (1.0 - self.shrinkage) * sample_cov + self.shrinkage * diag_cov
        return shrunk

