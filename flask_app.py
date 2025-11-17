import os
from collections import Counter
import pathlib
import datetime
import re

from flask import Flask, render_template, request, session

from utils import find_app_version, parse_line, get_geo_for_ip

# Detect debug mode from environment
DEBUG_ENV = os.environ.get("FLASK_DEBUG") == "1"

APP_VERSION= find_app_version()

LOCAL_LOG_FILE_MAIN_PATH = pathlib.Path("../lookout-tower-sharded-data")
app_names = [
    "skrutable",
    "splitter-server",
    "vatayana",
    "panditya",
    "hansel"]
app_names += [
    app_name + '-stg'
    for app_name in app_names
    if app_name != "splitter-server"
]

SERVER_LOG_FILE_MAIN_PATH = pathlib.Path("/var/log/nginx/")

LOG_FILE_MAIN_PATH = LOCAL_LOG_FILE_MAIN_PATH if DEBUG_ENV else SERVER_LOG_FILE_MAIN_PATH

LOG_FILES = {
    app_name: LOG_FILE_MAIN_PATH / f"{app_name}-archive"
    for app_name in app_names
}

MAX_LINES_PER_FILE = 200

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.debug = DEBUG_ENV


def find_archived_logs_for_daterange(dir_path, start_date, end_date):
    if not dir_path.is_dir():
        return []

    # Regex to find dates in the format YYYY-MM-DD at the end of the filename
    date_pattern = re.compile(r'.*(\d{4}-\d{2}-\d{2})-(\d{4}-\d{2}-\d{2})$')

    log_files = []
    for p in dir_path.glob("*"): # Any file, not just .log
        match = date_pattern.match(p.name)
        if match:
            try:
                log_start_str, log_end_str = match.groups()
                log_start_date = datetime.date.fromisoformat(log_start_str)
                log_end_date = datetime.date.fromisoformat(log_end_str)

                # Check for overlap
                if start_date <= log_end_date and end_date >= log_start_date:
                    log_files.append(p)
            except ValueError:
                # Ignore files with malformed dates in their names
                continue
    return sorted(log_files)


def get_log_sources_for_app(app_name, start_date, end_date):
    """
    Finds all relevant log files for a given app and date range,
    including archived files and the current log file.
    """
    archive_path = LOG_FILES.get(app_name)

    # 1. Get dated log files from the archive directory
    log_files = find_archived_logs_for_daterange(archive_path, start_date, end_date)

    # 2. Add the current log if the selected date range overlaps with the current week.
    today = datetime.date.today()
    # Assuming weeks start on Monday (weekday() == 0)
    start_of_current_week = today - datetime.timedelta(days=today.weekday())

    # The current log's effective date range is from the start of the week to today.
    # Check if the user's selected range [start_date, end_date] overlaps with
    # the current log's range [start_of_current_week, today].
    # Overlap condition: (start1 <= end2) and (end1 >= start2)
    if start_date <= today and end_date >= start_of_current_week:
        current_log_path = LOG_FILE_MAIN_PATH / f"{app_name}-app.access.log"
        if current_log_path.is_file():
            log_files.append(current_log_path)

    return log_files


def read_lines_from_files(paths):
    all_lines = []
    for path in paths:
        try:
            with path.open("rb") as f:
                all_lines.extend(f.readlines())
        except FileNotFoundError:
            continue
    return all_lines


def get_dates_from_request():
    end_date_str = request.args.get('end_date')
    start_date_str = request.args.get('start_date')

    try:
        end_date = datetime.date.fromisoformat(end_date_str) if end_date_str else datetime.date.today()
        start_date = datetime.date.fromisoformat(start_date_str) if start_date_str else (datetime.date.today() - datetime.timedelta(days=7))
    except ValueError:
        end_date = datetime.date.today()
        start_date = datetime.date.today() - datetime.timedelta(days=7)
    return start_date, end_date


@app.route("/")
def index():
    start_date, end_date = get_dates_from_request()
    return render_template(
        "base.html",
        app_version=APP_VERSION,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )


@app.route("/raw")
def raw_view():
    start_date, end_date = get_dates_from_request()

    app_logs = {}
    for app_name in app_names:
        log_files = get_log_sources_for_app(app_name, start_date, end_date)
        lines = read_lines_from_files(log_files)

        filtered_lines = []
        for l in lines:
            p = parse_line(l) # Parse to get date
            if p and p.get("date") and start_date <= p["date"] <= end_date:
                filtered_lines.append(l) # Append original line

        if len(filtered_lines) > MAX_LINES_PER_FILE:
            filtered_lines = filtered_lines[-MAX_LINES_PER_FILE:]

        text_lines = [l.decode("utf-8", errors="replace") for l in filtered_lines]
        app_logs[app_name] = text_lines

    return render_template(
        "raw.html",
        app_logs=app_logs,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )


@app.route("/summary", methods=['GET', 'POST'])
def summary_view():
    start_date, end_date = get_dates_from_request()

    if request.method == 'POST':
        session['selected_apps'] = request.form.getlist('apps')

    selected_apps = session.get('selected_apps', app_names)

    parsed_entries = []

    for app_name in selected_apps:
        log_files = get_log_sources_for_app(app_name, start_date, end_date)
        lines = read_lines_from_files(log_files)
        for l in lines:
            p = parse_line(l)
            if not p or not p.get("date"):
                continue

            # Filter by date range
            if start_date <= p["date"] <= end_date:
                p["app"] = app_name
                parsed_entries.append(p)

    filter_ip = request.args.get('ip')
    filter_ua = request.args.get('ua')

    if filter_ip:
        parsed_entries = [p for p in parsed_entries if p['ip'] == filter_ip]
    if filter_ua:
        parsed_entries = [p for p in parsed_entries if p['ua'] == filter_ua]

    total = len(parsed_entries)

    ip_counts = Counter(p["ip"] for p in parsed_entries)
    ua_counts = Counter(p["ua"] for p in parsed_entries)
    status_counts = Counter(p["status"] for p in parsed_entries)
    app_counts = Counter(p["app"] for p in parsed_entries)

    # Enrich IPs with geolocation
    ip_counts_geo = []
    for ip, count in ip_counts.most_common(20):
        geo_info = get_geo_for_ip(ip)
        ip_counts_geo.append({"ip": ip, "count": count, "geo": geo_info})

    total_req_time = sum(p['req_time'] for p in parsed_entries if p['req_time'] is not None)
    avg_req_time = total_req_time / total if total > 0 else 0

    return render_template(
        "summary.html",
        total=total,
        ip_counts=ip_counts_geo,
        ua_counts=ua_counts.most_common(20),
        status_counts=status_counts.most_common(),
        app_counts=app_counts.most_common(),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        app_names=app_names,
        selected_apps=selected_apps,
        filter_ip=filter_ip,
        filter_ua=filter_ua,
        avg_req_time=avg_req_time,
    )


if __name__ == "__main__":
    # Local run
    app.run(host="127.0.0.1", port=5070, debug=DEBUG_ENV)
