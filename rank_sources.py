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
  AWR_API_TOKEN, AWR_PROJECT                            (both required to enable)
  AWR_AUTH        "bearer" (modern api.advancedwebranking.com, Bearer JWT) or
                  "query"  (legacy api.awrcloud.com). Auto: bearer if the token
                  looks like a JWT, else query.
  AWR_GEO         default "United Kingdom"  (substring-matched against AWR location)
  AWR_DEVICE      default "mobile"          (substring-matched against AWR device)
  AWR_BASE        override the endpoint to suit your AWR plan
  AWR_ACTION      default "export_ranking_data"  (legacy query mode only)
"""
import json
import os
import sys
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


def _awr_iter(payload):
    """Yield candidate row dicts from whatever shape AWR returns."""
    if isinstance(payload, list):
        for x in payload:
            if isinstance(x, dict):
                yield x
    elif isinstance(payload, dict):
        for key in ("rows", "data", "keywords", "results", "ranking"):
            v = payload.get(key)
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        yield x
                return
        # dict keyed by keyword -> position/record
        for k, v in payload.items():
            if isinstance(v, dict):
                yield {"keyword": k, **v}
            elif _num(v) is not None:
                yield {"keyword": k, "position": v}


def _pick(d, names):
    low = {str(k).lower(): k for k in d.keys()}
    for n in names:
        if n in low:
            return d[low[n]]
    return None


def fetch_awr(keywords) -> dict:
    """Return {keyword_lower: position} from Advanced Web Ranking. Empty if off.

    Supports two AWR APIs:
      - modern (api.advancedwebranking.com): Bearer JWT auth. Default when the
        token looks like a JWT (two dots) or AWR_AUTH=bearer.
      - legacy AWR Cloud (api.awrcloud.com/v2/get.php): token in query string.

    Endpoint/response shape vary by plan, so AWR_BASE / AWR_ACTION are
    overridable and the parser detects keyword/position fields flexibly.
    """
    token = os.environ.get("AWR_API_TOKEN", "")
    project = os.environ.get("AWR_PROJECT", "")
    if not (token and project):
        return {}
    auth = os.environ.get("AWR_AUTH", "bearer" if token.count(".") == 2 else "query")
    default_base = ("https://api.advancedwebranking.com/v1/ranking"
                    if auth == "bearer" else "https://api.awrcloud.com/v2/get.php")
    base = os.environ.get("AWR_BASE", default_base)
    action = os.environ.get("AWR_ACTION", "export_ranking_data")
    geo = os.environ.get("AWR_GEO", "United Kingdom").lower()
    device = os.environ.get("AWR_DEVICE", "mobile").lower()

    params = {"project": project, "date": _today_uk().isoformat()}
    headers = {"User-Agent": "wegovy-sentinel/3.0", "Accept": "application/json"}
    if auth == "bearer":
        headers["Authorization"] = f"Bearer {token}"
    else:
        params.update({"action": action, "token": token})
    req = urllib.request.Request(
        f"{base}?{urllib.parse.urlencode(params)}", headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"AWR returned non-JSON ({raw.strip()[:80]})")

    want = {k.lower() for k in keywords}
    out = {}
    for row in _awr_iter(payload):
        kw = _pick(row, ("keyword", "kw", "phrase", "query", "term"))
        if not kw or str(kw).strip().lower() not in want:
            continue
        # optional geo/device match -- skip rows that clearly don't match
        loc = str(_pick(row, ("location", "country", "region", "search_engine")) or "")
        dev = str(_pick(row, ("device", "platform")) or "")
        if loc and geo and geo not in loc.lower():
            continue
        if dev and device and device not in dev.lower():
            continue
        pos = _num(_pick(row, ("position", "rank", "pos", "ranking", "current")))
        k = str(kw).strip().lower()
        if pos is not None and (k not in out or pos < out[k]):
            out[k] = pos
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
