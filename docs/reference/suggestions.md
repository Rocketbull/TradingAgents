Document type: reference notes and external suggestions, not the primary project plan.
Accepted decisions should be reflected in `docs/plans/active-portfolio-plan.md` or the relevant workflow guide.

This discussion has moved from the theoretical "Bible" of quantitative finance to a practical framework for building and auditing an investment strategy. By applying the **Grinold and Kahn** lens, we’ve shifted the focus from "picking winners" to "managing a repeatable process."

Here is the high-level summary and a structured project plan to implement these concepts.

---

### Executive Summary: The 4 Pillars

1. **The Fundamental Law:** Success ($IR$) is the product of your skill ($IC$) and how often you apply it ($\sqrt{BR}$). If you aren't a genius, you must be prolific.
2. **Alpha Refinement:** Raw data is noise. To turn a signal into a trade, you must standardize it into a Z-score and adjust for volatility.
3. **The Constraints Tax ($TC$):** Real-world limits (no shorting, high fees, low liquidity) "tax" your skill. A great researcher with a bad execution platform will have a low $IR$.
4. **The Horizon of Skill:** High-volatility strategies (like ARKK) require much longer time horizons to prove skill ($IR$) versus luck ($Beta$).

---

### Project Plan: Building the "Grinold" Engine

If you were to build a local version of this system (utilizing your existing Python/AMD setup), here is your checklist.

#### Phase 1: Signal Generation & Backtesting

* [ ] **Define the Universe:** Select a broad index (e.g., S&P 500 or Russell 2000) to maximize Breadth ($BR$).
* [ ] **Engineer Multiple Signals:** Create at least three uncorrelated factors (e.g., Value, Momentum, and a "Wildcard" like Sentiment).
* [ ] **Calculate Historical IC:** Run a rolling correlation between your signals and forward 1-month returns.
* *Goal:* Achieve a steady $IC$ between **0.02 and 0.07**.



#### Phase 2: Alpha Refinement & Decay

* [ ] **Standardization Module:** Write a function to Z-score all raw signals daily.
* [ ] **Volatility Scaling:** Multiply the Z-score by the asset’s residual volatility to create a "Raw Alpha."
* [ ] **Apply Decay Factor:** Set a "half-life" for each signal. If a signal's $IC$ drops by 50% in 5 days, ensure the optimizer knows to exit the trade by day 5.

#### Phase 3: Construction & Optimization

* [ ] **Build the Covariance Matrix:** Use historical data to find how your stocks move together (to manage Active Risk).
* [ ] **The Transfer Coefficient Test:** * Run an "Unconstrained" optimization (Long/Short).
* Run a "Constrained" optimization (Long-Only).
* Compare the two to see how much alpha your "Long-Only" rule is costing you.


* [ ] **Cost Penalty:** Add a "slippage model" (e.g., 5-10 bps per trade) to the objective function to prevent over-trading.

#### Phase 4: Performance Audit

* [ ] **Tracking Error Monitoring:** Calculate your realized Tracking Error ($\omega$) against your benchmark (e.g., QQQ).
* [ ] **Skill vs. Luck T-Stat:** Every quarter, calculate $IR \times \sqrt{Time}$.
* *Note:* Do not change the strategy until the T-stat is consistently below 1.0 for over a year.



---
