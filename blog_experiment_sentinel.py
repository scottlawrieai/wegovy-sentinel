#!/usr/bin/env python3
"""
Blog template experiment — before/after tracking for a small page cohort.

Purpose: a new blog template is being trialled. This collector
  1. SELECTS the cohort on first run: the health-advice pages with the most
     impressions whose 28-day average position sits in the 5-15 band
     (striking distance -- where template-driven CTR/position moves are
     most visible), written to data/blog_experiment_config.json.
  2. Tracks each cohort page daily: 90-day GSC clicks/impressions/CTR/
     position series plus its top queries.
  3. Carries each page's "live" date (when the new template ships, edit the
     config: "live": "YYYY-MM-DD") into the output so the dashboard can
     split before/after and measure uplift.

Edit data/blog_experiment_config.json to swap pages or set live dates; the
next patrol picks the changes up. Never fatal; without GSC credentials the
previous output is left untouched.

Run:
  python blog_experiment_sentinel.py           # collect
  python blog_experiment_sentinel.py --test    # offline self-test
"""
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "data", "blog_experiment_config.json")
DATA = os.path.join(HERE, "data", "blog_experiment.json")
DOCS = os.path.join(HERE, "docs", "blog_experiment.json")

POS_MIN, POS_MAX = 5.0, 15.0        # striking-distance band for selection
MIN_IMPR = 300                      # 28-day impressions floor
COHORT_SIZE = 5
MAX_PAGES = 8                       # hard cap however the config is edited


def today_uk() -> str:
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def _label(url: str) -> str:
    path = url.split("//", 1)[-1].split("/", 1)[-1]
    slug = [p for p in path.split("/") if p][-1] if path.strip("/") else path
    return slug.replace("-", " ").strip() or url


def select_candidates(rows: list) -> list:
    """Pick the cohort from GSC page rows [{page, impr, pos, clicks}]."""
    picks = []
    for r in sorted(rows, key=lambda x: -x.get("impr", 0)):
        url = r.get("page") or ""
        if "/health-advice/" not in url:
            continue
        pos = r.get("pos")
        if pos is None or not (POS_MIN <= pos <= POS_MAX):
            continue
        if r.get("impr", 0) < MIN_IMPR:
            continue
        picks.append({"url": url, "label": _label(url), "live": None,
                      "picked": {"pos": pos, "impr": r.get("impr", 0),
                                 "clicks": r.get("clicks", 0)}})
        if len(picks) >= COHORT_SIZE:
            break
    return picks


def fetch_page_rows() -> list:
    """GSC 28-day totals per page across the whole property."""
    import rank_sources
    token = rank_sources._gsc_access_token()
    if not token:
        return []
    prop = os.environ.get("GSC_PROPERTY", "sc-domain:simpleonlinepharmacy.co.uk")
    end = rank_sources._today_uk() - timedelta(days=3)
    start = end - timedelta(days=28)
    payload = rank_sources._gsc_query(token, prop, {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["page"],
        "rowLimit": 5000,
        "type": "web",
    })
    rows = []
    for row in payload.get("rows", []):
        page = (row.get("keys") or [""])[0]
        if not page:
            continue
        rows.append({"page": page,
                     "clicks": int(row.get("clicks", 0)),
                     "impr": int(row.get("impressions", 0)),
                     "pos": round(float(row.get("position", 0)), 1)})
    return rows


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (ValueError, OSError) as e:
            print(f"[warn] {path}: {e}", file=sys.stderr)
    return default


