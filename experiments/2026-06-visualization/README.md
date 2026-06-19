# Visualization study

A worked example of generating data for statistical visualization against the
search suite, and the visualization scripts themselves. It runs three algorithm
families over ~100 instances per domain and draws figures correlating runtime,
solution quality, and search effort, plus anytime-search profiles.

Like the [baseline study](../2026-06-baseline/), it drives the generic Lab layer
via the shared [`../searchlab/`](../searchlab/) package and produces Lab's
canonical `properties` file. The figures are drawn by [`plots.py`](plots.py),
which reads that `properties` file — so the data path stays standard and the
plotting is a thin consumer on top.

## What it runs

Three independent scripts, one per algorithm family, sharing the same instances,
parser, and plotting (all via [`run_study`](../searchlab/study.py)):

- [`2026-06-19-A-greedy.py`](2026-06-19-A-greedy.py) — **greedy** best-first search
- [`2026-06-19-B-wastar.py`](2026-06-19-B-wastar.py) — **weighted A\*** at several
  weights (`VIZ_WEIGHTS`, default `1.5,2,3,5`)
- [`2026-06-19-C-anytime.py`](2026-06-19-C-anytime.py) — **ARA\*** (anytime
  weighted A\*), which emits an improving-incumbent trajectory

Each is its own Lab experiment (own `data/<script>/` and `-eval/`), but they
share the generated `instances/` directory (generation is idempotent, so only
the first run pays for it) and all write figures into the shared `plots/`.

Instances are swept across sizes for a difficulty spread (see
[`../searchlab/instances.py`](../searchlab/instances.py)): parametric domains use
5 sizes × ~20 seeds; size-locked domains (tiles, pancake, synth_tree) use one
size × ~100 seeds.

## What it produces

[`plots.py`](plots.py) writes PNGs to `plots/`:

- `scatter_<algorithm>.png` — a **metric cross-product** (pairs matrix) of
  {wall time, cost, length, expansions, generated}, points colored by domain,
  log axes where a metric is positive. One per algorithm (so the wA\* sweep
  yields one per weight). This is where you read how runtime relates to solution
  length/cost and to nodes expanded/generated.
- `anytime_<algorithm>.png` — **anytime profile**: mean solution quality vs wall
  time with a 95% CI band, averaged over instances, a subplot per domain. Raw
  incumbent costs differ by orders of magnitude across instances, so each is
  normalized to its own converged best (quality = best/in-hand ∈ (0,1]) before
  averaging. Built from the `incumbent_*` list properties the
  [parser](../searchlab/parser.py) captures.
- `anytime_convergence.png` — **normalized anytime convergence**, a subplot per
  domain, a line per algorithm. y(t) is the mean over instances of
  `best_cost / cost_in_hand(t)`, where `best_cost` is the lowest cost found by
  *any* algorithm on that instance, so y is in (0, 1] and rises toward 1 as an
  algorithm reaches the best-known solution. Anytime runs (ARA\*) contribute
  their whole incumbent trajectory; single-shot runs contribute one step at
  their finish time. To compare across algorithms, pass several studies'
  `properties` files at once (see Run).
- `weight_trends.png` — **trends over the weight sequence** for the wA\* sweep:
  one subplot per metric, x = weight, a line per domain showing the geometric
  mean with a shaded 95% confidence interval (computed in log space, so the
  band stays positive on the log axes). Shows the weight tradeoff — search
  effort falls while solution cost/length rise. Produced whenever the data
  contains ≥2 distinct weights (the weight is read from each run's `weight`
  property, or parsed from the algorithm name as a fallback).

## Setup

Requires Python 3.10+, Lab 8.9, and matplotlib.

```sh
cd experiments/2026-06-visualization
uv sync && source .venv/bin/activate          # or: python3 -m venv .venv && \
                                              #     pip install lab==8.9 matplotlib
```

Build the solvers first (repo root): `make everything`.

## Run

Run each script with `--all` (build, run, parse, fetch, report, plots):

```sh
./2026-06-19-A-greedy.py --all
./2026-06-19-B-wastar.py --all
./2026-06-19-C-anytime.py --all
```

Each script's `plots` step runs `plots.py` on its own fetched `properties`,
writing to the shared `plots/`. You can also redraw figures for any one study
without re-running it:

```sh
python plots.py data/2026-06-19-A-greedy-eval/properties -o plots
```

For cross-algorithm figures — notably `anytime_convergence.png`, whose
normalizer is the best cost found by *any* algorithm — pass several studies'
`properties` files at once so the plot sees every algorithm's runs:

```sh
python plots.py \
  data/2026-06-19-A-greedy-eval/properties \
  data/2026-06-19-B-wastar-eval/properties \
  data/2026-06-19-C-anytime-eval/properties \
  -o plots
```

A quick local subset (just two domains, a handful of instances):

```sh
VIZ_DOMAINS=gridnav,drobot VIZ_INSTANCES_PER_DOMAIN=10 VIZ_TIME_LIMIT=10 \
  ./2026-06-19-A-greedy.py --all
VIZ_DOMAINS=gridnav,drobot VIZ_INSTANCES_PER_DOMAIN=10 VIZ_TIME_LIMIT=10 \
  ./2026-06-19-C-anytime.py --all
```

## Scope

| Variable | Default |
|---|---|
| `VIZ_INSTANCES_PER_DOMAIN` | 100 |
| `VIZ_TIME_LIMIT` (CPU s/run) | 60 |
| `VIZ_MEMORY_MB` | 3584 |
| `VIZ_PROCESSES` (local) | 4 |
| `VIZ_DOMAINS` | all working |
| `VIZ_WEIGHTS` (wA\* weights) | `1.5,2,3,5` |
| `VIZ_ARA_WT0` / `VIZ_ARA_DWT` | `5` / `0.5` |
| `TETRALITH_ACCOUNT` | `naiss2026-4-694` |

The full default scope is large (7 domains × ~6 algorithms × ~100 instances ≈
4k runs); on Tetralith the script submits a Slurm array job. Start with a subset
locally.

`instances/`, `data/`, and `plots/` are git-ignored (all reproducible).
