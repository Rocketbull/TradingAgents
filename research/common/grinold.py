from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class GrinoldDiagnostics:
    weighting_mode: str = "long_short"
    top_k: int = 25
    ic_gate_lookback: int = 26
    ic_gate_min_mean: float | None = None
    ic_gate_use_abs_mean: bool = False
    ic_gate_min_tstat: float | None = None
    ic_gate_min_hit_rate: float | None = None
    ic_gate_min_samples: int = 12

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
        gate_df = self._ic_gate_stats(daily_df["ic"] if not daily_df.empty else pd.Series(dtype=float))
        if not gate_df.empty:
            daily_df = pd.concat([daily_df.reset_index(drop=True), gate_df.reset_index(drop=True)], axis=1)

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
        gate_pass_rate = (
            float(pd.to_numeric(daily_df["ic_gate_pass"], errors="coerce").mean())
            if ("ic_gate_pass" in daily_df.columns and not daily_df.empty)
            else float("nan")
        )
        gate_effective_points = (
            int(pd.to_numeric(daily_df["ic_gate_is_effective"], errors="coerce").fillna(0).sum())
            if "ic_gate_is_effective" in daily_df.columns
            else 0
        )
        gate_fallback_rate = (
            float(pd.to_numeric(daily_df["ic_gate_fallback"], errors="coerce").mean())
            if ("ic_gate_fallback" in daily_df.columns and not daily_df.empty)
            else float("nan")
        )

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
            "ic_gate_lookback": int(self.ic_gate_lookback),
            "ic_gate_min_samples": int(self.ic_gate_min_samples),
            "ic_gate_min_mean": self.ic_gate_min_mean,
            "ic_gate_use_abs_mean": bool(self.ic_gate_use_abs_mean),
            "ic_gate_min_tstat": self.ic_gate_min_tstat,
            "ic_gate_min_hit_rate": self.ic_gate_min_hit_rate,
            "ic_gate_effective_points": gate_effective_points,
            "ic_gate_pass_rate": gate_pass_rate,
            "ic_gate_fallback_rate": gate_fallback_rate,
        }
        return summary, daily_df

    def _ic_gate_stats(self, ic_series: pd.Series) -> pd.DataFrame:
        if ic_series.empty:
            return pd.DataFrame()

        vals = pd.to_numeric(ic_series, errors="coerce").replace([np.inf, -np.inf], np.nan)
        n = len(vals)
        lookback = int(max(1, self.ic_gate_lookback))
        min_samples = int(max(1, self.ic_gate_min_samples))

        rec: list[dict[str, Any]] = []
        for i in range(n):
            hist = vals.iloc[max(0, i - lookback) : i].dropna().values
            h_n = int(hist.size)
            if h_n > 0:
                h_mean = float(np.mean(hist))
                h_hit = float(np.mean(hist > 0.0))
            else:
                h_mean = float("nan")
                h_hit = float("nan")
            if h_n > 1:
                h_std = float(np.std(hist, ddof=1))
                if h_std > 0:
                    h_t = float(h_mean / h_std * np.sqrt(h_n))
                elif h_mean > 0:
                    h_t = float("inf")
                elif h_mean < 0:
                    h_t = float("-inf")
                else:
                    h_t = 0.0
            else:
                h_std = float("nan")
                h_t = float("nan")

            # A gate is considered "effective" only if thresholds are set.
            has_threshold = any(
                [
                    self.ic_gate_min_mean is not None,
                    self.ic_gate_min_tstat is not None,
                    self.ic_gate_min_hit_rate is not None,
                ]
            )
            is_effective = bool(has_threshold)

            passed = True
            if self.ic_gate_min_mean is not None:
                thr = float(self.ic_gate_min_mean)
                if self.ic_gate_use_abs_mean:
                    passed = passed and (np.isfinite(h_mean) and abs(h_mean) >= thr)
                else:
                    passed = passed and (np.isfinite(h_mean) and h_mean >= thr)
            if (self.ic_gate_min_tstat is not None) or (self.ic_gate_min_hit_rate is not None):
                passed = passed and (h_n >= min_samples)
                if self.ic_gate_min_tstat is not None:
                    passed = passed and (np.isfinite(h_t) and h_t >= float(self.ic_gate_min_tstat))
                if self.ic_gate_min_hit_rate is not None:
                    passed = passed and (np.isfinite(h_hit) and h_hit >= float(self.ic_gate_min_hit_rate))

            rec.append(
                {
                    "ic_hist_n": h_n,
                    "ic_hist_mean": h_mean,
                    "ic_hist_std": h_std,
                    "ic_hist_tstat": h_t,
                    "ic_hist_hit_rate": h_hit,
                    "ic_gate_is_effective": int(is_effective),
                    "ic_gate_pass": int(bool(passed)),
                    "ic_gate_fallback": int(bool(is_effective) and not bool(passed)),
                }
            )
        return pd.DataFrame(rec)
