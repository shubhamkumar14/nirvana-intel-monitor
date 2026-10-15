import hashlib
import html
import re
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_TRACKING = ("utm_", "ocid", "cmpid", "fbclid", "gclid", "mc_", "cvid")


def strip_html(s):
    if not s:
        return ""
    s = _TAG.sub(" ", s)
    return _WS.sub(" ", html.unescape(html.unescape(s))).strip()


def norm_text(s):
    s = (s or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-")
    return _WS.sub(" ", s).strip()


def norm_title(title, publisher=None):
    t = title or ""
    if publisher and t.lower().endswith(" - " + publisher.lower()):
        t = t[: -(len(publisher) + 3)]
    t = re.sub(r"\s[-|]\s[^-|]{2,40}$", "", t)  # trailing " - Publisher" / " | Site"
    t = _NONWORD.sub(" ", t.lower())
    return _WS.sub(" ", t).strip()


def fingerprint(title, publisher=None):
    return hashlib.sha1(norm_title(title, publisher).encode()).hexdigest()[:12]


def url_hash(url):
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:16]


def canonical_url(url):
    try:
        p = urllib.parse.urlparse(url.strip())
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(_TRACKING)]
        return urllib.parse.urlunparse((p.scheme.lower(), p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), "", urllib.parse.urlencode(q), ""))
    except Exception:
        return url


def domain_of(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def parse_date(s):
    """Return aware UTC datetime or None."""
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        d = None
    if d is None:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y%m%dT%H%M%SZ", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f%z"):
            try:
                d = datetime.strptime(s.replace("Z", "+0000") if "%z" in fmt and s.endswith("Z") else s, fmt)
                break
            except Exception:
                continue
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None
