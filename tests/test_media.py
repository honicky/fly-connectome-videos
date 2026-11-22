"""Unit tests for X/LinkedIn video resolution and rendering.

  python3 -m unittest discover -s tests -q
Offline: no network calls.
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

_spec = importlib.util.spec_from_file_location("fetch_media", os.path.join(ROOT, "tools", "fetch_media.py"))
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)


def x_payload(media):
    return {"__typename": "Tweet", "mediaDetails": media}


class TokenTest(unittest.TestCase):
    def test_token_shape(self):
        t = fm.x_token("2111589148146749616")
        self.assertTrue(t)
        self.assertNotIn("0", t)
        self.assertNotIn(".", t)
        self.assertEqual(t, fm.x_token("2111589148146749616"))  # deterministic

    def test_b36_matches_js(self):
        # (255.5).toString(36) === "73.i" in JavaScript
        self.assertTrue(fm._b36(255.5).startswith("73.i"))


class ParseXTest(unittest.TestCase):
    def test_video_variants_sorted_and_capped(self):
        p = x_payload([{"type": "video", "media_url_https": "https://pbs.twimg.com/p.jpg",
                        "video_info": {"aspect_ratio": [16, 9], "variants": [
                            {"content_type": "application/x-mpegURL", "url": "https://v/pl.m3u8"},
                            {"content_type": "video/mp4", "bitrate": 10368000, "url": "https://v/1080.mp4"},
                            {"content_type": "video/mp4", "bitrate": 256000, "url": "https://v/270.mp4"},
                            {"content_type": "video/mp4", "bitrate": 2176000, "url": "https://v/720.mp4"}]}}])
        r = fm.parse_x(p)
        self.assertEqual(r["status"], "ok")
        self.assertEqual([s["url"] for s in r["sources"]], ["https://v/270.mp4", "https://v/720.mp4"])
        self.assertEqual(r["aspect"], [16, 9])
        self.assertFalse(r["gif"])

    def test_only_high_bitrate_keeps_one(self):
        p = x_payload([{"type": "video", "video_info": {"variants": [
            {"content_type": "video/mp4", "bitrate": 9_000_000, "url": "https://v/a.mp4"}]}}])
        self.assertEqual(len(fm.parse_x(p)["sources"]), 1)

    def test_photo_only_is_novideo(self):
        self.assertEqual(fm.parse_x(x_payload([{"type": "photo"}]))["status"], "novideo")
        self.assertEqual(fm.parse_x({})["status"], "novideo")


class ParseLinkedInTest(unittest.TestCase):
    def test_native_video(self):
        srcs = json.dumps([{"src": "https://dms/720.mp4", "type": "video/mp4", "data-bitrate": 338875},
                           {"src": "https://dms/640.mp4", "type": "video/mp4", "data-bitrate": 252697}])
        page = (f'<video data-sources="{srcs.replace(chr(34), "&quot;")}" '
                f'data-poster-url="https://media/p.jpg?e=1&amp;v=beta"></video>')
        r = fm.parse_linkedin(page)
        self.assertEqual(r["status"], "ok")
        self.assertEqual([s["url"] for s in r["sources"]], ["https://dms/640.mp4", "https://dms/720.mp4"])
        self.assertEqual(r["poster"], "https://media/p.jpg?e=1&v=beta")

    def test_linked_youtube(self):
        page = '<iframe data-delayed-url="https://www.youtube-nocookie.com/embed/cwTjgTfiMGc?rel=0"></iframe>'
        self.assertEqual(fm.parse_linkedin(page), {"status": "ok", "youtube": "cwTjgTfiMGc"})

    def test_text_post(self):
        self.assertEqual(fm.parse_linkedin("<p>just text</p>")["status"], "novideo")


class MediaKeyTest(unittest.TestCase):
    def test_keys_match_build_identity(self):
        x = {"platform": "x", "url": "https://x.com/a/status/123456"}
        li = {"platform": "linkedin", "url": "https://www.linkedin.com/feed/update/urn:li:activity:7522664575549476864/"}
        for it in (x, li):
            self.assertEqual(fm.media_key(it), build.canonical_url(it))


class RenderTest(unittest.TestCase):
    X = {"platform": "x", "url": "https://x.com/a/status/42", "author": "@a", "text": "hi"}
    LI = {"platform": "linkedin", "url": "https://www.linkedin.com/feed/update/urn:li:activity:7522664575549476864/",
          "author": "B", "text": "post"}
    MEDIA = {"x:42": {"status": "ok", "poster": "https://p.jpg",
                      "sources": [{"url": "https://v/a.mp4", "bitrate": 1}, {"url": "https://v/b.mp4", "bitrate": 2}]},
             "linkedin:7522664575549476864": {"status": "ok", "youtube": "cwTjgTfiMGc"}}

    def test_x_with_media_renders_native_video(self):
        kind, h = build.embed_html(self.X, self.MEDIA)
        self.assertEqual(kind, "video")
        self.assertIn("facade-vid", h)
        # highest bitrate first
        self.assertLess(h.index("b.mp4"), h.index("a.mp4"))

    def test_x_without_media_falls_back_to_text(self):
        _, h = build.embed_html(self.X, {})
        self.assertIn("facade-text", h)
        _, h = build.embed_html(self.X, {"x:42": {"status": "novideo"}})
        self.assertIn("facade-text", h)

    def test_linkedin_linked_youtube_uses_youtube_facade(self):
        _, h = build.embed_html(self.LI, self.MEDIA)
        self.assertIn('data-yt="cwTjgTfiMGc"', h)

    def test_primary_prefers_playable(self):
        x_novid = dict(self.X, url="https://x.com/a/status/7")
        self.assertIs(build.pick_primary([x_novid, self.LI], self.MEDIA), self.LI)
        self.assertIs(build.pick_primary([x_novid, self.LI], {}), x_novid)  # old order without media

    def test_full_page_builds(self):
        page = build.build({"clusters": [{"id": "c", "track": "viral", "title": "T", "commentary": "C",
                                          "first_seen": "2026-11-22", "items": [self.X]}]}, self.MEDIA)
        self.assertIn("facade-vid", page)
        self.assertIn("no-referrer", page)  # X's video host 403s foreign Referers


if __name__ == "__main__":
    unittest.main()
