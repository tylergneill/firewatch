import shelve
import json
import pathlib
import sys
import argparse
import ipaddress
from collections import defaultdict, Counter

"""
Usage: python inspect_analytics.py \
    --cache-file static/cache/analytics.db \
    --output-file analytics_output.json \
    --top-n-ips 10
"""


def get_sort_key(item):
    """
    Helper function to calculate the sort key (combined violations) for an item.
    It handles both CIDR groups and lone IPs.
    """
    key, value = item
    
    # Check if this is a CIDR group with a summary
    if '_summary' in value:
        counts = value['_summary']
    # Otherwise, it's a lone IP
    else:
        counts = value

    junk = counts.get('junk_probe_count', 0)
    restricted = counts.get('restricted_path_count', 0)
    return junk + restricted

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

    # --- Separate into CIDR groups and Lone IPs ---
    cidr_groups_dict = {}
    lone_ips_dict = {}
    for cidr, ips_in_group in temp_grouped_by_cidr.items():
        if len(ips_in_group) > 1:
            summary_counts = Counter()
            summary_counts['individual_ip_count'] = len(ips_in_group)
            for ip, data in ips_in_group.items():
                summary_counts.update(data)
            ips_in_group['_summary'] = dict(summary_counts)
            cidr_groups_dict[cidr] = ips_in_group
        else:
            ip, data = ips_in_group.popitem()
            lone_ips_dict[ip] = data

    # --- Sort Each Category Independently ---
    sorted_cidr_groups = sorted(cidr_groups_dict.items(), key=get_sort_key, reverse=True)
    sorted_lone_ips = sorted(lone_ips_dict.items(), key=get_sort_key, reverse=True)

    # --- Print Top N LONE IPs Table ---
    print(f"\n--- Top {top_n_ips} Individual IPs by Combined Violations (not_yet_banned) ---")
    headers_individual = ["IP Address", "Total Reqs", "Junk Probes", "Restricted", "Combined Violations", "Junk Ratio"]
    header_fmt_individual = "{:<18} | {:>10} | {:>11} | {:>10} | {:>19} | {:>10}"
    print(header_fmt_individual.format(*headers_individual))
    print("-" * 100)

    for ip, data in sorted_lone_ips[:top_n_ips]:
        total_reqs = data.get('total_request_count', 0)
        junk_probes = data.get('junk_probe_count', 0)
        restricted = data.get('restricted_path_count', 0)
        combined_violations = junk_probes + restricted
        ratio = (junk_probes / total_reqs) if total_reqs > 0 else 0
        
        row_data = [
            ip,
            f"{total_reqs:,}",
            f"{junk_probes:,}",
            f"{restricted:,}",
            f"{combined_violations:,}",
            f"{ratio:.2%}"
        ]
        print(header_fmt_individual.format(*row_data))
    print("-" * 100)
    print(f"\nDisplayed top {len(sorted_lone_ips[:top_n_ips])} of {len(sorted_lone_ips)} total lone IPs.")
    # --- End Top N Individual IPs ---

    # --- Print Top N CIDR Group Summary Table ---
    print("\n--- CIDR Group Summary (not_yet_banned) ---")
    headers_cidr = ["CIDR Block", "IPs", "Total Reqs", "Junk Probes", "Restricted", "Combined Violations", "Avg Violations/IP", "Junk Ratio"]
    header_fmt_cidr = "{:<18} | {:>5} | {:>10} | {:>11} | {:>10} | {:>19} | {:>17} | {:>10}"
    print(header_fmt_cidr.format(*headers_cidr))
    print("-" * 120)

    total_ips_in_displayed_cidrs = 0
    for cidr, value in sorted_cidr_groups[:top_n_ips]:
        summary = value['_summary']
        ip_count = summary.get('individual_ip_count', 0)
        total_reqs = summary.get('total_request_count', 0)
        junk_probes = summary.get('junk_probe_count', 0)
        restricted = summary.get('restricted_path_count', 0)
        combined_violations = junk_probes + restricted
        avg_violations_per_ip = (combined_violations / ip_count) if ip_count > 0 else 0
        ratio = (junk_probes / total_reqs) if total_reqs > 0 else 0
        
        row_data = [
            cidr,
            ip_count,
            f"{total_reqs:,}",
            f"{junk_probes:,}",
            f"{restricted:,}",
            f"{combined_violations:,}",
            f"{avg_violations_per_ip:.2f}",
            f"{ratio:.2%}"
        ]
        print(header_fmt_cidr.format(*row_data))
        total_ips_in_displayed_cidrs += ip_count
    
    print("-" * 120)
    print(f"\nDisplayed top {len(sorted_cidr_groups[:top_n_ips])} of {len(sorted_cidr_groups)} total CIDR blocks, comprising {total_ips_in_displayed_cidrs:,} individual IPs.")
    # --- End Summary Table ---

    # --- Final JSON Output ---
    # Combine sorted lists back for a comprehensive, sorted JSON output
    all_sorted_items = sorted(list(cidr_groups_dict.items()) + list(lone_ips_dict.items()), key=get_sort_key, reverse=True)
    all_analytics['not_yet_banned'] = dict(all_sorted_items)

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
