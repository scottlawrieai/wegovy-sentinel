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
   - Optional `GSC_DAYS` (default `28`) — window for the keyword/insight tables.
   - Optional `GSC_TS_DAYS` (default `90`) — window for the **performance
     charts**. This series is pulled straight from Google dimensioned by date,
     so the charts show real backfilled history the first time it runs.

Until these are set the performance charts fall back to the Semrush modelled
position, and the clicks / impressions / CTR tiles stay hidden.

The patrol also stores a **per-keyword daily series** (`gsckw` in the
snapshot): one Search Analytics query dimensioned by date + query over the
same `GSC_TS_DAYS` window, filtered to the tracked keywords, giving each
keyword its own daily position / clicks / impressions history straight from
Google. Like the other GSC data it is optional, degrades to nothing on error,
and the last known series is carried forward when a patrol runs without
credentials.

---

## Changelog

`changelog.py` records what changed on the pill page and plots it onto the
performance charts, so a ranking or traffic movement can be read against what
actually shipped that day.

- **Auto-detected** — diffs our page day over day against the content-audit
  history (`docs/content.json`): title, meta, H1, robots, H2 sections added /
  removed / reordered, FAQs, word count, sub-heading count and topical
  coverage. Regenerated from scratch each run, so it is idempotent. Headings
  that differ only by digits (`46,000+ reviews` → `47,000+ reviews`) are
  treated as the same section, and word-count moves under 25 are ignored, to
  keep rolling boilerplate out of the log.
- **Logged by hand** — anything the crawler cannot see (accordion default
  state, visual reordering, design changes) goes in
  `data/changelog_manual.json`:

  ```json
  [{"date":"2026-09-03","changes":[{"type":"ux","text":"Accordions open by default"}]}]
  ```

  `type` drives the colour of the chart marker and the chip: `ux`, `seo`,
  `content`, `structure`, `technical`, `eeat`.

Run it standalone with `python changelog.py` (or `--test` for the offline
self-test); the daily patrol runs it automatically.

## Advanced Web Ranking (AWR)

Uses the documented **AWR Cloud v2 export API**
(`https://api.awrcloud.com/v2/get.php`): calls `export_ranking` with
`format=json`, follows the returned file URL, and parses the keyword groups,
selecting the UK / mobile result per keyword.

> ⚠️ **Use the right token.** AWR has two different credentials:
> - **AWR Cloud v2 API token** — a plain string from **Connectors & API
>   Settings**. *This* is what the daily patrol needs.
> - **MCP server JWT** (`api.advancedwebranking.com/mcp`) — for connecting AWR
>   to ChatGPT/Claude. It is **not** the v2 API token and won't work here.
>
> If a token is ever pasted into chat or code, rotate it in AWR.

Setup:

1. Add repo **secret** `AWR_API_TOKEN` = your **AWR Cloud v2 API token**.
2. Add repo **variables**:
   - `AWR_PROJECT` — the AWR project name that tracks these keywords.
   - Optional `AWR_GEO` (default `United Kingdom`), `AWR_DEVICE` (default `mobile`).
   - Optional `AWR_AUTH=bearer` + `AWR_BASE` to use a Bearer-token endpoint
     instead of the v2 export API.

> The v2 export field names are confirmed by the parser flexibly (it walks
> nested groups and detects keyword/position fields). This dev sandbox blocks
> egress to AWR, so the first GitHub Actions run (clean egress) is what verifies
> it end to end; if anything needs adjusting, share a sample response.

---

Test everything offline (uses canned fixtures, no network/keys):

```bash
python sentinel.py --test
```

## PageSpeed Insights (Lighthouse speed score)

Runs automatically each patrol — no credentials required. Google's public PSI
API is keyless but rate-limited per IP; if the runner ever hits 429s, create a
free API key (Google Cloud → enable "PageSpeed Insights API" → API key) and add
it as repo **secret** `PSI_API_KEY`. On failure the last known score is carried
forward (stamped "as of").
