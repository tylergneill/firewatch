#!/usr/bin/env python3
import argparse
import ipaddress
import pathlib
import re
import shelve
from collections import defaultdict, Counter
from urllib.robotparser import RobotFileParser
from tqdm import tqdm

from purge_bad_crawlers import BLOCKED_NETWORKS
from utils import parse_line

"""
Usage: python learn_patterns.py \
  --access-dir static/data/access \
  --forbidden-dir static/data/forbidden \
  --robots-dir static/data/robots \
  --cache-file static/cache/analytics.db
"""

# --- Junk Probe Logic (from purge_bad_crawlers.py) ---
JUNK_PROBE_PATTERNS = [
    r"\.git(/|$)",
    r"(^|/)\.env",
    r"/(env|git|config|configs|conf|settings|production|app|home)\.zip$",
    r"\.php$",
    r"/cgi-bin/",
]
JUNK_PROBE_REGEXES = [re.compile(p, re.IGNORECASE) for p in JUNK_PROBE_PATTERNS]


def is_junk_probe(uri_str: str) -> bool:
    """Checks if a given request URI is a junk/security probe."""
    if not uri_str:
        return False
    for regex in JUNK_PROBE_REGEXES:
        if regex.search(uri_str):
            return True
    return False


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


def main(access_dir: str, forbidden_dir: str, robots_dir: str, cache_file: str):
    """
    Analyzes log files to learn patterns about IPs found in forbidden logs.
    """
    access_path = pathlib.Path(access_dir)
    forbidden_path = pathlib.Path(forbidden_dir)
    robots_path = pathlib.Path(robots_dir)

    print("Step 1: Gathering unique IPs from forbidden logs...")
    forbidden_ips = set()
    forbidden_log_files = list(forbidden_path.rglob('*.log*'))
    
    total_size = sum(f.stat().st_size for f in forbidden_log_files)
    with tqdm(total=total_size, unit='B', unit_scale=True, desc="Gathering Forbidden IPs") as pbar:
        for log_file in forbidden_log_files:
            with log_file.open('rb') as f:
                for line in f:
                    p = parse_line(line)
                    if p and p.get('ip'):
                        forbidden_ips.add(p['ip'])
                    pbar.update(len(line))

    print(f"  - Found {len(forbidden_ips)} unique IPs in forbidden logs.")

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
        "not_yet_banned": defaultdict(Counter)
    }
    
    all_log_files = list(access_path.rglob('*.log*')) + forbidden_log_files
    print(f"  - Found {len(all_log_files)} total log files to process.")

    total_size = sum(f.stat().st_size for f in all_log_files)
    with tqdm(total=total_size, unit='B', unit_scale=True, desc="Processing All Logs") as pbar:
        for log_file in all_log_files:
            app_name = get_app_name_from_filename(log_file.name)
            robot_parser = robot_parsers.get(app_name)

            with log_file.open('rb') as f:
                for line in f:
                    pbar.update(len(line))
                    if not (p := parse_line(line)) or not (p.get('ip') in forbidden_ips):
                        continue
                    
                    ip = p['ip']
                    path = p.get('path', '')
                    ua = p.get('ua', '*')

                    category, key = get_ip_category_and_key(ip)
                    if not category:
                        continue
                    
                    # Get the correct dictionary to update
                    if category == "already_banned":
                        target_dict = analytics[category][key]['counts']
                        analytics[category][key]['ips'].add(ip)
                    else:
                        target_dict = analytics[category][key]

                    target_dict['total_request_count'] += 1
                    if is_junk_probe(path):
                        target_dict['junk_probe_count'] += 1
                    if robot_parser and not robot_parser.can_fetch(ua, path):
                        target_dict['restricted_path_count'] += 1

    print("\n  - Log processing complete.")

    # --- Step 4: Write analytics to shelve cache ---
    print(f"Step 4: Writing analytics to cache file: {cache_file}")
    with shelve.open(cache_file, 'c') as cache:
        # Convert defaultdicts and sets to plain dicts and lists for shelving
        banned_cache_data = {}
        for cidr, data in analytics['already_banned'].items():
            banned_cache_data[cidr] = {
                'counts': dict(data['counts']),
                'ips': list(data['ips'])
            }
        cache['already_banned'] = banned_cache_data
        
        cache['not_yet_banned'] = {k: dict(v) for k, v in analytics['not_yet_banned'].items()}
            
    print("Learn patterns script finished successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze log files to learn patterns and build an analytics cache."
    )
    parser.add_argument(
        '--access-dir',
        default='static/data/access',
        help="The input directory containing access log files."
    )
    parser.add_argument(
        '--forbidden-dir',
        default='static/data/forbidden',
        help="The input directory containing forbidden log files."
    )
    parser.add_argument(
        '--robots-dir',
        default='static/data/robots',
        help="The directory containing robots.txt files."
    )
    parser.add_argument(
        '--cache-file',
        default='static/cache/analytics.db',
        help="The path to the shelve cache file for analytics."
    )
    
    args = parser.parse_args()
    main(args.access_dir, args.forbidden_dir, args.robots_dir, args.cache_file)
