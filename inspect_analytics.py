import shelve
import json
import pathlib
import sys
import argparse
import ipaddress
from collections import defaultdict, Counter
from tqdm import tqdm

"""
Usage: python inspect_analytics.py \
    --cache-file static/cache/analytics.db \
    --top-n 10
"""

def get_sort_key(item):
    """
    Helper function to calculate the sort key (combined violations) for an item.
    It handles both CIDR groups and lone IPs.
    """
    key, value = item
    
    if '_summary' in value:
        counts = value['_summary']
    else:
        counts = value

    junk = counts.get('junk_probe_count', 0)
    restricted = counts.get('restricted_path_count', 0)
    return junk + restricted

def process_and_display_category(category_name: str, flat_data: dict, top_n: int, headers: list, header_fmt: str):
    """
    Groups, sorts, and prints summary tables for a given data category ('not_yet_banned' or 'access_only').
    """
    # --- Grouping Logic ---
    temp_grouped_by_cidr = defaultdict(dict)
    for ip_str, counts in tqdm(flat_data.items(), desc=f"Grouping {category_name} CIDRs", unit=" IP"):
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
    for cidr, ips_in_group in tqdm(temp_grouped_by_cidr.items(), desc=f"Separating {category_name} IPs", unit=" CIDR"):
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
    print(f"\n--- Top {top_n} Individual IPs by Combined Violations ({category_name}) ---")
    print(header_fmt.format(*headers))
    print("-" * 130)

    grand_lone_reqs = sum(d.get('total_request_count', 0) for _, d in sorted_lone_ips)
    grand_lone_junk = sum(d.get('junk_probe_count', 0) for _, d in sorted_lone_ips)
    grand_lone_restricted = sum(d.get('restricted_path_count', 0) for _, d in sorted_lone_ips)
    
    disp_lone_reqs, disp_lone_junk, disp_lone_restricted, printed_lone_count = 0, 0, 0, 0

    for ip, data in sorted_lone_ips[:top_n]:
        total_reqs, junk, restricted = data.get('total_request_count', 0), data.get('junk_probe_count', 0), data.get('restricted_path_count', 0)
        combined = junk + restricted
        violation_ratio = (combined / total_reqs) if total_reqs > 0 else 0
        
        row = [ip, 1, f"{total_reqs:,}", f"{junk:,}", f"{restricted:,}", f"{combined:,}", f"{combined:.2f}", f"{violation_ratio:.2%}"]
        print(header_fmt.format(*row))

        disp_lone_reqs += total_reqs
        disp_lone_junk += junk
        disp_lone_restricted += restricted
        printed_lone_count += 1
    
    print("-" * 130)
    disp_lone_combined = disp_lone_junk + disp_lone_restricted
    disp_lone_avg_viol = (disp_lone_combined / printed_lone_count) if printed_lone_count > 0 else 0
    disp_lone_viol_ratio = (disp_lone_combined / disp_lone_reqs) if disp_lone_reqs > 0 else 0
    displayed_total_row = ["Total (Displayed)", f"{printed_lone_count:,}", f"{disp_lone_reqs:,}", f"{disp_lone_junk:,}", f"{disp_lone_restricted:,}", f"{disp_lone_combined:,}", f"{disp_lone_avg_viol:.2f}", f"{disp_lone_viol_ratio:.2%}"]
    print(header_fmt.format(*displayed_total_row))

    grand_lone_combined = grand_lone_junk + grand_lone_restricted
    grand_lone_avg_viol = (grand_lone_combined / len(sorted_lone_ips)) if sorted_lone_ips else 0
    grand_lone_viol_ratio = (grand_lone_combined / grand_lone_reqs) if grand_lone_reqs > 0 else 0
    grand_total_row = ["Grand Total (All)", f"{len(sorted_lone_ips):,}", f"{grand_lone_reqs:,}", f"{grand_lone_junk:,}", f"{grand_lone_restricted:,}", f"{grand_lone_combined:,}", f"{grand_lone_avg_viol:.2f}", f"{grand_lone_viol_ratio:.2%}"]
    print(header_fmt.format(*grand_total_row))
    print(f"\nDisplayed top {printed_lone_count} of {len(sorted_lone_ips)} total lone IPs.")

    # --- Print Top N CIDR Group Summary Table ---
    print(f"\n--- CIDR Group Summary ({category_name}) ---")
    print(header_fmt.format(*headers))
    print("-" * 130)

    grand_cidr_ips = sum(v['_summary'].get('individual_ip_count', 0) for _, v in sorted_cidr_groups)
    grand_cidr_reqs = sum(v['_summary'].get('total_request_count', 0) for _, v in sorted_cidr_groups)
    grand_cidr_junk = sum(v['_summary'].get('junk_probe_count', 0) for _, v in sorted_cidr_groups)
    grand_cidr_restricted = sum(v['_summary'].get('restricted_path_count', 0) for _, v in sorted_cidr_groups)
    
    disp_cidr_ips, disp_cidr_reqs, disp_cidr_junk, disp_cidr_restricted, printed_cidr_count = 0, 0, 0, 0, 0
    
    for cidr, value in sorted_cidr_groups[:top_n]:
        summary = value['_summary']
        ip_count, total_reqs, junk, restricted = summary.get('individual_ip_count', 0), summary.get('total_request_count', 0), summary.get('junk_probe_count', 0), summary.get('restricted_path_count', 0)
        combined = junk + restricted
        avg_viol = (combined / ip_count) if ip_count > 0 else 0
        viol_ratio = (combined / total_reqs) if total_reqs > 0 else 0
        row = [cidr, f"{ip_count:,}", f"{total_reqs:,}", f"{junk:,}", f"{restricted:,}", f"{combined:,}", f"{avg_viol:.2f}", f"{viol_ratio:.2%}"]
        print(header_fmt.format(*row))

        disp_cidr_ips += ip_count
        disp_cidr_reqs += total_reqs
        disp_cidr_junk += junk
        disp_cidr_restricted += restricted
        printed_cidr_count += 1
    
    print("-" * 130)
    disp_cidr_combined = disp_cidr_junk + disp_cidr_restricted
    disp_cidr_avg_viol = (disp_cidr_combined / disp_cidr_ips) if disp_cidr_ips > 0 else 0
    disp_cidr_viol_ratio = (disp_cidr_combined / disp_cidr_reqs) if disp_cidr_reqs > 0 else 0
    displayed_total_row = ["Total (Displayed)", f"{disp_cidr_ips:,}", f"{disp_cidr_reqs:,}", f"{disp_cidr_junk:,}", f"{disp_cidr_restricted:,}", f"{disp_cidr_combined:,}", f"{disp_cidr_avg_viol:.2f}", f"{disp_cidr_viol_ratio:.2%}"]
    print(header_fmt.format(*displayed_total_row))

    grand_cidr_combined = grand_cidr_junk + grand_cidr_restricted
    grand_cidr_avg_viol = (grand_cidr_combined / grand_cidr_ips) if grand_cidr_ips > 0 else 0
    grand_cidr_viol_ratio = (grand_cidr_combined / grand_cidr_reqs) if grand_cidr_reqs > 0 else 0
    grand_total_row = ["Grand Total (All)", f"{grand_cidr_ips:,}", f"{grand_cidr_reqs:,}", f"{grand_cidr_junk:,}", f"{grand_cidr_restricted:,}", f"{grand_cidr_combined:,}", f"{grand_cidr_avg_viol:.2f}", f"{grand_cidr_viol_ratio:.2%}"]
    print(header_fmt.format(*grand_total_row))
    print(f"\nDisplayed top {printed_cidr_count} of {len(sorted_cidr_groups)} total CIDR blocks.")
    
    all_sorted_items = sorted(list(cidr_groups_dict.items()) + list(lone_ips_dict.items()), key=get_sort_key, reverse=True)
    return dict(all_sorted_items)

