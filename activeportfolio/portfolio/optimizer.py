from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Any

import numpy as np
import pandas as pd


@dataclass
class PortfolioOptimizer:
    """
    Active portfolio optimizer with optional PyPortfolioOpt backend.

    Falls back to deterministic heuristic optimizer if PyPortfolioOpt is unavailable.
    """

    risk_aversion: float = 3.0
    max_weight: float = 0.05
    active_weight_cap: Optional[float] = None
    sector_active_weight_cap: Optional[float] = None
    tracking_error_target: Optional[float] = None
    turnover_limit: float = 0.20
    sector_cap: Optional[float] = None

    def optimize(
        self,
        alpha_scores: pd.Series,
        covariance: pd.DataFrame,
        current_weights: Optional[Dict[str, float]] = None,
        benchmark_weights: Optional[Dict[str, float]] = None,
        sector_benchmark_weights: Optional[Dict[str, float]] = None,
        sector_map: Optional[Dict[str, str]] = None,
        return_details: bool = False,
    ) -> Dict[str, float] | tuple[Dict[str, float], Dict[str, Any]]:
        symbols = list(alpha_scores.index)
        if not symbols:
            raise ValueError("alpha_scores cannot be empty")

        current = self._align_weights(symbols, current_weights)
        benchmark = self._align_weights(symbols, benchmark_weights)

        details: Dict[str, Any] = {
            "backend": "pypfopt",
            "used_fallback": False,
        }
        try:
            target, raw_target = self._optimize_with_pypfopt(
                alpha_scores,
                covariance,
                current,
                benchmark,
                sector_map,
                sector_benchmark_weights,
            )
        except Exception:
            details["backend"] = "fallback"
            details["used_fallback"] = True
            target, raw_target = self._fallback_optimize(
                alpha_scores,
                current,
                benchmark,
                sector_map,
                sector_benchmark_weights,
            )

        details["audit_unconstrained_active_weights"] = self.audit_unconstrained_active_weights(
            alpha_scores=alpha_scores,
            covariance=covariance,
        )
        details["raw_target_weights"] = raw_target
        details["target_weights"] = target
        if return_details:
            return target, details
        return target

    def audit_unconstrained_active_weights(
        self,
        alpha_scores: pd.Series,
        covariance: pd.DataFrame,
    ) -> Dict[str, float]:
        """
        Solve an unconstrained active-weight audit portfolio from the same alpha/covariance
        inputs used by the constrained optimizer.

        This is a diagnostic long-short active portfolio with the budget constraint
        sum(active_weights) == 0. It is used for corrected TC measurement, not execution.
        """
        symbols = list(alpha_scores.index)
        if not symbols:
            raise ValueError("alpha_scores cannot be empty")

        mu = alpha_scores.reindex(symbols).astype(float).fillna(0.0).values
        cov = (
            covariance.reindex(index=symbols, columns=symbols)
            .astype(float)
            .fillna(0.0)
            .values
        )
        cov = 0.5 * (cov + cov.T)
        cov = np.nan_to_num(cov, nan=0.0, posinf=0.0, neginf=0.0)

        inv_cov = np.linalg.pinv(cov)
        ones = np.ones(len(symbols), dtype=float)
        denom = float(ones @ inv_cov @ ones)
        if abs(denom) > 1e-12:
            lagrange = float(ones @ inv_cov @ mu) / denom
            adjusted_mu = mu - lagrange * ones
        else:
            adjusted_mu = mu - float(np.mean(mu))

        risk_aversion = max(float(self.risk_aversion), 1e-12)
        active = (inv_cov @ adjusted_mu) / risk_aversion
        active = np.nan_to_num(active, nan=0.0, posinf=0.0, neginf=0.0)

        if np.allclose(active, 0.0):
            active = adjusted_mu

        active = active - float(np.mean(active))
        return {symbol: float(weight) for symbol, weight in zip(symbols, active)}

    def _optimize_with_pypfopt(
        self,
        alpha_scores: pd.Series,
        covariance: pd.DataFrame,
        current: pd.Series,
        benchmark: pd.Series,
        sector_map: Optional[Dict[str, str]],
        sector_benchmark_weights: Optional[Dict[str, float]],
    ) -> tuple[Dict[str, float], Dict[str, float]]:
        from pypfopt import EfficientFrontier
        import cvxpy as cp

        benchmark = self._normalize_nonnegative(benchmark)
        mu = alpha_scores.to_dict()
        cov = covariance.loc[alpha_scores.index, alpha_scores.index]
        bounds = self._weight_bounds(benchmark)

        ef = EfficientFrontier(
            expected_returns=pd.Series(mu),
            cov_matrix=cov,
            weight_bounds=bounds,
        )
        self._add_sector_active_constraints(
            ef=ef,
            symbols=list(alpha_scores.index),
            benchmark=benchmark,
            sector_map=sector_map,
            sector_benchmark_weights=sector_benchmark_weights,
        )
        if self.tracking_error_target is not None and float(self.tracking_error_target) > 0:
            te_ann = float(self.tracking_error_target)
            te_var_daily = (te_ann * te_ann) / 252.0
            b_vec = benchmark.reindex(alpha_scores.index).astype(float).values
            cov_arr = cov.values
            ef.add_constraint(lambda w: cp.quad_form(w - b_vec, cov_arr) <= te_var_daily)
        ef.max_quadratic_utility(risk_aversion=self.risk_aversion)
        weights = pd.Series(ef.clean_weights()).reindex(alpha_scores.index).fillna(0.0)
        weights = self._enforce_active_cap(weights, benchmark)
        weights = self._apply_sector_cap(weights, sector_map, benchmark)
        weights = self._enforce_sector_active_cap(weights, benchmark, sector_map, sector_benchmark_weights)
        raw_target = weights.copy()
        adjusted = self._apply_turnover(weights, current)
        adjusted = self._enforce_active_cap(adjusted, benchmark)
        adjusted = self._apply_sector_cap(adjusted, sector_map, benchmark)
        adjusted = self._enforce_sector_active_cap(adjusted, benchmark, sector_map, sector_benchmark_weights)
        return adjusted.to_dict(), raw_target.to_dict()

    def _fallback_optimize(
        self,
        alpha_scores: pd.Series,
        current: pd.Series,
        benchmark: pd.Series,
        sector_map: Optional[Dict[str, str]],
        sector_benchmark_weights: Optional[Dict[str, float]],
    ) -> tuple[Dict[str, float], Dict[str, float]]:
        benchmark = self._normalize_nonnegative(benchmark)
        active = alpha_scores.astype(float) - float(alpha_scores.mean())
        if float(active.abs().sum()) <= 0:
            active = pd.Series(0.0, index=alpha_scores.index)
        if self.active_weight_cap is not None and float(self.active_weight_cap) > 0:
            scale = float(self.active_weight_cap) / max(float(active.abs().max()), 1e-12)
            active = active * min(1.0, scale)
        target = benchmark + active
        target = target.clip(lower=0.0, upper=self.max_weight)
        if target.sum() <= 0:
            target = pd.Series(1.0 / len(target), index=target.index)
        else:
            target = target / target.sum()
        target = self._enforce_active_cap(target, benchmark)
        target = self._apply_sector_cap(target, sector_map, benchmark)
        target = self._enforce_sector_active_cap(target, benchmark, sector_map, sector_benchmark_weights)
        raw_target = target.copy()
        adjusted = self._apply_turnover(target, current)
        adjusted = self._enforce_active_cap(adjusted, benchmark)
        adjusted = self._apply_sector_cap(adjusted, sector_map, benchmark)
        adjusted = self._enforce_sector_active_cap(adjusted, benchmark, sector_map, sector_benchmark_weights)
        return adjusted.to_dict(), raw_target.to_dict()

    def _apply_turnover(self, target: pd.Series, current: pd.Series) -> pd.Series:
        turnover = float((target - current).abs().sum())
        if turnover <= self.turnover_limit:
            return target
        if turnover <= 0:
            return current
        scale = self.turnover_limit / turnover
        adjusted = current + scale * (target - current)
        adjusted = adjusted.clip(lower=0.0, upper=self.max_weight)
        if adjusted.sum() <= 0:
            return target
        return adjusted / adjusted.sum()

    def _apply_sector_cap(
        self,
        weights: pd.Series,
        sector_map: Optional[Dict[str, str]],
        benchmark: Optional[pd.Series] = None,
    ) -> pd.Series:
        if not sector_map or self.sector_cap is None:
            return self._normalize_clip(weights)
        cap = float(self.sector_cap)
        if cap <= 0:
            return self._normalize_clip(weights)

        w = self._normalize_clip(weights)
        lower_bound = pd.Series(0.0, index=w.index)
        upper_bound = pd.Series(float(self.max_weight), index=w.index)
        groups = self._sector_groups(list(w.index), sector_map)
        sector_targets: dict[str, float] = {}
        sector_lowers: dict[str, float] = {}
        sector_uppers: dict[str, float] = {}
        for sector, idxs in groups.items():
            lower = float(lower_bound.iloc[idxs].sum())
            upper = min(float(upper_bound.iloc[idxs].sum()), cap)
            if lower > upper + 1e-10:
                raise ValueError(f"Infeasible sector cap for sector '{sector}'")
            sector_lowers[sector] = lower
            sector_uppers[sector] = upper
            sector_targets[sector] = float(w.iloc[idxs].sum())
        if (
            float(sum(sector_lowers.values())) > 1.0 + 1e-10
            or float(sum(sector_uppers.values())) < 1.0 - 1e-10
        ):
            return self._normalize_clip(w)
        target = self._project_to_sum_with_bounds(
            pd.Series(sector_targets, dtype=float),
            1.0,
            pd.Series(sector_lowers, dtype=float),
            pd.Series(sector_uppers, dtype=float),
        )
        pieces: list[pd.Series] = []
        for sector, idxs in groups.items():
            members = w.index[idxs]
            pieces.append(
                self._project_to_sum_with_bounds(
                    w.loc[members],
                    float(target.loc[sector]),
                    lower_bound.loc[members],
                    upper_bound.loc[members],
                )
            )
        result = pd.concat(pieces).reindex(w.index).fillna(0.0)
        return result.astype(float)

    def _normalize_clip(self, weights: pd.Series) -> pd.Series:
        w = weights.astype(float).clip(lower=0.0, upper=self.max_weight)
        total = float(w.sum())
        if total <= 0:
            return pd.Series(1.0 / len(w), index=w.index)
        return w / total

    def _enforce_active_cap(self, weights: pd.Series, benchmark: pd.Series) -> pd.Series:
        if self.active_weight_cap is None or float(self.active_weight_cap) <= 0:
            return self._normalize_clip(weights)
        cap = float(self.active_weight_cap)
        b = self._normalize_nonnegative(benchmark.reindex(weights.index).fillna(0.0))
        lower = (b - cap).clip(lower=0.0, upper=self.max_weight)
        upper = (b + cap).clip(upper=self.max_weight)
        w = weights.reindex(b.index).fillna(0.0).astype(float)

        for _ in range(12):
            w = w.clip(lower=lower, upper=upper)
            total = float(w.sum())
            deficit = 1.0 - total
            if abs(deficit) <= 1e-10:
                break
            if deficit > 0:
                room = (upper - w).clip(lower=0.0)
                room_sum = float(room.sum())
                if room_sum <= 1e-12:
                    break
                w = w + room * (deficit / room_sum)
            else:
                removable = (w - lower).clip(lower=0.0)
                removable_sum = float(removable.sum())
                if removable_sum <= 1e-12:
                    break
                w = w - removable * ((-deficit) / removable_sum)
        return w.clip(lower=0.0, upper=self.max_weight)

    def _enforce_sector_active_cap(
        self,
        weights: pd.Series,
        benchmark: pd.Series,
        sector_map: Optional[Dict[str, str]],
        sector_benchmark_weights: Optional[Dict[str, float]] = None,
    ) -> pd.Series:
        if (
            self.sector_active_weight_cap is None
            or float(self.sector_active_weight_cap) <= 0
            or not sector_map
        ):
            return self._normalize_clip(weights)

        cap = float(self.sector_active_weight_cap)
        w0 = self._normalize_clip(weights)
        b = self._normalize_nonnegative(benchmark.reindex(w0.index).fillna(0.0))
        if self.sector_cap is None:
            lower_bound, upper_bound = self._active_bounds(b)
        else:
            lower_bound = pd.Series(0.0, index=w0.index)
            upper_bound = pd.Series(float(self.max_weight), index=w0.index)
        groups = self._sector_groups(list(w0.index), sector_map)
        sector_benchmark = self._sector_benchmark_totals(groups, b, sector_benchmark_weights)

        try:
            import cvxpy as cp

            solver_attempts = [
                (cp.OSQP, {"eps_abs": 1e-8, "eps_rel": 1e-8, "max_iter": 100000, "warm_start": True}),
                (cp.CLARABEL, {"warm_start": True}),
                (cp.SCS, {"eps": 1e-6, "max_iters": 20000, "warm_start": True}),
            ]
            last_error: Exception | None = None
            for solver, kwargs in solver_attempts:
                try:
                    x = cp.Variable(len(w0))
                    constraints = [
                        x >= lower_bound.values,
                        x <= upper_bound.values,
                        cp.sum(x) == 1.0,
                    ]
                    for sector, idxs in groups.items():
                        b_sec = float(sector_benchmark.loc[sector])
                        lower = max(0.0, b_sec - cap)
                        upper = min(1.0, b_sec + cap, float(upper_bound.iloc[idxs].sum()))
                        if self.sector_cap is not None:
                            upper = min(upper, float(self.sector_cap))
                        constraints.append(cp.sum(x[idxs]) >= lower)
                        constraints.append(cp.sum(x[idxs]) <= upper)

                    obj = cp.Minimize(cp.sum_squares(x - w0.values))
                    prob = cp.Problem(obj, constraints)
                    prob.solve(solver=solver, **kwargs)
                    if x.value is None:
                        raise ValueError("No solution from cvxpy sector active projection")
                    w = pd.Series(np.asarray(x.value).reshape(-1), index=w0.index)
                    w = w.clip(lower=0.0, upper=self.max_weight)
                    total = float(w.sum())
                    if total <= 0:
                        raise ValueError("Projected weights sum to non-positive total")
                    if abs(total - 1.0) > 1e-6:
                        w = w / total
                    if self._max_sector_active_violation(w, groups, sector_benchmark, cap) > 1e-5:
                        raise ValueError(f"Sector active projection violated cap under solver {solver}")
                    return w
                except Exception as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
        except Exception:
            w = self._repair_sector_active_cap_deterministic(
                weights=w0,
                benchmark=b,
                groups=groups,
                sector_benchmark=sector_benchmark,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                cap=cap,
            )
            if self._max_sector_active_violation(w, groups, sector_benchmark, cap) > 1e-5:
                raise ValueError("Unable to enforce sector active weight cap")
            return w

    @staticmethod
    def _sector_groups(symbols: list[str], sector_map: Dict[str, str]) -> Dict[str, list[int]]:
        groups: Dict[str, list[int]] = {}
        for i, s in enumerate(symbols):
            sec = (
                sector_map.get(s)
                if isinstance(sector_map.get(s), str) and sector_map.get(s)
                else f"Unknown::{s}"
            )
            groups.setdefault(sec, []).append(i)
        return groups

    def _active_bounds(self, benchmark: pd.Series) -> tuple[pd.Series, pd.Series]:
        b = self._normalize_nonnegative(benchmark)
        if self.active_weight_cap is None or float(self.active_weight_cap) <= 0:
            lower = pd.Series(0.0, index=b.index)
            upper = pd.Series(float(self.max_weight), index=b.index)
        else:
            cap = float(self.active_weight_cap)
            lower = (b - cap).clip(lower=0.0, upper=float(self.max_weight))
            upper = (b + cap).clip(upper=float(self.max_weight))
        return lower.astype(float), upper.astype(float)

    @staticmethod
    def _sector_benchmark_totals(
        groups: Dict[str, list[int]],
        benchmark: pd.Series,
        sector_benchmark_weights: Optional[Dict[str, float]],
    ) -> pd.Series:
        totals: dict[str, float] = {}
        provided = pd.Series(sector_benchmark_weights or {}, dtype=float)
        for sector, idxs in groups.items():
            if sector in provided.index and pd.notna(provided.loc[sector]):
                totals[sector] = max(0.0, float(provided.loc[sector]))
            else:
                totals[sector] = float(benchmark.iloc[idxs].sum())
        return pd.Series(totals, dtype=float)

    def _repair_sector_active_cap_deterministic(
        self,
        *,
        weights: pd.Series,
        benchmark: pd.Series,
        groups: Dict[str, list[int]],
        sector_benchmark: pd.Series,
        lower_bound: pd.Series,
        upper_bound: pd.Series,
        cap: float,
    ) -> pd.Series:
        w0 = weights.reindex(benchmark.index).fillna(0.0).astype(float)

        sector_targets: dict[str, float] = {}
        sector_lowers: dict[str, float] = {}
        sector_uppers: dict[str, float] = {}
        for sector, idxs in groups.items():
            b_sec = float(sector_benchmark.loc[sector])
            lower = max(float(lower_bound.iloc[idxs].sum()), b_sec - float(cap), 0.0)
            upper = min(float(upper_bound.iloc[idxs].sum()), b_sec + float(cap), 1.0)
            if self.sector_cap is not None:
                upper = min(upper, float(self.sector_cap))
            if lower > upper + 1e-10:
                raise ValueError(f"Infeasible sector active cap for sector '{sector}'")
            sector_lowers[sector] = lower
            sector_uppers[sector] = upper
            sector_targets[sector] = float(w0.iloc[idxs].sum())

        target = pd.Series(sector_targets, dtype=float)
        lower = pd.Series(sector_lowers, dtype=float).reindex(target.index)
        upper = pd.Series(sector_uppers, dtype=float).reindex(target.index)
        if float(lower.sum()) > 1.0 + 1e-10 or float(upper.sum()) < 1.0 - 1e-10:
            raise ValueError("Infeasible sector active cap across sectors")

        target = self._project_to_sum_with_bounds(target, 1.0, lower, upper)

        pieces: list[pd.Series] = []
        for sector, idxs in groups.items():
            members = w0.index[idxs]
            projected = self._project_to_sum_with_bounds(
                w0.loc[members],
                float(target.loc[sector]),
                lower_bound.loc[members],
                upper_bound.loc[members],
            )
            pieces.append(projected)
        result = pd.concat(pieces).reindex(w0.index).fillna(0.0)
        return result.astype(float)

    @staticmethod
    def _project_to_sum_with_bounds(
        values: pd.Series,
        target_sum: float,
        lower: pd.Series,
        upper: pd.Series,
    ) -> pd.Series:
        lower = lower.reindex(values.index).astype(float)
        upper = upper.reindex(values.index).astype(float)
        if target_sum < float(lower.sum()) - 1e-10 or target_sum > float(upper.sum()) + 1e-10:
            raise ValueError("Target sum is infeasible under bounds")

        w = values.reindex(lower.index).fillna(0.0).astype(float).clip(lower=lower, upper=upper)
        for _ in range(32):
            gap = float(target_sum) - float(w.sum())
            if abs(gap) <= 1e-10:
                break
            if gap > 0:
                room = (upper - w).clip(lower=0.0)
                room_sum = float(room.sum())
                if room_sum <= 1e-12:
                    break
                w = w + room * min(1.0, gap / room_sum)
            else:
                removable = (w - lower).clip(lower=0.0)
                removable_sum = float(removable.sum())
                if removable_sum <= 1e-12:
                    break
                w = w - removable * min(1.0, (-gap) / removable_sum)
        if abs(float(w.sum()) - float(target_sum)) > 1e-7:
            raise ValueError("Could not project weights to requested bounded sum")
        return w

    @staticmethod
    def _max_sector_active_violation(
        weights: pd.Series,
        groups: Dict[str, list[int]],
        sector_benchmark: pd.Series,
        cap: float,
    ) -> float:
        max_violation = 0.0
        for sector, idxs in groups.items():
            weight_sum = float(weights.iloc[idxs].sum())
            benchmark_sum = float(sector_benchmark.loc[sector])
            max_violation = max(max_violation, abs(weight_sum - benchmark_sum) - float(cap))
        return max_violation

    def _add_sector_active_constraints(
        self,
        ef: Any,
        symbols: list[str],
        benchmark: pd.Series,
        sector_map: Optional[Dict[str, str]],
        sector_benchmark_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        if (
            self.sector_active_weight_cap is None
            or float(self.sector_active_weight_cap) <= 0
            or not sector_map
        ):
            return

        cap = float(self.sector_active_weight_cap)
        b = self._normalize_nonnegative(benchmark.reindex(symbols).fillna(0.0))
        groups = self._sector_groups(symbols, sector_map)
        sector_benchmark = self._sector_benchmark_totals(groups, b, sector_benchmark_weights)

        for sec, idxs in groups.items():
            b_sec = float(sector_benchmark.loc[sec])
            lower = max(0.0, b_sec - cap)
            upper = min(1.0, b_sec + cap)
            ef.add_constraint(lambda w, ii=idxs, lo=lower: sum(w[i] for i in ii) >= lo)
            ef.add_constraint(lambda w, ii=idxs, hi=upper: sum(w[i] for i in ii) <= hi)

    def _weight_bounds(self, benchmark: pd.Series) -> list[tuple[float, float]]:
        b = self._normalize_nonnegative(benchmark)
        if self.active_weight_cap is None or float(self.active_weight_cap) <= 0:
            lower = pd.Series(0.0, index=b.index)
            upper = pd.Series(self.max_weight, index=b.index)
        else:
            cap = float(self.active_weight_cap)
            lower = (b - cap).clip(lower=0.0, upper=self.max_weight)
            upper = (b + cap).clip(upper=self.max_weight)
        return [(float(lower.loc[s]), float(max(lower.loc[s], upper.loc[s]))) for s in b.index]

    @staticmethod
    def _normalize_nonnegative(weights: pd.Series) -> pd.Series:
        w = weights.astype(float).clip(lower=0.0)
        total = float(w.sum())
        if total <= 0:
            return pd.Series(1.0 / len(w), index=w.index)
        return w / total

    @staticmethod
    def _align_weights(symbols: list[str], raw: Optional[Dict[str, float]]) -> pd.Series:
        if not raw:
            return pd.Series(1.0 / len(symbols), index=symbols)
        s = pd.Series(raw, dtype=float).reindex(symbols).fillna(0.0)
        total = float(s.sum())
        if total <= 0:
            return pd.Series(1.0 / len(symbols), index=symbols)
        return s / total
