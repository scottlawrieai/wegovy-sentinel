/* Sentinel chart primitives — global window.C */
(function () {
  'use strict';

  var C = {};

  /* ---------- utils ---------- */

  C.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  };

  C.fmtInt = function (n) {
    if (n == null || isNaN(n)) return '—';
    var neg = n < 0 ? '-' : '';
    var s = String(Math.round(Math.abs(n)));
    return neg + s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  };

  C.inRange = function (points, state) {
    if (!Array.isArray(points)) return [];
    return points.filter(function (p) {
      return p && p.d >= state.from && p.d <= state.to;
    });
  };

  /* ---------- heat ---------- */

  function lerp(a, b, t) { return a + (b - a) * t; }
  function mix(c1, c2, t) {
    return 'rgb(' + Math.round(lerp(c1[0], c2[0], t)) + ',' +
      Math.round(lerp(c1[1], c2[1], t)) + ',' + Math.round(lerp(c1[2], c2[2], t)) + ')';
  }

  // C.heat(v, min, max, invert)
  // default (volume): low -> #FBF3DB, high -> near-white
  // invert semantics (avg position): low(good) -> green #DCEFE2, high(bad) -> red #FBE3DF
  C.heat = function (v, min, max, invert) {
    if (v == null || isNaN(v)) return 'transparent';
    var t = (max - min) === 0 ? 0 : (v - min) / (max - min);
    t = Math.max(0, Math.min(1, t));
    if (invert) {
      // good (low) green -> bad (high) red, through near-white in the middle
      var green = [220, 239, 226]; // #DCEFE2
      var red = [251, 227, 223];   // #FBE3DF
      var white = [252, 252, 253];
      return t < 0.5 ? mix(green, white, t * 2) : mix(white, red, (t - 0.5) * 2);
    }
    var lowc = [251, 243, 219];   // #FBF3DB
    var hic = [253, 252, 249];    // near-white
    return mix(lowc, hic, t);
  };

  /* ---------- pills ---------- */

  C.pills = function (groupId, options, activeValue) {
    var html = '<div class="pills" data-pill-group="' + C.esc(groupId) + '">';
    (options || []).forEach(function (o) {
      var active = String(o.value) === String(activeValue);
      html += '<button type="button" class="pill' + (active ? ' active' : '') +
        '" data-value="' + C.esc(o.value) + '">' + C.esc(o.label) + '</button>';
    });
    return html + '</div>';
  };

  /* ---------- dates / weeks ---------- */

  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function parseD(d) { return new Date(d + 'T00:00:00Z'); }
  function isoD(dt) { return dt.toISOString().slice(0, 10); }
  function fmtDM(dt) {
    return String(dt.getUTCDate()).padStart(2, '0') + ' ' + MONTHS[dt.getUTCMonth()];
  }

  // Monday of the week containing d, as ISO string
  C.weekKey = function (d) {
    var dt = parseD(d);
    var dow = (dt.getUTCDay() + 6) % 7; // Mon=0
    dt.setUTCDate(dt.getUTCDate() - dow);
    return isoD(dt);
  };

  // groups daily points into Mon-Sun weeks
  C.groupWeeks = function (points) {
    var map = {}, order = [];
    (points || []).forEach(function (p) {
      if (!p || !p.d) return;
      var wk = C.weekKey(p.d);
      if (!map[wk]) { map[wk] = []; order.push(wk); }
      map[wk].push(p);
    });
    order.sort();
    return order.map(function (wk) {
      var from = parseD(wk);
      var to = new Date(from.getTime());
      to.setUTCDate(to.getUTCDate() + 6);
      return {
        key: fmtDM(from) + '–' + fmtDM(to) + ' ' + to.getUTCFullYear(),
        from: isoD(from),
        to: isoD(to),
        rows: map[wk]
      };
    });
  };

  /* ---------- change letters ---------- */

  // changelog: [{date, changes:[...]}], availableDates: Set or array of 'YYYY-MM-DD'
  C.letters = function (changelog, availableDates) {
    var avail = availableDates instanceof Set ? availableDates : new Set(availableDates || []);
    var dates = (changelog || [])
      .map(function (e) { return e && e.date; })
      .filter(function (d) { return d && avail.has(d); });
    dates = Array.from(new Set(dates)).sort();
    var out = {};
    dates.forEach(function (d, i) {
      out[d] = String.fromCharCode(65 + (i % 26));
    });
    return out;
  };

  /* ---------- line chart ---------- */

  function fmtDateLabel(d) {
    var dt = parseD(d);
    return String(dt.getUTCDate()).padStart(2, '0') + ' ' + MONTHS[dt.getUTCMonth()];
  }

  C.lineChart = function (opts) {
    opts = opts || {};
    var series = (opts.series || []).filter(function (s) { return s && Array.isArray(s.points); });
    var height = opts.height || 260;
    var W = 1000, H = height;
    var padL = 46, padR = 14, padT = 16, padB = 26;
    var yFmt = opts.yFmt || function (v) { return C.fmtInt(v); };
    var markers = opts.markers || [];

    // collect x domain (dates) and y domain
    var dateSet = new Set();
    var vmin = Infinity, vmax = -Infinity;
    series.forEach(function (s) {
      s.points.forEach(function (p) {
        if (!p || !p.d) return;
        dateSet.add(p.d);
        if (p.v != null && !isNaN(p.v)) {
          if (p.v < vmin) vmin = p.v;
          if (p.v > vmax) vmax = p.v;
        }
      });
    });
    markers.forEach(function (m) { if (m && m.d) dateSet.add(m.d); });

    var dates = Array.from(dateSet).sort();
    var empty = dates.length === 0 || vmin === Infinity;
    if (empty) {
      return '<div class="chart"><div class="empty">No data in this range.</div>' +
        legendHtml(series, opts.showLegend) + '</div>';
    }
    if (vmin === vmax) { vmin -= 1; vmax += 1; }
    // slight headroom
    var span = vmax - vmin;
    vmin -= span * 0.06; vmax += span * 0.06;

    var t0 = parseD(dates[0]).getTime();
    var t1 = parseD(dates[dates.length - 1]).getTime();
    if (t1 === t0) t1 = t0 + 1;

    function X(d) {
      return padL + (parseD(d).getTime() - t0) / (t1 - t0) * (W - padL - padR);
    }
    function Y(v) {
      var t = (v - vmin) / (vmax - vmin);
      if (opts.invertY) t = 1 - t; // low value at TOP
      return padT + (1 - t) * (H - padT - padB);
    }

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" xmlns="http://www.w3.org/2000/svg" role="img">';

    // gridlines + y labels (4 lines)
    for (var i = 0; i < 4; i++) {
      var gv = vmin + (vmax - vmin) * (i / 3);
      var gy = Y(gv);
      svg += '<line x1="' + padL + '" y1="' + gy.toFixed(1) + '" x2="' + (W - padR) +
        '" y2="' + gy.toFixed(1) + '" stroke="#E6ECF7" stroke-width="1"/>';
      svg += '<text x="' + (padL - 8) + '" y="' + (gy + 3.5).toFixed(1) +
        '" text-anchor="end" font-size="11" fill="#94A3B8">' + C.esc(yFmt(gv)) + '</text>';
    }

    // x labels: first / middle / last date
    var xlab = [dates[0]];
    if (dates.length > 2) xlab.push(dates[Math.floor(dates.length / 2)]);
    if (dates.length > 1) xlab.push(dates[dates.length - 1]);
    xlab.forEach(function (d, idx) {
      var anchor = idx === 0 ? 'start' : (idx === xlab.length - 1 ? 'end' : 'middle');
      svg += '<text x="' + X(d).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="' + anchor +
        '" font-size="11" fill="#94A3B8">' + C.esc(fmtDateLabel(d)) + '</text>';
    });

    // marker vertical dashed lines (behind polylines)
    markers.forEach(function (m) {
      if (!m || !m.d) return;
      var mx = X(m.d);
      svg += '<line x1="' + mx.toFixed(1) + '" y1="' + padT + '" x2="' + mx.toFixed(1) +
        '" y2="' + (H - padB) + '" stroke="' + C.esc(m.color || '#5B6B83') +
        '" stroke-width="1" stroke-dasharray="4 3" opacity="0.7"/>';
    });

    // polylines — a null v breaks the line
    series.forEach(function (s) {
      var runs = [], cur = [];
      s.points.slice().sort(function (a, b) { return a.d < b.d ? -1 : 1; }).forEach(function (p) {
        if (!p || p.v == null || isNaN(p.v)) {
          if (cur.length) runs.push(cur);
          cur = [];
        } else {
          cur.push(p);
        }
      });
      if (cur.length) runs.push(cur);
      runs.forEach(function (run) {
        if (run.length === 1) {
          svg += '<circle cx="' + X(run[0].d).toFixed(1) + '" cy="' + Y(run[0].v).toFixed(1) +
            '" r="3" fill="' + C.esc(s.color || '#1C7ED6') + '"/>';
        } else {
          var pts = run.map(function (p) {
            return X(p.d).toFixed(1) + ',' + Y(p.v).toFixed(1);
          }).join(' ');
          svg += '<polyline points="' + pts + '" fill="none" stroke="' +
            C.esc(s.color || '#1C7ED6') + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
        }
      });
    });

    // marker letter circles — chronological, stack upward when closer than 24px
    var ms = markers.filter(function (m) { return m && m.d; })
      .slice().sort(function (a, b) { return a.d < b.d ? -1 : 1; });
    var placed = []; // {x, y}
    ms.forEach(function (m) {
      var mx = X(m.d);
      var my = padT + 10;
      var collide = true;
      while (collide) {
        collide = placed.some(function (p) {
          return Math.abs(p.x - mx) < 24 && Math.abs(p.y - my) < 20;
        });
        if (collide) my -= 20;
      }
      placed.push({ x: mx, y: my });
      var col = m.color || '#1D4ED8';
      svg += '<circle cx="' + mx.toFixed(1) + '" cy="' + my.toFixed(1) + '" r="9" fill="' +
        C.esc(col) + '"/>';
      svg += '<text x="' + mx.toFixed(1) + '" y="' + (my + 3.5).toFixed(1) +
        '" text-anchor="middle" font-size="10" font-weight="700" fill="#FFFFFF">' +
        C.esc(m.letter || '') + '</text>';
    });

    svg += '</svg>';
    return '<div class="chart">' + svg + legendHtml(series, opts.showLegend) + '</div>';
  };

  function legendHtml(series, show) {
    if (!show || !series.length) return '';
    var html = '<div class="legend">';
    series.forEach(function (s) {
      html += '<span class="item"><span class="dot" style="background:' +
        C.esc(s.color || '#1C7ED6') + '"></span>' + C.esc(s.label || '') + '</span>';
    });
    return html + '</div>';
  }

  window.C = C;
})();
