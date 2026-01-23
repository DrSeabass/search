#!/usr/bin/env python3
"""Convert an RDB text file into JSON.

This script understands the subset of the RDB format used by files like
`example_rdb_file`, which contains:

  - A header and footer:
        #start data file format N
        ...
        #end data file format N

  - Scalar key/value pairs:
        #pair  "key"  "value"

  - "Alternate" tables:
        #altcols  "table_name"  "col1"  "col2" ...
        #altrow   "table_name"  v1       v2      ...

JSON STRUCTURE
--------------

The output JSON has the following top-level structure:

    {
        "format": <int or null>,          # RDB format version, if present
        "pairs": {                        # scalar key/value pairs from #pair lines
            "wall start date": "...",
            ...
        },
        "tables": [                       # column-oriented tables from #altcols/#altrow
            {
                "name": "incumbent",    # table name (first token on #altcols/#altrow)
                "columns": ["incumbent num", ...],
                "data": {
                    "incumbent num": [1, 2, 3, ...],
                    "incumbent nodes expanded": [77, 15065, 45397, ...],
                    ...
                }
            },
            ...
        ]
    }

Values in both "pairs" and table columns are parsed as numbers when possible:
  - If a token looks like an integer, it becomes an int.
  - Otherwise, if it looks like a float (including scientific notation), it
    becomes a float.
  - Otherwise it remains a string.

USAGE
-----

    python utils/rdb_to_json.py [RDB_FILE] [--pretty]

If RDB_FILE is omitted, the script reads from standard input. JSON is written
to standard output.

"""

import argparse
import json
import shlex
import sys
from typing import Any, Dict, Iterable, List, Optional, TextIO


def _parse_scalar(token: str) -> Any:
    """Best-effort conversion of a token to int, then float, else str.

    This is used for both #pair values and table cells.
    """

    # Try integer
    try:
        # Avoid treating things like "01" as octal; int() in Python3 is fine.
        return int(token)
    except ValueError:
        pass

    # Try float (includes scientific notation like 1.23e+09)
    try:
        return float(token)
    except ValueError:
        return token


def _parse_rdb(stream: Iterable[str]) -> Dict[str, Any]:
    """Parse an RDB text stream into a JSON-serializable Python structure.

    The parser is intentionally simple and only knows about the constructs
    seen in example_rdb_file: #start/#end, #pair, #altcols, #altrow.
    Unknown line types are ignored.
    """

    format_version: Optional[int] = None
    pairs: Dict[str, Any] = {}

    # tables[table_name] -> {"name": str, "columns": [str, ...], "data": {col: [values]}}
    tables: Dict[str, Dict[str, Any]] = {}

    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue

        # Tokenize with shell-style rules, honoring quoted strings.
        try:
            tokens = shlex.split(line, comments=False)
        except ValueError:
            # If splitting fails for some reason, skip the line rather than crash.
            continue

        if not tokens:
            continue

        tag = tokens[0]

        # Header/footer with format version.
        if tag == "#start":
            # Expect something like: #start data file format 4
            for i, tok in enumerate(tokens):
                if tok == "format" and i + 1 < len(tokens):
                    try:
                        format_version = int(tokens[i + 1])
                    except ValueError:
                        format_version = None
                    break
            continue

        if tag == "#end":
            # We could validate the format here, but it's not strictly necessary
            # for JSON conversion.
            continue

        # Simple key/value pair.
        if tag == "#pair":
            if len(tokens) < 3:
                # Malformed pair; ignore.
                continue
            key = tokens[1]
            # In practice we expect exactly one value token, but join any extras
            # just in case there are unquoted spaces.
            value_token = " ".join(tokens[2:])
            pairs[key] = _parse_scalar(value_token)
            continue

        # Column definitions for a table.
        if tag == "#altcols":
            if len(tokens) < 3:
                # Need at least table name + 1 column.
                continue
            table_name = tokens[1]
            col_names = tokens[2:]

            if table_name in tables:
                # If we see repeated #altcols for the same table, ensure the
                # columns match what we already know.
                existing = tables[table_name]["columns"]
                if existing != col_names:
                    raise ValueError(
                        f"Conflicting #altcols for table '{table_name}': "
                        f"{existing} vs {col_names}"
                    )
            else:
                tables[table_name] = {
                    "name": table_name,
                    "columns": col_names,
                    "data": {col: [] for col in col_names},
                }
            continue

        # Row data for a table.
        if tag == "#altrow":
            if len(tokens) < 2:
                continue
            table_name = tokens[1]
            if table_name not in tables:
                raise ValueError(
                    f"Encountered #altrow for unknown table '{table_name}' "
                    f"before any #altcols definition."
                )

            row_values = tokens[2:]
            table = tables[table_name]
            col_names = table["columns"]
            if len(row_values) != len(col_names):
                raise ValueError(
                    f"Row for table '{table_name}' has {len(row_values)} values, "
                    f"expected {len(col_names)}. Line: {raw_line.rstrip()}"
                )

            for col, tok in zip(col_names, row_values):
                table["data"][col].append(_parse_scalar(tok))

            continue

        # Unknown tags are ignored so we remain forwards-compatible with
        # additional RDB constructs.

    return {
        "format": format_version,
        "pairs": pairs,
        "tables": list(tables.values()),
    }


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert an RDB file (Search project format) to JSON."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to RDB file (default: read from standard input)",
    )
    parser.add_argument(
        "--pretty",
        "-p",
        action="store_true",
        help="Pretty-print JSON with indentation.",
    )

    args = parser.parse_args(argv)

    # Open input
    if args.path and args.path != "-":
        infile: TextIO
        try:
            infile = open(args.path, "r", encoding="utf-8")
        except OSError as e:
            sys.stderr.write(f"Failed to open RDB file '{args.path}': {e}\n")
            sys.exit(1)
    else:
        infile = sys.stdin

    try:
        data = _parse_rdb(infile)
    except Exception as e:  # noqa: BLE001 - we want to surface parsing issues
        sys.stderr.write(f"Error while parsing RDB input: {e}\n")
        sys.exit(1)
    finally:
        if infile is not sys.stdin:
            infile.close()

    indent = 2 if args.pretty else None
    json.dump(data, sys.stdout, indent=indent)
    if args.pretty:
        # Ensure a trailing newline when pretty-printing for terminal friendliness.
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
