# Firewatch

Firewatch is a traffic-analysis and defense tool layered on top of detailed Nginx access logs. It gives quick visibility into both human and non-human traffic and helps surface abusive crawlers early enough to block them before they drag an app down.

## Conceptual Overview

Everything starts at the Nginx + logrotate layer. As soon as it’s reasonable, Nginx can be configured to fast-fail obviously irrelevant or hostile requests (e.g., `.php`, `.git`, `.env`) as 444s. Each app then produces **two** daily log streams:
- an **access** log for traffic that reached the app, and
- a **junk** log for traffic fast-failed at the Nginx boundary.

Firewatch’s UI ingests these daily logs directly. Access logs are parsed fully. junk logs get a lighter pass—mostly timestamp, IP, route pattern—just enough to summarize unwanted activity. While reading, the system builds a compact cache so that it never reprocesses data it has already seen.

When abusive crawlers are active, access logs inflate and become harder to interpret. Even so, the UI can still highlight the worst offenders quickly, since crawler behavior tends to cluster in related IP networks. Once those blocks are identified, adding their CIDR ranges to Nginx to deny with 403s protects the app going forward.

Offline, Firewatch adds a second layer of refinement. A full log-download utility pulls every rotated file and runs deeper analytics. One tool, `move_old_primary_junk`, rewrites history: it applies today’s fast-fail rules retroactively, relocating matching lines from access logs into junk logs. The cleaned set can then be re-uploaded so the live UI reflects a more realistic view of “real” traffic.

Another script, `generate_traffic_analytics`, mines the junk logs for IPs that ask for the junk that Nginx fast-fails. Those same IPs are then tagged inside access logs. There are too many of them to block individually at the Nginx layer, but tagging lets the UI distinguish them instantly. The script also flags IPs that hammer routes discouraged by `robots.txt`, applying a second tag.

Taken together, Firewatch removes the most obvious and voluminous garbage at the source (by shunting it into junk logs), and then applies a second, more probabilistic tagging layer inside the application at runtime. That combination leaves something much closer to a signal-only dataset: human-centric traffic patterns, meaningful request distributions, and contextual understanding of the junk.

## Core Components

*   **Web UI (`flask_app.py`)**: The main interface for viewing and analyzing log data from the cache.
*   **Offline Analytics Scripts**: A suite of tools for processing and analyzing logs offline.
    *   `move_old_primary_junk.py`: Retroactively sorts log entries into `access` and `junk` directories based on an evolving set of rules (e.g., junk probes, banned CIDRs).
    *   `generate_traffic_analytics.py`: Processes all access and junk logs to build a detailed analytics database, identifying patterns of abuse.
    *   `summarize_traffic_analytics.py`: Reads the analytics database to produce a human-readable summary report in the console and an optional JSON output file.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd firewatch
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up data directories:**
    The application expects sibling directories for data and cache. From within the `firewatch` project directory, you can create them like this:
    ```bash
    mkdir ../firewatch-data
    mkdir ../firewatch-data-cache
    ```
    Your log files should be placed inside `../firewatch-data` following the structure found in `static/data`.

