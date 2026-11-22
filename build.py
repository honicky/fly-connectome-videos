#!/usr/bin/env python3
"""
Build index.html from data/items.json.

Data model
----------
{
  "updated": "2026-09-15T14:02:00Z",
  "clusters": [
    {
      "id": "slug",                      # stable, unique
      "track": "viral" | "science",
      "title": "Human-readable title",
      "commentary": "1-3 sentences.",
      "first_seen": "2026-09-15",
      "last_seen": "2026-09-15",
      "items": [
        {"platform":"youtube","url":"https://www.youtube.com/watch?v=ID",
         "video_id":"ID","author":"Channel","author_url":"https://...",
         "title":"...","published":"2 days ago","views":"407K views",
         "duration":"6:26"},
        {"platform":"x","url":"https://x.com/handle/status/123",
         "author":"@handle","text":"...","published":"Sep 6, 2026",
         "views":"11.5M"},
        {"platform":"linkedin","url":"https://www.linkedin.com/posts/...-activity-7123...-AbCd",
         "author":"Name","author_title":"...","text":"...","published":"20h"}
      ]
    }
  ]
}

One cluster == one underlying video/story. Cross-platform dedup happens by
putting every platform's copy in the same cluster's `items` list; the page
renders the best available embed once and links the rest.
"""

import html
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "items.json")
OUT = os.path.join(ROOT, "index.html")
MEDIA = os.path.join(ROOT, "data", "media.json")

PLATFORM_ORDER = {"youtube": 0, "x": 1, "linkedin": 2, "other": 3}
PLATFORM_LABEL = {"youtube": "YouTube", "x": "X", "linkedin": "LinkedIn", "other": "Web"}

LI_ACTIVITY = re.compile(r"activity[-:](\d{10,25})")
YT_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")
X_STATUS = re.compile(r"(?:twitter|x)\.com/([^/]+)/status/(\d+)")


def esc(s):
    return html.escape(s or "", quote=True)


# --------------------------------------------------------------------------
# normalization / dedup safety net
# --------------------------------------------------------------------------

def canonical_url(item):
    """Platform-native identity, used to drop exact duplicates inside a cluster."""
    url = (item.get("url") or "").strip()
    p = item.get("platform")
    if p == "youtube":
        vid = item.get("video_id") or (YT_ID.search(url).group(1) if YT_ID.search(url) else None)
        return f"youtube:{vid}" if vid else f"url:{url.lower()}"
    if p == "x":
        m = X_STATUS.search(url)
        return f"x:{m.group(2)}" if m else f"url:{url.lower()}"
    if p == "linkedin":
        m = LI_ACTIVITY.search(url)
        return f"linkedin:{m.group(1)}" if m else f"url:{url.split('?')[0].lower()}"
    return f"url:{url.split('?')[0].lower()}"


def youtube_id(item):
    if item.get("video_id"):
        return item["video_id"]
    m = YT_ID.search(item.get("url") or "")
    return m.group(1) if m else None


def linkedin_urn(item):
    if item.get("urn"):
        return item["urn"]
    m = LI_ACTIVITY.search(item.get("url") or "")
    return f"urn:li:activity:{m.group(1)}" if m else None


# --------------------------------------------------------------------------
# embeds
# --------------------------------------------------------------------------

def _excerpt(item, limit=340):
    txt = (item.get("text") or item.get("title") or "").strip()
    if len(txt) > limit:
        txt = txt[:limit].rsplit(" ", 1)[0] + "…"
    return txt


