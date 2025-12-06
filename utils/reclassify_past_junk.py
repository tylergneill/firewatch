#!/usr/bin/env python3
import argparse
import ipaddress
import pathlib
import re
import shelve
import sys
from collections import deque, defaultdict

from junk_definitions import BLOCKED_NETWORKS, is_junk_probe
from utils import parse_line

"""
Usage: python reclassify_past_junk.py \
  --data-dir static/data \
  --junk-dir static/data \
  --cache-file static/cache/firewatch_cache.db
"""


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


def process_log_file(log_path: pathlib.Path, junk_dir: pathlib.Path):
    """
    Reads a log file, separates lines based on IP or junk URI, overwrites
    the original with clean lines, and writes blocked lines to the junk
    directory.
    """
    print(f"  Processing: {log_path}...")
    good_lines = deque()
    junk_lines = deque()

    try:
        with log_path.open('rb') as f:
            for line_bytes in f:
                # We need the raw bytes, but our logic needs to decode parts of it.
                # Let's get the required fields without fully depending on parse_line's success for performance.
                try:
                    # Quick split to get IP, faster than full regex for every line
                    ip = line_bytes.split(b' ', 3)[2].decode('utf-8')

                    # Also extract request URI for junk probing
                    # It's usually in the form "VERB /path HTTP/ver"
                    request_part = line_bytes.split(b'"', 2)
                    if len(request_part) > 1:
                        # e.g., 'GET /path HTTP/1.1'
                        full_request = request_part[1].decode('utf-8', errors='ignore')
                        # We only need the URI part
                        uri = full_request.split(' ')[1] if len(full_request.split(' ')) > 1 else ''
                    else:
                        uri = ''
                except (IndexError, UnicodeDecodeError):
                    # If line format is weird, treat as good and keep it
                    good_lines.append(line_bytes)
                    continue

                if is_ip_blocked(ip) or is_junk_probe(uri):
                    junk_lines.append(line_bytes)
                else:
                    good_lines.append(line_bytes)
    except FileNotFoundError:
        print(f"    - File not found, skipping: {log_path}")
        return None, None
    except Exception as e:
        print(f"    - Error reading file {log_path}: {e}")
        return None, None
    
    # --- Write junk logs ---
    if junk_lines:
        # Construct the output path.
        # For a path like .../{archive}/access/{logfile}, we want to write to .../{archive}/junk/{junkfile}
        if log_path.parent.name == 'access':
            junk_target_dir = log_path.parent.parent / 'junk'
        else:
            # Fallback for logs not in an 'access' directory.
            # Create a 'junk' subdirectory in the log's parent directory.
            junk_target_dir = log_path.parent / 'junk'

        junk_target_dir.mkdir(parents=True, exist_ok=True)
        
        # Add .junk suffix
        junk_filename = log_path.name.replace(".access.log", ".junk.log")
        final_junk_path = junk_target_dir / junk_filename

        with final_junk_path.open('ab') as f:
            f.writelines(junk_lines)
        print(f"    - Wrote {len(junk_lines)} lines to {final_junk_path}")
    else:
        print(f"    - No junk lines found in {log_path.name}.")

    # --- Overwrite original with purified logs ---
    with log_path.open('wb') as f:
        f.writelines(good_lines)
    
    print(f"    - Rewrote original file with {len(good_lines)} lines.")
    
    return len(good_lines), len(junk_lines)


