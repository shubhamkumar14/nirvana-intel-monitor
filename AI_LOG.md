# AI Implementation Log

This is a record of the prompts, human decisions, AI corrections and test evidence behind the build, kept for review with Rushil and Gary.
Builder: Claude (Forward Deployed PM chat). Owner and decision-maker: Shubham Kumar (CoS).

## Human decisions (Shubham)

| # | When (PT) | Decision | Effect on the build |
|---|---|---|---|
| H1 | 2026-10-15 15:12 | Scope expanded beyond a fixed competitor list. Added: (1) discovery of new and adjacent companies, (2) industry headwinds and tailwinds, (3) consulting, finance and industry reports, (4) political and geopolitical signals, (5) X, LinkedIn, and tech, insurance, business and political media. | Added 4 collection lanes and a discovery queue that a human approves |
| H2 | 2026-10-15 15:17 | Ship an MVP now and add sophistication later. Use personal keys and accounts only, with no enterprise tools. Prioritize scraping wherever possible. Add a **What's New** section that is filled only when there is new information versus yesterday's pull, plus a **historic repo of daily pulls**. | Git-as-database daily snapshots, a What's New tab, and a Daily Pulls tab |
| H3 | 2026-10-15 15:48 | Use a free or open model instead of a paid account for the MVP. | Added a provider switch. The default is GitHub Models (free, uses the workflow's own GitHub token). Gemini free tier and Claude are optional. |
| H4 | 2026-10-15 15:53 | Extract Nirvana's brand language from nirvanatech.com into a reusable design-system PDF and restyle the dashboard with it. | `brand/Nirvana_Brand_Design_System.pdf` (10 pages). The dashboard now uses Manrope, Instrument Serif, the navy palette and pill components. |
| H5 | pending | Competitor watchlist sign-off | `config/monitor.json` seed is still a hypothesis |

## AI proposals that were changed, and why

| # | Original AI proposal | Changed to | Why |
|---|---|---|---|
| C1 | Supabase Postgres as the store | JSON snapshots committed to git, served by GitHub Pages | H2 asked for speed and personal accounts. One account (GitHub) instead of three, and full history for free via `git log`. `store.py` keeps the Supabase upgrade path open. |
| C2 | Google News RSS as the primary news source | Dropped. Replaced with Bing News RSS (robots-checked at runtime), the GDELT DOC API, and direct trade-press and wire RSS. | On 2026-10-15 a fetch of news.google.com was refused because robots.txt disallows it. We respect robots.txt. |
| C3 | X and LinkedIn collectors (from H1) | Deferred and not scraped | X now charges per read through its official API (verified via web search 2026-10-15). LinkedIn's terms prohibit scraping. Both are listed as known limits rather than faked. |
| C4 | One classifier path that needs an API key | Claude primary, deterministic rules fallback | The run never fails silently. The dashboard shows which classifier produced every item. |
| C5 | Trusting the LLM's summary | The `evidence_quote` must be verbatim in the fetched text; otherwise the item is quarantined | Prevents hallucinated claims from reaching executives. Tested with a deliberately lying fake LLM. |
| C6 | Dashboard function named `history()` | Renamed to `pullsView()` | It shadowed `window.history` and would have broken URL-hash navigation. Caught in self-review before any test run. |
| C8 | Claude API as the only AI | Provider-agnostic client (GitHub Models / Gemini / Claude) via OpenAI-compatible endpoints | H3. GitHub Models needs no extra account. Free-tier limits (Copilot Free, low-tier model: 15 requests/min, 150/day, 8k input tokens) fit about 10 classification calls a day. The model ID and endpoint get confirmed on the first live run. |
| C9 | Put the Nirvana logo on the dashboard | Brand typography and colors only, no logo, plus a footer saying it is not an official Nirvana product | The dashboard sits on a public URL, and a logo there could read as an official Nirvana page. The logo stays in the internal brand PDF. |
| C7 | Every pull's items shown as new | The first run is a **baseline**; What's New only shows deltas versus the previous pull. Items published more than 10 days ago are tagged *late discovery*. | Old news showing up as "new" on day 1 would mislead leadership. |

## Prompts in production

- **Classifier system prompt:** `monitor/classify.py → SYSTEM_PROMPT`. Claude Haiku, temperature 0, JSON array output, verbatim evidence quote required.
- **Digest prompt:** `monitor/classify.py → DIGEST_PROMPT`. Claude Sonnet, 3–5 bullets, only from that day's new events, each bullet with a reference.

## Verified facts used in the build (2026-10-15)

| Source | Status | Detail |
|---|---|---|
| Insurance Journal RSS | ✅ valid, current items | |
| Carrier Management RSS | ✅ valid, current items | |
| Supply Chain Dive RSS | ✅ valid, current items | |
| PR Newswire insurance RSS | ✅ valid, current items | |
| FreightWaves RSS | ✅ valid, ⚠️ stale ordering | Its top items are from 2022, so the pipeline's date filter handles it. |
| Federal Register API | ✅ JSON fields confirmed | |
| Google News RSS | ❌ robots-disallowed | |
| GDELT API | ⚠️ unconfirmed | The fetch errored from the build tool; we will confirm on the first live Actions run. |
| Bing News RSS | ⚠️ unconfirmed | Same as GDELT. |

## Test evidence

| Date | What ran | Result |
|---|---|---|
| 2026-10-15 | Offline suite, `python -m unittest` on synthetic fixtures | **10/10 pass.** Covers: baseline → next-day delta (1 new, 1 updated via corroboration, 1 late discovery) → same-day re-run with 0 new and 0 LLM calls; fabricated quote quarantined; rules mode; discovery excludes the watchlist; ranking; Atom/RSS parsing; a failing source is recorded, not raised; page-diff watch. |
| 2026-10-15 | Rules classifier on the synthetic golden set (n=24) | Precision 0.947, recall 1.0, lane accuracy 0.917. Misses: a Progressive rate filing was classed as market_driver because of an alias gap; "pizza delivery deals" passed the keyword gate. These numbers are **optimistic**: the same author wrote the set and the rules. |
| _pending_ | First live GitHub Actions runs | Will be recorded here: source health, counts, and the URL of each run log. |

## Environment constraint (disclosed)

The build sandbox cannot reach news sites or PyPI; it can only reach GitHub. So:
- The code is standard-library-only.
- Logic is proven on labeled synthetic fixtures.
- **Live collection is proven only by real GitHub Actions runs.** Nothing in the dashboard is simulated.
