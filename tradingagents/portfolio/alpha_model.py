from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class AlphaModel:
    """Simple cross-sectional alpha model from price history."""

    short_lookback: int = 21
    long_lookback: int = 126
    vol_lookback: int = 63

    def score(self, close_prices: pd.DataFrame) -> pd.Series:
        """
        Compute expected active returns proxy per symbol.

        Args:
            close_prices: DataFrame indexed by date with symbols as columns.
        Returns:
            Series of normalized alpha scores keyed by symbol.
        """
        if close_prices.empty:
            raise ValueError("close_prices is empty")
        if close_prices.shape[1] < 2:
            raise ValueError("Need at least 2 symbols for cross-sectional alpha")

        closes = close_prices.sort_index().ffill()
        short_mom = closes.pct_change(self.short_lookback).iloc[-1]
        long_mom = closes.pct_change(self.long_lookback).iloc[-1]
        daily_ret = closes.pct_change().dropna()
        vol = daily_ret.tail(self.vol_lookback).std(ddof=0)

        # Blend momentum horizons; penalize high volatility.
        raw = 0.6 * short_mom + 0.4 * long_mom - 0.25 * vol
        raw = raw.replace([np.inf, -np.inf], np.nan).dropna()
        if raw.empty:
            raise ValueError("Alpha model produced no valid scores")

        centered = raw - raw.mean()
        std = centered.std(ddof=0)
        if std <= 0:
            return pd.Series(0.0, index=centered.index)
        return centered / std

