#!/usr/bin/env python3

"""Random instance generator for the vacuum world.

This script generates instances compatible with `vacuum_instance.ml`.

Each instance file has the format produced by `fprint` in
`vacuum/vacuum_instance.ml`:

    <height> <width>\n
    Board:\n
    <row h-1>\n
    ...\n
    <row 0>\n
    \n
where each cell is one of:

    '#'  blocked
    'V'  starting location of the vacuum
    '*'  a pile of dirt
    ' '  empty/unblocked cell

Usage (flags come in flag/value pairs, order does not matter):

    ./make_instances.py \
        --height <height> \
        --width <width> \
        --p-blocked <probability_of_blocked_cell> \
        --dirts <number_of_dirt_piles> \
        [--seed <seed>] \
        [--count <number_of_instances>] \
        [--out-dir <output_directory>]

Examples:

    ./make_instances.py --height 10 --width 15 --p-blocked 0.2 --dirts 5 \
        --seed 42 --count 10 --out-dir ./data/vacuum_instances

"""

import copy
from pathlib import Path
import random
import sys


USAGE = (
    "./make_instances.py --height <height> --width <width> "
    "--p-blocked <prob> --dirts <num_dirt_piles> "
    "[--seed <seed>] [--count <num_instances>] [--out-dir <output_directory>]"
)

EXPECTED_FLAGS = [
    "--height",
    "--width",
    "--p-blocked",
    "--dirts",
    "--seed",
    "--count",
    "--out-dir",
]

DEFAULTS = {
    "--height": None,
    "--width": None,
    "--p-blocked": 0.1,  # probability each cell is blocked
    "--dirts": 2,        # number of piles of dirt
    "--seed": None,
    "--count": 1,
    "--out-dir": ".",
}


def make_instance(settings: dict, index: int) -> None:
    """Create a single vacuum instance and write it to `<out-dir>/<index>`.

    The generated instance mirrors the representation in `vacuum_instance.ml`.
    """

    height = settings["--height"]
    width = settings["--width"]
    p_blocked = settings["--p-blocked"]
    num_dirts = settings["--dirts"]

    # Generate blocked cells: True means blocked.
    blocked = [
        [random.random() < p_blocked for _ in range(width)]
        for _ in range(height)
    ]

    # Ensure there is at least one unblocked cell so we can place the start.
    if all(all(row) for row in blocked):
        ry = random.randrange(height)
        rx = random.randrange(width)
        blocked[ry][rx] = False

    # Choose a random unblocked start cell (mirrors `find_start` in ML code).
    while True:
        sx = random.randrange(width)
        sy = random.randrange(height)
        if not blocked[sy][sx]:
            break

    # Place dirt piles. As in the ML implementation, we try `num_dirts` times
    # but may end up with fewer distinct piles due to duplicates/conflicts.
    dirt_positions = []  # list of (x, y)
    for _ in range(num_dirts):
        dx = random.randrange(width)
        dy = random.randrange(height)
        if (dx, dy) != (sx, sy) and not blocked[dy][dx] and (dx, dy) not in dirt_positions:
            dirt_positions.append((dx, dy))

    out_dir = Path(settings["--out-dir"])
    out_path = out_dir / str(index)

    # Write in the same format `fprint` uses in `vacuum_instance.ml`.
    with out_path.open("w", encoding="utf-8") as f:
        # Note: ML prints "height width" on the first line.
        f.write(f"{height} {width}\n")
        f.write("Board:\n")

        # ML prints rows from y = height-1 down to 0, columns x = 0..width-1.
        for y in range(height - 1, -1, -1):
            row_chars = []
            for x in range(width):
                if blocked[y][x]:
                    c = "#"
                elif (x, y) == (sx, sy):
                    c = "V"
                elif (x, y) in dirt_positions:
                    c = "*"
                else:
                    c = " "
                row_chars.append(c)
            f.write("".join(row_chars) + "\n")

        # Trailing blank line, matching `fprint`.
        f.write("\n")


def make_instances(settings: dict) -> None:
    """Generate `--count` instances using the provided settings."""

    out_dir = Path(settings["--out-dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    seed = settings["--seed"]
    if seed is not None:
        random.seed(seed)

    for i in range(1, settings["--count"] + 1):
        make_instance(settings, i)


def get_args() -> dict:
    """Parse command-line arguments into a settings dict.

    Arguments must come in flag/value pairs. Unknown flags raise an error.
    """

    # Simple pair-based parsing, similar to other generators in this repo.
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
        elif flag == "--p-blocked":
            settings[flag] = float(value)
        elif flag == "--seed":
            settings[flag] = int(value)
        else:
            # height, width, dirts, count
            settings[flag] = int(value)

    # Ensure required parameters are provided.
    if settings["--height"] is None or settings["--width"] is None:
        raise ValueError("Both --height and --width must be specified")

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
