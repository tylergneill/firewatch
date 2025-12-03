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
        print(f"Error: Cache file '{cache_file}' not found. Please run learn_patterns.py first.", file=sys.stderr)
        sys.exit(1)

    all_analytics = {}
    try:
        with shelve.open(str(cache_file), 'r') as cache:
            banned_data_from_cache = cache.get('already_banned', {})
            not_yet_banned_flat = cache.get('not_yet_banned', {})
    except Exception as e:
        print(f"Error opening or reading cache file: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Print Already Banned Summary Table ---
    sorted_already_banned = sorted(
        banned_data_from_cache.items(),
        key=lambda item: item[1]['counts'].get('junk_probe_count', 0) + item[1]['counts'].get('restricted_path_count', 0),
        reverse=True
    )

    print("\n--- Already Banned Summary ---")
    headers = ["Banned Entity", "IPs", "Total Reqs", "Junk Probes", "Restricted", "Combined Violations", "Avg Violations/IP", "Violation Ratio"]
    header_fmt = "{:<18} | {:>5} | {:>10} | {:>11} | {:>10} | {:>19} | {:>17} | {:>15}"
    print(header_fmt.format(*headers))
    print("-" * 130)

    # --- Calculate Grand Totals for Already Banned ---
    grand_banned_ips_sum = 0
    grand_banned_reqs_sum = 0
    grand_banned_junk_sum = 0
    grand_banned_restricted_sum = 0
    for key, data in sorted_already_banned:
        counts = data['counts']
        grand_banned_ips_sum += len(data.get('ips', []))
        grand_banned_reqs_sum += counts.get('total_request_count', 0)
        grand_banned_junk_sum += counts.get('junk_probe_count', 0)
        grand_banned_restricted_sum += counts.get('restricted_path_count', 0)

    # --- Print Displayed Rows and calculate Displayed Totals for Already Banned ---
    displayed_banned_ips_sum = 0
    displayed_banned_reqs_sum = 0
    displayed_banned_junk_sum = 0
    displayed_banned_restricted_sum = 0
    printed_banned_entities_count = 0

    for key, data in sorted_already_banned[:top_n_ips]:
        counts = data['counts']
        ip_count = len(data.get('ips', []))
        total_reqs = counts.get('total_request_count', 0)
        junk_probes = counts.get('junk_probe_count', 0)
        restricted = counts.get('restricted_path_count', 0)
        combined_violations = junk_probes + restricted
        avg_violations = (combined_violations / ip_count) if ip_count > 0 else 0
        violation_ratio = (combined_violations / total_reqs) if total_reqs > 0 else 0
        
        row_data = [
            key, f"{ip_count:,}", f"{total_reqs:,}", f"{junk_probes:,}",
            f"{restricted:,}", f"{combined_violations:,}", f"{avg_violations:.2f}",
            f"{violation_ratio:.2%}"
        ]
        print(header_fmt.format(*row_data))
        
        displayed_banned_ips_sum += ip_count
        displayed_banned_reqs_sum += total_reqs
        displayed_banned_junk_sum += junk_probes
        displayed_banned_restricted_sum += restricted
        printed_banned_entities_count += 1
    
    print("-" * 130)

    # --- Print Total Rows for Already Banned ---
    displayed_combined_violations = displayed_banned_junk_sum + displayed_banned_restricted_sum
    displayed_avg_violations = (displayed_combined_violations / displayed_banned_ips_sum) if displayed_banned_ips_sum > 0 else 0
    displayed_violation_ratio = (displayed_combined_violations / displayed_banned_reqs_sum) if displayed_banned_reqs_sum > 0 else 0
    displayed_total_row = [
        "Total (Displayed)", f"{displayed_banned_ips_sum:,}", f"{displayed_banned_reqs_sum:,}",
        f"{displayed_banned_junk_sum:,}", f"{displayed_banned_restricted_sum:,}",
        f"{displayed_combined_violations:,}", f"{displayed_avg_violations:.2f}",
        f"{displayed_violation_ratio:.2%}"
    ]
    print(header_fmt.format(*displayed_total_row))

    grand_banned_combined_violations = grand_banned_junk_sum + grand_banned_restricted_sum
    grand_banned_avg_violations = (grand_banned_combined_violations / grand_banned_ips_sum) if grand_banned_ips_sum > 0 else 0
    grand_banned_violation_ratio = (grand_banned_combined_violations / grand_banned_reqs_sum) if grand_banned_reqs_sum > 0 else 0
    grand_total_row = [
        "Grand Total (All)", f"{grand_banned_ips_sum:,}", f"{grand_banned_reqs_sum:,}",
        f"{grand_banned_junk_sum:,}", f"{grand_banned_restricted_sum:,}",
        f"{grand_banned_combined_violations:,}", f"{grand_banned_avg_violations:.2f}",
        f"{grand_banned_violation_ratio:.2%}"
    ]
    print(header_fmt.format(*grand_total_row))
    print(f"\nDisplayed top {printed_banned_entities_count} of {len(sorted_already_banned)} total already banned entities.")
    # --- End Already Banned Summary ---


    # --- Grouping Logic for Not Yet Banned ---
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
    print(header_fmt.format(*headers))
    print("-" * 130)

    # Calculate Grand Totals for ALL lone IPs
    grand_lone_reqs_sum = sum(d.get('total_request_count', 0) for _, d in sorted_lone_ips)
    grand_lone_junk_sum = sum(d.get('junk_probe_count', 0) for _, d in sorted_lone_ips)
    grand_lone_restricted_sum = sum(d.get('restricted_path_count', 0) for _, d in sorted_lone_ips)

    # Print Displayed Rows and calculate Displayed Totals for Lone IPs
    displayed_lone_reqs_sum = 0
    displayed_lone_junk_sum = 0
    displayed_lone_restricted_sum = 0
    printed_lone_ips_count = 0

    for ip, data in sorted_lone_ips[:top_n_ips]:
        ip_count = 1
        total_reqs = data.get('total_request_count', 0)
        junk_probes = data.get('junk_probe_count', 0)
        restricted = data.get('restricted_path_count', 0)
        combined_violations = junk_probes + restricted
        avg_violations = combined_violations / ip_count
        violation_ratio = (combined_violations / total_reqs) if total_reqs > 0 else 0
        
        row_data = [
            ip, f"{ip_count:,}", f"{total_reqs:,}", f"{junk_probes:,}",
            f"{restricted:,}", f"{combined_violations:,}", f"{avg_violations:.2f}",
            f"{violation_ratio:.2%}"
        ]
        print(header_fmt.format(*row_data))

        displayed_lone_reqs_sum += total_reqs
        displayed_lone_junk_sum += junk_probes
        displayed_lone_restricted_sum += restricted
        printed_lone_ips_count += 1

    print("-" * 130)

    # --- Print Total Rows for Lone IPs ---
    displayed_combined_violations = displayed_lone_junk_sum + displayed_lone_restricted_sum
    displayed_avg_violations = (displayed_combined_violations / printed_lone_ips_count) if printed_lone_ips_count > 0 else 0
    displayed_violation_ratio = (displayed_combined_violations / displayed_lone_reqs_sum) if displayed_lone_reqs_sum > 0 else 0
    displayed_total_row = [
        "Total (Displayed)", f"{printed_lone_ips_count:,}", f"{displayed_lone_reqs_sum:,}",
        f"{displayed_lone_junk_sum:,}", f"{displayed_lone_restricted_sum:,}",
        f"{displayed_combined_violations:,}", f"{displayed_avg_violations:.2f}",
        f"{displayed_violation_ratio:.2%}"
    ]
    print(header_fmt.format(*displayed_total_row))

    grand_lone_combined_violations = grand_lone_junk_sum + grand_lone_restricted_sum
    grand_lone_avg_violations = (grand_lone_combined_violations / len(sorted_lone_ips)) if len(sorted_lone_ips) > 0 else 0
    grand_lone_violation_ratio = (grand_lone_combined_violations / grand_lone_reqs_sum) if grand_lone_reqs_sum > 0 else 0
    grand_total_row = [
        "Grand Total (All)", f"{len(sorted_lone_ips):,}", f"{grand_lone_reqs_sum:,}",
        f"{grand_lone_junk_sum:,}", f"{grand_lone_restricted_sum:,}",
        f"{grand_lone_combined_violations:,}", f"{grand_lone_avg_violations:.2f}",
        f"{grand_lone_violation_ratio:.2%}"
    ]
    print(header_fmt.format(*grand_total_row))
    print(f"\nDisplayed top {printed_lone_ips_count} of {len(sorted_lone_ips)} total lone IPs.")
    # --- End Top N Individual IPs ---

    # --- Print Top N CIDR Group Summary Table ---
    print("\n--- CIDR Group Summary (not_yet_banned) ---")
    print(header_fmt.format(*headers))
    print("-" * 130)

    # Calculate Grand Totals for ALL CIDR groups
    grand_cidr_ips_sum = sum(v['_summary'].get('individual_ip_count', 0) for _, v in sorted_cidr_groups)
    grand_cidr_reqs_sum = sum(v['_summary'].get('total_request_count', 0) for _, v in sorted_cidr_groups)
    grand_cidr_junk_sum = sum(v['_summary'].get('junk_probe_count', 0) for _, v in sorted_cidr_groups)
    grand_cidr_restricted_sum = sum(v['_summary'].get('restricted_path_count', 0) for _, v in sorted_cidr_groups)

    # Print Displayed Rows and calculate Displayed Totals for CIDR Groups
    displayed_cidr_ips_sum = 0
    displayed_cidr_reqs_sum = 0
    displayed_cidr_junk_sum = 0
    displayed_cidr_restricted_sum = 0
    printed_cidr_count = 0

    for cidr, value in sorted_cidr_groups[:top_n_ips]:
        summary = value['_summary']
        ip_count = summary.get('individual_ip_count', 0)
        total_reqs = summary.get('total_request_count', 0)
        junk_probes = summary.get('junk_probe_count', 0)
        restricted = summary.get('restricted_path_count', 0)
        combined_violations = junk_probes + restricted
        avg_violations = (combined_violations / ip_count) if ip_count > 0 else 0
        violation_ratio = (combined_violations / total_reqs) if total_reqs > 0 else 0
        
        row_data = [
            cidr, f"{ip_count:,}", f"{total_reqs:,}", f"{junk_probes:,}",
            f"{restricted:,}", f"{combined_violations:,}", f"{avg_violations:.2f}",
            f"{violation_ratio:.2%}"
        ]
        print(header_fmt.format(*row_data))

        displayed_cidr_ips_sum += ip_count
        displayed_cidr_reqs_sum += total_reqs
        displayed_cidr_junk_sum += junk_probes
        displayed_cidr_restricted_sum += restricted
        printed_cidr_count += 1
    
    print("-" * 130)

    # --- Print Total Rows for CIDR Groups ---
    displayed_combined_violations = displayed_cidr_junk_sum + displayed_cidr_restricted_sum
    displayed_avg_violations = (displayed_combined_violations / displayed_cidr_ips_sum) if displayed_cidr_ips_sum > 0 else 0
    displayed_violation_ratio = (displayed_combined_violations / displayed_cidr_reqs_sum) if displayed_cidr_reqs_sum > 0 else 0
    displayed_total_row = [
        "Total (Displayed)", f"{displayed_cidr_ips_sum:,}", f"{displayed_cidr_reqs_sum:,}",
        f"{displayed_cidr_junk_sum:,}", f"{displayed_cidr_restricted_sum:,}",
        f"{displayed_combined_violations:,}", f"{displayed_avg_violations:.2f}",
        f"{displayed_violation_ratio:.2%}"
    ]
    print(header_fmt.format(*displayed_total_row))

    grand_cidr_combined_violations = grand_cidr_junk_sum + grand_cidr_restricted_sum
    grand_cidr_avg_violations = (grand_cidr_combined_violations / grand_cidr_ips_sum) if grand_cidr_ips_sum > 0 else 0
    grand_cidr_violation_ratio = (grand_cidr_junk_sum / grand_cidr_reqs_sum) if grand_cidr_reqs_sum > 0 else 0 # Corrected calculation
    grand_total_row = [
        "Grand Total (All)", f"{grand_cidr_ips_sum:,}", f"{grand_cidr_reqs_sum:,}",
        f"{grand_cidr_junk_sum:,}", f"{grand_cidr_restricted_sum:,}",
        f"{grand_cidr_combined_violations:,}", f"{grand_cidr_avg_violations:.2f}",
        f"{grand_cidr_violation_ratio:.2%}"
    ]
    print(header_fmt.format(*grand_total_row))
    print(f"\nDisplayed top {printed_cidr_count} of {len(sorted_cidr_groups)} total CIDR blocks.")
    # --- End Summary Table ---

    # --- Final JSON Output ---
    # Combine sorted lists back for a comprehensive, sorted JSON output
    all_sorted_items = sorted(list(cidr_groups_dict.items()) + list(lone_ips_dict.items()), key=get_sort_key, reverse=True)
    all_analytics['not_yet_banned'] = dict(all_sorted_items)
    all_analytics['already_banned'] = banned_data_from_cache

    if output_file_path:
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
        default=None,
        help="Optional: Path for the output JSON file. If not provided, no file is written."
    )
    parser.add_argument(
        '--top-n-ips',
        type=int,
        default=10,
        help="The number of top individual IPs to display (defaults to 10)."
    )
    args = parser.parse_args()
    main(args.cache_file, args.output_file, args.top_n_ips)
