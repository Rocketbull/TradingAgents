---
name: tradingagents-test-performance-diagnostics
description: Diagnose slow or regressed pytest performance in the TradingAgents repository. Use when tests get slower, CI/test runtime spikes, specific modules are slow/flaky, or performance comparisons are needed before and after code changes.
---

# TradingAgents Test Performance Diagnostics

## Quick Start
1. Use the project environment: `conda run -n activepm python`.
2. Record baseline timings with durations:
   - `conda run -n activepm python -m pytest -q --durations=25`
3. Re-run only suspect files or tests:
   - `conda run -n activepm python -m pytest -q tests/test_backtest_engine.py --durations=10`
   - `conda run -n activepm python -m pytest -q -k "optimizer and not slow" --durations=10`
4. Compare before/after timings and report deltas.

## Workflow

### 1) Establish a Baseline
1. Run the smallest meaningful suite first (touched modules), then broaden.
2. Capture command, wall-clock runtime, and `--durations` output.
3. If relevant, run twice to reduce one-off noise (warm cache effects).

### 2) Isolate Slow Tests
1. Use `--durations` to identify hotspots.
2. Narrow with `-k`, direct test paths, or single tests.
3. If a test is data-heavy, confirm input size and date ranges are unchanged.

### 3) Identify Root Cause Category
1. Data I/O overhead: repeated parquet loads, large matrix construction, wide universes.
2. Optimization overhead: repeated solver calls or expensive constraints.
3. Test fixture overhead: large setup performed per test instead of once.
4. Re-run instability: flaky timing due to network or environment variability.

### 4) Apply Safe Fixes
1. Keep behavior identical unless user asks for logic change.
2. Prefer local fixture reuse, tighter date windows in tests, or reduced synthetic data dimensions.
3. Avoid adding dependencies just for profiling.

### 5) Verify and Report
1. Re-run targeted tests with `--durations`.
2. Re-run broader relevant suite.
3. Report:
   - commands used,
   - before/after timings,
   - top slow tests before/after,
   - residual risk (if full suite not run).

## TradingAgents-Specific Hotspots
- Backtest/portfolio tests:
  - `tests/test_backtest_engine.py`
  - `tests/test_portfolio_pipeline.py`
- Backtest path costs often come from:
  - repeated universe resolution,
  - covariance/optimizer loops,
  - file I/O for large artifacts.

## Command Patterns
- Full quick baseline:
  - `conda run -n activepm python -m pytest -q --durations=25`
- Module timing:
  - `conda run -n activepm python -m pytest -q tests/test_portfolio_pipeline.py --durations=20`
- One test timing:
  - `conda run -n activepm python -m pytest -q tests/test_portfolio_pipeline.py::test_optimizer_enforces_active_weight_cap --durations=5`
- Fail-fast while iterating:
  - `conda run -n activepm python -m pytest -q -x --durations=10`

## Guardrails
- Use `conda run -n activepm python` for all pytest runs.
- Keep comparisons apples-to-apples: same test selection, same env, same data window.
- Do not claim performance improvements without measured before/after evidence.
