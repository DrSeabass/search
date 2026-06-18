# Performance-regression baseline

This directory holds the **fast, self-contained** regression layer for the
search suite. It answers one question quickly: *did a code change alter the
search behavior of the standard algorithms on the standard domains?*

For the **full empirical-analysis workflow** (realistic instance sets, time and
memory limits, reports and scatter plots, cluster execution), see
[`../experiments/2026-06-baseline/`](../experiments/2026-06-baseline/), which
drives the same solvers through Downward Lab. This layer is the smoke test; that
layer is how you actually run a study.

## What it does

[`run_regression.py`](run_regression.py), for each domain in the working set:

1. generates **one small instance from a fixed seed**,
2. runs a few standard algorithms (A\*, weighted A\*, greedy, speedy) on it,
3. parses the solver's RDB output with the suite's own
   [`utils/rdb_to_json.py`](../utils/rdb_to_json.py), and
4. compares a stable metric subset against [`golden.json`](golden.json).

## Run it

```sh
make regression                 # build everything, then check against golden
# or directly:
python3 regression/run_regression.py
python3 regression/run_regression.py --verbose          # show every run
python3 regression/run_regression.py --only tiles gridnav
```

Exit status is `0` when everything matches, `1` on a mismatch, `2` on a
setup/run error. The whole suite runs in a few seconds, so it is cheap enough
for a pre-commit or CI gate.

## Re-blessing the baseline

When you make a change that **intentionally** alters search behavior (a new
tie-breaking rule, a domain fix, a heuristic change), update the golden file:

```sh
make regression-update
# or: python3 regression/run_regression.py --update
```

Then review the diff to `golden.json` in your commit — the changed numbers are
the visible, reviewable evidence of what your change did.

## What is and isn't asserted

Only **deterministic** metrics are compared:

- `final sol cost`
- `total nodes expanded`
- `total nodes generated`
- `final sol length`

These are reproducible run-to-run for a fixed binary, instance, and
tie-breaking, so a change in any of them is a real behavioral change. Wall and
CPU time are recorded by the solver but **never asserted** here — they are
machine dependent and would make the check flaky. Timing comparisons belong in
the Lab study, under controlled resource limits.

## Working-domain set

Included: `tiles`, `gridnav`, `vacuum`, `drobot`, `synth_tree`, `traffic`,
`pancake`.

Excluded (see [`../TODO.md`](../TODO.md)):

- **blocksworld** — intermittent assertion failure in `Blocksworld::pathcost`
  ([blocksworld/blocksworld.cc:64](../blocksworld/blocksworld.cc)) on some
  generated instances.
- **segments** — no instance has been observed to solve; generator CLI is also
  broken.
- **visnav** — flagged as segfaulting.
- **plat2d** — requires the external `mid` level generator, so it can't be run
  hermetically here.

## Per-domain notes

- **tiles**: A\* on a random 4×4 is ~5M expansions, too slow for a smoke test,
  so this layer uses the satisficing baskets (greedy/speedy/wA\*). A\* on tiles
  is exercised in the Lab study instead.
- **gridnav**: instances are reproducible only when the generators are seeded
  (`mkseedinst -seed S`, `randinst -s S`); both otherwise default to wall-clock
  seeds.
- **vacuum**: run with `--chargers 0`; a charge operator currently stalls the
  search.
- **pancake**: A\* on 50 cakes is heavy, so greedy and wA\* are used.
