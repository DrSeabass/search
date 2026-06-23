#!/usr/bin/env python3
"""Performance regression for the depth-striated beam family (triangle/rectangle).

The sibling [`run_regression.py`](run_regression.py) pins *behavior* (node
counts, cost) and deliberately ignores time. This script measures *throughput* —
expansions per second — which is exactly what an implementation-tightening change
should improve without changing behavior.

Wall-clock numbers are machine dependent, so the committed baseline stores a
machine-independent **ratio**: each probe's exp/sec divided by a reference
algorithm's exp/sec on the *same* instance (both run on the same CPU, so the
ratio cancels machine speed). A probe regresses when its ratio drops materially
below the blessed value.

Method: each probe runs on one fixed-seed, deliberately-hard instance with an
expansion cap (`-expd`) so the algorithm does a fixed, large amount of work
without solving (which would make the timing depend on solution difficulty
rather than per-node cost). Each probe is timed `REPEATS` times and the *minimum*
wall time is used (least affected by scheduling noise). Memory/time guards are
always passed so a pathological run cannot wedge the machine.

Usage:
    python3 regression/perf.py                 # measure + check vs perf_golden.json
    python3 regression/perf.py --update        # re-bless the ratio baseline
    python3 regression/perf.py --verbose        # print exp/sec for every probe
    python3 regression/perf.py --tolerance 0.30 # allowed relative ratio drop

Exit 0 if all ratios are within tolerance (or on --update), 1 on a regression,
2 on a setup error.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "perf_golden.json"

sys.path.insert(0, str(REPO / "utils"))
from rdb_to_json import _parse_rdb  # noqa: E402

REPEATS = 3
# Generous guards: these only fire if something has gone badly wrong; the
# expansion cap is what bounds normal runs.
WALLTIME_GUARD = "120"
MEM_GUARD = "4000M"


def _run(argv, stdin_path=None):
    argv = [str(a) for a in argv]
    fin = open(stdin_path, "rb") if stdin_path else subprocess.DEVNULL
    try:
        proc = subprocess.run(argv, cwd=REPO, stdin=fin,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=int(WALLTIME_GUARD) + 30)
    finally:
        if stdin_path:
            fin.close()
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace") if proc.stderr else ""
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(argv)}\n{err}")
    return proc.stdout.decode("utf-8", "replace")


# --- Hard instances sized so the capped run never solves early ---------------

def gen_gridnav_hard(workdir, seed):
    # mkseedinst and randinst both write to stdout.
    grid = workdir / "g.grid"
    grid.write_text(_run([REPO / "gridnav/mkseedinst", "-seed", str(seed),
                          "-width", "2000", "-height", "2000", "-prob", "0.35",
                          "-eightway"]))
    inst = workdir / "g.inst"
    inst.write_text(_run([REPO / "gridnav/randinst", "-s", str(seed), "-m", str(grid)]))
    return inst


def gen_pancake_hard(workdir, seed):
    d = workdir / "pan"
    _run([sys.executable, REPO / "pancake/make_instances.py", "--seed", str(seed),
          "--ncakes", "50", "--count", "1", "--out-dir", str(d)])
    return d / "1"


# --- Probe matrix -------------------------------------------------------------
# Each probe: (domain, solver, gen, seed, reference?, alg_argv, expd_cap).
# `ref` marks the per-domain reference algorithm the ratio is taken against.
# Caps are chosen so each probe runs in roughly 0.1-3s at current throughput.

PROBES = [
    # gridnav: cheap successors, so open-list overhead dominates -> the cleanest
    # signal for the open-list implementation.
    ("gridnav", "gridnav/gridnav_solver", gen_gridnav_hard, 3, True,
     "beam", ["beam", "-width", "1000"], 300000),
    ("gridnav", "gridnav/gridnav_solver", gen_gridnav_hard, 3, False,
     "triangle_s8", ["triangle", "-slope", "8"], 300000),
    ("gridnav", "gridnav/gridnav_solver", gen_gridnav_hard, 3, False,
     "rectangle_w10", ["rectangle", "-width", "10", "-aspect", "5"], 300000),
    ("gridnav", "gridnav/gridnav_solver", gen_gridnav_hard, 3, False,
     "rectangle_w100", ["rectangle", "-width", "100", "-aspect", "5"], 300000),
    # pancake: high branching (b=49) -> exposes any per-successor open-list cost.
    ("pancake", "pancake/50pancake_solver", gen_pancake_hard, 7, True,
     "beam", ["beam", "-width", "100"], 50000),
    ("pancake", "pancake/50pancake_solver", gen_pancake_hard, 7, False,
     "rectangle_w30", ["rectangle", "-width", "30", "-aspect", "5"], 5000),
]


def measure(solver, alg_argv, expd, instance):
    """Run the probe REPEATS times; return (expansions, best_exp_per_sec)."""
    best_eps, expd_seen = 0.0, None
    argv = [REPO / solver] + alg_argv + ["-expd", str(expd),
            "-walltime", WALLTIME_GUARD, "-mem", MEM_GUARD]
    for _ in range(REPEATS):
        parsed = _parse_rdb(_run(argv, stdin_path=instance).splitlines())
        exp = parsed.get("total nodes expanded")
        wall = parsed.get("total wall time")
        if not exp or not wall or wall <= 0:
            continue
        expd_seen = exp
        best_eps = max(best_eps, exp / wall)
    return expd_seen, best_eps


def run_all(verbose=False):
    """Return {probe_name: {expansions, exp_per_sec, ratio}} keyed by 'domain :: name'."""
    results = {}
    refs = {}  # domain -> reference exp/sec
    with tempfile.TemporaryDirectory(prefix="search-perf-") as tmp:
        workroot = Path(tmp)
        gen_cache = {}
        for dom, solver, gen, seed, is_ref, name, argv, expd in PROBES:
            if not (REPO / solver).exists():
                raise RuntimeError(f"missing solver: {solver} (run `make everything`)")
            key = (gen, seed)
            if key not in gen_cache:
                wd = workroot / f"{dom}_{seed}"
                wd.mkdir(parents=True, exist_ok=True)
                gen_cache[key] = gen(wd, seed)
            exp, eps = measure(solver, argv, expd, gen_cache[key])
            results[f"{dom} :: {name}"] = {"expansions": exp, "exp_per_sec": eps,
                                           "domain": dom, "is_ref": is_ref}
            if is_ref:
                refs[dom] = eps
            if verbose:
                print(f"  {dom} :: {name:<16} exp={exp} exp/s={eps:,.0f}")
    # Fill in ratios now that references are known.
    for name, r in results.items():
        ref = refs.get(r["domain"])
        r["ratio"] = (r["exp_per_sec"] / ref) if ref else None
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="re-bless perf_golden.json")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--tolerance", type=float, default=0.30,
                    help="allowed fractional drop in ratio vs golden (default 0.30)")
    args = ap.parse_args(argv)

    try:
        results = run_all(verbose=args.verbose)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Persisted form: just the machine-independent ratio per probe.
    ratios = {k: round(v["ratio"], 4) for k, v in results.items() if v["ratio"] is not None}

    print("\nThroughput (exp/sec) and ratio vs per-domain reference:")
    for k, v in results.items():
        tag = "  [ref]" if v["is_ref"] else ""
        rat = f"{v['ratio']:.3f}" if v["ratio"] is not None else "n/a"
        print(f"  {k:<26} {v['exp_per_sec']:>12,.0f}  ratio={rat}{tag}")

    if args.update:
        GOLDEN.write_text(json.dumps(ratios, indent=2, sort_keys=True) + "\n")
        print(f"\nUpdated {GOLDEN} ({len(ratios)} ratio(s) blessed).")
        return 0

    if not GOLDEN.exists():
        print(f"\nERROR: {GOLDEN} missing; run with --update to create it.", file=sys.stderr)
        return 2

    golden = json.loads(GOLDEN.read_text())
    regressions = []
    for k, ratio in ratios.items():
        g = golden.get(k)
        if g is None:
            continue
        if ratio < g * (1.0 - args.tolerance):
            regressions.append((k, g, ratio))

    if not regressions:
        print(f"\nOK: {len(ratios)} probe(s) within {args.tolerance:.0%} of baseline.")
        return 0
    print(f"\nPERF REGRESSION: {len(regressions)} probe(s) slower than baseline:", file=sys.stderr)
    for k, g, r in regressions:
        print(f"  {k}: golden ratio={g:.3f} now={r:.3f} "
              f"({(1 - r / g):.0%} slower)", file=sys.stderr)
    print("\nIf intentional, re-bless with: python3 regression/perf.py --update", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
