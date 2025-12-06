#!/usr/bin/env python3
import shelve
import json
import pathlib
import sys
import argparse
import ipaddress
import datetime
from collections import defaultdict, Counter
from tqdm import tqdm

"""
Usage: python inspect_analytics.py --cache-file <path> [options]

A tool to inspect the analytics cache, generate reports, and create banlists.
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
    Groups, sorts, and prints summary tables for a given data category.
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

    # --- Print Top N Lone IPs Table ---
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


def analyze_and_print_ratios(access_only_flat: dict):
    """
    Analyzes the 'access_only' data to show the distribution of
    restricted path violation ratios.
    """
    if not access_only_flat:
        print("\nNo 'access_only' data found to analyze for ratios.")
        return
    bins = [{'ip_count': 0, 'req_count': 0} for _ in range(10)]
    total_ips_analyzed = 0
    for ip, data in access_only_flat.items():
        total_reqs = data.get('total_request_count', 0)
        if total_reqs > 0:
            total_ips_analyzed += 1
            restricted = data.get('restricted_path_count', 0)
            ratio = restricted / total_reqs
            bin_index = min(9, int(ratio * 10))
            bins[bin_index]['ip_count'] += 1
            bins[bin_index]['req_count'] += total_reqs
    print("\n--- Distribution of Restricted Path Violation Ratios ('access_only' IPs) ---")
    print("-" * 80)
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

# --- Banlist generation functions (from generate_banlist.py) ---


def group_ips_into_cidrs(ip_list: list) -> list:
    """
    Takes a flat list of IP address strings and groups them into
    /24 CIDR blocks where possible.
    """
    cidrs = defaultdict(list)
    for ip_str in ip_list:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.version == 4:
                network = ipaddress.ip_network(f"{ip_str}/24", strict=False)
                cidrs[str(network)].append(ip_str)
            else:
                cidrs[ip_str].append(ip_str)
        except ValueError:
            continue
    final_list = []
    for cidr, ips in cidrs.items():
        if len(ips) > 5 or len(ips) > (254 * 0.05):
            final_list.append(cidr)
        else:
            final_list.extend(ips)
    return sorted(final_list)


def write_ban_list_file(filename: str, header: str, ban_list: list):
    """Writes the ban list and its metadata header to a file."""
    try:
        with open(filename, 'w') as f:
            f.write(header)
            f.write("\n".join(ban_list))
        print(f"\nSuccessfully wrote ban list to {filename}")
    except Exception as e:
        print(f"\nError writing to output file {filename}: {e}", file=sys.stderr)


def generate_banlists(not_yet_banned_flat: dict, access_only_flat: dict, threshold: float, junk_output_file: str,
                      restricted_output_file: str):
    """
    Generates ban lists from the analytics cache data.
    """
    # Generate Ban List for Junk Probers
    if not_yet_banned_flat:
        print("\n--- Generating Junk Prober Ban List ---")
        junk_prober_ips = list(not_yet_banned_flat.keys())
        total_requests = sum(v.get('total_request_count', 0) for v in not_yet_banned_flat.values())
        compressed_list = group_ips_into_cidrs(junk_prober_ips)
        header = (
            f"# Ban list for junk-probe IPs.\n"
            f"# Generated by: {pathlib.Path(__file__).name} at {datetime.datetime.now().isoformat()}\n"
            f"# Total unique IPs: {len(junk_prober_ips):,}\n"
            f"# Total associated requests: {total_requests:,}\n"
            f"# Compressed to {len(compressed_list):,} entries.\n#\n"
        )
        write_ban_list_file(junk_output_file, header, compressed_list)
    else:
        print("\nNo 'not_yet_banned' data found, skipping junk prober ban list.")

    # Generate Ban List for Restricted Path Violators
    if access_only_flat:
        print(f"\n--- Generating Restricted Path Violator Ban List (Threshold > {threshold:.0%}) ---")
        violator_ips = [
            ip for ip, data in access_only_flat.items()
            if data.get('total_request_count', 0) > 0 and (data.get('restricted_path_count', 0) / data['total_request_count']) > threshold
        ]
        total_requests = sum(access_only_flat[ip].get('total_request_count', 0) for ip in violator_ips)
        compressed_list = group_ips_into_cidrs(violator_ips)
        header = (
            f"# Ban list for restricted-path violators (>{threshold:.0%} violation ratio).\n"
            f"# Generated by: {pathlib.Path(__file__).name} at {datetime.datetime.now().isoformat()}\n"
            f"# Total unique IPs found: {len(violator_ips):,}\n"
            f"# Total associated requests: {total_requests:,}\n"
            f"# Compressed to {len(compressed_list):,} entries.\n#\n"
        )
        write_ban_list_file(restricted_output_file, header, compressed_list)
    else:
        print("\nNo 'access_only' data found, skipping restricted path violator ban list.")

# --- Main execution ---

def main(args):
    """
    Main function to read cache and orchestrate analysis and reporting.
    """
    cache_file = pathlib.Path(args.cache_file)
    if not cache_file.exists():
        # Corrected the error message to point to the new script name
        print(f"Error: Cache file '{cache_file}' not found. Please run recognize_junk_in_access.py first.", file=sys.stderr)
        sys.exit(1)
    try:
        with shelve.open(str(cache_file), 'r') as cache:
            banned_data_from_cache = cache.get('already_banned', {})
            not_yet_banned_flat = cache.get('not_yet_banned', {})
            access_only_flat = cache.get('access_only', {})
    except Exception as e:
        print(f"Error opening or reading cache file: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Standard Inspection Report ---
    if args.run_inspection:
        headers = ["Entity", "IPs", "Total Reqs", "Junk Probes", "Restricted", "Combined Violations", "Avg Violations/IP", "Violation Ratio"]
        header_fmt = "{:<18} | {:>5} | {:>10} | {:>11} | {:>10} | {:>19} | {:>17} | {:>15}"
        print("\n--- Already Banned Summary ---")
        print(header_fmt.format(*headers))
        # ... (logic from original main to print already_banned table)
        sorted_already_banned = sorted(banned_data_from_cache.items(), key=lambda item: item[1]['counts'].get('junk_probe_count', 0) + item[1]['counts'].get('restricted_path_count', 0), reverse=True)
        for key, data in sorted_already_banned[:args.top_n]:
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
        all_analytics = {'already_banned': banned_data_from_cache}
        all_analytics['not_yet_banned'] = process_and_display_category("Not Yet Banned", not_yet_banned_flat, args.top_n, headers, header_fmt)
        all_analytics['access_only'] = process_and_display_category("Access Only", access_only_flat, args.top_n, headers, header_fmt)
        if args.output_file:
            try:
                with open(args.output_file, 'w') as f:
                    json.dump(all_analytics, f, indent=2)
                print(f"\nSuccessfully wrote full grouped analytics to {args.output_file}")
            except Exception as e:
                print(f"Error writing to output file {args.output_file}: {e}", file=sys.stderr)

    # --- Optional Analyses ---
    if args.analyze_ratios:
        analyze_and_print_ratios(access_only_flat)
    if args.generate_banlist:
        generate_banlists(not_yet_banned_flat, access_only_flat, args.threshold, args.output_junk_file, args.output_restricted_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inspect analytics cache, generate reports, analyze ratios, and create banlists.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # General arguments
    parser.add_argument('--cache-file', default='static/cache/analytics.db', help="Path to the shelve cache file.")
    # Inspection report arguments
    inspection_group = parser.add_argument_group('Inspection Report')
    inspection_group.add_argument('--inspection-json-file', default=None, help="Optional path for the JSON output of the inspection report.")
    inspection_group.add_argument('--inspection-table-top-n', type=int, default=10, help="Number of top entries to display in tables.")
    # Ratio analysis arguments
    ratio_group = parser.add_argument_group('Ratio Analysis')
    ratio_group.add_argument('--analyze-ratios', action='store_true', help="Analyze and display the distribution of restricted path violation ratios.")
    # Banlist generation arguments
    banlist_group = parser.add_argument_group('Banlist Generation')
    banlist_group.add_argument('--generate-banlist', action='store_true', help="Generate ban lists based on the analysis.")
    banlist_group.add_argument('--threshold', type=float, default=0.8, help="Violation ratio threshold for banning IPs from 'access_only' data.")
    banlist_group.add_argument('--output-junk-file', default='junk_probers_banlist.txt', help="Output file for the junk probers ban list.")
    banlist_group.add_argument('--output-restricted-file', default='restricted_violators_banlist.txt', help="Output file for the restricted path violators ban list.")
    args = parser.parse_args()
    main(args)
