#!/usr/bin/env python3
"""
Technical self-audit for the pill page (stdlib only).

Checks the things that quietly cap rankings and that the rank/content
patrols can observe but not explain:

  - HTTP status + redirect (the ranking URL should answer 200 directly)
  - canonical tag (must self-reference the pill page, else Google may
    consolidate signals onto another URL -> cannibalisation / wrong page)
  - meta robots (accidental noindex/nofollow)
  - structured data (JSON-LD @types; FAQPage unlocks FAQ rich results,
    Product/Offer unlocks price snippets, MedicalWebPage helps E-E-A-T)
  - single H1
  - internal links: how many anchors on our hub pages point at the pill
    page (weak internal linking starves it of authority and is the usual
    root cause of wrong-page routing)

Each check returns pass/warn/fail + evidence. A network failure on any
fetch degrades that check to a warn -- the audit never raises.

Run `python tech_audit.py --test` for an offline self-test.
"""
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

PILL_PAGE = "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/"
# Hub pages that should be funnelling internal links to the pill page.
HUB_PAGES = [
    "https://www.simpleonlinepharmacy.co.uk/",
    "https://www.simpleonlinepharmacy.co.uk/weight-loss/",
]
WANT_SCHEMA = ("FAQPage", "Product", "MedicalWebPage")


def fetch(url: str, timeout: int = 25):
    """Return (status, final_url, html). Raises on network failure."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", "replace")


class _Head(HTMLParser):
    """Pull canonical, meta robots, JSON-LD blobs, H1 count and anchors."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonical = ""
        self.robots = ""
        self.jsonld = []
        self.h1 = 0
        self.hrefs = []
        self._in_ld = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = (a.get("href") or "").strip()
        elif tag == "meta" and (a.get("name") or "").lower() == "robots":
            self.robots = (a.get("content") or "").lower()
        elif tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_ld = True
            self._buf = []
        elif tag == "h1":
            self.h1 += 1
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])

    def handle_data(self, data):
        if self._in_ld:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self._in_ld = False
            self.jsonld.append("".join(self._buf))


def _schema_types(blobs) -> set:
    types = set()

    def walk(x):
        if isinstance(x, dict):
            t = x.get("@type")
            if isinstance(t, str):
                types.add(t)
            elif isinstance(t, list):
                types.update(str(i) for i in t)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for blob in blobs:
        try:
            walk(json.loads(blob))
        except (json.JSONDecodeError, TypeError):
            continue
    return types


def _norm(u: str) -> str:
    return (u or "").split("#")[0].split("?")[0].rstrip("/").lower()


def run(pill_url: str = PILL_PAGE, hub_pages=None,
        fetch_fn=fetch) -> dict:
    """Return {"checks": [...], "score": pass-count} -- never raises."""
    hubs = HUB_PAGES if hub_pages is None else hub_pages
    checks = []

    def add(name, state, evidence):
        checks.append({"name": name, "state": state, "evidence": evidence[:140]})

    # -- the pill page itself ------------------------------------------------
    try:
        status, final, html = fetch_fn(pill_url)
        p = _Head()
        p.feed(html)

        if status == 200 and _norm(final) == _norm(pill_url):
            add("HTTP status", "pass", f"200 OK, no redirect ({final})")
        elif status == 200:
            add("HTTP status", "warn", f"200 via redirect -> {final}")
        else:
            add("HTTP status", "fail", f"HTTP {status} -> {final}")

        if not p.canonical:
            add("Canonical tag", "warn", "no canonical tag found")
        elif _norm(p.canonical) == _norm(pill_url):
            add("Canonical tag", "pass", f"self-referencing ({p.canonical})")
        else:
            add("Canonical tag", "fail",
                f"points elsewhere: {p.canonical} -- signals consolidate off-page")

        if "noindex" in p.robots or "nofollow" in p.robots:
            add("Meta robots", "fail", f"'{p.robots}' -- page is telling Google to ignore it")
        else:
            add("Meta robots", "pass", p.robots or "not set (indexable)")

        types = _schema_types(p.jsonld)
        missing = [t for t in WANT_SCHEMA if t not in types]
        if not missing:
            add("Structured data", "pass", f"has {', '.join(sorted(types & set(WANT_SCHEMA)))}")
        elif len(missing) < len(WANT_SCHEMA):
            add("Structured data", "warn",
                f"has {', '.join(sorted(types & set(WANT_SCHEMA))) or 'some'}; "
                f"missing {', '.join(missing)}")
        else:
            add("Structured data", "fail",
                f"none of {', '.join(WANT_SCHEMA)} -- no rich-result eligibility")

        if p.h1 == 1:
            add("H1 count", "pass", "exactly one H1")
        else:
            add("H1 count", "warn", f"{p.h1} H1 tags")
    except Exception as e:
        add("Pill page fetch", "warn", f"unreachable from runner: {e}")

    # -- internal links from hub pages ----------------------------------------
    target = _norm(pill_url)
    total, reached = 0, 0
    for hub in hubs:
        try:
            _, _, html = fetch_fn(hub)
            hp = _Head()
            hp.feed(html)
            total += sum(1 for h in hp.hrefs if _norm(h).endswith(target.split("/")[-1])
                         or target in _norm(h))
            reached += 1
        except Exception:
            continue
    if reached == 0:
        add("Internal links", "warn", "hub pages unreachable from runner")
    elif total == 0:
        add("Internal links", "fail",
            f"0 links to pill page across {reached} hub page(s) -- page is orphaned from hubs")
    elif total < 2:
        add("Internal links", "warn", f"only {total} hub link(s) to pill page")
    else:
        add("Internal links", "pass", f"{total} links from {reached} hub page(s)")

    return {"checks": checks,
            "score": sum(1 for c in checks if c["state"] == "pass"),
            "of": len(checks)}


# ---------------------------------------------------------------------------
FIXTURE_HTML = """<html><head>
<link rel="canonical" href="https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}</script>
</head><body><h1>Wegovy pill UK</h1>
<a href="/weight-loss/wegovy-pill/">Wegovy pill</a></body></html>"""

FIXTURE_HUB = """<html><body>
<a href="/weight-loss/wegovy-pill/">pill</a>
<a href="https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/">pill again</a>
</body></html>"""


def _fixture_fetch(url, timeout=25):
    if "wegovy-pill" in url:
        return 200, url, FIXTURE_HTML
    return 200, url, FIXTURE_HUB


if __name__ == "__main__":
    if "--test" in sys.argv:
        out = run(fetch_fn=_fixture_fetch)
        assert out["of"] >= 6, out
        by = {c["name"]: c["state"] for c in out["checks"]}
        assert by["HTTP status"] == "pass"
        assert by["Canonical tag"] == "pass"
        assert by["Meta robots"] == "pass"
        assert by["Structured data"] == "warn", by       # FAQPage only
        assert by["Internal links"] == "pass", by
        print(json.dumps(out, indent=1))
        print("[tech-audit self-test] all assertions passed")
    else:
        print(json.dumps(run(), indent=1))
