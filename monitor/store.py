"""Git-as-database store. Every daily pull is a JSON snapshot committed to the repo (full history via git)."""
import json
import os


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class Store:
    def __init__(self, data_dir):
        self.dir = data_dir
        self.events = _load(self.p("events.json"), {})          # event_id -> event
        self.runs = _load(self.p("runs.json"), [])              # run summaries, oldest first
        self.seen = _load(self.p("seen.json"), {})              # url_hash -> {"first_seen", "outcome", "event_id"}
        self.entities = _load(self.p("entities.json"), {})      # discovered org name -> record
        self.pull_index = _load(self.p("pulls/index.json"), [])

    def p(self, *parts):
        return os.path.join(self.dir, *parts)

    @property
    def previous_run(self):
        return self.runs[-1] if self.runs else None

    def save(self, run_summary, pull, latest):
        self.runs.append(run_summary)
        self.runs = self.runs[-500:]
        if len(self.seen) > 50000:  # cap; keep newest
            self.seen = dict(sorted(self.seen.items(), key=lambda kv: kv[1]["first_seen"])[-40000:])
        _save(self.p("events.json"), self.events)
        _save(self.p("runs.json"), self.runs)
        _save(self.p("seen.json"), self.seen)
        _save(self.p("entities.json"), self.entities)
        _save(self.p("pulls", run_summary["run_id"] + ".json"), pull)
        self.pull_index.append({"run_id": run_summary["run_id"], "date": run_summary["date"], "started": run_summary["started"],
                                "new": run_summary["counts"]["new_events"], "updated": run_summary["counts"]["updated_events"],
                                "baseline": run_summary["baseline"], "trigger": run_summary.get("trigger"), "run_url": run_summary.get("run_url"),
                                "sources_ok": run_summary["evals"]["source_success_rate"], "scanned": run_summary["counts"]["unique"], "file": f"pulls/{run_summary['run_id']}.json"})
        _save(self.p("pulls/index.json"), self.pull_index)
        _save(self.p("latest.json"), latest)
