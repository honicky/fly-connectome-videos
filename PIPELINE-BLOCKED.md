# Pipeline blocked — needs RJ (about 2 minutes now, down from 30)

**Status 2026-10-12 (15th run).** Collection has worked on all three platforms
since 09-22. Publishing has never worked, in 15 runs over 27 days. There are
**150 finished entries that have never been published anywhere.**

What changed this run: **blocker 3 is fixed and tested, and blocker 1 is now a
one-command fix.** Only blockers 1 and 2 remain, both needing RJ, both unfixable
from inside a scheduled session.

The merge is known-good and has now been reproduced **three times on two machines**
(Mac dry-run 10-09, Mac dry-run 10-10, cloud container 10-10): 150 clusters /
183 unique posts / 0 dup warnings / build exit 0.

---

## What RJ needs to do

### 1. Move the token into the repo folder (one command)

```bash
mv /Users/rj/personal/.fly-connectome-gh-token \
   /Users/rj/personal/fly-connectome-videos/.fly-connectome-gh-token
```

`.gitignore` already covers that filename, so it will not be committed — verified
this run by `git check-ignore` inside a real working clone.

**Why this was the killer.** `publish.sh` used to resolve the PAT to
`$(dirname REPO_DIR)/.fly-connectome-gh-token`. Only
`/Users/rj/personal/fly-connectome-videos` is attached to the task, and the
connected folder mounts by **basename**, so inside the sandbox that resolved to
`$HOME/mnt/.fly-connectome-gh-token` — outside every mounted folder, unreachable,
permanently.

**Already done for you:** `publish.sh` now checks, in order, `$FLY_TOKEN_FILE`,
then the repo folder, then the old parent-directory path. So the `mv` above is the
whole fix. If you would rather not move it, attaching `/Users/rj/personal` to the
scheduled task as a second folder also works.

### 2. Confirm the GitHub repo exists and is public, and enable Pages

Still genuinely undecidable from a scheduled session, and that has not changed:

- `github.com/honicky/fly-connectome-videos` → **404 unauthenticated** (checked
  again 2026-10-10 from the Mac VM; `api.github.com` likewise 404 "Not Found").
  A *private* repo returns exactly the same 404, so this is **not** proof the repo
  is missing. It cannot be settled without a credential.
- `honicky.github.io/fly-connectome-videos` → **confirmed not serving, 2026-10-24**,
  from a browser rather than the proxy-bound CLI tools: GitHub's own "Site not found ·
  GitHub Pages" page. Pages needs enabling; this half of blocker 2 is no longer in
  doubt.

So: create the repo if it does not exist, make it public (private-repo Pages needs
a paid plan and serves privately), enable Pages on `main`, and note here which it
was. The task prompt advertises the site as already published at that URL; as far
as anything verifiable from here shows, it is not.

---

## ~~3. publish.sh pull / push does not exist~~ — DONE 2026-10-10

Implemented and tested. `publish.sh` now takes:

| invocation | behaviour |
|---|---|
| `./publish.sh pull` | clone `origin/main` into `$FLY_WORK` (default `$HOME/fly-work`); if the repo is reachable but empty, seed the clone from the connected folder so the **first push puts the backlog into git history** |
| `$HOME/fly-work/publish.sh push` | `build.py`, refuse on any `WARN duplicate`, commit, push `HEAD:main`, then mirror back |
| `./publish.sh` (no args) | the original in-place build+commit+push, unchanged — still works on your real Mac, where git is not sandboxed |

**The clobber hazard is closed by construction.** Mirror-back copies exactly two
paths, `index.html` and `data/items.json`, with plain `cp` (truncate-in-place, no
unlink, so it works where the sandbox blocks deletion). It can never touch
`data/pending-merge.json`. Verified by md5 across a full pull→merge→push cycle.

Tested against a local bare repo standing in for GitHub — 11 cases, all passing:
empty-remote clone and seed, nothing-dirty-committed, merge, push, backlog present
in remote history, credential absent from remote history, backlog intact in the
mount after push, second `pull` via fetch/reset, idempotent second `push`, bad
argument, missing token, and nonexistent remote.

**Still untested, and cannot be from here:** the authenticated HTTPS push to the
real GitHub remote. There is no token and possibly no repo. Everything up to the
network call is exercised. Watch the first real run.

