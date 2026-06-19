"""Instance generation and enumeration for the search-suite experiments.

Two responsibilities:

1. `generate(root, target_per_domain, ...)` populates a `key_file` directory
   hierarchy (the convention from agentic_experiment_running_plan.md §1) from the
   suite's seeded generators. Each domain is swept over a list of *sizes* (the
   swept dimension is the hierarchy key); each size gets enough seeds to reach
   roughly `target_per_domain` instances. Domains whose solver is compiled for a
   fixed size (tiles, pancake, synth_tree) declare a single size and vary the
   seed only.

2. `enumerate_instances(domain_root)` walks the hierarchy and yields one record
   per instance: `{"id", "params", "path"}` (the §1 walker, plus the file path).

Directory form (example, drobot swept over `ncontainers`):

    <root>/drobot/
        key_file              # "key=ncontainers"
        4/  key_file          # "key=instance"   -> files 0,1,2,...
        6/  key_file          # "key=instance"   -> files 0,1,2,...
        ...

Only the working domains are generated here; blocksworld/segments/visnav/plat2d
exclusions are discussed in ../../regression/README.md and ../../TODO.md
(blocksworld is now fixed and included).
"""

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Instance i of a (domain, size) uses BASE_SEED + size_index*1000 + i, so every
# instance is distinct and the whole set is reproducible.
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


# --- Single-instance generators: write one instance of `size` to `dest` -------
# `size` is the per-domain size token (its meaning is domain specific and
# documented in DOMAINS below). `seed` makes the instance reproducible.

def _one_tiles(dest, size, seed):  # size: board, only "4x4" (15md solver)
    with tempfile.TemporaryDirectory() as t:
        _run([REPO / "tiles/generator", "-w", "4", "-h", "4", "-n", "1",
              "-d", t, "-seed", seed])
        shutil.copyfile(Path(t) / "0", dest)


def _one_gridnav(dest, size, seed):  # size: "WxH"
    w, h = str(size).split("x")
    with tempfile.TemporaryDirectory() as t:
        grid = Path(t) / "g.grid"
        _run([REPO / "gridnav/mkseedinst", "-seed", seed,
              "-width", w, "-height", h, "-prob", "0.1"], stdout_path=grid)
        _run([REPO / "gridnav/randinst", "-s", seed, "-m", str(grid)],
             stdout_path=dest)


def _one_vacuum(dest, size, seed):  # size: number of dirt piles
    with tempfile.TemporaryDirectory() as t:
        _run([sys.executable, REPO / "vacuum/make_instances.py",
              "--height", "10", "--width", "15", "--p-blocked", "0.2",
              "--dirts", str(size), "--chargers", "0", "--seed", seed,
              "--count", "1", "--out-dir", t])
        shutil.copyfile(Path(t) / "1", dest)


def _one_drobot(dest, size, seed):  # size: number of containers
    _run([sys.executable, REPO / "drobot/make_instances.py",
          "--nlocs", "5", "--piles-per-loc", "2", "--cranes-per-loc", "1",
          "--ncontainers", str(size), "--seed", seed, "-o", str(dest)])


def _one_synth_tree(dest, size, seed):  # size: "default" (seed-only)
    with tempfile.TemporaryDirectory() as t:
        _run([sys.executable, REPO / "synth_tree/make_instances.py",
              "--count", "1", "--seed", seed, "--out-dir", t])
        shutil.copyfile(Path(t) / "1", dest)


def _one_traffic(dest, size, seed):  # size: number of moving objects
    _run([REPO / "traffic/randinst", "10", "10", str(size), seed],
         stdout_path=dest)


def _one_pancake(dest, size, seed):  # size: number of cakes (50pancake solver)
    with tempfile.TemporaryDirectory() as t:
        _run([sys.executable, REPO / "pancake/make_instances.py",
              "--seed", seed, "--ncakes", str(size), "--count", "1",
              "--out-dir", t])
        shutil.copyfile(Path(t) / "1", dest)


def _one_blocksworld(dest, size, seed):  # size: number of blocks (<= 20)
    _run([sys.executable, REPO / "blocksworld/make_instances.py",
          "-b", str(size), "-ss", "3", "-sg", "3", "--seed", seed,
          "-f", str(dest)])


