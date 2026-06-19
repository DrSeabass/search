"""Shared experiment driver for the search-suite visualization studies.

`run_study(algorithms)` builds and runs one Lab experiment for a given set of
algorithms over the working domains: it reads scope from VIZ_* environment
variables, generates the size-swept instance set (shared across studies in the
same directory), adds one run per (instance x algorithm), parses the RDB output,
fetches an AbsoluteReport, and (locally) draws figures with plots.py.

Each calling script gets its own Lab data/eval directory (named after the
script), so the greedy / weighted-A* / anytime studies are independent runs but
share instances, the parser, and the plotting. See the thin scripts in
experiments/2026-06-visualization/ for usage.
"""

import os
import platform
import re
import subprocess
import sys
from pathlib import Path

from lab.experiment import Experiment
from lab.reports import Attribute, arithmetic_mean, geometric_mean

from searchlab import instances, project
from searchlab import parser as rdb_parser

SEARCHLAB = Path(__file__).resolve().parent
REPO = SEARCHLAB.parents[1]

NODE = platform.node()
IS_TETRALITH = bool(re.match(r"tetralith\d+\.nsc\.liu\.se|n\d+", NODE))

ATTRIBUTES = [
    "error", "coverage", "cost", "length",
    Attribute("expansions", function=arithmetic_mean, min_wins=True),
    Attribute("generated", function=arithmetic_mean, min_wins=True),
    Attribute("solver_wall_time", function=geometric_mean, min_wins=True, digits=4),
    "initial_h",
]


def _domains():
    env = os.environ.get("VIZ_DOMAINS")
    if not env:
        return sorted(instances.DOMAINS)
    chosen = [d.strip() for d in env.split(",") if d.strip()]
    unknown = [d for d in chosen if d not in instances.DOMAINS]
    if unknown:
        sys.exit(f"Unknown VIZ_DOMAINS: {unknown}; "
                 f"available: {sorted(instances.DOMAINS)}")
    return chosen


def run_study(algorithms):
    """Build and run a Lab experiment for *algorithms* = [(name, argv), ...]."""
    script = Path(sys.argv[0]).resolve()
    exp_dir = script.parent
    instances_root = exp_dir / "instances"

    target = int(os.environ.get("VIZ_INSTANCES_PER_DOMAIN", "100"))
    time_limit = int(os.environ.get("VIZ_TIME_LIMIT", "60"))
    memory_mb = int(os.environ.get("VIZ_MEMORY_MB", "3584"))
    processes = int(os.environ.get("VIZ_PROCESSES", "4"))
    domains = _domains()

    if IS_TETRALITH:
        env = project.TetralithEnvironment(
            memory_per_cpu="3G", cpus_per_task=1,
            extra_options="#SBATCH --account="
            + os.environ.get("TETRALITH_ACCOUNT", "naiss2026-4-694"),
        )
    else:
        env = project.LocalEnvironment(processes=processes)

    # Instances live in the experiment directory and are shared by every study
    # there; generation is idempotent so only the first study pays for it.
    instances.generate(instances_root, target, domains=domains)

    exp = Experiment(path=str(exp_dir / "data" / script.stem), environment=env)
    exp.add_resource("run_solver", str(SEARCHLAB / "run-solver.sh"))
    for domain in domains:
        exp.add_resource(f"solver_{domain}",
                         str(REPO / instances.DOMAINS[domain]["solver"]))

    num_runs = 0
    for domain in domains:
        for inst in instances.enumerate_instances(instances_root / domain):
            problem = instances.problem_name(inst)
            for algo_name, alg_argv in algorithms:
                run = exp.add_run()
                run.add_resource("instance", inst["path"], "instance")
                run.add_command(
                    "solve",
                    ["{run_solver}", f"{{solver_{domain}}}", "instance", *alg_argv],
                    time_limit=time_limit, memory_limit=memory_mb,
                )
                run.set_property("domain", domain)
                run.set_property("problem", problem)
                run.set_property("algorithm", algo_name)
                run.set_property("id", [algo_name, domain, problem])
                for k, v in inst["params"].items():
                    run.set_property(f"param_{k}", v)
                run.set_property("limit_time", time_limit)
                run.set_property("limit_memory_mb", memory_mb)
                num_runs += 1

    algo_names = ", ".join(name for name, _ in algorithms)
    print(f"[{script.stem}] {num_runs} runs: {len(domains)} domains x "
          f"{len(algorithms)} algorithms ({algo_names}) x ~{target} instances "
          f"(time_limit={time_limit}s, memory={memory_mb}MB)")

    exp.add_parser(rdb_parser.get_parser())
    exp.add_step("build", exp.build)
    exp.add_step("start", exp.start_runs)
    exp.add_step("parse", exp.parse)
    exp.add_fetcher(name="fetch")
    project.add_absolute_report(exp, attributes=ATTRIBUTES)

    if not project.REMOTE:
        eval_props = Path(exp.eval_dir) / "properties"
        exp.add_step("plots", subprocess.call,
                     [sys.executable, str(exp_dir / "plots.py"), str(eval_props),
                      "-o", str(exp_dir / "plots")])

    exp.run_steps()
