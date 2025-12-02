import os
from collections import Counter, defaultdict
import pathlib
import datetime
import json
import shelve

from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from urllib.parse import urlparse, parse_qs

from utils import (
    find_app_version, parse_line, get_geo_for_ip,
    get_log_sources_for_app,
    read_lines_from_files, get_dates_from_request_args, tail_lines,
    _process_single_log_file
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

# Ensure the cache directory exists once at startup.
CACHE_DIR = "static/cache"
os.makedirs(os.path.join(app.root_path, CACHE_DIR), exist_ok=True)
CACHE_FILE = os.path.join(CACHE_DIR, "firewatch_cache.db")

@app.template_filter('commify')
def commify_filter(value):
    return "{:,}".format(value)


@app.route("/")
def index():
    start_date, end_date = get_dates_from_request_args(request.args)
    prod_app_names = sorted([name for name in app_names if not name.endswith('-stg')])
    non_default_items = {'firewatch', 'kalpataru-grove'}
    default_prod_app_names = [app for app in prod_app_names if app not in non_default_items]
    stg_app_names = sorted([name for name in app_names if name.endswith('-stg')])

    selected_apps = session.get('selected_apps') or default_prod_app_names
    selected_apps.sort()

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

    # Determine the current view mode (uptime, requests, or logs)
    view_mode = request.args.get('view_mode', 'uptime')

    # Filters for logs view
    tail_filter_ip = request.args.get('ip') if view_mode == 'logs' else None
    tail_filter_status = request.args.get('status') if view_mode == 'logs' else None

    filter_ip = request.args.get('ip')
    filter_ua = request.args.get('ua')
    filter_status = request.args.get('status')

    # --- Data Processing ---
    # Initialize aggregated data structures
    total = 0
    total_req_time = 0.0
    ip_counts = Counter()
    ua_counts = Counter()
    route_app_counts = defaultdict(Counter)
    status_counts = Counter()
    app_counts = defaultdict(Counter)
    ip_status_counts = defaultdict(Counter)
    app_response_times = defaultdict(list)
    app_ip_sets = defaultdict(set)
    app_requests_by_day = defaultdict(lambda: defaultdict(int))
    
    # Initialize uptime data structures
    uptime_data = {}
    num_days = (end_date - start_date).days + 1
    for app_name in selected_apps:
        uptime_data[app_name] = {
            (start_date + datetime.timedelta(days=i)): {'2xx': 0, '5xx': 0, 'total': 0} for i in range(num_days)
        }

    today_str = datetime.date.today().isoformat()
    app_logs = {} # Still need to collect raw lines for the 'logs' view

    with shelve.open(CACHE_FILE) as cache:
        for app_name in selected_apps:
            log_files_for_app = get_log_sources_for_app(app_name, LOG_FILES, LOG_FILE_PATH, start_date, end_date)
            
            for log_file in log_files_for_app:
                log_file_str = str(log_file.resolve())
                file_is_present_day = today_str in log_file.name

                processed_file_data = None
                if not file_is_present_day and log_file_str in cache:
                    processed_file_data = cache[log_file_str]
                else:
                    processed_file_data = _process_single_log_file(log_file_str, app_names)
                    if not file_is_present_day:
                        cache[log_file_str] = processed_file_data
                
                if not processed_file_data:
                    continue

                total += processed_file_data["total"]
                total_req_time += processed_file_data["total_req_time"]
                ip_counts.update(processed_file_data["ip_counts"])
                ua_counts.update(processed_file_data["ua_counts"])
                for route, counts in processed_file_data["route_app_counts"].items():
                    route_app_counts[route].update(counts)
                status_counts.update(processed_file_data["status_counts"])
                for app_n, counts in processed_file_data["app_counts"].items():
                    app_counts[app_n].update(counts)
                for ip, counts in processed_file_data["ip_status_counts"].items():
                    ip_status_counts[ip].update(counts)
                app_response_times[app_name].extend(processed_file_data["app_response_times"].get(app_name, []))
                app_ip_sets[app_name].update(processed_file_data["app_ip_sets"].get(app_name, []))
                
                for date_str, count in processed_file_data["app_requests_by_day"].get(app_name, {}).items():
                    app_requests_by_day[app_name][datetime.date.fromisoformat(date_str)] += count

                for date_str, counts in processed_file_data["uptime_data"].get(app_name, {}).items():
                    date_obj = datetime.date.fromisoformat(date_str)
                    if date_obj in uptime_data.get(app_name, {}):
                        uptime_data[app_name][date_obj]['2xx'] += counts.get('2xx', 0)
                        uptime_data[app_name][date_obj]['5xx'] += counts.get('5xx', 0)
                        uptime_data[app_name][date_obj]['total'] += counts.get('total', 0)

            # Raw view data
            if tail_filter_ip or tail_filter_status:
                filtered_lines = []
                for line_bytes in read_lines_from_files(log_files_for_app):
                    p = parse_line(line_bytes)
                    if not p:
                        continue
                    
                    ip_match = (not tail_filter_ip) or (p['ip'] == tail_filter_ip)
                    status_match = (not tail_filter_status) or (p['status'] == tail_filter_status)

                    if ip_match and status_match:
                        filtered_lines.append(line_bytes.decode("utf-8", errors="replace"))
                
                app_logs[app_name] = filtered_lines
            else:
                raw_lines_to_fetch = num_lines
                all_lines_bytes = []
                for log_file in log_files_for_app:
                    all_lines_bytes.extend(tail_lines(log_file, raw_lines_to_fetch))
                if len(all_lines_bytes) > raw_lines_to_fetch:
                    all_lines_bytes = all_lines_bytes[-raw_lines_to_fetch:]
                app_logs[app_name] = [l.decode("utf-8", errors="replace") for l in all_lines_bytes]
    
    # --- Post-processing and Preparation for Render ---

    # Prepare data for the Per App Per Day chart
    all_dates = [start_date + datetime.timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    requests_by_day_labels = [date.strftime('%Y-%m-%d') for date in all_dates]
    requests_by_day_data = {}
    for app_name in selected_apps:
        requests_by_day_data[app_name] = [app_requests_by_day[app_name].get(date, 0) for date in all_dates]

    # Finalize uptime data colors
    final_uptime_data = {}
    for app_name, daily_counts in uptime_data.items():
        final_uptime_data[app_name] = {}
        for date, counts in daily_counts.items():
            
            color = 'red' # Default to red if not explicitly set below

            if counts['total'] == 0:
                color = 'no-activity' # Dark gray for zero activity
            elif counts['2xx'] == 0:
                color = 'red' # No 200s, but there is activity
            else:
                # We have activity and 2xx requests
                if counts['5xx'] == 0:
                    color = 'blue' # Activity, 200s, and NO 500s
                else:
                    # We have 5xx errors, calculate ratio
                    ratio = counts['5xx'] / counts['2xx']
                    if ratio >= 0.1: # User's threshold for "too high"
                        color = 'yellow' # High ratio of 5xx to 2xx
                    else:
                        color = 'green' # Low ratio of 5xx to 2xx
            
            final_uptime_data[app_name][date] = color
    
    uptime_data = final_uptime_data

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
    
    # Sort by name
    app_counts_table.sort(key=lambda x: x['name'])

    app_counts_totals = defaultdict(int)
    for app_data in app_counts_table:
        app_counts_totals['total'] += app_data['total']
        for code, count in app_data['statuses'].items():
            app_counts_totals[code] += count

    total_route_counts = Counter()
    for route, app_counts_for_route in route_app_counts.items():
        total_route_counts[route] = sum(app_counts_for_route.values())
    
    top_routes_names = [route for route, count in total_route_counts.most_common(top_n)]

    route_counts_list = []
    for route_name in top_routes_names:
        app_counts_for_route = route_app_counts[route_name]
        for app_name, count in app_counts_for_route.items():
            route_counts_list.append({
                "route": route_name,
                "app": app_name,
                "count": count
            })
            
    route_counts_list.sort(key=lambda x: (total_route_counts[x['route']], x['count']), reverse=True)

    def calculate_percentiles(data, percentiles_to_calc):
        if not data:
            return {p: 0 for p in percentiles_to_calc}
        data.sort()
        n = len(data)
        results = {}
        for p in percentiles_to_calc:
            idx = int((p / 100) * (n - 1))
            results[p] = data[idx] * 1000
        return results

    percentiles_to_calculate = [50, 75, 90, 95, 99]
    app_percentile_stats = []

    sorted_apps = sorted(selected_apps)

    for app_name in sorted_apps:
        response_times = app_response_times.get(app_name, [])
        total_requests = sum(app_counts[app_name].values())
        if not response_times:
            # Still show the app, but with 0 stats
            stats = {p: 0 for p in percentiles_to_calculate}
        else:
            stats = calculate_percentiles(response_times, percentiles_to_calculate)

        app_percentile_stats.append({
            "name": app_name,
            "total": total_requests,
            "percentiles": stats
        })

    unique_visitor_counts = []
    for app_name in selected_apps:
        unique_visitor_counts.append({
            "app": app_name,
            "count": len(app_ip_sets[app_name])
        })
    
    unique_visitor_counts.sort(key=lambda x: x['count'], reverse=True)

    uptime_color_explanations = {
        'no-activity': 'No activity',
        'red': 'Activity, but no 200s',
        'yellow': 'High 5xx/2xx error ratio (>= 10%)',
        'green': 'Healthy (5xx/2xx < 10%)',
        'blue': 'Activity, 200s, and no 5xx errors'
    }

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
        selected_apps_json=json.dumps(selected_apps),
        app_logs=app_logs,
        num_lines=num_lines,
        top_n=top_n,
        view_mode=view_mode,
        total=total,
        ip_counts=ip_counts_top,
        ua_counts=ua_counts.most_common(top_n),
        route_counts_list=route_counts_list,
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
        app_percentile_stats=app_percentile_stats,
        unique_visitor_counts=unique_visitor_counts,
        percentiles_to_calculate=percentiles_to_calculate,
        uptime_color_explanations=uptime_color_explanations,
        requests_by_day_labels=json.dumps(requests_by_day_labels),
        requests_by_day_data=json.dumps(requests_by_day_data),
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
