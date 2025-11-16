import os
from collections import Counter
import pathlib

from flask import Flask, render_template

from utils import find_app_version, tail_lines, parse_line

# Detect debug mode from environment
DEBUG_ENV = os.environ.get("FLASK_DEBUG") == "1"

APP_VERSION= find_app_version()

LOCAL_LOG_FILE_MAIN_PATH = pathlib.Path("../lookout-tower-sharded-data")
app_names = ["skrutable", "splitter-server", "vatayana", "panditya", "hansel"]
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


@app.route("/")
def index():
    return render_template(
        "base.html",
        app_version=APP_VERSION,
    )


@app.route("/raw")
def raw_view():
    app_logs = {}
    for app_name, path in LOG_FILES.items():
        lines = tail_lines(path, MAX_LINES_PER_FILE)
        text_lines = [l.decode("utf-8", errors="replace") for l in lines]
        app_logs[app_name] = text_lines

    return render_template("raw.html", app_logs=app_logs)


@app.route("/summary")
def summary_view():
    parsed_entries = []

    for app_name, path in LOG_FILES.items():
        lines = tail_lines(path, MAX_LINES_PER_FILE)
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
    )


if __name__ == "__main__":
    # Local run
    app.run(host="127.0.0.1", port=5070, debug=DEBUG_ENV)
