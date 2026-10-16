"""AI classification (Claude) with a deterministic rules fallback.

The LLM only sees the title + snippet we fetched and must quote evidence verbatim from it;
verify.py rejects anything it cannot find in the source text.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

LANES = ["competitor_move", "market_driver", "research", "policy_macro", "irrelevant"]
EVENT_TYPES = ["product_launch", "market_entry", "market_exit", "pricing_rate", "filing_regulatory", "funding",
               "partnership_distribution", "m_and_a", "leadership", "litigation_claims", "trend_data", "other"]

SYSTEM_PROMPT = """You are a competitive-intelligence analyst for Nirvana Insurance, a telematics-based commercial auto insurance MGA evaluating a new product for US LAST-MILE DELIVERY fleets (Amazon DSPs, FedEx ISPs, courier/parcel fleets, gig and on-demand delivery drivers, cargo vans and box trucks).

For each news item decide whether it matters to that opportunity and classify it. Rules:
- Use ONLY the text provided for the item. Never add facts from memory.
- evidence_quote MUST be copied verbatim (exact characters) from the item's title or snippet, max 25 words.
- summary: max 30 words, your own words, factual, no hype.
- lane:
  competitor_move = a specific insurer/MGA/insurtech/telematics or fleet-platform company doing something (launch, entry, exit, pricing/rate, filing, funding, partnership, M&A, leadership, litigation)
  market_driver   = industry headwind/tailwind for last-mile commercial auto (claims severity, verdicts, rates, delivery volumes, DSP economics, EV/autonomy, repair costs)
  research        = report/survey/outlook/data release about the market
  policy_macro    = legislation, regulation, courts, tariffs, macro/geopolitical factors affecting the market
  irrelevant      = personal auto only, unrelated industries, non-US with no US read-through, generic stock commentary
