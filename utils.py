import pathlib
import re
from collections import deque
import requests
import json
import datetime


def find_app_version():
    app_version_filepath = './VERSION'
    with open(app_version_filepath, 'r', encoding='utf8') as file:
        # Assuming the __version__ line is the first line
        return file.readline().strip().split('=')[1].strip().replace("'", "").replace('"', '')


LOG_RE = re.compile(
    r'^(?P<host>\S+)\s+'                 # $host
    r'(?P<port>\S+)\s+'                  # $server_port
    r'(?P<ip>\S+)\s+'                    # $remote_addr
    r'-\s+'                              # literal dash
    r'(?P<remote_user>\S+)\s+'           # $remote_user (often "-")
    r'\[(?P<time>[^\]]+)\]\s+'           # [time_local]
    r'"(?P<method>\S+)\s+'               # "GET
    r'(?P<path>\S+)\s+'                  # /foo
    r'(?P<protocol>[^"]+)"\s+'           # HTTP/1.1"
    r'(?P<status>\d+)\s+'                # 200
    r'(?P<size>\S+)\s+'                  # body_bytes_sent
    r'"(?P<referer>[^"]*)"\s+'           # "referer"
    r'"(?P<ua>[^"]*)"\s+'                # "user_agent"
    r'(?P<req_time>\S+)$'                # request_time
)


def tail_lines(path: pathlib.Path, n: int):
    """Return last n lines of a text file as bytes."""
    try:
        dq = deque(maxlen=n)
        with path.open("rb") as f:
            for line in f:
                dq.append(line.rstrip(b"\n"))
        return list(dq)
    except FileNotFoundError:
        return []


def parse_line(line: bytes):
    """Parse one Nginx log line into fields used by the summary."""
    try:
        s = line.decode("utf-8", errors="replace").strip()
    except Exception:
        return None

    if not s:
        return None

    m = LOG_RE.match(s)
    if not m:
        return None

    d = m.groupdict()

    try:
        # Format: 16/Nov/2025:15:04:05 +0000
        log_time_str = d["time"].split(':')[0]
        log_datetime = datetime.datetime.strptime(log_time_str, '%d/%b/%Y')
        log_date = log_datetime.date()
    except (ValueError, IndexError):
        log_date = None

    try:
        req_time = float(d["req_time"])
    except ValueError:
        req_time = None

    return {
        "raw": s,
        "ip": d["ip"],
        "host": d["host"],
        "status": d["status"],
        "path": d["path"],
        "method": d["method"],
        "req_time": req_time,
        "ua": d["ua"],
        "date": log_date,
    }


GEO_CACHE_FILE = pathlib.Path("ip_geocache.json")

def load_geo_cache():
    if GEO_CACHE_FILE.exists():
        with GEO_CACHE_FILE.open("r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} # Return empty dict if file is corrupt
    return {}

def save_geo_cache(cache):
    with GEO_CACHE_FILE.open("w") as f:
        json.dump(cache, f, indent=2)

def get_geo_for_ip(ip: str):
    cache = load_geo_cache()
    if ip in cache:
        return cache[ip]

    # Don't geolocate private/local IPs
    if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172.") or ip == "127.0.0.1" or ip.startswith("::"):
         geo_info = {"country": "Private", "city": "N/A", "regionName": "N/A", "query": ip}
         cache[ip] = geo_info
         save_geo_cache(cache)
         return geo_info

    try:
        # The user mentioned this API
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=country,regionName,city,query", timeout=3)
        response.raise_for_status()
        data = response.json()
        cache[ip] = data
        save_geo_cache(cache)
        return data
    except requests.exceptions.RequestException:
        # Fail silently and cache the failure so we don't keep trying
        geo_info = {"error": "Failed to fetch", "query": ip}
        cache[ip] = geo_info
        save_geo_cache(cache)
        return geo_info
