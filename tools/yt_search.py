#!/usr/bin/env python3
"""YouTube search for the fly-connectome index, without a browser.

Fetches YouTube's public search results page for each query, pulls the
embedded ytInitialData JSON, and prints one JSON object per unique video:
  {"id","q","title","ch","chUrl","pub","views","len","desc"}
Same fields as the old in-page innertube extractor. Standard library only.

  python3 tools/yt_search.py              # default queries
  python3 tools/yt_search.py "query" ...  # custom queries
"""
import json, re, sys, time, urllib.parse, urllib.request

QUERIES = ["fly connectome", "fruit fly brain simulation", "MaleCNS fly brain",
           "flywire connectome", "fly brain bad apple", "fruit fly brain video game",
           "drosophila connectome visualization", "fly brain neural simulation"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def text(o):
    if not o: return ""
    if "simpleText" in o: return o["simpleText"]
    return "".join(r.get("text", "") for r in o.get("runs", []))

def fetch(q):
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": q, "hl": "en", "gl": "US"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                                               "Cookie": "CONSENT=YES+1"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S) \
        or re.search(r"ytInitialData\"?\]?\s*=\s*(\{.*?\});", html, re.S)
    if not m: raise RuntimeError("ytInitialData not found (consent page or layout change?)")
    return json.loads(m.group(1))

def walk(o, out, d=0):
    if d > 20: return
    if isinstance(o, dict):
        if "videoRenderer" in o: out.append(o["videoRenderer"])
        for v in o.values(): walk(v, out, d + 1)
    elif isinstance(o, list):
        for v in o: walk(v, out, d + 1)

def ch_url(v):
    try:
        ne = v["ownerText"]["runs"][0]["navigationEndpoint"]
    except (KeyError, IndexError, TypeError):
        return ""
    u = ne.get("commandMetadata", {}).get("webCommandMetadata", {}).get("url")
    if u: return u
    bid = ne.get("browseEndpoint", {}).get("browseId")
    return "/channel/" + bid if bid else ""

def main():
    qs = sys.argv[1:] or QUERIES
    seen, n, errors = set(), 0, 0
    for q in qs:
        try:
            data = fetch(q)
        except Exception as e:
            errors += 1
            print(json.dumps({"id": "", "q": q, "error": str(e)}), flush=True)
            continue
        found = []
        walk(data, found)
        for v in found:
            vid = v.get("videoId")
            if not vid or vid in seen: continue
            seen.add(vid); n += 1
            snip = v.get("detailedMetadataSnippets") or [{}]
            print(json.dumps({
                "id": vid, "q": q, "title": text(v.get("title")),
                "ch": text(v.get("ownerText")), "chUrl": ch_url(v),
                "pub": text(v.get("publishedTimeText")), "views": text(v.get("viewCountText")),
                "len": text(v.get("lengthText")),
                "desc": text(snip[0].get("snippetText"))[:260],
            }, ensure_ascii=False), flush=True)
        time.sleep(1)
    print(json.dumps({"summary": {"videos": n, "queries": len(qs), "failed_queries": errors}}), file=sys.stderr)
    sys.exit(1 if errors == len(qs) else 0)

if __name__ == "__main__":
    main()
