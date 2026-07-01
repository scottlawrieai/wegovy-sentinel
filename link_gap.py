#!/usr/bin/env python3
"""
Backlink gap tracker (stdlib only, Semrush analytics/v1 API).

We are at ~0 referring domains on the pill page while every competitor on
page one has an established link profile -- the single biggest gap. This
module turns the patrol into a prospecting engine:

  1. Pull referring domains for OUR pill page.
  2. Pull referring domains for each competitor's ranking pill URL
     (taken live from the day's SERP data, so it tracks whoever ranks).
  3. Prospects = domains linking to >=2 competitors but NOT to us
     (a domain that links to two rival pharmacy pill pages will very
     plausibly link to ours), ranked by how many competitors they cover.

Uses the same SEMRUSH_API_KEY as the rank patrol. Every failure degrades
to an empty result -- never breaks the patrol.
"""
import sys

MAX_DOMAINS = 200          # refdomains pulled per target
MAX_PROSPECTS = 25         # kept in the snapshot / shown on the dashboard


def _refdomains(semrush_fn, target: str, target_type: str) -> set:
    """Return the set of referring domains for a URL/domain target."""
    text = semrush_fn({
        "type": "backlinks_refdomains",
        "target": target,
        "target_type": target_type,
        "export_columns": "domain",
        "display_limit": MAX_DOMAINS,
    }, base="https://api.semrush.com/analytics/v1/")
    domains = set()
    for line in text.splitlines()[1:]:
        d = line.strip().split(";")[0].strip().lower()
        if d and "." in d:
            domains.add(d)
    return domains


def build(semrush_fn, our_url: str, comp_urls: dict) -> dict:
    """comp_urls: {label: competitor_pill_url}. Returns the gap summary."""
    try:
        ours = _refdomains(semrush_fn, our_url, "url")
    except Exception as e:
        print(f"[links] our refdomains unavailable: {e}", file=sys.stderr)
        ours = set()

    seen = {}                                     # domain -> [competitor labels]
    comp_counts = {}
    own_domains = {d.split("/")[2].replace("www.", "") if "://" in d else d
                   for d in [our_url]}
    for label, url in comp_urls.items():
        if not url:
            continue
        try:
            doms = _refdomains(semrush_fn, url, "url")
        except Exception as e:
            print(f"[links] {label} refdomains unavailable: {e}", file=sys.stderr)
            continue
        comp_counts[label] = len(doms)
        host = url.split("/")[2].replace("www.", "") if "://" in url else ""
        for d in doms:
            if d in ours or d.endswith(host) or any(d.endswith(o) for o in own_domains):
                continue
            seen.setdefault(d, []).append(label)

    prospects = sorted(
        ({"d": d, "n": len(who), "who": sorted(who)} for d, who in seen.items()),
        key=lambda x: (-x["n"], x["d"]))
    # domains covering 2+ competitors first; pad with strongest singles
    strong = [p for p in prospects if p["n"] >= 2]
    out = (strong + [p for p in prospects if p["n"] == 1])[:MAX_PROSPECTS]
    return {"ours": len(ours), "comp": comp_counts, "prospects": out,
            "strong": len(strong)}


# ---------------------------------------------------------------------------
_FIXTURE = {
    "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/":
        "domain\nnhs-friends.co.uk\n",
    "https://onlinedoctor.superdrug.com/wegovy-pill.html":
        "domain\nhealthline-style.com\npharmatimes-style.co.uk\ndietblog.example\n",
    "https://www.chemist-4-u.com/wegovy-pills":
        "domain\nhealthline-style.com\npharmatimes-style.co.uk\ncoupon.example\n",
    "https://www.medexpress.co.uk/clinics/weight-loss/wegovy-pill":
        "domain\nhealthline-style.com\nnhs-friends.co.uk\n",
}


def _fixture_semrush(params, base=""):
    return _FIXTURE.get(params.get("target", ""), "domain\n")


if __name__ == "__main__":
    if "--test" in sys.argv:
        gap = build(
            _fixture_semrush,
            "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/",
            {"Superdrug": "https://onlinedoctor.superdrug.com/wegovy-pill.html",
             "Chemist4U": "https://www.chemist-4-u.com/wegovy-pills",
             "MedExpress": "https://www.medexpress.co.uk/clinics/weight-loss/wegovy-pill"})
        assert gap["ours"] == 1
        top = gap["prospects"][0]
        # healthline-style links to all 3 competitors, not to us -> top prospect
        assert top["d"] == "healthline-style.com" and top["n"] == 3, gap
        # nhs-friends links to us already -> must NOT be a prospect
        assert all(p["d"] != "nhs-friends.co.uk" for p in gap["prospects"]), gap
        print(gap)
        print("[link-gap self-test] all assertions passed")
