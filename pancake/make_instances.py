#!/bin/python3

import copy
from pathlib import Path
import random
import sys

USAGE = "./make_instances.py --seed <seed> --ncakes <number_of_pancakes> --count <number_of_instances> --out-dir <output_directory>"
EXPECTED_FLAGS = ["--seed", "--ncakes", "--count", "--out-dir"]
DEFAULTS = {
    "--seed" : None,
    "--ncakes" : 50,
    "--count"  : 1,
    "--out-dir" : "."
}

def make_instance(settings, i):
    ar = list(range(settings["--ncakes"]))
    random.shuffle(ar)
    p = Path().joinpath(settings["--out-dir"], str(i))
    with open(p, "+w") as f:
        f.write(f"{settings["--ncakes"]}\n")
        for el in ar:
            f.write(f"{el} ")
        f.write("\n")
    
def make_instances(settings):
    Path(settings["--out-dir"]).mkdir(parents = True, exist_ok = True)
    random.seed(settings["--seed"])
    for i in range(1,settings["--count"]):
        make_instance(settings, i)

def get_args():
    flag_idx = 1
    value_idx = 2
    settings = copy.copy(DEFAULTS)
    while (value_idx < len(sys.argv)):
        flag_str = sys.argv[flag_idx]
        value_str = sys.argv[value_idx]
        flag_idx += 2
        value_idx += 2
        if flag_str in EXPECTED_FLAGS:
            if flag_str != "--out-dir":
                settings[flag_str] = int(value_str)
            else:
                settings[flag_str] = value_str
        else:
            raise ValueError(f"Got unexpected flag:{flag_str}")
    return settings



if __name__ == "__main__":
    if len(sys.argv) > len(EXPECTED_FLAGS) * 2:
        print(USAGE)
        exit(-1)
    settings = get_args()
    make_instances(settings)