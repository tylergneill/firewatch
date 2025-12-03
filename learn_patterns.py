#!/usr/bin/env python3
import argparse
import datetime
import pathlib
import re
import shelve
import sys
from collections import defaultdict
from urllib.robotparser import RobotFileParser

from utils import parse_line

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

def get_app_name_from_filename(filename: str) -> str:
    """Extracts the application name from a log file name."""
    # Covers names like 'hansel-app.access.log-DATE' or 'panditya-stg-app.forbidden.log'
    parts = filename.split('-app.')
    return parts[0] if parts else "unknown"

def main(access_dir: str, forbidden_dir: str, robots_dir: str, cache_file: str):
    """
    Analyzes log files to learn patterns about IPs found in forbidden logs.
    """
    access_path = pathlib.Path(access_dir)
    forbidden_path = pathlib.Path(forbidden_dir)
    robots_path = pathlib.Path(robots_dir)

    # --- Step 1: Gather all unique IPs from forbidden logs ---
    print("Step 1: Gathering unique IPs from forbidden logs...")
    forbidden_ips = set()
    forbidden_log_files = list(forbidden_path.rglob('*.log*'))
    for log_file in forbidden_log_files:
        with log_file.open('rb') as f:
            for line in f:
                p = parse_line(line)
                if p and p.get('ip'):
                    forbidden_ips.add(p['ip'])
    print(f"  - Found {len(forbidden_ips)} unique IPs in forbidden logs.")

    # --- Step 2: Load robots.txt files ---
    print("Step 2: Loading robots.txt files...")
    robot_parsers = {}
    robot_files = list(robots_path.glob('*.robots.txt'))
    for robot_file in robot_files:
        app_name = robot_file.stem.replace('.robots', '')
        parser = RobotFileParser()
        parser.set_url(f"http://{app_name}.com/robots.txt") # Base URL is arbitrary
        with robot_file.open('r') as f:
            parser.parse(f.readlines())
        robot_parsers[app_name] = parser
        print(f"  - Loaded rules for '{app_name}'")

    # --- Step 3: Process all logs to build analytics ---
    print("Step 3: Processing all log files to build analytics...")
    # Structure: {ip: {date: {counter: value}}}
    analytics = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    
    all_log_files = list(access_path.rglob('*.log*')) + forbidden_log_files
    print(f"  - Found {len(all_log_files)} total log files to process.")

    for i, log_file in enumerate(all_log_files):
        print(f"  - Processing file {i+1}/{len(all_log_files)}: {log_file.name}", end='\r')
        app_name = get_app_name_from_filename(log_file.name)
        robot_parser = robot_parsers.get(app_name)

        with log_file.open('rb') as f:
            for line in f:
                p = parse_line(line)
                if not (p and p.get('ip') in forbidden_ips and p.get('time')):
                    continue
                
                ip = p['ip']
                datestamp = p['time'].date().isoformat()
                path = p.get('path', '')
                ua = p.get('ua', '*')

                # Increment total requests
                analytics[ip][datestamp]['total_request_count'] += 1

                # Increment junk probe count
                if is_junk_probe(path):
                    analytics[ip][datestamp]['junk_probe_count'] += 1
                
                # Increment restricted path count
                if robot_parser and not robot_parser.can_fetch(ua, path):
                    analytics[ip][datestamp]['restricted_path_count'] += 1

    print("\n  - Log processing complete.")

    # --- Step 4: Write analytics to shelve cache ---
    print(f"Step 4: Writing analytics to cache file: {cache_file}")
    with shelve.open(cache_file, 'c') as cache:
        for ip, date_data in analytics.items():
            if ip not in cache:
                cache[ip] = {}
            
            # shelve requires assigning a modified object back to the key
            ip_cache_data = cache[ip]
            for datestamp, counts in date_data.items():
                ip_cache_data[datestamp] = dict(counts)
            cache[ip] = ip_cache_data
            
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
