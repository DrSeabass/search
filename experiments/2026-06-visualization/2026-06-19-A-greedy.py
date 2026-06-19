#!/usr/bin/env python3
"""Visualization study, part A: greedy best-first search.

Runs greedy over the working domains (~100 instances each, swept across sizes)
and draws the metric cross-product scatter via plots.py. Shares instances, the
parser, and the plotting with the wA* and anytime studies in this directory.

See README.md. Scope is controlled by the VIZ_* environment variables.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from searchlab.study import run_study  # noqa: E402

ALGORITHMS = [("greedy", ["greedy"])]

run_study(ALGORITHMS)
