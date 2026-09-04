#!/usr/bin/env python3
"""
Alerts — the patrol opens a GitHub issue when something needs a human.

Rules (latest snapshot vs the previous one):
  - drop:      a pill-goal keyword worsened by DROP_THRESHOLD+ positions
  - page_one:  a pill-goal keyword fell off page one (was <=10, now >10)
  - overtaken: a competitor now outranks SOP on a pill keyword it didn't
               outrank yesterday
  - cann:      the cannibalised-keyword count increased

All triggered alerts are batched into ONE issue per run, labelled
'sentinel-alert'. A fingerprint of each alert is remembered in
data/alerts_state.json so the same condition re-alerts at most once every
COOLDOWN_DAYS while it persists.

Needs GITHUB_TOKEN + GITHUB_REPOSITORY (both provided by GitHub Actions).
Without them it prints what it would have sent and exits 0 — never fatal.

Run:
  python alerts.py           # evaluate latest snapshots, maybe open an issue
  python alerts.py --test    # offline self-test with canned data
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPS = os.path.join(HERE, "docs", "snapshots.json")
STATE = os.path.join(HERE, "data", "alerts_state.json")

# Per-product paths / labels; wegovy (default) keeps the historical locations.
PRODUCTS = {
    "wegovy": {"snaps": SNAPS, "state": STATE, "module": "sentinel",
               "title": "Sentinel alerts"},
    "mounjaro": {
        "snaps": os.path.join(HERE, "docs", "mounjaro_snapshots.json"),
        "state": os.path.join(HERE, "data", "mounjaro_alerts_state.json"),
        "module": "mounjaro_sentinel",
        "title": "Sentinel alerts (Mounjaro)",
    },
    "wegovy-injection": {
        "snaps": os.path.join(HERE, "docs", "wegovy_injection_snapshots.json"),
        "state": os.path.join(HERE, "data", "wegovy_injection_alerts_state.json"),
        "module": "wegovy_injection_sentinel",
        "title": "Sentinel alerts (Wegovy injection)",
    },
    "homepage": {
        "snaps": os.path.join(HERE, "docs", "homepage_snapshots.json"),
        "state": os.path.join(HERE, "data", "homepage_alerts_state.json"),
        "module": "homepage_sentinel",
        "title": "Sentinel alerts (Homepage)",
    },
    "weightloss": {
        "snaps": os.path.join(HERE, "docs", "weightloss_snapshots.json"),
        "state": os.path.join(HERE, "data", "weightloss_alerts_state.json"),
        "module": "weightloss_sentinel",
        "title": "Sentinel alerts (Weight loss hub)",
    },
}

DROP_THRESHOLD = 5
COOLDOWN_DAYS = 7

# product-goal keywords, mirrored from the product sentinel's TRACKED
# (imported lazily so this module stays runnable standalone; the mounjaro
# module may not exist in old checkouts — warn and exit cleanly then)
def pill_keywords(module: str = "sentinel"):
    import importlib
    try:
        mod = importlib.import_module(module)
    except ImportError as e:
        print(f"[warn] cannot import {module} ({e}); nothing to do")
        raise SystemExit(0)
    return [kw for kw, goal, _ in mod.TRACKED if goal in ("pill", "product")]


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


def today_uk() -> str:
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def evaluate(prev: dict, cur: dict, pill_kws: list) -> list:
    """Return [{fp, line}] alert candidates for cur vs prev."""
    alerts = []
    pb, cb = (prev or {}).get("best") or {}, (cur or {}).get("best") or {}

    for kw in pill_kws:
        was = (pb.get(kw) or {}).get("p")
        now = (cb.get(kw) or {}).get("p")
        if was is not None and now is not None and now - was >= DROP_THRESHOLD:
            alerts.append({
                "fp": f"drop:{kw}",
                "line": f'**Drop** — "{kw}" fell {now - was} positions '
                        f"(#{was} → #{now})",
            })
        if was is not None and was <= 10 and (now is None or now > 10):
            alerts.append({
                "fp": f"page_one:{kw}",
                "line": f'**Lost page one** — "{kw}" was #{was}, now '
                        f"{'unranked' if now is None else '#%d' % now}",
            })

    pcomp, ccomp = (prev or {}).get("comp") or {}, (cur or {}).get("comp") or {}
    for label, kws in ccomp.items():
        for kw in pill_kws:
            c_now = (kws or {}).get(kw)
            if not c_now:
                continue
            s_now = (cb.get(kw) or {}).get("p")
            if s_now is None or c_now["p"] >= s_now:
                continue                      # not outranking us now
            c_was = ((pcomp.get(label) or {}).get(kw) or {}).get("p")
            s_was = (pb.get(kw) or {}).get("p")
            beat_before = (c_was is not None and s_was is not None
                           and c_was < s_was)
            if not beat_before:
                alerts.append({
                    "fp": f"overtaken:{label}:{kw}",
                    "line": f'**Overtaken** — {label} moved ahead on "{kw}" '
                            f"(them #{c_now['p']} vs us #{s_now})",
                })

    p_cann = ((prev or {}).get("flags") or {}).get("cann") or 0
    c_cann = ((cur or {}).get("flags") or {}).get("cann") or 0
    if c_cann > p_cann:
        alerts.append({
            "fp": "cann",
            "line": f"**Cannibalisation up** — {p_cann} → {c_cann} keywords "
                    f"with 2+ SOP URLs ranking",
        })
    return alerts


def load_state(path: str = STATE) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (ValueError, OSError):
            pass
    return {}


def within_cooldown(state: dict, fp: str, today: str) -> bool:
    last = state.get(fp)
    if not last:
        return False
    try:
        gap = (datetime.strptime(today, "%Y-%m-%d")
               - datetime.strptime(last, "%Y-%m-%d")).days
    except ValueError:
        return False
    return gap < COOLDOWN_DAYS


def open_issue(title: str, body: str) -> bool:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not (token and repo):
        print("[alerts] GITHUB_TOKEN/GITHUB_REPOSITORY not set -- would send:\n"
              + title + "\n" + body)
        return False
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps({"title": title, "body": body,
                         "labels": ["sentinel-alert"]}).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        num = json.loads(r.read().decode()).get("number")
    print(f"[alerts] opened issue #{num}: {title}")
    return True


def main():
    if "--test" in sys.argv:
        pill = ["wegovy pill", "wegovy price", "wegovy uk"]
        prev = {"best": {"wegovy pill": {"p": 8}, "wegovy price": {"p": 9},
                         "wegovy uk": {"p": 20}},
                "comp": {"Superdrug": {"wegovy pill": {"p": 12}}},
                "flags": {"cann": 4}}
        cur = {"best": {"wegovy pill": {"p": 15}, "wegovy price": {"p": 9},
                        "wegovy uk": {"p": 21}},
               "comp": {"Superdrug": {"wegovy pill": {"p": 3}}},
               "flags": {"cann": 6}}
        got = evaluate(prev, cur, pill)
        fps = {a["fp"] for a in got}
        assert "drop:wegovy pill" in fps, fps           # 8 -> 15 (>=5)
        assert "page_one:wegovy pill" in fps, fps       # was 8, now 15
        assert "overtaken:Superdrug:wegovy pill" in fps, fps
        assert "cann" in fps, fps
        assert "drop:wegovy uk" not in fps, fps         # only moved 1
        # no-change run produces nothing
        assert evaluate(cur, cur, pill) == []
        # cooldown
        st = {"drop:wegovy pill": "2026-09-01"}
        assert within_cooldown(st, "drop:wegovy pill", "2026-09-03")
        assert not within_cooldown(st, "drop:wegovy pill", "2026-09-09")
        print("[self-test] all assertions passed")
        return

    p = PRODUCTS[product_from_argv(sys.argv)]
    try:
        with open(p["snaps"]) as f:
            snaps = json.load(f)
    except (OSError, ValueError):
        print("[alerts] no snapshot history; nothing to do")
        return
    if len(snaps) < 2:
        print("[alerts] need two snapshots to compare; nothing to do")
        return

    today = today_uk()
    state = load_state(p["state"])
    fresh = [a for a in evaluate(snaps[-2], snaps[-1], pill_keywords(p["module"]))
             if not within_cooldown(state, a["fp"], today)]
    if not fresh:
        print("[alerts] nothing to report")
        return

    body = (f"Patrol {snaps[-1].get('date')} vs {snaps[-2].get('date')}:\n\n"
            + "\n".join("- " + a["line"] for a in fresh)
            + "\n\n[Dashboard](https://scottlawrieai.github.io/wegovy-sentinel/)"
            + " · repeated conditions re-alert after "
            + f"{COOLDOWN_DAYS} days.")
    sent = open_issue(f"{p['title']} — {today}", body)
    if sent:
        for a in fresh:
            state[a["fp"]] = today
        os.makedirs(os.path.dirname(p["state"]), exist_ok=True)
        with open(p["state"], "w") as f:
            json.dump(state, f, indent=1)


if __name__ == "__main__":
    main()
