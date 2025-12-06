import ipaddress
import re

# --- Configuration ---
BLOCKED_CIDRS = [
    "146.174.0.0/16",
    "202.76.0.0/16",
    "8.160.0.0/16",
    "47.82.0.0/16",
    "47.79.51.0/24",
    "66.249.75.0/24",
]

# --- Pre-compile networks for performance ---
BLOCKED_NETWORKS = [ipaddress.ip_network(cidr) for cidr in BLOCKED_CIDRS]


# --- New Configuration for Junk Probes ---
JUNK_PROBE_PATTERNS = [
    r"\.git(/|$)",
    r"(^|/)\.env",
    r"/(env|git|config|configs|conf|settings|production|app|home)\.zip$",
    r"\.php$",
    r"/cgi-bin/",
]

# --- Pre-compile junk regexes for performance ---
JUNK_PROBE_REGEXES = [re.compile(p, re.IGNORECASE) for p in JUNK_PROBE_PATTERNS]


def is_junk_probe(uri_str: str) -> bool:
    """Checks if a given request URI is a junk/security probe."""
    if not uri_str:
        return False
    for regex in JUNK_PROBE_REGEXES:
        if regex.search(uri_str):
            return True
    return False
