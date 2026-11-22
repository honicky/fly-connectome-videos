# Daily collection runbook

This is the procedure the scheduled task follows. It exists in the repo so the
scheduled task prompt can stay short and this logic stays version-controlled.

Everything runs on RJ's Mac: the browser work uses Claude's **browser pane**
(`Claude_Browser__*` tools), which has persistent logged-in sessions. The shell
work uses `device_bash`, where the repo is at `$HOME/mnt/fly-connectome-videos`.
(The connected folder mounts by **basename**, so there is no `personal/` segment
inside the sandbox even though the Mac path is `/Users/rj/personal/...`.)

**Never** re-type `data/items.json` from memory. Always read it, mutate it with a
script, and write it back.

---

## 1. YouTube

Open any YouTube page in the browser pane, then run the in-page search API. This
is far more reliable than scraping the DOM, which changes constantly.

```js
(async()=>{
const key=ytcfg.get('INNERTUBE_API_KEY'),ctx=ytcfg.get('INNERTUBE_CONTEXT');
const qs=["fly connectome","fruit fly brain simulation","MaleCNS fly brain",
          "flywire connectome","fly brain bad apple","fruit fly brain video game",
          "drosophila connectome visualization","fly brain neural simulation"];
const seen={},out=[];
for(const q of qs){
 let j;
 try{
  const r=await fetch(`/youtubei/v1/search?key=${key}`,{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({context:ctx,query:q})});
  j=await r.json();
 }catch(e){out.push({id:'',q,error:String(e)});continue}
 const found=[];
 (function walk(o,d){if(!o||typeof o!=='object'||d>14)return;
   if(o.videoRenderer)found.push(o.videoRenderer);for(const k in o)walk(o[k],d+1)})(j,0);
 found.forEach(v=>{if(!v.videoId||seen[v.videoId])return;seen[v.videoId]=1;
  out.push({id:v.videoId,q,
   title:(v.title&&(v.title.runs?v.title.runs[0].text:v.title.simpleText))||'',
   ch:(v.ownerText&&v.ownerText.runs&&v.ownerText.runs[0].text)||'',
   chUrl:(function(){try{
     const ne=v.ownerText&&v.ownerText.runs&&v.ownerText.runs[0].navigationEndpoint;
     if(!ne)return '';
     const cm=ne.commandMetadata&&ne.commandMetadata.webCommandMetadata;
     if(cm&&cm.url)return cm.url;
     const bid=ne.browseEndpoint&&ne.browseEndpoint.browseId;
     return bid?('/channel/'+bid):''}catch(e){return ''}})(),
   pub:(v.publishedTimeText&&v.publishedTimeText.simpleText)||'',
   views:(v.viewCountText&&v.viewCountText.simpleText)||'',
   len:(v.lengthText&&v.lengthText.simpleText)||'',
   desc:((v.detailedMetadataSnippets&&v.detailedMetadataSnippets[0]
          &&v.detailedMetadataSnippets[0].snippetText.runs)||[])
          .map(r=>r.text).join('').slice(0,260)})})
}
return {n:out.length,items:out};
})()
```

Keep anything published within roughly the last two weeks, plus older items with
real substance (lab/university channels, talks). Skip obvious AI-slop re-uploads:
generic titles, sub-500 views, no specific claim, channel posts nothing else on
the topic.

## 2. X

Use **Claude in Chrome** (`mcp__claude-in-chrome__*`) — RJ's real Chrome holds the
signed-in X session. The **browser pane is logged out of X** and redirects
`x.com/search` to `/i/jf/onboarding/web?...&mode=login`.

Verified both ways 2026-10-19, which settles the prompt/runbook disagreement the
10-18 run flagged: Chrome returned 10 results on `f=top` with a compose button and
no login link; the pane returned 0 results sitting at the login wall. The prompt was
right and this section was wrong — it previously said X required the browser pane.

X's login wall blocks logged-out search, individual post pages, and even
`publish.twitter.com/oembed`, so there is no logged-out fallback. If Chrome *also*
redirects to a login screen, record that X was unavailable this run, skip it, and
carry on; do not try to work around it.

Load the Chrome tools in ONE `ToolSearch` call. Three gotchas:

- `javascript_tool` cannot return a promise. No `async` wrapper — return
  `JSON.stringify(...)` of a synchronous expression.
- Page variables do not survive a `navigate`.
- Reading `location.href`, `document.cookie` or whole-page text can trip the
  extension's content filter, which returns `[BLOCKED: Cookie/query string data]`
  and discards your result. Select specific DOM facts instead (observed 2026-10-19).

Close any tab you open with `tabs_close_mcp` when done.

Search URLs (`f=live` for recency, `f=video` for video-only, `f=top` for engagement).

> **`min_faves:` is silently ignored with `f=live`.** Only `f=top` honours it. When
> ranking by engagement rather than recency, drop `f=live` — otherwise the operator
> is dropped and you get a recency list that merely looks engagement-ranked.
>
> **X search-listing dates are unreliable.** A 2026-10-03 listing claimed that date
> for posts whose own status pages read 09-28 and 09-13. Read every date off the
> post's own page, never off the search listing.

```
https://x.com/search?q=%22fly%20brain%22%20OR%20connectome%20filter%3Avideos&f=live
https://x.com/search?q=%22fly%20connectome%22%20OR%20MaleCNS&f=live
```

Extract per post: status URL, author handle, text, timestamp, engagement counts.
The status URL is the identity — `x:<status_id>`.

## 3. LinkedIn

Two steps, because LinkedIn strips post permalinks out of search results entirely.

