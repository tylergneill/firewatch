#!/usr/bin/env python3
import argparse
import ipaddress
import pathlib
import shelve
import sys
from collections import deque, defaultdict

from utils import parse_line

"""
Usage: python purge_bad_crawlers.py \
  --data-dir ../firewatch-data \
  --forbidden-dir ../firewatch-data-forbidden \
  --cache-file static/cache/firewatch_cache.db
"""



# --- Configuration ---
BLOCKED_CIDRS = [
    "146.174.0.0/16",
    "202.76.0.0/16",
    "8.160.0.0/16",
    "47.82.0.0/16",
]

# --- Pre-compile networks for performance ---
BLOCKED_NETWORKS = [ipaddress.ip_network(cidr) for cidr in BLOCKED_CIDRS]

def is_ip_blocked(ip_str: str) -> bool:
    """Checks if a given IP address string is in one of the blocked networks."""
    if not ip_str:
        return False
    try:
        ip_addr = ipaddress.ip_address(ip_str)
        for network in BLOCKED_NETWORKS:
            if ip_addr in network:
                return True
    except ValueError:
        # Ignore lines where the IP address is invalid
        return False
    return False

def process_log_file(log_path: pathlib.Path, forbidden_dir: pathlib.Path):
    """
    Reads a log file, separates lines based on IP, overwrites the original
    with clean lines, and writes blocked lines to the forbidden directory.
    """
    print(f"  Processing: {log_path}...")
    good_lines = deque()
    forbidden_lines = deque()

    try:
        with log_path.open('rb') as f:
            for line_bytes in f:
                # We need the raw bytes, but parse_line needs to decode it.
                # Let's get the IP without fully depending on parse_line's success.
                try:
                    # Quick split to get IP, faster than full regex for every line
                    ip = line_bytes.split(b' ', 3)[2].decode('utf-8')
                except (IndexError, UnicodeDecodeError):
                    # If line format is weird, treat as good and keep it
                    good_lines.append(line_bytes)
                    continue

                if is_ip_blocked(ip):
                    forbidden_lines.append(line_bytes)
                else:
                    good_lines.append(line_bytes)
    except FileNotFoundError:
        print(f"    - File not found, skipping: {log_path}")
        return None, None
    except Exception as e:
        print(f"    - Error reading file {log_path}: {e}")
        return None, None
    
    # --- Write forbidden logs ---
    if forbidden_lines:
        # Construct the output path
        relative_path = log_path.relative_to(log_path.parent.parent) # e.g., panditya-archive/log-file
        forbidden_path = forbidden_dir / relative_path
        forbidden_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Add .forbidden suffix
        final_forbidden_path = forbidden_path.with_name(forbidden_path.name + ".forbidden")

        with final_forbidden_path.open('ab') as f:
            f.writelines(forbidden_lines)
        print(f"    - Wrote {len(forbidden_lines)} lines to {final_forbidden_path}")

    # --- Overwrite original with purified logs ---
    with log_path.open('wb') as f:
        f.writelines(good_lines)
    
    print(f"    - Rewrote original file with {len(good_lines)} lines.")
    
    return len(good_lines), len(forbidden_lines)


