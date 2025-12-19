import argparse
import datetime
import shelve
import os
import time
import sys
from pathlib import Path

"""
Usage Options:
    python utils/update_cache.py --rebuild-all  # for a full refresh
    python utils/update_cache.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD  # for a partial update
"""


# Add project root to path to allow importing from flask_app
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.constants import app_names, LOG_FILE_PATH
from utils.utils import get_log_sources_for_app, _process_single_log_file, get_junk_log_sources_for_app, \
    _process_single_junk_log_file

"""
Usage: nice -n 19 python update_cache.py --start-date 2025-03-01 --end-date 2025-10-31
"""


def update_cache(start_date, end_date, rebuild_all=False, cache_file=None, data_dir=None):
    """
    Populates the cache for all apps.
    If rebuild_all is True, clears the cache and processes all logs.
    Otherwise, updates only the logs within the given date range.
    """
    if rebuild_all:
        print("Rebuilding entire cache (Scorched Earth Mode)...")
        # Set a wide date range to capture all logs
        start_date = datetime.date(2020, 1, 1)
        end_date = datetime.date.today()
    else:
        print(f"Updating cache for dates: {start_date.isoformat()} to {end_date.isoformat()}")

    CACHE_FILE = Path(cache_file).resolve()
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
    data_path = Path(data_dir).resolve()


    if rebuild_all and CACHE_FILE.exists():
        print(f"  - Deleting existing cache file: {CACHE_FILE}")
        # shelve creates multiple files, so we need to remove them all
        # Common extensions are .db, .dat, .bak, .dir or no extension + .db (bsddb)
        # But the globs below should cover the standard cases on Linux/Mac
        for f in CACHE_FILE.parent.glob(f"{CACHE_FILE.name}*"):
            try:
                f.unlink()
            except OSError as e:
                print(f"    Error deleting {f}: {e}")

    with shelve.open(str(CACHE_FILE)) as cache:
        for app_name in app_names:
            print(f"  Processing app: {app_name}")

            # Process access logs
            access_log_files_for_app = get_log_sources_for_app(app_name, data_path, start_date, end_date)
            if not access_log_files_for_app:
                print(f"    No access log files found for this date range.")
            else:
                for log_file in access_log_files_for_app:
                    log_file_str = str(log_file)
                    print(f"    Processing access file: {log_file_str}")
                    processed_data = _process_single_log_file(log_file_str, app_name)
                    cache[log_file_str] = processed_data
                    time.sleep(0.05)
                print(f"    Finished processing {len(access_log_files_for_app)} access file(s) for {app_name}.")

            # Process junk logs
            junk_log_files_for_app = get_junk_log_sources_for_app(app_name, data_path, start_date, end_date)
            if not junk_log_files_for_app:
                print(f"    No junk log files found for this date range.")
            else:
                for log_file in junk_log_files_for_app:
                    log_file_str = str(log_file)
                    print(f"    Processing junk file: {log_file_str}")
                    processed_data = _process_single_junk_log_file(log_file_str, app_name)
                    cache[f"junk_{log_file_str}"] = processed_data
                    time.sleep(0.05)
                print(f"    Finished processing {len(junk_log_files_for_app)} junk file(s) for {app_name}.")

    print("\nCache update complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update the cache for the Firewatch application.")
    
    # Create a mutually exclusive group so user must pick a strategy
    mode_group = parser.add_argument_group('Update Mode')
    
    # Option 1: Selective update (requires dates)
    mode_group.add_argument(
        '--start-date',
        help="Start date in YYYY-MM-DD format. Required unless --rebuild-all is set."
    )
    mode_group.add_argument(
        '--end-date',
        help="End date in YYYY-MM-DD format. Required unless --rebuild-all is set."
    )
    
    # Option 2: Scorched earth (no dates needed)
    mode_group.add_argument(
        '--rebuild-all',
        action='store_true',
        help="Delete the existing cache and process ALL available log files from scratch."
    )

    parser.add_argument(
        '--data-dir',
        default="static/data",
        help="Path to the data directory containing log files (default: static/data)"
    )
    parser.add_argument(
        '--cache-file',
        default="static/cache/firewatch_cache.db",
        help="Path to the shelve cache file (default: static/cache/firewatch_cache.db)"
    )

    args = parser.parse_args()

    # Validation
    if args.rebuild_all:
        if args.start_date or args.end_date:
            print("Warning: --start-date and --end-date are ignored when --rebuild-all is set.")
        start = None
        end = None
    else:
        if not args.start_date or not args.end_date:
            parser.error("Both --start-date and --end-date are required for selective update mode.")
        
        try:
            start = datetime.date.fromisoformat(args.start_date)
            end = datetime.date.fromisoformat(args.end_date)
        except ValueError:
            print("Error: Dates must be in YYYY-MM-DD format.")
            exit(1)

    update_cache(start, end, rebuild_all=args.rebuild_all, cache_file=args.cache_file, data_dir=args.data_dir)
