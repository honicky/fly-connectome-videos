#!/usr/bin/env python3
"""Resolve playable video for X and LinkedIn posts into data/media.json.

build.py uses the cache to render X/LinkedIn cards as a poster + native
<video> player (click to play), like YouTube cards, instead of a text card.
No login needed:

  X         cdn.syndication.twimg.com/tweet-result  (the endpoint behind
            X's own embed widget) -> poster + MP4 variants on video.twimg.com
  LinkedIn  linkedin.com/embed/feed/update/<urn>    (public embed page)
            -> poster + MP4 sources on dms.licdn.com (signed, e=2147483647,
            i.e. no expiry)

Only posts not already cached are fetched, so a daily run makes a handful of
requests. Posts without a video are cached as {"status": "novideo"} and not
retried; network/parse failures are cached as "error" and retried next run.

  python3 tools/fetch_media.py            # fill in missing entries
  python3 tools/fetch_media.py --refresh  # re-fetch everything
  python3 tools/fetch_media.py --retry-novideo  # re-check posts cached as "novideo"
Standard library only. Never fails the publish: exits 0 unless items.json
itself is unreadable.
"""
import html, json, math, os, re, sys, time, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.json")
CACHE = os.path.join(ROOT, "data", "media.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
X_STATUS = re.compile(r"(?:twitter|x)\.com/[^/]+/status/(\d+)")
LI_ACTIVITY = re.compile(r"activity[-:](\d{10,25})")
MAX_BITRATE = 2_200_000  # skip 1080p variants: 720p is plenty in a card


def _b36(x, frac_digits=12):
    """JavaScript Number.prototype.toString(36) for a positive float."""
    d = "0123456789abcdefghijklmnopqrstuvwxyz"
    ip, fp = int(x), x - int(x)
    s = ""
    while ip:
        s, ip = d[ip % 36] + s, ip // 36
    f = ""
    for _ in range(frac_digits):
        fp *= 36
        k = int(fp)
        f, fp = f + d[k], fp - k
    return (s or "0") + "." + f


def x_token(status_id):
    """Token the syndication endpoint expects (same formula as X's embed code)."""
    return _b36(int(status_id) / 1e15 * math.pi).replace("0", "").replace(".", "")


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def pick_variants(variants):
    """MP4 variants sorted low->high bitrate, capped at MAX_BITRATE (keep at least one)."""
    mp4 = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
    mp4.sort(key=lambda v: v.get("bitrate") or 0)
    capped = [v for v in mp4 if (v.get("bitrate") or 0) <= MAX_BITRATE]
    return [{"url": v["url"], "bitrate": v.get("bitrate") or 0} for v in (capped or mp4[:1])]


def parse_x(payload):
    md = [m for m in (payload.get("mediaDetails") or []) if m.get("type") in ("video", "animated_gif")]
    if not md:
        return {"status": "novideo"}
    m = md[0]
    srcs = pick_variants((m.get("video_info") or {}).get("variants") or [])
    if not srcs:
        return {"status": "novideo"}
    ar = (m.get("video_info") or {}).get("aspect_ratio") or []
    out = {"status": "ok", "poster": m.get("media_url_https", ""), "sources": srcs,
           "gif": m.get("type") == "animated_gif"}
    if len(ar) == 2 and ar[0] and ar[1]:
        out["aspect"] = [ar[0], ar[1]]
    return out


def parse_linkedin(page):
    srcs = re.search(r'data-sources="([^"]+)"', page)
    if not srcs:
        # Post that links an external YouTube video: LinkedIn embeds it via youtube-nocookie.
        yt = re.search(r'youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]{11})', page)
        return {"status": "ok", "youtube": yt.group(1)} if yt else {"status": "novideo"}
    try:
        lst = json.loads(html.unescape(srcs.group(1)))
    except ValueError:
        return {"status": "error", "error": "bad data-sources"}
    lst = [{"url": s["src"], "bitrate": s.get("data-bitrate") or 0}
           for s in lst if s.get("src") and "mp4" in (s.get("type") or "")]
    if not lst:
        return {"status": "novideo"}
    lst.sort(key=lambda s: s["bitrate"])
    poster = re.search(r'(?:data-poster-url|poster)="([^"]+)"', page)
    return {"status": "ok", "poster": html.unescape(poster.group(1)) if poster else "", "sources": lst}


def fetch_x(sid):
    u = f"https://cdn.syndication.twimg.com/tweet-result?id={sid}&lang=en&token={x_token(sid)}"
    return parse_x(json.loads(_get(u)))


def fetch_linkedin(activity_id):
    page = _get(f"https://www.linkedin.com/embed/feed/update/urn:li:activity:{activity_id}")
    return parse_linkedin(page.decode("utf-8", "replace"))


def media_key(item):
    """Cache key: same identity build.py uses for dedup (x:<id>, linkedin:<id>)."""
    url = item.get("url") or ""
    if item.get("platform") == "x":
        m = X_STATUS.search(url)
        return f"x:{m.group(1)}" if m else None
    if item.get("platform") == "linkedin":
        m = LI_ACTIVITY.search(item.get("urn") or "") or LI_ACTIVITY.search(url)
        return f"linkedin:{m.group(1)}" if m else None
    return None


def main():
    refresh = "--refresh" in sys.argv
    items = json.load(open(ITEMS))
    try:
        cache = json.load(open(CACHE))
    except (OSError, ValueError):
        cache = {}
    keys = []
    for c in items["clusters"]:
        for it in c["items"]:
            k = media_key(it)
            if k and k not in keys:
                keys.append(k)
    retry_li_novideo = "--retry-novideo" in sys.argv
    todo = [k for k in keys if refresh or cache.get(k, {}).get("status") not in ("ok", "novideo")
            or (retry_li_novideo and cache[k]["status"] == "novideo")]
    counts = {"ok": 0, "novideo": 0, "error": 0}
    for i, k in enumerate(todo):
        plat, ident = k.split(":", 1)
        try:
            res = fetch_x(ident) if plat == "x" else fetch_linkedin(ident)
        except Exception as e:  # network, HTTP 404 for deleted posts, bad JSON
            res = {"status": "error", "error": str(e)[:200]}
        res["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cache[k] = res
        counts[res["status"]] = counts.get(res["status"], 0) + 1
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(todo)} …", flush=True)
        time.sleep(0.4)
    tmp = CACHE + ".tmp"
    json.dump(dict(sorted(cache.items())), open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, CACHE)
    have = sum(1 for k in keys if cache.get(k, {}).get("status") == "ok")
    print(f"media: fetched {len(todo)} ({counts['ok']} video, {counts['novideo']} no video, "
          f"{counts['error']} errors); {have}/{len(keys)} X/LinkedIn posts have playable video", flush=True)


if __name__ == "__main__":
    main()
