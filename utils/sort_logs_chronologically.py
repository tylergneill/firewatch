#!/usr/bin/env python3
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
import shutil
import argparse

# Add project root to sys.path to allow importing from utils package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
        # datetime.strptime doesn't support %z for all timezones consistently
        # so we'll parse without it and handle offset manually if necessary.
        # However, for Nginx, %z is usually +0000, which works.
        return datetime.strptime(ts_str, TIME_FMT)
    except ValueError:
        # Try parsing without timezone for logs that might omit it
        try:
            return datetime.strptime(ts_str, TIME_FMT[:-3]) # Remove " %z"
        except ValueError:
            return None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Sort log files in place by timestamp.")
    parser.add_argument("log_root_dir", nargs="?", default="static/data",
                        help="Path to the root directory containing log files. Defaults to 'static/data'.")
    args = parser.parse_args()

    log_root_dir = Path(args.log_root_dir).resolve()
    if not log_root_dir.is_dir():
        print(f"Log directory not found: {log_root_dir}", file=sys.stderr)
        sys.exit(1)

    # Find all files ending with .log or .log-YYYY-MM-DD or .log-unparsable
    # We should exclude directories like .git/, __pycache__/ etc.
    # rglob will handle recursion.
    files_to_sort = []
    for p in log_root_dir.rglob('*'):
        if p.is_file() and (
            p.name.endswith('.log') or 
            re.match(r'.*\.log-(\d{4}-\d{2}-\d{2}|unparsable)$', p.name)
        ):
            files_to_sort.append(p)
            
    if not files_to_sort:
        print(f"No log files found in {log_root_dir} to sort.", file=sys.stderr)
        sys.exit(0)

    for file_path in files_to_sort:
        print(f"Sorting {file_path.relative_to(log_root_dir)}...", file=sys.stderr)
        
        lines_with_timestamps = []
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    ts = parse_time_from_line(line)
                    # Use datetime.min as a fallback for None timestamps to put them at the beginning
                    # We add the line itself as a secondary sort key to ensure stability if timestamps are truly identical
                    # or for unparsable lines.
                    lines_with_timestamps.append((ts if ts is not None else datetime.min.replace(tzinfo=timezone.utc), line))
            
            # Perform a stable sort by timestamp. Python's list.sort() is stable.
            # If timestamps are identical, the original relative order (from reading the file) is maintained.
            lines_with_timestamps.sort(key=lambda x: x[0])

            sorted_lines = [item[1] for item in lines_with_timestamps]

            # Write sorted lines back to the file using a temporary file for safety
            temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
            try:
                with temp_path.open("w", encoding="utf-8") as f:
                    f.writelines(sorted_lines)
                shutil.move(temp_path, file_path)
            except Exception as e:
                print(f"Error writing sorted data to {file_path}: {e}", file=sys.stderr)
            finally:
                if temp_path.exists():
                    temp_path.unlink()

        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=sys.stderr)

    print("Log sorting complete.", file=sys.stderr)


if __name__ == "__main__":
    main()