def _text_facade(item, data_attr, label):
    """Readable post text up front; the real embed loads on click.

    Third-party frames fail for reasons outside our control -- tracking
    blockers, a post going private, a sandboxed preview. A facade means the
    substance is always visible and a blocked frame degrades to something
    readable instead of an empty box.
    """
    role = esc(item.get("author_title") or "")
    role_html = f'<span class="frole">{role}</span>' if role else ""
    meta = esc(item.get("published") or "")
    views = esc(item.get("views") or "")
    sub = " · ".join(b for b in (meta, views) if b)
    return (
        f'<div class="facade facade-text" {data_attr} data-url="{esc(item.get("url") or "")}" '
        f'data-plat="{esc(PLATFORM_LABEL.get(item.get("platform"), "the web"))}" '
        f'role="button" tabindex="0" aria-label="{esc(label)}">'
        f'<div class="fq">'
        f'<div class="fwho">{esc(item.get("author") or "")}{role_html}</div>'
        f'<p>{esc(_excerpt(item))}</p>'
        f'<div class="fsub">{sub}</div>'
        f'</div>'
        f'<span class="floadbar">{esc(label)}</span>'
        f'</div>'
    )


def _yt_facade(vid):
    thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return (
        f'<div class="facade facade-yt" data-yt="{esc(vid)}" role="button" tabindex="0" '
        f'aria-label="Play video">'
        f'<img src="{esc(thumb)}" alt="" loading="lazy" decoding="async" '
        f'onerror="this.closest(\'.facade\').classList.add(\'nothumb\')">'
        f'<span class="play" aria-hidden="true"></span></div>'
    )


def _native_video_facade(item, m):
    """Poster + play button; click swaps in a native <video> streaming the
    platform's own MP4 (resolved by tools/fetch_media.py). Highest allowed
    bitrate first so the browser takes it; lower ones are fallbacks."""
    srcs = sorted(m.get("sources") or [], key=lambda s: -(s.get("bitrate") or 0))
    plat = PLATFORM_LABEL.get(item.get("platform"), "the web")
    poster = m.get("poster") or ""
    img = (f'<img src="{esc(poster)}" alt="" loading="lazy" decoding="async" '
           f'onerror="this.closest(\'.facade\').classList.add(\'nothumb\')">') if poster else ""
    return (
        f'<div class="facade facade-vid{"" if poster else " nothumb"}" '
        f'data-vsrc="{esc(json.dumps([s["url"] for s in srcs]))}" data-poster="{esc(poster)}" '
        f'data-gif="{1 if m.get("gif") else 0}" '
        f'data-url="{esc(item.get("url") or "")}" data-plat="{esc(plat)}" '
        f'role="button" tabindex="0" aria-label="Play video from {esc(plat)}">'
        f'{img}<span class="play" aria-hidden="true"></span>'
        f'<span class="vplat p-{esc(item.get("platform"))}">{esc(plat)}</span></div>'
    )


def playable(item, media):
    """Media-cache entry with a playable video for an X/LinkedIn item, else None."""
    if not media or item.get("platform") not in ("x", "linkedin"):
        return None
    m = media.get(canonical_url(item))
    if m and m.get("status") == "ok" and (m.get("sources") or m.get("youtube")):
        return m
    return None


def embed_html(item, media=None):
    """Return (kind, html). Every embed is click-to-load: dozens of live
    third-party frames would make the page slow and fragile."""
    p = item.get("platform")

    if p == "youtube":
        vid = youtube_id(item)
        if vid:
            return "video", _yt_facade(vid)

    m = playable(item, media)
    if m:
        if m.get("youtube"):          # LinkedIn post that links a YouTube video
            return "video", _yt_facade(m["youtube"])
        return "video", _native_video_facade(item, m)

    if p == "x":
        m = X_STATUS.search(item.get("url") or "")
        if m:
            return "video", _text_facade(item, f'data-x="{esc(m.group(2))}"', "Load post from X")

    if p == "linkedin":
        urn = linkedin_urn(item)
        if urn:
            return "video", _text_facade(item, f'data-li="{esc(urn)}"', "Load post from LinkedIn")

    # No embeddable form at all -- plain text card.
    return "text", (
        f'<div class="textcard"><p>{esc(_excerpt(item, 420))}</p>'
        f'<a class="out" href="{esc(item.get("url"))}" target="_blank" rel="noopener">'
        f'Open on {esc(PLATFORM_LABEL.get(p, "the web"))} →</a></div>'
    )


