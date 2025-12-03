import shelve
import json
import pathlib
import sys

cache_file = pathlib.Path('static/cache/analytics.db')

if not cache_file.exists():
    print(f"Error: Cache file '{cache_file}' not found.", file=sys.stderr)
    sys.exit(1)

all_analytics = {}
try:
    with shelve.open(str(cache_file)) as cache:
        for ip, date_data in cache.items():
            all_analytics[ip] = {}
            # shelve stores dict-like objects, ensure they are copied
            # to avoid issues with direct modification in another session
            for datestamp, counts in date_data.items():
                all_analytics[ip][datestamp] = counts
except Exception as e:
    print(f"Error opening or reading cache file: {e}", file=sys.stderr)
    sys.exit(1)

print(json.dumps(all_analytics, indent=2))
