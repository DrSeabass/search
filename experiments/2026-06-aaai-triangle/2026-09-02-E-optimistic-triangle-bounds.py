#!/usr/bin/env python3
"""Optimistic Triangle vs weighted A* and Aggressive Search.

Sweeps controlled suboptimality bounds, Triangle slopes, and switching
exponents on tiles, gridnav, and pancake. Aggressive Search sweeps the same
values for alpha as Optimistic Triangle uses for k, allowing matched k/alpha
comparisons. Its aggressive weight is 1 + alpha(w - 1).

Local defaults are intentionally small; cluster defaults use ten instances and
30-minute runs. Environment overrides use the COMPLETE_* knobs shared by the
sibling Triangle experiments.

Usage:
  ./2026-09-02-E-optimistic-triangle-bounds.py --all
  ./2026-09-02-E-optimistic-triangle-bounds.py build start parse fetch
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

BOUNDS = [1.05, 1.1, 1.25, 1.5, 1.75, 2, 3, 5]
SLOPES = [1, 50, 100, 1000]
KS = [1, 2, 3, 5]
DOMAINS = ["tiles", "gridnav", "pancake"]

DIR = Path(__file__).resolve().parent
REPO = DIR.parents[1]
SEARCHLAB = Path(instances.__file__).resolve().parent
INSTANCES_ROOT = DIR / "instances"
NODE = platform.node()
IS_TETRALITH = bool(re.match(r"tetralith\d+\.nsc\.liu\.se|n\d+", NODE))
NAISS_ACCOUNT = os.environ.get("TETRALITH_ACCOUNT", "naiss2026-4-694")

if IS_TETRALITH:
    INSTANCES_PER_DOMAIN = int(os.environ.get("COMPLETE_INSTANCES_PER_DOMAIN", "10"))
    TIME_LIMIT = int(os.environ.get("COMPLETE_TIME_LIMIT", "1800"))
    MEMORY_MB = int(os.environ.get("COMPLETE_MEMORY_MB", "8192"))
else:
    INSTANCES_PER_DOMAIN = int(os.environ.get("COMPLETE_INSTANCES_PER_DOMAIN", "3"))
    TIME_LIMIT = int(os.environ.get("COMPLETE_TIME_LIMIT", "60"))
    MEMORY_MB = int(os.environ.get("COMPLETE_MEMORY_MB", "4096"))

LOCAL_PROCESSES = int(os.environ.get("COMPLETE_PROCESSES", "4"))
MAX_SIZES = int(os.environ.get("COMPLETE_MAX_SIZES", "1"))
# Lab's Tetralith default permits up to 2000 array tasks. This experiment has
# thousands of short, independent runs, so that default would submit an
# unnecessarily large array. Group runs sequentially into at most this many
# tasks instead (5040 runs -> 252 tasks at the default 256-task cap).
SLURM_MAX_TASKS = int(os.environ.get("COMPLETE_SLURM_TASKS", "256"))


def token(value):
    return str(value).replace(".", "_")


# (name, argv, family, w, slope, k, alpha)
ALGORITHMS = []
for w in BOUNDS:
    for slope in SLOPES:
        for k in KS:
            ALGORITHMS.append((
                f"ot-w{token(w)}-s{slope}-k{k}",
                ["optimistic_triangle", "-w", str(w), "-slope", str(slope),
                 "-k", str(k)],
                "optimistic_triangle", w, slope, k, None,
            ))
    ALGORITHMS.append((
        f"wastar-w{token(w)}", ["wastar", "-wt", str(w)],
        "wastar", w, None, None, None,
    ))
    for alpha in KS:
        ALGORITHMS.append((
            f"aggressive-w{token(w)}-a{alpha}",
            ["aggressive", "-w", str(w), "-alpha", str(alpha)],
            "aggressive", w, None, None, alpha,
        ))

assert len(ALGORITHMS) == 168


def with_limits(argv):
    return [*argv, "-walltime", str(TIME_LIMIT), "-mem", f"{MEMORY_MB}M"]


if IS_TETRALITH:
    if SLURM_MAX_TASKS < 1:
        sys.exit("COMPLETE_SLURM_TASKS must be >= 1")

    class CompactTetralithEnvironment(project.TetralithEnvironment):
        MAX_TASKS = SLURM_MAX_TASKS

    ENV = CompactTetralithEnvironment(
        memory_per_cpu=f"{MEMORY_MB // 1024 + 1}G",
        cpus_per_task=1,
        extra_options=f"#SBATCH --account={NAISS_ACCOUNT}",
    )
else:
    ENV = project.LocalEnvironment(processes=LOCAL_PROCESSES)

instances.generate(INSTANCES_ROOT, INSTANCES_PER_DOMAIN, domains=DOMAINS,
                   max_sizes=MAX_SIZES)

exp = Experiment(environment=ENV)
exp.add_resource("run_solver", str(SEARCHLAB / "run-solver.sh"))
for domain in DOMAINS:
    exp.add_resource(f"solver_{domain}", str(REPO / instances.DOMAINS[domain]["solver"]))

num_runs = 0
num_instances = 0
for domain in DOMAINS:
    domain_instances = list(instances.enumerate_instances(INSTANCES_ROOT / domain))
    # The shared instance directory may contain more files from earlier
    # studies. Keep this experiment's requested per-domain scope exact.
    for inst in domain_instances[:INSTANCES_PER_DOMAIN]:
        num_instances += 1
        problem = instances.problem_name(inst)
        for name, argv, family, w, slope, k, alpha in ALGORITHMS:
            run = exp.add_run()
            run.add_resource("instance", inst["path"], "instance")
            run.add_command(
                "solve",
                ["{run_solver}", f"{{solver_{domain}}}", "instance",
                 *with_limits(argv)],
                time_limit=TIME_LIMIT,
                memory_limit=MEMORY_MB,
            )
            run.set_property("id", [name, domain, problem])
            run.set_property("algorithm", name)
            run.set_property("algorithm_family", family)
            run.set_property("domain", domain)
            run.set_property("problem", problem)
            run.set_property("suboptimality_bound", w)
            if slope is not None:
                run.set_property("slope", slope)
            if k is not None:
                run.set_property("switch_k", k)
            if alpha is not None:
                run.set_property("aggressive_alpha", alpha)
            for key, value in inst["params"].items():
                run.set_property(f"param_{key}", value)
            run.set_property("limit_time", TIME_LIMIT)
            run.set_property("limit_memory_mb", MEMORY_MB)
            num_runs += 1

print(f"[optimistic-triangle-bounds] {num_runs} runs: {len(DOMAINS)} domains "
      f"x {len(ALGORITHMS)} configs x {num_instances} total instances "
      f"(time={TIME_LIMIT}s, memory={MEMORY_MB}MB)")


def parse_bound_certificate(content, props):
    props["proved_within_bound"] = int(bool(
        re.search(r'"proved within bound"\s+"yes"', content)))


parser = rdb_parser.get_parser()
parser.add_function(parse_bound_certificate, file="run.log")
exp.add_parser(parser)

exp.add_step("build", exp.build)
exp.add_step("start", exp.start_runs)
exp.add_step("parse", exp.parse)
exp.add_fetcher(name="fetch")

ATTRIBUTES = [
    "error", "coverage", "algorithm_family", "suboptimality_bound",
    "slope", "switch_k", "aggressive_alpha", "cost", "proved_within_bound",
    Attribute("expansions", function=arithmetic_mean, min_wins=True),
    Attribute("generated", function=arithmetic_mean, min_wins=True),
    "length", "reopened",
    Attribute("solver_wall_time", function=geometric_mean, min_wins=True, digits=4),
    "solver_max_vmem_kb", "incumbent_cost", "incumbent_wall_time",
    "incumbent_expansions",
]
project.add_absolute_report(exp, attributes=ATTRIBUTES)

# Direct baseline comparisons for every bound and every optimistic setting.
pairs = []
for w in BOUNDS:
    wa = f"wastar-w{token(w)}"
    for slope in SLOPES:
        for k in KS:
            ot = f"ot-w{token(w)}-s{slope}-k{k}"
            ag = f"aggressive-w{token(w)}-a{k}"
            pairs.extend([(wa, ot), (ag, ot)])
project.add_scatter_plot_reports(exp, pairs, ["expansions", "cost"])

exp.run_steps()
