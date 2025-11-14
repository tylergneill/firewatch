import pathlib
import re


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
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            block = -1024
            data = b""
            while len(data.splitlines()) <= n and -block < size:
                f.seek(block, 2)
                data = f.read(-block) + data
                block *= 2
        return data.splitlines()[-n:]
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

    return {
        "raw": s,
        "ip": d["ip"],
        "host": d["host"],
        "status": d["status"],
        "path": d["path"],
        "method": d["method"],
        "req_time": req_time,
    }