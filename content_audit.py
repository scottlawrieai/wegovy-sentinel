#!/usr/bin/env python3
"""
Wegovy Sentinel -- content audit ("daily review update").

Companion to sentinel.py. Where sentinel.py tracks *rank positions*, this module
measures *on-page content* for the "wegovy pill" SERP: it pulls the live top-N
organic results from Semrush, fetches each page plus our own pill page, and
compares them to expose keyword/semantic gaps, missing entities, FAQ gaps and
how well our page is aligned for the target terms.

Optimises for: "wegovy pill", "buy wegovy pill", "wegovy pill uk"
(secondary: wegovy pills/tablets, oral semaglutide, oral wegovy).

Design notes
------------
* Standard library only (urllib + html.parser), to match sentinel.py and run
  unchanged in the GitHub Actions daily patrol.
* The top-N is pulled fresh from Semrush each run, so the audit tracks whoever
  is actually ranking for "wegovy pill" -- which is NOT the same set as the
  rank-tracker's hardcoded competitors (e.g. Voy, Pharmica, Boots).
* Competitor pages sit behind bot protection (Cloudflare/Akamai) that returns
  403 to non-browser agents. We send a realistic browser User-Agent and degrade
  gracefully: a page that can't be fetched is marked "blocked" and skipped, the
  audit still completes on whatever pages succeed (our own page always does).

Run:
  python content_audit.py            # live audit (needs SEMRUSH_API_KEY)
  python content_audit.py --test     # offline self-test on canned fixtures
  python content_audit.py --seed     # write a seed snapshot from canned data
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

PHRASE = "wegovy pill"
DATABASE = "uk"
TOP_N = 6
OUR_DOMAIN = "simpleonlinepharmacy.co.uk"
OUR_PAGE = "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/"

DATA = os.path.join(os.path.dirname(__file__), "data", "content.json")
DOCS = os.path.join(os.path.dirname(__file__), "docs", "content.json")
HISTORY_KEEP = 30
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Target search terms we want the pill page to win.
PRIMARY = ["wegovy pill", "buy wegovy pill", "wegovy pill uk"]
SECONDARY = ["wegovy pills", "buy wegovy pills", "wegovy tablets",
             "oral semaglutide", "oral wegovy", "semaglutide tablets",
             "wegovy oral tablet"]

# Curated semantic/medical lexicon for the oral-semaglutide topic, grounded in
# the live top-5 (Superdrug, Voy, Pharmica, Boots, Wegovy.com). Each canonical
# label maps to the surface variants that count as a "hit". `entity` flags named
# entities (brands, trials, compounds) reported separately as entity gaps.
LEXICON = [
    # label, category, variants, is_entity
    ("semaglutide", "mechanism", ["semaglutide"], False),
    ("oral semaglutide", "mechanism", ["oral semaglutide"], False),
    ("GLP-1 receptor agonist", "mechanism",
     ["glp-1 receptor agonist", "glp 1 receptor agonist", "glp-1 agonist",
      "glp1 receptor agonist", "glp-1 ra"], False),
    ("GLP-1", "mechanism", ["glp-1", "glp 1", "glp1"], False),
    ("appetite suppression", "mechanism",
     ["appetite", "less hungry", "reduce hunger", "hunger"], False),
    ("satiety / fullness", "mechanism",
     ["fullness", "feel full", "feeling full", "satiety", "fuller for longer"], False),
    ("slows gastric emptying", "mechanism",
     ["gastric emptying", "stomach emptying", "slows digestion", "delays gastric"], False),
    ("incretin / gut hormone", "mechanism", ["incretin", "gut hormone"], False),
    ("blood sugar", "mechanism",
     ["blood sugar", "blood glucose", "glycaemic", "glycemic"], False),

    ("dose escalation / titration", "dosing",
     ["dose escalation", "titration", "increase the dose", "1.5mg", "1.5 mg",
      "3mg", "4mg", "9mg", "14mg"], False),
    ("25 mg maintenance dose", "dosing", ["25mg", "25 mg"], False),
    ("once daily", "dosing",
     ["once daily", "once a day", "daily tablet", "every morning", "once per day"], False),
    ("empty stomach", "dosing",
     ["empty stomach", "before food", "fasted", "on an empty"], False),
    ("120ml water rule", "dosing",
     ["120ml", "120 ml", "half a glass", "plain water"], False),
    ("30-minute wait / fast", "dosing",
     ["30 minutes", "30-minute", "thirty minutes", "wait 30", "fast for 30"], False),
    ("absorption enhancer", "dosing",
     ["absorption enhancer", "salcaprozate", "caprylate", "sodium n-"], False),
    ("SNAC", "dosing", ["snac"], True),

    ("OASIS trial", "evidence", ["oasis 4", "oasis trial", "oasis"], True),
    ("headline % weight loss", "evidence",
     ["16.6%", "16.6 %", "13.6%", "15%", "16%", "17%"], False),
    ("clinical trial evidence", "evidence",
     ["clinical trial", "clinically proven", "study found", "trial showed", "studies"], False),
    ("trial duration (weeks)", "evidence",
     ["64 weeks", "68 weeks", "over 64", "over 68"], False),
    ("% of body weight", "evidence",
     ["body weight", "percent of body weight", "% of their body weight"], False),

    ("MHRA approval", "regulatory", ["mhra"], True),
    ("FDA approval", "regulatory", ["fda"], True),
    ("prescription-only", "regulatory",
     ["prescription-only", "prescription only", "requires a prescription",
      "prescribed", "pom"], False),
    ("Novo Nordisk", "regulatory", ["novo nordisk"], True),
    ("side effects", "safety", ["side effects", "side-effects", "adverse effects"], False),
    ("GI side effects", "safety",
     ["nausea", "vomiting", "diarrhoea", "diarrhea", "constipation"], False),
    ("BMI eligibility", "safety",
     ["bmi", "body mass index", "27 kg", "30 kg", "comorbidity", "weight-related condition"], False),
    ("contraindications", "safety",
     ["contraindication", "not suitable", "should not take", "pregnancy", "pancreatitis"], False),
    ("cardiovascular benefit", "safety",
     ["cardiovascular", "heart health", "heart attack", "stroke"], False),

    ("vs injection", "comparison",
     ["vs injection", "versus injection", "pill vs injection", "injection or pill",
      "compared to the injection", "pill or injection"], False),
    ("Wegovy injection", "comparison",
     ["wegovy injection", "weekly injection", "subcutaneous"], False),
    ("Ozempic", "comparison", ["ozempic"], True),
    ("Mounjaro / tirzepatide", "comparison", ["mounjaro", "tirzepatide"], True),
    ("Rybelsus", "comparison", ["rybelsus"], True),
    ("orforglipron / Foundayo", "comparison", ["orforglipron", "foundayo"], True),
    ("orlistat", "comparison", ["orlistat"], True),
    ("Saxenda / liraglutide", "comparison", ["saxenda", "liraglutide"], True),

    ("buy intent", "commercial",
     ["buy wegovy pill", "buy wegovy", "buy online", "order online", "order now"], False),
    ("price / cost", "commercial",
     ["price", "cost", "£", "cheapest", "how much"], False),
    ("UK availability", "commercial",
     ["in the uk", "uk availability", "available in the uk", "united kingdom"], False),
    ("NHS", "commercial", ["nhs"], True),
    ("online consultation", "commercial",
     ["online doctor", "consultation", "prescriber", "assessment", "clinician"], False),
    ("delivery", "commercial",
     ["delivery", "next day", "discreet", "free delivery"], False),
]

STOP = set("""a an and are as at be by for from has have how i in is it its of on or
that the to was were what when where which who why will with your you our we us this
these those they their them he she his her not but if then than so can could should
would may might do does did done about into over under more most some any all each
about www com co uk html https http page pill pills wegovy weight loss""".split())


# ----------------------------------------------------------------------------- IO
def today_uk() -> str:
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def _default_semrush(params: dict) -> str:
    key = os.environ.get("SEMRUSH_API_KEY", "")
    if not key:
        raise RuntimeError("SEMRUSH_API_KEY is not set")
    q = urllib.parse.urlencode({**params, "key": key})
    req = urllib.request.Request("https://api.semrush.com/?" + q,
                                 headers={"User-Agent": "wegovy-sentinel/2.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    if text.startswith("ERROR"):
        if "NOTHING FOUND" in text:
            return ""
        raise RuntimeError(f"Semrush: {text.strip()[:120]}")
    return text


def fetch_html(url: str, timeout: int = 25) -> tuple:
    """Return (status, html). status is 'ok', 'blocked', or 'error:...'."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(3_000_000)
            enc = r.headers.get_content_charset() or "utf-8"
            return "ok", raw.decode(enc, "replace")
    except urllib.error.HTTPError as e:
        return ("blocked" if e.code in (401, 403, 406, 429, 503) else f"error:{e.code}"), ""
    except Exception as e:  # timeout, DNS, TLS, ...
        return f"error:{type(e).__name__}", ""