def main(data_dir: str, forbidden_dir: str, cache_file: str):
    """
    Main function to find and process all log files.
    """
    data_path = pathlib.Path(data_dir)
    forbidden_path = pathlib.Path(forbidden_dir)

    if not data_path.is_dir():
        print(f"Error: Data directory not found at '{data_dir}'")
        sys.exit(1)

    print(f"Starting crawler purge for directory: {data_path}")
    print(f"Forbidden logs will be written to: {forbidden_path}")
    print(f"Purging cache entries from: {cache_file}")

    log_files = list(data_path.rglob('*.access.log*'))
    print(f"Found {len(log_files)} log files to process.\n")

    app_stats = defaultdict(lambda: {'good': 0, 'newly_forbidden': 0})

    with shelve.open(cache_file) as cache:
        for log_file in log_files:
            if log_file.is_file():
                app_name_parts = log_file.name.split('-app.access.log')
                app_name = app_name_parts[0] if app_name_parts else "unknown"

                good_count, forbidden_count = process_log_file(log_file, forbidden_path)
                if good_count is not None:
                    app_stats[app_name]['good'] += good_count
                    app_stats[app_name]['newly_forbidden'] += forbidden_count

                    # If we purged lines, the cache is stale and must be deleted.
                    if forbidden_count > 0:
                        # Use the absolute path as the key, just like the web app does.
                        log_file_key = str(log_file.resolve())
                        if log_file_key in cache:
                            print(f"    - Deleting stale cache entry for: {log_file.name}")
                            del cache[log_file_key]

    # --- Start Final Report Calculation ---
    print("\nCalculating final totals...")
    total_forbidden_stats = defaultdict(int)
    if forbidden_path.is_dir():
        forbidden_files = list(forbidden_path.rglob('*.forbidden'))
        for f_file in forbidden_files:
            app_name_parts = f_file.name.split('-app.access.log')
            app_name = app_name_parts[0] if app_name_parts else "unknown"
            with f_file.open('rb') as f:
                # Fast line counting
                lines = sum(1 for _ in f)
                total_forbidden_stats[app_name] += lines
    
    print("\n--- Purge Summary ---")
    header = f"{'Application':<25} | {'Original Lines':>15} | {'Just Purged':>15} | {'Total Forbidden':>15} | {'% Purged (Overall)':>20}"
    print(header)
    print("-" * len(header))

    grand_total_good = 0
    grand_total_newly_purged = 0
    grand_total_forbidden = 0

    # Combine keys from both stats dicts to not miss any app
    all_app_names = sorted(list(set(app_stats.keys()) | set(total_forbidden_stats.keys())))

    for app_name in all_app_names:
        stats = app_stats[app_name]
        good_lines_in_run = stats['good']
        newly_purged = stats['newly_forbidden']
        
        total_in_forbidden_file = total_forbidden_stats[app_name]
        
        # As per user request: Original Lines = (Lines in purified file) + (Total lines in forbidden file)
        # Note: 'good_lines_in_run' is the count *after* the current purge.
        true_original_lines = good_lines_in_run + total_in_forbidden_file

        grand_total_good += good_lines_in_run
        grand_total_newly_purged += newly_purged
        
        percent_purged_overall = (total_in_forbidden_file / true_original_lines * 100) if true_original_lines > 0 else 0
        
        print(f"{app_name:<25} | {true_original_lines:>15,d} | {newly_purged:>15,d} | {total_in_forbidden_file:>15,d} | {percent_purged_overall:>19.2f}%")

    grand_total_forbidden = sum(total_forbidden_stats.values())
    grand_total_original_overall = grand_total_good + grand_total_forbidden

    print("-" * len(header))
    total_percent_purged_overall = (grand_total_forbidden / grand_total_original_overall * 100) if grand_total_original_overall > 0 else 0
    print(f"{'Total':<25} | {grand_total_original_overall:>15,d} | {grand_total_newly_purged:>15,d} | {grand_total_forbidden:>15,d} | {total_percent_purged_overall:>19.2f}%")
    print("\nPurge complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rewrite log files to separate entries from blocked IPs."
    )
    parser.add_argument(
        '--data-dir',
        default='../firewatch-data',
        help="The input directory containing log files (e.g., ../firewatch-data)."
    )
    parser.add_argument(
        '--forbidden-dir',
        default='../firewatch-data-forbidden',
        help="The output directory for forbidden log entries."
    )
    parser.add_argument(
        '--cache-file',
        default='static/cache/firewatch_cache.db',
        help="The path to the shelve cache file to purge."
    )
    
    args = parser.parse_args()
    
    main(args.data_dir, args.forbidden_dir, args.cache_file)