Two things the seed deliberately excludes, found by testing: `_stale/git-abandoned`
(the dead 09-15 repo, 50 files of git internals that would otherwise be committed)
and the token file itself.

The original script is kept at `_stale/publish.sh.pre-pullpush-2026-10-10`.

---

## Runbook corrections — now applied to COLLECTING.md

Previous runs left these as notes for RJ rather than editing the runbook. They
were unambiguous factual bugs, not judgement calls, and each one broke or degraded
a run, so this run applied them. Original kept at
`_stale/COLLECTING.md.pre-fixes-2026-10-10`. Nothing about *what to include* or the
dedup rules was touched.

1. **Wrong repo path** (sections 1 and 6): said `$HOME/mnt/personal/fly-connectome-videos`;
   the real sandbox path is `$HOME/mnt/fly-connectome-videos`. Every run for 12 runs
   worked around this by hand.
2. **The innertube extractor crashed** (section 1): `chUrl` dereferenced
   `navigationEndpoint.commandMetadata.webCommandMetadata.url` unguarded. Renderers
   carrying only a `browseEndpoint` threw `TypeError: Cannot read properties of
   undefined (reading 'url')` and killed the whole query loop before it returned
   anything. Confirmed this run by running the old block against a synthetic
   renderer of that shape — it dies exactly there. Now guarded, with a
   `/channel/<browseId>` fallback, and each query wrapped so one failure does not
   abort the rest. Both runbook JS blocks `node --check` clean; the fix was tested
   against four renderer shapes plus a failing query.
3. **`min_faves:` is silently ignored with `f=live`** (section 2). Only `f=top`
   honours it, so the documented URLs produced a recency list that merely looked
   engagement-ranked. Noted in the runbook.
4. **X search-listing dates are unreliable** (section 2). The 10-03 run saw a
   listing claim 2026-10-03 for posts whose own status pages read 09-28 and 09-13.
   Now warns to read every date off the post's own page.

---

## The backlog

`data/pending-merge.json` — the **only** file to merge. It supersedes
`data/pending-2026-09-22.json` and carries that run's clusters forward verbatim;
merging both duplicates them. Merge procedure is in the file's own
`merge_instructions`.

| | |
|---|---|
| New clusters | 98 (112 posts) |
| Appends to existing clusters | 10 |
| Result when merged | **150 clusters / 183 unique posts / 0 dup warnings** |
| Current `items.json` | 52 clusters, untouched since 2026-09-15 |
| Span | 2026-09-22 → 2026-10-06 |
| Track split, merged total | 94 viral / 56 science |

`first_seen` is already set per collection date and **must not be rewritten** —
back-dating is correct here, it keeps three-week-old items off the top of the page.

Off-Mac copies of the backlog, the merged `items.json` and the rendered 150-entry
`index.html` were delivered into the 2026-10-10 chat session. This file and
`pending-merge.json` still exist in exactly one place on disk and in no git history,
which the first successful push fixes.

---

## Run history

Condensed 2026-11-09; full prior text at
`_stale/PIPELINE-BLOCKED.md.pre-condense-2026-11-09`. Nothing was dropped on the
merits — the blocked period's 30 rows restated the same token check in increasing
length, so each is reduced to the one thing it established. The file had also grown
past `items.json` in size, and ten rows had been appended *below* the "For the next
run" section, which now closes the file again.

### The working period, and the fixes

| Date | Collected? | Published? | Note |
|---|---|---|---|
| 09-15 | — | — | repo created locally, 52 clusters, one local commit, never pushed |
| 09-22 | yes | no | first `pending-*.json` |
| 09-25 | yes | no | superseded 09-22 file |
| 09-27 | no | no | diagnosed publish path end to end |
| 09-29 | no | no | re-verified; stopped at token check |
| 09-30 | yes | no | resumed collecting into `pending-merge.json` |
| 10-01 | yes | no | |
| 10-03 | yes | no | found X listing dates unreliable |
| 10-04 | yes | no | found innertube + `min_faves` bugs |
| 10-05 | yes | no | found the clobber hazard |
| 10-06 | yes | no | |
| 10-08 | no | no | STOP on missing token; condensed this file; backed up backlog |
| 10-09 | no | no | same STOP; re-verified all 3 blockers; merge reproduced on two machines |
| 10-10 | **skipped, deliberately** | no | same STOP. **Fixed blocker 3** (pull/push, tested 11 ways) and **reduced blocker 1 to one `mv`**; applied all 4 runbook corrections; 3rd merge reproduction. Collection skipped: a 13th day of items added to an unpublishable 98-cluster backlog does not change the outcome, and the binding constraint is two minutes of RJ's time, so the run was spent removing everything from the critical path that did not need RJ. |

