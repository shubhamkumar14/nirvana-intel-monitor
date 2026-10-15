"""Delivery: Slack incoming webhook, SMTP email, generic JSON webhook (Teams/Discord/Zapier/n8n). All optional, env-driven."""
import json
import os
import smtplib
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

LANE_LABEL = {"competitor_move": "Competitor move", "market_driver": "Market driver", "research": "Research", "policy_macro": "Policy / macro"}


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def _lines(latest, limit=8):
    evs = latest["whats_new"]["new"] + latest["whats_new"]["updated"]
    return evs[:limit], len(evs)


def build_text(latest, dashboard):
    evs, total = _lines(latest)
    if latest["baseline"]:
        return f"Baseline pull complete: {latest['total_events']} events indexed. Daily deltas start with the next pull.\n{dashboard}"
    if not total:
        return f"No new developments since the previous pull ({latest['previous_started']}). Pipeline healthy.\n{dashboard}"
    head = f"{latest['counts']['new_events']} new, {latest['counts']['updated_events']} updated since previous pull"
    body = latest.get("digest") or ""
    links = "\n".join(f"[{i + 1}] {e['title']} — {e['sources'][0]['publisher']} {e['url']}" for i, e in enumerate(evs))
    return f"{head}\n\n{body}\n\n{links}\n\nDashboard: {dashboard}"


def slack(latest, webhook, dashboard):
    evs, total = _lines(latest)
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Last-mile commercial auto: competitor intel"}}]
    if latest["baseline"] or not total:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": build_text(latest, dashboard)}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{latest['counts']['new_events']} new · {latest['counts']['updated_events']} updated* since previous pull\n{latest.get('digest') or ''}"}})
        for i, e in enumerate(evs):
            tag = "UPDATED · " if e["first_run"] != latest["run_id"] else ""
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
                           f"*[{i + 1}] <{e['url']}|{e['title'][:140]}>*\n{tag}{LANE_LABEL.get(e['lane'], e['lane'])} · {e['event_type'].replace('_', ' ')} · score {e['score']} · {e['verification']} · {e['sources'][0]['publisher']}"}})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"<{dashboard}|Open dashboard> · classifier: {latest['classifier']}"}]})
    return _post(webhook, {"text": "Competitor intel update", "blocks": blocks[:48]})


def email(latest, dashboard):
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("EMAIL_TO")
    if not host or not to:
        return None
    msg = MIMEMultipart()
    n = latest["counts"]
    msg["Subject"] = f"[Intel] {n['new_events']} new / {n['updated_events']} updated — last-mile commercial auto" if not latest["baseline"] else "[Intel] Baseline pull complete"
    msg["From"] = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER", "")
    msg["To"] = to
    msg.attach(MIMEText(build_text(latest, dashboard), "plain", "utf-8"))
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.sendmail(msg["From"], [x.strip() for x in to.split(",")], msg.as_string())
    return 250


def make_notifier(log=print):
    dashboard = os.environ.get("DASHBOARD_URL", "")
    heartbeat = os.environ.get("NOTIFY_HEARTBEAT", "true").lower() == "true"

    def notify(latest):
        has_news = latest["baseline"] or latest["counts"]["new_events"] or latest["counts"]["updated_events"]
        if not has_news and not heartbeat:
            log("notify: nothing new, heartbeat off")
            return
        for name, fn in [("slack", lambda: os.environ.get("SLACK_WEBHOOK_URL") and slack(latest, os.environ["SLACK_WEBHOOK_URL"], dashboard)),
                         ("email", lambda: email(latest, dashboard)),
                         ("webhook", lambda: os.environ.get("WEBHOOK_URL") and _post(os.environ["WEBHOOK_URL"], {"text": build_text(latest, dashboard), "latest": {k: latest[k] for k in ("run_id", "counts", "digest", "baseline")}}))]:
            try:
                r = fn()
                log(f"notify {name}: {'sent ' + str(r) if r else 'not configured'}")
            except Exception as e:
                log(f"notify {name}: FAILED {type(e).__name__}: {e}")
    return notify
