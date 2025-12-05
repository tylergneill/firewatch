# Firewatch

Firewatch is a traffic-analysis and defense tool layered on top of detailed Nginx access logs. It gives quick visibility into both human and non-human traffic and helps surface abusive crawlers early enough to block them before they drag an app down.

## Conceptual Overview

Everything starts at the Nginx + logrotate layer. As soon as it’s reasonable, Nginx can be configured to fast-fail obviously irrelevant or hostile requests (e.g., `.php`, `.git`, `.env`) as 444s. Each app then produces **two** daily log streams:
- an **access** log for traffic that reached the app, and
- a **junk** log for traffic fast-failed at the Nginx boundary.

Firewatch’s UI ingests these daily logs directly. Access logs are parsed fully. junk logs get a lighter pass—mostly timestamp, IP, route pattern—just enough to summarize unwanted activity. While reading, the system builds a compact cache so that it never reprocesses data it has already seen.

When abusive crawlers are active, access logs inflate and become harder to interpret. Even so, the UI can still highlight the worst offenders quickly, since crawler behavior tends to cluster in related IP networks. Once those blocks are identified, adding their CIDR ranges to Nginx to deny with 403s protects the app going forward.

Offline, Firewatch adds a second layer of refinement. A full log-download utility pulls every rotated file and runs deeper analytics. One tool, `reclassify_past_abuse`, rewrites history: it applies today’s fast-fail rules retroactively, relocating matching lines from access logs into junk logs. The cleaned set can then be re-uploaded so the live UI reflects a more realistic view of “real” traffic.

Another script, `recognize_unblocked_abuse`, mines the junk logs for IPs that ask for the junk that Nginx fast-fails. Those same IPs are then tagged inside access logs. There are too many of them to block individually at the Nginx layer, but tagging lets the UI distinguish them instantly. The script also flags IPs that hammer routes discouraged by `robots.txt`, applying a second tag.

Taken together, Firewatch removes the most obvious and voluminous garbage at the source (by shunting it into junk logs), and then applies a second, more probabilistic tagging layer inside the application at runtime. That combination leaves something much closer to a signal-only dataset: human-centric traffic patterns, meaningful request distributions, and contextual understanding of the junk.

## Core Components

*   **Web UI (`flask_app.py`)**: The main interface for viewing and analyzing log data from the cache.
*   **Offline Analytics Scripts**: A suite of tools for processing and analyzing logs offline.
    *   `reclassify_past_junk.py`: Retroactively sorts log entries into `access` and `junk` directories based on an evolving set of rules (e.g., junk probes, banned CIDRs).
    *   `recognize_junk_in_access.py`: Processes all access and junk logs to build a detailed analytics database, identifying patterns of abuse.
    *   `inspect_analytics.py`: Reads the analytics database to produce a human-readable summary report in the console and an optional JSON output file.

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
    python reclassify_past_junk.py
    ```

2.  **Recognize Unblocked Abuse:**
    After cleaning the logs, run this script to process all logs and build the analytics cache.
    ```bash
    python recognize_junk_in_access.py
    ```

3.  **Inspect Analytics:**
    Finally, inspect the results with this script, which prints summary tables to the console. It can also optionally generate a detailed JSON report with `--output-file`.
    ```bash
    python inspect_analytics.py
    ```