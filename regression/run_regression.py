#!/usr/bin/env python3
"""Performance-regression baseline for the search suite.

This is the *fast, self-contained* layer (no external deps beyond the standard
library and the in-repo RDB parser). For each domain in the working set it:

  1. generates one small instance from a fixed seed,
  2. runs a handful of standard algorithms (A*, wA*, greedy, speedy, ...) on it,
  3. parses the solver's RDB output, and
  4. compares a stable subset of metrics against committed golden numbers.

Only *deterministic* metrics are asserted: solution cost, nodes expanded, nodes
generated, solution length. Wall/CPU time is intentionally NOT compared -- it is
machine dependent and would make the check flaky. A mismatch here means a code
change altered search *behavior*; that is exactly what we want a regression
baseline to catch.

Usage:
    python3 regression/run_regression.py            # check against golden.json
    python3 regression/run_regression.py --update   # re-bless golden.json
    python3 regression/run_regression.py --only tiles gridnav
    python3 regression/run_regression.py --verbose   # print every run's metrics

Exit status is 0 when all runs match the golden file, 1 on any mismatch or
failure, 2 on a usage/setup error. See regression/README.md for the rationale
and for how this relates to the Downward Lab study in experiments/.
"""

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden.json"

# Reuse the suite's own RDB parser rather than re-implementing it.
sys.path.insert(0, str(REPO / "utils"))
from rdb_to_json import _parse_rdb  # noqa: E402

# Metrics we assert on. All are deterministic for a fixed binary + instance.
STABLE_METRICS = [
    "final sol cost",
    "total nodes expanded",
    "total nodes generated",
    "final sol length",
]

# Per-run timeout. Every configuration below is sub-second on a laptop; this is
# only a guard against a regression that turns a fast run into a hang.
RUN_TIMEOUT_SEC = 60


def _run(argv, stdout_path=None, stdin_path=None, cwd=REPO):
    """Run a command, raising RuntimeError with context on failure.

    Returns captured stdout bytes when stdout_path is None, else writes stdout
    to that file and returns None.
    """
    argv = [str(a) for a in argv]
    fin = open(stdin_path, "rb") if stdin_path else subprocess.DEVNULL
    fout = open(stdout_path, "wb") if stdout_path else subprocess.PIPE
    try:
        proc = subprocess.run(
            argv, cwd=cwd, stdin=fin, stdout=fout,
            stderr=subprocess.PIPE, timeout=RUN_TIMEOUT_SEC,
        )
    finally:
        if stdin_path:
            fin.close()
        if stdout_path:
            fout.close()
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace") if proc.stderr else ""
        raise RuntimeError(
            f"command failed ({proc.returncode}): {shlex.join(argv)}\n{err}")
    return proc.stdout if stdout_path is None else None


# --- Per-domain instance generators ------------------------------------------
# Each returns the path to a single generated instance file. The quirks of each
# domain's generator live here (binary vs python script, stdout vs file vs dir,
# seed flag naming) so the rest of the driver stays uniform.

def gen_tiles(workdir, seed):
    d = workdir / "tiles"
    d.mkdir(parents=True, exist_ok=True)
    _run([REPO / "tiles/generator", "-w", "4", "-h", "4", "-n", "1",
          "-d", str(d), "-seed", str(seed)])
    return d / "0"


def gen_gridnav(workdir, seed):
    grid = workdir / "g.grid"
    _run([REPO / "gridnav/mkseedinst", "-seed", str(seed),
          "-width", "80", "-height", "25", "-prob", "0.1"], stdout_path=grid)
    inst = workdir / "g.inst"
    _run([REPO / "gridnav/randinst", "-s", str(seed), "-m", str(grid)],
         stdout_path=inst)
    return inst


def gen_vacuum(workdir, seed):
    d = workdir / "vac"
    _run([sys.executable, REPO / "vacuum/make_instances.py",
          "--height", "10", "--width", "15", "--p-blocked", "0.2",
          "--dirts", "5", "--chargers", "0",  # chargers > 0 stalls the solver
          "--seed", str(seed), "--count", "1", "--out-dir", str(d)])
    return d / "1"


def gen_drobot(workdir, seed):
    f = workdir / "dr.txt"
    _run([sys.executable, REPO / "drobot/make_instances.py",
          "--nlocs", "5", "--piles-per-loc", "2", "--cranes-per-loc", "1",
          "--ncontainers", "6", "--seed", str(seed), "-o", str(f)])
    return f


def gen_synth_tree(workdir, seed):
    d = workdir / "st"
    _run([sys.executable, REPO / "synth_tree/make_instances.py",
          "--count", "1", "--seed", str(seed), "--out-dir", str(d)])
    return d / "1"


def gen_traffic(workdir, seed):
    f = workdir / "tr.inst"
    _run([REPO / "traffic/randinst", "5", "5", "1", str(seed)], stdout_path=f)
    return f


def gen_pancake(workdir, seed):
    d = workdir / "pan"
    _run([sys.executable, REPO / "pancake/make_instances.py",
          "--seed", str(seed), "--ncakes", "50", "--count", "1",
          "--out-dir", str(d)])
    return d / "1"


def gen_blocksworld(workdir, seed):
    f = workdir / "bw.txt"
    _run([sys.executable, REPO / "blocksworld/make_instances.py",
          "-b", "10", "-ss", "3", "-sg", "3", "--seed", str(seed), "-f", str(f)])
    return f


