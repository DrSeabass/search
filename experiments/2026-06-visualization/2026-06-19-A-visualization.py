#!/usr/bin/env python3
"""Visualization study: greedy, a weighted-A* sweep, and an anytime search.

A worked example of producing data for statistical visualization against the
search suite. It runs three algorithm families over ~100 instances per domain
(swept across sizes for a spread of difficulty):

  1. greedy best-first search
  2. weighted A* at several weights
  3. ARA* (anytime weighted A*), which emits an improving-incumbent trajectory

It uses the shared searchlab package (Experiment + Run, the stdin shim, the RDB
parser, the size-sweep instance generator) and produces Lab's canonical
`properties` file. The actual figures are drawn by the companion plots.py, which
reads that `properties` file:

  - metric cross-product scatter (wall time x cost x length x expansions x
    generated), one figure per algorithm, points colored by domain;
  - anytime profiles (solution cost vs wall time) for ARA*, from the incumbent
    trajectory captured into list-valued properties by the parser.

Run the experiment (build/run/parse/fetch) here, then run plots.py on the
resulting data/<exp>-eval/properties. See README.md.

Environment variables (defaults shown):
  VIZ_INSTANCES_PER_DOMAIN   default 100 (set lower for a quick local run)
  VIZ_TIME_LIMIT             per-run CPU seconds; default 60
  VIZ_MEMORY_MB              per-run memory cap; default 3584
  VIZ_PROCESSES              local parallelism; default 4
  VIZ_DOMAINS                comma-separated subset; default all working
  VIZ_WEIGHTS                wA* weights, comma-separated; default 1.5,2,3,5
  VIZ_ARA_WT0 / VIZ_ARA_DWT  ARA* start weight / decrement; default 5 / 0.5
  TETRALITH_ACCOUNT          default naiss2026-4-694
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
TARGET_PER_DOMAIN = int(os.environ.get("VIZ_INSTANCES_PER_DOMAIN", "100"))
TIME_LIMIT = int(os.environ.get("VIZ_TIME_LIMIT", "60"))
MEMORY_MB = int(os.environ.get("VIZ_MEMORY_MB", "3584"))
LOCAL_PROCESSES = int(os.environ.get("VIZ_PROCESSES", "4"))

_domains_env = os.environ.get("VIZ_DOMAINS")
if _domains_env:
    DOMAINS = [d.strip() for d in _domains_env.split(",") if d.strip()]
    unknown = [d for d in DOMAINS if d not in instances.DOMAINS]
    if unknown:
        sys.exit(f"Unknown VIZ_DOMAINS: {unknown}; "
                 f"available: {sorted(instances.DOMAINS)}")
else:
    DOMAINS = sorted(instances.DOMAINS)

WEIGHTS = [w.strip() for w in os.environ.get("VIZ_WEIGHTS", "1.5,2,3,5").split(",")
           if w.strip()]
ARA_WT0 = os.environ.get("VIZ_ARA_WT0", "5")
ARA_DWT = os.environ.get("VIZ_ARA_DWT", "0.5")

# ----------------------------------------------------------------------------
# Algorithm basket: greedy, a wA* weight sweep, and ARA* (anytime).
# ----------------------------------------------------------------------------
ALGORITHMS = [("greedy", ["greedy"])]
for w in WEIGHTS:
    ALGORITHMS.append((f"wastar-{w}", ["wastar", "-wt", w]))
ALGORITHMS.append((f"arastar", ["arastar", "-wt0", ARA_WT0, "-dwt", ARA_DWT]))

# ----------------------------------------------------------------------------
# Environment
# ----------------------------------------------------------------------------
if IS_TETRALITH:
    ENV = project.TetralithEnvironment(
        memory_per_cpu="3G", cpus_per_task=1,
        extra_options=f"#SBATCH --account={NAISS_ACCOUNT}",
    )
else:
    ENV = project.LocalEnvironment(processes=LOCAL_PROCESSES)

# ----------------------------------------------------------------------------
# Generate ~100 instances/domain across sizes, then enumerate them.
# ----------------------------------------------------------------------------
instances.generate(INSTANCES_ROOT, TARGET_PER_DOMAIN, domains=DOMAINS)

# ----------------------------------------------------------------------------
# Build the experiment
# ----------------------------------------------------------------------------
exp = Experiment(environment=ENV)
exp.add_resource("run_solver", str(SEARCHLAB / "run-solver.sh"))
for domain in DOMAINS:
    exp.add_resource(f"solver_{domain}", str(REPO / instances.DOMAINS[domain]["solver"]))

num_runs = 0
for domain in DOMAINS:
    for inst in instances.enumerate_instances(INSTANCES_ROOT / domain):
        problem = instances.problem_name(inst)
        for algo_name, alg_argv in ALGORITHMS:
            run = exp.add_run()
            run.add_resource("instance", inst["path"], "instance")
            run.add_command(
                "solve",
                ["{run_solver}", f"{{solver_{domain}}}", "instance", *alg_argv],
                time_limit=TIME_LIMIT, memory_limit=MEMORY_MB,
            )
            run.set_property("domain", domain)
            run.set_property("problem", problem)
            run.set_property("algorithm", algo_name)
            run.set_property("id", [algo_name, domain, problem])
            for k, v in inst["params"].items():
                run.set_property(f"param_{k}", v)
            run.set_property("limit_time", TIME_LIMIT)
            run.set_property("limit_memory_mb", MEMORY_MB)
            num_runs += 1

print(f"[viz] {num_runs} runs: {len(DOMAINS)} domains x {len(ALGORITHMS)} "
      f"algorithms x ~{TARGET_PER_DOMAIN} instances "
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
    "error", "coverage", "cost", "length",
    Attribute("expansions", function=arithmetic_mean, min_wins=True),
    Attribute("generated", function=arithmetic_mean, min_wins=True),
    Attribute("solver_wall_time", function=geometric_mean, min_wins=True, digits=4),
    "initial_h",
]
project.add_absolute_report(exp, attributes=ATTRIBUTES)

# Figures are produced by plots.py from the fetched properties; see README.
if not project.REMOTE:
    import subprocess
    eval_props = Path(exp.eval_dir) / "properties"
    exp.add_step("plots", subprocess.call,
                 [sys.executable, str(DIR / "plots.py"), str(eval_props),
                  "-o", str(DIR / "plots")])

exp.run_steps()