# --- Domain registry ----------------------------------------------------------
# size_key : the swept dimension's name (becomes the key_file key).
# sizes    : ascending list of size tokens; sizes[0] is the easiest. Parametric
#            domains list 5; size-locked domains (solver compiled for one size)
#            list a single token and vary only the seed.

DOMAINS = {
    "gridnav":    {"solver": "gridnav/gridnav_solver", "size_key": "grid",
                   "sizes": ["40x15", "60x20", "80x25", "100x30", "120x40"],
                   "gen": _one_gridnav},
    "vacuum":     {"solver": "vacuum/vacuum_solver", "size_key": "dirts",
                   "sizes": [2, 4, 6, 8, 10], "gen": _one_vacuum},
    "drobot":     {"solver": "drobot/drobot_solver", "size_key": "ncontainers",
                   "sizes": [4, 6, 8, 10, 12], "gen": _one_drobot},
    "traffic":    {"solver": "traffic/traffic_solver", "size_key": "nobjects",
                   "sizes": [1, 2, 3, 4, 5], "gen": _one_traffic},
    "blocksworld": {"solver": "blocksworld/20bw_solver", "size_key": "blocks",
                    "sizes": [6, 9, 12, 15, 18], "gen": _one_blocksworld},
    # Size-locked: solver compiled for one size, so vary the seed only.
    "tiles":      {"solver": "tiles/15md_solver", "size_key": "board",
                   "sizes": ["4x4"], "gen": _one_tiles},
    "pancake":    {"solver": "pancake/50pancake_solver", "size_key": "ncakes",
                   "sizes": [50], "gen": _one_pancake},
    "synth_tree": {"solver": "synth_tree/synth_tree_solver", "size_key": "variant",
                   "sizes": ["default"], "gen": _one_synth_tree},
}


def _terminal_dir(root, domain, size):
    """Build domain/<size_key>/<size>/ with key_files and return the leaf."""
    spec = DOMAINS[domain]
    top = Path(root) / domain
    top.mkdir(parents=True, exist_ok=True)
    (top / "key_file").write_text(f"key={spec['size_key']}\n")
    leaf = top / str(size)
    leaf.mkdir(parents=True, exist_ok=True)
    (leaf / "key_file").write_text("key=instance\n")
    return leaf


def generate(root, target_per_domain=100, domains=None, max_sizes=None):
    """Populate the hierarchy under *root*. Idempotent: skips existing files.

    Each domain is swept over its sizes (capped at *max_sizes* if given), and
    each size gets ceil(target_per_domain / nsizes) seeds.
    """
    root = Path(root)
    for domain in (domains or DOMAINS):
        spec = DOMAINS[domain]
        if not (REPO / spec["solver"]).exists():
            raise RuntimeError(
                f"missing solver {spec['solver']} (run `make everything`)")
        sizes = spec["sizes"]
        if max_sizes is not None:
            sizes = sizes[:max_sizes]
        seeds_per_size = max(1, math.ceil(target_per_domain / len(sizes)))
        for si, size in enumerate(sizes):
            leaf = _terminal_dir(root, domain, size)
            for i in range(seeds_per_size):
                dest = leaf / str(i)
                if dest.exists():
                    continue
                spec["gen"](dest, size, str(BASE_SEED + si * 1000 + i))


def _parse_value(name):
    for typ in (int, float):
        try:
            return typ(name)
        except ValueError:
            pass
    return name


def enumerate_instances(domain_root):
    """Yield {"id", "params", "path"} per instance, in deterministic order."""
    domain_root = Path(domain_root)

    def walk(dir_path, accum):
        key_file = dir_path / "key_file"
        if not key_file.exists():
            return
        key = key_file.read_text().strip().split("=", 1)[1]
        if key == "instance":
            files = sorted((p for p in dir_path.iterdir()
                            if p.is_file() and p.name != "key_file"),
                           key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem)
            for f in files:
                yield {"id": f.stem, "params": dict(accum), "path": str(f)}
            return
        for sub in sorted(p for p in dir_path.iterdir() if p.is_dir()):
            yield from walk(sub, accum + [(key, _parse_value(sub.name))])

    yield from walk(domain_root, [])


def problem_name(inst):
    """A unique, readable problem id: '<size>-<instance-stem>'.

    Instance file stems repeat across sizes (each size dir has 0,1,2,...), so the
    size value is folded in to keep Lab run ids unique.
    """
    parts = [str(v) for v in inst["params"].values()] + [inst["id"]]
    return "-".join(parts)