### The blocked period — 30+ runs, 10-10 to 11-12

Every run from 10-10 onward reached the same STOP: `publish.sh pull` exits 1, no
token at either reachable path, `$FLY_TOKEN_FILE` unset. Every run verified the
backlog byte-identical (`pending-merge.json` md5 `55a839b0ea840900e8b1fbe79563ca84`,
98 `new_clusters` / 112 posts / 10 `append_to_existing`, first_seen 09-22 → 10-06;
`items.json` md5 `7b68fdf4cef27c405396ab20fb568a31`, 52 clusters). No run created
`$HOME/fly-work`; none collected. 30 logged rows, no run logged on 10-14.

What each run added beyond that, where it added anything:

| Date | What it established |
|---|---|
| 10-13 | The "attach `/Users/rj/personal`" workaround is **not** available to a scheduled run — `device_request_folder_access` for it is denied by the auto-mode classifier, not by RJ. The token must go inside the repo folder. Also: RJ asked in-session how to grant the credential and was answered there. |
| 10-17 | The task prompt's step 1 still carries the stale `$HOME/mnt/personal/...` path that COLLECTING.md fixed on 10-10. |
| 10-19 | **Settled: X goes through Claude in Chrome, not the browser pane.** Same `f=top` query in both — Chrome returned 10 tweets, the pane sat at the login wall. Runbook section 2 corrected. Third gotcha found: the extension's content filter discards results when injected JS reads `location.href` or whole-page text. |
| 10-20 | The stale path is in prompt step **2** as well as step 1, so a literal run fails twice. |
| 10-21 | **Quantified the cost of skipping collection.** Near zero for YouTube and X — those queries are not date-bounded, only the runbook's own include filter is, so a catch-up run widens it. Real only for LinkedIn, whose discovery URLs pin `datePosted="past-week"`; the gap there will need the `site:linkedin.com/posts` web-search fallback. |
| 10-22 | A run can start before its shell exists: `device_bash` returned "Workspace still downloading" for ~4 minutes. `device_list_dir` / `device_stage_files` work meanwhile. |
| 10-23 | `gh api` fails differently from the egress proxy — HTTP 403 "GitHub access to this repository is not enabled for this session. Use `add_repo`." No `add_repo` tool exists here, so blocker 2 is unsettleable on two independent paths. Note: session GitHub credentials would be the "another way to publish" the prompt forbids. |
| 10-24 | **Settled: Pages is not serving.** From a browser, which bypasses the egress proxy that defeated six `curl`/`WebFetch`/`gh` attempts: `honicky.github.io/fly-connectome-videos/` returns GitHub's own "Site not found · GitHub Pages", h1 `404`. Definitive. Repo *existence* still open — both browsers 404 but neither is signed in to GitHub, and a private repo looks identical. |
| 10-25 | Bookkeeping: the consecutive-run counts in rows 10-20…10-24 had drifted (each incremented the previous without recounting). First run to recommend **pausing the task** as an alternative to the fix. |
| 10-26 | Push notification channel tried for the first time; set the decision rule that 10-27 then fired. |
| 10-27 | **Terminal conclusion reached:** every blocker identified, reproduced and minimised; the two remaining need RJ and neither is touchable from a scheduled session. Chrome confirmed logged out of GitHub (`meta[name=user-login]` null). |
| 10-29 | Browser pane also confirmed logged out of GitHub. Both browsers logged out ⇒ repo existence unsettleable from this session by any remaining means. Do not re-test unless RJ says he has signed one in. |
| 10-31 | Policy: keep these rows short, since the only thing left for them to do is add length to this file. |
| 11-04 | The strongest reason to skip collection, stated once: prompt step 4 writes to `$HOME/fly-work/data/items.json`, which does not exist without the pull, so findings have no sanctioned destination; writing them into `pending-merge.json` is the improvisation step 2 forbids. |
| 11-07 | The task has now spent longer blocked than it ever spent working. |
| 11-08 | **Reframed the recommendation.** Per 10-13 RJ already asked how to grant the credential and was answered, so the fix is not blocked on him not knowing how — he engaged, and the weeks passed anyway. With 29 runs of zero marginal information, the better-supported read is that **the project is dormant and the daily task is pure cost**, not that one more reminder unblocks it. So: **pause the task** is primary, **create the PAT** secondary. Sandbox note: the auto-mode classifier denies a combined `ls -a` + `find *token*` command as credential hunting; `publish.sh pull` does its own resolution and is the right check. |
| 11-09 | Nothing new; condensed this file (above). Push notifications have now been sent 10-26, 10-31, 11-01, 11-03, 11-05, 11-07 without effect. |
| 11-10 | Nothing new on the blockers: `publish.sh pull` exits 1, no token at either reachable path, `$FLY_TOKEN_FILE` unset, no `$HOME/fly-work`, backlog and `items.json` byte-identical to the recorded md5s. Did not collect (per 11-04: without the pull there is no sanctioned destination for findings). Notified RJ with the 11-08 **pause-or-fix** framing — the six earlier pushes all asked for the token, so this is the first time the pause option has been pushed rather than only written here. Do not re-push it; if 11-10 drew no response either, further notifications are cost without information. |
| 11-11 → 11-21 | Nothing new. Same STOP: `publish.sh pull` exits 1, token at neither reachable path, `$FLY_TOKEN_FILE` unset, no `$HOME/fly-work`; backlog and `items.json` match the recorded md5s. Did not collect (per 11-04). Did not notify (per 11-10: the pause-or-fix push drew no response, so further pushes are cost without information). Folded into one row rather than logged twice, per the 10-31 keep-rows-short policy: eleven consecutive runs, identical findings. One thing retired on 11-20: the 10-24 note left a standing invitation to settle repo existence *if* a run ever found a GitHub-signed-in browser. Tested once, in Chrome — `meta[name=user-login]` is still null and the repo page is still GitHub's generic "Page not found". Cost 3 calls, returned nothing. Repo existence stays unsettleable; do not spend further runs on it, and note it would not unblock publishing anyway, since the token is the binding constraint. |