4.  **GeoIP Database Setup:**
    This application uses the MaxMind GeoLite2 City database for IP geolocation. You need to download the database and make it available to the application.

    1.  **Sign up for a MaxMind account:** Go to the [MaxMind website](https://www.maxmind.com/en/geolite2/signup) and sign up for a GeoLite2 Free Downloadable Databases account.
    2.  **Download the database:** Download the `GeoLite2-City.mmdb` file.
    3.  **Setup for Local and Docker Usage:**
        To support both local offline analysis scripts (like `generate_traffic_analytics.py` used in `make data-refresh-full`) and the Docker container, create a directory named `firewatch-data-geoip-db` alongside the project directory and place the `.mmdb` file inside it.

        ```bash
        mkdir ../firewatch-data-geoip-db
        mv /path/to/downloaded/GeoLite2-City.mmdb ../firewatch-data-geoip-db/
        ```

        *   **Local Scripts:** The Python scripts default to looking in `../firewatch-data-geoip-db/GeoLite2-City.mmdb`.
        *   **Docker:** The `Makefile` targets (`make run`, `make run-official`) are configured to mount this local directory to `/data/geoip` in the container.


## Usage

### Running the Web UI

There are two ways to run the web application:

1.  **Local Development Server (Recommended for quick iteration):**
    Use the provided launch script, which starts a Flask development server.
    ```bash
    ./launch.sh
    ```
    The application will be available at `http://127.0.0.1:5071`.

2.  **Using Docker:**
    The `Makefile` provides a convenient way to build and run the application in a containerized environment. This is useful for testing in a production-like setup.
    ```bash
    make run
    ```
    This command builds the Docker image and runs it, mapping the local data and cache directories into the container. The application will be available at `http://127.0.0.1:5071`.

### Running Offline Analysis

The core analysis is performed by a series of Python scripts. They should generally be run in the following order.

1.  **Reclassify Past Abuse:**
    This script moves requests from known bad IPs or matching junk patterns from the `access` logs to the `junk` logs. It's safe to run this multiple times.
    ```bash
    python move_old_primary_junk.py
    ```

2.  **Recognize Unblocked Abuse:**
    After cleaning the logs, run this script to process all logs and build the analytics cache.
    ```bash
    python generate_traffic_analytics.py
    ```

3.  **Summarize Analytics:**
    Finally, inspect the results with this script, which prints summary tables to the console. It can also optionally generate a detailed JSON report with `--output-file`.
    ```bash
    python summarize_traffic_analytics.py
    ```

### Data Refresh Workflow

The `data-refresh-full` Makefile target executes a complete cycle of data synchronization, log processing, and cache rebuilding. This ensures local data is completely up-to-date, and the server is also updated with properly sharded daily logs and a current access/junk distinction.

```bash
make data-refresh-full
```
This command performs the following operations:
1.  **`bash utils/sync_data_down.sh`**: Downloads the latest raw log data from its source to your local `firewatch-data` directory.
2.  **`python utils/reshard_logs.py`**: Reorganizes and reshard log files within the `../firewatch-data` directory, optimizing them for processing.
3.  **`python utils/generate_traffic_analytics.py`**: Processes all access and junk logs to rebuild the detailed traffic analytics database.
4.  **`python utils/move_old_junk.py`**: Reclassifies log entries retroactively, moving traffic that matches current junk definitions from access logs to junk logs.
5.  **`python utils/update_cache.py --rebuild-all`**: Completely rebuilds the application's cache based on the newly processed and reclassified log data.
6.  **`bash utils/sync_data_up.sh`**: Uploads the processed log data (archived only) back to the server.

Afterward, `update_cache` still needs to be run on the server. Shell into the container:

```bash
docker exec -it firewatch /bin/bash
```

And inside the container, at `/app`:
```bash
nice -n 19 python utils/update_cache.py --rebuild-all
```
(`nice` helps deprioritize this backend task if any other requests on the host machine need resources.)

If you ran a `-local` variant for local testing and later want to push the processed data to the server, you can run the sync-up step on its own:

```bash
bash utils/sync_data_up.sh
```

Then run `update_cache` on the server as described above (using `--rebuild-all` or `--since-last-processed` as appropriate).

#### Recent-only refresh

`data-refresh-recent` and `data-refresh-recent-local` run the same pipeline but skip already-processed historical data. They auto-detect the last processed date from the archive filenames and limit resharding, junk-moving, and cache-building to that date onward.

```bash
make data-refresh-recent       # syncs updated logs up to server at the end
make data-refresh-recent-local # local only, no server sync
```

After `data-refresh-recent`, run `update_cache` on the server for just the recent date range:

```bash
docker exec -it firewatch /bin/bash
```

Inside the container, at `/app`:
```bash
nice -n 19 python utils/update_cache.py --since-last-processed
```