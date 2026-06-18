# Baseline study (Downward Lab)

A worked example of how to run an empirical study against this search suite, and
a standing performance baseline for the standard algorithms. It runs A\*,
weighted A\*, greedy, and speedy across the working domains under controlled
time and memory limits, then produces an `AbsoluteReport` (HTML) and scatter
plots (PNG).

This is the **full-harness** layer. For the fast, dependency-free behavioral
regression check, see [`../../regression/`](../../regression/). The two share
the same solvers and the same RDB output format; this layer adds realistic
instance sets, resource limits, and reports, and runs locally or on a Slurm
cluster (Tetralith).

## Why generic Lab (not FastDownwardExperiment)

The suite has no PDDL translate/preprocess pipeline, so this drives the generic
`lab.experiment` layer (`Experiment` + `Run`) directly. The only suite-specific
glue is:

- [`run-solver.sh`](run-solver.sh) — a stdin shim. The solvers read their
  instance from stdin (`cat inst | solver alg args`), which Lab's no-shell
  `add_command` can't express, so each run calls this instead.
- [`parser.py`](parser.py) — turns the solver's RDB `#pair` output (captured by
  Lab in `run.log`) into Lab attributes (`cost`, `expansions`, `generated`,
  `coverage`, ...). Self-contained so it works on remote nodes.
- [`instances.py`](instances.py) — generates a reproducible instance set into a
  `key_file` directory hierarchy from the suite's seeded generators, and walks
  that hierarchy to feed runs.
- [`project.py`](project.py) — framework-agnostic Lab helpers (cluster-aware
  environments, report helpers), trimmed from the Fast Downward / Scorpion
  `project.py` so the two suites share one analysis style.

## Setup

Requires Python 3.10+ and Lab 8.9. With [uv](https://docs.astral.sh/uv/):

```sh
cd experiments/2026-06-baseline
uv sync                     # creates .venv from pyproject.toml
source .venv/bin/activate
```

or with pip:

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install lab==8.9
```

Build the solvers first (from the repo root): `make everything`.

## Run

```sh
./2026-06-18-A-baseline.py --all        # build, run, parse, fetch, report, plots
```

Or step by step (names or numbers; list them by running with no arguments):

```sh
./2026-06-18-A-baseline.py build start parse fetch
./2026-06-18-A-baseline.py 5            # the AbsoluteReport
```

Outputs land in `data/<exp-name>-eval/` (HTML report + PNG scatter plots).
Instances are generated under `instances/` on first run and reused thereafter;
both directories are git-ignored.

## Scope

Tight by default so a first local run finishes in seconds; widen via env vars:

| Variable | Local default | Tetralith default |
|---|---|---|
| `BASELINE_INSTANCES_PER_DOMAIN` | 3 | 10 |
| `BASELINE_TIME_LIMIT` (CPU s/run) | 30 | 300 |
| `BASELINE_MEMORY_MB` | 3584 | 3584 |
| `BASELINE_PROCESSES` (local) | 4 | — |
| `BASELINE_DOMAINS` | all working | all working |
| `TETRALITH_ACCOUNT` | — | `naiss2026-4-694` |

Example — a quick subset:

```sh
BASELINE_DOMAINS=gridnav,traffic,synth_tree BASELINE_INSTANCES_PER_DOMAIN=2 \
  ./2026-06-18-A-baseline.py --all
```

On Tetralith the script auto-detects the cluster, switches to a
`TetralithEnvironment`, and submits the runs as a Slurm array job.

## Domains and algorithms

Working domains (see [`../../TODO.md`](../../TODO.md) for the exclusions
blocksworld/segments/visnav/plat2d): `tiles`, `gridnav`, `vacuum`, `drobot`,
`synth_tree`, `traffic`, `pancake`.

Algorithm basket: `astar`, `wastar -wt 2`, `greedy`, `speedy`. Limits are
Lab-owned and uniform across algorithms, so heavy optimal runs (e.g. A\* on
tiles or pancake) simply hit the time limit and count as unsolved — which is the
honest, comparable outcome for a study.

## Reusing this as a template

To start a new study, copy this directory to
`experiments/<date>-<slug>/`, rename the experiment script, and edit the
`ALGORITHMS` basket and scope. The shim, parser, instance machinery, and
`project.py` carry over unchanged.
