(function () {
  'use strict';

  // Share of voice + weekly movers, computed entirely from the Semrush
  // snapshot history — this panel has real data from day one, no GSC needed.

  var COMP_COLORS = {
    Superdrug: '#1C7ED6', Chemist4U: '#E8590C', FamilyChemist: '#7048E8',
    MedExpress: '#0CA678', Boots: '#C2255C'
  };

  // Click-through-rate curve by position: turns a set of rankings into a
  // single comparable visibility number (same idea Semrush/Sistrix use).
  function ctrAt(p) {
    if (p == null) return 0;
    if (p <= 1) return 0.28;
    if (p <= 2) return 0.15;
    if (p <= 3) return 0.10;
    if (p <= 4) return 0.07;
    if (p <= 5) return 0.05;
    if (p <= 6) return 0.04;
    if (p <= 7) return 0.035;
    if (p <= 8) return 0.03;
    if (p <= 9) return 0.027;
    if (p <= 10) return 0.025;
    if (p <= 20) return 0.01;
    return 0.004;
  }

  // latest known volume per keyword (kwmeta from the newest snapshot that
  // has it, topped up from best[kw].v); {} when nothing known yet
  function volumeMap(snaps) {
    var vol = {};
    for (var i = (snaps || []).length - 1; i >= 0; i--) {
      var km = snaps[i] && snaps[i].kwmeta;
      if (km && Object.keys(km).length) {
        Object.keys(km).forEach(function (k) {
          if (km[k] && km[k].v) vol[k] = km[k].v;
        });
        break;
      }
    }
    (snaps || []).forEach(function (s) {
      Object.keys((s && s.best) || {}).forEach(function (k) {
        var b = s.best[k];
        if (b && b.v && !vol[k]) vol[k] = b.v;
      });
    });
    return vol;
  }

  function trackedKws(snaps) {
    var set = {};
    (snaps || []).forEach(function (s) {
      Object.keys((s && s.best) || {}).forEach(function (k) { set[k] = 1; });
    });
    return Object.keys(set);
  }

  function sovOf(getPos, kws, vol) {
    var got = 0, max = 0;
    kws.forEach(function (kw) {
      var w = (vol && vol[kw]) || 500;   // unknown volume: modest default
      got += ctrAt(getPos(kw)) * w;
      max += 0.28 * w;
    });
    return max > 0 ? got / max * 100 : 0;
  }

  function snapAgo(snaps, n) {
    return snaps.length > n ? snaps[snaps.length - 1 - n] : null;
  }

  var STYLE = '<style>' +
    '#sec-movers .mv-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}' +
    '@media (max-width:980px){#sec-movers .mv-grid{grid-template-columns:1fr}}' +
    '#sec-movers .mv-kw{font-weight:600}' +
    '#sec-movers .mv-note{font-size:11px;color:#94A3B8;margin-top:6px}' +
    '#sec-movers td .up{color:#2F9E44;font-weight:700}' +
    '#sec-movers td .down{color:#E03131;font-weight:700}' +
    '#sec-movers td .flat{color:#94A3B8}' +
    '</style>';

  function render(body, S) {
    var snaps = S.data.snaps || [];
    var changelog = S.data.changelog || [];
    if (!snaps.length) {
      body.innerHTML = '<div class="panel"><div class="empty">No patrol history yet.</div></div>';
      return;
    }
    var kws = trackedKws(snaps);
    var vol = volumeMap(snaps);
    var comps = {};
    snaps.forEach(function (s) {
      Object.keys((s && s.comp) || {}).forEach(function (l) { comps[l] = 1; });
    });
    var compLabels = Object.keys(comps);

    /* ---------- share of voice trend ---------- */

    var series = [{
      label: 'SOP', color: '#0F172A',
      points: snaps.map(function (s) {
        return { d: s.date, v: sovOf(function (kw) {
          var b = s.best && s.best[kw]; return b ? b.p : null;
        }, kws, vol) };
      })
    }];
    compLabels.forEach(function (label) {
      series.push({
        label: label, color: COMP_COLORS[label] || '#868E96',
        points: snaps.map(function (s) {
          var c = (s.comp || {})[label] || {};
          var has = Object.keys(c).length > 0;
          return { d: s.date, v: has ? sovOf(function (kw) {
            return c[kw] ? c[kw].p : null;
          }, kws, vol) : null };
        })
      });
    });
    series.forEach(function (sr) { sr.points = C.inRange(sr.points, S.state); });

    var inRangeDates = changelog
      .map(function (e) { return e && e.date; })
      .filter(function (d) { return d && d >= S.state.from && d <= S.state.to; });
    var letters = C.letters(changelog, inRangeDates);

    var html = STYLE +
      '<div class="panel">' + C.lineChart({
        series: series, height: 230,
        yFmt: function (v) { return v.toFixed(0) + '%'; },
        markers: inRangeDates.map(function (d) {
          return { d: d, letter: letters[d] || '', color: '#1D4ED8' };
        }),
        showLegend: true
      }) +
      '<div class="mv-note">Share of voice — CTR- and search-volume-weighted visibility across all ' +
      C.esc(String(kws.length)) + ' tracked keywords (100% = P1 on every keyword). ' +
      'Computed from daily Semrush positions; lettered markers = logged changes.</div></div>';

    /* ---------- weekly movers table ---------- */

    var cur = snaps[snaps.length - 1];
    var ago = snapAgo(snaps, 7) || snaps[0];
    var rows = kws.map(function (kw) {
      var now = cur.best && cur.best[kw] ? cur.best[kw].p : null;
      var was = ago.best && ago.best[kw] ? ago.best[kw].p : null;
      var delta = (now != null && was != null) ? was - now : null; // + = improved
      var bestC = null;
      compLabels.forEach(function (label) {
        var c = (cur.comp || {})[label];
        if (c && c[kw] && (bestC == null || c[kw].p < bestC.p)) {
          bestC = { label: label, p: c[kw].p };
        }
      });
      return { kw: kw, now: now, was: was, delta: delta, bestC: bestC,
               vol: vol[kw] || null };
    }).filter(function (r) { return r.now != null || r.was != null || r.bestC; });

    rows.sort(function (a, b) {
      var va = a.vol == null ? -1 : a.vol;
      var vb = b.vol == null ? -1 : b.vol;
      if (vb !== va) return vb - va;                 // volume, highest first
      var da = a.delta == null ? -1 : Math.abs(a.delta);
      var db = b.delta == null ? -1 : Math.abs(b.delta);
      if (db !== da) return db - da;                 // then biggest move
      return (a.now == null ? 999 : a.now) - (b.now == null ? 999 : b.now);
    });

    var trs = '';
    rows.forEach(function (r) {
      var dCell;
      if (r.delta == null) dCell = '<span class="flat">—</span>';
      else if (r.delta > 0) dCell = '<span class="up">▲ ' + C.esc(String(r.delta)) + '</span>';
      else if (r.delta < 0) dCell = '<span class="down">▼ ' + C.esc(String(-r.delta)) + '</span>';
      else dCell = '<span class="flat">=</span>';
      var gap = (r.bestC && r.now != null) ? r.now - r.bestC.p : null;
      trs += '<tr>' +
        '<td class="mv-kw">' + C.esc(r.kw) + '</td>' +
        '<td class="num" style="color:#5B6B83">' + (r.vol == null ? '—' : C.esc(C.fmtInt(r.vol))) + '</td>' +
        '<td class="num">' + (r.now == null ? '—' : '#' + C.esc(String(r.now))) + '</td>' +
        '<td class="num">' + (r.was == null ? '—' : '#' + C.esc(String(r.was))) + '</td>' +
        '<td class="num">' + dCell + '</td>' +
        '<td>' + (r.bestC ? C.esc(r.bestC.label) + ' <span class="num">#' + C.esc(String(r.bestC.p)) + '</span>' : '—') + '</td>' +
        '<td class="num">' + (gap == null ? '—'
          : gap > 0 ? '<span class="down">' + C.esc(String(gap)) + ' behind</span>'
          : '<span class="up">' + C.esc(String(-gap)) + ' ahead</span>') + '</td>' +
        '</tr>';
    });

    html += '<div class="panel" style="margin-top:14px"><div class="tbl-wrap"><table class="tbl">' +
      '<thead><tr><th>Keyword</th><th class="num">Volume</th><th class="num">Now</th><th class="num">7d ago</th>' +
      '<th class="num">Δ</th><th>Best competitor</th><th class="num">Gap</th></tr></thead>' +
      '<tbody>' + (trs || '<tr><td colspan="7"><div class="empty">No ranking data.</div></td></tr>') +
      '</tbody></table></div></div>' +
      '<div class="mv-note">Movers — Semrush position now vs 7 patrols earlier, biggest moves first. ' +
      'Gap compares our position with the best-ranked competitor for the keyword. ' +
      'Positions are the best-ranking URL on each site, whichever page that is.</div>';

    body.innerHTML = html;
  }

  Sentinel.register({
    id: 'movers',
    title: 'Competitive movers & share of voice',
    sub: 'CTR-weighted visibility for SOP vs each competitor, and this week’s biggest ranking moves.',
    order: 15,
    render: render
  });
})();
