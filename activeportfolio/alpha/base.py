from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class AlphaSignal(ABC):
    """Base class for pluggable cross-sectional alpha signals."""

    name: str

    @property
    @abstractmethod
    def lookback(self) -> int:
        """Return minimum price history rows required for this signal."""

    @abstractmethod
    def compute(
        self,
        closes: pd.DataFrame,
        volumes: pd.DataFrame | None = None,
    ) -> pd.Series:
        """Compute raw cross-sectional signal score indexed by symbol."""
