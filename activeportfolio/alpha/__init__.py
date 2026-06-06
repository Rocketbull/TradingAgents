"""Alpha research module: signals, model composition, and alpha profiles."""

from .base import AlphaSignal
from .model import AlphaModel
from .profiles import apply_alpha_profile, get_alpha_profile, list_alpha_profiles
from .signals import (
    BreakoutAlpha,
    DownsideVolAlpha,
    FlatVolumeBreakoutAlpha,
    LowVolAlpha,
    MomentumAlpha,
    MomentumSkipRecentAlpha,
    RangePositionAlpha,
    ReversalAlpha,
    TrendAlpha,
    VolAdjMomentumAlpha,
    VolumeConfirmedMomentumAlpha,
    VolumeShockAlpha,
)

__all__ = [
    "AlphaSignal",
    "AlphaModel",
    "MomentumAlpha",
    "MomentumSkipRecentAlpha",
    "ReversalAlpha",
    "LowVolAlpha",
    "DownsideVolAlpha",
    "TrendAlpha",
    "BreakoutAlpha",
    "FlatVolumeBreakoutAlpha",
    "VolAdjMomentumAlpha",
    "RangePositionAlpha",
    "VolumeShockAlpha",
    "VolumeConfirmedMomentumAlpha",
    "apply_alpha_profile",
    "get_alpha_profile",
    "list_alpha_profiles",
]
