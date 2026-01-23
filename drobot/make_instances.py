#!/usr/bin/env python3
"""Dock-robot instance generator (Python translation of
   drobot/dock_robot_instance.ml).

This script can generate *unit-square* style random instances identical in
spirit to the OCaml implementation’s `random_usquare` family.  It produces
text files in the same format written by the original `write` routine.

Example
-------
Generate a single 10-location instance and write it to stdout::

    ./drobot/make_instance.py --nlocs 10 --piles-per-loc 2 \\
                              --cranes-per-loc 1 --ncontainers 40

Write to a file::

    ./drobot/make_instance.py --nlocs 20 -p 3 -c 2 -n 100 \\
                              -o inst.txt
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass, field
from typing import List, Sequence


@dataclass
class Instance:
    """Dock-robot problem instance."""

    # Core data structures  (names match the OCaml record fields)
    adjacent: List[List[float]]
    pile_contents: List[List[int]]
    cranes_at_location: List[List[int]]
    piles_at_location: List[List[int]]
    goal: List[int]

    # Size metadata (redundant but convenient / matches OCaml)
    nlocations: int
    ncranes: int
    ncontainers: int
    npiles: int
    nrobots: int = 1

    # --------------------------------------------------------------------- #
    #  Pretty-printing / serialization                                     #
    # --------------------------------------------------------------------- #
    def _write_sizes(self, fh: "TextIO") -> None:
        fh.write(f"nlocations: {self.nlocations}\n")
        fh.write(f"ncranes: {self.ncranes}\n")
        fh.write(f"ncontainers: {self.ncontainers}\n")
        fh.write(f"npiles: {self.npiles}\n")
        fh.write(f"nrobots: {self.nrobots}\n")

    def _write_locations(self, fh: "TextIO") -> None:
        for loc, adj in enumerate(self.adjacent):
            fh.write(f"location {loc}\n")

            fh.write("\tadjacent: ")
            fh.write(" ".join(f"{d}" for d in adj))
            fh.write("\n")

            if self.cranes_at_location[loc]:
                fh.write("\tcranes: ")
                fh.write(" ".join(map(str, self.cranes_at_location[loc])))
                fh.write("\n")

            if self.piles_at_location[loc]:
                fh.write("\tpiles: ")
                fh.write(" ".join(map(str, self.piles_at_location[loc])))
                fh.write("\n")

    def _write_piles(self, fh: "TextIO") -> None:
        for pile, contents in enumerate(self.pile_contents):
            fh.write(f"pile {pile}\n\t")
            fh.write(" ".join(map(str, contents)))  
            fh.write("\n")

    def _write_goal(self, fh: "TextIO") -> None:
        for container, loc in enumerate(self.goal):
            fh.write(f"container {container} at {loc}\n")

    def write(self, fh=sys.stdout) -> None:
        """Emit a textual representation identical to the OCaml version."""
        self._write_sizes(fh)
        self._write_locations(fh)
        self._write_piles(fh)
        self._write_goal(fh)


# ------------------------------------------------------------------------- #
#  Helpers                                                                  #
# ------------------------------------------------------------------------- #
def place_locations(nlocs: int) -> List[List[float]]:
    """Generate an Euclidean distance matrix for *nlocs* random points in
    the unit square (matches `place_locations` in the OCaml code)."""
    xs = [random.random() for _ in range(nlocs)]
    ys = [random.random() for _ in range(nlocs)]
    adj: List[List[float]] = [[0.0] * nlocs for _ in range(nlocs)]
    for i in range(nlocs):
        xi, yi = xs[i], ys[i]
        for j in range(i, nlocs):
            xj, yj = xs[j], ys[j]
            dist = math.hypot(xi - xj, yi - yj)
            adj[i][j] = adj[j][i] = dist
    return adj


def map_ntimes(start_idx: int, num: int) -> List[int]:
    """Return *num* sequential integers starting at *start_idx*."""
    return list(range(start_idx, start_idx + num))


def random_usquare(
    *,
    nlocs: int,
    piles_per_loc: int,
    cranes_per_loc: int,
    ncontainers: int,
) -> Instance:
    """Python translation of `random_usquare` from OCaml."""

    # Sequential id generators
    next_pile = 0
    next_crane = 0
    next_container = 0

    # Create locations and adjacency
    adj = place_locations(nlocs)

    # Piles + cranes per location
    piles_at_location: List[List[int]] = []
    cranes_at_location: List[List[int]] = []

    for _ in range(nlocs):
        # piles
        pile_ids = map_ntimes(next_pile, piles_per_loc)
        next_pile += piles_per_loc
        piles_at_location.append(pile_ids)

        # cranes
        crane_ids = map_ntimes(next_crane, cranes_per_loc)
        next_crane += cranes_per_loc
        cranes_at_location.append(crane_ids)

    npiles = next_pile
    ncranes = next_crane

    # Fill piles with containers
    pile_contents: List[List[int]] = [[] for _ in range(npiles)]
    for pile in range(npiles):
        left = ncontainers - next_container
        num_here = random.randint(0, left) if pile < npiles - 1 else left
        conts = map_ntimes(next_container, num_here)
        next_container += num_here
        random.shuffle(conts)  # permute as in OCaml
        pile_contents[pile] = conts

    ncontainers_actual = next_container
    if ncontainers_actual != ncontainers:
        raise ValueError(
            "Container allocation mismatch "
            f"(expected {ncontainers}, got {ncontainers_actual})"
        )

    # Random goal location (any location) for each container
    goal = [random.randrange(nlocs) for _ in range(ncontainers)]

    return Instance(
        adjacent=adj,
        pile_contents=pile_contents,
        cranes_at_location=cranes_at_location,
        piles_at_location=piles_at_location,
        goal=goal,
        nlocations=nlocs,
        ncranes=ncranes,
        ncontainers=ncontainers,
        npiles=npiles,
        nrobots=1,
    )


# ------------------------------------------------------------------------- #
#  CLI                                                                      #
# ------------------------------------------------------------------------- #
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate random dock-robot problem instances "
        "(unit-square model)."
    )
    p.add_argument("--seed", type=int, help="RNG seed")
    p.add_argument(
        "--nlocs",
        type=int,
        required=True,
        help="Number of locations (nodes) in the unit-square graph",
    )
    p.add_argument(
        "--piles-per-loc",
        "-p",
        type=int,
        required=True,
        help="Number of piles placed at each location",
    )
    p.add_argument(
        "--cranes-per-loc",
        "-c",
        type=int,
        required=True,
        help="Number of cranes at each location",
    )
    p.add_argument(
        "--ncontainers",
        "-n",
        type=int,
        required=True,
        help="Total number of containers in the instance",
    )
    p.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Write the instance to PATH instead of stdout",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.seed is not None:
        random.seed(args.seed)

    inst = random_usquare(
        nlocs=args.nlocs,
        piles_per_loc=args.piles_per_loc,
        cranes_per_loc=args.cranes_per_loc,
        ncontainers=args.ncontainers,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            inst.write(fh)
    else:
        inst.write(sys.stdout)


if __name__ == "__main__":
    main()