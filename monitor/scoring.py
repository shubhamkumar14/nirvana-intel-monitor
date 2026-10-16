"""Deterministic verification + ranking (no LLM involved, fully inspectable)."""
import math
import re

from .textutil import domain_of, norm_text, parse_date

_PUNCT = re.compile(r"[^a-z0-9 ]+")


def _loose(s):
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", norm_text(s))).strip()


def evidence_found(quote, title, snippet):
    """True if the LLM's evidence quote appears verbatim (case/whitespace/punctuation-insensitive) in fetched text."""
    q = _loose(quote)
    if len(q) < 8:
        return False
    return q in _loose(f"{title} {snippet}")


def source_tier(url, publisher, tier_hint, cfg, competitor_domains):
    if tier_hint:
        return int(tier_hint)
    d = domain_of(url)
    if any(d == cd or d.endswith("." + cd) for cd in competitor_domains):
        return 1
    for tier in ("1", "2"):
        if any(d == x or d.endswith("." + x) for x in cfg["source_tiers"].get(tier, [])):
            return int(tier)
    return 3


TIER_SCORE = {1: 1.0, 2: 0.75, 3: 0.5, 4: 0.25}


def recency_score(published_iso, now, half_life):
    d = parse_date(published_iso) if published_iso else None
    if not d:
        return 0.3, None
    age = max(0.0, (now - d).total_seconds() / 86400)
    return math.exp(-math.log(2) * age / half_life), round(age, 1)


def verification_status(event):
    publishers = {s["publisher_key"] for s in event["sources"]}
    if len(publishers) >= 2:
        return "Corroborated"
    if event["best_tier"] == 1:
        return "Confirmed (primary source)"
    return "Reported"


def score_event(event, cfg, now, priority_lookup):
    w = cfg["weights"]
    rec, age = recency_score(event.get("published"), now, w.get("recency_half_life_days", 7))
    prios = [priority_lookup[c] for c in event.get("watchlist_companies", []) if c in priority_lookup]
    prio = max(prios) if prios else (0.5 if event["lane"] != "competitor_move" else 0.4)
    s = (w["materiality"] * event["materiality"] / 5 + w["priority"] * prio + w["source_tier"] * TIER_SCORE.get(event["best_tier"], 0.5)
         + w["recency"] * rec + w["last_mile_fit"] * event["last_mile_fit"])
    if len({x["publisher_key"] for x in event["sources"]}) >= 2:
        s += 0.03  # small corroboration bonus
    event["score"] = round(min(1.0, s) * 100, 1)
    event["age_days"] = age
    event["score_parts"] = {"materiality": event["materiality"], "priority": round(prio, 2), "tier": event["best_tier"],
                            "recency": round(rec, 2), "last_mile_fit": event["last_mile_fit"]}
    return event


def confidence(event):
    """Deterministic confidence label + reason (shown on every card)."""
    pubs = {s["publisher_key"] for s in event["sources"]}
    reasons = []
    pts = 0
    if event["best_tier"] == 1:
        pts += 2; reasons.append("primary source")
    elif event["best_tier"] == 2:
        pts += 1; reasons.append("trade press")
    else:
        reasons.append("general news")
    if len(pubs) >= 2:
        pts += 2; reasons.append(f"{len(pubs)} independent publishers")
    else:
        reasons.append("single source")
    if event.get("date_known"):
        pts += 1
    else:
        reasons.append("publish date unknown")
    if str(event.get("classifier", "")).startswith("rules"):
        pts -= 1; reasons.append("rules classifier (no AI)")
    level = "High" if pts >= 3 else "Medium" if pts >= 2 else "Low"
    return level, ", ".join(reasons)
