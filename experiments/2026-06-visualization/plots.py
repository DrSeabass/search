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
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt  # noqa: E402

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


def load_properties(path):
    """Accept either the properties file or the -eval dir containing it."""
    path = Path(path)
    if path.is_dir():
        path = path / "properties"
    with open(path) as f:
        data = json.load(f)
    # Lab stores {run_id: {props}}.
    return list(data.values())


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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("properties", help="path to the Lab `properties` file or -eval dir")
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