**Discovery** — browser pane, read the rendered text:

```
https://www.linkedin.com/search/results/content/?keywords=fly%20connectome&datePosted=%22past-week%22
https://www.linkedin.com/search/results/content/?keywords=connectome%20fly%20brain&datePosted=%22past-week%22
```

`get_page_text` returns author names, headlines, relative timestamps and post
bodies. It does **not** return permalinks.

**Permalinks** — for each author found, open their activity page and pair URNs to
post text:

```
https://www.linkedin.com/in/<slug>/recent-activity/all/
```

```js
(async()=>{await new Promise(r=>setTimeout(r,3500));
const out=[],seen=new Set();
document.querySelectorAll('*').forEach(el=>{let hit=null;
 for(const a of el.attributes||[]){
   const m=(a.value||'').match(/urn:li:(?:activity|ugcPost|share):(\d{17,20})/);
   if(m){hit=m[0];break}}
 if(!hit||seen.has(hit))return;let n=el,txt='';
 for(let i=0;i<8&&n;i++){const t=(n.innerText||'').trim();if(t.length>120){txt=t;break}n=n.parentElement}
 seen.add(hit);out.push({urn:hit,text:(txt||el.innerText||'').replace(/\s+/g,' ').slice(0,420)})});
return out.slice(0,6);})()
```

Match by text prefix, then build:

- link: `https://www.linkedin.com/feed/update/<urn>/`
- embed: `https://www.linkedin.com/embed/feed/update/<urn>` (handled by `build.py`)

For posts older than a day or two, a web search for
`site:linkedin.com/posts <keywords>` often returns the permalink directly and
skips the activity-page step.

---

## 4. Deduplication

Two different levels — do not conflate them.

**Identity (exact duplicate).** `build.py:canonical_url()` already collapses these:
`youtube:<video_id>`, `x:<status_id>`, `linkedin:<activity_id>`. The build prints a
`WARN duplicate` line if the same post lands in two clusters. Treat that as an error
and fix the data.

**Cluster (same underlying thing on multiple platforms).** This is the judgement
call and it is yours, not the script's. Put items in the same cluster when they are
the *same video or the same specific artifact*:

- the same video cross-posted to YouTube and X → one cluster
- the same lab video re-uploaded by three university channels → one cluster
- several LinkedIn posts all reacting to one project's release → one cluster with
  that project's video as primary

Keep them **separate** when they are distinct creations, even on the same topic:
two different people each putting a fly brain in Minecraft are two entries, and a
reaction video is not the same item as the thing it reacts to.

Signals for "same thing": near-identical title after lowercasing and stripping
punctuation; same creator handle across platforms; same duration; one explicitly
links to the other.

## 5. Writing entries

- `track`: `viral` for builds, remixes, stunts and reaction content;
  `science` for data releases, lab visualizations, talks, and explainers.
- `commentary`: 1–3 sentences. Say what it actually is and what it does or does not
  demonstrate. State numbers only when the source states them, and attribute
  contested claims to whoever made them. Do not pad, do not cheerlead, and do not
  assert that a simulation shows something it does not.
- `first_seen`: the date this index first saw it — set it once, never rewrite it.
  It drives ordering, so back-dating an old item keeps it out of the top of the page.
- Never edit `commentary` or `first_seen` on an existing cluster during a routine
  run. Only add new clusters and add newly-found platform copies to existing ones.

## 6. Build and publish

Git **cannot** run inside `$HOME/mnt/fly-connectome-videos`. The sandbox
blocks file deletion there, so git's lock files survive and the second commit ever
made dies with `cannot lock ref 'HEAD': File exists`. Delete permission does not
fix this — that grant needs a fresh human approval on every run, which a scheduled
job cannot get. So GitHub is the source of truth and all git work happens in the
VM's scratch space.

```bash
cd $HOME/mnt/fly-connectome-videos
./publish.sh pull            # clones GitHub -> $HOME/fly-work
# ... edit $HOME/fly-work/data/items.json with a script ...
$HOME/fly-work/publish.sh push   # builds, commits, pushes, mirrors back
```

Always edit `$HOME/fly-work/data/items.json` — the copy in the mounted folder is a
mirror, and anything written only there is overwritten on the next push.

`publish.sh` resolves the GitHub token in this order, taking the first that exists:

1. `$FLY_TOKEN_FILE`, if set
2. `<connected folder>/.fly-connectome-gh-token`  ← **preferred**
3. `$(dirname <connected folder>)/.fly-connectome-gh-token`  (legacy; **unreachable
   from the sandbox** when only the repo folder is attached)

Keep the token at option 2 — inside the repo folder, where `.gitignore` already
covers it. Option 3 was the old default and is why 12 runs could not publish: it
resolves outside every mounted folder. The token is never written to git config,
the remote URL, or the reflog.

If no token file exists the script exits non-zero with the list of paths it tried —
report that and stop rather than improvising another way to publish.

`pull` and `push` are implemented as of 2026-10-10 (`publish.sh` with no argument
keeps the old in-place build-and-push, which only works outside the sandbox where
git is not restricted). `push` refuses to publish if `build.py` reports any
duplicate warnings, and mirrors **only** `index.html` and `data/items.json` back to
the connected folder — deliberately narrow, so a clone of an empty repo can never
overwrite `data/pending-merge.json`.

### Merging new findings

Read, mutate, write — never regenerate the file by hand:

```python
import json, datetime
p = "data/items.json"
d = json.load(open(p))
by_id = {c["id"]: c for c in d["clusters"]}
# ... append new clusters / append items to existing clusters ...
d["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
```
