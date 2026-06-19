"""RDB -> Lab attribute parser for the search suite.

The solvers emit the suite's "data file format 4": lines of the form

    #pair  "key"  "value"

plus optional `#altcols`/`#altrow` tables (e.g. the anytime `incumbent`
trajectory). This parser pulls the scalar `#pair` values out of run.log and maps
the ones we care about to Lab attributes.

It deliberately inlines a small #pair reader rather than importing
utils/rdb_to_json.py: Lab copies this file into each run directory and executes
it there (possibly on a remote cluster node), so it must be self-contained. The
parsing rules match rdb_to_json.py's: try int, then float, else keep the string.
"""

import re

from lab.parser import Parser

# RDB key -> (Lab attribute, type). Only scalars we report on.
SCALAR_MAP = {
    "final sol cost": ("cost", float),
    "final sol length": ("length", int),
    "total nodes expanded": ("expansions", int),
    "total nodes generated": ("generated", int),
    "total nodes reopened": ("reopened", int),
    "total nodes duplicated": ("duplicated", int),
    "total wall time": ("solver_wall_time", float),
    "total raw cpu time": ("solver_cpu_time", float),
    "initial heuristic": ("initial_h", float),
    "max virtual kilobytes": ("solver_max_vmem_kb", int),
    "algorithm": ("solver_algorithm", str),
}

_PAIR_RE = re.compile(r'^#pair\s+"([^"]*)"\s+"(.*)"\s*$')


def _coerce(token, typ):
    try:
        return typ(token)
    except (ValueError, TypeError):
        return None


def parse_pairs(content, props):
    """Extract #pair scalars from run.log and map them to Lab attributes."""
    for line in content.splitlines():
        m = _PAIR_RE.match(line.strip())
        if not m:
            continue
        key, raw = m.group(1), m.group(2)
        if key not in SCALAR_MAP:
            continue
        attr, typ = SCALAR_MAP[key]
        value = _coerce(raw, typ)
        if value is not None:
            props[attr] = value


def derive_coverage(content, props):
    """coverage = 1 iff the solver returned a real (non-negative) solution cost.

    The solvers print `final sol cost = -1` when no solution was found, so a
    negative or missing cost means the instance was not solved within limits.
    """
    cost = props.get("cost")
    solved = cost is not None and cost >= 0
    props["coverage"] = int(solved)
    if not solved:
        # Drop the sentinel so reports don't average -1 into cost statistics.
        props.pop("cost", None)
        props.setdefault("error", "unsolved-or-resource-limit")
    else:
        props.setdefault("error", "none")


def get_parser():
    parser = Parser()
    parser.add_function(parse_pairs, file="run.log")
    parser.add_function(derive_coverage, file="run.log")
    return parser


if __name__ == "__main__":
    get_parser().parse()
