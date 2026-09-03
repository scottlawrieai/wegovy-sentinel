/* Sentinel section: Keyword rankings — per-keyword small multiples across rank sources */
(function () {
  'use strict';

  var MAIN_KWS = [
    'wegovy pill',
    'wegovy pills',
    'wegovy price',
    'wegovy price uk',
    'wegovy uk',
    'oral semaglutide'
  ];

  var SOURCES = [
    { value: 'semrush', label: 'Semrush' },
    { value: 'gsc', label: 'Search Console' },
    { value: 'awr', label: 'AWR' },
    { value: 'comp', label: 'vs Competitors' }
  ];

  var COMP_COLORS = {
    'Superdrug': '#1C7ED6',
    'Chemist4U': '#E8590C',
    'FamilyChemist': '#7048E8',
    'MedExpress': '#0CA678',
    'Boots': '#C2255C'
  };

  var CSS =
    '<style>' +
    '.rank-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}' +
    '@media (max-width:900px){.rank-grid{grid-template-columns:1fr}}' +
    '.rank-card .rank-kw{font-size:13px;font-weight:700;color:var(--ink)}' +
    '.rank-card .rank-now{display:flex;align-items:baseline;gap:8px;margin:2px 0 8px}' +
    '.rank-card .rank-pos{font-size:28px;font-weight:800;color:var(--ink);line-height:1.15}' +
    '.rank-card .rank-delta{font-size:12px}' +
    '.rank-card .rank-note{font-size:11px;color:var(--muted);margin-top:6px}' +
    '.rank-card .empty{min-height:190px}' +
    '.rank-feats{display:flex;flex-wrap:wrap;gap:4px;margin:2px 0 6px}' +
    '.rank-feat{font-size:9.5px;font-weight:600;color:#5B6B83;background:#EEF2F7;border:1px solid #E2E8F0;border-radius:8px;padding:1px 6px}' +
    '.rank-vol{font-size:9.5px;font-weight:700;color:#B45309;background:#FEF3C7;border:1px solid #FDE293;border-radius:8px;padding:1px 6px}' +
    '</style>';

  // module-local state: active ranking source
  var activeSrc = 'semrush';

  function shiftDaysIso(isoStr, n) {
    var dt = new Date(isoStr + 'T00:00:00Z');
    if (isNaN(dt.getTime())) return isoStr;
    dt.setUTCDate(dt.getUTCDate() + n);
    return dt.toISOString().slice(0, 10);
  }

  function intFmt(v) {
    return (v == null || isNaN(v)) ? '' : String(Math.round(v));
  }

  function sortByDate(pts) {
    return pts.slice().sort(function (a, b) { return a.d < b.d ? -1 : (a.d > b.d ? 1 : 0); });
  }

  /* latest non-null value + delta vs the last non-null value at/before 7 days earlier */
  function latestDelta(pts) {
    var nn = sortByDate(pts).filter(function (p) { return p && p.v != null && !isNaN(p.v); });
    if (!nn.length) return null;
    var last = nn[nn.length - 1];
    var cutoff = shiftDaysIso(last.d, -7);
    var prev = null;
    for (var i = 0; i < nn.length; i++) {
      if (nn[i].d <= cutoff) prev = nn[i]; else break;
    }
    return { v: last.v, d: last.d, delta: prev ? last.v - prev.v : null };
  }

  function deltaHtml(ld) {
    if (!ld) return '<span class="rank-delta" style="color:var(--muted)">no data in range</span>';
    if (ld.delta == null) {
      return '<span class="rank-delta" style="color:var(--muted)">no 7d comparison</span>';
    }
    if (ld.delta === 0) {
      return '<span class="rank-delta" style="color:var(--muted)">— vs 7d ago</span>';
    }
    // lower position = better
    var better = ld.delta < 0;
    var cls = better ? 'delta-pos' : 'delta-neg';
    var arrow = better ? '▲' : '▼';
    return '<span class="rank-delta ' + cls + '">' + arrow + ' ' +
      C.esc(Math.abs(Math.round(ld.delta))) + ' vs 7d ago</span>';
  }

  /* ---------- per-source point builders (full history; range applied later) ---------- */

  function semrushPoints(snaps, kw) {
    return (snaps || []).map(function (s) {
      var b = s && s.best ? s.best[kw] : null;
      return { d: s && s.date, v: (b && b.p != null && !isNaN(b.p)) ? b.p : null };
    }).filter(function (p) { return !!p.d; });
  }

  function gscPoints(snaps, kw) {
    if (!snaps || !snaps.length) return [];
    // prefer the last snapshot's daily gsckw series
    var last = snaps[snaps.length - 1];
    var daily = last && last.gsckw ? last.gsckw[kw] : null;
    if (Array.isArray(daily) && daily.length) {
      return daily.map(function (r) {
        return { d: r && r.d, v: (r && r.pos != null && !isNaN(r.pos)) ? r.pos : null };
      }).filter(function (p) { return !!p.d; });
    }
    // fall back to snapshot history of src.gsc
    var out = [];
    (snaps || []).forEach(function (s) {
      if (!s || !s.date) return;
      var g = s.src && s.src.gsc ? s.src.gsc[kw] : null;
      out.push({ d: s.date, v: (g && g.pos != null && !isNaN(g.pos)) ? g.pos : null });
    });
    var hasAny = out.some(function (p) { return p.v != null; });
    return hasAny ? out : [];
  }

  function awrPoints(snaps, kw) {
    return (snaps || []).map(function (s) {
      var v = s && s.src && s.src.awr ? s.src.awr[kw] : null;
      return { d: s && s.date, v: (v != null && !isNaN(v)) ? v : null };
    }).filter(function (p) { return !!p.d; });
  }

  function compSeries(snaps, kw) {
    var series = [{ label: 'SOP', color: '#0F172A', points: semrushPoints(snaps, kw) }];
    Object.keys(COMP_COLORS).forEach(function (label) {
      var pts = (snaps || []).map(function (s) {
        var e = s && s.comp && s.comp[label] ? s.comp[label][kw] : null;
        return { d: s && s.date, v: (e && e.p != null && !isNaN(e.p)) ? e.p : null };
      }).filter(function (p) { return !!p.d; });
      var hasAny = pts.some(function (p) { return p.v != null; });
      if (hasAny) series.push({ label: label, color: COMP_COLORS[label], points: pts });
    });
    return series;
  }

  /* ---------- card rendering ---------- */

  function emptyCard(kw, msg) {
    return '<div class="panel rank-card">' +
      '<div class="rank-kw">' + C.esc(kw) + '</div>' +
      '<div class="empty">' + C.esc(msg) + '</div>' +
      '</div>';
  }

  function chartMarkers(S, series) {
    var dates = new Set();
    series.forEach(function (s) {
      (s.points || []).forEach(function (p) { if (p && p.d) dates.add(p.d); });
    });
    var letters = C.letters(S.data.changelog, dates);
    return Object.keys(letters).sort().map(function (d) {
      return { d: d, letter: letters[d] };
    });
  }

  function kwCard(S, kw) {
    var snaps = S.data.snaps;

    if (activeSrc === 'gsc') {
      var gp = gscPoints(snaps, kw);
      if (!gp.length) {
        return emptyCard(kw,
          'Daily Search Console series arrives after the next patrol runs with GSC credentials');
      }
      return seriesCard(S, kw,
        [{ label: 'Search Console', color: '#0CA678', points: C.inRange(gp, S.state) }],
        false, '');
    }

    if (activeSrc === 'awr') {
      var ap = awrPoints(snaps, kw);
      var tracked = ap.filter(function (p) { return p.v != null; }).length;
      if (!tracked) {
        return emptyCard(kw,
          'No AWR data for this keyword yet — set AWR_API_TOKEN and AWR_PROJECT so the patrol can pull AWR rankings');
      }
      return seriesCard(S, kw,
        [{ label: 'AWR', color: '#E8590C', points: C.inRange(ap, S.state) }],
        false, C.fmtInt(tracked) + ' tracked days');
    }

    if (activeSrc === 'comp') {
      var series = compSeries(snaps, kw).map(function (s) {
        return { label: s.label, color: s.color, points: C.inRange(s.points, S.state) };
      });
      return seriesCard(S, kw, series, true, '');
    }

    // default: Semrush
    return seriesCard(S, kw,
      [{ label: 'Semrush', color: '#1C7ED6', points: C.inRange(semrushPoints(snaps, kw), S.state) }],
      false, '');
  }

  // Semrush SERP-feature codes -> labels (unknown codes shown as F<code>)
  var FEATURES = {
    0: 'Instant answer', 1: 'Knowledge panel', 3: 'Local pack', 5: 'Images',
    6: 'Sitelinks', 7: 'Reviews', 9: 'Video', 10: 'Featured video',
    11: 'Featured snippet', 13: 'Image pack', 14: 'Ads top', 15: 'Ads bottom',
    16: 'Shopping', 21: 'People also ask', 22: 'FAQ'
  };

  function serpChips(S, kw) {
    var snaps = S.data.snaps || [];
    for (var i = snaps.length - 1; i >= 0; i--) {
      var km = snaps[i] && snaps[i].kwmeta;
      if (km && Object.keys(km).length) {
        var m = km[kw];
        if (!m) return '';
        var bits = (m.feat || []).slice(0, 5).map(function (c) {
          return '<span class="rank-feat">' + C.esc(FEATURES[c] || ('F' + c)) + '</span>';
        }).join('');
        var volTxt = m.v ? '<span class="rank-vol">' + C.esc(C.fmtInt(m.v)) + '/mo</span>' : '';
        return (bits || volTxt) ? '<div class="rank-feats">' + volTxt + bits + '</div>' : '';
      }
    }
    return '';
  }

  function seriesCard(S, kw, series, showLegend, note) {
    // headline stat comes from the primary (first) series of the active source
    var ld = latestDelta(series[0] ? series[0].points : []);
    var posHtml = ld ? '#' + C.esc(Math.round(ld.v)) : '—';

    var chart = C.lineChart({
      series: series,
      height: 190,
      invertY: true,
      yFmt: intFmt,
      markers: chartMarkers(S, series),
      showLegend: !!showLegend
    });

    return '<div class="panel rank-card">' +
      '<div class="rank-kw">' + C.esc(kw) + '</div>' +
      serpChips(S, kw) +
      '<div class="rank-now">' +
        '<span class="rank-pos">' + posHtml + '</span>' +
        deltaHtml(ld) +
      '</div>' +
      chart +
      (note ? '<div class="rank-note">' + C.esc(note) + '</div>' : '') +
      '</div>';
  }

  /* ---------- section ---------- */

  window.Sentinel.pillHandlers['rank-src'] = function (value) {
    activeSrc = value;
  };

  window.Sentinel.register({
    id: 'rankings',
    title: 'Keyword rankings',
    sub: 'Daily positions for the main Wegovy pill keywords, by ranking source.',
    order: 20,
    render: function (body, S) {
      var html = CSS + C.pills('rank-src', SOURCES, activeSrc);
      html += '<div class="rank-grid">';
      var kws = (S.product && S.product.mainKws) || MAIN_KWS;
      kws.forEach(function (kw) {
        html += kwCard(S, kw);
      });
      html += '</div>';
      body.innerHTML = html;
    }
  });
})();
