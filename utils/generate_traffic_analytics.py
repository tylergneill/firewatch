#!/usr/bin/env python3
import argparse
import ipaddress
import pathlib
import shelve
import sys
import json
from collections import defaultdict, Counter
from urllib.robotparser import RobotFileParser
from tqdm import tqdm

from primary_junk_definitions import BLOCKED_NETWORKS, is_junk_probe
from utils import parse_line

"""
Usage: python generate_traffic_analytics.py \
  --access-dir static/data \
  --junk-dir static/data \
  --robots-dir static/data/robots \
  --cache-file static/cache/analytics.db
"""


def get_ip_category_and_key(ip_str: str):
    """
    Categorizes an IP as 'already_banned' or 'not_yet_banned' and
    returns the appropriate key (CIDR for banned, IP for not banned).
    """
    if not ip_str:
        return None, None
    try:
        ip_addr = ipaddress.ip_address(ip_str)
        for network in BLOCKED_NETWORKS:
            if ip_addr in network:
                return "already_banned", str(network)
    except ValueError:
        return None, None
    return "not_yet_banned", ip_str


def get_app_name_from_filename(filename: str) -> str:
    """Extracts the application name from a log file name."""
    parts = filename.split('-app.')
    return parts[0] if parts else "unknown"


def main(data_dir: str, robots_dir: str, db_file: str):
    """
    Analyzes log files to learn patterns about IPs found in junk logs.
    """
    data_path = pathlib.Path(data_dir)
    robots_path = pathlib.Path(robots_dir)

    all_log_files = list(data_path.rglob('*.log*'))
    junk_log_files = [f for f in all_log_files if '.junk.' in f.name]

    print("Step 1: Gathering unique IPs from junk logs...")
    junk_ips = set()
    
    total_size = sum(f.stat().st_size for f in junk_log_files)
    with tqdm(total=total_size, unit='B', unit_scale=True, desc="Gathering Junk IPs") as pbar:
        for log_file in junk_log_files:
            with log_file.open('rb') as f:
                for line in f:
                    p = parse_line(line)
                    if p and p.get('ip'):
                        junk_ips.add(p['ip'])
                    pbar.update(len(line))

    print(f"  - Found {len(junk_ips)} unique IPs in junk logs.")

    print("Step 2: Loading robots.txt files...")
    robot_parsers = {}
    robot_files = list(robots_path.glob('*.robots.txt'))
    for robot_file in robot_files:
        app_name = robot_file.stem.replace('.robots', '')
        parser = RobotFileParser()
        parser.set_url(f"http://{app_name}.com/robots.txt")
        with robot_file.open('r') as f:
            parser.parse(f.readlines())
        robot_parsers[app_name] = parser
        print(f"  - Loaded rules for '{app_name}'")

    # --- Step 3: Process all log files to build analytics ---
    print("Step 3: Processing all log files to build analytics...")
    analytics = {
        "already_banned": defaultdict(lambda: {'counts': Counter(), 'ips': set()}),
        "not_yet_banned": defaultdict(Counter),
        "access_only": defaultdict(Counter)
    }
    
    print(f"  - Found {len(all_log_files)} total log files to process.")

    total_size = sum(f.stat().st_size for f in all_log_files)
    with tqdm(total=total_size, unit='B', unit_scale=True, desc="Processing All Logs") as pbar:
        for log_file in all_log_files:
            app_name = get_app_name_from_filename(log_file.name)
            robot_parser = robot_parsers.get(app_name)
            is_access_log = '.access.' in log_file.name

            with log_file.open('rb') as f:
                for line in f:
                    pbar.update(len(line))
                    if not (p := parse_line(line)):
                        continue
                    
                    ip = p['ip']
                    path = p.get('path', '')
                    ua = p.get('ua', '*')

                    # Determine category and process
                    if ip in junk_ips:
                        category, key = get_ip_category_and_key(ip)
                        if not category: continue
                        
                        if category == "already_banned":
                            target_dict = analytics[category][key]['counts']
                            analytics[category][key]['ips'].add(ip)
                        else: # not_yet_banned
                            target_dict = analytics[category][key]
                    elif is_access_log:
                        category = "access_only"
                        key = ip
                        target_dict = analytics[category][key]
                    else:
                        continue # Skip lines from junk dir whose IP wasn't in the initial set for some reason
                    
                    target_dict['total_request_count'] += 1
                    if is_junk_probe(path):
                        target_dict['junk_probe_count'] += 1
                    if robot_parser and not robot_parser.can_fetch(ua, path):
                        target_dict['restricted_path_count'] += 1

    print("\n  - Log processing complete.")

    # --- Step 4: Write analytics to shelve db ---
    print(f"Step 4: Writing analytics to db file: {db_file}")

    # Explicitly convert all complex types to basic types before shelving
    final_analytics = {
        'not_yet_banned': {k: dict(v) for k, v in analytics['not_yet_banned'].items()},
        'access_only': {k: dict(v) for k, v in analytics['access_only'].items()},
        'already_banned': {}
    }
    for cidr, data in analytics['already_banned'].items():
        final_analytics['already_banned'][cidr] = {
            'counts': dict(data['counts']),
            'ips': list(data['ips'])
        }

    # Brute-force sanitization with a JSON cycle to ensure no complex objects remain
    sanitized_analytics = json.loads(json.dumps(final_analytics))

    try:
        with shelve.open(db_file, 'c') as db:
            db['already_banned'] = sanitized_analytics['already_banned']
            db['not_yet_banned'] = sanitized_analytics['not_yet_banned']
            db['access_only'] = sanitized_analytics['access_only']
        print("Analytics generation finished successfully.")
    except Exception as e:
        print(f"Error writing to db: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze log files to learn patterns and build an analytics db."
    )
    parser.add_argument(
        '--data-dir',
        default='static/data',
        help="The input directory containing log files."
    )
    parser.add_argument(
        '--robots-dir',
        default='static/data/robots',
        help="The directory containing robots.txt files."
    )
    parser.add_argument(
        '--db-file',
        default='static/cache/traffic_analytics.db',
        help="The path to the shelve db file for traffic analytics."
    )
    
    args = parser.parse_args()
    main(args.data_dir, args.robots_dir, args.db_file)
