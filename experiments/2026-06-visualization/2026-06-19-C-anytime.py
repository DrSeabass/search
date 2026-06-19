#!/usr/bin/env python3
"""Visualization study, part C: ARA* (anytime weighted A*).

Runs ARA* (start weight VIZ_ARA_WT0, decrement VIZ_ARA_DWT) over the working
domains. Besides the metric cross-product scatter, plots.py draws anytime
profiles (incumbent cost vs wall time) from the incumbent trajectory the parser
captures. Shares instances, the parser, and the plotting with the greedy and
wA* studies in this directory.

See README.md. Scope is controlled by the VIZ_* environment variables.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from searchlab.study import run_study  # noqa: E402

WT0 = os.environ.get("VIZ_ARA_WT0", "5")
DWT = os.environ.get("VIZ_ARA_DWT", "0.5")
ALGORITHMS = [("arastar", ["arastar", "-wt0", WT0, "-dwt", DWT])]

run_study(ALGORITHMS)
