import os
from collections import Counter
import pathlib


from flask import Flask, render_template, request, session, redirect, url_for, jsonify

from utils import (
    find_app_version, parse_line, get_geo_for_ip,
    find_archived_logs_for_daterange, get_log_sources_for_app,
    read_lines_from_files, get_dates_from_request_args, tail_lines
)

# Detect debug mode from environment
DEBUG_ENV = os.environ.get("FLASK_DEBUG") == "1"

APP_VERSION= find_app_version()

LOCAL_LOG_FILE_MAIN_PATH = pathlib.Path("../firewatch-data")
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


@app.route("/")
def index():
    start_date, end_date = get_dates_from_request_args(request.args)
    selected_apps = session.get('selected_apps') or app_names
    return render_template(
        "base.html",
        app_version=APP_VERSION,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        app_names=app_names,
        selected_apps=selected_apps,
    )


@app.route("/raw")
def raw_view():
    start_date, end_date = get_dates_from_request_args(request.args)
    selected_apps = session.get('selected_apps') or app_names

    try:
        num_lines = int(request.args.get('num_lines', MAX_LINES_PER_FILE))
    except (ValueError, TypeError):
        num_lines = MAX_LINES_PER_FILE
    
    # Add some bounds
    if not 1 <= num_lines <= 10000:
        num_lines = MAX_LINES_PER_FILE

    app_logs = {}
    for app_name in selected_apps:
        log_files = get_log_sources_for_app(app_name, LOG_FILES, LOG_FILE_MAIN_PATH, start_date, end_date)

        all_lines = []
        for log_file in log_files:
            lines = tail_lines(log_file, num_lines)
            all_lines.extend(lines)

        if len(all_lines) > num_lines:
            all_lines = all_lines[-num_lines:]

        text_lines = [l.decode("utf-8", errors="replace") for l in all_lines]
        app_logs[app_name] = text_lines

    return render_template(
        "raw.html",
        app_logs=app_logs,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        app_names=app_names,
        selected_apps=selected_apps,
        num_lines=num_lines,
    )


@app.route("/summary")
def summary_view():
    start_date, end_date = get_dates_from_request_args(request.args)
    selected_apps = session.get('selected_apps') or app_names

    parsed_entries = []

    for app_name in selected_apps:
        log_files = get_log_sources_for_app(app_name, LOG_FILES, LOG_FILE_MAIN_PATH, start_date, end_date)
        lines = read_lines_from_files(log_files)
        for l in lines:
            p = parse_line(l)
            if not p:
                continue

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

    ip_counts_top20 = [{"ip": ip, "count": count} for ip, count in ip_counts.most_common(20)]

    total_req_time = sum(p['req_time'] for p in parsed_entries if p['req_time'] is not None)
    avg_req_time = total_req_time / total if total > 0 else 0

    return render_template(
        "summary.html",
        total=total,
        ip_counts=ip_counts_top20,
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


@app.route('/api/geo/<ip>')
def geo_for_ip(ip):
    geo_info = get_geo_for_ip(ip)
    return jsonify(geo_info)


@app.route("/select_apps", methods=['POST'])
def select_apps():
    session['selected_apps'] = request.form.getlist('apps')
    # Redirect back to the referring page
    return redirect(request.referrer or url_for('index'))


if __name__ == "__main__":
    # Local run
    app.run(host="127.0.0.1", port=5070, debug=DEBUG_ENV)