def main():
    if "--test" in sys.argv:
        rows = [
            {"page": "https://x/health-advice/a/", "impr": 9000, "pos": 7.2, "clicks": 200},
            {"page": "https://x/health-advice/b/", "impr": 8000, "pos": 4.1, "clicks": 400},   # too good
            {"page": "https://x/weight-loss/c/", "impr": 7000, "pos": 8.0, "clicks": 100},     # not blog
            {"page": "https://x/health-advice/d/", "impr": 200, "pos": 9.0, "clicks": 5},      # too few impr
            {"page": "https://x/health-advice/e/", "impr": 6000, "pos": 14.9, "clicks": 90},
            {"page": "https://x/health-advice/f/", "impr": 5000, "pos": 15.1, "clicks": 80},   # just outside
            {"page": "https://x/health-advice/g/", "impr": 4000, "pos": 5.0, "clicks": 150},
            {"page": "https://x/health-advice/h/", "impr": 3000, "pos": 10.0, "clicks": 70},
            {"page": "https://x/health-advice/i/", "impr": 2000, "pos": 12.0, "clicks": 40},
            {"page": "https://x/health-advice/j/", "impr": 1000, "pos": 11.0, "clicks": 20},
        ]
        picks = select_candidates(rows)
        urls = [p["url"] for p in picks]
        assert len(picks) == COHORT_SIZE, picks
        assert "https://x/health-advice/a/" in urls
        assert "https://x/health-advice/b/" not in urls      # pos < 5
        assert "https://x/weight-loss/c/" not in urls        # not health-advice
        assert "https://x/health-advice/d/" not in urls      # impressions floor
        assert "https://x/health-advice/f/" not in urls      # pos > 15
        assert urls[0] == "https://x/health-advice/a/"       # impressions order
        assert _label("https://x/health-advice/mounjaro-vs-wegovy/") == "mounjaro vs wegovy"
        print("[self-test] all assertions passed")
        return

    import rank_sources

    config = load_json(CONFIG, {})
    pages = (config.get("pages") or [])[:MAX_PAGES]

    if not pages:
        rows = fetch_page_rows()
        if not rows:
            print("[blog-exp] no GSC credentials/rows; cannot select cohort yet")
            return
        pages = select_candidates(rows)
        if not pages:
            print("[blog-exp] no health-advice pages matched the 5-15 band")
            return
        config = {"pages": pages, "selected": today_uk(),
                  "criteria": f"health-advice pages, avg pos {POS_MIN}-{POS_MAX}, "
                              f">= {MIN_IMPR} impressions/28d, top {COHORT_SIZE} by impressions"}
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w") as f:
            json.dump(config, f, indent=1)
        print(f"[blog-exp] cohort selected ({len(pages)} pages):")
        for p in pages:
            print(f"  - {p['url']}  (pos {p['picked']['pos']}, "
                  f"{p['picked']['impr']} impr/28d)")

    out_pages = []
    for p in pages:
        url = p.get("url")
        if not url:
            continue
        entry = {"url": url, "label": p.get("label") or _label(url),
                 "live": p.get("live")}
        try:
            token = rank_sources._gsc_access_token()
            prop = os.environ.get("GSC_PROPERTY",
                                  "sc-domain:simpleonlinepharmacy.co.uk")
            end = rank_sources._today_uk() - timedelta(days=3)
            start = end - timedelta(days=90)
            entry["series"] = rank_sources._gsc_series(token, prop, start, end, url)
        except Exception as e:
            print(f"[warn] blog-exp series {url}: {e}", file=sys.stderr)
            entry["series"] = []
        try:
            q = rank_sources.fetch_gsc_queries(page_url=url, limit=10)
            entry["queries"] = (q.get("rows") or [])[:8]
        except Exception as e:
            print(f"[warn] blog-exp queries {url}: {e}", file=sys.stderr)
            entry["queries"] = []
        out_pages.append(entry)

    if not any(p["series"] for p in out_pages):
        prev = load_json(DOCS, None)
        if prev:
            print("[blog-exp] no fresh series; keeping previous output")
            return

    out = {"pages": out_pages, "as_of": today_uk(),
           "criteria": config.get("criteria", "")}
    for path in (DATA, DOCS):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    live_n = sum(1 for p in out_pages if p.get("live"))
    print(f"[blog-exp] tracked {len(out_pages)} pages ({live_n} live on the "
          f"new template); series days: "
          + ", ".join(str(len(p['series'])) for p in out_pages))


if __name__ == "__main__":
    main()
