#!/usr/bin/env python3
"""AAAI parameterless-Triangle: first cross-suite (Burns) batch.

The classic-heuristic-search half of the AAAI evaluation. Runs the Triangle
family and the suite baselines across the working domains under Lab-owned
time/memory limits, and harvests two things:

  * first-solution / coverage  (anytime=off): a static-slope sweep for the
    headline figure -- does the best static slope vary across domains? -- plus
    Rectangle (the ablation) and the satisficing baselines.
  * anytime quality-over-time  (anytime=on): Triangle's improving-incumbent
    trajectory vs ARA*, read from the `#altrow "incumbent"` table.

Mirrors experiments/2026-06-baseline (generic Lab Experiment + Run, the stdin
shim, the RDB parser). Auto-detects Tetralith and computes a Slurm reservation;
otherwise runs locally with a tight default scope.

Every solver argv carries `-walltime`/`-mem` as defense in depth on top of Lab's
own limits: anytime Triangle retains all closed nodes, so an unbounded run will
swap the box. With a wall-time self-stop the run ends gracefully and its final
plan is preserved; if memory binds first the run still recorded its incumbent
trajectory (the data the anytime score uses).

Environment variables (defaults shown):
  TRI_INSTANCES_PER_DOMAIN   default 3 local / 10 Tetralith
  TRI_TIME_LIMIT             per-run CPU seconds; default 30 local / 300 Tetralith
  TRI_MEMORY_MB              per-run memory cap; default 3584
  TRI_PROCESSES              local parallelism; default 4
  TRI_DOMAINS               comma-separated subset; default all working
  TETRALITH_ACCOUNT          default naiss2026-4-694

Usage:
  ./2026-06-22-A-triangle-burns.py --all          # build, run, parse, fetch, report
  ./2026-06-22-A-triangle-burns.py build start parse fetch
See README.md.
"""

import os
import platform
import re
import sys
from pathlib import Path

# Make the shared searchlab package importable (experiments/searchlab).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from searchlab import instances, project            # noqa: E402
from searchlab import parser as rdb_parser           # noqa: E402

from lab.experiment import Experiment                # noqa: E402
from lab.reports import Attribute, arithmetic_mean, geometric_mean  # noqa: E402

# ----------------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------------
DIR = Path(__file__).resolve().parent
REPO = DIR.parents[1]
SEARCHLAB = Path(instances.__file__).resolve().parent
NODE = platform.node()
IS_TETRALITH = bool(re.match(r"tetralith\d+\.nsc\.liu\.se|n\d+", NODE))
NAISS_ACCOUNT = os.environ.get("TETRALITH_ACCOUNT", "naiss2026-4-694")

INSTANCES_ROOT = DIR / "instances"

# ----------------------------------------------------------------------------
# Scope
# ----------------------------------------------------------------------------
if IS_TETRALITH:
    INSTANCES_PER_DOMAIN = int(os.environ.get("TRI_INSTANCES_PER_DOMAIN", "10"))
    TIME_LIMIT = int(os.environ.get("TRI_TIME_LIMIT", "300"))
else:
    INSTANCES_PER_DOMAIN = int(os.environ.get("TRI_INSTANCES_PER_DOMAIN", "3"))
    TIME_LIMIT = int(os.environ.get("TRI_TIME_LIMIT", "30"))

MEMORY_MB = int(os.environ.get("TRI_MEMORY_MB", "3584"))
LOCAL_PROCESSES = int(os.environ.get("TRI_PROCESSES", "4"))

_domains_env = os.environ.get("TRI_DOMAINS")
if _domains_env:
    DOMAINS = [d.strip() for d in _domains_env.split(",") if d.strip()]
    unknown = [d for d in DOMAINS if d not in instances.DOMAINS]
    if unknown:
        sys.exit(f"Unknown TRI_DOMAINS: {unknown}; "
                 f"available: {sorted(instances.DOMAINS)}")
else:
    DOMAINS = sorted(instances.DOMAINS)

# ----------------------------------------------------------------------------
# Algorithm basket. Each entry: (lab algorithm name, solver argv before limits).
# Limits (-walltime/-mem) are appended uniformly below.
# ----------------------------------------------------------------------------
SLOPES = [1, 2, 4, 8, 16, 32, 48, 64]