# --- The regression matrix ----------------------------------------------------
# Working domains only (blocksworld/segments/visnav/plat2d are excluded; see
# TODO.md and regression/README.md). Algorithms are chosen to be fast and to
# exercise the standard baskets: A*, weighted A*, greedy, speedy.

DOMAINS = [
    {
        "name": "tiles", "solver": "tiles/15md_solver", "gen": gen_tiles, "seed": 1,
        # A* on a random 4x4 is ~5M expansions; use the satisficing baskets here.
        "algs": [["greedy"], ["speedy"], ["wastar", "-wt", "3"]],
    },
    {
        "name": "gridnav", "solver": "gridnav/gridnav_solver", "gen": gen_gridnav, "seed": 42,
        "algs": [["astar"], ["greedy"], ["wastar", "-wt", "2"]],
    },
    {
        "name": "vacuum", "solver": "vacuum/vacuum_solver", "gen": gen_vacuum, "seed": 42,
        "algs": [["astar"], ["greedy"]],
    },
    {
        "name": "drobot", "solver": "drobot/drobot_solver", "gen": gen_drobot, "seed": 42,
        "algs": [["astar"], ["greedy"]],
    },
    {
        "name": "synth_tree", "solver": "synth_tree/synth_tree_solver", "gen": gen_synth_tree, "seed": 42,
        "algs": [["astar"], ["greedy"]],
    },
    {
        "name": "traffic", "solver": "traffic/traffic_solver", "gen": gen_traffic, "seed": 0,
        "algs": [["astar"], ["greedy"]],
    },
    {
        "name": "pancake", "solver": "pancake/50pancake_solver", "gen": gen_pancake, "seed": 7,
        # A* on 50 cakes is heavy; greedy/wA* are the standard satisficing runs.
        "algs": [["greedy"], ["wastar", "-wt", "3"]],
    },
    {
        "name": "blocksworld", "solver": "blocksworld/20bw_solver", "gen": gen_blocksworld, "seed": 42,
        "algs": [["astar"], ["greedy"], ["wastar", "-wt", "2"]],
    },
]


def solve(solver, alg_argv, instance):
    """Run one solver invocation, return the stable metric subset."""
    out = _run([REPO / solver] + alg_argv, stdin_path=instance)
    parsed = _parse_rdb(out.decode("utf-8", "replace").splitlines())
    return {k: parsed.get(k) for k in STABLE_METRICS}


def run_all(only=None, verbose=False):
    """Execute the matrix. Returns {run_key: metrics}."""
    results = {}
    with tempfile.TemporaryDirectory(prefix="search-regression-") as tmp:
        workroot = Path(tmp)
        for dom in DOMAINS:
            if only and dom["name"] not in only:
                continue
            solver_path = REPO / dom["solver"]
            if not solver_path.exists():
                raise RuntimeError(
                    f"missing solver binary: {dom['solver']} (run `make everything`)")
            wd = workroot / dom["name"]
            wd.mkdir(parents=True, exist_ok=True)
            instance = dom["gen"](wd, dom["seed"])
            for alg in dom["algs"]:
                key = f"{dom['name']} :: {' '.join(alg)}"
                metrics = solve(dom["solver"], alg, instance)
                results[key] = metrics
                if verbose:
                    print(f"  {key:<32} {metrics}")
    return results


def compare(results, golden):
    """Return list of (key, field, expected, actual) mismatches."""
    mismatches = []
    for key, metrics in results.items():
        if key not in golden:
            mismatches.append((key, "<entire run>", "(absent from golden)", metrics))
            continue
        for field in STABLE_METRICS:
            exp, act = golden[key].get(field), metrics.get(field)
            if exp != act:
                mismatches.append((key, field, exp, act))
    for key in golden:
        if key not in results:
            mismatches.append((key, "<entire run>", golden[key], "(not produced)"))
    return mismatches


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true",
                    help="re-bless golden.json from this run instead of checking")
    ap.add_argument("--only", nargs="+", metavar="DOMAIN",
                    help="restrict to the named domains")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="print metrics for every run")
    args = ap.parse_args(argv)

    try:
        results = run_all(only=args.only, verbose=args.verbose)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.update:
        # Preserve entries for domains not exercised this run (e.g. --only).
        existing = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
        existing.update(results)
        GOLDEN.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")
        print(f"Updated {GOLDEN} ({len(results)} run(s) blessed).")
        return 0

    if not GOLDEN.exists():
        print(f"ERROR: {GOLDEN} does not exist. Run with --update to create it.",
              file=sys.stderr)
        return 2

    golden = json.loads(GOLDEN.read_text())
    if args.only:
        golden = {k: v for k, v in golden.items()
                  if k.split(" :: ", 1)[0] in args.only}
    mismatches = compare(results, golden)

    if not mismatches:
        print(f"OK: {len(results)} run(s) match golden baseline.")
        return 0

    print(f"REGRESSION: {len(mismatches)} mismatch(es):", file=sys.stderr)
    for key, field, exp, act in mismatches:
        print(f"  {key}\n    {field}: golden={exp!r} actual={act!r}", file=sys.stderr)
    print("\nIf this change is intentional, re-bless with: "
          "python3 regression/run_regression.py --update", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
