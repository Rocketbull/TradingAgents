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

    @staticmethod
    def sector_exposure_matrix(
        symbols: list[str],
        sector_map: dict[str, str],
        include_unknown: bool = True,
    ) -> pd.DataFrame:
        """Build a one-hot sector exposure matrix indexed by symbol."""
        if not symbols:
            raise ValueError("symbols cannot be empty")
        sectors = []
        for symbol in symbols:
            sector = sector_map.get(symbol)
            if isinstance(sector, str) and sector.strip():
                sectors.append(sector.strip())
            else:
                sectors.append("Unknown" if include_unknown else "")

        exposure = pd.get_dummies(pd.Series(sectors, index=symbols), dtype=float)
        if not include_unknown and "" in exposure.columns:
            exposure = exposure.drop(columns=[""], errors="ignore")
        return exposure.reindex(index=symbols).fillna(0.0)

    @staticmethod
    def beta_vector(
        symbols: list[str],
        beta_map: dict[str, float],
        default_beta: float = 1.0,
    ) -> pd.Series:
        if not symbols:
            raise ValueError("symbols cannot be empty")
        values = []
        for symbol in symbols:
            beta = beta_map.get(symbol, default_beta)
            try:
                values.append(float(beta))
            except Exception:
                values.append(float(default_beta))
        return pd.Series(values, index=symbols, dtype=float)
