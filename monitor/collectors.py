"""Source collectors. Each returns a list of raw item dicts; failures are recorded, never raised.

Raw item schema:
  source_id, source_name, source_kind, lane_hint, query, title, url, publisher, published (ISO|None),
  snippet, tier_hint (int|None)
"""
import difflib
import hashlib
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timedelta

from .http import FetchError, RobotsDisallowed
from .textutil import domain_of, iso, parse_date, strip_html


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_feed(xml_text):
    """Parse RSS 2.0 or Atom into [{title,url,published,snippet,publisher,publisher_url}]."""
    xml_text = re.sub(r"^[^<]+", "", xml_text or "")
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        # Some feeds (seen on Bing News, 2026-10-16) ship bare '&' or control chars; repair and retry once.
        fixed = re.sub(r"&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)", "&amp;", xml_text)
        fixed = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", fixed)
        root = ET.fromstring(fixed.encode("utf-8"))
    out = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        rec = {"title": "", "url": "", "published": None, "snippet": "", "publisher": "", "publisher_url": ""}
        for ch in node:
            t = _local(ch.tag)
            txt = (ch.text or "").strip()
            if t == "title":
                rec["title"] = strip_html(txt)
            elif t == "link":
                rec["url"] = txt or ch.attrib.get("href", "") or rec["url"]
            elif t in ("pubdate", "published", "updated", "date") and not rec["published"]:
                rec["published"] = iso(parse_date(txt))
            elif t in ("description", "summary", "content", "encoded") and not rec["snippet"]:
                rec["snippet"] = strip_html(txt)[:800]
            elif t == "source":
                rec["publisher"] = txt
                rec["publisher_url"] = ch.attrib.get("url", "")
        if rec["title"] and rec["url"]:
            out.append(rec)
    return out


def _health(source_id, name, kind):
    return {"source_id": source_id, "name": name, "kind": kind, "status": "ok", "items": 0, "error": None, "ms": 0}


def _run(health, fn):
    t0 = time.time()
    try:
        items = fn()
        health["items"] = len(items)
        return items
    except RobotsDisallowed as e:
        health["status"], health["error"] = "skipped_robots", str(e)
    except FetchError as e:
        health["status"], health["error"] = "error", str(e)[:300]
    except ET.ParseError as e:
        health["status"], health["error"] = "error", f"parse error: {e}"
    except Exception as e:  # never let one source kill the run
        health["status"], health["error"] = "error", f"{type(e).__name__}: {e}"[:300]
    finally:
        health["ms"] = int((time.time() - t0) * 1000)
    return []


# ---------- RSS feeds (trade press, wires) ----------
def collect_feed(feed, fetch):
    h = _health(feed["id"], feed["name"], "rss")

    def go():
        recs = parse_feed(fetch(feed["url"], respect_robots=feed.get("robots", True)))
        return [{
            "source_id": feed["id"], "source_name": feed["name"], "source_kind": "rss", "lane_hint": None, "query": None,
            "title": r["title"], "url": r["url"], "publisher": feed["name"], "published": r["published"],
            "snippet": r["snippet"], "tier_hint": feed.get("tier"), "broad": True,
        } for r in recs]
    return _run(h, go), h


# ---------- Bing News RSS (query-targeted) ----------
def _bing_real_url(link):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    return q.get("url", [link])[0]


def collect_bing(query, lane, cfg, fetch):
    sid = "bing:" + query
    h = _health(sid, f"Bing News: {query}", "search")

    def go():
        url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": query, "format": "RSS", "qft": 'interval="8"'})
        recs = parse_feed(fetch(url, respect_robots=cfg.get("robots", True)))
        items = []
        for r in recs:
            real = _bing_real_url(r["url"])
            items.append({
                "source_id": "bing_news", "source_name": "Bing News", "source_kind": "search", "lane_hint": lane, "query": query,
                "title": r["title"], "url": real, "publisher": r["publisher"] or domain_of(real), "published": r["published"],
                "snippet": r["snippet"], "tier_hint": None, "broad": False,
            })
        return items
    return _run(h, go), h


