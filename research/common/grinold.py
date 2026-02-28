from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class GrinoldDiagnostics:
    weighting_mode: str = "long_short"
    top_k: int = 25

    @staticmethod
    def parse_forward_days(raw: str) -> list[int]:
        out: list[int] = []
        for token in str(raw).split(","):
            t = token.strip()
            if not t:
                continue
            val = int(t)
            if val < 1:
                raise ValueError("forward days must be >= 1")
            out.append(val)
        if not out:
            raise ValueError("forward-days cannot be empty")
        return sorted(set(out))

    @staticmethod
    def safe_rank_corr(a: pd.Series, b: pd.Series, min_points: int = 10) -> float:
        aligned = pd.concat([a, b], axis=1).dropna()
        if aligned.shape[0] < min_points:
            return float("nan")
        x = aligned.iloc[:, 0].rank()
        y = aligned.iloc[:, 1].rank()
        if int(x.nunique()) < 2 or int(y.nunique()) < 2:
            return float("nan")
        return float(x.corr(y))

    @staticmethod
    def effective_breadth(weights: pd.Series) -> float:
        w = pd.to_numeric(weights, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
        denom = float((w * w).sum())
        if denom <= 0.0:
            return float("nan")
        return float(1.0 / denom)

    def build_research_weights(self, score_row: pd.Series) -> pd.Series:
        s = pd.to_numeric(score_row, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        weights = pd.Series(0.0, index=score_row.index, dtype=float)
        if s.empty or self.top_k <= 0:
            return weights

        if self.weighting_mode == "long_only":
            k = min(self.top_k, int(s.shape[0]))
            winners = s.nlargest(k).index
            if len(winners) == 0:
                return weights
            weights.loc[winners] = 1.0 / float(len(winners))
            return weights

        k = min(self.top_k, int(s.shape[0] // 2))
        if k <= 0:
            return weights
        winners = s.nlargest(k).index
        losers = s.nsmallest(k).index
        weights.loc[winners] = 0.5 / float(k)
        weights.loc[losers] = -0.5 / float(k)
        return weights

    def evaluate_horizon(
        self,
        signal: pd.DataFrame,
        score: pd.DataFrame,
        fwd_ret: pd.DataFrame,
        horizon_days: int,
    ) -> tuple[dict[str, Any], pd.DataFrame]:
        sig_mask = signal > 0
        sig_vals = fwd_ret.where(sig_mask)
        unsig_vals = fwd_ret.where(~sig_mask)

        sig_count = int(sig_mask.sum().sum())
        total_count = int(signal.notna().sum().sum())
        coverage = float(sig_count / total_count) if total_count else float("nan")
        sig_mean = float(sig_vals.stack().mean()) if sig_count else float("nan")
        base_mean = float(fwd_ret.stack().mean()) if total_count else float("nan")
        unsig_mean = float(unsig_vals.stack().mean()) if total_count else float("nan")
        lift_vs_base = float(sig_mean - base_mean) if sig_count else float("nan")
        spread_vs_unsig = float(sig_mean - unsig_mean) if sig_count else float("nan")
        hit_num = int(((fwd_ret > 0) & sig_mask).sum().sum())
        sig_hit = float(hit_num / sig_count) if sig_count else float("nan")
        base_hit = float((fwd_ret > 0).stack().mean()) if total_count else float("nan")

        daily_records: list[dict[str, Any]] = []
        eval_dates = list(fwd_ret.index[:-horizon_days]) if horizon_days < len(fwd_ret.index) else []
        for dt in eval_dates:
            s_row = score.loc[dt]
            r_row = fwd_ret.loc[dt]
            w = self.build_research_weights(s_row)

            ic = self.safe_rank_corr(s_row, r_row)
            tc = self.safe_rank_corr(s_row, w, min_points=5)
            br = self.effective_breadth(w)
            implied_ir_component = (
                float(ic * np.sqrt(br) * tc)
                if np.isfinite(ic) and np.isfinite(br) and np.isfinite(tc)
                else float("nan")
            )

            aligned_returns = r_row.reindex(w.index).fillna(0.0)
            port_ret = float((w * aligned_returns).sum())
            base_ret = float(pd.to_numeric(r_row, errors="coerce").replace([np.inf, -np.inf], np.nan).mean())
            active_ret = float(port_ret - base_ret)

            daily_records.append(
                {
                    "date": dt,
                    "horizon_days": horizon_days,
                    "ic": ic,
                    "tc_proxy": tc,
                    "breadth_proxy": br,
                    "implied_ir_component": implied_ir_component,
                    "portfolio_return": port_ret,
                    "baseline_return": base_ret,
                    "active_return": active_ret,
                    "signal_count": int(sig_mask.loc[dt].sum()) if dt in sig_mask.index else 0,
                }
            )

        daily_df = pd.DataFrame(daily_records)

        ic_mean = float(daily_df["ic"].mean()) if not daily_df.empty else float("nan")
        ic_std = float(daily_df["ic"].std(ddof=0)) if not daily_df.empty else float("nan")
        ic_ir = float(ic_mean / ic_std) if np.isfinite(ic_std) and ic_std > 0 else float("nan")
        tc_mean = float(daily_df["tc_proxy"].mean()) if not daily_df.empty else float("nan")
        br_mean = float(daily_df["breadth_proxy"].mean()) if not daily_df.empty else float("nan")

        implied_ir = (
            float(ic_mean * np.sqrt(br_mean) * tc_mean)
            if np.isfinite(ic_mean) and np.isfinite(br_mean) and br_mean > 0 and np.isfinite(tc_mean)
            else float("nan")
        )
        active_mean = float(daily_df["active_return"].mean()) if not daily_df.empty else float("nan")
        active_std = float(daily_df["active_return"].std(ddof=0)) if not daily_df.empty else float("nan")
        realized_active_ir = float(active_mean / active_std) if np.isfinite(active_std) and active_std > 0 else float("nan")

        summary = {
            "horizon_days": horizon_days,
            "sample_points": total_count,
            "signal_points": sig_count,
            "signal_coverage": coverage,
            "signal_mean_return": sig_mean,
            "baseline_mean_return": base_mean,
            "unsignaled_mean_return": unsig_mean,
            "lift_vs_baseline": lift_vs_base,
            "spread_signal_minus_unsignaled": spread_vs_unsig,
            "signal_hit_rate": sig_hit,
            "baseline_hit_rate": base_hit,
            "avg_rank_ic": ic_mean,
            "ic_std": ic_std,
            "ic_ir": ic_ir,
            "avg_tc_proxy": tc_mean,
            "avg_breadth_proxy": br_mean,
            "implied_ir": implied_ir,
            "realized_active_ir": realized_active_ir,
        }
        return summary, daily_df