def main(data_dir: str, junk_dir: str, cache_file: str):
    """
    Main function to find and process all log files.
    """
    data_path = pathlib.Path(data_dir)
    junk_path = pathlib.Path(junk_dir)

    if not data_path.is_dir():
        print(f"Error: Data directory not found at '{data_dir}'")
        sys.exit(1)

    print(f"Starting crawler purge for directory: {data_path}")
    print(f"Junk logs will be written to: {junk_path}")
    print(f"Purging cache entries from: {cache_file}")

    log_files = sorted(data_path.rglob('*.access.log*'))
    print(f"Found {len(log_files)} log files to process.\n")

    app_stats = defaultdict(lambda: {'good': 0, 'newly_junk': 0})

    with shelve.open(cache_file) as cache:
        for log_file in log_files:
            if log_file.is_file():
                app_name_parts = log_file.name.split('-app.access.log')
                app_name = app_name_parts[0] if app_name_parts else "unknown"

                good_count, junk_count = process_log_file(log_file, junk_path)
                if good_count is not None:
                    app_stats[app_name]['good'] += good_count
                    app_stats[app_name]['newly_junk'] += junk_count

                    # If we purged lines, the cache is stale and must be deleted.
                    if junk_count > 0:
                        # Use the absolute path as the key, just like the web app does.
                        log_file_key = str(log_file.resolve())
                        if log_file_key in cache:
                            print(f"    - Deleting stale cache entry for: {log_file.name}")
                            del cache[log_file_key]

    # --- Start Final Report Calculation ---
    print("\nCalculating final totals...")
    total_junk_stats = defaultdict(int)
    if junk_path.is_dir():
        junk_files = list(junk_path.rglob('*.junk'))
        for j_file in junk_files:
            app_name_parts = j_file.name.split('-app.access.log')
            app_name = app_name_parts[0] if app_name_parts else "unknown"
            with j_file.open('rb') as f:
                # Fast line counting
                lines = sum(1 for _ in f)
                total_junk_stats[app_name] += lines
    
    print("\n--- Purge Summary ---")
    header = f"{'Application':<25} | {'Original Lines':>15} | {'Just Purged':>15} | {'Total Junk':>15} | {'% Purged (Overall)':>20}"
    print(header)
    print("-" * len(header))

    grand_total_good = 0
    grand_total_newly_purged = 0
    grand_total_junk = 0

    # Combine keys from both stats dicts to not miss any app
    all_app_names = sorted(list(set(app_stats.keys()) | set(total_junk_stats.keys())))

    for app_name in all_app_names:
        stats = app_stats[app_name]
        good_lines_in_run = stats['good']
        newly_purged = stats['newly_junk']
        
        total_in_junk_file = total_junk_stats[app_name]
        
        # As per user request: Original Lines = (Lines in purified file) + (Total lines in junk file)
        # Note: 'good_lines_in_run' is the count *after* the current purge.
        true_original_lines = good_lines_in_run + total_in_junk_file

        grand_total_good += good_lines_in_run
        grand_total_newly_purged += newly_purged
        
        percent_purged_overall = (total_in_junk_file / true_original_lines * 100) if true_original_lines > 0 else 0
        
        print(f"{app_name:<25} | {true_original_lines:>15,d} | {newly_purged:>15,d} | {total_in_junk_file:>15,d} | {percent_purged_overall:>19.2f}%")

    grand_total_junk = sum(total_junk_stats.values())
    grand_total_original_overall = grand_total_good + grand_total_junk

    print("-" * len(header))
    total_percent_purged_overall = (grand_total_junk / grand_total_original_overall * 100) if grand_total_original_overall > 0 else 0
    print(f"{'Total':<25} | {grand_total_original_overall:>15,d} | {grand_total_newly_purged:>15,d} | {grand_total_junk:>15,d} | {total_percent_purged_overall:>19.2f}%")
    print("\nPurge complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rewrite log files to separate entries from blocked IPs."
    )
    parser.add_argument(
        '--data-dir',
        default='static/data',
        help="The input directory containing log files (e.g., ../firewatch-data)."
    )
    parser.add_argument(
        '--junk-dir',
        default='static/data',
        help="The output directory for junk log entries."
    )
    parser.add_argument(
        '--cache-file',
        default='static/cache/firewatch_cache.db',
        help="The path to the shelve cache file to purge."
    )
    
    args = parser.parse_args()
    
    main(args.data_dir, args.junk_dir, args.cache_file)
