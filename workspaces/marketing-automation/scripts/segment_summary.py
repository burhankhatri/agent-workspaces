#!/usr/bin/env python3
"""Summarise a segment CSV: row count, and the distribution of one column.

Deliberately dependency-free (stdlib only) so it runs on a bare image.
Usage: segment_summary.py <csv-path> [column]
"""
import csv
import sys
from collections import Counter


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: segment_summary.py <csv-path> [column]", file=sys.stderr)
        return 2
    path = sys.argv[1]
    column = sys.argv[2] if len(sys.argv) > 2 else None

    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))

    print(f"rows: {len(rows)}")
    if not rows:
        return 0
    print(f"columns: {', '.join(rows[0].keys())}")

    if column:
        if column not in rows[0]:
            print(f"no such column: {column}", file=sys.stderr)
            return 1
        for value, n in Counter(r[column] for r in rows).most_common(10):
            print(f"  {value or '(blank)'}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