def pick_primary(items, media=None):
    """Prefer the copy that embeds best and richest: anything with a playable
    video first, then YouTube > X > LinkedIn."""
    def key(i):
        has_video = i.get("platform") == "youtube" or playable(i, media) is not None
        return (0 if has_video else 1, PLATFORM_ORDER.get(i.get("platform"), 9))
    return sorted(items, key=key)[0]


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def render_meta(item):
    bits = []
    if item.get("author"):
        a = esc(item["author"])
        if item.get("author_url"):
            bits.append(f'<a href="{esc(item["author_url"])}" target="_blank" rel="noopener">{a}</a>')
        else:
            bits.append(a)
    for k in ("published", "views", "duration"):
        if item.get(k):
            bits.append(esc(str(item[k])))
    return '<span class="sep">·</span>'.join(f"<span>{b}</span>" for b in bits)


def render_cluster(c, media=None):
    items = []
    seen = set()
    for it in c.get("items", []):
        cu = canonical_url(it)
        if cu in seen:
            continue
        seen.add(cu)
        items.append(it)
    if not items:
        return ""

    primary = pick_primary(items, media)
    kind, media_html = embed_html(primary, media)
    others = [i for i in items if i is not primary]

    platforms = sorted({i.get("platform", "other") for i in items},
                       key=lambda p: PLATFORM_ORDER.get(p, 9))
    chips = "".join(
        f'<span class="chip p-{esc(p)}">{esc(PLATFORM_LABEL.get(p, p))}</span>' for p in platforms
    )

    also = ""
    if others:
        links = " ".join(
            f'<a href="{esc(o.get("url"))}" target="_blank" rel="noopener" class="alt p-{esc(o.get("platform"))}">'
            f'{esc(PLATFORM_LABEL.get(o.get("platform"), "Web"))}'
            + (f' · {esc(o.get("author"))}' if o.get("author") else "")
            + "</a>"
            for o in others
        )
        also = f'<div class="also"><span class="also-label">Also posted on</span>{links}</div>'

    title = c.get("title") or primary.get("title") or "Untitled"
    return f"""
    <article class="card" data-platforms="{esc(' '.join(platforms))}" data-track="{esc(c.get('track','viral'))}">
      <div class="media">{media_html}</div>
      <div class="body">
        <div class="chips">{chips}</div>
        <h3><a href="{esc(primary.get('url'))}" target="_blank" rel="noopener">{esc(title)}</a></h3>
        <div class="meta">{render_meta(primary)}</div>
        <p class="commentary">{esc(c.get('commentary',''))}</p>
        {also}
      </div>
    </article>"""


