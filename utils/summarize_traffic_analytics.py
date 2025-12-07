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
Usage: python summarize_traffic_analytics.py --db-file <path> [options]

A tool to inspect the traffic analytics db, generate reports, and create secondary junk tags.
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


def process_and_display_category(
    category_name: str, 
    flat_data: dict, 
    inspection_table_top_n: int, 
    headers: list, 
    header_fmt: str,
):
    """
    Groups, sorts, and prints summary tables for a given data category.
    """

    print(category_name.upper(), "\n")

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
    print(f"\n--- Top {inspection_table_top_n} Individual IPs by Combined Violations ({category_name}) ---")
    print(header_fmt.format(*headers))
    print("-" * 130)
    grand_lone_reqs = sum(d.get('total_request_count', 0) for _, d in sorted_lone_ips)
    grand_lone_junk = sum(d.get('junk_probe_count', 0) for _, d in sorted_lone_ips)
    grand_lone_restricted = sum(d.get('restricted_path_count', 0) for _, d in sorted_lone_ips)
    disp_lone_reqs, disp_lone_junk, disp_lone_restricted, printed_lone_count = 0, 0, 0, 0
    for ip, data in sorted_lone_ips[:inspection_table_top_n]:
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
    for cidr, value in sorted_cidr_groups[:inspection_table_top_n]:
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

    print("\n", "-" * 130, "\n")

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

# --- Secondary junk tag functions ---


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


def write_secondary_junk_tag_file(filename: str, header: str, ban_list: list):
    """Writes the junk tags and their metadata header to a file."""
    try:
        with open(filename, 'w') as f:
            f.write(header)
            f.write("\n".join(ban_list))
        print(f"\nSuccessfully wrote secondary junk tags to {filename}")
    except Exception as e:
        print(f"\nError writing to output file {filename}: {e}", file=sys.stderr)


def generate_secondary_junk_tags(
    not_yet_banned_flat: dict, 
    access_only_flat: dict, 
    threshold: float, 
    junk_probe_junk_tags_output_file: str,
    restricted_path_junk_tags_output_file: str,
):
    """
    Generates secondary junk tags from the traffic analytics db data.
    """
    # Generate secondary junk tags for Junk Probers
    if not_yet_banned_flat:
        print("\n--- Generating Junk Prober secondary junk tags ---")
        junk_prober_ips = list(not_yet_banned_flat.keys())
        total_requests = sum(v.get('total_request_count', 0) for v in not_yet_banned_flat.values())
        compressed_list = group_ips_into_cidrs(junk_prober_ips)
        header = (
            f"# secondary junk tags for junk-probe IPs.\n"
            f"# Generated by: {pathlib.Path(__file__).name} at {datetime.datetime.now().isoformat()}\n"
            f"# Total unique IPs: {len(junk_prober_ips):,}\n"
            f"# Total associated requests: {total_requests:,}\n"
            f"# Compressed to {len(compressed_list):,} entries.\n#\n"
        )
        write_secondary_junk_tag_file(
            junk_probe_junk_tags_output_file,
            header,
            compressed_list,
        )
    else:
        print("\nNo 'not_yet_banned' data found, skipping junk prober secondary junk tags.")

    # Generate secondary junk tags for Restricted Path Violators
    if access_only_flat:
        print(f"\n--- Generating Restricted Path Violator secondary junk tags (Threshold > {threshold:.0%}) ---")
        violator_ips = [
            ip for ip, data in access_only_flat.items()
            if data.get('total_request_count', 0) > 0 and (data.get('restricted_path_count', 0) / data['total_request_count']) > threshold
        ]
        total_requests = sum(access_only_flat[ip].get('total_request_count', 0) for ip in violator_ips)
        compressed_list = group_ips_into_cidrs(violator_ips)
        header = (
            f"# secondary junk tags for restricted-path violators (>{threshold:.0%} violation ratio).\n"
            f"# Generated by: {pathlib.Path(__file__).name} at {datetime.datetime.now().isoformat()}\n"
            f"# Total unique IPs found: {len(violator_ips):,}\n"
            f"# Total associated requests: {total_requests:,}\n"
            f"# Compressed to {len(compressed_list):,} entries.\n#\n"
        )
        write_secondary_junk_tag_file(
            restricted_path_junk_tags_output_file,
            header,
            compressed_list,
        )
    else:
        print("\nNo 'access_only' data found, skipping restricted path violator secondary junk tags.")

# --- Main execution ---


