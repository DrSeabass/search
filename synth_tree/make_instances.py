#!/usr/bin/env python3

"""Random instance generator for the synthetic tree domain.

This script generates instances compatible with the C++ implementation in
`synth_tree/synth_tree.cc`.

The C++ `SynthTree` constructor expects an input file of the form::

    <seed>\n

where ``seed`` is a (non-negative) integer read using ``fscanf("%ld", &seed)``.
Each such seed deterministically defines the entire synthetic tree that the
search algorithms explore.

Usage (flags come in flag/value pairs, order does not matter)::

    ./make_instances.py \
        --count <number_of_instances> \
        [--seed <rng_seed>] \
        [--out-dir <output_directory>]

Examples
--------

Generate 10 instances using RNG seed 42 and write them into a directory
``./data/synth_tree`` as files ``1``, ``2``, ..., ``10``::

    ./make_instances.py --count 10 --seed 42 --out-dir ./data/synth_tree

This mirrors the style of the instance generators in the vacuum, drobot,
and pancake domains: a lightweight Python script that emits text files in
the format expected by the corresponding C++ domain.
"""

from __future__ import annotations

import copy
from pathlib import Path
import random
import sys


USAGE = (
    "./make_instances.py --count <num_instances> "
    "[--seed <rng_seed>] [--out-dir <output_directory>]"
)

EXPECTED_FLAGS = [
    "--count",
    "--seed",
    "--out-dir",
]

DEFAULTS = {
    "--count": 1,
    "--seed": None,
    "--out-dir": ".",
}


def make_instance(settings: dict, index: int) -> None:
    """Create a single SynthTree instance and write it to `<out-dir>/<index>`.

    The generated instance mirrors the representation expected by the C++
    constructor in `synth_tree/synth_tree.cc` and `synth_tree/main.cc`.

    We emit a single non-negative integer ``seed`` on its own line. This is
    read by the C++ code using ``fscanf(in, "%ld", &seed)``.
    """

    # Use a 31-bit range so the value is safe on both 32-bit and 64-bit
    # platforms when read into a C/C++ `long`.
    seed_value = random.randint(0, 2**31 - 1)

    out_dir = Path(settings["--out-dir"])
    out_path = out_dir / str(index)

    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"{seed_value}\n")


def make_instances(settings: dict) -> None:
    """Generate `--count` instances using the provided settings."""

    out_dir = Path(settings["--out-dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    seed = settings["--seed"]
    if seed is not None:
        random.seed(seed)

    count = settings["--count"]
    for i in range(1, count + 1):
        make_instance(settings, i)


def get_args() -> dict:
    """Parse command-line arguments into a settings dict.

    Arguments must come in flag/value pairs. Unknown flags raise an error.
    This mirrors the simple pair-based parsing used by other generators in
    this repository (e.g., `vacuum/make_instances.py`).
    """

    # Expect an even number of additional arguments: flag/value pairs.
    if (len(sys.argv) - 1) % 2 != 0:
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    settings = copy.copy(DEFAULTS)

    idx = 1
    while idx < len(sys.argv):
        flag = sys.argv[idx]
        value = sys.argv[idx + 1]
        idx += 2

        if flag not in EXPECTED_FLAGS:
            raise ValueError(f"Got unexpected flag: {flag}")

        if flag == "--out-dir":
            settings[flag] = value
        elif flag == "--seed":
            settings[flag] = int(value)
        elif flag == "--count":
            settings[flag] = int(value)

    if settings["--count"] <= 0:
        raise ValueError("--count must be a positive integer")

    return settings


def main() -> None:
    if len(sys.argv) == 1:
        print(USAGE)
        sys.exit(1)

    try:
        settings = get_args()
    except Exception as e:  # noqa: BLE001 - simple CLI tool
        print(f"Error: {e}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    make_instances(settings)


if __name__ == "__main__":
    main()