def build(data, media=None):
    clusters = data.get("clusters", [])
    viral = [c for c in clusters if c.get("track") != "science"]
    science = [c for c in clusters if c.get("track") == "science"]

    # Newest first by date discovered; within a date, keep the curated order
    # of the JSON file rather than letting id-sorting scramble it.
    order = {id(c): i for i, c in enumerate(clusters)}
    viral.sort(key=lambda c: (c.get("first_seen") or "", -order[id(c)]), reverse=True)
    science.sort(key=lambda c: (c.get("first_seen") or "", -order[id(c)]), reverse=True)

    n_items = sum(len(c.get("items", [])) for c in clusters)
    n_plat = len({i.get("platform") for c in clusters for i in c.get("items", [])})
    updated = data.get("updated") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        u = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        updated_h = u.strftime("%d %b %Y, %H:%M UTC")
    except Exception:
        updated_h = updated

    def section(title, blurb, items, anchor):
        if not items:
            return ""
        cards = "".join(render_cluster(c, media) for c in items)
        return f"""
  <section id="{anchor}">
    <div class="sechead">
      <h2>{esc(title)}</h2>
      <p>{esc(blurb)}</p>
      <span class="count">{len(items)}</span>
    </div>
    <div class="grid">{cards}</div>
  </section>"""

    body = section(
        "The viral wave",
        "Simulations, remixes, and stunts built on the connectome data. Ranked newest first.",
        viral, "viral",
    ) + section(
        "Science and source material",
        "The actual connectome releases, lab visualizations, talks, and explainers the wave is built on.",
        science, "science",
    )

    return TEMPLATE.format(
        body=body,
        updated=esc(updated_h),
        n_clusters=len(clusters),
        n_items=n_items,
        n_plat=n_plat,
        year=datetime.now(timezone.utc).year,
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Fly Connectome Videos</title>
<meta name="description" content="A daily-updated index of fruit fly connectome videos across YouTube, X, and LinkedIn — the viral simulation wave and the science underneath it.">
<meta property="og:title" content="Fly Connectome Videos">
<meta property="og:description" content="Every fruit fly connectome video worth watching, updated daily across YouTube, X, and LinkedIn.">
<meta property="og:type" content="website">
<style>
  :root {{
    color-scheme: dark;
    --bg: #0b0d10;
    --bg-2: #12161b;
    --card: #151a20;
    --line: #232b34;
    --fg: #e8edf2;
    --fg-dim: #97a3b0;
    --fg-faint: #6b7784;
    --accent: #6ee7a8;
    --accent-2: #7cc4ff;
    --yt: #ff4e45;
    --x: #cfd6dd;
    --li: #4aa3e8;
    --radius: 14px;
  }}
  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    font: 16px/1.6 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
    padding: 0 16px env(safe-area-inset-bottom, 0px);
  }}
  a {{ color: inherit; }}
  img {{ max-width: 100%; }}
  .wrap {{ max-width: 1180px; margin: 0 auto; }}

  header {{
    padding: 56px 0 28px;
    border-bottom: 1px solid var(--line);
  }}
  h1 {{
    margin: 0 0 10px;
    font-size: clamp(30px, 5.2vw, 46px);
    line-height: 1.1;
    letter-spacing: -0.025em;
    font-weight: 680;
  }}
  h1 .dot {{ color: var(--accent); }}
  .lede {{
    margin: 0 0 22px;
    max-width: 62ch;
    color: var(--fg-dim);
    font-size: 17px;
  }}
  .stats {{
    display: flex; flex-wrap: wrap; gap: 10px 26px;
    font: 500 13px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--fg-faint);
  }}
  .stats b {{ color: var(--accent); font-weight: 600; }}

  nav {{
    position: sticky; top: env(safe-area-inset-top, 0px); z-index: 20;
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
    padding: 12px 0;
    background: color-mix(in srgb, var(--bg) 88%, transparent);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--line);
  }}
  .filt {{
    appearance: none; cursor: pointer;
    border: 1px solid var(--line); background: var(--bg-2); color: var(--fg-dim);
    border-radius: 999px; padding: 7px 14px;
    font: 500 13px/1 inherit;
    transition: .14s border-color, .14s color, .14s background;
  }}
  .filt:hover {{ color: var(--fg); border-color: #32404e; }}
  .filt[aria-pressed="true"] {{ background: var(--accent); color: #07110b; border-color: var(--accent); }}
  .nav-sp {{ flex: 1 1 auto; }}
  .jump {{ font-size: 13px; color: var(--fg-faint); text-decoration: none; }}
  .jump:hover {{ color: var(--accent-2); }}

  section {{ padding: 44px 0 8px; }}
  .sechead {{ position: relative; margin-bottom: 26px; padding-right: 54px; }}
  .sechead h2 {{
    margin: 0 0 6px; font-size: 24px; letter-spacing: -0.015em; font-weight: 640;
  }}
  .sechead p {{ margin: 0; color: var(--fg-dim); font-size: 15px; max-width: 64ch; }}
  .count {{
    position: absolute; right: 0; top: 0;
    font: 600 13px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--accent); border: 1px solid var(--line);
    border-radius: 999px; padding: 6px 11px;
  }}

  .grid {{
    display: grid; gap: 22px;
    grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  }}
  .card {{
    display: flex; flex-direction: column;
    background: var(--card); border: 1px solid var(--line);
    border-radius: var(--radius); overflow: hidden;
    transition: .16s border-color, .16s transform;
  }}
  .card:hover {{ border-color: #33414f; }}
  .card[hidden] {{ display: none !important; }}

  .media {{ background: #0e1216; border-bottom: 1px solid var(--line); }}
  .facade {{
    position: relative; aspect-ratio: 16/9; cursor: pointer;
    display: block; overflow: hidden;
  }}
  .facade img {{ width: 100%; height: 100%; object-fit: cover; display: block; transition: .3s transform, .2s opacity; }}
  .facade:hover img {{ transform: scale(1.035); opacity: .85; }}
  .facade .play {{
    position: absolute; inset: 0; margin: auto;
    width: 62px; height: 44px; border-radius: 11px;
    background: rgba(12,15,18,.74); border: 1px solid rgba(255,255,255,.18);
    transition: .16s background;
  }}
  .facade .play::after {{
    content: ""; position: absolute; inset: 0; margin: auto;
    width: 0; height: 0;
    border-left: 15px solid #fff;
    border-top: 9px solid transparent; border-bottom: 9px solid transparent;
    transform: translateX(2px);
  }}
  .facade:hover .play {{ background: var(--yt); }}
  .facade-yt iframe {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }}
  .facade.nothumb {{ background: linear-gradient(135deg,#16202a,#0e1216); }}
  .facade.nothumb img {{ display: none; }}

  /* X / LinkedIn native video: poster letterboxed (many clips are vertical),
     click swaps in a <video> playing the platform's own MP4. */
  .facade-vid {{ background: #000; }}
  .facade-vid img {{ object-fit: contain; }}
  .facade-vid:hover .play {{ background: var(--accent); }}
  .facade-vid iframe {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: #000; }}
  .facade .vplat {{
    position: absolute; left: 10px; top: 10px; padding: 4px 7px; border-radius: 6px;
    font: 600 10.5px/1 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .04em;
    color: #fff; background: rgba(12,15,18,.74); border: 1px solid rgba(255,255,255,.18);
  }}
  .facade-vid.loaded .vplat {{ display: none; }}
  .vfail-msg {{
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    padding: 16px; text-align: center; font-size: 13px; color: var(--fg-faint);
  }}
  .vfail-msg a {{ color: var(--accent-2); text-decoration: none; font-weight: 500; }}

  /* Text facade for X / LinkedIn: the post itself is readable immediately,
     the rich embed loads on click. A blocked frame never leaves a blank box. */
  .facade-text {{
    display: flex; flex-direction: column; justify-content: space-between;
    min-height: 190px; cursor: pointer; position: relative;
  }}
  .facade-text .fq {{ padding: 16px 18px 10px; }}
  .facade-text .fwho {{
    font-size: 13px; font-weight: 600; color: var(--fg); margin-bottom: 7px;
    display: flex; flex-direction: column; gap: 1px;
  }}
  .facade-text .frole {{ font-weight: 400; font-size: 11.5px; color: var(--fg-faint); }}
  .facade-text p {{
    margin: 0; font-size: 13.5px; line-height: 1.55; color: var(--fg-dim);
  }}
  .facade-text .fsub {{
    margin-top: 9px;
    font: 500 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--fg-faint);
  }}
  .floadbar {{
    display: block; padding: 9px 18px;
    border-top: 1px solid var(--line);
    font: 600 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
    letter-spacing: .05em; text-transform: uppercase; color: var(--fg-faint);
    transition: .15s color, .15s background;
  }}
  .floadbar::before {{ content: "\\25b8  "; }}
  .facade-text:hover .floadbar {{ color: var(--accent); background: #101519; }}
  .facade-text.loaded {{ cursor: default; min-height: 0; display: block; }}
  .facade-text.loaded iframe {{ display: block; border: 0; width: 100%; background: #0e1216; }}
  .facade-text.loaded .twitter-tweet {{ margin: 6px auto !important; }}
  .embed-fail {{
    margin: 0; padding: 14px 18px; font-size: 12.5px; color: var(--fg-faint);
    border-top: 1px solid var(--line);
  }}
  .embed-fail a {{ color: var(--accent-2); text-decoration: none; font-weight: 500; }}
  .embed-fail a:hover {{ text-decoration: underline; }}
  .embed-fail span {{ opacity: .6; }}
  .textcard {{ padding: 18px 18px 16px; }}
  .textcard p {{ margin: 0 0 12px; color: var(--fg-dim); font-size: 14px; }}
  .out {{ font-size: 13px; color: var(--accent-2); text-decoration: none; }}
  .out:hover {{ text-decoration: underline; }}

  .body {{ padding: 16px 18px 18px; display: flex; flex-direction: column; gap: 9px; flex: 1; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .chip {{
    font: 600 10.5px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
    letter-spacing: .07em; text-transform: uppercase;
    padding: 4px 8px; border-radius: 5px;
    border: 1px solid var(--line); color: var(--fg-faint);
  }}
  .chip.p-youtube {{ color: var(--yt); border-color: color-mix(in srgb, var(--yt) 38%, transparent); }}
  .chip.p-x {{ color: var(--x); border-color: #3a444f; }}
  .chip.p-linkedin {{ color: var(--li); border-color: color-mix(in srgb, var(--li) 38%, transparent); }}

  .card h3 {{ margin: 0; font-size: 16.5px; line-height: 1.34; font-weight: 600; letter-spacing: -0.008em; }}
  .card h3 a {{ text-decoration: none; }}
  .card h3 a:hover {{ color: var(--accent-2); }}
  .meta {{ font-size: 12.5px; color: var(--fg-faint); display: flex; flex-wrap: wrap; gap: 5px; align-items: baseline; }}
  .meta a {{ color: var(--fg-dim); text-decoration: none; }}
  .meta a:hover {{ color: var(--accent-2); }}
  .meta .sep {{ opacity: .45; }}
  .commentary {{
    margin: 2px 0 0; font-size: 14.5px; color: var(--fg-dim);
    border-left: 2px solid var(--line); padding-left: 12px;
  }}
  .also {{
    margin-top: auto; padding-top: 12px; border-top: 1px dashed var(--line);
    display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline;
  }}
  .also-label {{
    font: 600 10px/1 ui-monospace, Menlo, monospace; letter-spacing: .08em;
    text-transform: uppercase; color: var(--fg-faint); margin-right: 2px;
  }}
  .alt {{
    font-size: 12.5px; text-decoration: none; color: var(--fg-dim);
    border: 1px solid var(--line); border-radius: 6px; padding: 3px 8px;
  }}
  .alt:hover {{ border-color: #3a4854; color: var(--fg); }}

  footer {{
    margin-top: 56px; padding: 26px 0 44px;
    border-top: 1px solid var(--line);
    color: var(--fg-faint); font-size: 13px;
  }}
  footer a {{ color: var(--fg-dim); }}
  .empty {{ color: var(--fg-faint); font-size: 14px; padding: 30px 0; }}

  @media (max-width: 560px) {{
    header {{ padding-top: 36px; }}
    .grid {{ grid-template-columns: 1fr; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; }}
  }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>Fly connectome videos<span class="dot">.</span></h1>
  <p class="lede">Everything people are making with the fruit fly connectome — the viral simulation
  wave and the science it came from — collected daily from YouTube, X, and LinkedIn, deduplicated
  across platforms, and annotated.</p>
  <div class="stats">
    <span><b>{n_clusters}</b> entries</span>
    <span><b>{n_items}</b> posts</span>
    <span><b>{n_plat}</b> platforms</span>
    <span>updated <b>{updated}</b></span>
  </div>
</header>

<nav aria-label="Filter by platform">
  <button class="filt" data-f="all" aria-pressed="true">All</button>
  <button class="filt" data-f="youtube" aria-pressed="false">YouTube</button>
  <button class="filt" data-f="x" aria-pressed="false">X</button>
  <button class="filt" data-f="linkedin" aria-pressed="false">LinkedIn</button>
  <span class="nav-sp"></span>
  <a class="jump" href="#viral">Viral</a>
  <a class="jump" href="#science">Science</a>
</nav>

{body}

<footer>
  <p>Rebuilt daily. Commentary is editorial; embeds and links point to the original creators.
  Nothing here is hosted locally — every video plays from its own platform.</p>
  <p>Source: <a href="https://github.com/honicky/fly-connectome-videos">honicky/fly-connectome-videos</a> · &copy; {year}</p>
</footer>

</div>

<script>
// Every embed is click-to-load. Dozens of live third-party frames would make
// the page slow, and a blocked frame would leave a blank box with no way out.
document.addEventListener('click', function (e) {{
  var f = e.target.closest && e.target.closest('.facade:not(.loaded)');
  if (f) activate(f);
}});
document.addEventListener('keydown', function (e) {{
  if (e.key !== 'Enter' && e.key !== ' ') return;
  var f = e.target.closest && e.target.closest('.facade:not(.loaded)');
  if (!f) return;
  e.preventDefault();
  activate(f);
}});

function escapeAttr(s) {{ return String(s).replace(/"/g, '&quot;'); }}
function escapeHtml(s) {{
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}}

// Called from inside a native-video frame when no source could play.
window.videoFailed = function (ifr) {{
  var f = ifr && ifr.closest('.facade');
  if (!f) return;
  f.innerHTML = '<div class="vfail-msg"><a href="' + escapeAttr(f.getAttribute('data-url')) +
    '" target="_blank" rel="noopener">Video could not play here. Watch on ' +
    (f.getAttribute('data-plat') || 'the web') + ' \\u2197</a></div>';
}};

// Always leave a way through: if the frame is blocked by a tracking blocker,
// a sandbox, or the post going private, this link still works.
function addFallback(f) {{
  var url = f.getAttribute('data-url');
  if (!url) return;
  var p = document.createElement('p');
  p.className = 'embed-fail';
  p.innerHTML = '<a href="' + escapeAttr(url) +
                '" target="_blank" rel="noopener">View on ' +
                (f.getAttribute('data-plat') || 'the web') + ' \\u2197</a>' +
                '<span> \\u00b7 if the embed is blocked, this link still works</span>';
  f.appendChild(p);
}}

function activate(f) {{
  if (f.dataset.yt) {{
    var id = f.dataset.yt;
    f.removeAttribute('data-yt');
    var ifr = document.createElement('iframe');
    ifr.src = 'https://www.youtube-nocookie.com/embed/' + id + '?autoplay=1&rel=0';
    ifr.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; picture-in-picture';
    ifr.allowFullscreen = true;
    ifr.title = 'YouTube video player';
    f.classList.add('loaded');
    f.innerHTML = '';
    f.appendChild(ifr);
    return;
  }}

  if (f.dataset.vsrc) {{
    // The <video> lives in a same-origin srcdoc frame whose only job is to
    // send no Referer: video.twimg.com answers 403 to any Referer that is not
    // X's own, but serves requests without one. A page-wide no-referrer policy
    // is not an option because YouTube embeds need the Referer.
    var srcs = JSON.parse(f.dataset.vsrc);
    f.removeAttribute('data-vsrc');
    var poster = f.getAttribute('data-poster');
    var gif = f.dataset.gif === '1';
    var doc = '<!doctype html><meta name="referrer" content="no-referrer">' +
      '<style>html,body{{margin:0;height:100%;background:#000;overflow:hidden}}' +
      'video{{display:block;width:100%;height:100%}}</style>' +
      '<video controls autoplay playsinline' + (gif ? ' loop muted' : '') +
      (poster ? ' poster="' + escapeHtml(poster) + '"' : '') + '>' +
      srcs.map(function (u) {{ return '<source type="video/mp4" src="' + escapeHtml(u) + '">'; }}).join('') +
      '</video><script>' +
      // Last <source> failing means none could play (deleted post, hotlink
      // refused, blocker): the parent swaps in a link instead of a black box.
      'var s=document.querySelectorAll("source");' +
      'if(s.length)s[s.length-1].addEventListener("error",function(){{parent.videoFailed(frameElement)}});' +
      '<\\/script>';
    var ifr = document.createElement('iframe');
    ifr.setAttribute('allow', 'autoplay; fullscreen; picture-in-picture');
    ifr.allowFullscreen = true;
    ifr.title = (f.getAttribute('data-plat') || '') + ' video';
    ifr.srcdoc = doc;
    f.classList.add('loaded');
    f.innerHTML = '';
    f.appendChild(ifr);
    return;
  }}

  if (f.dataset.li) {{
    var urn = f.dataset.li;
    f.removeAttribute('data-li');
    var li = document.createElement('iframe');
    li.src = 'https://www.linkedin.com/embed/feed/update/' + urn;
    li.height = 560; li.width = '100%';
    li.frameBorder = 0; li.allowFullscreen = true;
    li.title = 'LinkedIn post';
    f.classList.add('loaded');
    f.innerHTML = '';
    f.appendChild(li);
    addFallback(f);
    return;
  }}

  if (f.dataset.x) {{
    var sid = f.dataset.x;
    f.removeAttribute('data-x');
    f.classList.add('loaded');
    f.innerHTML = '';
    var host = document.createElement('div');
    f.appendChild(host);
    addFallback(f);
    loadTwitter(function () {{
      if (window.twttr && window.twttr.widgets) {{
        window.twttr.widgets.createTweet(sid, host,
          {{ theme: 'dark', dnt: true, conversation: 'none' }});
      }}
    }});
  }}
}}

// Load widgets.js once, on first use, and queue callers until it is ready.
function loadTwitter(cb) {{
  if (window.twttr && window.twttr.widgets) {{ cb(); return; }}
  if (!window.__twQ) {{
    window.__twQ = [];
    var s = document.createElement('script');
    s.src = 'https://platform.twitter.com/widgets.js';
    s.charset = 'utf-8';
    s.onload = function () {{
      var q = window.__twQ; window.__twQ = null;
      q.forEach(function (fn) {{ fn(); }});
    }};
    s.onerror = function () {{ window.__twQ = null; }};
    document.head.appendChild(s);
  }}
  if (window.__twQ) {{ window.__twQ.push(cb); }} else {{ cb(); }}
}}

// Platform filter
var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
var btns = Array.prototype.slice.call(document.querySelectorAll('.filt'));
btns.forEach(function (b) {{
  b.addEventListener('click', function () {{
    var f = b.getAttribute('data-f');
    btns.forEach(function (o) {{ o.setAttribute('aria-pressed', String(o === b)); }});
    cards.forEach(function (c) {{
      c.hidden = !(f === 'all' || (c.dataset.platforms || '').split(' ').indexOf(f) !== -1);
    }});
    document.querySelectorAll('section').forEach(function (s) {{
      var vis = s.querySelectorAll('.card:not([hidden])').length;
      s.hidden = vis === 0;
      var c = s.querySelector('.count');
      if (c) c.textContent = vis;
    }});
  }});
}});
</script>
</body>
</html>
"""


def main():
    if not os.path.exists(DATA):
        print(f"no data file at {DATA}", file=sys.stderr)
        return 1
    with open(DATA, encoding="utf-8") as fh:
        data = json.load(fh)

    # Global dedup guard: the same platform post must not appear in two clusters.
    seen, dupes = {}, []
    for c in data.get("clusters", []):
        for it in c.get("items", []):
            cu = canonical_url(it)
            if cu in seen and seen[cu] != c["id"]:
                dupes.append((cu, seen[cu], c["id"]))
            seen[cu] = c["id"]
    if dupes:
        for cu, a, b in dupes:
            print(f"WARN duplicate {cu} in clusters {a} and {b}", file=sys.stderr)

    media = {}
    if os.path.exists(MEDIA):  # optional: written by tools/fetch_media.py
        with open(MEDIA, encoding="utf-8") as fh:
            media = json.load(fh)
    out = build(data, media)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"wrote {OUT} — {len(data.get('clusters', []))} clusters, "
          f"{len(seen)} unique posts, {len(dupes)} dup warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
