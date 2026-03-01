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

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        return closes.pct_change(self.window).iloc[-1]


@dataclass(frozen=True)
class ReversalAlpha(AlphaSignal):
    name: str
    window: int

    @property
    def lookback(self) -> int:
        return int(self.window) + 1

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        return -closes.pct_change(self.window).iloc[-1]


@dataclass(frozen=True)
class LowVolAlpha(AlphaSignal):
    name: str
    window: int

    @property
    def lookback(self) -> int:
        return int(self.window) + 2

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
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

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
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

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        long_mom = closes.pct_change(self.long_window).iloc[-1]
        short_mom = closes.pct_change(self.short_window).iloc[-1]
        return long_mom - short_mom


@dataclass(frozen=True)
class VolAdjMomentumAlpha(AlphaSignal):
    name: str
    momentum_window: int = 63
    vol_window: int = 21

    @property
    def lookback(self) -> int:
        return int(max(self.momentum_window + 1, self.vol_window + 2))

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        if closes.shape[0] < self.lookback:
            return pd.Series(0.0, index=closes.columns)
        returns = closes.pct_change().dropna(how="all")
        if returns.empty:
            return pd.Series(0.0, index=closes.columns)
        mom = closes.pct_change(int(self.momentum_window)).iloc[-1]
        vol = returns.tail(int(self.vol_window)).std(ddof=0)
        score = mom / vol.replace(0.0, np.nan)
        return score.replace([np.inf, -np.inf], np.nan).fillna(0.0)


@dataclass(frozen=True)
class RangePositionAlpha(AlphaSignal):
    name: str
    window: int = 63

    @property
    def lookback(self) -> int:
        return int(self.window)

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        if closes.shape[0] < self.lookback:
            return pd.Series(0.0, index=closes.columns)
        trailing = closes.tail(int(self.window))
        low = trailing.min(axis=0)
        high = trailing.max(axis=0)
        latest = closes.iloc[-1]
        denom = (high - low).replace(0.0, np.nan)
        pos01 = (latest - low) / denom
        score = pos01 - 0.5
        return score.replace([np.inf, -np.inf], np.nan).fillna(0.0)


@dataclass(frozen=True)
class VolumeShockAlpha(AlphaSignal):
    name: str
    price_window: int = 5
    vol_short_window: int = 5
    vol_long_window: int = 20

    @property
    def lookback(self) -> int:
        return int(max(self.price_window + 1, self.vol_long_window))

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        if closes.empty or volumes is None or volumes.empty:
            return pd.Series(0.0, index=closes.columns)

        common_cols = [c for c in closes.columns if c in volumes.columns]
        if not common_cols:
            return pd.Series(0.0, index=closes.columns)

        c = closes[common_cols]
        v = volumes[common_cols]
        if c.shape[0] < self.lookback or v.shape[0] < int(self.vol_long_window):
            return pd.Series(0.0, index=closes.columns)

        price_ret = c.pct_change(int(self.price_window)).iloc[-1]
        vol_short = v.rolling(int(self.vol_short_window), min_periods=int(self.vol_short_window)).mean()
        vol_long = v.rolling(int(self.vol_long_window), min_periods=int(self.vol_long_window)).mean()
        vol_ratio = (vol_short / vol_long.replace(0.0, np.nan)).iloc[-1]
        vol_shock = (vol_ratio - 1.0).clip(lower=0.0)
        score = price_ret * vol_shock
        return score.reindex(closes.columns).replace([np.inf, -np.inf], np.nan).fillna(0.0)


@dataclass(frozen=True)
class BreakoutAlpha(AlphaSignal):
    name: str
    window: int

    @property
    def lookback(self) -> int:
        return int(self.window)

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        if closes.shape[0] < self.window:
            return pd.Series(0.0, index=closes.columns)
        trailing_high = closes.tail(self.window).max(axis=0)
        latest = closes.iloc[-1]
        return latest / trailing_high - 1.0


