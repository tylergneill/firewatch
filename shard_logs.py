#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

if len(sys.argv) < 2:
    print("Usage: shard_nginx_log.py /path/to/log [days_per_shard]", file=sys.stderr)
    sys.exit(1)

log_path = Path(sys.argv[1])
days_per_shard = int(sys.argv[2]) if len(sys.argv) >= 3 else 7

# Nginx $time_local format: [15/Nov/2025:13:51:02 +0000]
TIME_FMT = "%d/%b/%Y:%H:%M:%S %z"

def parse_time_from_line(line):
    # Find the stuff between '[' and ']'
    start = line.find('[')
    end = line.find(']', start + 1)
    if start == -1 or end == -1:
        return None
    ts_str = line[start + 1:end]
    try:
        return datetime.strptime(ts_str, TIME_FMT)
    except Exception:
        return None

def main():
    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    # First pass: find the earliest timestamp to define shard 0
    first_ts = None
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            ts = parse_time_from_line(line)
            if ts is not None:
                first_ts = ts
                break

    if first_ts is None:
        print("Could not find any valid timestamps in log.", file=sys.stderr)
        sys.exit(1)

    # Normalize start to midnight for nicer shard boundaries
    first_ts = first_ts.astimezone(timezone.utc)
    first_ts = first_ts.replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"First timestamp: {first_ts.isoformat()}", file=sys.stderr)

    # Open output file handles as needed
    out_files = {}

    def get_shard_file(ts):
        # Compute shard index
        delta_days = (ts - first_ts).days
        shard_index = delta_days // days_per_shard
        shard_start = first_ts + timedelta(days=shard_index * days_per_shard)
        shard_end = shard_start + timedelta(days=days_per_shard - 1)

        # e.g. foo.log-20251101-20251114
        base = log_path.name
        shard_name = f"{base}-{shard_start.date()}-{shard_end.date()}"
        shard_path = log_path.parent / shard_name
        if shard_path not in out_files:
            out_files[shard_path] = shard_path.open("a", encoding="utf-8")
        return out_files[shard_path]

    # Second pass: assign lines to shards
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            ts = parse_time_from_line(line)
            if ts is None:
                # If unparsable, you can either skip or dump into a "misc" file
                # Here we just skip.
                continue
            ts = ts.astimezone(timezone.utc)
            outf = get_shard_file(ts)
            outf.write(line)

    for fh in out_files.values():
        fh.close()

    print("Sharding complete.", file=sys.stderr)

if __name__ == "__main__":
    main()
