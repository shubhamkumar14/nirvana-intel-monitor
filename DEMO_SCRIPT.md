# 15-minute live demo: Last-Mile Intel Monitor

**Audience:** Rushil Goel (CEO) and Gary Weber (Head of Finance).
**Presenter:** Shubham.

## Before you start (T-30 min)

1. **Check the last scheduled run went green.** Open `github.com/shubhamkumar14/nirvana-intel-monitor/actions`. The most recent scheduled run should have a green check.
   - If it failed, open the run log and check the Health tab.
   - Do not start a fresh run just before the meeting. A run takes about 4–6 minutes.
2. **Open three tabs:**
   - the dashboard (`https://shubhamkumar14.github.io/nirvana-intel-monitor/`)
   - the Actions page
   - `AI_LOG.md` on GitHub
3. **Pick the examples you'll click:**
   - one **Competitor Moves** card
   - one **Market Radar** headwind
   - one pull in **Daily Pulls** that has new items
4. **Rehearse the backup.** If the live run in step 4 is slow, use the most recent completed run instead.

---

## 0:00–1:30 · The problem

"We're entering last-mile commercial auto. The players that matter are LEEO (formerly Fairmatic), Progressive, the DSP programs like One80 and SPG, Risk Strategies, InShare, HDVI and Cover Whale. They move every week. Today someone has to go and look. This tool looks for us every day, records what changed, and tells us what it means for Nirvana."

## 1:30–4:00 · What's New (change detection)

1. Open **What's New**.
   - Say: "This only shows what is new or updated since the previous pull, compared against the full history. It is not a list of everything we know."
   - If it's empty, say: "Nothing new since this morning, and the tool says so instead of padding the page."
2. Open the top card and walk through it, top to bottom:
   - **Action chip** (Respond / Watch / Context): what we should do.
   - **For Nirvana**: the implication. Stress that this is the AI's analyst judgment, labeled as such.
   - **Evidence quote**: copied word for word from the source, and checked automatically.
   - **Source links**, with publish date, age and source tier.
   - **Confidence** (High / Medium / Low): hover to show the reason, e.g. "trade press, 2 independent publishers".
   - **UPDATED** badge, where one appears: a second publisher picked the story up.

## 4:00–7:00 · Breadth

1. **Competitor Moves.** Filter the company dropdown to one competitor, e.g. LEEO or Progressive.
2. **Market Radar.** Headwinds sit on the left, tailwinds on the right, e.g. verdicts, rates, DSP economics. "This is the market backdrop Gary's model depends on."
3. **Policy & Macro** and **Research.**
4. **New on the Radar.** These are companies the AI found that are *not* on our watchlist. A human approves each one before it's tracked.

## 7:00–10:00 · It runs by itself (automation history)

1. **Daily Pulls tab.** Every row is one automated run, showing:
   - its trigger (schedule or manual)
   - how many items it scanned
   - how many sources succeeded
   - new and updated counts
   - a link to the GitHub Actions log
2. Click a row to see exactly what that pull surfaced.
3. **Actions tab.** Show the green runs on the twice-daily schedule. Then click **Run workflow** and leave it running in the background.
4. Explain the pipeline in one breath: "Collect from about 40 source queries → deduplicate against all history → AI classifies → code checks every AI quote against the source → rank → save the snapshot to git → publish."

## 10:00–13:00 · Why you can trust it (AI decision log and evals)

1. **AI Decisions tab.** Every item the model looked at in the latest pull, with:
   - its decision
   - what the checker did with it: kept, dropped as irrelevant, **quarantined** because the quote wasn't in the source, or merged as a duplicate
   - the model name and token usage
2. Scroll down to the **implementation log**:
   - the human decisions (H1–H6)
   - the places where I overrode the AI (C1–C13), e.g. "Google News dropped because its robots.txt forbids scraping" and "confidence is computed in code, not by the AI"
3. **Health & Evals tab:**
   - percentage of sources that fetched successfully
   - percentage of AI claims verified against the source text
   - date coverage
   - classifier precision and recall on the test set
   - per-source status, so failures are visible

## 13:00–14:30 · Live run lands

Refresh the dashboard.
- **If something new turned up:** the new pull appears at the top of Daily Pulls and What's New updates.
- **If nothing new turned up:** say "Same sources, nothing new. Re-running costs no AI calls, because seen items are skipped."

## 14:30–15:00 · Limits and next steps

| | |
|---|---|
| **Not covered** | X (paid API), LinkedIn (its terms forbid scraping), SERFF rate filings (no free automated access), paywalled report text |
| **Next steps** | Human-labeled test set from live pulls; Slack and email digest (needs a webhook); licensed filings feed if Gary approves the cost |

---

## If something goes wrong

| Symptom | What to say or do |
|---|---|
| Live run still going at 13:00 | "It finishes in a few minutes; here's the previous run." Use the latest completed pull. |
| A source shows `error` on Health | "That's the point of the health panel: failures are visible, not silent." |
| What's New is empty | Use Daily Pulls → the most recent pull with new items. |
| Dashboard shows old data | Hard-refresh. Pages deploys about 1 minute after the run finishes. |
