# 4-Week Study Plan (7:00-9:00 PM)

## Daily Session Structure
1. 7:00-7:45 PM: Concept learning
2. 7:45-8:45 PM: Implementation and experiments
3. 8:45-9:00 PM: Log results and plan next task

## Week 1: Foundations
1. Monday: Metrics basics (`hit_rate`, `base_rate`, `lift`, `edge`) and manual calculation from one sweep row.
2. Tuesday: Binomial CI basics and 90% CI calculation for 2-3 rows.
3. Wednesday: Read `research/hypothesis_analysis.py` and map formulas to code.
4. Thursday: Run 3 targeted sweeps and compare `lift` vs `edge`.
5. Friday: Write one-page summary of what signal quality means in your context.
6. Saturday: Reproduce key outputs from scratch.

## Week 2: Reliability
1. Monday: Add CI columns to sweep outputs (script/notebook).
2. Tuesday: Learn significance testing for proportions (signal vs baseline).
3. Wednesday: Add ranking rules (`min sample`, `edge`, CI lower bound).
4. Thursday: Run broader sweep and filter statistically credible rows.
5. Friday: Build top-candidate table with rationale.
6. Saturday: Robustness check with nearby thresholds.

## Week 3: Out-of-Sample Discipline
1. Monday: Split data into train/test windows.
2. Tuesday: Tune thresholds on train only.
3. Wednesday: Evaluate fixed thresholds on test.
4. Thursday: Run walk-forward validation (2-3 windows).
5. Friday: Compare in-sample vs out-of-sample degradation.
6. Saturday: Keep only signals that survive OOS criteria.

## Week 4: Practical Usage
1. Monday: Define action policy (what to do when signal is on/off).
2. Tuesday: Simulate policy impact with simple assumptions.
3. Wednesday: Add one regime filter (e.g., volatility/rates proxy).
4. Thursday: Compare regime-conditioned vs unconditional signal.
5. Friday: Write a concise research playbook.
6. Saturday: Final review and next-month roadmap.

## Tracking Template Columns
1. `Date`
2. `Topic`
3. `Task`
4. `Command/Script`
5. `Output file`
6. `Key metrics`
7. `Conclusion`
8. `Next step`
