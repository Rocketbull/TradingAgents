# Config Policy

`research/configs/` is for reusable experiment definitions, not every scratch idea forever.

Current policy:

- Keep durable, named configs in git.
- Put new canonical baselines under `research/configs/baselines/`.
- Put active, reviewable variants under `research/configs/experiments/`.
- Move dead ends and superseded ideas to `research/configs/archive/`.
- Keep lifecycle notes in `research/configs/backtest_decisions.json`.

Status guidance:

- `keep`: canonical baseline or durable reference config.
- `active`: actively used and expected to keep producing runs.
- `candidate`: worth comparing further, not yet canonical.
- `rejected`: test was bad or not worth continuing.
- `superseded`: replaced by a better config or cleaner rerun.
- `bad_test`: output or config was exploratory noise and can be pruned.

Naming guidance for new files:

- `backtest_<domain>_<purpose>.json`
- Examples:
  - `backtest_sp500_current_baseline.json`
  - `backtest_sp500_defensive_candidate.json`
  - `backtest_csi300_relaxed_baseline.json`

Transition note:

- Existing flat config files remain supported.
- New work should prefer the subdirectories below.
- Backtest indexing now scans nested config folders, so migration can happen gradually.
