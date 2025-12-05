import logging
from collections import Counter, defaultdict
import pathlib
import re
import requests
import datetime
import os
from functools import lru_cache


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
    if n <= 0:
        return []
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            if file_size == 0:
                return []

            offset = 0
            lines_found = 0
            buffer = b''
            block_size = 4096  # Increased block size for efficiency

            # Keep reading backwards from the end of the file in blocks
            # until we find at least n + 1 newline characters.
            while lines_found < (n + 1) and offset < file_size:
                block_end_pos = file_size - offset
                block_start_pos = max(0, block_end_pos - block_size)

                f.seek(block_start_pos)
                block = f.read(block_end_pos - block_start_pos)

                buffer = block + buffer
                lines_found = buffer.count(b'\n')
                offset += block_size

            # The original implementation returned lines with `rstrip(b"\n")`.
            # `splitlines()` removes standard line endings, which is correct.
            lines = buffer.splitlines()

            # Return the last n lines.
            return lines[-n:]

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
        req_time = float(d["req_time"])
    except ValueError:
        req_time = None

    try:
        time = datetime.datetime.strptime(d['time'], "%d/%b/%Y:%H:%M:%S %z")
    except (ValueError, KeyError):
        time = None

    return {
        "raw": s,
        "ip": d["ip"],
        "host": d["host"],
        "status": d["status"],
        "path": d["path"],
        "method": d["method"],
        "req_time": req_time,
        "ua": d["ua"],
        "time": time,
    }


@lru_cache(maxsize=2048)
def get_geo_for_ip(ip: str):
    """Get geo location for an IP, with in-memory caching."""
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def find_archived_logs_for_daterange(dir_path, start_date, end_date):
    if not dir_path.is_dir():
        return []

    log_files = set()
    delta = end_date - start_date
    for i in range(delta.days + 1):
        day = start_date + datetime.timedelta(days=i)
        date_str = day.isoformat()
        for p in dir_path.glob(f"*{date_str}*"):
            log_files.add(p)

    return sorted(list(log_files))


def get_log_sources_for_app(app_name, data_dir, start_date, end_date):
    """
    Finds all relevant log files for a given app and date range,
    including archived files and the current log file.
    """
    archive_dir = data_dir / f"{app_name}-archive" / "access"

    log_files = set()
    delta = end_date - start_date
    for i in range(delta.days + 1):
        day = start_date + datetime.timedelta(days=i)
        date_str = day.isoformat()
        archived_log_path = archive_dir / f"{app_name}-app.access.log-{date_str}"
        if archived_log_path.is_file():
            log_files.add(archived_log_path)

    # Add the current log if the selected date range includes today.
    today = datetime.date.today()
    if start_date <= today and today <= end_date:
        current_log_path = data_dir / f"{app_name}-app.access.log"
        if current_log_path.is_file():
            log_files.add(current_log_path)

    return sorted(list(log_files))


def read_lines_from_files(paths):
    for path in paths:
        try:
            with path.open("rb") as f:
                yield from f
        except FileNotFoundError:
            logging.warning(f"Log file not found: {path}")
            continue


def get_dates_from_request_args(request_args):
    end_date_str = request_args.get('end_date')
    start_date_str = request_args.get('start_date')

    try:
        end_date = datetime.date.fromisoformat(end_date_str) if end_date_str else datetime.date.today()
        start_date = datetime.date.fromisoformat(start_date_str) if start_date_str else datetime.date.today()
    except ValueError:
        today = datetime.date.today()
        end_date = today
        start_date = today
    return start_date, end_date

def _process_single_log_file(file_path_str: str, app_names: list):
    """
    Processes a single log file and returns aggregated data.
    """
    file_path = pathlib.Path(file_path_str)

    # Initialize local counters for this file
    file_total = 0
    file_total_req_time = 0.0
    file_ip_counts = Counter()
    file_ua_counts = Counter()
    file_route_app_counts = defaultdict(Counter)
    file_status_counts = Counter()
    file_app_counts = defaultdict(Counter)
    file_ip_status_counts = defaultdict(Counter)
    file_app_response_times = defaultdict(list)
    file_app_ip_sets = defaultdict(set)
    file_app_requests_by_day = defaultdict(lambda: defaultdict(int))
    file_uptime_data = defaultdict(lambda: defaultdict(lambda: {'2xx': 0, '5xx': 0, 'total': 0}))

    app_name = "unknown"
    for name in app_names:
        if name in file_path.name:
            app_name = name
            break
    
    # Process lines for this file
    for line in read_lines_from_files([file_path]):
        p = parse_line(line)
        if not p:
            continue

        # Uptime data
        if p['time']:
            log_date = p['time'].date()
            file_app_requests_by_day[app_name][log_date] += 1
            file_uptime_data[app_name][log_date]['total'] += 1
            try:
                status_code = int(p['status'])
                if 200 <= status_code < 300:
                    file_uptime_data[app_name][log_date]['2xx'] += 1
                elif 500 <= status_code < 600:
                    file_uptime_data[app_name][log_date]['5xx'] += 1
            except (ValueError, TypeError):
                pass

        # Requests data
        file_total += 1
        file_ip_counts[p["ip"]] += 1
        file_ua_counts[p["ua"]] += 1
        route = p["path"].split('?')[0]
        file_route_app_counts[route][app_name] += 1
        file_status_counts[p["status"]] += 1
        file_app_counts[app_name][p["status"]] += 1
        file_ip_status_counts[p["ip"]][p["status"]] += 1
        file_app_ip_sets[app_name].add(p['ip'])
        if p["req_time"] is not None:
            file_total_req_time += p["req_time"]
            file_app_response_times[app_name].append(p["req_time"])

    # Convert sets to lists and datetimes to strings for serialization
    serializable_app_ip_sets = {k: list(v) for k, v in file_app_ip_sets.items()}
    serializable_app_requests_by_day = {
        app: {date.isoformat(): count for date, count in daily_counts.items()}
        for app, daily_counts in file_app_requests_by_day.items()
    }
    serializable_uptime_data = {
        app: {date.isoformat(): counts for date, counts in daily_counts.items()}
        for app, daily_counts in file_uptime_data.items()
    }

    return {
        "app_name": app_name,
        "total": file_total,
        "total_req_time": file_total_req_time,
        "ip_counts": file_ip_counts,
        "ua_counts": file_ua_counts,
        "route_app_counts": file_route_app_counts,
        "status_counts": file_status_counts,
        "app_counts": file_app_counts,
        "ip_status_counts": file_ip_status_counts,
        "app_response_times": file_app_response_times,
        "app_ip_sets": serializable_app_ip_sets,
        "app_requests_by_day": serializable_app_requests_by_day,
        "uptime_data": serializable_uptime_data,
    }
