from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

import numpy as np
import pandas as pd

from .base import AlphaSignal
from .signals import (
    BtcGldCorrelationAlpha,
    BreakoutAlpha,
    DownsideVolAlpha,
    FlatVolumeBreakoutAlpha,
    LowVolAlpha,
    MomentumAlpha,
    ReversalAlpha,
    TrendAlpha,
    cross_sectional_zscore,
)


class AlphaModel:
    """
    Multi-factor alpha combiner with pluggable signals and IC-based weighting.

    Factors are inspired by open-source quant stacks (e.g. qlib-style momentum/
    reversal/volatility families and Alpha101-style price transforms), adapted to
    close-only data for this project.
    """

    SIGNAL_BUILDERS: Dict[str, Callable[[Mapping[str, Any]], AlphaSignal]] = {}

    def __init__(self, signals: Sequence[AlphaSignal] | None = None):
        configured = list(signals) if signals is not None else self.default_signals()
        self._signals: Dict[str, AlphaSignal] = {s.name: s for s in configured}
        if not self._signals:
            raise ValueError("AlphaModel requires at least one signal")

        # Backward-compatible attributes used by existing engine warmup logic.
        self.long_lookback = max(
            [s.lookback for s in self._signals.values() if "mom" in s.name or "trend" in s.name] or [22]
        )
        self.vol_lookback = max(
            [s.lookback for s in self._signals.values() if "vol" in s.name] or [62]
        )

    @staticmethod
    def default_signals() -> List[AlphaSignal]:
        return [
            MomentumAlpha(name="mom_1m", window=21),
            MomentumAlpha(name="mom_3m", window=63),
            MomentumAlpha(name="mom_6m", window=126),
            MomentumAlpha(name="mom_12m", window=252),
            ReversalAlpha(name="rev_1w", window=5),
            ReversalAlpha(name="rev_1m", window=21),
            LowVolAlpha(name="low_vol", window=60),
            DownsideVolAlpha(name="downside_vol", window=60),
            TrendAlpha(name="trend_12m_1m", long_window=252, short_window=21),
            BreakoutAlpha(name="breakout_52w", window=252),
        ]

    @classmethod
    def _init_builders(cls) -> None:
        if cls.SIGNAL_BUILDERS:
            return
        cls.SIGNAL_BUILDERS = {
            "momentum": lambda d: MomentumAlpha(
                name=str(d.get("name", "momentum")),
                window=int(d.get("window", 21)),
            ),
            "reversal": lambda d: ReversalAlpha(
                name=str(d.get("name", "reversal")),
                window=int(d.get("window", 5)),
            ),
            "low_vol": lambda d: LowVolAlpha(
                name=str(d.get("name", "low_vol")),
                window=int(d.get("window", 60)),
            ),
            "downside_vol": lambda d: DownsideVolAlpha(
                name=str(d.get("name", "downside_vol")),
                window=int(d.get("window", 60)),
            ),
            "trend": lambda d: TrendAlpha(
                name=str(d.get("name", "trend")),
                long_window=int(d.get("long_window", 252)),
                short_window=int(d.get("short_window", 21)),
            ),
            "breakout": lambda d: BreakoutAlpha(
                name=str(d.get("name", "breakout")),
                window=int(d.get("window", 252)),
            ),
            "flat_vol_breakout": lambda d: FlatVolumeBreakoutAlpha(
                name=str(d.get("name", "flat_vol_breakout")),
                flat_window=int(d.get("flat_window", 60)),
                flat_max_abs_return=float(d.get("flat_max_abs_return", 0.15)),
                price_window=int(d.get("price_window", 20)),
                price_ratio_min=float(d.get("price_ratio_min", 1.10)),
                vol_short_window=int(d.get("vol_short_window", 5)),
                vol_long_window=int(d.get("vol_long_window", 20)),
                vol_ratio_min=float(d.get("vol_ratio_min", 1.50)),
            ),
            "btc_gld_corr": lambda d: BtcGldCorrelationAlpha(
                name=str(d.get("name", "btc_gld_corr")),
                lookback_window=int(d.get("lookback_window", 120)),
                risk_symbol=str(d.get("risk_symbol", "BTC-USD")).upper(),
                defensive_symbol=str(d.get("defensive_symbol", "GLD")).upper(),
                defensive_weight=float(d.get("defensive_weight", 1.0)),
                risk_weight=float(d.get("risk_weight", 1.0)),
                flip_sign=bool(d.get("flip_sign", True)),
            ),
        }

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> AlphaModel:
        cfg = config or {}
        registry = cfg.get("alpha_signal_registry", [])
        if isinstance(registry, list) and len(registry) > 0:
            signals = cls.signals_from_registry(registry)
            return cls(signals=signals)
        return cls()

    @classmethod
    def signals_from_registry(cls, registry: Sequence[Mapping[str, Any]]) -> List[AlphaSignal]:
        cls._init_builders()
        built: List[AlphaSignal] = []
        seen: set[str] = set()
        for raw_spec in registry:
            spec = dict(raw_spec)
            enabled = bool(spec.get("enabled", True))
            if not enabled:
                continue
            kind = str(spec.get("type", "")).strip().lower()
            if not kind:
                raise ValueError(f"Missing alpha signal type in spec: {spec}")
            if kind not in cls.SIGNAL_BUILDERS:
                allowed = sorted(cls.SIGNAL_BUILDERS.keys())
                raise ValueError(f"Unknown alpha signal type '{kind}'. Allowed: {allowed}")
            signal = cls.SIGNAL_BUILDERS[kind](spec)
            if signal.name in seen:
                raise ValueError(f"Duplicate alpha signal name '{signal.name}' in alpha_signal_registry")
            seen.add(signal.name)
            built.append(signal)

        if not built:
            raise ValueError("alpha_signal_registry produced no enabled alpha signals")
        return built

    def available_signals(self) -> list[str]:
        return list(self._signals.keys())

    def component_scores(
        self,
        closes: pd.DataFrame,
        volumes: pd.DataFrame | None = None,
        signals: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        if closes.empty:
            raise ValueError("closes is empty")

        selected = list(signals) if signals is not None else self.available_signals()
        missing = [name for name in selected if name not in self._signals]
        if missing:
            raise ValueError(f"Unknown alpha signals: {missing}")

        components: dict[str, pd.Series] = {}
        for name in selected:
            raw = self._signals[name].compute(closes, volumes=volumes).reindex(closes.columns)
            components[name] = cross_sectional_zscore(raw)
        return pd.DataFrame(components).fillna(0.0)

    def score(
        self,
        closes: pd.DataFrame,
        volumes: pd.DataFrame | None = None,
        signals: Iterable[str] | None = None,
    ) -> pd.Series:
        components = self.component_scores(closes, volumes=volumes, signals=signals)
        if components.empty:
            return pd.Series(0.0, index=closes.columns)
        weights = pd.Series(1.0 / components.shape[1], index=components.columns)
        return cross_sectional_zscore(components.mul(weights, axis=1).sum(axis=1))

    def ic_weighted_alpha(
        self,
        components: pd.DataFrame,
        ic_history: Mapping[str, Sequence[float]] | None = None,
        ic_lookback: int = 26,
        weighting_mode: str = "positive",
        corr_penalty: float = 0.35,
        min_abs_weight: float = 0.0,
        prev_weights: Mapping[str, float] | None = None,
        weight_smoothing: float = 0.0,
        max_signal_weight: float | None = None,
        ic_ewm_decay: float = 0.0,
    ) -> tuple[pd.Series, Dict[str, float]]:
        # TODO(framework-stage, deferred):
        # 1) Add IC threshold gating to zero-out persistently weak signals.
        # 2) Add IC significance gating (t-stat / hit-rate filter) before non-zero weights.
        if components.empty:
            return pd.Series(dtype=float), {}

        ic_history = ic_history or {}
        mean_ic = pd.Series(index=components.columns, dtype=float)
        ic_ewm_decay = float(np.clip(ic_ewm_decay, 0.0, 0.999))
        for name in components.columns:
            values = list(ic_history.get(name, []))
            tail = values[-int(ic_lookback) :] if ic_lookback > 0 else values
            tail_arr = np.asarray(tail, dtype=float)
            finite = tail_arr[np.isfinite(tail_arr)]
            if finite.size == 0:
                mean_ic.loc[name] = np.nan
                continue
            if ic_ewm_decay > 0 and finite.size > 1:
                # EWMA with stronger weight on recent observations.
                weights = np.power(ic_ewm_decay, np.arange(finite.size - 1, -1, -1))
                weights = weights / weights.sum()
                mean_ic.loc[name] = float(np.sum(finite * weights))
            else:
                mean_ic.loc[name] = float(finite.mean())

        if weighting_mode == "signed":
            base = mean_ic.fillna(0.0)
        else:
            base = mean_ic.fillna(0.0).clip(lower=0.0)

        if float(base.abs().sum()) <= 0.0:
            base = pd.Series(1.0, index=components.columns, dtype=float)

        corr = components.corr().fillna(0.0)
        corr_penalty = float(np.clip(corr_penalty, 0.0, 1.0))
        corr_scale = pd.Series(1.0, index=components.columns, dtype=float)
        if len(corr.columns) > 1 and corr_penalty > 0:
            for name in corr.columns:
                peers = corr.loc[name].drop(index=name, errors="ignore")
                avg_abs_corr = float(peers.abs().mean()) if len(peers) > 0 else 0.0
                corr_scale[name] = max(0.05, 1.0 - corr_penalty * avg_abs_corr)

        penalized = base * corr_scale
        floor = float(max(0.0, min_abs_weight))
        if floor > 0.0:
            penalized = penalized.apply(
                lambda x: np.sign(x) * max(abs(float(x)), floor) if float(x) != 0.0 else 0.0
            )

        denom = float(penalized.abs().sum())
        if denom <= 0:
            norm = pd.Series(1.0 / len(penalized), index=penalized.index, dtype=float)
        else:
            norm = penalized / denom

        if max_signal_weight is not None and float(max_signal_weight) > 0:
            max_w = float(max_signal_weight)
            sign = np.sign(norm)
            capped_abs = norm.abs().clip(upper=max_w)
            if float(capped_abs.sum()) > 0:
                norm = sign * capped_abs
                norm = norm / float(norm.abs().sum())

        smooth = float(np.clip(weight_smoothing, 0.0, 0.95))
        if prev_weights and smooth > 0:
            prev = pd.Series(prev_weights, dtype=float).reindex(norm.index).fillna(0.0)
            if float(prev.abs().sum()) > 0:
                prev = prev / float(prev.abs().sum())
                norm = (1.0 - smooth) * norm + smooth * prev
                if float(norm.abs().sum()) > 0:
                    norm = norm / float(norm.abs().sum())

        composite = cross_sectional_zscore(components.mul(norm, axis=1).sum(axis=1))
        return composite, {name: float(norm.loc[name]) for name in norm.index}
