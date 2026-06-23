#!/usr/bin/env python3
"""Triangle and Rectangle, base configs, run to completion.

Runs the two depth-striated beam searches in their *base* configurations
(default parameters -- triangle slope 1, rectangle width 100 / aspect 1) in
ANYTIME mode, letting each run "to completion": it keeps improving the incumbent
until the open lists are exhausted (the cost is then proved optimal) or it hits
a generous time/memory budget. A* is included as the optimal reference so the
incumbent each search converges to can be checked against the true optimum.

This is the experiment the reopening + anytime convergence work was built for:
on instances small enough to exhaust, triangle/rectangle should reach A*'s cost
and report `proved_optimal=1`; on larger ones the incumbent_cost trajectory
shows how close they get within the budget.

Mirrors experiments/2026-06-baseline: generic Lab Experiment + Run, the stdin
shim, the shared RDB parser (extended here with a proved-optimal flag). Auto-
detects Tetralith; otherwise runs locally with a tighter default scope.

Environment variables (defaults shown):
  COMPLETE_INSTANCES_PER_DOMAIN   3 local / 10 Tetralith
  COMPLETE_TIME_LIMIT             per-run seconds; 60 local / 1800 Tetralith
  COMPLETE_MEMORY_MB              per-run memory cap; 4096 local / 8192 Tetralith
  COMPLETE_PROCESSES              local parallelism; default 4
  COMPLETE_DOMAINS                comma-separated subset; default all working
  TETRALITH_ACCOUNT               default naiss2026-4-694

Usage:
  ./2026-06-23-B-base-to-completion.py --all
  ./2026-06-23-B-base-to-completion.py build start parse fetch
"""

import os
import platform
import re
import sys
from pathlib import Path

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
    INSTANCES_PER_DOMAIN = int(os.environ.get("COMPLETE_INSTANCES_PER_DOMAIN", "10"))
    TIME_LIMIT = int(os.environ.get("COMPLETE_TIME_LIMIT", "1800"))
    MEMORY_MB = int(os.environ.get("COMPLETE_MEMORY_MB", "8192"))
else:
    INSTANCES_PER_DOMAIN = int(os.environ.get("COMPLETE_INSTANCES_PER_DOMAIN", "3"))
    TIME_LIMIT = int(os.environ.get("COMPLETE_TIME_LIMIT", "60"))
    MEMORY_MB = int(os.environ.get("COMPLETE_MEMORY_MB", "4096"))

LOCAL_PROCESSES = int(os.environ.get("COMPLETE_PROCESSES", "4"))

_domains_env = os.environ.get("COMPLETE_DOMAINS")
if _domains_env:
    DOMAINS = [d.strip() for d in _domains_env.split(",") if d.strip()]
    unknown = [d for d in DOMAINS if d not in instances.DOMAINS]
    if unknown:
        sys.exit(f"Unknown COMPLETE_DOMAINS: {unknown}; "
                 f"available: {sorted(instances.DOMAINS)}")
else:
    DOMAINS = sorted(instances.DOMAINS)

# ----------------------------------------------------------------------------
# Algorithm basket: base configs, run to completion (anytime), plus A* (the
# optimal reference). Limits are appended uniformly below.
# ----------------------------------------------------------------------------
ALGORITHMS = [
    ("astar", ["astar"]),                          # optimal reference
    ("triangle", ["triangle", "-anytime"]),        # base config (slope 1), to completion
    ("rectangle", ["rectangle", "-anytime"]),      # base config (width 100, aspect 1)
]


def with_limits(argv):
    """Append the solver's own time/memory caps (defense in depth on top of
    Lab's limits, and so anytime runs self-stop and flush their incumbent before
    any hard kill)."""
    return [*argv, "-walltime", str(TIME_LIMIT), "-mem", f"{MEMORY_MB}M"]


# ----------------------------------------------------------------------------
# Environment
# ----------------------------------------------------------------------------
if IS_TETRALITH:
    ENV = project.TetralithEnvironment(
        memory_per_cpu=f"{MEMORY_MB // 1024 + 1}G",
        cpus_per_task=1,
        extra_options=f"#SBATCH --account={NAISS_ACCOUNT}",
    )
else:
    ENV = project.LocalEnvironment(processes=LOCAL_PROCESSES)

# ----------------------------------------------------------------------------
# Instances (idempotent), then enumerate.
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

print(f"[base-to-completion] {num_runs} runs: {len(DOMAINS)} domains x "
      f"{len(ALGORITHMS)} algorithms x {INSTANCES_PER_DOMAIN} instances "
      f"(time_limit={TIME_LIMIT}s, memory={MEMORY_MB}MB)")


# A run that exhausts its open lists prints this; for an anytime triangle /
# rectangle that means the incumbent is proved optimal.
def parse_proved_optimal(content, props):
    props["proved_optimal"] = int("best solution found" in content)


parser = rdb_parser.get_parser()
parser.add_function(parse_proved_optimal, file="run.log")
exp.add_parser(parser)

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
    "proved_optimal",
    Attribute("expansions", function=arithmetic_mean, min_wins=True),
    Attribute("generated", function=arithmetic_mean, min_wins=True),
    "length",
    "reopened",
    Attribute("solver_wall_time", function=geometric_mean, min_wins=True, digits=4),
    "initial_h",
    "solver_max_vmem_kb",
    # Anytime trajectory for quality-over-time profiles.
    "incumbent_cost",
    "incumbent_wall_time",
    "incumbent_expansions",
]

project.add_absolute_report(exp, attributes=ATTRIBUTES)

exp.run_steps()
