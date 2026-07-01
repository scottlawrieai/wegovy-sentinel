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
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
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
    body = json.dumps({
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "rowLimit": 1000,
        "type": "web",
    }).encode()
    url = ("https://www.googleapis.com/webmasters/v3/sites/"
           + urllib.parse.quote(prop, safe="") + "/searchAnalytics/query")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
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
        keys = {str(k).lower() for k in payload}
        if keys & set(_KW_FIELDS) and keys & set(_POS_FIELDS):
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


def _awr_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


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
        # 3. export is async -- follow the generated-file URL, retrying while it builds.
        payload, follow = None, _awr_url(exp)
        for attempt in range(6):
            if not follow:
                break
            try:
                cand = _awr_json(follow, headers)
                if any(True for _ in _awr_iter(cand)):
                    payload = cand
                    break
                payload = cand
            except Exception:
                pass
            time.sleep(3)
        if payload is None:
            print(f"[awr] export unavailable: code={code} msg={msg} "
                  f"date={start} url={'yes' if follow else 'no'}", file=sys.stderr)
            payload = exp

    want = {k.lower() for k in keywords}
    strict, loose = {}, {}         # strict = geo/device matched; loose = any
    rows_seen = matched = 0
    sample = []
    for row in _awr_iter(payload):
        rows_seen += 1
        kw = _pick(row, _KW_FIELDS)
        if not kw:
            continue
        k = str(kw).strip().lower()
        if len(sample) < 8:
            sample.append(k)
        if k not in want:
            continue
        pos = _num(_pick(row, _POS_FIELDS))
        if pos is None:
            continue
        matched += 1
        if k not in loose or pos < loose[k]:
            loose[k] = pos
        loc = str(_pick(row, ("location", "country", "region", "search_engine")) or "").lower()
        dev = str(_pick(row, ("device", "platform")) or "").lower()
        if (not geo or not loc or geo in loc) and (not device or not dev or device in dev):
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