- direction: tailwind / headwind / neutral FOR A NEW ENTRANT selling last-mile commercial auto insurance.
- materiality 1-5: 5 = direct competitor launches/exits/prices a last-mile product or major regulatory change; 1 = tangential.
- last_mile_fit 0.0-1.0: how specifically the item is about last-mile delivery commercial auto.
- companies: organizations named in the item that are insurers, MGAs, insurtechs, telematics or delivery platforms (exact names as written).
- implication: max 30 words. What this means for Nirvana's last-mile entry (target: Amazon DSP / FedEx ISP / courier fleets; telematics underwriting; broker distribution). Concrete and specific; say "Context only" if nothing actionable. Clearly an analyst judgment, never a new fact.
- action: one of "respond" (Nirvana should consider a response soon), "watch" (track for follow-up), "context" (background only).
Return ONLY a JSON array, one object per item, keys: id, lane, event_type, direction, materiality, last_mile_fit, companies, summary, evidence_quote, implication, action."""


def _items_payload(items):
    return [{"id": it["_cid"], "title": it["title"], "publisher": it.get("publisher"), "published": it.get("published"),
             "snippet": (it.get("snippet") or "")[:600], "search_query": it.get("query")} for it in items]


class AnthropicClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "errors": 0}

    @property
    def available(self):
        return bool(self.api_key)

    def complete(self, model, system, user, max_tokens=4000):
        body = json.dumps({"model": model, "max_tokens": max_tokens, "temperature": 0, "system": system,
                           "messages": [{"role": "user", "content": user}]}).encode()
        for attempt in range(4):
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
                "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = json.loads(r.read())
                u = data.get("usage", {})
                self.usage["input_tokens"] += u.get("input_tokens", 0)
                self.usage["output_tokens"] += u.get("output_tokens", 0)
                self.usage["calls"] += 1
                return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                    time.sleep(5 * (attempt + 1))
                    continue
                self.usage["errors"] += 1
                raise RuntimeError(f"Anthropic API HTTP {e.code}: {e.read()[:300]!r}")
        self.usage["errors"] += 1
        raise RuntimeError("Anthropic API retries exhausted")


class OpenAICompatClient:
    """Free-tier providers via OpenAI-compatible chat endpoints.

    github: GitHub Models — auth with the workflow's own GITHUB_TOKEN (needs `permissions: models: read`), no extra account.
    gemini: Google AI Studio free key (GEMINI_API_KEY). Free-tier prompts may be reviewed/used by Google; we only send public news.
    """
    PROVIDERS = {
        "github": {"url": "https://models.github.ai/inference/chat/completions", "env": "GITHUB_TOKEN",
                   "models": {"classify": "openai/gpt-4.1-mini", "digest": "openai/gpt-4.1-mini"},
                   "fallbacks": ["openai/gpt-4o-mini", "openai/gpt-5-mini", "meta/Llama-3.3-70B-Instruct"]},
        "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "env": "GEMINI_API_KEY",
                   "models": {"classify": "gemini-flash-latest", "digest": "gemini-flash-latest"},
                   "fallbacks": ["gemini-flash-lite-latest"]},
    }

    def __init__(self, provider):
        p = self.PROVIDERS[provider]
        self.provider, self.url = provider, p["url"]
        self.api_key = os.environ.get(p["env"], "").strip()
        m = os.environ.get("LLM_MODEL", "").strip()
        self.models = {"classify": m or p["models"]["classify"], "digest": os.environ.get("LLM_DIGEST_MODEL", "").strip() or m or p["models"]["digest"]}
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "errors": 0, "provider": provider}
        self.fallbacks = [m for m in p.get("fallbacks", []) if m != self.models["classify"]]

    @property
    def available(self):
        return bool(self.api_key)

    def complete(self, model, system, user, max_tokens=4000):
        model = getattr(self, "_active", None) or model
        body = json.dumps({"model": model, "max_tokens": max_tokens, "temperature": 0,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
        for attempt in range(4):
            req = urllib.request.Request(self.url, data=body, headers={
                "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                "Accept": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    raw = r.read()
                    try:
                        data = json.loads(raw)
                    except ValueError:
                        raise RuntimeError(f"{self.provider} non-JSON response (HTTP {r.status}, {r.headers.get('Content-Type')}): {raw[:200]!r}")
                    if not (data.get("choices") or [{}])[0].get("message", {}).get("content"):
                        raise RuntimeError(f"{self.provider} empty completion: {json.dumps(data)[:300]}")
                u = data.get("usage", {}) or {}
                self.usage["input_tokens"] += u.get("prompt_tokens", 0)
                self.usage["output_tokens"] += u.get("completion_tokens", 0)
                self.usage["calls"] += 1
                return data["choices"][0]["message"]["content"] or ""
            except urllib.error.HTTPError as e:
                err = e.read()[:400]
                if e.code in (429, 500, 502, 503) and attempt < 3:
                    time.sleep(min(60, int(e.headers.get("Retry-After", "0") or 0) or 10 * (attempt + 1)))
                    continue
                quota = e.code == 429
                if ((e.code in (400, 404) and b"model" in err.lower()) or quota) and self.fallbacks:
                    nxt = self.fallbacks.pop(0)  # model retired/renamed -> try next free model, record it
                    self.usage.setdefault("model_fallbacks", []).append(f"{model} -> {nxt}")
                    self.models = {"classify": nxt, "digest": nxt}
                    self._active = nxt
                    self.label = f"{self.provider}:{nxt}"
                    return self.complete(nxt, system, user, max_tokens)
                self.usage["errors"] += 1
                raise RuntimeError(f"{self.provider} HTTP {e.code}: {err!r}")
        self.usage["errors"] += 1
        raise RuntimeError(f"{self.provider} retries exhausted")


def make_client(cfg):
    """Pick the LLM by LLM_PROVIDER (gemini | anthropic | github). Default: first provider with a key, Gemini first."""
    want = os.environ.get("LLM_PROVIDER", "").strip().lower()
    order = [want] if want else ["gemini", "anthropic"]  # GitHub Models inference API was retired (verified 2026-10-16)
    for p in order:
        c = AnthropicClient() if p == "anthropic" else OpenAICompatClient(p) if p in OpenAICompatClient.PROVIDERS else None
        if c and c.available:
            if p != "anthropic":
                cfg["models"] = dict(c.models)
            c.label = f"{p}:{cfg['models']['classify']}"
            return c
    return None


def _parse_json_array(text):
    text = text.strip()
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0) if m else text)


def _clean(r):
    lane = r.get("lane") if r.get("lane") in LANES else "irrelevant"
    et = r.get("event_type") if r.get("event_type") in EVENT_TYPES else "other"
    d = r.get("direction") if r.get("direction") in ("tailwind", "headwind", "neutral") else "neutral"
    try:
        mat = max(1, min(5, int(r.get("materiality", 1))))
    except Exception:
        mat = 1
    try:
        fit = max(0.0, min(1.0, float(r.get("last_mile_fit", 0))))
    except Exception:
        fit = 0.0
    comps = [c for c in (r.get("companies") or []) if isinstance(c, str)][:8]
    return {"lane": lane, "event_type": et, "direction": d, "materiality": mat, "last_mile_fit": fit,
            "companies": comps, "summary": str(r.get("summary", ""))[:300], "evidence_quote": str(r.get("evidence_quote", ""))[:400],
            "implication": str(r.get("implication", ""))[:300], "action": r.get("action") if r.get("action") in ("respond", "watch", "context") else "watch"}


def classify_llm(items, client, model, batch_size=30):
    results = {}
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        user = "Classify these items:\n" + json.dumps(_items_payload(batch), ensure_ascii=False)
        try:
            arr = _parse_json_array(client.complete(model, SYSTEM_PROMPT, user, max_tokens=8000))
        except Exception as e:
            for it in batch:
                results[it["_cid"]] = {"error": str(e)[:200]}
            continue
        for r in arr:
            if isinstance(r, dict) and r.get("id") in {it["_cid"] for it in batch}:
                results[r["id"]] = _clean(r)
    return results


# ---------------- Rules fallback (no API key) ----------------
_POLICY = ["tariff", "legislation", "bill ", "senate", "congress", "regulation", "rulemaking", "fmcsa", "governor",
           "law ", "lawmakers", "court", "supreme court", "executive order", "federal register", "proposed rule"]
_RESEARCH = ["report", "survey", "outlook", "study", "index", "forecast", "analysis finds", "data shows"]
_EVENTS = [("funding", ["raises", "funding", "series a", "series b", "series c", "series d", "investment"]),
           ("m_and_a", ["acquire", "acquisition", "merger", "acquired"]),
           ("product_launch", ["launch", "introduces", "unveils", "rolls out", "new product", "debuts"]),
           ("market_entry", ["expands", "enters", "expansion", "now available in"]),
           ("market_exit", ["exits", "withdraw", "pulls out", "non-renew", "shuts down", "winds down"]),
           ("pricing_rate", ["rate increase", "rates rise", "rate filing", "premium", "pricing"]),
           ("partnership_distribution", ["partner", "partnership", "teams up", "collaborat"]),
           ("leadership", ["appoints", "names ", "hires", "ceo", "chief"]),
           ("litigation_claims", ["verdict", "lawsuit", "settlement", "claims"])]
_HEAD = ["verdict", "rising", "increase", "higher", "losses", "tariff", "shortage", "lawsuit", "inflation", "exits", "decline in volume"]
_TAIL = ["reform", "growth", "grows", "record volume", "expands", "decline in claims", "lower costs", "demand"]


_HOT = {"product_launch", "market_entry", "market_exit", "pricing_rate", "m_and_a", "partnership_distribution"}


def _rule_implication(lane, et, comps):
    """Template text used only when no LLM is available; labelled as rules-generated in the UI."""
    who = ", ".join(comps) if comps else "A player"
    if lane == "competitor_move":
        return {"product_launch": f"{who} adds supply in a segment Nirvana may target; compare terms and broker reach.",
                "market_exit": f"{who} pulling back may free up DSP/courier accounts; brief target brokers.",
                "pricing_rate": f"{who} pricing move shifts the benchmark Nirvana's quotes will be compared against.",
                "partnership_distribution": f"{who} gains a distribution route; check overlap with Nirvana's broker targets.",
                "funding": f"{who} has new capital to compete on price or distribution."}.get(et, f"Track {who}; possible effect on Nirvana's last-mile position.")
    return {"market_driver": "Affects loss costs or demand in last-mile commercial auto; feed into pricing assumptions.",
            "policy_macro": "Regulatory or macro change; check impact on limits, loss costs or target states.",
            "research": "Third-party data point; check against Nirvana's sizing and loss assumptions."}.get(lane, "Context only.")


def classify_rules(items, competitors, topic_keywords):
    out = {}
    for it in items:
        text = f"{it['title']} {it.get('snippet') or ''}".lower()
        comps = [c["name"] for c in competitors if any(re.search(r"\b" + re.escape(a.lower()) + r"\b", text) for a in c["aliases"])]
        topical = any(k in text for k in topic_keywords)
        insurance = any(k in text for k in ["insur", "coverage", "underwrit", "premium", "mga", "carrier"])
        if comps and (insurance or topical):
            lane = "competitor_move"
        elif not topical:
            lane = "irrelevant"
        elif any(k in text for k in _POLICY):
            lane = "policy_macro"
        elif any(k in text for k in _RESEARCH):
            lane = "research"
        else:
            lane = "market_driver"
        et = next((name for name, kws in _EVENTS if any(k in text for k in kws)), "other")
        h, t = sum(k in text for k in _HEAD), sum(k in text for k in _TAIL)
        direction = "headwind" if h > t else "tailwind" if t > h else "neutral"
        fit = 0.9 if ("last-mile" in text or "last mile" in text) else 0.6 if any(k in text for k in ["delivery", "courier", "parcel", "dsp"]) else 0.3
        mat = 3 + (1 if et in ("product_launch", "market_entry", "market_exit", "m_and_a", "pricing_rate") else 0) + (1 if fit >= 0.9 else 0) if lane != "irrelevant" else 1
        out[it["_cid"]] = {"lane": lane, "event_type": et, "direction": direction, "materiality": min(mat, 5),
                           "last_mile_fit": fit, "companies": comps, "summary": it["title"][:300], "evidence_quote": it["title"],
                           "implication": _rule_implication(lane, et, comps), "action": "respond" if (comps and et in _HOT) else "watch" if lane != "irrelevant" else "context"}
    return out


DIGEST_PROMPT = """You write the daily competitor-intelligence brief for Nirvana Insurance's CEO and Head of Finance (topic: US last-mile delivery commercial auto insurance).
Use ONLY the events provided. 3-5 bullets, each <= 35 words, most important first, each ending with its reference like [3].
Say what changed and why it matters to a telematics-based commercial auto MGA entering last-mile. No speculation beyond the events. Plain text bullets starting with "- "."""


def write_digest(events, client, model):
    if not events:
        return None
    payload = [{"ref": i + 1, "title": e["title"], "lane": e["lane"], "event_type": e["event_type"], "direction": e["direction"],
                "summary": e["summary"], "implication": e.get("implication"), "confidence": e.get("confidence"), "publisher": e["sources"][0]["publisher"], "score": e["score"]} for i, e in enumerate(events[:15])]
    try:
        return client.complete(model, DIGEST_PROMPT, json.dumps(payload, ensure_ascii=False), max_tokens=800).strip()
    except Exception:
        return None
