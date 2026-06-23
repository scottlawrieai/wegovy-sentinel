#!/usr/bin/env python3
"""
Wegovy Sentinel — daily rank patrol for simpleonlinepharmacy.co.uk
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

DOMAIN = "www.simpleonlinepharmacy.co.uk"
PILL_PAGE = "https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss-pills/wegovy-pills/"
DATA = os.path.join(os.path.dirname(__file__), "data", "snapshots.json")
DOCS = os.path.join(os.path.dirname(__file__), "docs", "snapshots.json")
BASE_DATE = "2026-06-10"
BL_TARGET = 15

TRACKED = [
    ("wegovy pill", "pill", 26),
    ("wegovy pills", "pill", 25),
    ("wegovy tablets", "pill", 43),
    ("wegovy pill uk", "pill", 20),
    ("buy wegovy pills", "pill", None),
    ("oral semaglutide", "pill", None),
    ("buy wegovy", "injection", 9),
    ("buy wegovy online", "injection", 14),
    ("buy wegovy uk", "injection", 9),
    ("where can i buy wegovy uk", "injection", 7),
]


def classify(url: str) -> str:
    s = (url or "").lower()
    if "weight-loss-pills/wegovy-pills" in s:
        return "pill"
    if "medications/wegovy" in s:
        return "legacy"
    if "online-doctor/weight-loss/wegovy" in s:
        return "legacy"
    if "/weight-loss/wegovy" in s:
        return "injection"
    if "health-advice" in s:
        return "advice"
    return "other"


def today_uk() -> str:
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def semrush(params: dict) -> str:
    key = os.environ.get("SEMRUSH_API_KEY", "")
    if not key:
        raise RuntimeError("SEMRUSH_API_KEY is not set")
    q = urllib.parse.urlencode({**params, "key": key})
    url = f"https://api.semrush.com/?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "wegovy-sentinel/1.0"})
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


def build_snapshot(rows: list, bl: dict, mode: str = "semrush") -> dict:
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
    bw_inj = [r["p"] for r in clean if r["k"] == "buy wegovy" and r["c"] == "injection"]
    flags = {
        "wrong": any(best[k] and best[k]["c"] == "pill"
                     for k, g, _ in TRACKED if g == "injection"),
        "legacy": any(r["c"] == "legacy" for r in clean),
        "cann": sum(1 for k, _, _ in TRACKED if best[k] and best[k]["n"] > 1),
    }
    return {
        "date": today_uk(),
        "mode": mode,
        "best": best,
        "m": {
            "pill": best["wegovy pill"]["p"] if best["wegovy pill"] else None,
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
        return "-"
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
    d_base = (26 - pill) if pill is not None else None
    line = f"wegovy pill: {'P' + str(pill) if pill else 'n/a'} ({arrow(d_prev)} vs prev / {arrow(d_base)} vs baseline P26)"
    if pill is not None and pill <= 10:
        line += " -- PAGE ONE"
    L.append(line)
    bw = cur["best"].get("buy wegovy")
    if bw:
        tag = " ** WRONG PAGE **" if bw["c"] == "pill" else ""
        L.append(f"buy wegovy: P{bw['p']} via {bw['c'].upper()}{tag}"
                 + (f" (injection: P{cur['m']['bwInj']})" if cur["m"]["bwInj"] else ""))
    if cur["flags"]["wrong"]:
        L.append(f"[!] Wrong-page routing live -- day {streak(snaps, 'wrong')}")
    if cur["flags"]["legacy"]:
        L.append(f"[!] Legacy URL still ranking -- day {streak(snaps, 'legacy')}")
    if cur["flags"]["cann"]:
        L.append(f"[*] {cur['flags']['cann']} keywords cannibalised (2+ URLs)")
    L.append(f"Backlinks to pill page: {cur['m']['blD']} referring domains (target {BL_TARGET})")
    if pill is not None and pill <= 3:
        L.append("TARGET ACHIEVED -- P1-3. Hold through MHRA decision.")
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
    "buy wegovy;9;2400;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss-pills/wegovy-pills/\n"
    "buy wegovy;13;2400;https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy/\n"
    "wegovy pill;26;2900;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss-pills/wegovy-pills/\n"
    "buy wegovy uk;9;880;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/wegovy/\n"
)


def main():
    test = "--test" in sys.argv
    try:
        if test:
            rows, bl = parse_rows(FIXTURE_ROWS), {"t": 0, "d": 0}
        else:
            rows, bl = fetch_positions(), fetch_backlinks()
        snaps = load_history()
        snap = build_snapshot(rows, bl)
        snaps = [s for s in snaps if s["date"] != snap["date"]] + [snap]
        save_history(snaps)
        text = digest(snaps)
        print(text)
        if test:
            assert snap["flags"]["wrong"], "wrong-page flag should fire"
            assert snap["flags"]["legacy"], "legacy flag should fire"
            assert snap["m"]["pill"] == 26
            print("\n[self-test] all assertions passed")
    except Exception as e:
        msg = f"WEGOVY SENTINEL FAILED -- {today_uk()}: {e}"
        print(msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
