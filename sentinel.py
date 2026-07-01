#!/usr/bin/env python3
"""
Wegovy Sentinel — daily rank patrol for simpleonlinepharmacy.co.uk
Pulls Semrush UK positions for SOP + 4 competitors, pill-page backlinks,
computes structural audit flags and competitive gap, appends to snapshot
history, and prints a digest.

Env:
  SEMRUSH_API_KEY    required (semrush.com -> Profile -> API)
Run:
  python sentinel.py            # live patrol
  python sentinel.py --test     # offline self-test with canned data
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

DOMAIN = "www.simpleonlinepharmacy.co.uk"
PILL_PAGE = "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/"
DATA = os.path.join(os.path.dirname(__file__), "data", "snapshots.json")
DOCS = os.path.join(os.path.dirname(__file__), "docs", "snapshots.json")
BASE_DATE = "2026-06-19"
BL_TARGET = 15

# kw, goal page class, baseline position (19 Jun 2026 audit)
TRACKED = [
    ("wegovy pill", "pill", None),
    ("wegovy pills", "pill", None),
    ("buy wegovy pill", "pill", None),
    ("buy wegovy pills", "pill", None),
    ("wegovy pill uk", "pill", None),
    ("wegovy tablets", "pill", None),
    ("oral semaglutide", "pill", None),
    ("wegovy price", "pill", 8),
    ("wegovy price uk", "pill", 8),
    ("wegovy uk", "pill", 23),
    ("cheapest wegovy uk", "pill", 14),
    ("buy wegovy", "injection", None),
    ("buy wegovy uk", "injection", None),
    ("buy wegovy online", "injection", None),
    ("wegovy side effects", "advice", 8),
    ("wegovy vs mounjaro", "advice", 25),
    ("wegovy reviews", "advice", 23),
]

COMPETITORS = [
    ("onlinedoctor.superdrug.com", "Superdrug"),
    ("chemist-4-u.com", "Chemist4U"),
    ("thefamilychemist.co.uk", "FamilyChemist"),
    ("medexpress.co.uk", "MedExpress"),
]


def classify(url: str) -> str:
    s = (url or "").lower()
    if "health-advice" in s:
        return "advice"
    if "/weight-loss/wegovy-pill" in s:
        return "pill"
    if "/weight-loss-pills/wegovy-pills" in s:
        return "legacy"
    if "/medications/wegovy" in s:
        return "legacy"
    if "/online-doctor/weight-loss/wegovy" in s:
        return "legacy"
    if "/weight-loss/wegovy" in s:
        return "injection"
    return "other"


def today_uk() -> str:
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def semrush(params: dict) -> str:
    key = os.environ.get("SEMRUSH_API_KEY", "")
    if not key:
        raise RuntimeError("SEMRUSH_API_KEY is not set")
    q = urllib.parse.urlencode({**params, "key": key})
    url = f"https://api.semrush.com/?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "wegovy-sentinel/2.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    if text.startswith("ERROR"):
        if "NOTHING FOUND" in text:
            return ""
        raise RuntimeError(f"Semrush: {text.strip()[:120]}")
    return text


def parse_rows(csv_text: str) -> list:
    rows = []
    lines = [l for l in csv_text.splitlines() if l.strip()]
    if not lines:
        return rows
    cols = [c.strip().lower() for c in lines[0].split(";")]
    try:
        ki = next(i for i, c in enumerate(cols) if c.startswith("keyword"))
        pi = cols.index("position")
        ui = cols.index("url")
        vi = next((i for i, c in enumerate(cols) if "volume" in c), None)
    except (StopIteration, ValueError):
        return rows
    for line in lines[1:]:
        p = line.split(";")
        try:
            rows.append({
                "k": p[ki].strip().lower(),
                "p": int(p[pi]),
                "v": int(p[vi]) if vi is not None and p[vi].isdigit() else 0,
                "u": p[ui].strip(),
            })
        except (IndexError, ValueError):
            continue
    return rows


def fetch_positions() -> list:
    rows = []
    for filt in ("+|Ph|Co|wegovy", "+|Ph|Co|semaglutide"):
        rows += parse_rows(semrush({
            "type": "domain_organic",
            "domain": DOMAIN,
            "database": "uk",
            "display_filter": filt,
            "display_sort": "nq_desc",
            "display_limit": 50,
            "export_columns": "Ph,Po,Nq,Ur",
        }))
    return rows


def fetch_competitor_positions() -> dict:
    comp = {}
    for domain, label in COMPETITORS:
        try:
            rows = []
            for filt in ("+|Ph|Co|wegovy", "+|Ph|Co|semaglutide"):
                rows += parse_rows(semrush({
                    "type": "domain_organic",
                    "domain": domain,
                    "database": "uk",
                    "display_filter": filt,
                    "display_sort": "nq_desc",
                    "display_limit": 50,
                    "export_columns": "Ph,Po,Nq,Ur",
                }))
            best = {}
            for kw, _, _ in TRACKED:
                hits = [r for r in rows if r["k"] == kw]
                if hits:
                    top = min(hits, key=lambda r: r["p"])
                    best[kw] = {"p": top["p"], "u": top["u"]}
            if best:
                comp[label] = best
        except Exception as e:
            print(f"[warn] competitor {label}: {e}", file=sys.stderr)
    return comp


def fetch_backlinks() -> dict:
    try:
        text = semrush({
            "type": "backlinks_overview",
            "target": PILL_PAGE,
            "target_type": "url",
            "export_columns": "total,domains_num",
        })
        lines = [l for l in text.splitlines() if l.strip()]
        if len(lines) >= 2:
            cols = [c.strip().lower() for c in lines[0].split(";")]
            vals = lines[1].split(";")
            return {
                "t": int(vals[cols.index("total")]),
                "d": int(vals[cols.index("domains_num")]),
            }
    except Exception as e:
        print(f"[warn] backlinks unavailable: {e}", file=sys.stderr)
    return {"t": 0, "d": 0}


def fetch_extra_sources() -> dict:
    """Pull GSC + AWR rankings (optional, credential-gated). Never fatal."""
    import rank_sources
    kws = [kw for kw, _, _ in TRACKED]
    src = {"gsc": {}, "awr": {}}
    try:
        src["gsc"] = rank_sources.fetch_gsc(kws)
    except Exception as e:
        print(f"[warn] GSC unavailable: {e}", file=sys.stderr)
    try:
        src["awr"] = rank_sources.fetch_awr(kws)
    except Exception as e:
        print(f"[warn] AWR unavailable: {e}", file=sys.stderr)
    return src


def build_snapshot(rows: list, bl: dict, comp: dict, src: dict = None,
                   mode: str = "semrush") -> dict:
    clean = []
    for r in rows:
        if r.get("k") and isinstance(r.get("p"), int):
            clean.append({**r, "c": classify(r.get("u", ""))})
    best = {}
    for kw, goal, _ in TRACKED:
        hits = [r for r in clean if r["k"] == kw]
        if not hits:
            best[kw] = None
            continue
        top = min(hits, key=lambda r: r["p"])
        best[kw] = {"p": top["p"], "c": top["c"], "u": top["u"],
                    "n": len({h["u"] for h in hits})}

    pill_kw = best.get("wegovy pill") or best.get("wegovy pills")
    pill_pos = pill_kw["p"] if pill_kw else None

    bw_inj = [r["p"] for r in clean if r["k"] == "buy wegovy" and r["c"] == "injection"]

    flags = {
        "wrong": any(best[k] and best[k]["c"] != g and best[k]["c"] != "advice"
                     for k, g, _ in TRACKED if best[k]),
        "legacy": any(r["c"] == "legacy" for r in clean),
        "cann": sum(1 for k, _, _ in TRACKED if best[k] and best[k]["n"] > 1),
    }
    src = src or {"gsc": {}, "awr": {}}
    return {
        "date": today_uk(),
        "mode": mode,
        "best": best,
        "comp": comp,
        "src": {"gsc": src.get("gsc", {}), "awr": src.get("awr", {})},
        "m": {
            "pill": pill_pos,
            "bwInj": min(bw_inj) if bw_inj else None,
            "blD": bl.get("d", 0),
            "blT": bl.get("t", 0),
        },
        "flags": flags,
    }


def streak(snaps: list, key: str) -> int:
    n = 0
    for s in reversed(snaps):
        if s.get("flags", {}).get(key):
            n += 1
        else:
            break
    return n


def arrow(d):
    if d is None:
        return "--"
    if d == 0:
        return "="
    return ("+" if d > 0 else "-") + str(abs(d))


def digest(snaps: list) -> str:
    cur, prev = snaps[-1], (snaps[-2] if len(snaps) > 1 else None)
    pill = cur["m"]["pill"]
    pill_prev = prev["m"]["pill"] if prev else None
    L = [f"WEGOVY SENTINEL -- {cur['date']}"
         + (f" ({cur['mode']} mode)" if cur["mode"] != "semrush" else "")]

    d_prev = (pill_prev - pill) if (pill is not None and pill_prev is not None) else None
    line = f"  pill keyword: {'P' + str(pill) if pill else 'n/a'} ({arrow(d_prev)} vs prev)"
    if pill is not None and pill <= 10:
        line += " -- PAGE ONE"
    L.append(line)

    bw = cur["best"].get("buy wegovy")
    if bw:
        tag = " [!] WRONG PAGE" if bw["c"] != "injection" else ""
        L.append(f"  buy wegovy: P{bw['p']} via {bw['c'].upper()}{tag}"
                 + (f" (injection: P{cur['m']['bwInj']})" if cur["m"]["bwInj"] else ""))

    L.append("")
    L.append("TRACKED KEYWORDS (SOP across sources -- lower is better):")
    L.append(f"  {'Keyword':<30} {'Semrush':>7} {'GSC':>6} {'AWR':>5}  "
             f"{'Superdrug':>10}  {'Chemist4U':>10}  {'FamChem':>10}  {'MedExpr':>10}")
    L.append("  " + "-" * 104)
    comp = cur.get("comp", {})
    gsc = cur.get("src", {}).get("gsc", {})
    awr = cur.get("src", {}).get("awr", {})
    for kw, goal, baseline in TRACKED:
        sop = cur["best"].get(kw)
        sop_str = f"P{sop['p']}" if sop else "--"
        g = gsc.get(kw)
        gsc_str = f"P{g['pos']:g}" if g else "--"
        a = awr.get(kw)
        awr_str = f"P{a}" if a else "--"
        cols = [f"  {kw:<30} {sop_str:>7} {gsc_str:>6} {awr_str:>5}"]
        for _, label in COMPETITORS:
            c = comp.get(label, {}).get(kw)
            cols.append(f"{('P' + str(c['p'])) if c else '--':>10}")
        L.append("  ".join(cols))

    if cur["flags"]["wrong"]:
        L.append(f"\n[!] Wrong-page routing detected -- day {streak(snaps, 'wrong')}")
    if cur["flags"]["legacy"]:
        L.append(f"[!] Legacy URL still ranking -- day {streak(snaps, 'legacy')}")
    if cur["flags"]["cann"]:
        L.append(f"[*] {cur['flags']['cann']} keywords cannibalised (2+ URLs)")

    if gsc:
        gc = sum(v["clicks"] for v in gsc.values())
        gi = sum(v["impr"] for v in gsc.values())
        L.append(f"\nSearch Console (trailing window): {gc} clicks / {gi} impressions across tracked terms")

    L.append(f"\nBacklinks to pill page: {cur['m']['blD']} referring domains (target {BL_TARGET})")

    gaps = []
    for kw, goal, _ in TRACKED:
        if goal != "pill":
            continue
        sop = cur["best"].get(kw)
        sop_p = sop["p"] if sop else 999
        for _, label in COMPETITORS:
            c = comp.get(label, {}).get(kw)
            if c and c["p"] < sop_p:
                gaps.append((kw, label, c["p"], sop_p if sop_p < 999 else None))
    if gaps:
        L.append("\nCOMPETITIVE GAPS (pill keywords where competitors outrank SOP):")
        for kw, label, cp, sp in gaps:
            sop_str = f"P{sp}" if sp else "n/a"
            L.append(f"  {kw}: {label} P{cp} vs SOP {sop_str}")

    if pill is not None and pill <= 3:
        L.append("\n[TARGET] P1-3 achieved. Hold through MHRA decision.")
    return "\n".join(L)


def load_history() -> list:
    if os.path.exists(DATA):
        with open(DATA) as f:
            return json.load(f)
    return []


def save_history(snaps: list):
    snaps = snaps[-365:]
    for path in (DATA, DOCS):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(snaps, f, indent=1)


def post_slack(text: str):
    """Deliver the daily digest to Slack if SLACK_WEBHOOK_URL is configured."""
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        return
    try:
        data = json.dumps({"text": "```\n" + text[:3500] + "\n```"}).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print(f"[warn] slack post failed: {e}", file=sys.stderr)


FIXTURE_ROWS = (
    "Keyword;Position;Search Volume;Url\n"
    "wegovy uk;23;14800;https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/\n"
    "wegovy price;8;6600;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy-pill/oral-wegovy-price-comparison-uk/\n"
    "wegovy price uk;8;2900;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy-pill/oral-wegovy-price-comparison-uk/\n"
    "cheapest wegovy uk;14;1900;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy-pill/oral-wegovy-price-comparison-uk/\n"
    "wegovy side effects;8;9900;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy/wegovy-side-effects/\n"
    "wegovy vs mounjaro;25;6600;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy-pill/wegovy-pill-vs-mounjaro/\n"
    "wegovy reviews;23;9900;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy/wegovy-reviews/\n"
)

FIXTURE_COMP = {
    "Superdrug": {
        "wegovy pill": {"p": 3, "u": "https://onlinedoctor.superdrug.com/wegovy-pill.html"},
        "wegovy pill uk": {"p": 5, "u": "https://onlinedoctor.superdrug.com/wegovy-pill.html"},
        "buy wegovy pill": {"p": 8, "u": "https://onlinedoctor.superdrug.com/wegovy-pill.html"},
    },
    "Chemist4U": {
        "wegovy pill": {"p": 5, "u": "https://www.chemist-4-u.com/wegovy-pills"},
        "wegovy pills": {"p": 4, "u": "https://www.chemist-4-u.com/wegovy-pills"},
        "wegovy tablets": {"p": 7, "u": "https://www.chemist-4-u.com/wegovy-pills"},
    },
    "FamilyChemist": {
        "wegovy tablets": {"p": 10, "u": "https://www.thefamilychemist.co.uk/wegovy-tablets/"},
    },
    "MedExpress": {
        "wegovy pill": {"p": 12, "u": "https://www.medexpress.co.uk/clinics/weight-loss/wegovy-pill"},
    },
}


def main():
    test = "--test" in sys.argv
    try:
        if test:
            import rank_sources
            rows = parse_rows(FIXTURE_ROWS)
            bl = {"t": 2, "d": 2}
            comp = FIXTURE_COMP
            src = {"gsc": rank_sources.FIXTURE_GSC, "awr": rank_sources.FIXTURE_AWR}
        else:
            rows = fetch_positions()
            bl = fetch_backlinks()
            comp = fetch_competitor_positions()
            src = fetch_extra_sources()
        snaps = load_history()
        snap = build_snapshot(rows, bl, comp, src)
        snaps = [s for s in snaps if s["date"] != snap["date"]] + [snap]
        if not test:
            save_history(snaps)   # never overwrite real history during a self-test
        text = digest(snaps)
        print(text)

        # Daily content review (on-page gap analysis). Non-fatal: a failure here
        # must never break the rank patrol.
        content_text = ""
        try:
            import content_audit
            if test:
                serp_fn, fetch_fn = content_audit._fixtures()
                audit = content_audit.build_audit(serp_fn, fetch_fn, mode="test")
            else:
                audit = content_audit.run_and_store(mode="live")
            content_text = content_audit.digest_section(audit)
            print(content_text)
        except Exception as e:
            print(f"[warn] content review unavailable: {e}", file=sys.stderr)

        if not test:
            post_slack(text + ("\n" + content_text if content_text else ""))

        if test:
            assert snap["m"]["pill"] is None, "pill keywords not in fixture"
            assert snap["best"]["wegovy uk"]["p"] == 23
            assert snap["best"]["wegovy price"]["p"] == 8
            assert "Superdrug" in snap["comp"]
            assert snap["comp"]["Superdrug"]["wegovy pill"]["p"] == 3
            assert snap["src"]["gsc"]["wegovy pill"]["clicks"] == 41
            assert snap["src"]["awr"]["wegovy pill"] == 24
            assert "GSC" in text and "AWR" in text, "multi-source digest rendered"
            assert "Search Console" in text, "GSC highlight rendered"
            assert content_text and "CONTENT REVIEW" in content_text, "content review ran"
            print("\n[self-test] all assertions passed")
    except Exception as e:
        msg = f"WEGOVY SENTINEL FAILED -- {today_uk()}: {e}"
        print(msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
