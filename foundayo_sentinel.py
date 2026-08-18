#!/usr/bin/env python3
"""
Foundayo Sentinel — daily rank patrol for simpleonlinepharmacy.co.uk
Tracks Foundayo (orforglipron) keyword positions for SOP + 5 competitors,
computes structural audit flags and competitive gap, appends to snapshot
history, and prints a digest.

Env:
  SEMRUSH_API_KEY    required (semrush.com -> Profile -> API)
Run:
  python foundayo_sentinel.py            # live patrol
  python foundayo_sentinel.py --test     # offline self-test with canned data
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

DOMAIN = "www.simpleonlinepharmacy.co.uk"
PRODUCT_PAGE = "https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss-pills/foundayo/"
ORFOG_PAGE = "https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/orforglipron/"
DATA = os.path.join(os.path.dirname(__file__), "data", "foundayo_snapshots.json")
DOCS = os.path.join(os.path.dirname(__file__), "docs", "foundayo_snapshots.json")
BASE_DATE = "2026-07-28"

# kw, goal page class, baseline position (Jul 2026 Semrush)
TRACKED = [
    ("foundayo", "foundayo", 1),
    ("foundayo pill", "foundayo", 4),
    ("orforglipron", "orforglipron", 17),
    ("orforglipron uk", "orforglipron", 2),
    ("orforglipron price", "orforglipron", 1),
    ("orforglipron tablet", "orforglipron", 5),
    ("orforglipron tablets", "orforglipron", 2),
    ("orforglipron pill", "orforglipron", 3),
    ("orforglipron weight loss", "orforglipron", 9),
    ("orforglipron weight-loss pill", "orforglipron", 9),
    ("orforglipron side effects", "advice", 34),
    ("orforglipron uk where to buy", "orforglipron", 1),
    ("orforglipron buy online", "orforglipron", 2),
    ("orforglipron price per month", "orforglipron", 3),
    ("eli lilly orforglipron weight loss", "orforglipron", 45),
]

COMPETITORS = [
    ("onlinedoctor.superdrug.com", "Superdrug"),
    ("www.oxfordonlinepharmacy.co.uk", "OxfordPharm"),
    ("www.chemist-4-u.com", "Chemist4U"),
    ("www.theindependentpharmacy.co.uk", "IndepPharm"),
    ("onlinedoctor.boots.com", "Boots"),
]


def classify(url: str) -> str:
    s = (url or "").lower()
    if "health-advice" in s:
        return "advice"
    if "/weight-loss-pills/foundayo" in s:
        return "foundayo"
    if "/weight-loss/orforglipron" in s:
        return "orforglipron"
    if "/weight-loss/wegovy" in s:
        return "other"
    return "other"


def today_uk() -> str:
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def semrush(params: dict) -> str:
    key = os.environ.get("SEMRUSH_API_KEY", "")
    if not key:
        raise RuntimeError("SEMRUSH_API_KEY is not set")
    q = urllib.parse.urlencode({**params, "key": key})
    url = f"https://api.semrush.com/?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "foundayo-sentinel/1.0"})
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
    for filt in ("+|Ph|Co|foundayo", "+|Ph|Co|orforglipron"):
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
            for filt in ("+|Ph|Co|foundayo", "+|Ph|Co|orforglipron"):
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


def build_snapshot(rows: list, comp: dict, mode: str = "semrush") -> dict:
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

    hero_kw = best.get("foundayo")
    hero_pos = hero_kw["p"] if hero_kw else None

    orfog_kw = best.get("orforglipron")
    orfog_pos = orfog_kw["p"] if orfog_kw else None

    flags = {
        "wrong": any(best[k] and best[k]["c"] != g and best[k]["c"] != "advice"
                     for k, g, _ in TRACKED if best[k]),
        "cann": sum(1 for k, _, _ in TRACKED if best[k] and best[k]["n"] > 1),
    }
    return {
        "date": today_uk(),
        "mode": mode,
        "best": best,
        "comp": comp,
        "m": {
            "foundayo": hero_pos,
            "orforglipron": orfog_pos,
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
    fp = cur["m"]["foundayo"]
    fp_prev = prev["m"]["foundayo"] if prev else None
    op = cur["m"]["orforglipron"]
    op_prev = prev["m"]["orforglipron"] if prev else None

    L = [f"FOUNDAYO SENTINEL -- {cur['date']}"
         + (f" ({cur['mode']} mode)" if cur["mode"] != "semrush" else "")]

    d_prev = (fp_prev - fp) if (fp is not None and fp_prev is not None) else None
    L.append(f"  foundayo: {'P' + str(fp) if fp else 'n/a'} ({arrow(d_prev)} vs prev)")
    d_prev2 = (op_prev - op) if (op is not None and op_prev is not None) else None
    L.append(f"  orforglipron: {'P' + str(op) if op else 'n/a'} ({arrow(d_prev2)} vs prev)")

    L.append("")
    L.append("TRACKED KEYWORDS:")
    L.append(f"  {'Keyword':<35} {'SOP':>5}  {'Superdrug':>10}  {'OxfordPh':>10}  {'Chem4U':>10}  {'IndepPh':>10}  {'Boots':>10}")
    L.append("  " + "-" * 100)
    comp = cur.get("comp", {})
    for kw, goal, baseline in TRACKED:
        sop = cur["best"].get(kw)
        sop_str = f"P{sop['p']}" if sop else "--"
        cols = [f"  {kw:<35} {sop_str:>5}"]
        for _, label in COMPETITORS:
            c = comp.get(label, {}).get(kw)
            cols.append(f"{('P' + str(c['p'])) if c else '--':>10}")
        L.append("  ".join(cols))

    if cur["flags"]["wrong"]:
        L.append(f"\n[!] Wrong-page routing detected -- day {streak(snaps, 'wrong')}")
    if cur["flags"]["cann"]:
        L.append(f"[*] {cur['flags']['cann']} keywords cannibalised (2+ URLs)")

    gaps = []
    for kw, goal, _ in TRACKED:
        if goal == "advice":
            continue
        sop = cur["best"].get(kw)
        sop_p = sop["p"] if sop else 999
        for _, label in COMPETITORS:
            c = comp.get(label, {}).get(kw)
            if c and c["p"] < sop_p:
                gaps.append((kw, label, c["p"], sop_p if sop_p < 999 else None))
    if gaps:
        L.append("\nCOMPETITIVE GAPS (competitors outranking SOP):")
        for kw, label, cp, sp in gaps:
            sop_str = f"P{sp}" if sp else "n/a"
            L.append(f"  {kw}: {label} P{cp} vs SOP {sop_str}")

    if fp is not None and fp <= 3:
        L.append("\n[TARGET] foundayo P1-3 secured.")
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


FIXTURE_ROWS = (
    "Keyword;Position;Search Volume;Url\n"
    "foundayo;1;1300;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss-pills/foundayo/\n"
    "foundayo;19;1300;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/foundayo/how-does-foundayo-work/\n"
    "foundayo;57;1300;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/foundayo/what-is-foundayo-orforglipron/\n"
    "foundayo pill;4;260;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss-pills/foundayo/\n"
    "foundayo pill;28;260;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/foundayo/foundayo-weight-loss-results/\n"
    "foundayo pill;89;260;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/foundayo/what-is-foundayo-orforglipron/\n"
    "orforglipron;17;5400;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/orforglipron/\n"
    "orforglipron;47;5400;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/what-is-orforglipron-weight-loss-pill/\n"
    "orforglipron uk;2;1600;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/orforglipron/\n"
    "orforglipron uk;24;1600;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/what-is-orforglipron-weight-loss-pill/\n"
    "orforglipron price;2;1000;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/orforglipron/\n"
    "orforglipron price;19;1000;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/what-is-orforglipron-weight-loss-pill/\n"
    "orforglipron tablet;5;590;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/orforglipron/\n"
    "orforglipron side effects;34;210;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/what-is-orforglipron-weight-loss-pill/\n"
    "orforglipron uk where to buy;1;140;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/orforglipron/\n"
    "orforglipron buy online;2;90;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/orforglipron/\n"
)

FIXTURE_COMP = {
    "Superdrug": {
        "orforglipron": {"p": 7, "u": "https://onlinedoctor.superdrug.com/orforglipron-glp-1-pill.html"},
        "orforglipron uk": {"p": 3, "u": "https://onlinedoctor.superdrug.com/orforglipron-glp-1-pill.html"},
        "orforglipron price": {"p": 4, "u": "https://onlinedoctor.superdrug.com/orforglipron-glp-1-pill.html"},
    },
    "OxfordPharm": {
        "orforglipron uk": {"p": 1, "u": "https://www.oxfordonlinepharmacy.co.uk/blog/when-will-orforglipron-be-available-in-the-uk"},
        "orforglipron": {"p": 4, "u": "https://www.oxfordonlinepharmacy.co.uk/blog/when-will-orforglipron-be-available-in-the-uk"},
    },
    "Chemist4U": {
        "orforglipron": {"p": 10, "u": "https://www.chemist-4-u.com/guides/weight-loss/what-is-orforglipron-new-uk-weight-loss-pill/"},
        "orforglipron uk": {"p": 7, "u": "https://www.chemist-4-u.com/guides/weight-loss/what-is-orforglipron-new-uk-weight-loss-pill/"},
    },
    "Boots": {
        "orforglipron uk": {"p": 14, "u": "https://onlinedoctor.boots.com/treatments/orforglipron"},
    },
}


def main():
    test = "--test" in sys.argv
    try:
        if test:
            rows = parse_rows(FIXTURE_ROWS)
            comp = FIXTURE_COMP
        else:
            rows = fetch_positions()
            comp = fetch_competitor_positions()
        snaps = load_history()
        snap = build_snapshot(rows, comp)
        snaps = [s for s in snaps if s["date"] != snap["date"]] + [snap]
        save_history(snaps)
        text = digest(snaps)
        print(text)
        if test:
            assert snap["m"]["foundayo"] == 1
            assert snap["m"]["orforglipron"] == 17
            assert snap["best"]["foundayo"]["n"] == 3, "foundayo should have 3 cannibalising URLs"
            assert snap["flags"]["cann"] > 0, "cannibalisation flag should fire"
            assert "Superdrug" in snap["comp"]
            print("\n[self-test] all assertions passed")
    except Exception as e:
        msg = f"FOUNDAYO SENTINEL FAILED -- {today_uk()}: {e}"
        print(msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
