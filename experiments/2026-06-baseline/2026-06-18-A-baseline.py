#!/usr/bin/env python3
"""Baseline study: standard search algorithms across the working domains.

This is the worked-example empirical study for the search suite -- the
companion to the fast in-repo regression check in ../../regression/. It runs a
basket of standard algorithms (A*, weighted A*, greedy, speedy) on a small,
reproducible instance set drawn from each working domain, under Lab-owned time
and memory limits, and produces an AbsoluteReport plus scatter plots.

It uses the generic Lab layer (Experiment + Run), not FastDownwardExperiment:
the suite has no PDDL/translate pipeline. Each run invokes run-solver.sh, which
feeds the instance to the solver on stdin (the suite's `cat inst | solver alg`
idiom). parser.py turns the solver's RDB stdout into Lab attributes.

Scope is tight by default so a first local run finishes quickly; widen via env
vars. On Tetralith the defaults go wider and a Slurm reservation is computed.

Environment variables (defaults shown):
  BASELINE_INSTANCES_PER_DOMAIN   default 3 local / 10 Tetralith
  BASELINE_TIME_LIMIT             per-run CPU seconds; default 30 local / 300 Tetralith
  BASELINE_MEMORY_MB              per-run memory cap; default 3584
  BASELINE_PROCESSES              local parallelism; default 4
  BASELINE_DOMAINS                comma-separated subset; default all working
  TETRALITH_ACCOUNT               default naiss2026-4-694

Usage:
  ./2026-06-18-A-baseline.py --all          # build, run, parse, fetch, report
  ./2026-06-18-A-baseline.py build start parse fetch   # individual steps
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
    INSTANCES_PER_DOMAIN = int(os.environ.get("BASELINE_INSTANCES_PER_DOMAIN", "10"))
    TIME_LIMIT = int(os.environ.get("BASELINE_TIME_LIMIT", "300"))
else:
    INSTANCES_PER_DOMAIN = int(os.environ.get("BASELINE_INSTANCES_PER_DOMAIN", "3"))
    TIME_LIMIT = int(os.environ.get("BASELINE_TIME_LIMIT", "30"))

MEMORY_MB = int(os.environ.get("BASELINE_MEMORY_MB", "3584"))
LOCAL_PROCESSES = int(os.environ.get("BASELINE_PROCESSES", "4"))

_domains_env = os.environ.get("BASELINE_DOMAINS")
if _domains_env:
    DOMAINS = [d.strip() for d in _domains_env.split(",") if d.strip()]
    unknown = [d for d in DOMAINS if d not in instances.DOMAINS]
    if unknown:
        sys.exit(f"Unknown BASELINE_DOMAINS: {unknown}; "
                 f"available: {sorted(instances.DOMAINS)}")
else:
    DOMAINS = sorted(instances.DOMAINS)

# ----------------------------------------------------------------------------
# Algorithm basket. Each entry: (lab algorithm name, solver argv).
# ----------------------------------------------------------------------------
ALGORITHMS = [
    ("astar", ["astar"]),
    ("wastar2", ["wastar", "-wt", "2"]),
    ("greedy", ["greedy"]),
    ("speedy", ["speedy"]),
]

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
# This baseline stays small and fast: a single (easiest) size per domain.
instances.generate(INSTANCES_ROOT, INSTANCES_PER_DOMAIN, domains=DOMAINS,
                   max_sizes=1)

# ----------------------------------------------------------------------------
# Build the experiment
# ----------------------------------------------------------------------------
exp = Experiment(environment=ENV)

# The stdin shim, shared by every run.
exp.add_resource("run_solver", str(SEARCHLAB / "run-solver.sh"))

# One solver binary per domain, added once and referenced by all its runs.
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
                ["{run_solver}", f"{{solver_{domain}}}", "instance", *alg_argv],
                time_limit=TIME_LIMIT,
                memory_limit=MEMORY_MB,
            )
            problem = instances.problem_name(inst)
            run.set_property("domain", domain)
            run.set_property("problem", problem)
            run.set_property("algorithm", algo_name)
            run.set_property("id", [algo_name, domain, problem])
            # Surface instance params and limits in the run properties.
            for k, v in inst["params"].items():
                run.set_property(f"param_{k}", v)
            run.set_property("limit_time", TIME_LIMIT)
            run.set_property("limit_memory_mb", MEMORY_MB)
            num_runs += 1

print(f"[baseline] {num_runs} runs: {len(DOMAINS)} domains x {len(ALGORITHMS)} "
      f"algorithms x {INSTANCES_PER_DOMAIN} instances "
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
]

project.add_absolute_report(exp, attributes=ATTRIBUTES)

# Scatter plots: compare A* against each satisficing algorithm on search effort.
ALGO_NAMES = [name for name, _ in ALGORITHMS]
if "astar" in ALGO_NAMES:
    pairs = [("astar", other) for other in ALGO_NAMES if other != "astar"]
    project.add_scatter_plot_reports(exp, pairs, ["expansions", "cost"])

exp.run_steps()
