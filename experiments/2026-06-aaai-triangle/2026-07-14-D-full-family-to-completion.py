#!/usr/bin/env python3
"""Full Triangle/Rectangle family, run to completion -- search-suite port of the
AAAI27 planning experiment.

This is the classic-heuristic-search analogue of the Scorpion planning script
  experiments/aaai27/2026-07-10-A-bsor-rrr-rrdex-wastar.py
ported onto THIS repo's domains and Lab infrastructure (searchlab: the stdin
shim, the RDB parser, instance generation). The planning script sweeps a
bounded-suboptimal rectangle roster over a suboptimality-weight schedule at
aspects {primary=500, secondary=1}; the search suite has no w-bound (rectangle
here is anytime, not bounded-suboptimal), so the sweep dimension collapses to a
fixed head-to-head roster: the same two aspects {1, 500}, the static Triangle at
its best static slope, the three parameterless self-configuring variants, and
the A*/ANA* references. Everything runs anytime, to completion, the same
protocol as the sibling studies B (base configs) and C (enhanced variants).

Roster (edit ALGORITHMS / the ASPECTS / SLOPE knobs to adjust):
  ana        -anytime -- ANA* (Anytime Nonparametric A*); the parameterless
                        anytime baseline / foil
  triangle   -slope 50 -anytime          -- static Triangle (best static slope,
                                            ICAPS'23 HSDIP)
  rectangle  -aspect 1 -anytime          -- wide/square rectangle (ar = 1)
  rectangle  -aspect 500 -anytime        -- deep rectangle (ar = 500, primary)
  ratchet_triangle    -anytime           -- self-configuring slope (doubling ratchet)
  adaptive_triangle   -anytime -penalty 0 -- self-configuring dive (parameterless)
  adaptive_rectangle  -anytime           -- self-configuring aspect (best-first-chain
                                            ratchet), the width->AR generalization

Turning domains on/off: edit the DOMAIN_ENABLED block below -- flip a value to
False to drop that domain. (The COMPLETE_DOMAINS env var still overrides for
scripted/cluster runs.) Shares the COMPLETE_* scope knobs with studies B and C
so all three are a fair comparison on the same instances and budget.

Usage:
  ./2026-07-14-D-full-family-to-completion.py --all
  ./2026-07-14-D-full-family-to-completion.py build start parse fetch
  COMPLETE_DOMAINS=tiles,pancake ./2026-07-14-D-full-family-to-completion.py build start
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

# ============================================================================
# DOMAINS -- THE knob to edit. Flip True/False to include/exclude a domain.
# All entries must be keys of instances.DOMAINS (their solver must be built:
# `make everything`). The COMPLETE_DOMAINS env var, if set, overrides this block
# entirely (comma-separated, e.g. COMPLETE_DOMAINS=tiles,pancake).
# ============================================================================
DOMAIN_ENABLED = {
    "tiles":       True,
    "pancake":     True,
    "blocksworld": True,
    "gridnav":     True,
    "vacuum":      True,
    "drobot":      False,
    "traffic":     False,
    "synth_tree":  False,
}

# ============================================================================
# Roster knobs. ASPECTS mirrors the planning script's {primary 500, secondary 1};
# SLOPE is the static Triangle slope (best static slope from the ICAPS'23 HSDIP
# paper). The parameterless variants take no shape parameter by design.
# ============================================================================
ASPECTS = [1, 500]   # rectangle static-aspect roster (ar = {1, 500})
SLOPE = 50           # triangle static slope

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
# Scope -- shares the COMPLETE_* knobs with studies B and C so the three are a
# fair comparison on the same instances and budget.
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
# max instance sizes per domain (1 == only the easiest size, as B/C use).
MAX_SIZES = int(os.environ.get("COMPLETE_MAX_SIZES", "1"))


# ----------------------------------------------------------------------------
# Resolve the active domain set: env override, else the DOMAIN_ENABLED block.
# ----------------------------------------------------------------------------
def _resolve_domains():
    unknown = [d for d in DOMAIN_ENABLED if d not in instances.DOMAINS]
    if unknown:
        sys.exit(f"DOMAIN_ENABLED has unknown domains: {unknown}; "
                 f"available: {sorted(instances.DOMAINS)}")
    env = os.environ.get("COMPLETE_DOMAINS")
    if env:
        chosen = [d.strip() for d in env.split(",") if d.strip()]
        bad = [d for d in chosen if d not in instances.DOMAINS]
        if bad:
            sys.exit(f"Unknown COMPLETE_DOMAINS: {bad}; "
                     f"available: {sorted(instances.DOMAINS)}")
        return chosen
    return [d for d, on in DOMAIN_ENABLED.items() if on]


DOMAINS = _resolve_domains()
if not DOMAINS:
    sys.exit("No domains enabled: flip one to True in DOMAIN_ENABLED "
             "or set COMPLETE_DOMAINS.")

# ----------------------------------------------------------------------------
# Algorithm basket. Each entry: (lab algorithm name, solver argv before limits).
# Limits (-walltime/-mem) are appended uniformly below. Built from the ASPECTS /
# SLOPE knobs so the roster tracks those in one place.
# ----------------------------------------------------------------------------
ALGORITHMS = [
    # ANA* (van den Berg et al. 2011): Anytime Nonparametric A*, the
    # parameterless anytime baseline / foil.
    ("ana", ["ana", "-anytime"]),
    (f"tri_s{SLOPE}", ["triangle", "-anytime", "-slope", str(SLOPE)]),
]
for a in ASPECTS:
    ALGORITHMS.append((f"rect_a{a}", ["rectangle", "-anytime", "-aspect", str(a)]))
ALGORITHMS += [
    ("ratchet_triangle", ["ratchet_triangle", "-anytime"]),
    ("adaptive_triangle", ["adaptive_triangle", "-anytime", "-penalty", "0"]),
    ("adaptive_rectangle", ["adaptive_rectangle", "-anytime"]),
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
# Instances (idempotent; shared with studies B/C), then enumerate.
# ----------------------------------------------------------------------------
instances.generate(INSTANCES_ROOT, INSTANCES_PER_DOMAIN, domains=DOMAINS,
                   max_sizes=MAX_SIZES)

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

print(f"[full-family-to-completion] {num_runs} runs: {len(DOMAINS)} domains "
      f"({', '.join(DOMAINS)}) x {len(ALGORITHMS)} algorithms x "
      f"{INSTANCES_PER_DOMAIN} instances "
      f"(time_limit={TIME_LIMIT}s, memory={MEMORY_MB}MB)")


# An anytime run that exhausts its open list before any time/memory limit
# reports `converged: yes`; with an incumbent in hand that proves it optimal.
# The Triangle/Rectangle variants and ANA* all emit this datafile pair.
def parse_proved_optimal(content, props):
    props["proved_optimal"] = int(bool(
        re.search(r'"converged"\s+"yes"', content)))


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

# Scatter plots: the ANA* baseline vs the family on search effort and solution
# quality.
ALGO_NAMES = [name for name, _ in ALGORITHMS]
if "ana" in ALGO_NAMES:
    focus = [f"rect_a{ASPECTS[0]}", f"rect_a{ASPECTS[-1]}", f"tri_s{SLOPE}",
             "adaptive_rectangle"]
    pairs = [("ana", o) for o in focus if o in ALGO_NAMES]
    project.add_scatter_plot_reports(exp, pairs, ["expansions", "cost"])

exp.run_steps()
