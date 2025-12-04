import shelve
import pathlib
import sys
from collections import Counter
import argparse

def analyze_and_print_ratios(cache_file_path: str):
    """
    Analyzes the 'access_only' data to show the distribution of
    restricted path violation ratios.
    """
    cache_file = pathlib.Path(cache_file_path)
    if not cache_file.exists():
        print(f"Error: Cache file '{cache_file}' not found. Please run generate_analytics.py first.", file=sys.stderr)
        sys.exit(1)

    try:
        with shelve.open(str(cache_file), 'r') as cache:
            access_only_flat = cache.get('access_only', {})
    except Exception as e:
        print(f"Error opening or reading cache file: {e}", file=sys.stderr)
        sys.exit(1)

    if not access_only_flat:
        print("No 'access_only' data found in the cache.")
        return

    # --- Bin the Ratios into 10% increments ---
    # Each bin will store a dict: {'ip_count': X, 'req_count': Y}
    bins = [{'ip_count': 0, 'req_count': 0} for _ in range(10)]
    total_ips_analyzed = 0

    for ip, data in access_only_flat.items():
        total_reqs = data.get('total_request_count', 0)
        if total_reqs > 0:
            total_ips_analyzed += 1
            restricted = data.get('restricted_path_count', 0)
            ratio = restricted / total_reqs
            
            if ratio >= 1.0:
                bin_index = 9
            else:
                bin_index = int(ratio * 10)
            
            bins[bin_index]['ip_count'] += 1
            bins[bin_index]['req_count'] += total_reqs
            
    # --- Print the Histogram ---
    print("\nDistribution of Restricted Path Violation Ratios ('access_only' IPs)")
    print("-" * 80)
    
    # Scale the bar based on IP count
    max_ip_count = max(b['ip_count'] for b in bins) if any(b['ip_count'] for b in bins) else 1
    scale = 50 / max_ip_count

    for i, bin_data in enumerate(bins):
        ip_count = bin_data['ip_count']
        req_count = bin_data['req_count']
        bar = '█' * int(ip_count * scale)
        label_start = i * 10
        label_end = (i + 1) * 10
        print(f"{label_start:2d}%-{label_end:3d}% | {bar} ({ip_count:,} IPs, {req_count:,} Reqs)")
        
    print("-" * 80)
    print(f"Total IPs analyzed: {total_ips_analyzed:,}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze 'access_only' data to show the distribution of restricted path violation ratios."
    )
    parser.add_argument(
        '--cache-file',
        default='static/cache/analytics.db',
        help="Path to the shelve cache file (e.g., static/cache/analytics.db)."
    )
    args = parser.parse_args()
    analyze_and_print_ratios(args.cache_file)
