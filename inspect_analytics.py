import shelve
import json
import pathlib
import sys
import argparse
import ipaddress
from collections import defaultdict, Counter

def get_sort_key(item):
    """
    Helper function to calculate the sort key (ratio) for an item in the
    'not_yet_banned' dictionary. It handles both CIDR groups and lone IPs.
    """
    key, value = item
    
    # Check if this is a CIDR group with a summary
    if '_summary' in value:
        counts = value['_summary']
    # Otherwise, it's a lone IP
    else:
        counts = value

    total = counts.get('total_request_count', 0)
    junk = counts.get('junk_probe_count', 0)

    if total == 0:
        return 0
    return junk / total

def main(cache_file_path: str, output_file_path: str, top_n_ips: int):
    """
    Reads analytics from a shelve cache, groups IPs by CIDR, sorts them,
    and writes the result to a JSON file.
    """
    cache_file = pathlib.Path(cache_file_path)

    if not cache_file.exists():
        print(f"Error: Cache file '{cache_file}' not found.", file=sys.stderr)
        sys.exit(1)

    all_analytics = {}
    try:
        with shelve.open(str(cache_file), 'r') as cache:
            all_analytics['already_banned'] = cache.get('already_banned', {})
            not_yet_banned_flat = cache.get('not_yet_banned', {})
    except Exception as e:
        print(f"Error opening or reading cache file: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Grouping Logic ---
    temp_grouped_by_cidr = defaultdict(dict)
    for ip_str, counts in not_yet_banned_flat.items():
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.version == 4:
                network = ipaddress.ip_network(f"{ip_str}/24", strict=False)
            else:
                network = ipaddress.ip_network(f"{ip_str}/64", strict=False)
            temp_grouped_by_cidr[str(network)][ip_str] = counts
        except ValueError:
            temp_grouped_by_cidr["invalid_ips"][ip_str] = counts

    final_not_yet_banned = {}
    for cidr, ips_in_group in temp_grouped_by_cidr.items():
        if len(ips_in_group) > 1:
            summary_counts = Counter()
            # Add the count of unique IPs in the group to the summary
            summary_counts['individual_ip_count'] = len(ips_in_group)
            for ip, data in ips_in_group.items():
                summary_counts.update(data)
            ips_in_group['_summary'] = dict(summary_counts)
            final_not_yet_banned[cidr] = ips_in_group
        else:
            ip, data = ips_in_group.popitem()
            final_not_yet_banned[ip] = data

    # --- Top 10 Individual IPs by Total Requests (not_yet_banned) ---
    all_individual_ips_data = []
    for key, value in final_not_yet_banned.items():
        if '_summary' in value:  # This is a CIDR group
            for ip, data in value.items():
                if ip != '_summary':
                    data['ip'] = ip
                    all_individual_ips_data.append(data)
        else:  # This is a lone IP
            value['ip'] = key
            all_individual_ips_data.append(value)

    all_individual_ips_data.sort(key=lambda x: x.get('total_request_count', 0), reverse=True)

    print(f"\n--- Top {top_n_ips} Individual IPs by Total Requests (not_yet_banned) ---")
    headers = ["IP Address", "IPs", "Total Reqs", "Junk Probes", "Restricted", "Junk Ratio"]
    header_fmt = "{:<18} | {:>3} | {:>10} | {:>11} | {:>10} | {:>10}"
    print(header_fmt.format(*headers))
    print("-" * 85)

    for data in all_individual_ips_data[:top_n_ips]:
        ip = data.get('ip', 'N/A')
        total_reqs = data.get('total_request_count', 0)
        junk_probes = data.get('junk_probe_count', 0)
        restricted = data.get('restricted_path_count', 0)
        ratio = (junk_probes / total_reqs) if total_reqs > 0 else 0
        
        row_data = [
            ip,
            1,
            f"{total_reqs:,}",
            f"{junk_probes:,}",
            f"{restricted:,}",
            f"{ratio:.2%}"
        ]
        print(header_fmt.format(*row_data))
    print("-" * 85)
    # --- End Top 10 Individual IPs ---

    # --- Sorting Logic ---
    sorted_items = sorted(final_not_yet_banned.items(), key=get_sort_key, reverse=True)
    sorted_not_yet_banned = dict(sorted_items)
    all_analytics['not_yet_banned'] = sorted_not_yet_banned
    # --- End Sorting ---

    # --- Print Summary Table to Console ---
    print("\n--- CIDR Group Summary (not_yet_banned) ---")
    headers = ["CIDR Block", "IPs", "Total Reqs", "Junk Probes", "Restricted", "Junk Ratio"]
    header_fmt = "{:<18} | {:>5} | {:>10} | {:>11} | {:>10} | {:>10}"
    print(header_fmt.format(*headers))
    print("-" * 85)

    for key, value in sorted_not_yet_banned.items():
        if '_summary' in value:
            summary = value['_summary']
            cidr = key
            ip_count = summary.get('individual_ip_count', 0)
            total_reqs = summary.get('total_request_count', 0)
            junk_probes = summary.get('junk_probe_count', 0)
            restricted = summary.get('restricted_path_count', 0)
            ratio = (junk_probes / total_reqs) if total_reqs > 0 else 0
            
            row_data = [
                cidr,
                ip_count,
                f"{total_reqs:,}",
                f"{junk_probes:,}",
                f"{restricted:,}",
                f"{ratio:.2%}"
            ]
            print(header_fmt.format(*row_data))
    
    print("-" * 85)
    # --- End Summary Table ---

    try:
        with open(output_file_path, 'w') as f:
            json.dump(all_analytics, f, indent=2)
        print(f"\nSuccessfully wrote full grouped analytics to {output_file_path}")
    except Exception as e:
        print(f"Error writing to output file {output_file_path}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Read analytics from a shelve cache and write to a JSON file."
    )
    parser.add_argument(
        '--cache-file',
        default='static/cache/analytics.db',
        help="The path to the shelve cache file to read."
    )
    parser.add_argument(
        '--output-file',
        default='analytics_output.json',
        help="The path for the output JSON file."
    )
    parser.add_argument(
        '--top-n-ips',
        type=int,
        default=10,
        help="The number of top individual IPs to display (defaults to 10)."
    )
    args = parser.parse_args()
    main(args.cache_file, args.output_file, args.top_n_ips)
