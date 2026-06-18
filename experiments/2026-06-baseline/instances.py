"""Instance generation and enumeration for the baseline experiment.

Two responsibilities:

1. `generate(root, instances_per_domain)` populates a `key_file` directory
   hierarchy (the convention described in agentic_experiment_running_plan.md §1)
   from the suite's seeded instance generators, so the study is reproducible.

2. `enumerate_instances(domain_root)` walks that hierarchy and yields one record
   per instance: `{"id", "params", "path"}`. This is the §1 walker, extended to
   also return the instance file path so the experiment can feed it to a solver.

Directory form:

    <root>/<domain>/
        key_file                 # contains "key=<name>"
        <value>/
            key_file
            ...
                key_file         # contains "key=instance" (terminal level)
                0, 1, 2, ...      # instance files; the stem is the instance id

Only the working domains are generated here; see ../regression/README.md and
../../TODO.md for why blocksworld/segments/visnav/plat2d are excluded.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Base seed; instance i in a domain uses BASE_SEED + i so runs are reproducible
# and instances within a domain differ.
BASE_SEED = 100


def _run(argv, stdout_path=None):
    argv = [str(a) for a in argv]
    out = open(stdout_path, "wb") if stdout_path else None
    try:
        subprocess.run(argv, cwd=REPO, stdout=out, stderr=subprocess.PIPE,
                       check=True)
    finally:
        if out:
            out.close()


# --- Single-instance generators: write exactly one instance file to dest -----

def _one_tiles(dest, seed):
    with tempfile.TemporaryDirectory() as t:
        _run([REPO / "tiles/generator", "-w", "4", "-h", "4", "-n", "1",
              "-d", t, "-seed", seed])
        shutil.copyfile(Path(t) / "0", dest)


def _one_gridnav(dest, seed):
    with tempfile.TemporaryDirectory() as t:
        grid = Path(t) / "g.grid"
        _run([REPO / "gridnav/mkseedinst", "-seed", seed,
              "-width", "80", "-height", "25", "-prob", "0.1"], stdout_path=grid)
        _run([REPO / "gridnav/randinst", "-s", seed, "-m", str(grid)],
             stdout_path=dest)


def _one_vacuum(dest, seed):
    with tempfile.TemporaryDirectory() as t:
        _run([sys.executable, REPO / "vacuum/make_instances.py",
              "--height", "10", "--width", "15", "--p-blocked", "0.2",
              "--dirts", "5", "--chargers", "0", "--seed", seed,
              "--count", "1", "--out-dir", t])
        shutil.copyfile(Path(t) / "1", dest)


def _one_drobot(dest, seed):
    _run([sys.executable, REPO / "drobot/make_instances.py",
          "--nlocs", "5", "--piles-per-loc", "2", "--cranes-per-loc", "1",
          "--ncontainers", "6", "--seed", seed, "-o", str(dest)])


def _one_synth_tree(dest, seed):
    with tempfile.TemporaryDirectory() as t:
        _run([sys.executable, REPO / "synth_tree/make_instances.py",
              "--count", "1", "--seed", seed, "--out-dir", t])
        shutil.copyfile(Path(t) / "1", dest)


def _one_traffic(dest, seed):
    _run([REPO / "traffic/randinst", "5", "5", "1", seed], stdout_path=dest)


def _one_pancake(dest, seed):
    with tempfile.TemporaryDirectory() as t:
        _run([sys.executable, REPO / "pancake/make_instances.py",
              "--seed", seed, "--ncakes", "50", "--count", "1", "--out-dir", t])
        shutil.copyfile(Path(t) / "1", dest)


# --- Domain registry ----------------------------------------------------------
# Each entry: the solver binary, the (key, value) levels that describe the
# instance family, and the single-instance generator.

DOMAINS = {
    "tiles":      {"solver": "tiles/15md_solver",
                   "levels": [("width", 4), ("height", 4)], "gen": _one_tiles},
    "gridnav":    {"solver": "gridnav/gridnav_solver",
                   "levels": [("width", 80), ("height", 25), ("prob", "0.1")],
                   "gen": _one_gridnav},
    "vacuum":     {"solver": "vacuum/vacuum_solver",
                   "levels": [("dirts", 5), ("chargers", 0)], "gen": _one_vacuum},
    "drobot":     {"solver": "drobot/drobot_solver",
                   "levels": [("ncontainers", 6)], "gen": _one_drobot},
    "synth_tree": {"solver": "synth_tree/synth_tree_solver",
                   "levels": [("variant", "default")], "gen": _one_synth_tree},
    "traffic":    {"solver": "traffic/traffic_solver",
                   "levels": [("width", 5), ("height", 5), ("nobjects", 1)],
                   "gen": _one_traffic},
    "pancake":    {"solver": "pancake/50pancake_solver",
                   "levels": [("ncakes", 50)], "gen": _one_pancake},
}


def _terminal_dir(root, domain):
    """Build the key_file chain for *domain* and return its terminal dir."""
    spec = DOMAINS[domain]
    dir_path = Path(root) / domain
    levels = spec["levels"]
    # Write key_file at each level pointing to the next key, ending in "instance".
    cur = dir_path
    for i, (key, value) in enumerate(levels):
        cur.mkdir(parents=True, exist_ok=True)
        (cur / "key_file").write_text(f"key={key}\n")
        cur = cur / str(value)
    cur.mkdir(parents=True, exist_ok=True)
    (cur / "key_file").write_text("key=instance\n")
    return cur


def generate(root, instances_per_domain, domains=None):
    """Populate the hierarchy under *root*. Idempotent: skips existing files."""
    root = Path(root)
    for domain in (domains or DOMAINS):
        spec = DOMAINS[domain]
        if not (REPO / spec["solver"]).exists():
            raise RuntimeError(
                f"missing solver {spec['solver']} (run `make everything`)")
        term = _terminal_dir(root, domain)
        for i in range(instances_per_domain):
            dest = term / str(i)
            if dest.exists():
                continue
            spec["gen"](dest, str(BASE_SEED + i))


def _parse_value(name):
    for typ in (int, float):
        try:
            return typ(name)
        except ValueError:
            pass
    return name


def enumerate_instances(domain_root):
    """Yield {"id", "params", "path"} for every instance under *domain_root*.

    Deterministic (lexicographic) order. Mirrors agentic plan §1, plus "path".
    """
    domain_root = Path(domain_root)

    def walk(dir_path, accum):
        key_file = dir_path / "key_file"
        if not key_file.exists():
            return
        key = key_file.read_text().strip().split("=", 1)[1]
        if key == "instance":
            for f in sorted(p for p in dir_path.iterdir() if p.is_file()
                            and p.name != "key_file"):
                yield {"id": f.stem, "params": dict(accum), "path": str(f)}
            return
        for sub in sorted(p for p in dir_path.iterdir() if p.is_dir()):
            yield from walk(sub, accum + [(key, _parse_value(sub.name))])

    yield from walk(domain_root, [])
