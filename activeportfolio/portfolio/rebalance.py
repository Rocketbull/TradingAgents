from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class Rebalancer:
    """Convert current/target weights into trade instructions."""

    transaction_cost_bps: float = 5.0

    def generate_orders(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        portfolio_value: float = 1_000_000.0,
    ) -> list[dict]:
        orders = []
        all_symbols = sorted(set(current_weights) | set(target_weights))
        for symbol in all_symbols:
            current = float(current_weights.get(symbol, 0.0))
            target = float(target_weights.get(symbol, 0.0))
            delta = target - current
            if abs(delta) < 1e-8:
                continue
            notional = delta * portfolio_value
            est_cost = abs(notional) * (self.transaction_cost_bps / 10_000.0)
            orders.append(
                {
                    "symbol": symbol,
                    "action": "BUY" if delta > 0 else "SELL",
                    "delta_weight": delta,
                    "target_weight": target,
                    "notional": notional,
                    "estimated_cost": est_cost,
                }
            )
        return orders

