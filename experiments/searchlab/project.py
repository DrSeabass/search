"""Framework-agnostic Lab helpers for the search-suite baseline experiment.

This is a trimmed version of the `project.py` used by the Fast Downward /
Scorpion experiments. It keeps only the parts that do not depend on the
`downward` package's PDDL/translate machinery: the cluster-aware environments,
report helpers, and a couple of filesystem utilities. The search suite has no
translate/preprocess pipeline, so we drive the generic `lab.experiment`
layer (Experiment + Run) rather than FastDownwardExperiment.

The AbsoluteReport / ScatterPlotReport classes themselves come from the
`downward.reports` package, which is happy to work on any runs that set the
`domain`, `problem`, and `algorithm` properties -- which our experiment does.
"""

import contextlib
import subprocess
import sys
import tarfile
from pathlib import Path

from downward.reports.absolute import AbsoluteReport
from downward.reports.compare import ComparativeReport
from downward.reports.scatter import ScatterPlotReport
from lab import tools
from lab.environments import (
    BaselSlurmEnvironment,
    LocalEnvironment,
    TetralithEnvironment,
)
from lab.experiment import ARGPARSER

# Re-exported so experiment scripts can subclass them as project.<Env>.
assert BaselSlurmEnvironment and LocalEnvironment and TetralithEnvironment

SCRIPT = Path(sys.argv[0]).resolve()

# True when running on a known cluster: suppress interactive report-opening etc.
REMOTE = BaselSlurmEnvironment.is_present() or TetralithEnvironment.is_present()


def parse_args():
    ARGPARSER.add_argument("--tex", action="store_true", help="produce LaTeX output")
    ARGPARSER.add_argument(
        "--relative", action="store_true", help="make relative scatter plots"
    )
    args, _ = ARGPARSER.parse_known_args()
    return args


ARGS = parse_args()
TEX = ARGS.tex
RELATIVE = ARGS.relative


def get_repo_base() -> Path:
    """Return the repository root (nearest ancestor containing .git)."""
    path = SCRIPT
    while path.parent != path:
        if (path / ".git").is_dir():
            return path
        path = path.parent
    sys.exit("repo base could not be found")


def remove_file(path: Path):
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def add_scp_step(exp, login, remote_exp_dir, name="scp-eval-dir"):
    """Pull a remote experiment's -eval dir back to the local machine."""
    exp.add_step(
        name,
        subprocess.call,
        ["rsync", "-Pavz", f"{login}:{remote_exp_dir}-eval/", f"{exp.path}-eval/"],
    )


def add_compress_exp_dir_step(exp):
    def compress_exp_dir():
        tar_file_path = Path(exp.path).parent / f"{exp.name}.tar.xz"
        exp_dir_path = Path(exp.path)
        with tarfile.open(tar_file_path, mode="w:xz", dereference=True) as tar:
            for file in exp_dir_path.rglob("*"):
                relpath = file.relative_to(exp_dir_path.parent)
                tar.add(file, arcname=relpath)
        import shutil

        shutil.rmtree(exp_dir_path)

    exp.add_step("compress-exp-dir", compress_exp_dir)


def add_absolute_report(exp, *, name=None, outfile=None, **kwargs):
    report = AbsoluteReport(**kwargs)
    if name and not outfile:
        outfile = f"{name}.{report.output_format}"
    elif outfile and not name:
        name = Path(outfile).name
    elif not name and not outfile:
        name = f"{exp.name}-abs"
        outfile = f"{name}.{report.output_format}"

    if not Path(outfile).is_absolute():
        outfile = Path(exp.eval_dir) / outfile

    exp.add_report(report, name=name, outfile=outfile)
    if not REMOTE:
        exp.add_step(f"open-{name}", subprocess.call, ["xdg-open", outfile])


def add_comparative_report(exp, algorithm_pairs, *, name=None, outfile=None, **kwargs):
    report = ComparativeReport(algorithm_pairs=algorithm_pairs, **kwargs)
    if name and not outfile:
        outfile = f"{name}.{report.output_format}"
    elif outfile and not name:
        name = Path(outfile).name
    elif not name and not outfile:
        name = f"{exp.name}-cmp"
        outfile = f"{name}.{report.output_format}"

    if not Path(outfile).is_absolute():
        outfile = Path(exp.eval_dir) / outfile

    exp.add_report(report, name=name, outfile=outfile)
    if not REMOTE:
        exp.add_step(f"open-{name}", subprocess.call, ["xdg-open", outfile])


def add_scatter_plot_reports(exp, algorithm_pairs, attributes, *, filter=None):
    suffix = "-relative" if RELATIVE else ""
    for algo1, algo2 in algorithm_pairs:
        for attribute in attributes:
            exp.add_report(
                ScatterPlotReport(
                    relative=RELATIVE,
                    get_category=None if TEX else (lambda r1, r2: r1["domain"]),
                    attributes=[attribute],
                    filter_algorithm=[algo1, algo2],
                    filter=tools.make_list(filter),
                    format="tex" if TEX else "png",
                ),
                name=f"{exp.name}-{algo1}-{algo2}-{attribute}{suffix}",
            )