ALGORITHMS = [
    # Reference + satisficing baselines (already in the suite).
    ("astar", ["astar"]),
    ("greedy", ["greedy"]),
    ("wastar2", ["wastar", "-wt", "2"]),
    ("beam100", ["beam", "-width", "100"]),
    # Ablation: Rectangle (the parent algorithm, width-bounded first-solution).
    ("rect_w100_a1", ["rectangle", "-width", "100", "-aspect", "1"]),
    ("rect_w10_a5", ["rectangle", "-width", "10", "-aspect", "5"]),
    # Anytime baseline.
    ("arastar_5_1", ["arastar", "-wt0", "5", "-dwt", "1"]),
    # Anytime Triangle (improving-incumbent trajectory).
    ("tri_any_s1", ["triangle", "-anytime", "-slope", "1"]),
    ("tri_any_s48", ["triangle", "-anytime", "-slope", "48"]),
]
# Headline-figure data: static-slope first-solution sweep.
for s in SLOPES:
    ALGORITHMS.append((f"tri_s{s}", ["triangle", "-slope", str(s)]))


def with_limits(argv):
    """Append the solver's own time/memory caps as defense in depth."""
    return [*argv, "-walltime", str(TIME_LIMIT), "-mem", f"{MEMORY_MB}M"]


# ----------------------------------------------------------------------------
# Environment
# ----------------------------------------------------------------------------
if IS_TETRALITH:
    ENV = project.TetralithEnvironment(
        memory_per_cpu="3G",
        cpus_per_task=1,
        extra_options=f"#SBATCH --account={NAISS_ACCOUNT}",
    )
else:
    ENV = project.LocalEnvironment(processes=LOCAL_PROCESSES)

# ----------------------------------------------------------------------------
# Generate instances (idempotent), then enumerate them.
# ----------------------------------------------------------------------------
instances.generate(INSTANCES_ROOT, INSTANCES_PER_DOMAIN, domains=DOMAINS,
                   max_sizes=1)

# ----------------------------------------------------------------------------
# Build the experiment
# ----------------------------------------------------------------------------
exp = Experiment(environment=ENV)

exp.add_resource("run_solver", str(SEARCHLAB / "run-solver.sh"))

for domain in DOMAINS:
    solver_rel = instances.DOMAINS[domain]["solver"]
    exp.add_resource(f"solver_{domain}", str(REPO / solver_rel))

num_runs = 0
for domain in DOMAINS:
    domain_root = INSTANCES_ROOT / domain
    for inst in instances.enumerate_instances(domain_root):
        for algo_name, alg_argv in ALGORITHMS:
            run = exp.add_run()
            run.add_resource("instance", inst["path"], "instance")
            run.add_command(
                "solve",
                ["{run_solver}", f"{{solver_{domain}}}", "instance",
                 *with_limits(alg_argv)],
                time_limit=TIME_LIMIT,
                memory_limit=MEMORY_MB,
            )
            problem = instances.problem_name(inst)
            run.set_property("domain", domain)
            run.set_property("problem", problem)
            run.set_property("algorithm", algo_name)
            run.set_property("id", [algo_name, domain, problem])
            for k, v in inst["params"].items():
                run.set_property(f"param_{k}", v)
            run.set_property("limit_time", TIME_LIMIT)
            run.set_property("limit_memory_mb", MEMORY_MB)
            num_runs += 1

print(f"[aaai-triangle] {num_runs} runs: {len(DOMAINS)} domains x "
      f"{len(ALGORITHMS)} algorithms x {INSTANCES_PER_DOMAIN} instances "
      f"(time_limit={TIME_LIMIT}s, memory={MEMORY_MB}MB)")

exp.add_parser(rdb_parser.get_parser())

# ----------------------------------------------------------------------------
# Steps
# ----------------------------------------------------------------------------
exp.add_step("build", exp.build)
exp.add_step("start", exp.start_runs)
exp.add_step("parse", exp.parse)
exp.add_fetcher(name="fetch")

ATTRIBUTES = [
    "error",
    "coverage",
    "cost",
    Attribute("expansions", function=arithmetic_mean, min_wins=True),
    Attribute("generated", function=arithmetic_mean, min_wins=True),
    "length",
    "reopened",
    Attribute("solver_wall_time", function=geometric_mean, min_wins=True, digits=4),
    "initial_h",
    "solver_max_vmem_kb",
    # Anytime trajectory (list-valued; carried for the anytime-score analysis).
    "incumbent_cost",
    "incumbent_wall_time",
    "incumbent_expansions",
]

project.add_absolute_report(exp, attributes=ATTRIBUTES)

# Scatter plots: A* (optimal reference) vs the satisficing Triangle/Rectangle
# configs on search effort and solution quality.
ALGO_NAMES = [name for name, _ in ALGORITHMS]
if "astar" in ALGO_NAMES:
    focus = ["greedy", "beam100", "rect_w10_a5", "tri_s8", "tri_s48"]
    pairs = [("astar", o) for o in focus if o in ALGO_NAMES]
    project.add_scatter_plot_reports(exp, pairs, ["expansions", "cost"])

exp.run_steps()
