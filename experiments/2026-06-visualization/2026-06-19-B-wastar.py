#!/usr/bin/env python3
"""Visualization study, part B: weighted A* at several weights.

Runs wA* at each weight in VIZ_WEIGHTS (default 1.5,2,3,5) over the working
domains and draws one metric cross-product scatter per weight via plots.py.
Shares instances, the parser, and the plotting with the greedy and anytime
studies in this directory.

See README.md. Scope is controlled by the VIZ_* environment variables.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from searchlab.study import run_study  # noqa: E402

WEIGHTS = [w.strip() for w in os.environ.get("VIZ_WEIGHTS", "1.5,2,3,5").split(",")
           if w.strip()]
ALGORITHMS = [(f"wastar-{w}", ["wastar", "-wt", w]) for w in WEIGHTS]

run_study(ALGORITHMS)
