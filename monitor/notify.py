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


def _esc(x):
    import html
    return html.escape(str(x or ""))


def email_parts(latest, dashboard):
    """Return (subject, plain_text, html) for the per-run summary email. Pure function: tested without SMTP."""
    n, ev = latest["counts"], latest.get("evals", {})
    items = latest["whats_new"]["new"] + latest["whats_new"]["updated"]
    upd_ids = {e["id"] for e in latest["whats_new"]["updated"]}
    when = (latest.get("started") or "")[:16].replace("T", " ") + " UTC"
    ok = ev.get("source_success_rate")
    health = (f"{n['unique']} items scanned · {n['known_skipped']} already seen · "
              f"sources OK {round((ok or 0) * 100)}% · {n['quarantined']} AI claims quarantined · classifier {latest.get('model') or latest.get('classifier')}")
    run_link = latest.get("run_url") or ""
    if latest["baseline"]:
        subject, headline = "[Last-Mile Intel] Baseline pull complete", f"Baseline pull: {latest['total_events']} events indexed. Change detection starts with the next run."
    elif not items:
        subject, headline = "[Last-Mile Intel] No new developments", f"Nothing new or updated since the previous pull ({(latest.get('previous_started') or '')[:16].replace('T', ' ')} UTC)."
    else:
        respond = sum(1 for e in items if e.get("action") == "respond")
        subject = f"[Last-Mile Intel] {n['new_events']} new, {n['updated_events']} updated" + (f", {respond} to respond to" if respond else "")
        headline = f"{n['new_events']} new and {n['updated_events']} updated since the previous pull."

    # ---- plain text
    lines = [headline, "", f"Run: {when} · trigger {latest.get('trigger', '')}", health, ""]
    if latest.get("digest") and items:
        lines += ["SUMMARY", latest["digest"], ""]
    for i, e in enumerate(items[:12]):
        lines += [f"[{i + 1}] {'UPDATED' if e['id'] in upd_ids else 'NEW'} · {(e.get('action') or '').upper()} · {e.get('confidence', '')} confidence · {e['lane'].replace('_', ' ')}",
                  f"    {e['title']}",
                  f"    For Nirvana: {e.get('implication') or '-'}",
                  f"    Source: {e['sources'][0]['publisher']}, published {(e.get('published') or '?')[:10]} · {e['url']}", ""]
    lines += [f"Dashboard: {dashboard}", f"Run log: {run_link}" if run_link else "",
              "Automated message from the Last-Mile Intel Monitor (internal case-study tool, not an official Nirvana product)."]
    text = "\n".join(l for l in lines if l is not None)

    # ---- HTML (inline styles, email-client safe; Nirvana palette)
    chip = lambda t, bg, fg: f'<span style="display:inline-block;padding:2px 9px;border-radius:999px;background:{bg};color:{fg};font-size:11px;font-weight:600;margin-right:4px">{_esc(t)}</span>'
    act = {"respond": ("Respond", "#FDE3D8", "#B23A12"), "watch": ("Watch", "#FEF0D2", "#8A5A00"), "context": ("Context", "#F5F6F7", "#555B67")}
    conf = {"High": ("#D9F2EF", "#0B7A6F"), "Medium": ("#DEE7F9", "#003366"), "Low": ("#F5F6F7", "#555B67")}
    cards = ""
    for e in items[:12]:
        a = act.get(e.get("action"), act["watch"])
        c = conf.get(e.get("confidence"), conf["Low"])
        cards += f"""<tr><td style="padding:14px 16px;border:1px solid #E6E7E9;border-radius:12px;background:#ffffff">
          {chip('UPDATED' if e['id'] in upd_ids else 'NEW', '#1C2E52', '#ffffff')}{chip(a[0], a[1], a[2])}{chip(e['lane'].replace('_', ' '), '#C5D3F5', '#003366')}{chip((e.get('confidence') or '') + ' confidence', c[0], c[1])}
          <div style="font-size:15px;font-weight:600;color:#1C1F26;margin:8px 0 6px"><a href="{_esc(e['url'])}" style="color:#1C1F26;text-decoration:none">{_esc(e['title'])}</a></div>
          <div style="background:#FEF7EB;border-radius:8px;padding:8px 10px;font-size:13px;color:#363D4D"><b style="color:#8A5A00;font-size:11px;letter-spacing:.06em">FOR NIRVANA</b>&nbsp; {_esc(e.get('implication') or '-')}</div>
          <div style="font-size:12px;color:#767D8A;margin-top:8px">{_esc(e['sources'][0]['publisher'])} · published {_esc((e.get('published') or '?')[:10])} · {_esc(e.get('confidence_reason') or '')}</div>
        </td></tr><tr><td style="height:10px"></td></tr>"""
    digest = ""
    if latest.get("digest") and items:
        digest = '<div style="font-size:14px;color:#363D4D;line-height:1.55;white-space:pre-line;margin:0 0 18px">' + _esc(latest["digest"]) + "</div>"
    html_body = f"""<!doctype html><html><body style="margin:0;background:#F5F6F7;font-family:Manrope,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F6F7"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="620" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%">
<tr><td style="padding:0 0 6px;font-size:11px;letter-spacing:.12em;color:#555B67;font-weight:600">● LAST-MILE INTEL MONITOR</td></tr>
<tr><td style="font-family:'Instrument Serif',Georgia,serif;font-size:28px;color:#1C1F26;padding:0 0 6px">{_esc(headline)}</td></tr>
<tr><td style="font-size:12px;color:#767D8A;padding:0 0 18px">Run {_esc(when)} · {_esc(health)}</td></tr>
<tr><td>{digest}</td></tr>
<tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cards}</table></td></tr>
<tr><td style="padding:10px 0 0"><a href="{_esc(dashboard)}" style="display:inline-block;background:#003366;color:#ffffff;text-decoration:none;font-weight:600;font-size:13px;padding:10px 18px;border-radius:999px">Open dashboard</a>
{f'&nbsp;<a href="{_esc(run_link)}" style="font-size:13px;color:#003366">Run log</a>' if run_link else ''}</td></tr>
<tr><td style="font-size:11px;color:#9B9EA6;padding:18px 0 0">Automated after every run. Internal case-study tool, not an official Nirvana product. Implications are AI analyst judgments; verify against the linked source.</td></tr>
</table></td></tr></table></body></html>"""
    return subject, text, html_body


def email(latest, dashboard):
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("EMAIL_TO")
    if not host or not to:
        return None
    subject, text, html_body = email_parts(latest, dashboard)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER", "")
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587") or 587), timeout=30) as s:
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
