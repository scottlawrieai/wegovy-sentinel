# Ranking sources

Wegovy Sentinel triangulates each tracked keyword across **three** ranking
outputs for our own pages, shown side by side on the dashboard and in the
daily digest:

| Source | What it is | Auth |
|--------|------------|------|
| **Semrush** | Modelled UK desktop position (also powers competitor columns + backlinks). Always on. | `SEMRUSH_API_KEY` |
| **GSC** | Google Search Console — Google's *own* data for our pages: average position, clicks, impressions, CTR (trailing window). | OAuth refresh token |
| **AWR** | Advanced Web Ranking — tracked UK / mobile rank from AWR Cloud. | API token + project |

GSC and AWR are **optional**. If their credentials aren't set the patrol runs
on Semrush alone and those columns simply show `--`. Any network/parse error
degrades the same way and never breaks the patrol.

---

## Google Search Console (GSC)

We use an **OAuth refresh token** rather than a service account, so the whole
client stays standard-library only (a refresh-token exchange is a plain HTTPS
POST — no JWT/RSA signing, no extra dependency).

One-time setup:

1. In Google Cloud, enable the **Search Console API** and create an OAuth
   client (type *Desktop app*). Note the **client ID** and **client secret**.
2. Generate a **refresh token** for an account that has access to the property,
   with scope `https://www.googleapis.com/auth/webmasters.readonly`
   (the OAuth Playground is the quickest way — tick "use your own credentials").
3. Add repo **secrets** (Settings → Secrets and variables → Actions → *Secrets*):
   - `GSC_CLIENT_ID`
   - `GSC_CLIENT_SECRET`
   - `GSC_REFRESH_TOKEN`
4. Add a repo **variable** (same screen → *Variables*):
   - `GSC_PROPERTY` — e.g. `sc-domain:simpleonlinepharmacy.co.uk`
     (domain property) or `https://www.simpleonlinepharmacy.co.uk/` (URL property).
   - Optional `GSC_DAYS` (default `28`).

## Advanced Web Ranking (AWR)

Supports both AWR APIs and auto-selects by token type:

- **Modern** (`api.advancedwebranking.com`) — Bearer **JWT** auth. Used
  automatically when the token looks like a JWT.
- **Legacy AWR Cloud** (`api.awrcloud.com`) — token passed in the query string.

Setup:

1. Add repo **secret** `AWR_API_TOKEN` (AWR → account → API).
   > ⚠️ Keep this out of code/chat. If a token is ever exposed, rotate it in AWR.
2. Add repo **variables**:
   - `AWR_PROJECT` — the AWR project name that tracks these keywords.
   - Optional `AWR_GEO` (default `United Kingdom`), `AWR_DEVICE` (default `mobile`).
   - Optional `AWR_AUTH` (`bearer` | `query`) to force a mode.
   - Optional `AWR_BASE` / `AWR_ACTION` if your plan's endpoint differs — the
     response parser detects keyword/position fields flexibly, so a tweak here
     is usually all that's needed (no code change).

> The exact ranking endpoint/response shape on the modern API still needs to be
> confirmed against a live response (this dev sandbox blocks egress to AWR). The
> first patrol run in GitHub Actions (clean egress) will exercise it; if the
> field mapping needs adjusting, set `AWR_BASE` or share a sample response.

---

Test everything offline (uses canned fixtures, no network/keys):

```bash
python sentinel.py --test
```
