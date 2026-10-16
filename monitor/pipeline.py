"""Orchestrates one monitoring run: collect -> dedup/delta -> classify -> verify -> rank -> store -> notify."""
import difflib
import statistics
import time
from datetime import timedelta

from . import collectors as C
from .classify import classify_llm, classify_rules, write_digest
from .scoring import confidence, evidence_found, score_event, source_tier, verification_status
from .store import Store
from .textutil import domain_of, fingerprint, iso, norm_title, parse_date, url_hash

ENTITY_IGNORE = {"nirvana", "nirvana insurance", "amazon", "fedex", "ups", "usps", "doordash", "uber", "uber eats", "instacart",
                 "walmart", "target", "dhl", "grubhub", "gopuff", "shipt", "lyft", "fmcsa", "naic", "sec", "u.s. department of transportation"}


def _collect(cfg, fetch, now, data_dir, log, only=None):
    raw, health = [], []

    def add(res):
        items, h = res
        raw.extend(items)
        health.append(h)
        log(f"  [{h['status']:>14}] {h['name'][:70]:<70} {h['items']:>3} items  {h['ms']}ms")

    want = lambda k: only is None or k in only
    if want("feeds"):
        for f in cfg.get("feeds", []):
            add(C.collect_feed(f, fetch))
    queries = [(c["query"], "competitor_move") for c in cfg.get("competitors", []) if c.get("query")]
    queries += [(q["q"], q["lane"]) for q in cfg.get("query_packs", [])]
    se = cfg.get("search_engines", {})
    if want("bing") and se.get("bing_news", {}).get("enabled"):
        for q, lane in queries:
            add(C.collect_bing(q, lane, se["bing_news"], fetch))
            time.sleep(se["bing_news"].get("sleep_seconds", 1))
    if want("gdelt") and se.get("gdelt", {}).get("enabled"):
        for q, lane in queries:
            add(C.collect_gdelt(q, lane, se["gdelt"], fetch))
    if want("fedreg"):
        for t in cfg.get("federal_register_terms", []):
            add(C.collect_federal_register(t, now, cfg["lookback_days"], fetch))
    if want("sec"):
        for q in cfg.get("sec_queries", []):
            add(C.collect_sec(q, cfg.get("sec_forms", "8-K"), now, cfg["lookback_days"], fetch))
    if want("pages"):
        for p in cfg.get("page_watch", []):
            add(C.collect_page_watch(p, f"{data_dir}/pages", fetch, now))
    return raw, health


def _watchlist_matches(text, competitors):
    t = (text or "").lower()
    import re
    return sorted({c["name"] for c in competitors if any(re.search(r"\b" + re.escape(a.lower()) + r"\b", t) for a in c["aliases"])})


def _src(it, tier):
    return {"url": it["url"], "publisher": it.get("publisher") or domain_of(it["url"]), "publisher_key": it["publisher_key"],
            "published": it.get("published"), "tier": tier, "source_id": it["source_id"], "query": it.get("query")}


