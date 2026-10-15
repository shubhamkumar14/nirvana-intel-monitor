"""Polite HTTP layer: robots.txt check (per source), retries, timeouts. Stdlib only."""
import gzip
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

UA = "NirvanaIntelMonitor/0.1 (competitor-intelligence research bot; daily, low-volume)"


class FetchError(Exception):
    pass


class RobotsDisallowed(FetchError):
    pass


_robots_cache = {}


def _raw_get(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            charset = r.headers.get_content_charset() or "utf-8"
            return r.status, body.decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def robots_allowed(url, ua=UA):
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    rp = _robots_cache.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            status, text = _raw_get(base + "/robots.txt", timeout=15)
            if status == 200:
                rp.parse(text.splitlines())
            elif status in (401, 403):
                rp.disallow_all = True
            else:
                rp.allow_all = True
        except Exception:
            rp.allow_all = True  # robots unreachable -> standard crawler convention is allow
        _robots_cache[base] = rp
    return rp.can_fetch(ua, url)


def get(url, headers=None, respect_robots=True, retries=2, timeout=25):
    """Return response text or raise FetchError / RobotsDisallowed."""
    if url.startswith("fixture://"):
        raise FetchError("fixture URLs need a fixture fetcher")
    if respect_robots and not robots_allowed(url):
        raise RobotsDisallowed(f"robots.txt disallows {url}")
    last = None
    for attempt in range(retries + 1):
        try:
            status, text = _raw_get(url, headers, timeout)
            if status == 200:
                return text
            last = f"HTTP {status}"
            if status in (429, 500, 502, 503, 504):
                time.sleep(3 * (attempt + 1))
                continue
            break
        except Exception as e:  # network errors
            last = f"{type(e).__name__}: {e}"
            time.sleep(2 * (attempt + 1))
    raise FetchError(last or "unknown error")
