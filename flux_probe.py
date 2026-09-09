#!/usr/bin/env python3
"""
Flux probe — pins down why daily content diffs fire with no real edits.

The changelog keeps logging small +/- body-copy swings on every tracked page.
Two rival explanations:
  A. CDN cache vintages — different edge nodes serve different cached copies
     to the patrol's changing runner IPs.
  B. Dynamic server-rendered block — e.g. a rotating reviews widget embeds
     different review texts per request.

The probe fetches each page twice in the same run (seconds apart) and records
word count, a text hash, cache-relevant response headers, and a compact
per-block signature of the visible text.
  - both fetches differ           -> per-request dynamic content (B)
  - identical now, differs daily  -> cache vintages (A)
The block signature diff names the exact text that changed either way.

Writes data/flux_probe.json (last 14 runs) and prints a verdict per page.
Never fatal; no credentials needed.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import content_audit

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "flux_probe.json")
KEEP_RUNS = 14

PAGES = {
    "wegovy-pill": "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/",
    "mounjaro": "https://www.simpleonlinepharmacy.co.uk/weight-loss/mounjaro/",
    "wegovy-injection": "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy/",
    "homepage": "https://www.simpleonlinepharmacy.co.uk/",
    "weightloss-hub": "https://www.simpleonlinepharmacy.co.uk/weight-loss/",
}
HEADERS_OF_INTEREST = ("cf-cache-status", "age", "cf-ray", "etag",
                       "last-modified", "x-cache", "vary")


def fetch_with_headers(url: str, timeout: int = 25):
    """Like content_audit.fetch_html but also returns response headers."""
    req = urllib.request.Request(url, headers={
        "User-Agent": content_audit.UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(3_000_000)
            enc = r.headers.get_content_charset() or "utf-8"
            hdrs = {h: r.headers.get(h) for h in HEADERS_OF_INTEREST
                    if r.headers.get(h)}
            return "ok", raw.decode(enc, "replace"), hdrs
    except Exception as e:
        return f"error:{type(e).__name__}", "", {}


def signature(html: str) -> dict:
    """Word count, text hash and per-block signature of the visible copy."""
    pg = content_audit.parse_page(html)
    blocks = []
    for part in pg.text_parts:
        words = part.split()
        if len(words) >= 15:                       # ignore labels/crumbs
            blocks.append([len(words), " ".join(words[:6])[:60]])
    body = " ".join(pg.text_parts)
    return {"wc": len(body.split()),
            "hash": hashlib.sha1(body.encode()).hexdigest()[:12],
            "blocks": blocks}


def block_diff(a: list, b: list) -> dict:
    """Blocks present in one signature but not the other (by snippet+size)."""
    ka = {tuple(x) for x in a}
    kb = {tuple(x) for x in b}
    return {"removed": [list(x) for x in sorted(ka - kb)][:8],
            "added": [list(x) for x in sorted(kb - ka)][:8]}


def main():
    if "--test" in sys.argv:
        html = ("<html><body><h1>T</h1><p>" + "alpha " * 20 + "</p><p>"
                + "beta " * 30 + "</p><p>tiny</p></body></html>")
        sig = signature(html)
        assert sig["wc"] >= 50 and len(sig["blocks"]) == 2, sig
        d = block_diff(sig["blocks"], sig["blocks"][:1])
        assert d["removed"] and not d["added"], d
        print("[self-test] all assertions passed")
        return

    today = datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")
    history = []
    if os.path.exists(OUT):
        try:
            with open(OUT) as f:
                history = json.load(f)
        except (ValueError, OSError):
            history = []
    prev = history[-1] if history else None

    run = {"date": today, "pages": {}}
    for key, url in PAGES.items():
        st_a, html_a, hdr_a = fetch_with_headers(url)
        time.sleep(8)
        st_b, html_b, hdr_b = fetch_with_headers(url)
        if st_a != "ok" or st_b != "ok":
            run["pages"][key] = {"status": f"{st_a}/{st_b}"}
            print(f"[flux] {key}: fetch failed ({st_a}/{st_b})")
            continue
        sa, sb = signature(html_a), signature(html_b)
        same_run = sa["hash"] == sb["hash"]
        entry = {"status": "ok", "same_run": same_run,
                 "a": {"wc": sa["wc"], "hash": sa["hash"], "hdrs": hdr_a},
                 "b": {"wc": sb["wc"], "hash": sb["hash"], "hdrs": hdr_b},
                 "blocks": sa["blocks"]}
        if not same_run:
            entry["intra_diff"] = block_diff(sa["blocks"], sb["blocks"])
        pprev = ((prev or {}).get("pages") or {}).get(key) or {}
        if pprev.get("blocks"):
            entry["vs_prev"] = block_diff(pprev["blocks"], sa["blocks"])
            entry["same_as_prev"] = pprev.get("a", {}).get("hash") == sa["hash"]
        run["pages"][key] = entry

        verdict = ("DYNAMIC per-request content" if not same_run else
                   "stable within run")
        print(f"[flux] {key}: wc {sa['wc']}/{sb['wc']} "
              f"cache {hdr_a.get('cf-cache-status','?')}/{hdr_b.get('cf-cache-status','?')} "
              f"age {hdr_a.get('age','-')}/{hdr_b.get('age','-')} -> {verdict}")
        if not same_run:
            d = entry["intra_diff"]
            for x in d["removed"]:
                print(f"[flux]   only in fetch A ({x[0]}w): {x[1]}")
            for x in d["added"]:
                print(f"[flux]   only in fetch B ({x[0]}w): {x[1]}")

    history.append(run)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(history[-KEEP_RUNS:], f, indent=1)
    print(f"[flux] probe written for {len(run['pages'])} pages")


if __name__ == "__main__":
    main()
