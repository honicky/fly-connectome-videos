Daily rebuild of RJ's fly connectome video index, published at https://honicky.github.io/fly-connectome-videos/

This runs unattended on RJ's Mac (launchd -> tools/daily-run.sh -> headless claude), in the folder /Users/rj/personal/fly-connectome-videos. Do not ask clarifying questions — make reasonable calls and report them at the end.

STEP 1 — Read the runbook, COLLECTING.md in this folder. It is the authority on every detail below; follow it exactly.

STEP 2 — Check the last publish: tail -n 5 publish.log. Note any ERROR or WARN line for the report.

STEP 3 — Collect today's items.
  - YouTube: python3 tools/yt_search.py (no browser). Runbook section 1, including the Chrome fallback if every query errors.
  - X: Claude in Chrome (mcp__claude-in-chrome__* tools; if deferred, load them all in ONE ToolSearch call). Rank by engagement with min_faves: on f=top, not by recency. Runbook section 2 and its gotchas: javascript_tool cannot return a promise, page variables do not survive a navigate, and reading location.href / cookies / whole-page text trips the content filter.
  - LinkedIn: Claude in Chrome for discovery, then each author's /recent-activity/all/ page for the post URN. Runbook section 3.
  Close every tab you open with tabs_close_mcp when done. If a platform shows a login wall or otherwise fails, skip it, note it, and continue. A partial run is fine. If the Chrome tools are not available at all, do YouTube only and say so.

STEP 4 — Merge genuinely new material into data/items.json with a Python script (read, mutate, write — never retype the file by hand). Follow the dedup rules in runbook section 4 and the writing rules in section 5. In particular:
  - one cluster = one underlying video or artifact; the same clip on two platforms goes in one cluster, two different people building similar things stay separate
  - set first_seen to today's date for new clusters
  - NEVER change first_seen or commentary on clusters that already exist, and never remove clusters
  - commentary is 1-3 sentences, states what the thing actually demonstrates, and attributes contested numbers to whoever claimed them
  - skip AI-slop re-uploads and crypto-mint spam; this is an index of videos, not of posts about videos
  - data/pending-*.json are already merged; never merge them again

STEP 5 — Publish: bash tools/publish-local.sh
It builds, checks for duplicates, commits and pushes. If it reports duplicates or invalid JSON, fix data/items.json and run it again. For any other ERROR, report it and stop — never force-push or publish another way.

STEP 6 — Report briefly: how many new clusters were added, which platforms worked and which failed, the publish result, and anything that looks broken. "Nothing new today" is a perfectly good outcome — say so and stop.
