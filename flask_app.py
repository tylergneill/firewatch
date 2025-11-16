import os
from collections import Counter
import pathlib
import datetime
import re

from flask import Flask, render_template, request

from utils import find_app_version, parse_line

# Detect debug mode from environment
DEBUG_ENV = os.environ.get("FLASK_DEBUG") == "1"

APP_VERSION= find_app_version()

LOCAL_LOG_FILE_MAIN_PATH = pathlib.Path("../lookout-tower-sharded-data")
app_names = [
    "skrutable",
    "splitter-server",
    # "vatayana",
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
    app_name: LOG_FILE_MAIN_PATH / app_name
    for app_name in app_names
}

MAX_LINES_PER_FILE = 200

app = Flask(__name__)
app.debug = DEBUG_ENV


def get_log_files_for_daterange(dir_path, start_date, end_date):
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
    for app_name, path in LOG_FILES.items():
        log_files = get_log_files_for_daterange(path, start_date, end_date)
        lines = read_lines_from_files(log_files)
        if len(lines) > MAX_LINES_PER_FILE:
            lines = lines[-MAX_LINES_PER_FILE:]
        text_lines = [l.decode("utf-8", errors="replace") for l in lines]
        app_logs[app_name] = text_lines

    return render_template(
        "raw.html",
        app_logs=app_logs,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )


@app.route("/summary")
def summary_view():
    start_date, end_date = get_dates_from_request()

    parsed_entries = []

    for app_name, path in LOG_FILES.items():
        log_files = get_log_files_for_daterange(path, start_date, end_date)
        lines = read_lines_from_files(log_files)
        for l in lines:
            p = parse_line(l)
            if not p:
                continue
            p["app"] = app_name
            parsed_entries.append(p)

    total = len(parsed_entries)

    host_counts = Counter(p["host"] for p in parsed_entries)
    ip_counts = Counter(p["ip"] for p in parsed_entries)
    status_counts = Counter(p["status"] for p in parsed_entries)
    app_counts = Counter(p["app"] for p in parsed_entries)

    return render_template(
        "summary.html",
        total=total,
        host_counts=host_counts.most_common(),
        ip_counts=ip_counts.most_common(10),
        status_counts=status_counts.most_common(),
        app_counts=app_counts.most_common(),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )


if __name__ == "__main__":
    # Local run
    app.run(host="127.0.0.1", port=5070, debug=DEBUG_ENV)