def main(args):
    """
    Main function to read db and orchestrate analysis and reporting.
    """
    db_file = pathlib.Path(args.db_file)
    if not db_file.exists():
        # Corrected the error message to point to the new script name
        print(f"Error: Db file '{db_file}' not found. Please run generate_traffic_analytics.py first.", file=sys.stderr)
        sys.exit(1)
    try:
        with shelve.open(str(db_file), 'r') as db:
            banned_data_from_db = db.get('already_banned', {})
            not_yet_banned_flat = db.get('not_yet_banned', {})
            access_only_flat = db.get('access_only', {})
    except Exception as e:
        print(f"Error opening or reading db file: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Standard Inspection Report ---
    headers = ["Entity", "IPs", "Total Reqs", "Junk Probes", "Restricted", "Combined Violations", "Avg Violations/IP", "Violation Ratio"]
    header_fmt = "{:<18} | {:>5} | {:>10} | {:>11} | {:>10} | {:>19} | {:>17} | {:>15}"
    print("\n", "Already Banned".upper())
    print("\n--- Already Banned Summary ---")
    print(header_fmt.format(*headers))
    print("-" * 130)
    # already_banned table
    sorted_already_banned = sorted(banned_data_from_db.items(), key=lambda item: item[1]['counts'].get('junk_probe_count', 0) + item[1]['counts'].get('restricted_path_count', 0), reverse=True)
    disp_banned_ips, disp_banned_reqs, disp_banned_junk, disp_banned_restricted, printed_banned_count = 0, 0, 0, 0, 0
    for key, data in sorted_already_banned[:args.inspection_table_top_n]:
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
        disp_banned_ips += ip_count
        disp_banned_reqs += total_reqs
        disp_banned_junk += junk_probes
        disp_banned_restricted += restricted
        printed_banned_count += 1
    print("-" * 130)
    disp_banned_combined = disp_banned_junk + disp_banned_restricted
    disp_banned_avg_viol = (disp_banned_combined / disp_banned_ips) if disp_banned_ips > 0 else 0
    disp_banned_viol_ratio = (disp_banned_combined / disp_banned_reqs) if disp_banned_reqs > 0 else 0
    displayed_total_row = ["Total", f"{disp_banned_ips:,}", f"{disp_banned_reqs:,}", f"{disp_banned_junk:,}", f"{disp_banned_restricted:,}", f"{disp_banned_combined:,}", f"{disp_banned_avg_viol:.2f}", f"{disp_banned_viol_ratio:.2%}"]
    print(header_fmt.format(*displayed_total_row))
    print(f"\nDisplayed top {printed_banned_count} of {len(sorted_already_banned)} total already banned entries.")

    print("\n", "-" * 130, "\n")

    all_analytics = {'already_banned': banned_data_from_db}
    all_analytics['not_yet_banned'] = process_and_display_category(
        "Not Yet Banned",
        not_yet_banned_flat,
        args.inspection_table_top_n,
        headers,
        header_fmt,
    )
    all_analytics['access_only'] = process_and_display_category(
        "Access Only",
        access_only_flat,
        args.inspection_table_top_n,
        headers,
        header_fmt,
    )
    if args.inspection_json_file:
        try:
            with open(args.inspection_json_file, 'w') as f:
                json.dump(all_analytics, f, indent=2)
            print(f"\nSuccessfully wrote full grouped analytics to {args.inspection_json_file}")
        except Exception as e:
            print(f"Error writing to output file {args.inspection_json_file}: {e}", file=sys.stderr)

    # --- Optional Analyses ---
    if args.analyze_ratios:
        analyze_and_print_ratios(access_only_flat)
    if args.generate_secondary_junk_tags:
        generate_secondary_junk_tags(
            not_yet_banned_flat,
            access_only_flat,
            args.restricted_path_violation_threshold,
            args.junk_prober_junk_tag_output_file,
            args.restricted_path_violator_junk_tags_output_file,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inspect traffic analytics db, generate reports, analyze ratios, and create secondary junk tags.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # General arguments
    parser.add_argument('--db-file', default='static/cache/traffic_analytics.db', help="Path to the shelve db file.")
    # Inspection report arguments
    inspection_group = parser.add_argument_group('Inspection Report')
    inspection_group.add_argument('--inspection-json-file', default=None, help="Optional path for the JSON output of the inspection report.")
    inspection_group.add_argument('--inspection-table-top-n', type=int, default=10, help="Number of top entries to display in tables.")
    # Ratio analysis arguments
    ratio_group = parser.add_argument_group('Ratio Analysis')
    ratio_group.add_argument('--analyze-ratios', action='store_true', help="Analyze and display the distribution of restricted path violation ratios.")
    # Banlist generation arguments
    banlist_group = parser.add_argument_group('Banlist Generation')
    banlist_group.add_argument('--generate-secondary-junk-tags', action='store_true', help="Generate secondary junk tags based on the analysis.")
    banlist_group.add_argument('--restricted-path-violation-threshold', type=float, default=0.8, help="Violation ratio threshold for banning IPs from 'access_only' data.")
    banlist_group.add_argument('--junk-prober-junk-tag-output-file', default='junk_prober_junk_tags.txt', help="Output file for the junk prober junk tags.")
    banlist_group.add_argument('--restricted-path-violator-junk-tags-output-file', default='restricted_path_violator_junk_tags.txt', help="Output file for the restricted path violator junk tags.")
    args = parser.parse_args()
    main(args)
