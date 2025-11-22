import os
from collections import Counter, defaultdict
import pathlib
import datetime
import json

from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from urllib.parse import urlparse, parse_qs

from utils import (
    find_app_version, parse_line, get_geo_for_ip,
    get_log_sources_for_app,
    read_lines_from_files, get_dates_from_request_args, tail_lines
)

# Detect debug mode from environment
DEBUG_ENV = os.environ.get("FLASK_DEBUG") == "1"

APP_VERSION= find_app_version()

LOG_FILE_PATH = pathlib.Path("static/data")

app_names = [
    "skrutable",
    "splitter-server",
    "vatayana",
    "panditya",
    "hansel",
    "firewatch",
    "kalpataru-grove",
]
app_names += [
    app_name + '-stg'
    for app_name in app_names
    if app_name != "splitter-server"
]

LOG_FILES = {
    app_name: LOG_FILE_PATH / f"{app_name}-archive"
    for app_name in app_names
}

HTTP_STATUS_CODES = {
    '200': 'OK',
    '201': 'Created',
    '202': 'Accepted',
    '204': 'No Content',
    '206': 'Partial Content',
    '301': 'Moved Permanently',
    '302': 'Found',
    '304': 'Not Modified',
    '400': 'Bad Request',
    '401': 'Unauthorized',
    '403': 'Forbidden',
    '404': 'Not Found',
    '405': 'Method Not Allowed',
    '444': 'No Response',
    '499': 'Client Closed Request',
    '500': 'Internal Server Error',
    '502': 'Bad Gateway',
    '503': 'Service Unavailable',
    '504': 'Gateway Timeout',
}

MAX_LINES_PER_FILE = 20

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.debug = DEBUG_ENV

@app.template_filter('commify')
def commify_filter(value):
    return "{:,}".format(value)


@app.route("/")
def index():
    start_date, end_date = get_dates_from_request_args(request.args)
    prod_app_names = sorted([name for name in app_names if not name.endswith('-stg')])
    stg_app_names = sorted([name for name in app_names if name.endswith('-stg')])

    selected_apps = session.get('selected_apps') or prod_app_names

    # Tail log data
    try:
        num_lines = int(request.args.get('num_lines', MAX_LINES_PER_FILE))
    except (ValueError, TypeError):
        num_lines = MAX_LINES_PER_FILE
    
    # Add some bounds
    if not 1 <= num_lines <= 10000:
        num_lines = MAX_LINES_PER_FILE

    # Top N parameter: controls the number of top IPs/User Agents shown
    # Get it from request args, fall back to session, then to default.
    top_n_str = request.args.get('top_n')
    if top_n_str:
        try:
            top_n = int(top_n_str)
            # Ensure top_n is within reasonable bounds
            if not 1 <= top_n <= 1000:
                top_n = session.get('top_n', 20)
        except (ValueError, TypeError):
            top_n = session.get('top_n', 20)
    else:
        top_n = session.get('top_n', 20)

    # Save the latest valid top_n to the session
    session['top_n'] = top_n

    # Determine the current view mode (uptime, requests, or raw)
    view_mode = request.args.get('view_mode', 'uptime')

    # Filters for raw view
    tail_filter_ip = request.args.get('ip') if view_mode == 'raw' else None
    tail_filter_status = request.args.get('status') if view_mode == 'raw' else None

    filter_ip = request.args.get('ip')
    filter_ua = request.args.get('ua')
    filter_status = request.args.get('status')

    # --- Data Processing ---
    total = 0
    total_req_time = 0.0
    ip_counts = Counter()
    ua_counts = Counter()
    status_counts = Counter()
    app_counts = defaultdict(Counter)
    ip_status_counts = defaultdict(Counter)
    
    # Initialize uptime data structures
    uptime_data = {}
    num_days = (end_date - start_date).days + 1
    for app_name in selected_apps:
        uptime_data[app_name] = {
            (start_date + datetime.timedelta(days=i)): 'red' for i in range(num_days)
        }

    app_logs = {}
    for app_name in selected_apps:
        log_files = get_log_sources_for_app(app_name, LOG_FILES, LOG_FILE_PATH, start_date, end_date)
        
        # Raw view data
        all_lines_bytes = []
        for log_file in log_files:
            all_lines_bytes.extend(tail_lines(log_file, num_lines))
        if len(all_lines_bytes) > num_lines:
            all_lines_bytes = all_lines_bytes[-num_lines:]
        app_logs[app_name] = [l.decode("utf-8", errors="replace") for l in all_lines_bytes]

        # Requests and Uptime data processing
        for line in read_lines_from_files(log_files):
            p = parse_line(line)
            if not p:
                continue
            
            # Apply filters for requests view
            if filter_ip and p["ip"] != filter_ip:
                continue
            if filter_ua and p["ua"] != filter_ua:
                continue
            if filter_status and p["status"] != filter_status:
                continue

            # Uptime data
            if p['time']:
                log_date = p['time'].date()
                if log_date in uptime_data.get(app_name, {}):
                    if uptime_data[app_name][log_date] == 'red':
                        uptime_data[app_name][log_date] = 'yellow'
                    if p['status'] in ['200', '401']:
                        uptime_data[app_name][log_date] = 'green'

            # Requests data
            total += 1
            ip_counts[p["ip"]] += 1
            ua_counts[p["ua"]] += 1
            status_counts[p["status"]] += 1
            app_counts[app_name][p["status"]] += 1
            ip_status_counts[p["ip"]][p["status"]] += 1
            if p["req_time"] is not None:
                total_req_time += p["req_time"]
    
    # --- Post-processing and Preparation for Render ---
    ip_counts_top = []
    for ip, count in ip_counts.most_common(top_n):
        ip_counts_top.append({
            "ip": ip,
            "count": count,
            "status_summary": dict(ip_status_counts[ip].most_common())
        })
    
    avg_req_time = total_req_time / total if total > 0 else 0

    # Create a structured list of apps for the template
    prod_app_names = sorted([name for name in app_names if not name.endswith('-stg')])
    stg_app_names = sorted([name for name in app_names if name.endswith('-stg')])

    app_pairs = []
    prod_apps_with_stg = [name.replace('-stg', '') for name in stg_app_names]

    for name in prod_app_names:
        if name in prod_apps_with_stg:
            app_pairs.append({'prd': name, 'stg': f'{name}-stg'})
        else:
            app_pairs.append({'prd': name, 'stg': None})

    # Sort pairs alphabetically by prod name for consistent order
    app_pairs.sort(key=lambda x: x['prd'])

    all_status_codes = sorted(list(status_counts.keys()))

    app_counts_table = []
    for app_name in selected_apps:
        app_data = {
            "name": app_name,
            "total": sum(app_counts[app_name].values()),
            "statuses": { code: app_counts[app_name].get(code, 0) for code in all_status_codes }
        }
        app_counts_table.append(app_data)
    
    # Sort by total descending
    app_counts_table.sort(key=lambda x: x['total'], reverse=True)

    app_counts_totals = defaultdict(int)
    for app_data in app_counts_table:
        app_counts_totals['total'] += app_data['total']
        for code, count in app_data['statuses'].items():
            app_counts_totals[code] += count



    return render_template(
        "index.html",
        app_version=APP_VERSION,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        app_names=app_names,
        app_pairs=app_pairs,
        all_apps_json=json.dumps(app_names),
        prd_apps_json=json.dumps(prod_app_names),
        stg_apps_json=json.dumps(stg_app_names),
        selected_apps=selected_apps,
        app_logs=app_logs,
        num_lines=num_lines,
        top_n=top_n,
        view_mode=view_mode,
        total=total,
        ip_counts=ip_counts_top,
        ua_counts=ua_counts.most_common(top_n),
        status_counts=status_counts.most_common(),
        app_counts=app_counts_table,
        app_counts_totals=app_counts_totals,
        all_status_codes=all_status_codes,
        http_status_codes=HTTP_STATUS_CODES,
        filter_ip=filter_ip,
        filter_ua=filter_ua,
        filter_status=filter_status,
        avg_req_time=avg_req_time,
        tail_filter_ip=tail_filter_ip,
        tail_filter_status=tail_filter_status,
        uptime_data=uptime_data,
    )





