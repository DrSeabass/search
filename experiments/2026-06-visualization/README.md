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
- `anytime_<algorithm>.png` — **anytime profiles** (incumbent cost vs wall time)
  for ARA\*, a subplot per domain, drawn from the `incumbent_*` list properties
  the [parser](../searchlab/parser.py) captures from the `incumbent` table.

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
