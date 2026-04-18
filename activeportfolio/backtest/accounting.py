from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class PortfolioAccountant:
    """Handle transaction costs and NAV updates."""

    transaction_cost_bps: float = 5.0
    slippage_bps: float = 0.0
    min_trade_notional: float = 0.0

    def apply_rebalance(
        self,
        nav_before: float,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
    ) -> tuple[float, Dict[str, float], float, float]:
        """
        Returns:
            nav_after_costs, effective_target_weights, turnover, total_cost
        """
        turnover = sum(
            abs(float(target_weights.get(s, 0.0)) - float(current_weights.get(s, 0.0)))
            for s in set(current_weights) | set(target_weights)
        )
        traded_notional = turnover * nav_before

        if traded_notional < self.min_trade_notional:
            return nav_before, dict(current_weights), 0.0, 0.0

        total_bps = self.transaction_cost_bps + self.slippage_bps
        total_cost = traded_notional * (total_bps / 10_000.0)
        nav_after = max(nav_before - total_cost, 0.0)
        return nav_after, dict(target_weights), turnover, total_cost

    @staticmethod
    def step_nav(
        nav_after_rebalance: float,
        weights: Dict[str, float],
        symbol_returns: Dict[str, float],
    ) -> tuple[float, float]:
        period_return = sum(
            float(weights.get(symbol, 0.0)) * float(symbol_returns.get(symbol, 0.0))
            for symbol in weights
        )
        nav_after_period = nav_after_rebalance * (1.0 + period_return)
        return nav_after_period, period_return

