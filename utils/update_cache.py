import argparse
import datetime
import shelve
import os
import time
import sys
from pathlib import Path

# Add project root to path to allow importing from flask_app
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.constants import app_names, LOG_FILE_PATH
from utils.utils import get_log_sources_for_app, _process_single_log_file, get_junk_log_sources_for_app, \
    _process_single_junk_log_file

"""
Usage: nice -n 19 python update_cache.py --start-date 2025-03-01 --end-date 2025-10-31
"""


def update_cache(start_date, end_date):
    """
    Populates the cache for all apps for a given date range.
    """
    print(f"Updating cache for dates: {start_date.isoformat()} to {end_date.isoformat()}")

    CACHE_DIR = "../static/cache"
    os.makedirs(CACHE_DIR, exist_ok=True)
    CACHE_FILE = os.path.join(CACHE_DIR, "firewatch_cache.db")

    with shelve.open(CACHE_FILE) as cache:
        for app_name in app_names:
            print(f"  Processing app: {app_name}")

            # Process access logs
            access_log_files_for_app = get_log_sources_for_app(app_name, LOG_FILE_PATH, start_date, end_date)
            if not access_log_files_for_app:
                print(f"    No access log files found for this date range.")
            else:
                for log_file in access_log_files_for_app:
                    log_file_str = str(log_file)
                    print(f"    Processing access file: {log_file_str}")
                    processed_data = _process_single_log_file(log_file_str, app_names)
                    cache[log_file_str] = processed_data
                    time.sleep(0.05)
                print(f"    Finished processing {len(access_log_files_for_app)} access file(s) for {app_name}.")

            # Process junk logs
            junk_log_files_for_app = get_junk_log_sources_for_app(app_name, LOG_FILE_PATH, start_date, end_date)
            if not junk_log_files_for_app:
                print(f"    No junk log files found for this date range.")
            else:
                for log_file in junk_log_files_for_app:
                    log_file_str = str(log_file)
                    print(f"    Processing junk file: {log_file_str}")
                    processed_data = _process_single_junk_log_file(log_file_str, app_names)
                    cache[f"junk_{log_file_str}"] = processed_data
                    time.sleep(0.05)
                print(f"    Finished processing {len(junk_log_files_for_app)} junk file(s) for {app_name}.")

    print("\nCache update complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update the cache for the Firewatch application.")
    parser.add_argument(
        '--start-date',
        required=True,
        help="Start date in YYYY-MM-DD format."
    )
    parser.add_argument(
        '--end-date',
        required=True,
        help="End date in YYYY-MM-DD format."
    )

    args = parser.parse_args()

    try:
        start = datetime.date.fromisoformat(args.start_date)
        end = datetime.date.fromisoformat(args.end_date)
    except ValueError:
        print("Error: Dates must be in YYYY-MM-DD format.")
        exit(1)

    update_cache(start, end)
