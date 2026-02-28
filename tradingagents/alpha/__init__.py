"""Alpha research module: signals, model composition, and alpha profiles."""

from .base import AlphaSignal
from .model import AlphaModel
from .profiles import apply_alpha_profile, get_alpha_profile, list_alpha_profiles
from .signals import (
    BreakoutAlpha,
    DownsideVolAlpha,
    LowVolAlpha,
    MomentumAlpha,
    ReversalAlpha,
    TrendAlpha,
)

__all__ = [
    "AlphaSignal",
    "AlphaModel",
    "MomentumAlpha",
    "ReversalAlpha",
    "LowVolAlpha",
    "DownsideVolAlpha",
    "TrendAlpha",
    "BreakoutAlpha",
    "apply_alpha_profile",
    "get_alpha_profile",
    "list_alpha_profiles",
]
