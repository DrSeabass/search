#!/usr/bin/env python3
"""Draw figures from a Downward Lab `properties` file.

This is the visualization half of the study: the experiment script produces
Lab's canonical `properties` file; this script reads it and draws the figures.
Keeping the two separate means we consume the standard Lab artifact rather than
inventing a parallel data format.

Two kinds of figure:

  1. Metric cross-product scatter, one PNG per algorithm. For each pair of the
     metrics {wall time, cost, length, expansions, generated} it scatters one
     against another (lower triangle of the pairs matrix), points colored by
     domain. Log axes are used when a metric is strictly positive. This shows,
     e.g., how runtime correlates with solution length / cost / search effort.

  2. Anytime profiles, one PNG, a subplot per domain. For ARA* it draws each
     instance's improving-incumbent trajectory (solution cost vs wall time) as a
     step line, from the incumbent_* list properties the parser captured.

Usage:
    python plots.py <properties-file-or-eval-dir> -o <output-dir>
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# (attribute, axis label). The metrics we cross-plot.
METRICS = [
    ("solver_wall_time", "wall time (s)"),
    ("cost", "solution cost"),
    ("length", "solution length"),
    ("expansions", "nodes expanded"),
    ("generated", "nodes generated"),
]

ANYTIME_ALGORITHMS = ["arastar"]
MAX_TRAJECTORIES_PER_DOMAIN = 25


def load_properties(paths):
    """Load and merge one or more Lab `properties` files (or -eval dirs).

    Merging several studies' properties lets cross-algorithm figures (e.g. the
    anytime-convergence plot, whose normalizer is the best cost found by *any*
    algorithm on an instance) see every algorithm's runs.
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    merged = {}
    for path in paths:
        path = Path(path)
        if path.is_dir():
            path = path / "properties"
        with open(path) as f:
            merged.update(json.load(f))  # Lab stores {run_id: {props}}
    return list(merged.values())


def _runs_by(runs, key):
    out = {}
    for r in runs:
        out.setdefault(r.get(key), []).append(r)
    return out


def _scale_for(values):
    """'log' if every value is strictly positive (and they span a range)."""
    if values and all(v is not None and v > 0 for v in values):
        return "log"
    return "linear"


def _domain_colors(domains):
    cmap = plt.get_cmap("tab10")
    return {d: cmap(i % 10) for i, d in enumerate(sorted(domains))}


_TRAILING_NUM = re.compile(r"(\d+(?:\.\d+)?)$")


def _weight_of(run):
    """Numeric weight for a run: the 'weight' property if set, else a trailing
    number parsed from the algorithm name (e.g. 'wastar-2' -> 2.0)."""
    w = run.get("weight")
    if isinstance(w, (int, float)):
        return float(w)
    m = _TRAILING_NUM.search(run.get("algorithm", ""))
    return float(m.group(1)) if m else None


def _center_interval(values, logscale, confidence=1.96):
    """Central tendency and 95% CI (center, low, high) for a sample.

    On a log axis we use the geometric mean with the CI computed in log space,
    so the band is multiplicative and always positive -- appropriate for the
    positive, heavy-tailed search metrics here (and the convention the Lab
    reports use for time). On a linear axis we use the arithmetic mean with a
    normal-approximation CI.
    """
    arr = np.asarray(values, dtype=float)
    if logscale:
        log = np.log(arr)
        m = log.mean()
        half = confidence * log.std(ddof=1) / math.sqrt(arr.size) if arr.size > 1 else 0.0
        return math.exp(m), math.exp(m - half), math.exp(m + half)
    m = float(arr.mean())
    half = confidence * arr.std(ddof=1) / math.sqrt(arr.size) if arr.size > 1 else 0.0
    return m, m - half, m + half


