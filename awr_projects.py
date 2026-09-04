#!/usr/bin/env python3
"""
Diagnostic: list AWR Cloud projects visible to AWR_API_TOKEN.

Prints each project's name (and id/keyword count where the payload carries
them) so the patrol logs show exactly which names AWR_PROJECT /
AWR_PROJECT_MOUNJARO / AWR_PROJECT_INJECTION can be set to. Never fatal.
"""
import json
import os
import sys
import urllib.parse
import urllib.request


def main():
    token = os.environ.get("AWR_API_TOKEN", "")
    if not token:
        print("[awr-projects] AWR_API_TOKEN not set; nothing to list")
        return
    url = ("https://api.awrcloud.com/v2/get.php?"
           + urllib.parse.urlencode({"action": "projects", "token": token}))
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"[awr-projects] request failed: {e}")
        return

    # The v2 payload shape varies by plan; walk it defensively.
    def projects_of(x):
        if isinstance(x, dict):
            for key in ("projects", "details", "data", "response"):
                if key in x:
                    return projects_of(x[key])
            return [x] if ("name" in x or "project" in x) else []
        if isinstance(x, list):
            out = []
            for item in x:
                out.extend(projects_of(item))
            return out
        return []

    projs = projects_of(payload)
    if not projs:
        print("[awr-projects] no projects parsed; raw payload follows")
        print(json.dumps(payload)[:2000])
        return
    print(f"[awr-projects] {len(projs)} project(s):")
    for p in projs:
        name = p.get("name") or p.get("project") or "?"
        pid = p.get("id") or p.get("project_id") or "?"
        nkw = p.get("keywords") or p.get("keyword_count") or ""
        print(f"  - name={name!r}  id={pid}  keywords={nkw}")


if __name__ == "__main__":
    main()
