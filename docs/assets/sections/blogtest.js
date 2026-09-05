(function () {
  'use strict';

  // Blog template experiment: per-page before/after view around each page's
  // template go-live date, in the style of the migration report. Data comes
  // from docs/blog_experiment.json (written by blog_experiment_sentinel.py);
  // this section fetches it itself since the shape differs from snapshots.

  var STYLE = '<style>' +
    '#sec-blogtest .bt-url{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:#5B6B83;word-break:break-all}' +
    '#sec-blogtest .bt-label{font-size:15px;font-weight:700;text-transform:capitalize}' +
    '#sec-blogtest .bt-kpis{display:flex;flex-wrap:wrap;gap:22px;margin:10px 0 6px}' +
    '#sec-blogtest .bt-kpi .n{font-size:24px;font-weight:800}' +
    '#sec-blogtest .bt-kpi .l{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#5B6B83;font-weight:600}' +
    '#sec-blogtest .bt-up{color:#2F9E44}#sec-blogtest .bt-down{color:#E03131}' +
    '#sec-blogtest .bt-live{font-size:10px;font-weight:700;letter-spacing:.05em;padding:2px 8px;border-radius:10px;background:#E7F0FE;color:#1D4ED8;border:1px solid #BCD4F6}' +
    '#sec-blogtest .bt-baseline{font-size:10px;font-weight:700;letter-spacing:.05em;padding:2px 8px;border-radius:10px;background:#FEF7E0;color:#B06000;border:1px solid #FDE293}' +
    '#sec-blogtest tr.band td{background:#E7F0FE;border-top:1px solid #BCD4F6;border-bottom:1px solid #BCD4F6;font-size:12px;font-weight:700;color:#1D4ED8}' +
    '</style>';

  var CACHE = null;

  function weeklies(series, state) {
    var rows = C.inRange(series || [], state);
    return C.groupWeeks(rows).map(function (w) {
      var impr = w.rows.reduce(function (a, r) { return a + (r.impr || 0); }, 0);
      var wp = 0;
      w.rows.forEach(function (r) { if (r.pos != null) wp += r.pos * (r.impr || 0); });
      return {
        key: w.key, from: w.from, to: w.to,
        clicks: w.rows.reduce(function (a, r) { return a + (r.clicks || 0); }, 0),
        impr: impr,
        pos: impr > 0 ? wp / impr : null
      };
    });
  }

  function avg(rows, field) {
    if (!rows.length) return null;
    return rows.reduce(function (a, r) { return a + (r[field] || 0); }, 0) / rows.length;
  }

  function uplift(before, after) {
    if (before == null || after == null || before === 0) return null;
    return (after - before) / before * 100;
  }

  function upliftHtml(v, invert) {
    if (v == null) return '<span style="color:#94A3B8">—</span>';
    var good = invert ? v < 0 : v > 0;
    return '<span class="' + (good ? 'bt-up' : 'bt-down') + '">' +
      (v > 0 ? '▲' : '▼') + Math.abs(v).toFixed(0) + '%</span>';
  }

  function pageCard(p, S) {
    var live = p.live || null;
    var daily = p.series || [];
    var wk = weeklies(daily, S.state);

    var head = '<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;align-items:baseline">' +
      '<div><div class="bt-label">' + C.esc(p.label || '') + '</div>' +
      '<div class="bt-url">' + C.esc(p.url || '') + '</div></div>' +
      (live ? '<span class="bt-live">NEW TEMPLATE LIVE ' + C.esc(live) + '</span>'
            : '<span class="bt-baseline">BASELINE — template not live yet</span>') +
      '</div>';

    // before/after KPIs: equal-length windows either side of the live date,
    // capped at 21 days each so early reads are like-for-like
    var kpis = '';
    if (live && daily.length) {
      var after = daily.filter(function (r) { return r.d >= live; });
      var n = Math.min(after.length, 21);
      after = after.slice(0, n);
      var before = daily.filter(function (r) { return r.d < live; }).slice(-n);
      if (n >= 3 && before.length >= 3) {
        var bClicks = avg(before, 'clicks'), aClicks = avg(after, 'clicks');
        var bImpr = avg(before, 'impr'), aImpr = avg(after, 'impr');
        var bi = before.reduce(function (a, r) { return a + (r.impr || 0); }, 0);
        var ai = after.reduce(function (a, r) { return a + (r.impr || 0); }, 0);
        var bPos = bi ? before.reduce(function (a, r) { return a + (r.pos || 0) * (r.impr || 0); }, 0) / bi : null;
        var aPos = ai ? after.reduce(function (a, r) { return a + (r.pos || 0) * (r.impr || 0); }, 0) / ai : null;
        kpis = '<div class="bt-kpis">' +
          '<div class="bt-kpi"><div class="n">' + upliftHtml(uplift(bClicks, aClicks)) + '</div><div class="l">Clicks/day (' + n + 'd vs ' + before.length + 'd)</div></div>' +
          '<div class="bt-kpi"><div class="n">' + upliftHtml(uplift(bImpr, aImpr)) + '</div><div class="l">Impressions/day</div></div>' +
          '<div class="bt-kpi"><div class="n">' + upliftHtml(uplift(bPos, aPos), true) + '</div><div class="l">Avg position (down = better)</div></div>' +
          '<div class="bt-kpi"><div class="n">' + C.esc((aClicks || 0).toFixed(1)) + '</div><div class="l">Clicks/day after</div></div>' +
          '</div>';
      } else {
        kpis = '<div style="font-size:12px;color:#5B6B83;margin:8px 0">Live ' +
          C.esc(live) + ' — after-window building (' + after.length +
          ' days so far; verdict needs at least 3, best at 14–21).</div>';
      }
    } else if (!live) {
      kpis = '<div style="font-size:12px;color:#5B6B83;margin:8px 0">Baseline collecting — ' +
        daily.length + ' days of GSC history banked. Set <code>"live": "YYYY-MM-DD"</code> for this page in ' +
        '<code>data/blog_experiment_config.json</code> when the new template ships.</div>';
    }

    var markers = live ? [{ d: live, letter: 'T', color: '#1D4ED8' }] : [];
    var chart = C.lineChart({
      series: [
        { label: 'Clicks/day', color: '#1C7ED6', points: C.inRange(daily, S.state).map(function (r) { return { d: r.d, v: r.clicks }; }) },
        { label: 'Impressions/day', color: '#7048E8', points: C.inRange(daily, S.state).map(function (r) { return { d: r.d, v: r.impr }; }) }
      ],
      height: 170, markers: markers, showLegend: true
    });

    var trs = '';
    wk.forEach(function (w) {
      if (live && live >= w.from && live <= w.to) {
        trs += '<tr class="band"><td colspan="5">T · New template live · ' + C.esc(live) + '</td></tr>';
      }
      var phase = !live ? '—' : (w.to < live ? 'Before' : (w.from >= live ? 'After' : 'Cutover'));
      trs += '<tr>' +
        '<td style="white-space:nowrap">' + C.esc(w.key) + '</td>' +
        '<td style="color:#5B6B83">' + phase + '</td>' +
        '<td class="num">' + C.esc(C.fmtInt(w.clicks)) + '</td>' +
        '<td class="num">' + C.esc(C.fmtInt(w.impr)) + '</td>' +
        '<td class="num">' + (w.pos == null ? '—' : C.esc(w.pos.toFixed(1))) + '</td>' +
        '</tr>';
    });

    var queries = (p.queries || []).slice(0, 5).map(function (q) {
      return C.esc(q.q) + ' <span style="color:#94A3B8">(' + C.esc(String(q.pos != null ? q.pos.toFixed(1) : '—')) + ')</span>';
    }).join(' · ');

    return '<div class="panel" style="margin-bottom:14px">' + head + kpis + chart +
      '<div class="tbl-wrap" style="margin-top:8px"><table class="tbl">' +
      '<thead><tr><th>Week</th><th>Phase</th><th class="num">Clicks</th><th class="num">Impressions</th><th class="num">Avg position</th></tr></thead>' +
      '<tbody>' + (trs || '<tr><td colspan="5"><div class="empty">No data in range.</div></td></tr>') + '</tbody></table></div>' +
      (queries ? '<div class="perf-chart-note" style="margin-top:6px">Top queries: ' + queries + '</div>' : '') +
      '</div>';
  }

  function render(body, S) {
    if (S.product.key !== 'blogs') { body.innerHTML = ''; return; }
    if (CACHE) {
      draw(body, S, CACHE);
    } else {
      body.innerHTML = STYLE + '<div class="panel"><div class="empty">Loading experiment data…</div></div>';
    }
    fetch('./blog_experiment.json', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var had = !!CACHE;
        CACHE = d;
        if (S.product.key === 'blogs' && (!had || d)) draw(body, S, d);
      })
      .catch(function () { if (!CACHE) draw(body, S, null); });
  }

  function draw(body, S, d) {
    if (!d || !(d.pages || []).length) {
      body.innerHTML = STYLE + '<div class="panel"><div class="empty">' +
        'The cohort is selected automatically on the first patrol with GSC access: ' +
        'the health-advice pages with the most impressions sitting at average position 5–15. ' +
        'Check back after the next patrol, or edit <code>data/blog_experiment_config.json</code> to choose pages by hand.' +
        '</div></div>';
      return;
    }
    var liveN = d.pages.filter(function (p) { return p.live; }).length;
    var html = STYLE +
      '<div style="font-size:12.5px;color:#5B6B83;margin-bottom:12px">' +
      C.esc(String(d.pages.length)) + ' pages in the cohort · ' + C.esc(String(liveN)) +
      ' live on the new template · selection: ' + C.esc(d.criteria || '') +
      (d.as_of ? ' · data to ' + C.esc(d.as_of) : '') + '</div>';
    d.pages.forEach(function (p) { html += pageCard(p, S); });
    body.innerHTML = html;
  }

  Sentinel.register({
    id: 'blogtest',
    only: 'blogs',
    title: 'Blog template test',
    sub: 'Each page against its own Search Console baseline — flip a page to the new template, set its live date, and read the uplift.',
    order: 5,
    render: render
  });
})();
