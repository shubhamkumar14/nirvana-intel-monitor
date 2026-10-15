"""Classifier eval on the golden set. Usage: python -m evals.run_eval [--mode rules|llm|both] [--out docs/data/evals.json] [--gate 0.8]

Reports relevance precision/recall (relevant = any lane except irrelevant) and lane accuracy, plus every miss,
so prompt changes can be judged before they ship.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from monitor.classify import AnthropicClient, classify_llm, classify_rules  # noqa: E402


def score(items, preds):
    tp = fp = fn = correct = 0
    misses = []
    for it in items:
        p = preds.get(it["_cid"], {}).get("lane", "error")
        gold_rel, pred_rel = it["lane"] != "irrelevant", p not in ("irrelevant", "error")
        tp += gold_rel and pred_rel
        fp += (not gold_rel) and pred_rel
        fn += gold_rel and not pred_rel
        correct += p == it["lane"]
        if p != it["lane"]:
            misses.append({"title": it["title"], "gold": it["lane"], "pred": p})
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"n": len(items), "relevance_precision": round(prec, 3), "relevance_recall": round(rec, 3),
            "lane_accuracy": round(correct / len(items), 3), "misses": misses}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="evals/golden.json")
    ap.add_argument("--config", default="config/monitor.json")
    ap.add_argument("--mode", default="both")
    ap.add_argument("--out", default=None)
    ap.add_argument("--gate", type=float, default=None, help="fail if relevance precision of the active mode < gate")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    gold = json.load(open(a.golden))
    items = [{**it, "_cid": f"g{i}", "publisher": "golden", "published": None, "query": None} for i, it in enumerate(gold["items"])]
    report = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "golden_set": gold.get("_note", ""), "results": {}}
    if a.mode in ("rules", "both"):
        report["results"]["rules"] = score(items, classify_rules(items, cfg["competitors"], [k.lower() for k in cfg["topic_keywords"]]))
    client = AnthropicClient()
    if a.mode in ("llm", "both") and client.available:
        report["results"]["llm"] = score(items, classify_llm(items, client, cfg["models"]["classify"]))
        report["results"]["llm"]["model"] = cfg["models"]["classify"]
    elif a.mode in ("llm", "both"):
        report["results"]["llm"] = {"skipped": "ANTHROPIC_API_KEY not set"}
    for k, v in report["results"].items():
        print(k, {x: y for x, y in v.items() if x != "misses"})
        for m in v.get("misses", []):
            print("   miss:", m)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(report, open(a.out, "w"), indent=1)
    if a.gate is not None:
        active = report["results"].get("llm") if "relevance_precision" in report["results"].get("llm", {}) else report["results"].get("rules")
        if active and active["relevance_precision"] < a.gate:
            print(f"EVAL GATE FAILED: precision {active['relevance_precision']} < {a.gate}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