@dataclass(frozen=True)
class FlatVolumeBreakoutAlpha(AlphaSignal):
    name: str
    flat_window: int = 60
    flat_max_abs_return: float = 0.15
    price_window: int = 20
    price_ratio_min: float = 1.10
    vol_short_window: int = 5
    vol_long_window: int = 20
    vol_ratio_min: float = 1.50

    @property
    def lookback(self) -> int:
        return int(self.flat_window + self.price_window + self.vol_long_window + 1)

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        if closes.empty or volumes is None or volumes.empty:
            return pd.Series(0.0, index=closes.columns)

        common_cols = [c for c in closes.columns if c in volumes.columns]
        if not common_cols:
            return pd.Series(0.0, index=closes.columns)

        c = closes[common_cols]
        v = volumes[common_cols]
        if (
            c.shape[0] < self.lookback
            or v.shape[0] < self.vol_long_window
            or c.shape[0] < self.price_window + self.flat_window + 1
        ):
            return pd.Series(0.0, index=closes.columns)

        prior_end = c.shift(self.price_window)
        prior_start = c.shift(self.price_window + self.flat_window)
        flat_ret = (prior_end / prior_start) - 1.0

        price_ratio = c / c.shift(self.price_window)
        vol_short = v.rolling(int(self.vol_short_window), min_periods=int(self.vol_short_window)).mean()
        vol_long = v.rolling(int(self.vol_long_window), min_periods=int(self.vol_long_window)).mean()
        vol_ratio = vol_short / vol_long.replace(0.0, np.nan)
        flat_abs = flat_ret.abs().iloc[-1].replace([np.inf, -np.inf], np.nan)
        price_last = price_ratio.iloc[-1].replace([np.inf, -np.inf], np.nan)
        vol_last = vol_ratio.iloc[-1].replace([np.inf, -np.inf], np.nan)

        flat_cap = float(self.flat_max_abs_return)
        if flat_cap > 0:
            # 1.0 means very flat, 0.0 means outside allowed flat regime.
            flat_strength = ((flat_cap - flat_abs) / flat_cap).clip(lower=0.0, upper=1.0)
        else:
            flat_strength = (flat_abs <= 0.0).astype(float)

        # Positive excess above thresholds; both need to be positive for non-zero score.
        price_excess = (price_last / float(self.price_ratio_min) - 1.0).clip(lower=0.0)
        vol_excess = (vol_last / float(self.vol_ratio_min) - 1.0).clip(lower=0.0)
        score = flat_strength * price_excess * vol_excess
        return score.reindex(closes.columns).fillna(0.0)


@dataclass(frozen=True)
class BtcGldCorrelationAlpha(AlphaSignal):
    name: str
    lookback_window: int = 120
    risk_symbol: str = "BTC-USD"
    defensive_symbol: str = "GLD"
    defensive_weight: float = 1.0
    risk_weight: float = 1.0
    flip_sign: bool = True

    @property
    def lookback(self) -> int:
        return int(self.lookback_window) + 2

    def compute(self, closes: pd.DataFrame, volumes: pd.DataFrame | None = None) -> pd.Series:
        risk = str(self.risk_symbol).upper()
        defensive = str(self.defensive_symbol).upper()
        cols = [str(c).upper() for c in closes.columns]
        mapped = dict(zip(cols, closes.columns))
        if risk not in mapped or defensive not in mapped:
            return pd.Series(0.0, index=closes.columns)

        c = closes.copy()
        c.columns = cols
        if c.shape[0] < self.lookback:
            return pd.Series(0.0, index=closes.columns)

        ret = c.pct_change()
        risk_ret = ret[risk]
        defensive_ret = ret[defensive]
        corr_risk = ret.rolling(int(self.lookback_window), min_periods=int(self.lookback_window)).corr(risk_ret).iloc[-1]
        corr_def = ret.rolling(int(self.lookback_window), min_periods=int(self.lookback_window)).corr(defensive_ret).iloc[-1]
        score = float(self.defensive_weight) * corr_def - float(self.risk_weight) * corr_risk
        if bool(self.flip_sign):
            score = -score
        score = score.drop(labels=[risk, defensive], errors="ignore")
        score.index = [mapped.get(i, i) for i in score.index]
        return score.reindex(closes.columns).fillna(0.0)


def cross_sectional_zscore(values: pd.Series) -> pd.Series:
    s = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    std = float(s.std(ddof=0))
    if std <= 0:
        return pd.Series(0.0, index=s.index)
    return (s - float(s.mean())) / std