# ---------- GDELT DOC 2.0 API (open news index) ----------
def collect_gdelt(query, lane, cfg, fetch):
    sid = "gdelt:" + query
    h = _health(sid, f"GDELT: {query}", "search")

    def go():
        params = {"query": f"{query} sourcelang:english", "mode": "artlist", "format": "json",
                  "maxrecords": str(cfg.get("max_records", 25)), "timespan": cfg.get("timespan", "7d"), "sort": "datedesc"}
        text = fetch("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params), respect_robots=cfg.get("robots", False))
        time.sleep(cfg.get("sleep_seconds", 6))  # GDELT asks for <= 1 request / 5s
        text = text.strip()
        if not text.startswith("{"):
            raise FetchError(f"GDELT non-JSON response: {text[:120]}")
        data = json.loads(text)
        return [{
            "source_id": "gdelt", "source_name": "GDELT", "source_kind": "search", "lane_hint": lane, "query": query,
            "title": a.get("title", ""), "url": a.get("url", ""), "publisher": a.get("domain", ""),
            "published": iso(parse_date(a.get("seendate", ""))), "snippet": "", "tier_hint": None, "broad": False,
        } for a in data.get("articles", []) if a.get("url") and a.get("title")]
    return _run(h, go), h


# ---------- Federal Register API ----------
def collect_federal_register(term, now, lookback_days, fetch):
    h = _health("fedreg:" + term, f"Federal Register: {term}", "api")

    def go():
        since = (now - timedelta(days=lookback_days * 3)).strftime("%Y-%m-%d")
        q = urllib.parse.urlencode({"conditions[term]": term, "order": "newest", "per_page": "20",
                                    "conditions[publication_date][gte]": since})
        data = json.loads(fetch("https://www.federalregister.gov/api/v1/documents.json?" + q, respect_robots=False))
        out = []
        for d in data.get("results", []) or []:
            agencies = ", ".join(a.get("name", "") for a in d.get("agencies", []) if a.get("name"))
            out.append({
                "source_id": "federal_register", "source_name": "Federal Register", "source_kind": "api", "lane_hint": "policy_macro",
                "query": term, "title": d.get("title", ""), "url": d.get("html_url", ""), "publisher": "Federal Register",
                "published": iso(parse_date(d.get("publication_date"))),
                "snippet": f"{d.get('type', '')} · {agencies}. {d.get('abstract') or ''}"[:800], "tier_hint": 1, "broad": True,
            })
        return out
    return _run(h, go), h


# ---------- SEC EDGAR full-text search ----------
def collect_sec(query, forms, now, lookback_days, fetch):
    h = _health("sec:" + query, f"SEC EDGAR: {query}", "api")
    ua = os.environ.get("SEC_USER_AGENT", "").strip()

    def go():
        if not ua:
            raise FetchError("SEC_USER_AGENT not set (SEC requires 'Name email' user agent)")
        start = (now - timedelta(days=lookback_days * 3)).strftime("%Y-%m-%d")
        q = urllib.parse.urlencode({"q": query, "forms": forms, "dateRange": "custom", "startdt": start, "enddt": now.strftime("%Y-%m-%d")})
        data = json.loads(fetch("https://efts.sec.gov/LATEST/search-index?" + q, headers={"User-Agent": ua}, respect_robots=False))
        out = []
        for hit in (data.get("hits", {}) or {}).get("hits", [])[:20]:
            s = hit.get("_source", {})
            adsh, _, fname = hit.get("_id", "").partition(":")
            ciks = s.get("ciks") or [""]
            url = f"https://www.sec.gov/Archives/edgar/data/{ciks[0].lstrip('0')}/{adsh.replace('-', '')}/{fname}" if adsh and fname else "https://www.sec.gov/edgar/search/"
            name = (s.get("display_names") or ["Unknown filer"])[0]
            form = s.get("form") or s.get("file_type", "")
            out.append({
                "source_id": "sec_edgar", "source_name": "SEC EDGAR", "source_kind": "api", "lane_hint": "competitor_move", "query": query,
                "title": f"{name} {form} filing mentions {query}", "url": url, "publisher": "SEC EDGAR",
                "published": iso(parse_date(s.get("file_date"))),
                "snippet": f"{name} filed {form} on {s.get('file_date')} matching full-text query {query}.", "tier_hint": 1, "broad": False,
            })
        return out
    return _run(h, go), h


# ---------- Page watch (diff of visible text) ----------
_SCRIPT = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)


def page_text(html_text):
    return "\n".join(l.strip() for l in strip_html_lines(html_text) if len(l.strip()) > 2)


def strip_html_lines(html_text):
    t = _SCRIPT.sub(" ", html_text or "")
    t = re.sub(r"<(br|p|div|li|h[1-6]|tr|section|article)[^>]*>", "\n", t, flags=re.I)
    return [strip_html(x) for x in t.split("\n")]


def collect_page_watch(page, snapshot_dir, fetch, now):
    h = _health("page:" + page["id"], f"Page watch: {page['name']}", "page")

    def go():
        txt = page_text(fetch(page["url"], respect_robots=True))
        os.makedirs(snapshot_dir, exist_ok=True)
        path = os.path.join(snapshot_dir, page["id"] + ".txt")
        old = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                old = fh.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)
        if old is None or old == txt:
            return []  # baseline or unchanged
        added = [l[2:] for l in difflib.unified_diff(old.splitlines(), txt.splitlines(), lineterm="", n=0)
                 if l.startswith("+") and not l.startswith("+++")]
        if not added:
            return []
        digest = hashlib.sha1("\n".join(added).encode()).hexdigest()[:8]
        return [{
            "source_id": "page_watch", "source_name": "Page watch", "source_kind": "page", "lane_hint": "competitor_move", "query": None,
            "title": f"{page['name']} page changed ({len(added)} new lines)", "url": page["url"] + f"#chg-{digest}",
            "publisher": domain_of(page["url"]), "published": iso(now), "snippet": " | ".join(added)[:800],
            "tier_hint": 1, "broad": False,
        }]
    return _run(h, go), h
