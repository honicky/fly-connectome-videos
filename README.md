# fly-connectome-videos

A daily-rebuilt index of fruit fly connectome videos across YouTube, X, and
LinkedIn — the September 2026 viral simulation wave, and the science underneath it.

**Live page:** https://honicky.github.io/fly-connectome-videos/

Every entry is deduplicated across platforms, embedded where the platform allows
it, and annotated with a short note on what it actually shows.

## How it works

```
data/items.json   the corpus — one cluster per underlying video/artifact
build.py          renders index.html from that corpus; no dependencies
publish.sh        rebuilds, commits, pushes
COLLECTING.md     the daily collection procedure
```

A scheduled task runs each morning: it searches the three platforms, merges new
findings into `data/items.json`, and runs `publish.sh`. Entries are append-only —
a routine run adds clusters and adds newly-found platform copies to existing
clusters, but does not rewrite existing commentary.

## Deduplication

Two levels:

- **Identity.** `canonical_url()` reduces each post to `youtube:<video_id>`,
  `x:<status_id>` or `linkedin:<activity_id>`. The build warns if the same post
  appears in two clusters.
- **Cluster.** One cluster = one underlying video or artifact, with each platform's
  copy listed under it. The page renders the best available embed once (YouTube >
  X > LinkedIn) and links the rest as "also posted on". Two different people making
  similar videos are two clusters, not one.

## Rebuilding locally

```bash
python3 build.py && open index.html
```

No dependencies beyond the Python standard library.

## Embeds

YouTube uses a click-to-load thumbnail facade, so a page with dozens of entries
stays light and nothing loads from Google until you press play. X posts render
through the official widget; LinkedIn posts through the official post embed, which
only works for public posts and falls back to a text card otherwise.

Nothing is rehosted. Every video plays from its own platform, and every entry links
to the original creator.
