#!/usr/bin/env python3
"""
Multi-source rank enrichment for Wegovy Sentinel.

Semrush stays the primary signal. This module adds two extra ranking
outputs so the dashboard shows a triangulated view per keyword:

  - Google Search Console (GSC) -- Google's OWN data for our pages:
    average position, clicks, impressions, CTR. OAuth refresh-token auth
    (stdlib only: the token exchange is a plain HTTPS POST, no JWT/RSA
    signing -- so we avoid pulling in a crypto dependency).

  - Advanced Web Ranking (AWR) -- daily tracked rank from AWR Cloud, with
    UK / mobile granularity, via the AWR Cloud v2 "get" API.

Both are OPTIONAL and credential-gated. If the relevant env vars are not
set, the fetcher returns {} and the patrol continues on Semrush alone.
Any network/parse error degrades the same way -- it never breaks the patrol.

Env (GSC):
  GSC_CLIENT_ID, GSC_CLIENT_SECRET, GSC_REFRESH_TOKEN   (all required to enable)
  GSC_PROPERTY    default "sc-domain:simpleonlinepharmacy.co.uk"
                  (use "https://www.simpleonlinepharmacy.co.uk/" for a URL property)
  GSC_DAYS        default 28   (trailing window; GSC data lags ~3 days)

Env (AWR):
  AWR_API_TOKEN, AWR_PROJECT     (both required to enable)
                  NOTE: use the AWR Cloud v2 API token (Connectors & API
                  Settings), NOT the MCP server JWT -- those are different.
  AWR_AUTH        "query" (default; AWR Cloud v2 export, token in query string)
                  or "bearer" (Bearer-token endpoint via AWR_BASE).
  AWR_GEO         default "United Kingdom"  (substring-matched against AWR location)
  AWR_DEVICE      default "mobile"          (substring-matched against AWR device)
  AWR_BASE        override the endpoint to suit your AWR plan
  AWR_ACTION      default "export_ranking"  (query mode)
  AWR_POLL_TRIES  default 30   the export is async; poll the file URL this many
  AWR_POLL_SECS   default 6    times, waiting this many seconds between tries
"""
import csv
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _today_uk():
    return datetime.now(ZoneInfo("Europe/London")).date()