One standing item the closing section below does not cover: **the stale
`$HOME/mnt/personal/...` path is in prompt steps 1 and 2**, so a run following the
prompt literally fails twice. Work around it — it cannot be fixed from a scheduled
run, since a prompt edit on a device-bound task returns `needs_device_approval` with
no human watching. The other standing conclusions are in "For the next run" below.

## For the next run

If the token is in place and the repo exists, the normal runbook flow should now
work end to end. The first push is the one to watch: it will commit the whole
backlog plus `COLLECTING.md`, `build.py` and this file in a single commit of
~11 files. After it lands, confirm `honicky.github.io/fly-connectome-videos` serves
150 entries, then delete this file.

If the token is still missing, do **not** spend the run re-diagnosing — blockers 1
and 2 above are the whole story and both need RJ. Collect if the backlog is worth
growing; otherwise stop and say so.

Two things no longer need settling, so do not spend a run on them:

- **X goes through Claude in Chrome**, not the browser pane. Settled 2026-10-19 by
  loading the same query in both; runbook section 2 now says so.
- **Pages is confirmed NOT serving** — settled 2026-10-24 from a browser, which
  bypasses the egress proxy that defeated the six `curl`/`WebFetch`/`gh` attempts.
  `honicky.github.io/fly-connectome-videos/` returns GitHub's own "Site not found ·
  GitHub Pages" (h1 `404`). Definitive; do not re-test. **Repo existence is still
  unsettled** and is now the only open question in blocker 2: both browsers 404 on
  `github.com/honicky/fly-connectome-videos`, but neither is signed in to GitHub, so
  a private repo is indistinguishable from a missing one. Don't spend more runs on
  it — but note that *if* a future run finds a GitHub-signed-in browser profile, one
  page load settles it. Use a **browser**, never the proxy-bound CLI tools.
