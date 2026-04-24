#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})$')


def main():
    parser = argparse.ArgumentParser(description="Print the most recent date found in archive log filenames.")
    parser.add_argument('--data-dir', default='static/data', help="Path to the data directory containing *-archive dirs.")
    args = parser.parse_args()

    data_path = Path(args.data_dir).resolve()
    if not data_path.is_dir():
        print(f"Error: data directory not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    max_date = None
    for f in data_path.glob('*-archive/access/*'):
        m = DATE_RE.search(f.name)
        if m:
            d = m.group(1)
            if max_date is None or d > max_date:
                max_date = d

    if max_date is None:
        print("Error: no dated archive files found under data dir", file=sys.stderr)
        sys.exit(1)

    print(max_date)


if __name__ == "__main__":
    main()