# --------------------------------------------------------------------------
# Google Search Console
# --------------------------------------------------------------------------
def _gsc_access_token() -> str:
    cid = os.environ.get("GSC_CLIENT_ID", "")
    csec = os.environ.get("GSC_CLIENT_SECRET", "")
    rt = os.environ.get("GSC_REFRESH_TOKEN", "")
    if not (cid and csec and rt):
        return ""
    data = urllib.parse.urlencode({
        "client_id": cid,
        "client_secret": csec,
        "refresh_token": rt,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("access_token", "")


def fetch_gsc(keywords) -> dict:
    """Return {keyword_lower: {pos, clicks, impr, ctr}} for tracked keywords.

    One Search Analytics query over the trailing window, dimensioned by query,
    then filtered to the keywords we track. Empty dict if not configured.
    """
    token = _gsc_access_token()
    if not token:
        return {}
    prop = os.environ.get("GSC_PROPERTY", "sc-domain:simpleonlinepharmacy.co.uk")
    try:
        days = int(os.environ.get("GSC_DAYS", "28") or 28)
    except ValueError:
        days = 28
    end = _today_uk() - timedelta(days=3)   # GSC data lags a couple of days
    start = end - timedelta(days=days)
    payload = _gsc_query(token, prop, {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "rowLimit": 1000,
        "type": "web",
    })
    want = {k.lower() for k in keywords}
    out = {}
    for row in payload.get("rows", []):
        q = ((row.get("keys") or [""])[0] or "").strip().lower()
        if q in want:
            out[q] = {
                "pos": round(float(row.get("position", 0)), 1),
                "clicks": int(row.get("clicks", 0)),
                "impr": int(row.get("impressions", 0)),
                "ctr": round(float(row.get("ctr", 0)) * 100, 1),
            }
    return out


def _gsc_query(token, prop, body: dict) -> dict:
    url = ("https://www.googleapis.com/webmasters/v3/sites/"
           + urllib.parse.quote(prop, safe="") + "/searchAnalytics/query")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# what a title at position P should roughly earn; used to flag under-clicking pages
_EXPECTED_CTR = ((1, 28.0), (2, 15.0), (3, 10.0), (4, 7.0), (5, 5.0),
                 (8, 3.5), (10, 2.5), (20, 1.0), (100, 0.4))
_TOPIC = re.compile(r"wegovy|semaglutide|weight[ -]?loss pill|glp-?1", re.I)
_BUY = re.compile(r"\b(buy|price|cheapest|cost|order|online)\b", re.I)


def _expected_ctr(pos: float) -> float:
    for limit, ctr in _EXPECTED_CTR:
        if pos <= limit:
            return ctr
    return 0.4


def fetch_gsc_insights(tracked) -> dict:
    """Deep GSC analysis over query+page rows (trailing window). Returns {} if
    GSC creds are not configured. Sections:

      untracked -- wegovy-topic queries with real impressions that we do NOT
                   track (Google already associates us with them)
      ctr_opps  -- queries where our CTR is <50% of what the position should
                   earn (title/meta rewrite candidates)
      routing   -- buy-intent queries where Google serves 2+ of our URLs or a
                   non-pill page (cannibalisation as Google actually sees it)
      striking  -- positions 11-20 by impressions (cheapest page-1 wins)
    """
    token = _gsc_access_token()
    if not token:
        return {}
    prop = os.environ.get("GSC_PROPERTY", "sc-domain:simpleonlinepharmacy.co.uk")
    try:
        days = int(os.environ.get("GSC_DAYS", "28") or 28)
    except ValueError:
        days = 28
    end = _today_uk() - timedelta(days=3)
    start = end - timedelta(days=days)
    payload = _gsc_query(token, prop, {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query", "page"],
        "rowLimit": 5000,
        "type": "web",
    })
    rows = []
    for r in payload.get("rows", []):
        q, page = (r.get("keys") or ["", ""])[:2]
        q = (q or "").strip().lower()
        if not q or not _TOPIC.search(q):
            continue
        rows.append({
            "q": q, "page": page,
            "pos": round(float(r.get("position", 0)), 1),
            "clicks": int(r.get("clicks", 0)),
            "impr": int(r.get("impressions", 0)),
            "ctr": round(float(r.get("ctr", 0)) * 100, 1),
        })
    return analyse_gsc_rows(rows, tracked)


PILL_PAGE = "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/"


def _same_page(a: str, b: str) -> bool:
    norm = lambda u: (u or "").split("#")[0].split("?")[0].rstrip("/").lower()
    return norm(a) == norm(b)


def analyse_gsc_rows(rows, tracked, pill_url: str = PILL_PAGE) -> dict:
    """Pure analysis over query+page rows (separated for offline testing)."""
    tracked_set = {t.lower() for t in tracked}

    # every query Google serves THE PILL PAGE for (its own table on the dashboard)
    pill_page = sorted(
        ({"q": r["q"], "pos": r["pos"], "clicks": r["clicks"],
          "impr": r["impr"], "ctr": r["ctr"]}
         for r in rows if _same_page(r["page"], pill_url)),
        key=lambda a: -a["impr"])[:20]

    # roll rows up per query
    per_q = {}
    for r in rows:
        agg = per_q.setdefault(r["q"], {"q": r["q"], "clicks": 0, "impr": 0,
                                        "pages": []})
        agg["clicks"] += r["clicks"]
        agg["impr"] += r["impr"]
        agg["pages"].append(r)
    for agg in per_q.values():
        best = min(agg["pages"], key=lambda p: p["pos"])
        agg["pos"] = best["pos"]
        agg["ctr"] = round(agg["clicks"] * 100.0 / agg["impr"], 1) if agg["impr"] else 0.0

    untracked = sorted(
        (a for a in per_q.values() if a["q"] not in tracked_set and a["impr"] >= 100),
        key=lambda a: -a["impr"])[:15]

    ctr_opps = sorted(
        (a for a in per_q.values()
         if a["impr"] >= 300 and a["pos"] <= 20
         and a["ctr"] < _expected_ctr(a["pos"]) * 0.5),
        key=lambda a: -a["impr"])[:10]
    for a in ctr_opps:
        a["exp"] = _expected_ctr(a["pos"])

    routing = []
    for a in per_q.values():
        if not _BUY.search(a["q"]) or a["impr"] < 100:
            continue
        pages = sorted(a["pages"], key=lambda p: -p["impr"])
        multi = len({p["page"] for p in pages}) > 1
        top = pages[0]["page"] or ""
        off_pill = "/weight-loss/wegovy-pill" not in top and "wegovy" in a["q"]
        if multi or off_pill:
            routing.append({"q": a["q"], "impr": a["impr"],
                            "multi": multi, "top": top})
    routing = sorted(routing, key=lambda x: -x["impr"])[:10]

    striking = sorted(
        (a for a in per_q.values() if 11 <= a["pos"] <= 20 and a["impr"] >= 100),
        key=lambda a: -a["impr"])[:10]

    strip = lambda lst: [{k: v for k, v in a.items() if k != "pages"} for a in lst]
    return {"pill_page": pill_page,
            "untracked": strip(untracked), "ctr_opps": strip(ctr_opps),
            "routing": routing, "striking": strip(striking),
            "rows": len(rows), "queries": len(per_q)}


# --------------------------------------------------------------------------
# Advanced Web Ranking (AWR Cloud)
# --------------------------------------------------------------------------
def _num(v):
    try:
        n = int(round(float(v)))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


_KW_FIELDS = ("keyword", "kw", "phrase", "query", "term", "name")
_POS_FIELDS = ("position", "rank", "pos", "ranking", "current", "google")


def _awr_iter(payload):
    """Recursively yield dicts that look like a keyword+position record.

    AWR's export is a nested list of keyword groups, so we walk the whole
    structure and surface any dict carrying both a keyword-ish and a
    position-ish field.
    """
    if isinstance(payload, dict):
        if _kw_of(payload) is not None and _pos_of(payload) is not None:
            yield payload
        for v in payload.values():
            if isinstance(v, (list, dict)):
                yield from _awr_iter(v)
    elif isinstance(payload, list):
        for x in payload:
            yield from _awr_iter(x)


def _pick(d, names):
    low = {str(k).lower(): k for k in d.keys()}
    for n in names:
        if n in low:
            return d[low[n]]
    return None


def _kw_of(row):
    """Keyword from a row: exact field names first, then substring match
    (CSV exports use headers like 'Keyword Group / Keyword')."""
    v = _pick(row, _KW_FIELDS)
    if v:
        return v
    for k, val in row.items():
        lk = str(k).lower()
        if ("keyword" in lk or "phrase" in lk) and val:
            return val
    return None


def _pos_of(row):
    """Best (lowest) position from a row: exact fields first, then any
    column whose header mentions position/rank (e.g. 'Google.co.uk Rank')."""
    v = _num(_pick(row, _POS_FIELDS))
    if v is not None:
        return v
    best = None
    for k, val in row.items():
        lk = str(k).lower()
        if ("position" in lk or "rank" in lk) and "change" not in lk:
            n = _num(val)
            if n is not None and (best is None or n < best):
                best = n
    return best


def _parse_export(data):
    """Parse a downloaded AWR export file. Handles zip/gzip containers
    (AWR ships exports compressed), then JSON, then CSV. Returns a payload
    usable by _awr_iter, or None if it has no ranking rows (e.g. an
    'Export in progress' placeholder)."""
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    if data[:4] == b"PK\x03\x04":                       # zip archive
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if not names:
                return None
            data = z.read(names[0])
    elif data[:2] == b"\x1f\x8b":                        # gzip
        data = gzip.decompress(data)
    raw = data.decode("utf-8", "replace").lstrip("﻿ \r\n")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    head = raw.splitlines()[0] if raw else ""
    if "keyword" not in head.lower():
        return None
    delim = ";" if head.count(";") >= head.count(",") else ","
    rows = []
    for r in csv.DictReader(io.StringIO(raw), delimiter=delim):
        d = {str(k).strip().lower(): (v or "").strip()
             for k, v in r.items() if k}
        if d:
            rows.append(d)
    return rows or None


def _awr_get(url, headers):
    return _awr_get_bytes(url, headers).decode("utf-8", "replace")


def _awr_get_bytes(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def _awr_json(url, headers):
    raw = _awr_get(url, headers)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"AWR non-JSON ({raw.strip()[:80]})")


def _awr_url(payload):
    """Extract a generated-file URL from an AWR response, if present."""
    if isinstance(payload, dict):
        for k in ("details", "url", "file", "download", "link"):
            v = payload.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
    elif isinstance(payload, str) and payload.startswith("http"):
        return payload
    return None


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _awr_latest_date(payload):
    """Find the most recent YYYY-MM-DD anywhere in an AWR get_dates response."""
    found = set()

    def walk(x):
        if isinstance(x, str):
            found.update(_DATE_RE.findall(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(payload)
    return max(found) if found else None       # ISO dates sort chronologically


def fetch_awr(keywords) -> dict:
    """Return {keyword_lower: position} from Advanced Web Ranking. Empty if off.

    Default path is the documented AWR Cloud v2 export API
    (api.awrcloud.com/v2/get.php, token in the query string, format=json).
    export_ranking returns a URL to a generated file, which we then download
    and parse. Set AWR_AUTH=bearer (+ AWR_BASE) to use a Bearer-token endpoint
    instead. The parser walks nested keyword groups and detects fields flexibly.
    """
    token = os.environ.get("AWR_API_TOKEN", "")
    project = os.environ.get("AWR_PROJECT", "")
    if not (token and project):
        return {}
    auth = os.environ.get("AWR_AUTH", "query")
    default_base = ("https://api.advancedwebranking.com" if auth == "bearer"
                    else "https://api.awrcloud.com/v2/get.php")
    base = os.environ.get("AWR_BASE", default_base)
    action = os.environ.get("AWR_ACTION", "export_ranking")
    geo = os.environ.get("AWR_GEO", "United Kingdom").lower()
    device = os.environ.get("AWR_DEVICE", "mobile").lower()

    headers = {"User-Agent": "wegovy-sentinel/3.0", "Accept": "application/json"}

    if auth == "bearer":
        headers["Authorization"] = f"Bearer {token}"
        payload = _awr_json(f"{base}?{urllib.parse.urlencode({'project': project})}", headers)
    else:
        common = {"token": token, "project": project, "format": "json"}
        # 1. AWR Cloud v2 export_ranking needs a date range -- get the latest date.
        start = os.environ.get("AWR_START_DATE", "")
        stop = os.environ.get("AWR_STOP_DATE", "")
        if not (start and stop):
            dates = _awr_json(
                f"{base}?{urllib.parse.urlencode({'action': 'get_dates', **common})}", headers)
            latest = _awr_latest_date(dates)
            start = stop = latest or ""
        # 2. schedule/fetch the ranking export for that date.
        exp_params = {"action": action, **common}
        if start and stop:
            exp_params["startDate"], exp_params["stopDate"] = start, stop
        exp = _awr_json(f"{base}?{urllib.parse.urlencode(exp_params)}", headers)
        code = exp.get("response_code") if isinstance(exp, dict) else None
        msg = exp.get("message") if isinstance(exp, dict) else None
        # 3. export is async ("Export in progress. Please come back later") -- poll
        #    the generated-file URL until it has data or we run out of tries.
        tries = int(os.environ.get("AWR_POLL_TRIES", "30") or 30)
        secs = int(os.environ.get("AWR_POLL_SECS", "6") or 6)
        payload, follow, last = None, _awr_url(exp), b""
        for attempt in range(max(1, tries)):
            if not follow:
                break
            try:
                last = _awr_get_bytes(follow, headers)
                cand = _parse_export(last)          # zip/gzip -> JSON or CSV
                if cand is not None:
                    payload = cand
                    if any(True for _ in _awr_iter(cand)):
                        break
            except Exception as e:
                last = str(e).encode()
            if attempt < tries - 1:
                time.sleep(secs)
        if payload is None:
            print(f"[awr] export unavailable: code={code} msg={msg} date={start} "
                  f"url={'yes' if follow else 'no'} file_head={last[:60]!r}",
                  file=sys.stderr)
            payload = exp

    want = {k.lower() for k in keywords}
    strict, loose = {}, {}         # strict = geo/device matched; loose = any
    rows_seen = matched = 0
    sample = []
    for row in _awr_iter(payload):
        rows_seen += 1
        kw = _kw_of(row)
        if not kw:
            continue
        k = str(kw).strip().lower()
        if len(sample) < 8:
            sample.append(k)
        if k not in want:
            continue
        pos = _pos_of(row)
        if pos is None:
            continue
        matched += 1
        if k not in loose or pos < loose[k]:
            loose[k] = pos
        loc = str(_pick(row, ("location", "country", "region", "search_engine")) or "").lower()
        dev = str(_pick(row, ("device", "platform")) or "").lower()
        geo_ok = not geo or not loc or geo in loc or \
            ("united kingdom" in geo and ("co.uk" in loc or loc.endswith(" uk")))
        dev_ok = not device or not dev or device in dev or \
            (device == "mobile" and ("smartphone" in dev or "phone" in dev))
        if geo_ok and dev_ok:
            if k not in strict or pos < strict[k]:
                strict[k] = pos

    out = strict or loose         # fall back to unfiltered if the geo/device filter is too tight

    # Diagnostics (stderr -> Actions log; no token is ever printed).
    if not out:
        top = (list(payload.keys())[:8] if isinstance(payload, dict)
               else f"{type(payload).__name__}[{len(payload)}]" if isinstance(payload, list)
               else str(payload)[:80])
        code = payload.get("response_code") if isinstance(payload, dict) else None
        msg = payload.get("message") if isinstance(payload, dict) else None
        print(f"[awr] no positions: rows={rows_seen} matched={matched} "
              f"top={top} code={code} msg={msg} sample_kw={sample}", file=sys.stderr)
    elif out is loose:
        print(f"[awr] geo/device filter matched nothing (geo='{geo}' device='{device}'); "
              f"using unfiltered best positions for {len(out)} keywords", file=sys.stderr)
    return out


# --------------------------------------------------------------------------
# Offline fixtures (used by sentinel.py --test)
# --------------------------------------------------------------------------
FIXTURE_GSC = {
    "wegovy pill": {"pos": 22.4, "clicks": 41, "impr": 5800, "ctr": 0.7},
    "wegovy pill uk": {"pos": 18.1, "clicks": 12, "impr": 1600, "ctr": 0.8},
    "wegovy price": {"pos": 7.6, "clicks": 220, "impr": 9100, "ctr": 2.4},
    "wegovy price uk": {"pos": 6.9, "clicks": 95, "impr": 3200, "ctr": 3.0},
    "cheapest wegovy uk": {"pos": 12.8, "clicks": 30, "impr": 2100, "ctr": 1.4},
    "wegovy side effects": {"pos": 7.2, "clicks": 510, "impr": 22000, "ctr": 2.3},
    "wegovy uk": {"pos": 21.0, "clicks": 60, "impr": 14000, "ctr": 0.4},
    "wegovy reviews": {"pos": 19.5, "clicks": 70, "impr": 8800, "ctr": 0.8},
}

_P = "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill/"
_A = "https://www.simpleonlinepharmacy.co.uk/health-advice/weight-loss/wegovy-pill/oral-wegovy-price-comparison-uk/"
FIXTURE_GSC_ROWS = [
    {"q": "wegovy pill", "page": _P, "pos": 22.4, "clicks": 41, "impr": 5800, "ctr": 0.7},
    {"q": "oral wegovy uk", "page": _P, "pos": 9.2, "clicks": 8, "impr": 2400, "ctr": 0.3},
    {"q": "wegovy tablet vs injection", "page": _P, "pos": 12.1, "clicks": 12, "impr": 1900, "ctr": 0.6},
    {"q": "buy wegovy pill", "page": _P, "pos": 18.0, "clicks": 4, "impr": 700, "ctr": 0.6},
    {"q": "buy wegovy pill", "page": _A, "pos": 24.0, "clicks": 1, "impr": 350, "ctr": 0.3},
    {"q": "wegovy price", "page": _A, "pos": 7.6, "clicks": 220, "impr": 9100, "ctr": 2.4},
    {"q": "how much is wegovy pill uk", "page": _A, "pos": 6.1, "clicks": 15, "impr": 1200, "ctr": 1.2},
    {"q": "cheapest wegovy uk", "page": _A, "pos": 12.8, "clicks": 30, "impr": 2100, "ctr": 1.4},
]

FIXTURE_AWR = {
    "wegovy pill": 24,
    "wegovy pill uk": 17,
    "wegovy pills": 28,
    "wegovy price": 8,
    "wegovy price uk": 7,
    "cheapest wegovy uk": 13,
    "wegovy side effects": 8,
    "wegovy uk": 22,
    "wegovy vs mounjaro": 24,
    "wegovy reviews": 21,
}
