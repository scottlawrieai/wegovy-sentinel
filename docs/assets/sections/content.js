/* Sentinel section — Content intelligence */
(function () {
  'use strict';

  var CSS =
    '<style>' +
    '#sec-content .ci-subhead{font-size:13px;font-weight:700;color:var(--ink);margin:18px 0 8px;letter-spacing:.01em}' +
    '#sec-content .ci-subhead:first-child{margin-top:0}' +
    '#sec-content .ci-chip{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.05em;border-radius:6px;padding:2px 8px;white-space:nowrap}' +
    '#sec-content .ci-pass{color:#2F9E44;background:#E6F4EA;border:1px solid #C3E6CB}' +
    '#sec-content .ci-warn{color:#B45309;background:#FEF3C7;border:1px solid #FDE68A}' +
    '#sec-content .ci-fail{color:#E03131;background:#FBE3DF;border:1px solid #F5C6C0}' +
    '#sec-content .ci-day{color:#E03131;background:#FFF;border:1px solid #F5C6C0;font-size:10px;font-weight:700;border-radius:6px;padding:2px 7px;margin-left:8px}' +
    '#sec-content .ci-row{display:flex;align-items:flex-start;gap:10px;padding:8px 10px;border-bottom:1px solid #EEF2F7}' +
    '#sec-content .ci-row:last-child{border-bottom:0}' +
    '#sec-content .ci-row .ci-name{font-weight:600;color:var(--ink);min-width:170px}' +
    '#sec-content .ci-row .ci-ev{font-size:12px;color:var(--muted);flex:1;min-width:0;overflow-wrap:anywhere}' +
    '#sec-content .ci-muted{font-size:12px;color:var(--muted);margin:4px 0 8px}' +
    '#sec-content .ci-score{font-size:32px;font-weight:800;color:var(--ink);line-height:1.1}' +
    '#sec-content .ci-score small{font-size:14px;font-weight:600;color:var(--faint)}' +
    '#sec-content .ci-tag{display:inline-block;font-size:9px;font-weight:700;letter-spacing:.06em;border-radius:5px;padding:1px 6px;margin-left:6px;vertical-align:1px}' +
    '#sec-content .ci-tag-us{color:#FFF;background:#E8590C}' +
    '#sec-content .ci-tag-comp{color:var(--muted);background:var(--panel);border:1px solid var(--panel-line)}' +
    '#sec-content .ci-tag-brand{color:#FFF;background:#2F9E44}' +
    '#sec-content .ci-topic{display:inline-block;font-size:10.5px;color:var(--muted);background:var(--panel);border:1px solid var(--panel-line);border-radius:6px;padding:1px 7px;margin:1px 3px 1px 0;white-space:nowrap;max-width:150px;overflow:hidden;text-overflow:ellipsis;vertical-align:middle}' +
    '#sec-content .ci-gapchip{display:inline-block;font-size:11px;font-weight:600;color:#E03131;background:#FBE3DF;border:1px solid #F5C6C0;border-radius:6px;padding:2px 9px;margin:2px 6px 2px 0}' +
    '#sec-content ul.ci-list{margin:6px 0 0;padding-left:20px}' +
    '#sec-content ul.ci-list li,#sec-content ol.ci-list li{margin:3px 0;font-size:12.5px}' +
    '#sec-content ol.ci-list{margin:6px 0 0;padding-left:22px}' +
    '#sec-content details.ci-diag summary{cursor:pointer;font-size:13px;font-weight:700;color:var(--ink);padding:6px 0}' +
    '#sec-content .ci-grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:10px}' +
    '#sec-content .ci-panel-title{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:6px}' +
    '#sec-content .ci-tblwrap{overflow-x:auto;max-width:100%}' +
    '#sec-content .ci-tblwrap table.tbl{min-width:1300px}' +
    '</style>';

  function esc(v) { return window.C.esc(v); }
  function fmtInt(v) { return window.C.fmtInt(v); }
  function num(v) { return (v == null || isNaN(v)) ? null : Number(v); }

  function chip(state) {
    if (state === 'pass') return '<span class="ci-chip ci-pass">PASS</span>';
    if (state === 'warn') return '<span class="ci-chip ci-warn">IMPROVE</span>';
    return '<span class="ci-chip ci-fail">FIX</span>';
  }

  function techChip(state) {
    if (state === 'pass') return '<span class="ci-chip ci-pass">PASS</span>';
    if (state === 'warn') return '<span class="ci-chip ci-warn">CHECK</span>';
    return '<span class="ci-chip ci-fail">FIX</span>';
  }

  /* consecutive latest snapshots (from newest back) matching pred */
  function streak(snaps, pred) {
    var n = 0;
    for (var i = snaps.length - 1; i >= 0; i--) {
      if (pred(snaps[i])) n++; else break;
    }
    return n;
  }

  /* ---------- A. structural audit ---------- */

  function sectionA(snaps) {
    var last = snaps.length ? snaps[snaps.length - 1] : null;
    var html = '<div class="ci-subhead">Structural audit — re-checked every patrol</div>';
    if (!last) return html + '<div class="panel"><div class="empty">No patrol data yet.</div></div>';
    var flags = last.flags || {};
    var m = last.m || {};

    var rows = [
      {
        name: 'Wrong-page routing',
        fail: !!flags.wrong,
        pred: function (s) { return !!(s && s.flags && s.flags.wrong); },
        okText: 'Pill page ranks for pill queries',
        badText: 'Google serves a different page for pill queries'
      },
      {
        name: 'Legacy URL ranking',
        fail: !!flags.legacy,
        pred: function (s) { return !!(s && s.flags && s.flags.legacy); },
        okText: 'No retired URL in results',
        badText: 'A retired URL still appears in results'
      },
      {
        name: 'Keyword cannibalisation',
        fail: (num(flags.cann) || 0) > 0,
        pred: function (s) { return !!(s && s.flags && (num(s.flags.cann) || 0) > 0); },
        okText: 'No cannibalised keywords',
        badText: fmtInt(flags.cann) + ' keyword' + ((num(flags.cann) || 0) === 1 ? '' : 's') + ' cannibalised'
      },
      {
        name: 'Backlinks vs target 15',
        fail: (num(m.blD) || 0) < 15,
        pred: function (s) { return !!(s && s.m) && (num(s.m.blD) || 0) < 15; },
        okText: fmtInt(m.blD) + ' referring domains — target met',
        badText: fmtInt(m.blD || 0) + ' of 15 referring domains'
      }
    ];

    html += '<div class="panel">';
    rows.forEach(function (r) {
      var dayChip = '';
      if (r.fail) {
        var n = streak(snaps, r.pred);
        if (n > 0) dayChip = '<span class="ci-day">DAY ' + fmtInt(n) + '</span>';
      }
      html += '<div class="ci-row">' +
        (r.fail ? '<span class="ci-chip ci-fail">FAIL</span>' : '<span class="ci-chip ci-pass">PASS</span>') +
        '<span class="ci-name">' + esc(r.name) + '</span>' +
        '<span class="ci-ev">' + esc(r.fail ? r.badText : r.okText) + dayChip + '</span>' +
        '</div>';
    });
    return html + '</div>';
  }

  /* ---------- B. daily content review ---------- */

  function sectionB(audits) {
    var audit = audits.length ? audits[audits.length - 1] : null;
    var prev = audits.length > 1 ? audits[audits.length - 2] : null;
    var html = '<div class="ci-subhead">Daily content review</div>';
    if (!audit) return html + '<div class="panel"><div class="empty">No content audit yet.</div></div>';
    var al = audit.align || {};
    var score = num(al.score);
    var prevScore = prev && prev.align ? num(prev.align.score) : null;
    var delta = (score != null && prevScore != null) ? score - prevScore : null;
    var deltaHtml = '';
    if (delta != null) {
      if (delta > 0) deltaHtml = '<span class="delta-pos">+' + fmtInt(delta) + ' vs previous audit</span>';
      else if (delta < 0) deltaHtml = '<span class="delta-neg">' + fmtInt(delta) + ' vs previous audit</span>';
      else deltaHtml = 'no change vs previous audit';
    }
    var pagesN = Array.isArray(audit.pages) ? audit.pages.length : 0;
    var fetched = num(audit.fetched);

    html += '<div class="kpis">' +
      '<div class="kpi"><div class="label">Alignment score</div>' +
      '<div class="ci-score">' + (score != null ? fmtInt(score) : '—') + '<small> /100</small></div>' +
      '<div class="context">' + deltaHtml + '</div></div>' +
      '<div class="kpi"><div class="label">Body coverage</div>' +
      '<div class="value">' + (num(al.body_cov) != null ? fmtInt(al.body_cov) + '%' : '—') + '</div>' +
      '<div class="context">of competitor terms in our body copy</div></div>' +
      '<div class="kpi"><div class="label">FAQ coverage</div>' +
      '<div class="value">' + (num(al.faq_cov) != null ? fmtInt(al.faq_cov) + '%' : '—') + '</div>' +
      '<div class="context">of competitor FAQ topics covered</div></div>' +
      '<div class="kpi"><div class="label">Pages analysed</div>' +
      '<div class="value">' + (fetched != null ? fmtInt(fetched) : '—') +
      '<small style="font-size:14px;color:var(--faint);font-weight:600">/' + fmtInt(pagesN) + '</small></div>' +
      '<div class="context">fetched of ' + fmtInt(pagesN) + ' targeted</div></div>' +
      '</div>';

    var checks = Array.isArray(al.checks) ? al.checks : [];
    if (checks.length) {
      html += '<div class="panel" style="margin-top:12px">';
      checks.forEach(function (c) {
        if (!c) return;
        html += '<div class="ci-row">' + chip(c.state) +
          '<span class="ci-name">' + esc(c.name) + '</span>' +
          '<span class="ci-ev">' + esc(c.evidence || '') + '</span></div>';
      });
      html += '</div>';
    }
    return html;
  }

  /* ---------- C. competitive table ---------- */

  var NEW_FIELDS = ['schema', 'authors', 'imgs', 'videos', 'links_int', 'links_ext', 'articles', 'bytes', 'psi'];

  function pagesOf(audit) {
    var pages = Array.isArray(audit.pages) ? audit.pages.slice() : [];
    var usPage = audit.us && (audit.us.page || (audit.us.url ? audit.us : null));
    var hasUs = pages.some(function (p) { return p && p.role === 'us'; });
    if (usPage && !hasUs) pages.push(usPage);
    return pages.filter(function (p) { return !!p; });
  }

  function roleTag(role) {
    if (role === 'us') return '<span class="ci-tag ci-tag-us">US</span>';
    if (role === 'brand') return '<span class="ci-tag ci-tag-brand">BRAND</span>';
    return '<span class="ci-tag ci-tag-comp">COMP</span>';
  }

  function truncate(s, n) {
    s = String(s == null ? '' : s);
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  function sectionC(audits, snaps) {
    var audit = audits.length ? audits[audits.length - 1] : null;
    var html = '<div class="ci-subhead">Top results analysed vs our pill page</div>';
    if (!audit) return html + '<div class="panel"><div class="empty">No content audit yet.</div></div>';
    var pages = pagesOf(audit);
    if (!pages.length) return html + '<div class="panel"><div class="empty">No pages captured in the latest audit.</div></div>';

    pages.sort(function (a, b) {
      var ra = num(a.rank), rb = num(b.rank);
      if (ra == null && rb == null) return 0;
      if (ra == null) return 1;
      if (rb == null) return -1;
      return ra - rb;
    });

    var okPages = pages.filter(function (p) {
      return p.status === 'ok' || p.status === 200;
    });
    var union = {};
    okPages.forEach(function (p) {
      (Array.isArray(p.terms) ? p.terms : []).forEach(function (t) { union[String(t)] = 1; });
    });
    var unionSize = Object.keys(union).length;

    var anyMissing = pages.some(function (p) {
      return NEW_FIELDS.some(function (f) { return p[f] == null; });
    });
    if (anyMissing) {
      html += '<div class="ci-muted">columns showing — populate after the next patrol</div>';
    }

    var snapPsi = null;
    var lastSnap = snaps.length ? snaps[snaps.length - 1] : null;
    if (lastSnap && lastSnap.psi && num(lastSnap.psi.score) != null) snapPsi = num(lastSnap.psi.score);

    html += '<div class="ci-tblwrap"><table class="tbl"><thead><tr>' +
      '<th class="num">Rank</th><th>Page</th><th>Title</th>' +
      '<th class="num">Words</th><th class="num">Length</th><th class="num">KW coverage</th>' +
      '<th>Topics in order</th><th class="num">FAQs</th><th>Schema</th><th>Authors</th>' +
      '<th class="num">Img / Vid</th><th class="num">Links ext/int</th><th class="num">Articles</th>' +
      '<th class="num">Speed</th>' +
      '</tr></thead><tbody>';

    pages.forEach(function (p) {
      var rank = num(p.rank);
      var terms = Array.isArray(p.terms) ? p.terms.length : 0;
      var cov = unionSize > 0 ? Math.round(terms / unionSize * 100) + '%' : '—';
      var title = String(p.title || '');
      var h2 = Array.isArray(p.h2) ? p.h2 : [];
      var topics = h2.slice(0, 4).map(function (h) {
        return '<span class="ci-topic" title="' + esc(h) + '">' + esc(truncate(h, 30)) + '</span>';
      }).join('');
      if (h2.length > 4) topics += '<span class="ci-topic">+' + fmtInt(h2.length - 4) + ' more</span>';
      if (!h2.length) topics = '—';
      var topicsFull = h2.join(' · ');

      var schema = '—';
      if (Array.isArray(p.schema) && p.schema.length) {
        schema = p.schema.slice(0, 3).map(function (t) {
          return '<span class="ci-topic">' + esc(t) + '</span>';
        }).join('');
        if (p.schema.length > 3) schema += '<span class="ci-topic">+' + fmtInt(p.schema.length - 3) + '</span>';
      }
      var authors = (Array.isArray(p.authors) && p.authors.length) ? esc(p.authors.join(', ')) : '—';
      var imgvid = (p.imgs != null || p.videos != null)
        ? (p.imgs != null ? fmtInt(p.imgs) : '—') + ' / ' + (p.videos != null ? fmtInt(p.videos) : '—')
        : '—';
      var links = (p.links_ext != null || p.links_int != null)
        ? (p.links_ext != null ? fmtInt(p.links_ext) : '—') + ' / ' + (p.links_int != null ? fmtInt(p.links_int) : '—')
        : '—';
      var articles = (p.articles && num(p.articles.n) != null) ? fmtInt(p.articles.n) : '—';
      var bytes = num(p.bytes);
      var lenKb = bytes != null ? fmtInt(Math.round(bytes / 1024)) + ' KB' : '—';

      var speedV = (p.psi && num(p.psi.score) != null) ? num(p.psi.score) : null;
      if (speedV == null && p.role === 'us' && snapPsi != null) speedV = snapPsi;
      var speed = speedV != null ? fmtInt(speedV) : '—';

      html += '<tr>' +
        '<td class="num">' + (rank != null ? fmtInt(rank) : '—') + '</td>' +
        '<td style="white-space:nowrap">' + esc(p.domain || '') + roleTag(p.role) + '</td>' +
        '<td title="' + esc(title) + '" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(truncate(title, 60)) + '</td>' +
        '<td class="num">' + (num(p.wc) != null ? fmtInt(p.wc) : '—') + '</td>' +
        '<td class="num">' + lenKb + '</td>' +
        '<td class="num">' + esc(cov) + '</td>' +
        '<td title="' + esc(topicsFull) + '" style="max-width:340px">' + topics + '</td>' +
        '<td class="num">' + (Array.isArray(p.faqs) ? fmtInt(p.faqs.length) : '—') + '</td>' +
        '<td>' + schema + '</td>' +
        '<td>' + authors + '</td>' +
        '<td class="num">' + imgvid + '</td>' +
        '<td class="num">' + links + '</td>' +
        '<td class="num">' + articles + '</td>' +
        '<td class="num">' + speed + '</td>' +
        '</tr>';
    });

    return html + '</tbody></table></div>';
  }

  /* ---------- D. gaps and opportunities ---------- */

  function gapChips(list) {
    return (list || []).map(function (g) {
      if (!g || !g.term) return '';
      var n = Array.isArray(g.competitors) ? g.competitors.length : num(g.competitors);
      return '<span class="ci-gapchip">' + esc(g.term) + (n != null ? ' ×' + fmtInt(n) : '') + '</span>';
    }).join('');
  }

  function sectionD(audits) {
    var audit = audits.length ? audits[audits.length - 1] : null;
    var html = '<div class="ci-subhead">FAQ gaps — questions competitors answer, we don’t</div>';
    if (!audit) return html + '<div class="panel"><div class="empty">No content audit yet.</div></div>';
    var al = audit.align || {};

    var faqGaps = Array.isArray(al.faq_gaps) ? al.faq_gaps : [];
    if (faqGaps.length) {
      html += '<ul class="ci-list">' + faqGaps.map(function (q) {
        return '<li>' + esc(q) + '</li>';
      }).join('') + '</ul>';
    } else {
      html += '<div class="ci-muted">No FAQ gaps detected — we cover every competitor question.</div>';
    }

    var eg = Array.isArray(al.entity_gaps) ? al.entity_gaps : [];
    var tg = Array.isArray(al.term_gaps) ? al.term_gaps : [];
    if (eg.length || tg.length) {
      html += '<div class="ci-muted" style="margin-top:10px">Entity and term gaps (competitors covering, count):</div>' +
        '<div>' + gapChips(eg) + gapChips(tg) + '</div>';
    }

    var opps = Array.isArray(audit.opps) ? audit.opps : [];
    if (opps.length) {
      html += '<div class="ci-subhead">Prioritised opportunities</div>' +
        '<ol class="ci-list">' + opps.map(function (o) {
          return '<li>' + esc(o) + '</li>';
        }).join('') + '</ol>';
    }
    return html;
  }

  /* ---------- E. diagnostics ---------- */

  function psiColor(v) {
    if (v >= 90) return '#2F9E44';
    if (v >= 50) return '#B45309';
    return '#E03131';
  }

  function sectionE(snaps) {
    // The freshest snapshot can miss a diagnostic block (a degraded patrol);
    // fall back to the most recent snapshot that carries each one.
    function lastWith(key) {
      for (var i = snaps.length - 1; i >= 0; i--) {
        var v = snaps[i] && snaps[i][key];
        if (v && (typeof v !== 'object' || Object.keys(v).length)) return v;
      }
      return null;
    }
    var last = snaps.length ? snaps[snaps.length - 1] : null;
    if (last) {
      last = {
        tech: last.tech || lastWith('tech'),
        psi: last.psi || lastWith('psi'),
        links: last.links || lastWith('links'),
        gsci: last.gsci || lastWith('gsci')
      };
    }
    var html = '<details class="ci-diag" style="margin-top:16px">' +
      '<summary>Diagnostics — tech health, page speed, links, Search Console insights</summary>';
    if (!last) return html + '<div class="ci-muted">No patrol data yet.</div></details>';

    var inner = '';

    /* tech checks */
    var tech = last.tech || null;
    inner += '<div class="ci-panel-title" style="margin-top:10px">Tech health' +
      (tech && num(tech.score) != null ? ' — ' + fmtInt(tech.score) + (num(tech.of) != null ? ' / ' + fmtInt(tech.of) : '') : '') +
      '</div>';
    if (tech && Array.isArray(tech.checks) && tech.checks.length) {
      inner += '<div class="panel">';
      tech.checks.forEach(function (c) {
        if (!c) return;
        inner += '<div class="ci-row">' + techChip(c.state) +
          '<span class="ci-name">' + esc(c.name) + '</span>' +
          '<span class="ci-ev">' + esc(c.evidence || '') + '</span></div>';
      });
      inner += '</div>';
    } else {
      inner += '<div class="ci-muted">Not collected yet — populates after the next patrol.</div>';
    }

    /* PSI mini-card */
    var psi = last.psi || null;
    inner += '<div class="ci-panel-title" style="margin-top:14px">Page speed (PSI)</div>';
    if (psi && num(psi.score) != null) {
      var pv = num(psi.score);
      inner += '<div class="kpis"><div class="kpi">' +
        '<div class="label">Performance' + (psi.strategy ? ' — ' + esc(psi.strategy) : '') + '</div>' +
        '<div class="value" style="color:' + psiColor(pv) + '">' + fmtInt(pv) + '</div>' +
        '<div class="context">LCP ' + esc(psi.lcp != null ? psi.lcp : '—') +
        ' · CLS ' + esc(psi.cls != null ? psi.cls : '—') +
        ' · TBT ' + esc(psi.tbt != null ? psi.tbt : '—') +
        (psi.as_of ? ' · as of ' + esc(psi.as_of) : '') + '</div>' +
        '</div></div>';
    } else {
      inner += '<div class="ci-muted">Not collected yet — populates after the next patrol.</div>';
    }

    /* link prospects */
    var links = last.links || null;
    inner += '<div class="ci-panel-title" style="margin-top:14px">Link prospects' +
      (links && num(links.ours) != null ? ' — we have ' + fmtInt(links.ours) + ' referring domains' : '') + '</div>';
    if (links && Array.isArray(links.prospects) && links.prospects.length) {
      inner += '<div class="tbl-wrap"><table class="tbl"><thead><tr>' +
        '<th>Domain</th><th class="num">Competitors linked</th><th>Who</th>' +
        '</tr></thead><tbody>';
      links.prospects.forEach(function (p) {
        if (!p) return;
        inner += '<tr><td>' + esc(p.d || '') + '</td>' +
          '<td class="num">' + (num(p.n) != null ? fmtInt(p.n) : '—') + '</td>' +
          '<td>' + esc(Array.isArray(p.who) ? p.who.join(', ') : (p.who || '')) + '</td></tr>';
      });
      inner += '</tbody></table></div>';
    } else {
      inner += '<div class="ci-muted">Not collected yet — populates after the next patrol.</div>';
    }

    /* GSC insights */
    var gsci = last.gsci || null;
    inner += '<div class="ci-panel-title" style="margin-top:14px">Search Console insights' +
      (gsci && gsci.as_of ? ' — as of ' + esc(gsci.as_of) : '') + '</div>';
    if (gsci && ((Array.isArray(gsci.actions) && gsci.actions.length) || (Array.isArray(gsci.splits) && gsci.splits.length))) {
      if (Array.isArray(gsci.actions) && gsci.actions.length) {
        inner += '<ol class="ci-list">' + gsci.actions.map(function (a) {
          return '<li>' + esc(a) + '</li>';
        }).join('') + '</ol>';
      }
      if (Array.isArray(gsci.splits) && gsci.splits.length) {
        inner += '<div class="tbl-wrap" style="margin-top:8px"><table class="tbl"><thead><tr>' +
          '<th>Query</th><th class="num">Impr</th><th class="num">URLs</th><th class="num">Pill share %</th>' +
          '</tr></thead><tbody>';
        gsci.splits.forEach(function (s) {
          if (!s) return;
          var share = num(s.pill_pct);
          var shareColor = share == null ? 'var(--muted)' : (share >= 80 ? '#2F9E44' : (share >= 50 ? '#B45309' : '#E03131'));
          inner += '<tr><td>' + esc(s.q || '') + '</td>' +
            '<td class="num">' + (num(s.impr) != null ? fmtInt(s.impr) : '—') + '</td>' +
            '<td class="num">' + (num(s.n) != null ? fmtInt(s.n) : (Array.isArray(s.pages) ? fmtInt(s.pages.length) : '—')) + '</td>' +
            '<td class="num" style="color:' + shareColor + ';font-weight:600">' +
            (share != null ? fmtInt(share) + '%' : '—') + '</td></tr>';
        });
        inner += '</tbody></table></div>';
      }
    } else {
      inner += '<div class="ci-muted">Not collected yet — populates after the next patrol.</div>';
    }

    return html + inner + '</details>';
  }

  /* ---------- register ---------- */

  window.Sentinel.register({
    id: 'content',
    title: 'Content intelligence',
    sub: 'Structural checks, daily content alignment audit and competitive page analysis for the pill cluster.',
    order: 30,
    render: function (body, S) {
      var snaps = Array.isArray(S.data.snaps) ? S.data.snaps : [];
      var audits = Array.isArray(S.data.content) ? S.data.content : [];
      body.innerHTML = CSS +
        sectionA(snaps) +
        sectionB(audits) +
        sectionC(audits, snaps) +
        sectionD(audits) +
        sectionE(snaps);
    }
  });
})();
