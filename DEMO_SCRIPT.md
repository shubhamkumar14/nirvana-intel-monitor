# Live demo script (≈7 minutes)

**Setup before the meeting:** the dashboard is open, the GitHub Actions tab is open, and the Slack channel is open.

1. **The problem (30s).** "We want to know the day something changes in last-mile commercial auto: a competitor launches, exits or reprices; a new player shows up; or a law or verdict trend shifts the economics. Nobody should have to go look for it."

2. **What's New (60s).** Open the dashboard.
   - What's New only shows what changed since yesterday's pull. On a quiet day it says nothing is new, which is also a signal.
   - Open one card and point out its parts:
     - the source link and tier
     - the verbatim evidence quote
     - the publish date and age
     - the verification badge
     - the score, with its components on hover.

3. **Breadth (60s).**
   - **Competitor Moves:** filter by company.
   - **Market Radar:** headwinds versus tailwinds.
   - **New on the Radar:** companies the agent found that are not on our watchlist. A human approves each one before it is tracked, so the list stays clean.

4. **It runs by itself (90s).**
   - In GitHub Actions, show the daily schedule and the history of green runs.
   - Click **Run workflow** live. While it runs, explain the pipeline: collect → dedup against history → Claude classify → verify → rank → commit the snapshot → publish.
   - **Daily Pulls:** every pull is kept and clickable.

5. **Why you can trust it (90s).** Open **Health & Evals**.
   - Every AI claim is checked against the source text, and unverifiable items are quarantined. Show the pass rate.
   - Show the per-source health table: failures are visible, not silent.
   - Show the golden-set precision and recall. CI blocks any prompt change that drops precision.

6. **Where I overrode the AI (60s).** Open `AI_LOG.md` and walk through C1 to C7:
   - Supabase was swapped for git for speed.
   - Google News was dropped because of robots.txt.
   - X and LinkedIn were deferred rather than scraped.
   - The baseline rule stops old news from looking new.

7. **Next (30s).**
   - A human-labeled golden set from live pulls.
   - SME-approved watchlist.
   - X via the paid API if Gary approves about $30/month.
   - Supabase plus 👍/👎 feedback.
   - SERFF through a licensed feed.

When the live run finishes, refresh the dashboard. The new pull appears in Daily Pulls, and a Slack message arrives.
