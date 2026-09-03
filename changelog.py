#!/usr/bin/env python3
"""
Changelog — automated change detection for the Wegovy pill page.

Diffs our own page's structure day-over-day from the content audit history
(docs/content.json) and emits dated changelog entries. Auto-detected changes
are regenerated from scratch each run (idempotent); hand-written entries live
in data/changelog_manual.json and are merged in, so a human can record things
the crawler cannot see (accordion default state, visual reordering, etc).

The dashboard plots each dated entry as an annotation marker on the Search
Console performance charts, so a rank or traffic movement can be read against
what actually shipped that day.

Run:
  python changelog.py            # regenerate from content history
  python changelog.py --test     # offline self-test
"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "docs", "content.json")
MANUAL = os.path.join(HERE, "data", "changelog_manual.json")
DATA = os.path.join(HERE, "data", "changelog.json")
DOCS = os.path.join(HERE, "docs", "changelog.json")

# Per-product file paths; wegovy (default) keeps the historical locations.
PRODUCTS = {
    "wegovy": {"content": CONTENT, "manual": MANUAL, "data": DATA, "docs": DOCS},
    "mounjaro": {
        "content": os.path.join(HERE, "docs", "mounjaro_content.json"),
        "manual": os.path.join(HERE, "data", "mounjaro_changelog_manual.json"),
        "data": os.path.join(HERE, "data", "mounjaro_changelog.json"),
        "docs": os.path.join(HERE, "docs", "mounjaro_changelog.json"),
    },
    "wegovy-injection": {
        "content": os.path.join(HERE, "docs", "wegovy_injection_content.json"),
        "manual": os.path.join(HERE, "data", "wegovy_injection_changelog_manual.json"),
        "data": os.path.join(HERE, "data", "wegovy_injection_changelog.json"),
        "docs": os.path.join(HERE, "docs", "wegovy_injection_changelog.json"),
    },
}


def product_from_argv(argv: list) -> str:
    if "--product" in argv:
        i = argv.index("--product")
        name = argv[i + 1] if i + 1 < len(argv) else ""
        if name not in PRODUCTS:
            print(f"[error] unknown product {name!r}; choose from "
                  f"{', '.join(sorted(PRODUCTS))}", file=sys.stderr)
            raise SystemExit(2)
        return name
    return "wegovy"

# Word-count moves smaller than this are treated as boilerplate jitter
# (rotating review counts, dated copy) rather than a real content change.
WC_NOISE = 25


def today_uk() -> str:
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def _us_page(audit: dict):
    for p in audit.get("pages") or []:
        if p.get("role") == "us" and p.get("status") == "ok":
            return p
    return None


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def _denum(s: str) -> str:
    """Heading with digits/separators stripped, for rolling-counter matching."""
    return "".join(c for c in str(s or "").lower() if not c.isdigit()
                   and c not in ",.+")


def _trim(s: str, n: int = 70) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def diff_pages(prev: dict, cur: dict) -> list:
    """Structural diff of our page between two audits. Returns change dicts."""
    out = []

    for field, label in (("title", "Title tag"), ("meta", "Meta description"),
                         ("h1", "H1")):
        a, b = (prev.get(field) or "").strip(), (cur.get(field) or "").strip()
        if a != b:
            out.append({
                "type": "seo",
                "text": f"{label} changed: “{_trim(a)}” → “{_trim(b)}”",
            })

    if (prev.get("robots") or "") != (cur.get("robots") or ""):
        out.append({
            "type": "technical",
            "text": f"Robots directive {prev.get('robots') or 'none'} → {cur.get('robots') or 'none'}",
        })

    # H2 sections: added / removed / reordered. Headings that differ only in
    # their digits are the same section with a rolling counter ("46,000+
    # reviews" -> "47,000+ reviews") and are not reported as a change.
    pa, pb = list(prev.get("h2") or []), list(cur.get("h2") or [])
    na = {_denum(h) for h in pa}
    nb = {_denum(h) for h in pb}
    added = [h for h in pb if h not in pa and _denum(h) not in na]
    removed = [h for h in pa if h not in pb and _denum(h) not in nb]
    for h in added:
        out.append({"type": "structure", "text": f"Section added: “{_trim(h)}”"})
    for h in removed:
        out.append({"type": "structure", "text": f"Section removed: “{_trim(h)}”"})
    if not added and not removed:
        common = [h for h in pa if h in pb]
        if common and common != [h for h in pb if h in pa]:
            moved = _moved_sections(pa, pb)
            out.append({
                "type": "structure",
                "text": "Sections reordered" + (f": {', '.join(_trim(m, 40) for m in moved[:3])}" if moved else ""),
            })

    # FAQs
    fa, fb = list(prev.get("faqs") or []), list(cur.get("faqs") or [])
    fadd = [q for q in fb if q not in fa]
    frem = [q for q in fa if q not in fb]
    if fadd:
        out.append({
            "type": "content",
            "text": f"{len(fadd)} FAQ{'s' if len(fadd) != 1 else ''} added"
                    + (f": “{_trim(fadd[0], 55)}”" + (f" +{len(fadd) - 1} more" if len(fadd) > 1 else "") if fadd else ""),
        })
    if frem:
        out.append({
            "type": "content",
            "text": f"{len(frem)} FAQ{'s' if len(frem) != 1 else ''} removed"
                    + (f": “{_trim(frem[0], 55)}”" + (f" +{len(frem) - 1} more" if len(frem) > 1 else "") if frem else ""),
        })

    # Word count (noise-gated)
    wa, wb = prev.get("wc") or 0, cur.get("wc") or 0
    if abs(wb - wa) >= WC_NOISE:
        out.append({
            "type": "content",
            "text": f"Body copy {'+' if wb > wa else '−'}{_fmt(abs(wb - wa))} words ({_fmt(wa)} → {_fmt(wb)})",
        })

    # Sub-heading count
    ha, hb = prev.get("h3n") or 0, cur.get("h3n") or 0
    if ha != hb:
        out.append({"type": "structure", "text": f"H3 sub-headings {ha} → {hb}"})

    # Topical coverage
    ta, tb = set(prev.get("terms") or []), set(cur.get("terms") or [])
    gained, lost = sorted(tb - ta), sorted(ta - tb)
    if gained:
        out.append({
            "type": "content",
            "text": f"Topic coverage gained: {', '.join(gained[:4])}"
                    + (f" +{len(gained) - 4} more" if len(gained) > 4 else ""),
        })
    if lost:
        out.append({
            "type": "content",
            "text": f"Topic coverage lost: {', '.join(lost[:4])}"
                    + (f" +{len(lost) - 4} more" if len(lost) > 4 else ""),
        })

    return out


def _moved_sections(pa: list, pb: list) -> list:
    """Names of sections whose relative order changed between two H2 lists."""
    common = [h for h in pa if h in pb]
    ia = {h: i for i, h in enumerate(common)}
    ib = {h: i for i, h in enumerate([h for h in pb if h in pa])}
    return [h for h in common if ia.get(h) != ib.get(h)]


def build_auto(audits: list) -> dict:
    """date -> list of auto-detected changes, from consecutive audits."""
    by_date = {}
    prev = None
    for a in audits:
        cur = _us_page(a)
        if cur is None:
            continue
        if prev is not None:
            ch = diff_pages(prev, cur)
            if ch:
                by_date[a.get("date")] = ch
        prev = cur
    return by_date


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (ValueError, OSError) as e:
            print(f"[warn] {path}: {e}", file=sys.stderr)
    return default


def merge(auto: dict, manual: list) -> list:
    """Merge auto-detected and hand-written entries into one dated list."""
    by_date = {}
    for date, changes in auto.items():
        by_date.setdefault(date, []).extend(
            {**c, "source": "auto"} for c in changes)
    for entry in manual:
        date = entry.get("date")
        if not date:
            continue
        for c in entry.get("changes") or []:
            by_date.setdefault(date, []).append({**c, "source": "manual"})
    return [{"date": d, "changes": by_date[d]} for d in sorted(by_date)]


def save(entries: list, paths=(DATA, DOCS)):
    for path in paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(entries, f, indent=1, ensure_ascii=False)


def digest(entries: list, n: int = 6) -> str:
    if not entries:
        return "CHANGELOG -- no changes recorded yet."
    L = [f"CHANGELOG -- {len(entries)} dated entr"
         f"{'y' if len(entries) == 1 else 'ies'}"]
    for e in entries[-n:][::-1]:
        L.append(f"  {e['date']}")
        for c in e["changes"]:
            tag = "*" if c.get("source") == "manual" else "-"
            L.append(f"    {tag} [{c.get('type', 'change')}] {c['text']}")
    return "\n".join(L)


FIXTURE_PREV = {
    "role": "us", "status": "ok", "title": "Buy Wegovy Pill Online UK",
    "meta": "Old meta", "h1": "Wegovy pill UK", "robots": "index,follow",
    "h2": ["About Wegovy Pills", "Reviews", "Dosing"],
    "faqs": ["What is the Wegovy pill?"], "wc": 7000, "h3n": 57,
    "terms": ["oral semaglutide"],
}
FIXTURE_CUR = {
    "role": "us", "status": "ok", "title": "Buy Wegovy Pill Online UK",
    "meta": "New meta", "h1": "Wegovy pill UK", "robots": "index,follow",
    "h2": ["About Wegovy Pills", "Dosing", "Reviews", "Sources"],
    "faqs": ["What is the Wegovy pill?", "How does it work?"],
    "wc": 7400, "h3n": 60, "terms": ["oral semaglutide", "MHRA"],
}


def main():
    if "--test" in sys.argv:
        ch = diff_pages(FIXTURE_PREV, FIXTURE_CUR)
        text = " | ".join(c["text"] for c in ch)
        assert any("Meta description changed" in c["text"] for c in ch), text
        assert any("Section added" in c["text"] and "Sources" in c["text"] for c in ch), text
        assert any("1 FAQ added" in c["text"] for c in ch), text
        assert any("+400 words" in c["text"] for c in ch), text
        assert any("H3 sub-headings 57 → 60" in c["text"] for c in ch), text
        assert any("Topic coverage gained" in c["text"] for c in ch), text
        # No-change diff must be empty
        assert diff_pages(FIXTURE_CUR, FIXTURE_CUR) == []
        # Reorder detection without add/remove
        a = {"h2": ["A", "B", "C"]}
        b = {"h2": ["C", "A", "B"]}
        assert any("reordered" in c["text"] for c in diff_pages(a, b))
        merged = merge({"2026-01-02": [{"type": "content", "text": "x"}]},
                       [{"date": "2026-01-01", "changes": [{"type": "ux", "text": "y"}]}])
        assert [m["date"] for m in merged] == ["2026-01-01", "2026-01-02"]
        assert merged[0]["changes"][0]["source"] == "manual"
        assert merged[1]["changes"][0]["source"] == "auto"
        print(digest(merged))
        print("\n[self-test] all assertions passed")
        return

    p = PRODUCTS[product_from_argv(sys.argv)]
    audits = load_json(p["content"], [])
    manual = load_json(p["manual"], [])
    if not audits:
        print("[warn] no content audit history yet -- manual entries only",
              file=sys.stderr)
    entries = merge(build_auto(audits), manual)
    save(entries, (p["data"], p["docs"]))
    print(digest(entries))


if __name__ == "__main__":
    main()
