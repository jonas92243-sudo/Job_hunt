"""Small JSON-over-HTTP helper with gzip, ETag and retry support."""
import gzip
import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

USER_AGENT = "Mozilla/5.0 (compatible; me-job-scanner/1.0)"
TIMEOUT = 30
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_PER_HOST = 8    # many companies share one API host, so cap simultaneous requests to it
# Workday throttles by caller across all of its company subdomains.
SHARED_POOLS = {"myworkdayjobs.com": 3}
RATE_LIMIT_WAITS = [4, 10, 20, 30]   # seconds to pause after each HTTP 429

_host_slots = {}
_host_slots_lock = threading.Lock()


def _slot(url):
    host = urlsplit(url).netloc
    limit = MAX_PER_HOST
    for suffix, shared_limit in SHARED_POOLS.items():
        if host.endswith(suffix):
            host, limit = suffix, shared_limit
    with _host_slots_lock:
        if host not in _host_slots:
            _host_slots[host] = threading.BoundedSemaphore(limit)
        return _host_slots[host]


class HttpError(Exception):
    def __init__(self, status, url):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


class NotJobData(Exception):
    """The server answered, but not with the JSON a job board normally returns."""


class Response:
    def __init__(self, status, data, etag):
        self.status = status
        self.data = data
        self.etag = etag

    @property
    def not_modified(self):
        return self.status == 304


def request_text(url, retries=2):
    """GET a web page or feed and return it as text."""
    return _request(url, None, None, retries, "text/html,application/xml,*/*", parse=False).data


def request_json(url, body=None, etag=None, retries=2):
    """GET (or POST when body is given) and parse the JSON response.

    Passing the etag from an earlier response makes the server answer 304
    with no payload when nothing changed.
    """
    return _request(url, body, etag, retries, "application/json", parse=True)


def _request(url, body, etag, retries, accept, parse):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Encoding": "gzip",
    }
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if etag:
        headers["If-None-Match"] = etag

    last_error = None
    failures = rate_limits = 0
    while failures <= retries and rate_limits <= len(RATE_LIMIT_WAITS):
        req = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with _slot(url), urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                data = raw.decode("utf-8", "replace")
                if parse:
                    data = json.loads(data) if raw else None
                return Response(resp.status, data, resp.headers.get("ETag"))
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return Response(304, None, etag)
            last_error = HttpError(e.code, url)
            if e.code == 429:
                # Being told to slow down is not a failure: wait as asked, then go on.
                if rate_limits < len(RATE_LIMIT_WAITS):
                    wait = RATE_LIMIT_WAITS[rate_limits]
                    asked = e.headers.get("Retry-After", "")
                    if asked.isdigit():
                        wait = min(max(wait, int(asked)), 60)
                    time.sleep(wait)
                rate_limits += 1
                continue
            if e.code not in RETRY_STATUSES:
                raise last_error from None
        except json.JSONDecodeError:
            last_error = NotJobData(
                "the site answered with a web page instead of job data (usually maintenance)"
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_error = e
        failures += 1
        time.sleep(2 * failures)
    raise last_error
