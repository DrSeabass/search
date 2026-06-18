#!/usr/bin/env bash
# Stdin shim for Downward Lab.
#
# Lab runs commands without a shell, but every solver in this suite reads its
# instance from standard input:  `cat instance | ./domain_solver alg [args]`.
# Lab's add_command() can't express that pipe directly, so each run invokes
# this shim instead:
#
#     run-solver.sh <solver> <instance-file> <alg> [alg-args...]
#
# It feeds the instance file to the solver on stdin and forwards the algorithm
# arguments verbatim. The solver's RDB output goes to stdout, which Lab captures
# in run.log for parser.py to read.
set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "usage: run-solver.sh <solver> <instance> <alg> [args...]" >&2
    exit 2
fi

solver="$1"
instance="$2"
shift 2

exec "$solver" "$@" < "$instance"
