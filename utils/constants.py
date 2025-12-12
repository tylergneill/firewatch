import pathlib
import os

LOG_FILE_PATH = pathlib.Path("static/data")
# The path to the GeoLite2-City.mmdb file. This path should be mounted as a volume.
GEOIP_DATABASE_PATH = os.environ.get("GEOIP_DATABASE_PATH", "../firewatch-data-geoip-db/GeoLite2-City.mmdb")

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
