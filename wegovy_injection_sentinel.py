#!/usr/bin/env python3
"""
Wegovy Injection Sentinel — daily rank patrol for simpleonlinepharmacy.co.uk
Tracks Wegovy (semaglutide injection) keyword positions for SOP + 5
competitors, product-page backlinks, structural audit flags and competitive
gap, appends to snapshot history, and prints a digest.

Reuses the wegovy machinery: sentinel.semrush/parse_rows for API access,
rank_sources for GSC/AWR/GA4, tech_audit/link_gap/content_audit enrichments.
Snapshot shape mirrors sentinel.py exactly so the dashboard renders it
unchanged.

Env:
  SEMRUSH_API_KEY    required (semrush.com -> Profile -> API)
Run:
  python wegovy_injection_sentinel.py            # live patrol
  python wegovy_injection_sentinel.py --test     # offline self-test with canned data
"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import sentinel

DOMAIN = "www.simpleonlinepharmacy.co.uk"
PRODUCT_PAGE = "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy/"
DATA = os.path.join(os.path.dirname(__file__), "data",
                    "wegovy_injection_snapshots.json")
DOCS = os.path.join(os.path.dirname(__file__), "docs",
                    "wegovy_injection_snapshots.json")
BL_TARGET = 15
HERO_KW = "wegovy"

# kw, goal page class, baseline position
TRACKED = [
    ("wegovy", "product", None),
    ("wegovy uk", "product", None),
    ("buy wegovy", "product", None),
    ("buy wegovy uk", "product", None),
    ("buy wegovy online", "product", None),
    ("wegovy injection", "product", None),
    ("wegovy injections", "product", None),
    ("wegovy pen", "product", None),
    ("wegovy price", "product", None),
    ("wegovy price uk", "product", None),
    ("cheapest wegovy uk", "product", None),
    ("semaglutide injection", "product", None),
    ("wegovy side effects", "advice", None),
    ("wegovy dosage", "advice", None),
    ("wegovy vs mounjaro", "advice", None),
    ("wegovy reviews", "advice", None),
    ("wegovy weight loss", "advice", None),
]

COMPETITORS = [
    ("onlinedoctor.superdrug.com", "Superdrug"),
    ("chemist-4-u.com", "Chemist4U"),
    ("thefamilychemist.co.uk", "FamilyChemist"),
    ("medexpress.co.uk", "MedExpress"),
    ("onlinedoctor.boots.com", "Boots"),
]

# Curated semantic/medical lexicon for the semaglutide-injection topic; same
# tuple format as content_audit.LEXICON: (label, category, variants, is_entity).
WEGOVY_INJECTION_LEXICON = [
    ("semaglutide", "mechanism", ["semaglutide"], False),
    ("GLP-1 receptor agonist", "mechanism",
     ["glp-1 receptor agonist", "glp-1 agonist", "receptor agonist"], False),
    ("GLP-1", "mechanism", ["glp-1", "glp 1", "glp1"], False),
    ("appetite suppression", "mechanism",
     ["appetite", "less hungry", "reduce hunger", "hunger"], False),

    ("0.25 mg starting dose", "dosing",
     ["0.25mg", "0.25 mg", "starting dose"], False),
    ("2.4 mg maintenance dose", "dosing", ["2.4mg", "2.4 mg"], False),
    ("maintenance dose", "dosing", ["maintenance dose"], False),
    ("dose escalation / titration", "dosing",
     ["titration", "dose escalation", "increase the dose", "0.5mg", "0.5 mg",
      "1mg", "1 mg", "1.7mg", "1.7 mg"], False),
    ("weekly injection", "dosing",
     ["weekly injection", "once a week", "once-weekly", "once weekly",
      "every week"], False),
    ("injection site rotation", "dosing",
     ["injection site", "rotate", "thigh", "abdomen", "upper arm"], False),
    ("missed dose", "dosing",
     ["missed dose", "miss a dose", "forget a dose", "forgotten dose"], False),
    ("fridge / storage", "dosing",
     ["fridge", "refrigerate", "refrigerator", "cold storage", "storage"], False),
    ("FlexTouch pen", "device", ["flextouch", "flex touch"], True),
    ("pre-filled pen", "device",
     ["pre-filled pen", "prefilled pen", "pre filled pen"], False),
    ("needle", "device", ["needle", "needles"], False),

    ("STEP trials", "evidence",
     ["step 1", "step-1", "step trial", "step trials"], True),
    ("weight loss %", "evidence",
     ["15%", "16%", "17%", "% of their body weight", "body weight"], False),

    ("Novo Nordisk", "regulatory", ["novo nordisk", "novo"], True),
    ("prescription-only", "regulatory",
     ["prescription-only", "prescription only", "requires a prescription",
      "prescribed", "pom"], False),
    ("nausea", "safety",
     ["nausea", "vomiting", "diarrhoea", "diarrhea", "constipation"], False),
    ("side effects", "safety",
     ["side effects", "side-effects", "adverse effects"], False),
    ("pancreatitis", "safety", ["pancreatitis"], False),
    ("thyroid warning", "safety",
     ["thyroid", "medullary thyroid", "mtc"], False),
    ("pregnancy warning", "safety",
     ["pregnancy", "pregnant", "breastfeeding", "conceive"], False),
    ("BMI eligibility", "safety",
     ["bmi", "body mass index", "27 kg", "30 kg", "comorbidity",
      "weight-related condition"], False),

    ("Ozempic", "comparison", ["ozempic"], True),
    ("Rybelsus", "comparison", ["rybelsus"], True),

    ("private prescription", "commercial",
     ["private prescription", "private online"], False),
    ("price per month", "commercial",
     ["per month", "monthly cost", "price", "cost", "£", "cheapest",
      "how much"], False),
    ("clinician review", "commercial",
     ["clinician", "prescriber", "online consultation", "consultation",
      "assessment", "online doctor"], False),
]


def classify(url: str) -> str:
    s = (url or "").lower()
    if "health-advice" in s:
        return "advice"
    # Sibling and legacy paths contain "/weight-loss/wegovy" as a substring,
    # so they must be tested before the product-page check (same ordering
    # convention as sentinel.py).
    if "/weight-loss/wegovy-pill" in s:
        return "pill"
    if "/weight-loss-pills/wegovy-pills" in s:
        return "legacy"
    if "/medications/wegovy" in s:
        return "legacy"
    if "/online-doctor/weight-loss/wegovy" in s:   # pre-migration URL
        return "legacy"
    if "/weight-loss/wegovy" in s:
        return "product"
    return "other"


def today_uk() -> str:
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def fetch_positions() -> list:
    rows = []
    for filt in ("+|Ph|Co|wegovy", "+|Ph|Co|semaglutide"):
        rows += sentinel.parse_rows(sentinel.semrush({
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
                rows += sentinel.parse_rows(sentinel.semrush({
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
        # Backlink reports live on the analytics/v1 endpoint (root returns 400).
        text = sentinel.semrush({
            "type": "backlinks_overview",
            "target": PRODUCT_PAGE,
            "target_type": "url",
            "export_columns": "total,domains_num",
        }, base="https://api.semrush.com/analytics/v1/")
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


def fetch_kw_meta() -> dict:
    """Volume + SERP features for every tracked keyword in one call
    (phrase_these: a row per phrase regardless of whether we rank)."""
    try:
        phrases = ";".join(kw for kw, _, _ in TRACKED)
        text = sentinel.semrush({
            "type": "phrase_these",
            "phrase": phrases,
            "database": "uk",
            "export_columns": "Ph,Nq,Fk",
        })
        out = {}
        lines = [l for l in text.splitlines() if l.strip()]
        if len(lines) < 2:
            return {}
        cols = [c.strip().lower() for c in lines[0].split(";")]
        ki = next(i for i, c in enumerate(cols) if c.startswith("keyword"))
        vi = next((i for i, c in enumerate(cols) if "volume" in c), None)
        fi = next((i for i, c in enumerate(cols) if "feature" in c), None)
        for line in lines[1:]:
            parts = line.split(";")
            try:
                kw = parts[ki].strip().lower()
                v = int(parts[vi]) if vi is not None and parts[vi].strip().isdigit() else 0
                feats = []
                if fi is not None and fi < len(parts):
                    feats = [int(x) for x in parts[fi].strip().split(",")
                             if x.strip().isdigit()]
                out[kw] = {"v": v, "feat": feats}
            except (IndexError, ValueError):
                continue
        return out
    except Exception as e:
        print(f"[warn] keyword meta unavailable: {e}", file=sys.stderr)
        return {}


def fetch_extra_sources() -> dict:
    """Pull GSC + AWR + GA4 (optional, credential-gated). Never fatal.

    Unlike sentinel.py this skips gsci -- the insights analysis is
    pill-page specific (v1)."""
    import rank_sources
    kws = [kw for kw, _, _ in TRACKED]
    src = {"gsc": {}, "awr": {}, "gscts": {}, "gscq": {}, "gsckw": {}, "ga4": {},
           "ga4rev": {}}
    try:
        src["ga4rev"] = rank_sources.fetch_ga4_revenue(page_url=PRODUCT_PAGE)
    except Exception as e:
        print(f"[warn] GA4 revenue unavailable: {e}", file=sys.stderr)
    try:
        src["ga4"] = rank_sources.fetch_ga4(page_url=PRODUCT_PAGE)
    except Exception as e:
        print(f"[warn] GA4 unavailable: {e}", file=sys.stderr)
    try:
        src["gscts"] = rank_sources.fetch_gsc_timeseries(page_url=PRODUCT_PAGE)
    except Exception as e:
        print(f"[warn] GSC time series unavailable: {e}", file=sys.stderr)
    try:
        src["gscq"] = rank_sources.fetch_gsc_queries(page_url=PRODUCT_PAGE)
    except Exception as e:
        print(f"[warn] GSC queries unavailable: {e}", file=sys.stderr)
    try:
        src["gsckw"] = rank_sources.fetch_gsc_keyword_series(kws)
    except Exception as e:
        print(f"[warn] GSC keyword series unavailable: {e}", file=sys.stderr)
    try:
        src["gsc"] = rank_sources.fetch_gsc(kws)
    except Exception as e:
        print(f"[warn] GSC unavailable: {e}", file=sys.stderr)
    try:
        # This product can track its keywords in its own AWR project; without
        # the dedicated variable it falls back to the shared AWR_PROJECT.
        _proj = os.environ.get("AWR_PROJECT_INJECTION") or "SOP - Wegovy - Weekly"
        if _proj:
            os.environ["AWR_PROJECT"] = _proj
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
                    "n": len({h["u"] for h in hits}), "v": top.get("v", 0)}

    hero = best.get(HERO_KW)
    hero_pos = hero["p"] if hero else None

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
        "gscts": src.get("gscts", {}),
        "gscq": src.get("gscq", {}),
        "gsckw": src.get("gsckw", {}),
        "ga4": src.get("ga4", {}),
        "ga4rev": src.get("ga4rev", {}),
        "m": {
            "pill": hero_pos,           # hero "wegovy" position
            "bwInj": None,              # no injection/product split here
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
    hero = cur["m"]["pill"]
    hero_prev = prev["m"]["pill"] if prev else None
    L = [f"WEGOVY INJECTION SENTINEL -- {cur['date']}"
         + (f" ({cur['mode']} mode)" if cur["mode"] != "semrush" else "")]

    d_prev = (hero_prev - hero) if (hero is not None and hero_prev is not None) else None
    line = f"  wegovy: position {hero if hero else 'n/a'} ({arrow(d_prev)} vs prev)"
    if hero is not None and hero <= 10:
        line += " -- PAGE ONE"
    L.append(line)

    L.append("")
    L.append("TRACKED KEYWORDS (SOP across sources -- lower is better):")
    L.append(f"  {'Keyword':<30} {'Semrush':>7} {'AWR':>5}  "
             f"{'Superdrug':>11}  {'Chemist4U':>11}  {'FamilyChemist':>13}  {'MedExpress':>11}  {'Boots':>7}")
    L.append("  " + "-" * 115)
    comp = cur.get("comp", {})
    gsc = cur.get("src", {}).get("gsc", {})
    awr = cur.get("src", {}).get("awr", {})
    for kw, goal, baseline in TRACKED:
        sop = cur["best"].get(kw)
        sop_str = str(sop['p']) if sop else "--"
        a = awr.get(kw)
        awr_str = str(a) if a else "--"
        cols = [f"  {kw:<30} {sop_str:>7} {awr_str:>5}"]
        for (_, label), w in zip(COMPETITORS, (11, 11, 13, 11, 7)):
            c = comp.get(label, {}).get(kw)
            cols.append(f"{str(c['p']) if c else '--':>{w}}")
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

    L.append(f"\nBacklinks to product page: {cur['m']['blD']} referring domains (target {BL_TARGET})")

    tech = cur.get("tech") or {}
    if tech.get("checks"):
        L.append(f"\nTECH HEALTH (product page): {tech['score']}/{tech['of']} checks pass")
        for c in tech["checks"]:
            if c["state"] != "pass":
                L.append(f"  [{c['state'].upper()}] {c['name']}: {c['evidence']}")

    psi = cur.get("psi") or {}
    if psi.get("score") is not None and psi:
        f = psi.get("field", {})
        field_txt = (f"  |  real users: LCP {f['lcp_ms']}ms ({f.get('lcp_ms_cat', '')})"
                     if f.get("lcp_ms") else "")
        L.append(f"\nPAGESPEED (product page, {psi.get('strategy', 'mobile')}): "
                 f"Lighthouse {psi.get('score', '--')}/100  "
                 f"LCP {psi.get('lcp', '--')}  CLS {psi.get('cls', '--')}  "
                 f"TBT {psi.get('tbt', '--')}{field_txt}")

    links = cur.get("links") or {}
    if links.get("prospects"):
        L.append(f"\nLINK PROSPECTS (link to competitors' wegovy pages, not ours -- we have "
                 f"{links.get('ours', 0)} refdomains):")
        for p in links["prospects"][:10]:
            L.append(f"  {p['d']}  (links to {p['n']}: {', '.join(p['who'])})")

    gaps = []
    for kw, goal, _ in TRACKED:
        if goal != "product":
            continue
        sop = cur["best"].get(kw)
        sop_p = sop["p"] if sop else 999
        for _, label in COMPETITORS:
            c = comp.get(label, {}).get(kw)
            if c and c["p"] < sop_p:
                gaps.append((kw, label, c["p"], sop_p if sop_p < 999 else None))
    if gaps:
        L.append("\nCOMPETITIVE GAPS (product keywords where competitors outrank SOP):")
        for kw, label, cp, sp in gaps:
            sop_str = str(sp) if sp else "n/a"
            L.append(f"  {kw}: {label} {cp} vs SOP {sop_str}")

    if hero is not None and hero <= 3:
        L.append("\n[TARGET] Top-3 achieved for wegovy. Hold position.")
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
    "wegovy;4;368000;https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy/\n"
    "wegovy uk;6;60500;https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/\n"
    "buy wegovy;5;9900;https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy/\n"
    "wegovy price;9;8100;https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/wegovy/\n"
    "wegovy dosage;3;12100;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy/wegovy-dosage/\n"
    "wegovy side effects;7;14800;https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy/wegovy-side-effects/\n"
    "semaglutide injection;11;4400;https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy/\n"
)

FIXTURE_COMP = {
    "Superdrug": {
        "wegovy": {"p": 2, "u": "https://onlinedoctor.superdrug.com/wegovy.html"},
        "wegovy uk": {"p": 3, "u": "https://onlinedoctor.superdrug.com/wegovy.html"},
        "buy wegovy": {"p": 6, "u": "https://onlinedoctor.superdrug.com/wegovy.html"},
    },
    "Chemist4U": {
        "wegovy": {"p": 8, "u": "https://www.chemist-4-u.com/wegovy"},
        "wegovy pen": {"p": 5, "u": "https://www.chemist-4-u.com/wegovy"},
    },
    "MedExpress": {
        "wegovy": {"p": 12, "u": "https://www.medexpress.co.uk/clinics/weight-loss/wegovy"},
    },
    "Boots": {
        "wegovy uk": {"p": 9, "u": "https://onlinedoctor.boots.com/treatments/wegovy"},
    },
}

FIXTURE_KWMETA = {
    "wegovy": {"v": 368000, "feat": [11, 21, 22]},
    "wegovy price": {"v": 8100, "feat": [21]},
    "semaglutide injection": {"v": 4400, "feat": [11]},
}

FIXTURE_SRC = {
    "gsc": {"wegovy": {"pos": 4.6, "clicks": 880, "impr": 41000, "ctr": 2.1}},
    "awr": {"wegovy": 4, "wegovy uk": 7},
    "gscts": {}, "gsckw": {}, "ga4": {},
}


def main():
    test = "--test" in sys.argv
    try:
        if test:
            rows = sentinel.parse_rows(FIXTURE_ROWS)
            bl = {"t": 3, "d": 2}
            comp = FIXTURE_COMP
            src = FIXTURE_SRC
        else:
            rows = fetch_positions()
            bl = fetch_backlinks()
            comp = fetch_competitor_positions()
            src = fetch_extra_sources()
        snaps = load_history()
        snap = build_snapshot(rows, bl, comp, src)

        # Keyword meta: search volume + SERP feature codes per tracked keyword.
        snap["kwmeta"] = (FIXTURE_KWMETA if test else fetch_kw_meta())
        if not snap.get("kwmeta"):
            for prev_s in reversed(snaps):
                if prev_s.get("kwmeta"):
                    snap["kwmeta"] = prev_s["kwmeta"]
                    break

        # Technical self-audit + backlink gap (non-fatal enrichments).
        import link_gap
        import tech_audit
        try:
            snap["tech"] = (tech_audit.run(pill_url=PRODUCT_PAGE,
                                           fetch_fn=tech_audit._fixture_fetch)
                            if test else tech_audit.run(pill_url=PRODUCT_PAGE))
        except Exception as e:
            print(f"[warn] tech audit unavailable: {e}", file=sys.stderr)
        try:
            snap["psi"] = (tech_audit.FIXTURE_PSI if test
                           else tech_audit.fetch_psi(PRODUCT_PAGE))
        except Exception as e:
            print(f"[warn] pagespeed unavailable: {e}", file=sys.stderr)
        try:
            comp_urls = {label: comp.get(label, {}).get(HERO_KW, {}).get("u", "")
                         for _, label in COMPETITORS}
            snap["links"] = link_gap.build(
                link_gap._fixture_semrush if test else sentinel.semrush,
                PRODUCT_PAGE, comp_urls)
        except Exception as e:
            print(f"[warn] link gap unavailable: {e}", file=sys.stderr)

        # A PSI failure must not blank the speed card -- carry forward.
        if not snap.get("psi"):
            for prev_s in reversed(snaps):
                if prev_s.get("psi"):
                    snap["psi"] = {**prev_s["psi"],
                                   "as_of": prev_s["psi"].get("as_of", prev_s["date"])}
                    break

        # A patrol without GSC credentials must not blank the Search Console
        # panels -- carry forward the last known data (stamped with its date).
        if not snap.get("gscts"):
            for prev_s in reversed(snaps):
                g = prev_s.get("gscts")
                if g:
                    snap["gscts"] = {**g, "as_of": g.get("as_of", prev_s["date"])}
                    break
        if not snap.get("gscq"):
            for prev_s in reversed(snaps):
                g = prev_s.get("gscq")
                if g:
                    snap["gscq"] = g
                    break
        if not snap.get("gsckw"):
            for prev_s in reversed(snaps):
                g = prev_s.get("gsckw")
                if g:
                    snap["gsckw"] = {**g, "as_of": g.get("as_of", prev_s["date"])}
                    break
        if not snap.get("ga4"):
            for prev_s in reversed(snaps):
                g = prev_s.get("ga4")
                if g:
                    snap["ga4"] = g
                    break
        if not snap.get("ga4rev"):
            for prev_s in reversed(snaps):
                g = prev_s.get("ga4rev")
                if g:
                    snap["ga4rev"] = g
                    break
        if not snap.get("src", {}).get("gsc"):
            for prev_s in reversed(snaps):
                g = prev_s.get("src", {}).get("gsc")
                if g:
                    snap["src"]["gsc"] = g
                    break

        snaps = [s for s in snaps if s["date"] != snap["date"]] + [snap]
        if not test:
            save_history(snaps)   # never overwrite real history during a self-test
        text = digest(snaps)
        print(text)

        # Daily content review (on-page gap analysis). Non-fatal: a failure
        # here must never break the rank patrol. configure() MUST run before
        # run_and_store so the audit targets the injection page, not the
        # wegovy-pill defaults.
        content_text = ""
        try:
            import content_audit
            content_audit.configure(
                PHRASE="wegovy",
                OUR_PAGE=PRODUCT_PAGE,
                PRIMARY=["wegovy", "buy wegovy", "wegovy uk"],
                SECONDARY=["wegovy price", "wegovy injection", "wegovy pen",
                           "semaglutide", "buy wegovy online"],
                LEXICON=WEGOVY_INJECTION_LEXICON,
                DATA=os.path.join(os.path.dirname(__file__),
                                  "data", "wegovy_injection_content.json"),
                DOCS=os.path.join(os.path.dirname(__file__),
                                  "docs", "wegovy_injection_content.json"),
            )
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
            sentinel.post_slack(text + ("\n" + content_text if content_text else ""))

        if test:
            # classify() routes all five page classes correctly
            assert classify(PRODUCT_PAGE) == "product"
            assert classify("https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/") == "pill"
            assert classify("https://www.simpleonlinepharmacy.co.uk/online-doctor/weight-loss/wegovy/") == "legacy"
            assert classify("https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy/wegovy-dosage/") == "advice"
            assert classify("https://www.simpleonlinepharmacy.co.uk/") == "other"
            assert snap["best"]["wegovy"]["c"] == "product", snap["best"]["wegovy"]
            # pill sibling ranking for a product keyword -> "pill" + wrong-page
            assert snap["best"]["wegovy uk"]["c"] == "pill", snap["best"]["wegovy uk"]
            assert snap["flags"]["wrong"], "pill sibling URL should count as wrong-page"
            assert snap["best"]["wegovy price"]["c"] == "legacy", snap["best"]["wegovy price"]
            assert snap["best"]["wegovy dosage"]["c"] == "advice", snap["best"]["wegovy dosage"]
            assert snap["flags"]["legacy"], "legacy fixture URL should raise the flag"
            # hero best parsed with volume
            assert snap["m"]["pill"] == 4, snap["m"]
            assert snap["best"]["wegovy"]["v"] == 368000, snap["best"]["wegovy"]
            # competitors present
            assert "Superdrug" in snap["comp"]
            assert snap["comp"]["Superdrug"]["wegovy"]["p"] == 2
            # kwmeta volume present
            assert snap["kwmeta"]["wegovy"]["v"] == 368000
            # snapshot keys superset (dashboard contract)
            need = {"date", "best", "comp", "m", "flags", "gscts", "gsckw",
                    "kwmeta", "ga4rev"}
            assert need <= set(snap.keys()), need - set(snap.keys())
            print("\n[self-test] all assertions passed")
    except Exception as e:
        msg = f"WEGOVY INJECTION SENTINEL FAILED -- {today_uk()}: {e}"
        print(msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