@app.route('/api/geo/<ip>')
def geo_for_ip(ip):
    geo_info = get_geo_for_ip(ip)
    return jsonify(geo_info)


@app.route("/select_apps", methods=['POST'])
def select_apps():
    # Update the session with the newly selected applications
    session['selected_apps'] = request.form.getlist('apps')
    
    # Attempt to redirect the user back to the page they came from,
    # preserving all existing query parameters to maintain the state (e.g., dates, top_n, view_mode).
    referrer_url = request.referrer
    if referrer_url:
        parsed_url = urlparse(referrer_url)
        query_params = parse_qs(parsed_url.query)
        
        # Convert list values from parse_qs to single values suitable for url_for.
        redirect_args = {k: v[0] for k, v in query_params.items()}
        
        # Prioritize parameters submitted directly with the form (e.g., view_mode),
        # then fallback to parameters from the referrer's query string,
        # and finally to hardcoded defaults if neither is available.
        # This ensures view state and other filters are maintained across app selections.
        redirect_args['view_mode'] = request.form.get('view_mode', redirect_args.get('view_mode', 'requests'))
        redirect_args['start_date'] = redirect_args.get('start_date', request.form.get('start_date', (datetime.date.today() - datetime.timedelta(days=7)).isoformat()))
        redirect_args['end_date'] = redirect_args.get('end_date', request.form.get('end_date', datetime.date.today().isoformat()))
        redirect_args['top_n'] = redirect_args.get('top_n', request.form.get('top_n', session.get('top_n', 20)))
        redirect_args['num_lines'] = redirect_args.get('num_lines', request.form.get('num_lines', MAX_LINES_PER_FILE))

        return redirect(url_for('index', **redirect_args))
    
    # If no referrer is available, redirect to the default index page.
    return redirect(url_for('index'))


if __name__ == "__main__":
    # Local run
    app.run(host="127.0.0.1", port=5070, debug=DEBUG_ENV)