# ------------------------------------------------------------------------- parsing
SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"}
HEAD_TAGS = {"h1", "h2", "h3"}


class PageParser(HTMLParser):
    """Extract title, meta, headings, visible body text and FAQ blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta_desc = ""
        self.meta_robots = ""
        self.h1 = ""
        self.h2 = []
        self.h3 = []
        self.text_parts = []
        self.ld_json = []
        self.faq_questions = []
        self._skip = 0
        self._in_title = False
        self._in_ld = False
        self._cur_head = None
        self._head_buf = []
        self._in_summary = False
        self._sum_buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP_TAGS:
            if tag == "script" and a.get("type", "").lower() == "application/ld+json":
                self._in_ld = True
                return
            self._skip += 1
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in ("description", "og:description") and not self.meta_desc:
                self.meta_desc = (a.get("content") or "").strip()
            elif name == "robots":
                self.meta_robots = (a.get("content") or "").strip().lower()
        elif tag in HEAD_TAGS and not self._skip:
            self._cur_head = tag
            self._head_buf = []
        elif tag == "summary":
            self._in_summary = True
            self._sum_buf = []

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            if tag == "script" and self._in_ld:
                self._in_ld = False
                return
            if self._skip:
                self._skip -= 1
            return
        if tag == "title":
            self._in_title = False
        elif tag in HEAD_TAGS and self._cur_head == tag:
            txt = norm(" ".join(self._head_buf))
            if txt:
                if tag == "h1" and not self.h1:
                    self.h1 = txt
                elif tag == "h2":
                    self.h2.append(txt)
                elif tag == "h3":
                    self.h3.append(txt)
                if txt.endswith("?"):
                    self.faq_questions.append(txt)
            self._cur_head = None
        elif tag == "summary":
            self._in_summary = False
            txt = norm(" ".join(self._sum_buf))
            if txt.endswith("?"):
                self.faq_questions.append(txt)

    def handle_data(self, data):
        if self._in_ld:
            self.ld_json.append(data)
            return
        if self._in_title:
            self.title += data
            return
        if self._cur_head is not None:
            self._head_buf.append(data)
        if self._in_summary:
            self._sum_buf.append(data)
        if not self._skip:
            s = data.strip()
            if s:
                self.text_parts.append(s)

    def finish(self):
        self.title = norm(self.title)
        # FAQ schema (FAQPage JSON-LD) is the most reliable question source.
        for blob in self.ld_json:
            for q in ld_faq_questions(blob):
                if q not in self.faq_questions:
                    self.faq_questions.append(q)
        return self


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def ld_faq_questions(blob: str) -> list:
    out = []
    try:
        data = json.loads(blob)
    except Exception:
        return out
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Question" in types and node.get("name"):
                out.append(norm(str(node["name"])))
            stack.extend(v for v in node.values() if isinstance(v, (list, dict)))
    return out


def parse_page(html: str) -> PageParser:
    p = PageParser()
    try:
        p.feed(html)
    except Exception:
        pass
    return p.finish()


# ------------------------------------------------------------------------ analysis
def count_term(text_lc: str, variant: str) -> int:
    v = variant.lower()
    if not v:
        return 0
    if v.isalpha():  # whole-word match for plain words
        return len(re.findall(r"(?<![a-z])" + re.escape(v) + r"(?![a-z])", text_lc))
    return text_lc.count(v)


def lexicon_hits(text_lc: str) -> dict:
    """canonical label -> total variant hits (0 if absent)."""
    hits = {}
    for label, _cat, variants, _ent in LEXICON:
        hits[label] = sum(count_term(text_lc, v) for v in variants)
    return hits


def present_terms(hits: dict) -> set:
    return {k for k, v in hits.items() if v > 0}


def top_phrases(text_lc: str, n: int = 12) -> list:
    words = [w for w in re.findall(r"[a-z][a-z'-]{2,}", text_lc) if w not in STOP]
    grams = Counter()
    for size in (2, 3):
        for i in range(len(words) - size + 1):
            gram = " ".join(words[i:i + size])
            if not any(w in STOP for w in gram.split()):
                grams[gram] += 1
    return [g for g, c in grams.most_common(n) if c > 1]


def analyze(url: str, domain: str, rank, role: str, status: str, html: str) -> dict:
    if status != "ok" or not html:
        return {"url": url, "domain": domain, "rank": rank, "role": role,
                "status": status, "title": "", "meta": "", "h1": "",
                "h2": [], "wc": 0, "faqs": [], "terms": [], "phrases": []}
    p = parse_page(html)
    body = norm(" ".join(p.text_parts))
    body_lc = body.lower()
    title_lc = p.title.lower()
    hits = lexicon_hits((title_lc + " " + p.meta_desc.lower() + " " + body_lc))
    return {
        "url": url, "domain": domain, "rank": rank, "role": role, "status": "ok",
        "title": p.title, "meta": p.meta_desc, "robots": p.meta_robots,
        "h1": p.h1, "h2": p.h2[:25], "h3n": len(p.h3),
        "wc": len(body.split()),
        "faqs": dedupe(p.faq_questions)[:30],
        "open": " ".join(body.split()[:60]),
        "terms": sorted(present_terms(hits)),
        "termhits": {k: v for k, v in hits.items() if v > 0},
        "phrases": top_phrases(body_lc),
    }


def dedupe(seq: list) -> list:
    seen, out = set(), []
    for x in seq:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def term_in(text: str, terms: list) -> list:
    t = (text or "").lower()
    return [kw for kw in terms if kw in t]


def score_alignment(us: dict, competitors: list) -> dict:
    """SOP pill-page scorecard against the target terms and competitor coverage."""
    comp_ok = [c for c in competitors if c["status"] == "ok"]
    title = us.get("title", "")
    meta = us.get("meta", "")
    h1 = us.get("h1", "")
    opening = us.get("open", "")

    # competitor term coverage: a term "matters" if >=2 competitors use it
    comp_term_count = Counter()
    for c in comp_ok:
        for t in c["terms"]:
            comp_term_count[t] += 1
    important = {t for t, n in comp_term_count.items() if n >= 2}
    us_terms = set(us.get("terms", []))
    entity_labels = {label for label, _c, _v, ent in LEXICON if ent}
    # term gaps and entity gaps are reported separately, so keep them disjoint.
    term_gaps = sorted((important - us_terms) - entity_labels,
                       key=lambda t: -comp_term_count[t])
    body_cov = round(100 * len(us_terms & important) / len(important)) if important else 100

    # FAQ coverage: competitor FAQ topics vs ours (token-overlap match)
    us_faq = us.get("faqs", [])
    comp_faqs = dedupe([q for c in comp_ok for q in c["faqs"]])
    faq_gaps = [q for q in comp_faqs if not _faq_covered(q, us_faq)]
    faq_cov = (round(100 * (len(comp_faqs) - len(faq_gaps)) / len(comp_faqs))
               if comp_faqs else 100)

    # entity gaps (named brands/trials/compounds competitors cover and we don't)
    comp_entities = {t for t in important if t in entity_labels}
    entity_gaps = sorted(comp_entities - us_terms, key=lambda t: -comp_term_count[t])

    checks = [
        ("Title tag", "title", bool(term_in(title, PRIMARY)),
         bool(term_in(title, PRIMARY + SECONDARY)), title),
        ("Meta description", "meta", bool(term_in(meta, PRIMARY)),
         bool(term_in(meta, PRIMARY + SECONDARY)), meta),
        ("H1 heading", "h1", "wegovy pill" in h1.lower(),
         bool(term_in(h1, PRIMARY + SECONDARY)), h1),
        ("Opening copy (60w)", "open", bool(term_in(opening, PRIMARY)),
         bool(term_in(opening, PRIMARY + SECONDARY)), opening[:160]),
    ]
    check_rows = []
    for name, key, primary_ok, any_ok, evidence in checks:
        state = "pass" if primary_ok else ("warn" if any_ok else "fail")
        check_rows.append({"name": name, "key": key, "state": state,
                           "evidence": evidence})

    # structural checks vs competitors
    med_wc = median([c["wc"] for c in comp_ok]) if comp_ok else 0
    wc_state = "pass" if us["wc"] >= 0.8 * med_wc else ("warn" if us["wc"] >= 0.5 * med_wc else "fail")
    check_rows.append({"name": "Body depth (words)", "key": "wc", "state": wc_state,
                       "evidence": f"{us['wc']} words vs competitor median {med_wc}"})
    faq_state = "pass" if faq_cov >= 70 else ("warn" if faq_cov >= 40 else "fail")
    check_rows.append({"name": "FAQ coverage", "key": "faq", "state": faq_state,
                       "evidence": f"{us.get('faqs') and len(us['faqs']) or 0} FAQs, "
                                   f"{faq_cov}% of competitor FAQ topics covered"})
    body_state = "pass" if body_cov >= 80 else ("warn" if body_cov >= 60 else "fail")
    check_rows.append({"name": "Semantic coverage", "key": "body", "state": body_state,
                       "evidence": f"{body_cov}% of terms used by 2+ competitors"})

    weight = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    score = round(100 * sum(weight[c["state"]] for c in check_rows) / len(check_rows))

    return {
        "score": score,
        "checks": check_rows,
        "term_gaps": [{"term": t, "competitors": comp_term_count[t]} for t in term_gaps],
        "entity_gaps": [{"term": t, "competitors": comp_term_count[t]} for t in entity_gaps],
        "faq_gaps": faq_gaps[:20],
        "body_cov": body_cov,
        "faq_cov": faq_cov,
        "comp_median_wc": med_wc,
    }


def _faq_covered(question: str, our_faqs: list) -> bool:
    qtok = {w for w in re.findall(r"[a-z]{4,}", question.lower()) if w not in STOP}
    if not qtok:
        return True
    for ours in our_faqs:
        otok = {w for w in re.findall(r"[a-z]{4,}", ours.lower()) if w not in STOP}
        if otok and len(qtok & otok) / len(qtok) >= 0.6:
            return True
    return False


def median(xs: list):
    xs = sorted(x for x in xs if x)
    if not xs:
        return 0
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) // 2


def opportunities(align: dict) -> list:
    """Prioritised, plain-English actions derived from the scorecard."""
    out = []
    for c in align["checks"]:
        if c["state"] == "fail":
            out.append(f"Fix {c['name'].lower()}: {c['evidence'][:80]}")
    for c in align["checks"]:
        if c["state"] == "warn":
            out.append(f"Strengthen {c['name'].lower()} for a primary term ({c['evidence'][:60]})")
    if align["entity_gaps"]:
        names = ", ".join(g["term"] for g in align["entity_gaps"][:6])
        out.append(f"Add missing entities competitors cover: {names}")
    if align["term_gaps"]:
        names = ", ".join(g["term"] for g in align["term_gaps"][:8])
        out.append(f"Cover missing topics/terms: {names}")
    if align["faq_gaps"]:
        out.append(f"Add {len(align['faq_gaps'])} FAQ(s) competitors answer that we don't, "
                   f"e.g. “{align['faq_gaps'][0]}”")
    return out[:12]


# ------------------------------------------------------------------------- orchestrate
def top_serp(semrush_fn, phrase: str, n: int) -> list:
    text = semrush_fn({
        "type": "phrase_organic", "phrase": phrase, "database": DATABASE,
        "display_limit": max(n + 4, 10), "export_columns": "Dn,Ur",
    })
    rows = []
    if not text:
        return rows
    lines = [l for l in text.splitlines() if l.strip()]
    for line in lines[1:]:  # skip header row
        parts = line.split(";")
        if len(parts) >= 2:
            rows.append((parts[0].strip(), parts[1].strip()))
    return rows


def build_audit(semrush_fn=None, fetch_fn=None, mode="live") -> dict:
    semrush_fn = semrush_fn or _default_semrush
    fetch_fn = fetch_fn or fetch_html

    serp = top_serp(semrush_fn, PHRASE, TOP_N)
    # Build the page list: top-N organic results + our own page (deduped).
    pages, seen = [], set()
    rank = 0
    for domain, url in serp:
        rank += 1
        if rank > TOP_N:
            break
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        role = "us" if OUR_DOMAIN in domain else ("brand" if "wegovy.com" in domain else "competitor")
        pages.append({"rank": rank, "domain": domain, "url": url, "role": role})

    our_present = any(p["role"] == "us" for p in pages)
    if not our_present:
        pages.append({"rank": None, "domain": OUR_DOMAIN, "url": OUR_PAGE, "role": "us"})

    analysed = []
    for p in pages:
        status, html = fetch_fn(p["url"])
        analysed.append(analyze(p["url"], p["domain"], p["rank"], p["role"], status, html))

    us = next((a for a in analysed if a["role"] == "us"), None) or analyze(
        OUR_PAGE, OUR_DOMAIN, None, "us", "error:missing", "")
    competitors = [a for a in analysed if a["role"] != "us"]
    align = score_alignment(us, competitors)

    return {
        "date": today_uk(),
        "mode": mode,
        "phrase": PHRASE,
        "primary": PRIMARY,
        "secondary": SECONDARY,
        "us": us,
        "pages": analysed,
        "align": align,
        "opps": opportunities(align),
        "fetched": sum(1 for a in analysed if a["status"] == "ok"),
        "blocked": [a["domain"] for a in analysed if a["status"] != "ok"],
    }


def digest_section(audit: dict) -> str:
    a = audit["align"]
    L = ["", "CONTENT REVIEW -- \"wegovy pill\" SERP "
         + (f"({audit['mode']} mode)" if audit["mode"] != "live" else ""),
         "  " + "-" * 60,
         f"  pill-page alignment score: {a['score']}/100   "
         f"(body {a['body_cov']}% / FAQ {a['faq_cov']}% vs competitors)"]
    for c in a["checks"]:
        mark = {"pass": "OK ", "warn": "~  ", "fail": "[!]"}[c["state"]]
        L.append(f"   {mark} {c['name']:<22} {c['evidence'][:60]}")
    if a["entity_gaps"]:
        L.append("  missing entities: " + ", ".join(g["term"] for g in a["entity_gaps"][:8]))
    if a["term_gaps"]:
        L.append("  missing terms:    " + ", ".join(g["term"] for g in a["term_gaps"][:8]))
    if a["faq_gaps"]:
        L.append(f"  FAQ gaps ({len(a['faq_gaps'])}): " + a["faq_gaps"][0])
    if audit["blocked"]:
        L.append("  [note] pages not fetched: " + ", ".join(audit["blocked"]))
    if audit["opps"]:
        L.append("  TOP OPPORTUNITIES:")
        for o in audit["opps"][:5]:
            L.append("   - " + o)
    return "\n".join(L)


def load_history(path=DATA) -> list:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(audits: list):
    audits = audits[-HISTORY_KEEP:]
    for path in (DATA, DOCS):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(audits, f, indent=1)


def run_and_store(semrush_fn=None, fetch_fn=None, mode="live") -> dict:
    audit = build_audit(semrush_fn, fetch_fn, mode)
    hist = [s for s in load_history() if s.get("date") != audit["date"]]
    hist.append(audit)
    save_history(hist)
    return audit


# ----------------------------------------------------------------------- fixtures
# Realistic canned pages grounded in the live top-5 (June 2026), used for
# --test and --seed so the logic and dashboard can be exercised without egress.
def _fixtures():
    from fixtures_content import FIXTURE_SERP, FIXTURE_PAGES  # local module
    serp_fn = lambda params: FIXTURE_SERP
    def fetch_fn(url):
        html = FIXTURE_PAGES.get(url.rstrip("/"))
        return ("ok", html) if html else ("blocked", "")
    return serp_fn, fetch_fn


def selftest():
    serp_fn, fetch_fn = _fixtures()
    audit = build_audit(serp_fn, fetch_fn, mode="test")
    a = audit["align"]
    assert audit["us"]["status"] == "ok", "our page should parse"
    assert "wegovy pill" in audit["us"]["title"].lower(), "fixture title has target term"
    assert audit["us"]["faqs"], "our fixture should expose FAQs"
    assert 0 <= a["score"] <= 100
    # Superdrug fixture omits 'buy' in title and we encoded SNAC/OASIS only on
    # competitors -> they must surface as gaps for our page.
    gap_terms = {g["term"] for g in a["term_gaps"]} | {g["term"] for g in a["entity_gaps"]}
    assert "SNAC" in gap_terms or "absorption enhancer" in gap_terms, gap_terms
    assert a["faq_gaps"], "should detect at least one FAQ gap"
    assert audit["opps"], "should produce opportunities"
    print(digest_section(audit))
    print("\n[self-test] content_audit assertions passed "
          f"(score {a['score']}, {len(a['term_gaps'])} term gaps, "
          f"{len(a['faq_gaps'])} FAQ gaps)")


def main():
    if "--test" in sys.argv:
        selftest()
        return
    if "--seed" in sys.argv:
        serp_fn, fetch_fn = _fixtures()
        audit = run_and_store(serp_fn, fetch_fn, mode="seed")
        print(digest_section(audit))
        print(f"\n[seed] wrote {DATA} and {DOCS}")
        return
    audit = run_and_store(mode="live")
    print(digest_section(audit))


if __name__ == "__main__":
    main()
