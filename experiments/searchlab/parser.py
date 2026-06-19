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
import shlex

from lab.parser import Parser

# Anytime `incumbent` table column -> (list-valued attribute, type). The
# improving-incumbent trajectory (e.g. from ARA*) is captured as parallel lists
# so a (wall time, cost) anytime profile can be plotted. Lab supports
# list-valued properties; this keeps the trajectory on the standard properties
# path rather than in a side file.
INCUMBENT_MAP = {
    "incumbent wall time": ("incumbent_wall_time", float),
    "incumbent solution cost": ("incumbent_cost", float),
    "incumbent nodes expanded": ("incumbent_expansions", int),
    "incumbent nodes generated": ("incumbent_generated", int),
    "incumbent weight": ("incumbent_weight", float),
}

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


def parse_incumbent(content, props):
    """Capture the anytime `incumbent` table into parallel list properties.

    Reads `#altcols "incumbent" ...` for the column order and the following
    `#altrow "incumbent" ...` rows for the trajectory. Only emitted by anytime
    algorithms (e.g. ARA*); for everything else this is a no-op.
    """
    columns = None
    rows = []
    for line in content.splitlines():
        s = line.strip()
        if not (s.startswith("#altcols") or s.startswith("#altrow")):
            continue
        try:
            toks = shlex.split(s)
        except ValueError:
            continue
        if len(toks) < 2 or toks[1] != "incumbent":
            continue
        if toks[0] == "#altcols":
            columns = toks[2:]
        elif toks[0] == "#altrow" and columns is not None:
            cells = toks[2:]
            if len(cells) == len(columns):
                rows.append(cells)

    if not columns or not rows:
        return
    for col_idx, col in enumerate(columns):
        if col not in INCUMBENT_MAP:
            continue
        attr, typ = INCUMBENT_MAP[col]
        series = [_coerce(row[col_idx], typ) for row in rows]
        if all(v is not None for v in series):
            props[attr] = series


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
    parser.add_function(parse_incumbent, file="run.log")
    parser.add_function(derive_coverage, file="run.log")
    return parser


if __name__ == "__main__":
    get_parser().parse()
