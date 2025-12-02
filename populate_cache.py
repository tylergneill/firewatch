import argparse
import datetime
import shelve
import os
import time

from flask_app import app_names, LOG_FILES, LOG_FILE_PATH
from utils import get_log_sources_for_app, _process_single_log_file

"""
Usage: nice -n 19 python populate_cache.py --start-date 2025-11-01 --end-date 2025-11-30
"""

def populate_cache(start_date, end_date):
    """
    Populates the cache for all apps for a given date range.
    """
    print(f"Populating cache for dates: {start_date.isoformat()} to {end_date.isoformat()}")

    CACHE_DIR = "static/cache"
    os.makedirs(CACHE_DIR, exist_ok=True)
    CACHE_FILE = os.path.join(CACHE_DIR, "firewatch_cache.db")

    with shelve.open(CACHE_FILE) as cache:
        for app_name in app_names:
            print(f"  Processing app: {app_name}")
            log_files_for_app = get_log_sources_for_app(app_name, LOG_FILES, LOG_FILE_PATH, start_date, end_date)
            
            if not log_files_for_app:
                print(f"    No log files found for this date range.")
                continue

            for log_file in log_files_for_app:
                log_file_str = str(log_file)
                print(f"    Processing file: {log_file_str}")
                
                # We are explicitly populating the cache, so we don't check if it exists.
                # We just process and overwrite.
                processed_data = _process_single_log_file(log_file_str, app_names)
                cache[log_file_str] = processed_data
                
                # Throttle the script to be a good citizen
                time.sleep(0.05)
            
            print(f"    Finished processing {len(log_files_for_app)} file(s) for {app_name}.")

    print("\nCache population complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate the cache for the Firewatch application.")
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

    populate_cache(start, end)