def main(cache_file_path: str, output_file_path: str, top_n_ips: int):
    cache_file = pathlib.Path(cache_file_path)
    if not cache_file.exists():
        print(f"Error: Cache file '{cache_file}' not found. Please run generate_analytics.py first.", file=sys.stderr)
        sys.exit(1)

    try:
        with shelve.open(str(cache_file), 'r') as cache:
            banned_data_from_cache = cache.get('already_banned', {})
            not_yet_banned_flat = cache.get('not_yet_banned', {})
            access_only_flat = cache.get('access_only', {})
    except Exception as e:
        print(f"Error opening or reading cache file: {e}", file=sys.stderr)
        sys.exit(1)

    headers = ["Entity", "IPs", "Total Reqs", "Junk Probes", "Restricted", "Combined Violations", "Avg Violations/IP", "Violation Ratio"]
    header_fmt = "{:<18} | {:>5} | {:>10} | {:>11} | {:>10} | {:>19} | {:>17} | {:>15}"

    # --- Already Banned Table ---
    sorted_already_banned = sorted(banned_data_from_cache.items(), key=lambda item: item[1]['counts'].get('junk_probe_count', 0) + item[1]['counts'].get('restricted_path_count', 0), reverse=True)
    print("\n--- Already Banned Summary ---")
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
    
    # --- Process and Display Other Categories ---
    all_analytics = {'already_banned': banned_data_from_cache}
    all_analytics['not_yet_banned'] = process_and_display_category("Not Yet Banned", not_yet_banned_flat, top_n_ips, headers, header_fmt)
    all_analytics['access_only'] = process_and_display_category("Access Only", access_only_flat, top_n_ips, headers, header_fmt)

    if output_file_path:
        try:
            with open(output_file_path, 'w') as f:
                json.dump(all_analytics, f, indent=2)
            print(f"\nSuccessfully wrote full grouped analytics to {output_file_path}")
        except Exception as e:
            print(f"Error writing to output file {output_file_path}: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read analytics from a shelve cache and write to a JSON file.")
    parser.add_argument('--cache-file', default='static/cache/analytics.db', help="Path to the shelve cache file.")
    parser.add_argument('--output-file', default=None, help="Optional path for the output JSON file.")
    parser.add_argument('--top-n', type=int, default=10, help="Number of top entries to display in tables.")
    args = parser.parse_args()
    main(args.cache_file, args.output_file, args.top_n)

