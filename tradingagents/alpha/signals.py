from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base import AlphaSignal


@dataclass(frozen=True)
class MomentumAlpha(AlphaSignal):
    name: str
    window: int

    @property
    def lookback(self) -> int:
        return int(self.window) + 1

    def compute(self, closes: pd.DataFrame) -> pd.Series:
        return closes.pct_change(self.window).iloc[-1]


@dataclass(frozen=True)
class ReversalAlpha(AlphaSignal):
    name: str
    window: int

    @property
    def lookback(self) -> int:
        return int(self.window) + 1

    def compute(self, closes: pd.DataFrame) -> pd.Series:
        return -closes.pct_change(self.window).iloc[-1]


@dataclass(frozen=True)
class LowVolAlpha(AlphaSignal):
    name: str
    window: int

    @property
    def lookback(self) -> int:
        return int(self.window) + 2

    def compute(self, closes: pd.DataFrame) -> pd.Series:
        returns = closes.pct_change().dropna(how="all")
        if returns.empty:
            return pd.Series(0.0, index=closes.columns)
        return -returns.tail(self.window).std(ddof=0)


@dataclass(frozen=True)
class DownsideVolAlpha(AlphaSignal):
    name: str
    window: int

    @property
    def lookback(self) -> int:
        return int(self.window) + 2

    def compute(self, closes: pd.DataFrame) -> pd.Series:
        returns = closes.pct_change().dropna(how="all")
        if returns.empty:
            return pd.Series(0.0, index=closes.columns)
        downside = returns.tail(self.window).where(returns < 0.0, 0.0)
        return -np.sqrt((downside.pow(2)).mean())


@dataclass(frozen=True)
class TrendAlpha(AlphaSignal):
    name: str
    long_window: int
    short_window: int

    @property
    def lookback(self) -> int:
        return int(max(self.long_window, self.short_window)) + 1

    def compute(self, closes: pd.DataFrame) -> pd.Series:
        long_mom = closes.pct_change(self.long_window).iloc[-1]
        short_mom = closes.pct_change(self.short_window).iloc[-1]
        return long_mom - short_mom


@dataclass(frozen=True)
class BreakoutAlpha(AlphaSignal):
    name: str
    window: int

    @property
    def lookback(self) -> int:
        return int(self.window)

    def compute(self, closes: pd.DataFrame) -> pd.Series:
        if closes.shape[0] < self.window:
            return pd.Series(0.0, index=closes.columns)
        trailing_high = closes.tail(self.window).max(axis=0)
        latest = closes.iloc[-1]
        return latest / trailing_high - 1.0


def cross_sectional_zscore(values: pd.Series) -> pd.Series:
    s = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    std = float(s.std(ddof=0))
    if std <= 0:
        return pd.Series(0.0, index=s.index)
    return (s - float(s.mean())) / std