def run_pipeline(cfg, data_dir, fetch, client, now, notifier=None, only=None, log=print):
    t0 = time.time()
    store = Store(data_dir)
    run_id = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    prev = store.previous_run
    baseline = prev is None
    comps = cfg.get("competitors", [])
    comp_domains = [d for c in comps for d in c.get("domains", [])]
    prio = {c["name"]: c.get("priority", 0.5) for c in comps}
    ignore = ENTITY_IGNORE | {a.lower() for c in comps for a in c["aliases"]} | {x.lower() for x in cfg.get("entity_ignore", [])}
    counts = {k: 0 for k in ["raw", "unique", "known_skipped", "attached_existing", "prefiltered_out", "too_old", "deferred",
                             "classified", "irrelevant", "quarantined", "new_events", "updated_events", "late_discoveries", "classifier_errors"]}

    log(f"Run {run_id} (baseline={baseline})")
    raw, health = _collect(cfg, fetch, now, data_dir, log, only)
    counts["raw"] = len(raw)

    # ---- normalize + in-run dedup by canonical URL
    items, inrun = [], set()
    for it in raw:
        if not it.get("url") or not it.get("title"):
            continue
        uh = url_hash(it["url"])
        if uh in inrun:
            continue
        inrun.add(uh)
        it["_uh"], it["_fp"] = uh, fingerprint(it["title"], it.get("publisher"))
        it["publisher_key"] = (it.get("publisher") or domain_of(it["url"])).lower().strip()
        items.append(it)
    counts["unique"] = len(items)

    # ---- delta against history
    fp_index = {fp: eid for eid, e in store.events.items() for fp in e.get("fingerprints", [])}
    window_start = now - timedelta(days=cfg["cluster_window_days"])
    recent = [(eid, norm_title(e["title"])) for eid, e in store.events.items() if (parse_date(e["last_seen"]) or now) >= window_start]
    thr = cfg.get("fuzzy_merge_threshold", 0.86)

    def fuzzy(nt, pool):
        best, best_r = None, 0.0
        for eid, t in pool:
            if abs(len(t) - len(nt)) > 40:
                continue
            r = difflib.SequenceMatcher(None, nt, t).ratio()
            if r > best_r:
                best, best_r = eid, r
        return best if best_r >= thr else None

    topic = [k.lower() for k in cfg.get("topic_keywords", [])]
    aliases = [a.lower() for c in comps for a in c["aliases"]]
    attach, candidates = [], []
    for it in items:
        if it["_uh"] in store.seen or ("fp:" + it["_fp"]) in store.seen:
            counts["known_skipped"] += 1
            continue
        eid = fp_index.get(it["_fp"]) or fuzzy(norm_title(it["title"], it.get("publisher")), recent)
        if eid:
            attach.append((it, eid))
            continue
        pub = parse_date(it.get("published"))
        if pub and (now - pub).days > cfg["late_discovery_days"]:
            counts["too_old"] += 1
            store.seen[it["_uh"]] = {"first_seen": iso(now), "outcome": "too_old"}
            continue
        if it.get("broad"):
            text = f"{it['title']} {it.get('snippet', '')}".lower()
            if not any(k in text for k in topic) and not any(a in text for a in aliases):
                counts["prefiltered_out"] += 1
                store.seen[it["_uh"]] = {"first_seen": iso(now), "outcome": "prefiltered_out"}
                continue
        candidates.append(it)

    candidates.sort(key=lambda x: x.get("published") or "", reverse=True)
    cap = cfg.get("max_classify_per_run", 160)
    counts["deferred"] = max(0, len(candidates) - cap)
    candidates = candidates[:cap]
    for i, it in enumerate(candidates):
        it["_cid"] = f"i{i}"

    # ---- classify
    mode = "llm" if (client and client.available) else "rules"
    llm_errors = []
    if mode == "llm":
        results = classify_llm(candidates, client, cfg["models"]["classify"], cfg.get("classify_batch_size", 15))
        errored = [it for it in candidates if "error" in results.get(it["_cid"], {"error": "missing"})]
        counts["classifier_errors"] = len(errored)
        llm_errors = sorted({results[it["_cid"]]["error"] for it in errored if it["_cid"] in results})[:3]
        if llm_errors:
            log(f"LLM errors (falling back to rules for {len(errored)} items): {llm_errors}")
        if errored:
            for k, v in classify_rules(errored, comps, topic).items():
                v["_fallback"] = True
                results[k] = v
    else:
        results = classify_rules(candidates, comps, topic)
    counts["classified"] = len(candidates)

    # ---- verify + build events
    quarantine, new_ids, updated_ids = [], [], set()
    decisions = []  # AI decision log: what the model decided for every item it saw, and what the verifier did with it

    def decide(it, r, outcome, note=""):
        decisions.append({"title": it["title"], "url": it["url"], "publisher": it.get("publisher"), "lane": r.get("lane"),
                          "event_type": r.get("event_type"), "materiality": r.get("materiality"), "outcome": outcome,
                          "classifier": "rules-fallback" if r.get("_fallback") else (getattr(client, "label", mode) if mode == "llm" else mode),
                          "evidence_quote": r.get("evidence_quote"), "note": note})
    new_pool = []
    for it in candidates:
        r = results.get(it["_cid"])
        if not r:
            continue
        mark = {"first_seen": iso(now), "outcome": r["lane"]}
        if r["lane"] == "irrelevant":
            decide(it, r, "dropped: irrelevant", r.get("summary", ""))
            counts["irrelevant"] += 1
            store.seen[it["_uh"]] = mark
            store.seen["fp:" + it["_fp"]] = mark
            continue
        if not evidence_found(r["evidence_quote"], it["title"], it.get("snippet", "")):
            counts["quarantined"] += 1
            quarantine.append({"title": it["title"], "url": it["url"], "claimed_quote": r["evidence_quote"], "lane": r["lane"]})
            decide(it, r, "quarantined: evidence not in source", "Quoted text was not found in the fetched title/snippet")
            store.seen[it["_uh"]] = {"first_seen": iso(now), "outcome": "quarantined"}
            continue
        tier = source_tier(it["url"], it.get("publisher"), it.get("tier_hint"), cfg, comp_domains)
        nt = norm_title(it["title"], it.get("publisher"))
        same = fuzzy(nt, new_pool) if new_pool else None
        if same:
            attach.append((it, same))
            decide(it, r, "merged into existing event", same)
            continue
        eid = "ev_" + it["_fp"]
        pub = parse_date(it.get("published"))
        late = bool(pub and (now - pub).days > cfg["lookback_days"])
        wl = sorted(set(_watchlist_matches(f"{it['title']} {it.get('snippet', '')} {' '.join(r['companies'])}", comps)))
        ev = {"id": eid, "title": it["title"], "url": it["url"], "lane": r["lane"], "event_type": r["event_type"],
              "direction": r["direction"], "materiality": r["materiality"], "last_mile_fit": r["last_mile_fit"],
              "summary": r["summary"], "evidence_quote": r["evidence_quote"], "companies": r["companies"],
              "implication": r.get("implication", ""), "action": r.get("action", "watch"),
              "watchlist_companies": wl, "published": it.get("published"), "date_known": bool(it.get("published")),
              "first_seen": iso(now), "first_run": run_id, "last_seen": iso(now), "last_updated_run": run_id,
              "update_note": None, "late_discovery": late, "classifier": "rules-fallback" if r.get("_fallback") else (getattr(client, "label", mode) if mode == "llm" else mode),
              "lane_hint": it.get("lane_hint"), "fingerprints": [it["_fp"]], "sources": [_src(it, tier)], "best_tier": tier}
        store.events[eid] = ev
        decide(it, r, "kept: late discovery" if late else "kept: new event", r.get("implication", ""))
        new_pool.append((eid, nt))
        new_ids.append(eid)
        store.seen[it["_uh"]] = {"first_seen": iso(now), "outcome": "event", "event_id": eid}
        if late:
            counts["late_discoveries"] += 1
        if mode == "llm":
            for name in r["companies"]:
                key = name.strip()
                if not key or key.lower() in ignore:
                    continue
                ent = store.entities.setdefault(key, {"name": key, "first_seen": iso(now), "mentions": 0, "event_ids": [], "status": "proposed"})
                ent["mentions"] += 1
                ent["last_seen"] = iso(now)
                if eid not in ent["event_ids"]:
                    ent["event_ids"] = (ent["event_ids"] + [eid])[-10:]

    for it, eid in attach:
        ev = store.events.get(eid)
        if not ev:
            continue
        store.seen[it["_uh"]] = {"first_seen": iso(now), "outcome": "attached", "event_id": eid}
        ev["last_seen"] = iso(now)
        if it["_fp"] not in ev["fingerprints"]:
            ev["fingerprints"].append(it["_fp"])
        if it["publisher_key"] in {s["publisher_key"] for s in ev["sources"]}:
            continue  # same publisher, different URL (e.g. syndication) -> not news
        tier = source_tier(it["url"], it.get("publisher"), it.get("tier_hint"), cfg, comp_domains)
        ev["sources"].append(_src(it, tier))
        ev["best_tier"] = min(ev["best_tier"], tier)
        counts["attached_existing"] += 1
        if ev["first_run"] != run_id:
            ev["last_updated_run"] = run_id
            ev["update_note"] = f"New corroborating source: {it.get('publisher') or domain_of(it['url'])}"
            updated_ids.add(eid)

    # ---- rescore everything, prune > 180 days
    for eid in list(store.events):
        ev = store.events[eid]
        if (now - (parse_date(ev["last_seen"]) or now)).days > 180:
            del store.events[eid]
            continue
        score_event(ev, cfg, now, prio)
        ev["verification"] = verification_status(ev)
        ev["confidence"], ev["confidence_reason"] = confidence(ev)

    fresh_new = sorted([store.events[e] for e in new_ids if not store.events[e]["late_discovery"]], key=lambda e: -e["score"])
    updated = sorted([store.events[e] for e in updated_ids], key=lambda e: -e["score"])
    counts["new_events"], counts["updated_events"] = len(fresh_new), len(updated)

    digest = None
    if not baseline and (fresh_new or updated):
        if mode == "llm":
            digest = write_digest(fresh_new + updated, client, cfg["models"]["digest"])
        if not digest:
            digest = "\n".join(f"- {e['title']} ({e['sources'][0]['publisher']}) [{i + 1}]" for i, e in enumerate((fresh_new + updated)[:5]))

    # ---- run-level evals
    ok = sum(h["status"] == "ok" for h in health)
    ages = [e["age_days"] for e in fresh_new if e.get("age_days") is not None]
    verified = sum(1 for e in new_ids)
    evals = {
        "source_success_rate": round(ok / len(health), 3) if health else None,
        "verification_pass_rate": round(verified / (verified + counts["quarantined"]), 3) if (verified + counts["quarantined"]) else None,
        "date_coverage": round(sum(e["date_known"] for e in fresh_new) / len(fresh_new), 3) if fresh_new else None,
        "median_age_days_new": statistics.median(ages) if ages else None,
        "dedup_ratio": round(1 - len(candidates) / counts["unique"], 3) if counts["unique"] else None,
        "relevance_rate": round(len(new_ids) / counts["classified"], 3) if counts["classified"] else None,
    }
    import os
    gh_repo, gh_run = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    run_url = f"https://github.com/{gh_repo}/actions/runs/{gh_run}" if gh_repo and gh_run else None
    trigger = os.environ.get("GITHUB_EVENT_NAME", "local")
    summary = {"run_id": run_id, "run_url": run_url, "trigger": trigger, "repo": gh_repo, "date": now.strftime("%Y-%m-%d"), "started": iso(now), "duration_s": round(time.time() - t0, 1),
               "baseline": baseline, "previous_run": prev["run_id"] if prev else None, "previous_started": prev["started"] if prev else None,
               "classifier": mode, "model": getattr(client, "label", None) if mode == "llm" else None, "counts": counts, "evals": evals, "health": health,
               "llm_usage": dict(client.usage) if client and client.available else None, "llm_errors": llm_errors}
    pull = {**summary, "new": fresh_new, "updated": updated, "late_discoveries": [store.events[e] for e in new_ids if store.events[e]["late_discovery"]],
            "quarantine": quarantine, "decisions": decisions, "digest": digest}
    latest = {"run_id": run_id, "run_url": run_url, "trigger": trigger, "repo": gh_repo, "started": iso(now), "baseline": baseline, "previous_started": summary["previous_started"],
              "classifier": mode, "counts": counts, "evals": evals, "digest": digest,
              "whats_new": {"new": fresh_new, "updated": updated}, "total_events": len(store.events),
              "decisions": decisions[:300], "model": summary["model"], "llm_usage": summary["llm_usage"]}
    store.save(summary, pull, latest)
    log(f"Done: {counts}")
    log(f"Evals: {evals}")
    if notifier:
        notifier(latest)
    return summary, latest
