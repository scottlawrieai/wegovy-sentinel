/* Sentinel section: Search performance (GSC clicks/impressions + change tracking) */
(function () {
  'use strict';

  var TYPE_COLORS = {
    ux: '#1C7ED6',
    seo: '#E8590C',
    content: '#7048E8',
    structure: '#0CA678',
    technical: '#868E96',
    eeat: '#2F9E44'
  };

  var CLICKS_COLOR = '#1C7ED6';
  var IMPR_COLOR = '#7048E8';

  var view = 'page'; // 'page' | 'site'

  var STYLE =
    '<style>' +
    '#sec-perf .perf-badge{display:inline-flex;align-items:center;justify-content:center;' +
      'width:18px;height:18px;border-radius:50%;background:#1D4ED8;color:#fff;' +
      'font-size:10px;font-weight:700;line-height:1;flex:0 0 auto;margin-right:2px}' +
    '#sec-perf .perf-badge.grey{background:#868E96}' +
    '#sec-perf .perf-chip{display:inline-block;font-size:10px;font-weight:700;' +
      'text-transform:uppercase;letter-spacing:.05em;border:1px solid currentColor;' +
      'border-radius:6px;padding:1px 6px;line-height:1.5;flex:0 0 auto}' +
    '#sec-perf .perf-changes{margin-top:14px;display:flex;flex-direction:column;gap:8px}' +
    '#sec-perf .perf-change-row{display:flex;align-items:center;gap:8px;font-size:12.5px;flex-wrap:wrap}' +
    '#sec-perf .perf-change-date{color:#5B6B83;font-variant-numeric:tabular-nums;white-space:nowrap}' +
    '#sec-perf .perf-change-tag{font-size:10px;color:#94A3B8;text-transform:uppercase;letter-spacing:.06em}' +
    '#sec-perf .perf-toolbar{display:flex;align-items:center;justify-content:space-between;' +
      'gap:12px;flex-wrap:wrap;margin:16px 0 10px}' +
    '#sec-perf .perf-note{font-size:11px;color:#94A3B8;margin-top:6px}' +
    '#sec-perf .perf-tbl-panel{margin-top:14px}' +
    '</style>';

  function shiftDays(isoStr, n) {
    var dt = new Date(isoStr + 'T00:00:00Z');
    dt.setUTCDate(dt.getUTCDate() + n);
    return dt.toISOString().slice(0, 10);
  }
  function dayCount(from, to) {
    return Math.round((new Date(to + 'T00:00:00Z') - new Date(from + 'T00:00:00Z')) / 86400000) + 1;
  }

  function sum(rows, key) {
    var t = 0;
    rows.forEach(function (r) { if (r && r[key] != null && !isNaN(r[key])) t += r[key]; });
    return t;
  }
  function wPos(rows) {
    var wsum = 0, w = 0, plain = 0, n = 0;
    rows.forEach(function (r) {
      if (!r || r.pos == null || isNaN(r.pos)) return;
      plain += r.pos; n++;
      var im = (r.impr != null && !isNaN(r.impr)) ? r.impr : 0;
      wsum += r.pos * im; w += im;
    });
    if (!n) return null;
    return w > 0 ? wsum / w : plain / n;
  }

  // delta: {v, invert} -> arrow + coloured span; invert = lower is better
  function deltaHtml(v, fmt, invert) {
    if (v == null || isNaN(v)) return '<span style="color:#94A3B8">no prior data</span>';
    if (Math.abs(v) < 1e-9) return '<span style="color:#94A3B8">— vs prev</span>';
    var up = v > 0;
    var good = invert ? !up : up;
    var cls = good ? 'delta-pos' : 'delta-neg';
    var arrow = up ? '▲' : '▼';
    return '<span class="' + cls + '">' + arrow + ' ' + C.esc(fmt(Math.abs(v))) + '</span> vs prev';
  }

  function kpi(label, value, context) {
    return '<div class="kpi">' +
      '<div class="label">' + C.esc(label) + '</div>' +
      '<div class="value">' + value + '</div>' +
      '<div class="context">' + context + '</div>' +
      '</div>';
  }
  function mutedKpi(label) {
    return '<div class="kpi">' +
      '<div class="label">' + C.esc(label) + '</div>' +
      '<div class="value" style="color:#94A3B8">—</div>' +
      '<div class="context">needs GSC</div>' +
      '</div>';
  }

  function fmtCtr(v) { return v.toFixed(2) + '%'; }
  function fmtPos(v) { return v.toFixed(1); }

  function latestGscts(snaps) {
    for (var i = (snaps || []).length - 1; i >= 0; i--) {
      var g = snaps[i] && snaps[i].gscts;
      if (g && (((g.page || []).length) || ((g.site || []).length))) return g;
    }
    return null;
  }

  // flat chronological list of {date, type, text, source}
  function flatChanges(changelog) {
    var out = [];
    (changelog || []).forEach(function (e) {
      if (!e || !e.date) return;
      (e.changes || []).forEach(function (c) {
        if (c) out.push({ date: e.date, type: c.type || '', text: c.text || '', source: c.source || '' });
      });
    });
    out.sort(function (a, b) { return a.date < b.date ? -1 : (a.date > b.date ? 1 : 0); });
    return out;
  }

  function badge(letter, grey) {
    return '<span class="perf-badge' + (grey ? ' grey' : '') + '">' +
      C.esc(letter || '·') + '</span>';
  }
  function chip(type) {
    var col = TYPE_COLORS[type] || '#5B6B83';
    return '<span class="perf-chip" style="color:' + C.esc(col) + '">' + C.esc(type || '?') + '</span>';
  }

  function emptyGsc(what) {
    return '<div class="panel"><div class="empty">' +
      C.esc(what) + ' will appear once Search Console credentials are configured — add the ' +
      '<code>GSC_CLIENT_ID</code>, <code>GSC_CLIENT_SECRET</code> and <code>GSC_REFRESH_TOKEN</code> ' +
      'secrets plus the <code>GSC_PROPERTY</code> variable, then wait for the next patrol.' +
      '</div></div>';
  }

  function render(body, S) {
    var state = S.state;
    var snaps = S.data.snaps || [];
    var changelog = (S.data.changelog || []).slice().sort(function (a, b) {
      return (a && a.date) < (b && b.date) ? -1 : 1;
    });
    var g = latestGscts(snaps);

    // shared letter mapping: changelog dates inside the selected range
    var inRangeDates = changelog
      .map(function (e) { return e && e.date; })
      .filter(function (d) { return d && d >= state.from && d <= state.to; });
    var letters = C.letters(changelog, inRangeDates);

    var html = STYLE;

    /* ---------- KPI row ---------- */

    if (g) {
      var rows = (view === 'site' ? g.site : g.page) || [];
      var cur = C.inRange(rows, state);
      var len = dayCount(state.from, state.to);
      var prevState = { from: shiftDays(state.from, -len), to: shiftDays(state.from, -1) };
      var prev = C.inRange(rows, prevState);

      var clicks = sum(cur, 'clicks'), impr = sum(cur, 'impr');
      var ctr = impr > 0 ? clicks / impr * 100 : null;
      var pos = wPos(cur);

      var pClicks = prev.length ? sum(prev, 'clicks') : null;
      var pImpr = prev.length ? sum(prev, 'impr') : null;
      var pCtr = (prev.length && pImpr > 0) ? sum(prev, 'clicks') / pImpr * 100 : null;
      var pPos = prev.length ? wPos(prev) : null;

      html += '<div class="kpis">' +
        kpi('Total clicks', cur.length ? C.fmtInt(clicks) : '—',
          deltaHtml(pClicks == null ? null : clicks - pClicks, C.fmtInt, false)) +
        kpi('Total impressions', cur.length ? C.fmtInt(impr) : '—',
          deltaHtml(pImpr == null ? null : impr - pImpr, C.fmtInt, false)) +
        kpi('Avg CTR', ctr == null ? '—' : C.esc(fmtCtr(ctr)),
          deltaHtml((pCtr == null || ctr == null) ? null : ctr - pCtr,
            function (v) { return v.toFixed(2) + 'pp'; }, false)) +
        kpi('Avg position', pos == null ? '—' : C.esc(fmtPos(pos)),
          deltaHtml((pPos == null || pos == null) ? null : pos - pPos, fmtPos, true)) +
        '</div>';
    } else {
      // Semrush fallback for the first card
      var last = snaps.length ? snaps[snaps.length - 1] : null;
      var pill = last && last.m ? last.m.pill : null;
      var ago = snaps.length > 7 ? snaps[snaps.length - 8] : null;
      var pillPrev = ago && ago.m ? ago.m.pill : null;
      var d = (pill != null && pillPrev != null) ? pill - pillPrev : null;
      html += '<div class="kpis">' +
        kpi('"wegovy pill" position (Semrush)',
          pill == null ? '—' : '#' + C.esc(C.fmtInt(pill)),
          deltaHtml(d, C.fmtInt, true)) +
        mutedKpi('Total impressions') +
        mutedKpi('Avg CTR') +
        mutedKpi('Avg position') +
        '</div>';
    }

    /* ---------- toolbar: URL view pills ---------- */

    html += '<div class="perf-toolbar">' +
      C.pills('perf-view', [
        { value: 'page', label: 'Pill page' },
        { value: 'site', label: 'Whole site' }
      ], view) +
      '<span class="perf-change-tag">Source: Google Search Console · ' +
      (view === 'site' ? 'whole property' : 'Wegovy pill page') + '</span>' +
      '</div>';

    /* ---------- weekly chart + weekly table ---------- */

    if (g) {
      var rows2 = (view === 'site' ? g.site : g.page) || [];
      var cur2 = C.inRange(rows2, state);
      var weeks = C.groupWeeks(cur2);

      // weekly aggregates
      var wk = weeks.map(function (w) {
        var im = sum(w.rows, 'impr');
        return {
          key: w.key, from: w.from, to: w.to,
          clicks: sum(w.rows, 'clicks'),
          impr: im,
          pos: wPos(w.rows),
          changes: changelog.filter(function (e) {
            return e && e.date && letters[e.date] && e.date >= w.from && e.date <= w.to;
          })
        };
      });

      // chart markers: one per lettered changelog date, sitting on its week
      var markers = [];
      wk.forEach(function (w) {
        w.changes.forEach(function (e) {
          markers.push({ d: w.from, letter: letters[e.date], color: '#1D4ED8' });
        });
      });

      html += '<div class="panel">' +
        C.lineChart({
          series: [
            { label: 'Clicks (weekly)', color: CLICKS_COLOR, points: wk.map(function (w) { return { d: w.from, v: w.clicks }; }) },
            { label: 'Impressions (weekly)', color: IMPR_COLOR, points: wk.map(function (w) { return { d: w.from, v: w.impr }; }) }
          ],
          markers: markers,
          showLegend: true,
          height: 260
        }) +
        '<div class="perf-note">Weekly Google Search clicks · lettered markers = logged changes</div>' +
        '</div>';

      // heat domains
      var cMin = Infinity, cMax = -Infinity, iMin = Infinity, iMax = -Infinity, pMin = Infinity, pMax = -Infinity;
      wk.forEach(function (w) {
        if (w.clicks < cMin) cMin = w.clicks;
        if (w.clicks > cMax) cMax = w.clicks;
        if (w.impr < iMin) iMin = w.impr;
        if (w.impr > iMax) iMax = w.impr;
        if (w.pos != null) {
          if (w.pos < pMin) pMin = w.pos;
          if (w.pos > pMax) pMax = w.pos;
        }
      });

      var trs = '';
      wk.forEach(function (w) {
        w.changes.forEach(function (e) {
          var first = (e.changes && e.changes[0] && e.changes[0].text) || '';
          var more = (e.changes || []).length - 1;
          trs += '<tr class="band"><td colspan="5">' +
            C.esc(letters[e.date]) + ' · ' + C.esc(e.date) + ' — ' + C.esc(first) +
            (more > 0 ? ' (+' + C.esc(more) + ' more)' : '') +
            '</td></tr>';
        });
        var badges = w.changes.map(function (e) { return badge(letters[e.date], false); }).join('');
        trs += '<tr>' +
          '<td style="white-space:nowrap">' + C.esc(w.key) + '</td>' +
          '<td>' + (badges || '<span style="color:#94A3B8">—</span>') + '</td>' +
          '<td class="num" style="background:' + C.esc(C.heat(w.clicks, cMin, cMax)) + '">' + C.esc(C.fmtInt(w.clicks)) + '</td>' +
          '<td class="num" style="background:' + C.esc(C.heat(w.impr, iMin, iMax)) + '">' + C.esc(C.fmtInt(w.impr)) + '</td>' +
          '<td class="num" style="background:' + C.esc(C.heat(w.pos, pMin, pMax, true)) + '">' +
            (w.pos == null ? '—' : C.esc(fmtPos(w.pos))) + '</td>' +
          '</tr>';
      });

      html += '<div class="panel perf-tbl-panel"><div class="tbl-wrap"><table class="tbl">' +
        '<thead><tr>' +
        '<th>Week</th><th>Changes</th>' +
        '<th class="num">Clicks</th><th class="num">Impressions</th><th class="num">Avg position</th>' +
        '</tr></thead><tbody>' +
        (trs || '<tr><td colspan="5"><div class="empty">No data in this range.</div></td></tr>') +
        '</tbody></table></div></div>';
    } else {
      html += emptyGsc('Weekly clicks chart and table');
    }

    /* ---------- full change list ---------- */

    var flat = flatChanges(changelog);
    if (flat.length) {
      html += '<div class="perf-changes">';
      flat.forEach(function (c) {
        var letter = letters[c.date];
        html += '<div class="perf-change-row">' +
          badge(letter || '', !letter) +
          '<span class="perf-change-date">' + C.esc(c.date) + '</span>' +
          chip(c.type) +
          '<span>' + C.esc(c.text) + '</span>' +
          '<span class="perf-change-tag">' + (c.source === 'manual' ? 'logged' : 'detected') + '</span>' +
          '</div>';
      });
      html += '</div>';
    }

    body.innerHTML = html;
  }

  if (window.Sentinel && window.C) {
    window.Sentinel.pillHandlers['perf-view'] = function (v) {
      if (v === 'page' || v === 'site') view = v;
    };
    window.Sentinel.register({
      id: 'perf',
      title: 'Search performance',
      sub: 'Google Search Console clicks and impressions, week by week, against logged page changes.',
      order: 10,
      render: render
    });
  }
})();