def scatter_matrix(runs, algorithm, outdir):
    """Lower-triangle pairs scatter of METRICS for one algorithm's solved runs."""
    solved = [r for r in runs if r.get("coverage") == 1
              and all(r.get(m) is not None for m, _ in METRICS)]
    if len(solved) < 2:
        print(f"  [{algorithm}] too few solved runs ({len(solved)}); skipping scatter")
        return

    domains = sorted({r["domain"] for r in solved})
    colors = _domain_colors(domains)
    n = len(METRICS)
    fig, axes = plt.subplots(n, n, figsize=(3.2 * n, 3.0 * n))

    for i, (yattr, ylabel) in enumerate(METRICS):
        for j, (xattr, xlabel) in enumerate(METRICS):
            ax = axes[i][j]
            if j > i:                      # upper triangle: leave blank
                ax.axis("off")
                continue
            if i == j:                     # diagonal: metric name
                ax.text(0.5, 0.5, ylabel, ha="center", va="center",
                        fontsize=11, fontweight="bold", transform=ax.transAxes)
                ax.set_xticks([]); ax.set_yticks([])
                continue
            for d in domains:
                xs = [r[xattr] for r in solved if r["domain"] == d]
                ys = [r[yattr] for r in solved if r["domain"] == d]
                ax.scatter(xs, ys, s=10, alpha=0.6, color=colors[d], label=d)
            ax.set_xscale(_scale_for([r[xattr] for r in solved]))
            ax.set_yscale(_scale_for([r[yattr] for r in solved]))
            if i == n - 1:
                ax.set_xlabel(xlabel, fontsize=9)
            if j == 0:
                ax.set_ylabel(ylabel, fontsize=9)
            ax.tick_params(labelsize=7)

    handles = [plt.Line2D([], [], marker="o", linestyle="", color=colors[d], label=d)
               for d in domains]
    fig.legend(handles=handles, loc="upper right", title="domain", fontsize=9)
    fig.suptitle(f"{algorithm}: metric cross-product ({len(solved)} solved runs)",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = outdir / f"scatter_{algorithm}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"  wrote {out}")


def anytime_profiles(runs, algorithm, outdir):
    """Per-domain anytime profiles (incumbent cost vs wall time) for one algo."""
    have = [r for r in runs if r.get("algorithm") == algorithm
            and r.get("incumbent_wall_time") and r.get("incumbent_cost")]
    if not have:
        print(f"  [{algorithm}] no incumbent trajectories; skipping anytime profiles")
        return

    by_domain = _runs_by(have, "domain")
    domains = sorted(by_domain)
    ncol = min(3, len(domains))
    nrow = math.ceil(len(domains) / ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(5 * ncol, 3.5 * nrow),
                             squeeze=False)

    for idx, domain in enumerate(domains):
        ax = axes[idx // ncol][idx % ncol]
        for r in by_domain[domain][:MAX_TRAJECTORIES_PER_DOMAIN]:
            t = r["incumbent_wall_time"]
            c = r["incumbent_cost"]
            ax.step(t, c, where="post", alpha=0.4, linewidth=0.8)
        ax.set_title(domain, fontsize=10)
        ax.set_xlabel("wall time (s)", fontsize=8)
        ax.set_ylabel("incumbent cost", fontsize=8)
        if all(min(r["incumbent_wall_time"]) > 0 for r in by_domain[domain]):
            ax.set_xscale("log")
        ax.tick_params(labelsize=7)

    for idx in range(len(domains), nrow * ncol):
        axes[idx // ncol][idx % ncol].axis("off")

    fig.suptitle(f"{algorithm}: anytime profiles (up to "
                 f"{MAX_TRAJECTORIES_PER_DOMAIN} instances/domain)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = outdir / f"anytime_{algorithm}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"  wrote {out}")


def _run_events(run):
    """Sorted (time, cost) events for a run = the solutions it held over time.

    Anytime runs contribute their whole incumbent trajectory; single-shot runs
    contribute one event at their finish time. Returns [] if never solved.
    """
    if run.get("incumbent_cost") and run.get("incumbent_wall_time"):
        ev = list(zip(run["incumbent_wall_time"], run["incumbent_cost"]))
        return sorted(ev)
    if run.get("coverage") == 1 and run.get("cost") is not None \
            and run.get("solver_wall_time") is not None:
        return [(run["solver_wall_time"], run["cost"])]
    return []


def _cost_in_hand(events, t):
    """Cost of the best solution held at time t (None if none yet)."""
    best = None
    for time, cost in events:           # events sorted ascending by time
        if time > t:
            break
        best = cost if best is None else min(best, cost)
    return best


def _run_best_cost(events):
    return min((c for _, c in events), default=None)


def anytime_convergence(runs, outdir):
    """Normalized anytime convergence: quality = best-known / cost-in-hand vs t.

    For each instance the normalizer is the best (lowest) solution cost found by
    *any* algorithm. For each algorithm we plot the mean over instances of
    best_cost / (cost the algorithm holds at time t), so y is in (0, 1] and
    rises toward 1 as the algorithm reaches the best-known solution. One subplot
    per domain, one line per algorithm.
    """
    events = {id(r): _run_events(r) for r in runs}
    best = {}
    for r in runs:
        bc = _run_best_cost(events[id(r)])
        if bc is None:
            continue
        key = (r["domain"], r.get("problem"))
        best[key] = bc if key not in best else min(best[key], bc)
    if not best:
        print("  no solved instances; skipping anytime convergence")
        return

    by_domain = _runs_by([r for r in runs
                          if (r["domain"], r.get("problem")) in best], "domain")
    domains = sorted(by_domain)
    ncol = min(3, len(domains))
    nrow = math.ceil(len(domains) / ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(5 * ncol, 3.6 * nrow),
                             squeeze=False)

    for idx, domain in enumerate(domains):
        ax = axes[idx // ncol][idx % ncol]
        druns = by_domain[domain]
        all_times = [tm for r in druns for tm, _ in events[id(r)] if tm > 0]
        if not all_times:
            ax.axis("off")
            continue
        tgrid = np.logspace(math.log10(min(all_times)),
                            math.log10(max(all_times)), 60)
        for algo, rs in sorted(_runs_by(druns, "algorithm").items()):
            ys = []
            for t in tgrid:
                qs = []
                for r in rs:
                    key = (domain, r["problem"])
                    cih = _cost_in_hand(events[id(r)], t)
                    qs.append(best[key] / cih if cih else 0.0)
                ys.append(np.mean(qs) if qs else np.nan)
            ax.plot(tgrid, ys, label=algo, linewidth=1.3)
        ax.set_xscale("log")
        ax.set_ylim(0, 1.05)
        ax.set_title(domain, fontsize=10)
        ax.set_xlabel("wall time (s)", fontsize=8)
        ax.set_ylabel("quality = best / in-hand", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=6, loc="lower right")

    for idx in range(len(domains), nrow * ncol):
        axes[idx // ncol][idx % ncol].axis("off")

    fig.suptitle("anytime convergence: mean solution quality vs wall time "
                 "(1.0 = best found by any algorithm)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = outdir / "anytime_convergence.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"  wrote {out}")


def weight_trends(runs, outdir):
    """Mean performance vs weight, with 95% CI bands, one line per domain.

    Uses solved runs that carry a numeric weight (the weighted-A* sweep). One
    subplot per metric; x is the weight, y is the per-(domain, weight) mean with
    a shaded 95% confidence interval over the instances solved at that weight.
    """
    solved = [r for r in runs if r.get("coverage") == 1
              and _weight_of(r) is not None]
    weights = sorted({_weight_of(r) for r in solved})
    if len(weights) < 2:
        print("  fewer than 2 weights present; skipping weight trends")
        return

    domains = sorted({r["domain"] for r in solved})
    colors = _domain_colors(domains)
    n = len(METRICS)
    ncol = min(3, n)
    nrow = math.ceil(n / ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(5 * ncol, 3.6 * nrow),
                             squeeze=False)

    for mi, (attr, label) in enumerate(METRICS):
        ax = axes[mi // ncol][mi % ncol]
        # Use a log axis (geometric mean) when every value for this metric is
        # strictly positive, which is the case for all our search metrics.
        logscale = all(r[attr] > 0 for r in solved if r.get(attr) is not None)
        for domain in domains:
            xs, centers, los, his = [], [], [], []
            for w in weights:
                vals = [r[attr] for r in solved
                        if r["domain"] == domain and _weight_of(r) == w
                        and r.get(attr) is not None]
                if not vals:
                    continue
                c, lo, hi = _center_interval(vals, logscale)
                xs.append(w); centers.append(c); los.append(lo); his.append(hi)
            if not xs:
                continue
            ax.plot(xs, centers, marker="o", ms=4, color=colors[domain],
                    label=domain)
            ax.fill_between(xs, los, his, color=colors[domain], alpha=0.18)
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("weight", fontsize=9)
        if logscale:
            ax.set_yscale("log")
        ax.set_xticks(weights)
        ax.tick_params(labelsize=8)

    for idx in range(n, nrow * ncol):
        axes[idx // ncol][idx % ncol].axis("off")

    handles = [plt.Line2D([], [], marker="o", color=colors[d], label=d)
               for d in domains]
    fig.legend(handles=handles, loc="upper right", title="domain", fontsize=9)
    fig.suptitle("weighted A*: performance vs weight "
                 "(geometric mean on log axes, 95% CI; per domain)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = outdir / "weight_trends.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"  wrote {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("properties", nargs="+",
                    help="one or more Lab `properties` files or -eval dirs; "
                         "pass several studies to compare algorithms")
    ap.add_argument("-o", "--outdir", default="plots", help="output directory")
    args = ap.parse_args(argv)

    runs = load_properties(args.properties)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"Loaded {len(runs)} runs; writing figures to {outdir}/")

    by_algo = _runs_by(runs, "algorithm")
    for algorithm in sorted(a for a in by_algo if a is not None):
        scatter_matrix(by_algo[algorithm], algorithm, outdir)

    for algorithm in ANYTIME_ALGORITHMS:
        if algorithm in by_algo:
            anytime_profiles(by_algo[algorithm], algorithm, outdir)

    # Trends over a weight sequence (e.g. the weighted-A* sweep), if present.
    weight_trends(runs, outdir)

    # Normalized anytime convergence across all algorithms present.
    anytime_convergence(runs, outdir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
