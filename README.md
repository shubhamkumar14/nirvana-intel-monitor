# Last-Mile Commercial Auto · Competitor Intel Monitor (MVP)

A scheduled AI agent that watches the US last-mile delivery commercial auto insurance market every day.
It finds what changed since yesterday's pull and publishes a shareable dashboard, plus an optional Slack, email or webhook digest.

Built for the Nirvana Chief of Staff case study, part 2. The monitor runs again on its own every day, with no manual monitoring.

```
GitHub Actions (daily cron + "Run workflow" button)
  └─ collect ── trade-press & wire RSS · Bing News RSS · GDELT news API · Federal Register API · SEC EDGAR FTS · page-diff watch
  └─ dedup / delta ── canonical URL hash → title fingerprint → fuzzy cluster (14-day window) vs history
  └─ classify ── LLM (Gemini free tier by default; Claude optional), JSON, temp 0 ── rules fallback
  └─ verify ── evidence quote must appear verbatim in fetched text, else quarantined
  └─ rank ── deterministic score: materiality · watchlist priority · source tier · recency · last-mile fit
  └─ store ── docs/data/*.json committed to git (every daily pull = its own snapshot; git log = full history)
  └─ deliver ── GitHub Pages dashboard · Slack · email (SMTP) · generic webhook (Teams/Discord/Zapier)
```

## What it monitors

| Lane | What it covers | Sources |
|---|---|---|
| Competitor moves | Launches, entries and exits, pricing and rate moves, filings, funding, partnerships, M&A, leadership | Per-competitor queries, trade-press and wire RSS, SEC EDGAR full-text search, page-diff watch |
| Discovery | New or adjacent companies not on the watchlist. Claude extracts the organizations; a human approves them. | Query packs on Bing News and GDELT |
| Market drivers | Headwinds and tailwinds: verdicts and social inflation, rates, DSP economics, parcel volumes | Query packs and trade press |
| Research | Reports, surveys and outlooks (headline, abstract and link only; no paywalled text reproduced) | Query packs and trade press |
| Policy and macro | Regulation, tort reform, tariffs, contractor-classification law | Federal Register API and query packs |

The watchlist, queries and feeds all live in `config/monitor.json`, so changing them needs no code changes.
The watchlist was approved by Shubham on 2026-10-16, sourced from the approved Project docs.

## Dashboard

- **What's New:** filled **only** when the latest pull found something new or updated compared with the previous pull. Otherwise it says so explicitly. The first (baseline) pull never shows anything as "new".
- **Competitor Moves**, **Market Radar** (headwind/tailwind columns), **Research**, **Policy & Macro:** searchable and filterable, ranked by score.
- **New on the Radar:** discovered companies that are not on the watchlist.
- **Daily Pulls:** every historical pull. Click one to see exactly what it surfaced that day.
- **Health & Evals:** source-by-source fetch status, the run funnel, verification rate, date coverage, golden-set classifier metrics, and run history.

Every card shows:
- a source link and the source tier (T1 primary, T2 trade, T3 general)
- the verbatim evidence quote
- the publish date and age
- the verification status (Confirmed / Corroborated / Reported)
- the score, with its components shown on hover.

## Evals: how output is checked

| Check | When | How |
|---|---|---|
| **Grounding** | Every item, every run | The LLM's `evidence_quote` must be found in the fetched title or snippet. If it isn't, the item is quarantined and never shown. The pass rate is shown on the dashboard. |
| **Recency** | Every item | The publish date comes from feed or API metadata. Items older than 10 days are flagged as *late discovery* and never counted as new. Items older than 30 days are dropped. |
| **Relevance** | Every run, and CI on change | A golden set gives precision, recall and lane accuracy for Claude and for the rules classifier. CI fails if precision is below 0.80. |
| **Corroboration** | Every run | Two or more independent publishers make an event *Corroborated*; a T1 source makes it *Confirmed*. |
| **Dedup / idempotency** | Unit tests | A re-run with the same inputs produces 0 new events and 0 LLM calls. |
| **Operational health** | Every run | Per-source status (ok / error / skipped_robots), item counts and latency. A warning fires if fewer than 30% of sources succeed. |

> ⚠️ `evals/golden.json` is currently a **synthetic v0 set written by the AI**. Its scores are optimistic until we replace it with human-labeled items from live pulls. That replacement is next on the roadmap.

## Setup (≈10 minutes, personal accounts only)

1. **Repo.** Push this folder to a personal GitHub repo. It must be public for free GitHub Pages.
2. **Pages.** Go to Settings → Pages → Source → **GitHub Actions**.
3. **Secrets.** Go to Settings → Secrets and variables → Actions. Every secret is optional; anything you leave out is simply skipped.

   | Secret | Purpose |
   |---|---|
   | `GEMINI_API_KEY` | **Recommended (free).** Key from aistudio.google.com/apikey; used automatically when present. (GitHub Models, the original free default, was retired by GitHub.) |
| `ANTHROPIC_API_KEY` | Optional. A paid Claude API key; set `LLM_PROVIDER=anthropic`. |
   | `SLACK_WEBHOOK_URL` | Slack incoming webhook |
   | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO`, `EMAIL_FROM` | Email delivery. For Gmail, use `smtp.gmail.com`, port 587 and an App Password. |
   | `WEBHOOK_URL` | Generic JSON POST (Teams, Discord, Zapier, n8n) |

   | Variable | Purpose |
   |---|---|
   | `SEC_USER_AGENT` | Required for SEC EDGAR, e.g. `Your Name you@email.com` |
   | `LLM_PROVIDER` / `LLM_MODEL` | `github` (default), `gemini` or `anthropic`, plus an optional model override |
| `NOTIFY_HEARTBEAT` | `true` or `false`: whether to send a "nothing new" message |

4. **First run.** Go to Actions → *Daily competitor intel* → **Run workflow**. That creates the baseline pull.
5. **Share.** The dashboard lives at `https://<user>.github.io/<repo>/`, and that is the link to send.
6. **Daily runs** then happen automatically at 12:47 UTC.

Local run: `python -m monitor --no-notify`. It is Python 3.11+ standard library only, with no `pip install`.

Tests: `python -m unittest discover -s tests -v`

Eval: `python -m evals.run_eval --mode both`

## Known limits (stated, not hidden)

- **Not scraped:** Google News (its robots.txt disallows this), X (needs the paid API) and LinkedIn (scraping violates its terms).
- **SERFF rate filings are not covered.** There is no reliable free automated access; trade-press coverage of filings is the proxy.
- **Bing News RSS** is checked against robots.txt on every run. If it is disallowed, it appears as `skipped_robots` on the Health tab.
- **GDELT** is rate-limited to 1 request per 5 seconds, so it adds about 2–3 minutes per run.
- **No full article text.** Classification uses the title and snippet only, so evidence is limited to that text. This is deliberate, for copyright reasons and speed.
- **Git as the database** suits MVP volumes, around 100 events a day. Postgres or Supabase is the upgrade path; `monitor/store.py` is the single seam to swap.
