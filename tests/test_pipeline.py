"""Offline tests on SYNTHETIC fixtures (tests/fixtures). They prove pipeline logic, not live source coverage."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from monitor import collectors as C  # noqa: E402
from monitor.pipeline import run_pipeline  # noqa: E402
from monitor.scoring import evidence_found  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
D1 = datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc)
D2 = datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc)


def fixture_fetch(url, headers=None, respect_robots=True):
    name = url.replace("fixture://", "")
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def cfg(feeds):
    base = json.load(open(os.path.join(ROOT, "config", "monitor.json")))
    base["feeds"] = [{"id": f.split(".")[0].split("_")[0], "name": f.split("_")[0].upper(), "url": "fixture://" + f, "tier": 2} for f in feeds]
    return base


class FakeLLM:
    """Deterministic stand-in for Claude. `lie=True` returns a fabricated evidence quote."""
    def __init__(self, lie=False):
        self.lie = lie
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "errors": 0}
        self.available = True

    def complete(self, model, system, user, max_tokens=4000):
        self.usage["calls"] += 1
        if user.startswith("[") or "Classify" not in user:
            return "- digest bullet [1]"
        items = json.loads(user.split("\n", 1)[1])
        out = []
        for it in items:
            t = it["title"].lower()
            lane = "competitor_move" if any(k in t for k in ["fairmatic", "cover whale", "inshur"]) else \
                   "market_driver" if "verdict" in t else "research" if "study" in t else "irrelevant"
            quote = "Company confirmed record profits for the quarter" if self.lie else " ".join(it["title"].split()[:6])
            out.append({"id": it["id"], "lane": lane, "event_type": "product_launch" if "launch" in t else "market_exit" if "exit" in t else "trend_data",
                        "direction": "headwind", "materiality": 5 if lane == "competitor_move" else 3, "last_mile_fit": 0.9,
                        "companies": ["Fairmatic", "NewCo Delivery Insure"] if "fairmatic" in t else [], "summary": "s", "evidence_quote": quote,
                        "implication": "Benchmark for Nirvana DSP pricing", "action": "respond"})
        return json.dumps(out)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.log = lambda *a: None

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_day(self, feeds, now, client):
        return run_pipeline(cfg(feeds), self.dir, fixture_fetch, client, now, only={"feeds"}, log=self.log)

    def test_baseline_then_delta_then_idempotent(self):
        s1, l1 = self.run_day(["ij_day1.xml"], D1, FakeLLM())
        self.assertTrue(s1["baseline"])
        self.assertEqual(s1["counts"]["prefiltered_out"], 1)          # arctic ice dropped by keyword gate
        self.assertEqual(l1["total_events"], 2)
        self.assertIsNone(l1["digest"])                                  # baseline: no "what's new"

        s2, l2 = self.run_day(["ij_day2.xml", "wire_day2.xml"], D2, FakeLLM())
        self.assertFalse(s2["baseline"])
        self.assertEqual(s2["counts"]["known_skipped"], 2)               # yesterday's URLs not reprocessed
        new_titles = [e["title"] for e in l2["whats_new"]["new"]]
        self.assertEqual(new_titles, ["Cover Whale exits courier delivery segment in three states"])
        upd = l2["whats_new"]["updated"]
        self.assertEqual(len(upd), 1)                                    # Fairmatic story corroborated by 2nd publisher
        self.assertEqual(upd[0]["verification"], "Corroborated")
        self.assertEqual(s2["counts"]["late_discoveries"], 1)            # Sep 21 item stored but not "new"

        s3, l3 = self.run_day(["ij_day2.xml", "wire_day2.xml"], D2.replace(hour=14), FakeLLM())
        self.assertEqual(s3["counts"]["new_events"], 0)                  # idempotent re-run
        self.assertEqual(s3["counts"]["updated_events"], 0)
        self.assertEqual(s3["counts"]["classified"], 0)                  # zero LLM spend on re-run
        idx = json.load(open(os.path.join(self.dir, "pulls", "index.json")))
        self.assertEqual(len(idx), 3)                                    # history of daily pulls kept

    def test_fabricated_quote_is_quarantined(self):
        s, l = self.run_day(["ij_day1.xml"], D1, FakeLLM(lie=True))
        self.assertEqual(l["total_events"], 0)
        self.assertEqual(s["counts"]["quarantined"], 2)
        self.assertEqual(s["evals"]["verification_pass_rate"], 0.0)

    def test_rules_mode_without_api_key(self):
        s, l = self.run_day(["ij_day1.xml"], D1, None)
        self.assertEqual(s["classifier"], "rules")
        self.assertGreaterEqual(l["total_events"], 1)

    def test_discovered_entities_exclude_watchlist(self):
        self.run_day(["ij_day1.xml"], D1, FakeLLM())
        ents = json.load(open(os.path.join(self.dir, "entities.json")))
        self.assertIn("NewCo Delivery Insure", ents)
        self.assertNotIn("Fairmatic", ents)

    def test_events_carry_implication_confidence_and_decision_log(self):
        s, l = self.run_day(["ij_day1.xml"], D1, FakeLLM())
        evs = json.load(open(os.path.join(self.dir, "events.json"))).values()
        for e in evs:
            self.assertTrue(e["implication"])
            self.assertIn(e["confidence"], ("High", "Medium", "Low"))
            self.assertTrue(e["confidence_reason"])
        outcomes = sorted(d["outcome"] for d in l["decisions"])
        self.assertEqual(outcomes, ["kept: new event", "kept: new event"])
        s2, l2 = self.run_day(["ij_day2.xml", "wire_day2.xml"], D2, FakeLLM())
        self.assertEqual(l2["whats_new"]["updated"][0]["confidence"], "High")  # 2 publishers + trade press + dated

    def test_newly_added_source_is_baselined_not_new(self):
        self.run_day(["ij_day1.xml"], D1, FakeLLM())
        s2, l2 = self.run_day(["ij_day1.xml", "wire_day2.xml"], D2, FakeLLM())   # wire feed added on day 2
        self.assertEqual(l2["whats_new"]["new"], [])
        self.assertEqual(s2["counts"]["new_events"], 0)

    def test_malformed_json_batch_is_split_and_retried(self):
        class Flaky(FakeLLM):
            def complete(self, model, system, user, max_tokens=4000):
                items = json.loads(user.split("\n", 1)[1]) if "Classify" in user else []
                if len(items) > 1:
                    return "[{broken json"
                return super().complete(model, system, user, max_tokens)
        s, l = self.run_day(["ij_day1.xml"], D1, Flaky())
        self.assertEqual(s["counts"]["classifier_errors"], 0)
        self.assertEqual(l["total_events"], 2)

    def test_email_summary_after_run(self):
        from monitor.notify import email_parts
        self.run_day(["ij_day1.xml"], D1, FakeLLM())
        _, l2 = self.run_day(["ij_day2.xml", "wire_day2.xml"], D2, FakeLLM())
        subj, text, html_body = email_parts(l2, "https://x.test/")
        self.assertIn("1 new, 1 updated", subj)
        self.assertIn("For Nirvana:", text)
        self.assertIn("Cover Whale exits", html_body)
        self.assertIn("UPDATED", html_body)
        _, l3 = self.run_day(["ij_day2.xml", "wire_day2.xml"], D2.replace(hour=15), FakeLLM())
        self.assertIn("No new developments", email_parts(l3, "https://x.test/")[0])

    def test_rules_mode_has_templated_implication(self):
        s, l = self.run_day(["ij_day1.xml"], D1, None)
        e = next(iter(json.load(open(os.path.join(self.dir, "events.json"))).values()))
        self.assertTrue(e["implication"])
        self.assertIn("rules classifier", e["confidence_reason"])

    def test_ranking_prefers_competitor_move(self):
        self.run_day(["ij_day1.xml"], D1, FakeLLM())
        evs = sorted(json.load(open(os.path.join(self.dir, "events.json"))).values(), key=lambda e: -e["score"])
        self.assertIn("Fairmatic", evs[0]["title"])


class UnitTests(unittest.TestCase):
    def test_atom_and_html_unescape(self):
        recs = C.parse_feed(fixture_fetch("fixture://atom.xml"))
        self.assertEqual(recs[0]["title"], "Atom entry about delivery insurance")
        self.assertEqual(recs[0]["published"], "2026-10-14T08:00:00Z")

    def test_evidence_matching(self):
        self.assertTrue(evidence_found("Fairmatic launches telematics-based policy", "Fairmatic launches telematics‑based policy!", ""))
        self.assertFalse(evidence_found("raised $50 million", "Fairmatic launches policy", "no funding mentioned"))
        self.assertFalse(evidence_found("ok", "ok ok", ""))  # too short to count as evidence

    def test_gdelt_and_fedreg_parsers(self):
        g = {"robots": False, "sleep_seconds": 0}
        items, h = C.collect_gdelt("q", "discovery", g, lambda u, **k: fixture_fetch("fixture://gdelt.json"))
        self.assertEqual(h["status"], "ok")
        self.assertEqual(items[0]["published"], "2026-10-14T12:00:00Z")
        items, h = C.collect_federal_register("t", D2, 10, lambda u, **k: fixture_fetch("fixture://fedreg.json"))
        self.assertEqual(items[0]["tier_hint"], 1)

    def test_failing_source_is_recorded_not_raised(self):
        def boom(u, **k):
            raise C.FetchError("HTTP 503")
        items, h = C.collect_feed({"id": "x", "name": "X", "url": "https://x.test/feed"}, boom)
        self.assertEqual((items, h["status"]), ([], "error"))

    def test_page_watch_baseline_then_change(self):
        d = tempfile.mkdtemp()
        page = {"id": "p1", "name": "Pricing page", "url": "https://x.test/pricing"}
        html1 = "<html><body><h1>Plans</h1><p>Starter $99</p></body></html>"
        html2 = "<html><body><h1>Plans</h1><p>Starter $89</p><p>New: Last-mile fleet plan</p></body></html>"
        i1, _ = C.collect_page_watch(page, d, lambda u, **k: html1, D1)
        i2, _ = C.collect_page_watch(page, d, lambda u, **k: html2, D2)
        self.assertEqual(i1, [])
        self.assertIn("Last-mile fleet plan", i2[0]["snippet"])
        shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
