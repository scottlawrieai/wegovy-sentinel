(function () {
  'use strict';

  // Template experiments: per-page before/after view around each page's
  // go-live date. One factory powers two tabs — the blog template test
  // (blog_experiment.json) and the product page test
  // (product_experiment.json), both written by blog_experiment_sentinel.py.
  // Each section fetches its own file since the shape differs from snapshots.

  function styleFor(id) {
    var s = '#sec-' + id;
    return '<style>' +
      s + ' .bt-url{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:#5B6B83;word-break:break-all}' +
      s + ' .bt-label{font-size:15px;font-weight:700;text-transform:capitalize}' +
      s + ' .bt-kpis{display:flex;flex-wrap:wrap;gap:22px;margin:10px 0 6px}' +
      s + ' .bt-kpi .n{font-size:24px;font-weight:800}' +
      s + ' .bt-kpi .l{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#5B6B83;font-weight:600}' +
      s + ' .bt-up{color:#2F9E44}' + s + ' .bt-down{color:#E03131}' +
      s + ' .bt-live{font-size:10px;font-weight:700;letter-spacing:.05em;padding:2px 8px;border-radius:10px;background:#E7F0FE;color:#1D4ED8;border:1px solid #BCD4F6}' +
      s + ' .bt-baseline{font-size:10px;font-weight:700;letter-spacing:.05em;padding:2px 8px;border-radius:10px;background:#FEF7E0;color:#B06000;border:1px solid #FDE293}' +
      s + ' tr.band td{background:#E7F0FE;border-top:1px solid #BCD4F6;border-bottom:1px solid #BCD4F6;font-size:12px;font-weight:700;color:#1D4ED8}' +
      s + ' .eyebrow-sm{font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;color:#5B6B83}' +
      s + ' .q-delta{display:inline-block;margin-left:6px;font-size:10px;font-weight:700}' +
      s + ' .q-up{color:#2F9E44}' + s + ' .q-down{color:#E03131}' +
      s + ' .q-flat{color:#94A3B8}' +
      s + ' .q-new{color:#1C7ED6;font-size:9px;letter-spacing:.04em;text-transform:uppercase}' +
      '</style>';
  }

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

  function pageCard(p, S, exp) {
    var live = p.live || null;
    var daily = p.series || [];
    var wk = weeklies(daily, S.state);

    var head = '<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;align-items:baseline">' +
      '<div><div class="bt-label">' + C.esc(p.label || '') + '</div>' +
      '<div class="bt-url">' + C.esc(p.url || '') + '</div></div>' +
      (live ? '<span class="bt-live">' + exp.liveTag + ' ' + C.esc(live) + '</span>'
            : '<span class="bt-baseline">BASELINE — not live yet</span>') +
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
        '<code>' + exp.configName + '</code> when it ships.</div>';
    }

    var markers = live ? [{ d: live, letter: 'T', color: '#1D4ED8' }] : [];
    var chart = C.lineChart({
      series: [
        { label: 'Clicks/day', color: '#1C7ED6', points: C.inRange(daily, S.state).map(function (r) { return { d: r.d, v: r.clicks }; }) },
        { label: 'Impressions/day', color: '#7048E8', points: C.inRange(daily, S.state).map(function (r) { return { d: r.d, v: r.impr }; }) }
      ],
      height: 170, markers: markers, showLegend: true
    });

    var kwChart = '';
    var kwKeys = p.kwseries ? Object.keys(p.kwseries) : [];
    if (kwKeys.length) {
      var kwColors = ['#1C7ED6', '#7048E8', '#2F9E44', '#E8590C', '#C2255C'];
      var kwSeries = kwKeys.slice(0, 5).map(function (k, i) {
        return { label: k, color: kwColors[i % kwColors.length],
                 points: C.inRange(p.kwseries[k] || [], S.state)
                   .filter(function (r) { return r.pos != null; })
                   .map(function (r) { return { d: r.d, v: r.pos }; }) };
      }).filter(function (s2) { return s2.points.length; });
      if (kwSeries.length) {
        kwChart = '<div style="font-size:10px;font-weight:700;letter-spacing:.08em;color:#5B6B83;margin-top:14px">' +
          'GSC POSITION \u00b7 TOP QUERIES \u00b7 THIS PAGE ONLY (lower = better)</div>' +
          C.lineChart({ series: kwSeries, height: 170, invertY: true,
                        markers: markers, showLegend: true,
                        yFmt: function (v) { return '#' + Math.round(v); } });
      }
    }

    var trs = '';
    wk.forEach(function (w) {
      if (live && live >= w.from && live <= w.to) {
        trs += '<tr class="band"><td colspan="5">T · ' + exp.bandLabel + ' · ' + C.esc(live) + '</td></tr>';
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

    // Search-queries table, same output as the product tabs' SEARCH QUERIES
    // panel: trailing 28 days vs the preceding 28, heat cells + deltas.
    var qTable = '';
    var qRows = (p.queries || []).filter(function (r) { return r && r.q; });
    if (qRows.length) {
      var cMax = Math.max.apply(null, qRows.map(function (r) { return r.clicks || 0; }).concat([1]));
      var iMax = Math.max.apply(null, qRows.map(function (r) { return r.impr || 0; }).concat([1]));
      var pvs = qRows.map(function (r) { return r.pos; }).filter(function (v) { return v != null; });
      var pMin = Math.min.apply(null, pvs), pMax = Math.max.apply(null, pvs);
      function pctDelta(cur, prev) {
        if (prev == null) return '<span class="q-delta q-new">new</span>';
        if (!prev) return '';
        var d = (cur - prev) / prev * 100;
        if (Math.abs(d) < 0.5) return '<span class="q-delta q-flat">=</span>';
        var up = d > 0;
        return '<span class="q-delta ' + (up ? 'q-up' : 'q-down') + '">' +
          (up ? '\u25b2' : '\u25bc') + Math.abs(d).toFixed(0) + '%</span>';
      }
      function posDelta(cur, prev) {
        if (prev == null) return '<span class="q-delta q-new">new</span>';
        var d = prev - cur;
        if (Math.abs(d) < 0.05) return '<span class="q-delta q-flat">=</span>';
        var good = d > 0;
        return '<span class="q-delta ' + (good ? 'q-up' : 'q-down') + '">' +
          (good ? '\u25b2' : '\u25bc') + Math.abs(d).toFixed(1) + '</span>';
      }
      var anyPrev = qRows.some(function (r) { return r.prev; });
      var qtrs = qRows.map(function (r) {
        var pv = r.prev || null;
        var ctr = r.impr ? (r.clicks / r.impr * 100) : (r.ctr || 0);
        if (r.ctr != null) ctr = r.ctr;
        var pctr = pv ? (pv.ctr != null ? pv.ctr : (pv.impr ? pv.clicks / pv.impr * 100 : null)) : null;
        return '<tr>' +
          '<td>' + C.esc(r.q) + '</td>' +
          '<td class="num" style="background:' + C.esc(C.heat(r.clicks || 0, 0, cMax)) + '">' + C.esc(C.fmtInt(r.clicks || 0)) +
            (anyPrev ? pctDelta(r.clicks || 0, pv ? pv.clicks : null) : '') + '</td>' +
          '<td class="num" style="background:' + C.esc(C.heat(r.impr || 0, 0, iMax)) + '">' + C.esc(C.fmtInt(r.impr || 0)) +
            (anyPrev ? pctDelta(r.impr || 0, pv ? pv.impr : null) : '') + '</td>' +
          '<td class="num">' + C.esc((ctr || 0).toFixed(1)) + '%' +
            (anyPrev ? pctDelta(ctr || 0, pctr) : '') + '</td>' +
          '<td class="num" style="background:' + (r.pos != null ? C.esc(C.heat(r.pos, pMin, pMax, true)) : 'transparent') + '">' +
            (r.pos != null ? C.esc(r.pos.toFixed(1)) : '\u2014') +
            (anyPrev && r.pos != null ? posDelta(r.pos, pv ? pv.pos : null) : '') + '</td>' +
          '</tr>';
      }).join('');
      qTable = '<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin:14px 0 6px">' +
        '<span class="eyebrow-sm">Search queries \u2014 this page</span>' +
        '<span style="font-size:11px;color:#94A3B8">Google Search Console \u00b7 trailing 28 days vs the preceding 28</span></div>' +
        '<div class="tbl-wrap"><table class="tbl">' +
        '<thead><tr><th>Query</th><th class="num">Clicks</th><th class="num">Impressions</th>' +
        '<th class="num">CTR</th><th class="num">Position</th></tr></thead>' +
        '<tbody>' + qtrs + '</tbody></table></div>';
    }

    return '<div class="panel" style="margin-bottom:14px">' + head + kpis + chart + kwChart +
      '<div class="tbl-wrap" style="margin-top:8px"><table class="tbl">' +
      '<thead><tr><th>Week</th><th>Phase</th><th class="num">Clicks</th><th class="num">Impressions</th><th class="num">Avg position</th></tr></thead>' +
      '<tbody>' + (trs || '<tr><td colspan="5"><div class="empty">No data in range.</div></td></tr>') + '</tbody></table></div>' +
      qTable +
      '</div>';
  }

  function makeSection(exp) {
    var cache = null;

    function draw(body, S, d) {
      if (!d || !(d.pages || []).length) {
        body.innerHTML = styleFor(exp.id) + '<div class="panel"><div class="empty">' +
          exp.emptyMsg + '</div></div>';
        return;
      }
      var liveN = d.pages.filter(function (p) { return p.live; }).length;
      var html = styleFor(exp.id) +
        '<div style="font-size:12.5px;color:#5B6B83;margin-bottom:12px">' +
        C.esc(String(d.pages.length)) + ' pages in the cohort · ' + C.esc(String(liveN)) +
        ' live on the new template' +
        (d.criteria ? ' · selection: ' + C.esc(d.criteria) : '') +
        (d.as_of ? ' · data to ' + C.esc(d.as_of) : '') + '</div>';
      d.pages.forEach(function (p) { html += pageCard(p, S, exp); });
      body.innerHTML = html;
    }

    function render(body, S) {
      if (S.product.key !== exp.only) { body.innerHTML = ''; return; }
      if (cache) {
        draw(body, S, cache);
      } else {
        body.innerHTML = styleFor(exp.id) + '<div class="panel"><div class="empty">Loading experiment data…</div></div>';
      }
      fetch(exp.file, { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          var had = !!cache;
          cache = d;
          if (S.product.key === exp.only && (!had || d)) draw(body, S, d);
        })
        .catch(function () { if (!cache) draw(body, S, null); });
    }

    Sentinel.register({
      id: exp.id,
      only: exp.only,
      title: exp.title,
      sub: exp.sub,
      order: 5,
      render: render
    });
  }

  makeSection({
    id: 'blogtest',
    only: 'blogs',
    file: './blog_experiment.json',
    configName: 'data/blog_experiment_config.json',
    liveTag: 'NEW TEMPLATE LIVE',
    bandLabel: 'New template live',
    title: 'Blog template test',
    sub: 'Each page against its own Search Console baseline — flip a page to the new template, set its live date, and read the uplift.',
    emptyMsg: 'The cohort is selected automatically on the first patrol with GSC access: ' +
      'the health-advice pages with the most impressions sitting at average position 5–15. ' +
      'Check back after the next patrol, or edit <code>data/blog_experiment_config.json</code> to choose pages by hand.'
  });

  makeSection({
    id: 'prodtest',
    only: 'prodtests',
    file: './product_experiment.json',
    configName: 'data/product_experiment_config.json',
    liveTag: 'NEW PAGE LIVE',
    bandLabel: 'New page live',
    title: 'Product page test',
    sub: 'Rebuilt treatment pages against their own Search Console baseline — set each page\'s live date and read the uplift.',
    emptyMsg: 'No product pages configured yet. Add pages to ' +
      '<code>data/product_experiment_config.json</code> ({"pages":[{"url":"…","live":"YYYY-MM-DD"}]}) ' +
      'and the next patrol starts tracking them.'
  });
})();
