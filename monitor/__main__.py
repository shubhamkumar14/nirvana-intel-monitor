"""CLI: python -m monitor [--data-dir docs/data] [--no-notify] [--only feeds,bing,gdelt,fedreg,sec,pages]"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import http
from .classify import AnthropicClient
from .notify import make_notifier
from .pipeline import run_pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/monitor.json")
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "docs/data"))
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--only", default=None, help="comma list of collectors")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    client = AnthropicClient()
    print(f"classifier: {'Claude ' + cfg['models']['classify'] if client.available else 'RULES (no ANTHROPIC_API_KEY)'}")
    fetch = lambda url, headers=None, respect_robots=True: http.get(url, headers=headers, respect_robots=respect_robots)
    summary, _ = run_pipeline(cfg, a.data_dir, fetch, client, datetime.now(timezone.utc),
                              notifier=None if a.no_notify else make_notifier(), only=set(a.only.split(",")) if a.only else None)
    if summary["evals"]["source_success_rate"] is not None and summary["evals"]["source_success_rate"] < 0.3:
        print("::warning::Most sources failed this run — check health panel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
