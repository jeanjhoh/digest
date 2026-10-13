/* Weekly Research Digest — progressive enhancement. No dependencies. */
(function () {
  'use strict';
  var doc = document, html = doc.documentElement;
  html.classList.add('js');
  var PAGE = doc.body.getAttribute('data-page');
  var $ = function (s, r) { return (r || doc).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var store = { get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };
  var REL = (function () { var s = $('script[src*="app.js"]'); if (!s) return ''; var m = s.getAttribute('src').match(/^(.*?)app\.js/); return m ? m[1] : ''; })();

  // ---------- toast ----------
  var toastTimer;
  function toast(msg) { var t = $('#toast'); if (!t) return; t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.hidden = true; }, 1600); }
  function copyText(text, msg) {
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(function () { toast(msg || 'Copied'); }, function () { toast('Copy failed'); }); }
    else { var ta = doc.createElement('textarea'); ta.value = text; doc.body.appendChild(ta); ta.select(); try { doc.execCommand('copy'); toast(msg || 'Copied'); } catch (e) { toast('Copy failed'); } doc.body.removeChild(ta); }
  }

  // ---------- sidebar menu (mobile) ----------
  (function () {
    var btn = $('.sidebar-toggle'), panel = $('.sidebar-collapsible');
    if (!btn || !panel) return;
    btn.addEventListener('click', function () {
      var open = panel.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', String(open));
      var icon = btn.querySelector('i'); if (icon) icon.className = open ? 'bi bi-chevron-up' : 'bi bi-chevron-down';
    });
  })();

  // ---------- panels ----------
  var openPanel = null, lastFocus = null;
  function showPanel(name) {
    var p = $('#panel-' + name); if (!p) return;
    closePanels();
    lastFocus = doc.activeElement; p.hidden = false; openPanel = p;
    var f = p.querySelector('input, button, a'); if (f) f.focus();
  }
  function closePanels() {
    if (!openPanel) return;
    openPanel.hidden = true; openPanel = null;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  $$('[data-panel]').forEach(function (a) { a.addEventListener('click', function (e) { e.preventDefault(); showPanel(a.getAttribute('data-panel')); }); });
  $$('[data-close]').forEach(function (b) { b.addEventListener('click', closePanels); });
  $$('.overlay').forEach(function (o) { o.addEventListener('click', function (e) { if (e.target === o) closePanels(); }); });

  // ---------- notes toggle / expand all ----------
  if (store.get('digest.notes') === 'hidden') html.classList.add('notes-hidden');
  var notesBtn = $('[data-toggle-notes]');
  function syncNotesBtn() { if (notesBtn) notesBtn.textContent = html.classList.contains('notes-hidden') ? 'Show AI summaries' : 'Hide AI summaries'; }
  syncNotesBtn();
  if (notesBtn) notesBtn.addEventListener('click', function () { html.classList.toggle('notes-hidden'); store.set('digest.notes', html.classList.contains('notes-hidden') ? 'hidden' : 'shown'); syncNotesBtn(); });
  var expandBtn = $('[data-expand-all]'), expanded = false;
  if (expandBtn) expandBtn.addEventListener('click', function () { expanded = !expanded; $$('details.abstract').forEach(function (d) { d.open = expanded; }); expandBtn.textContent = expanded ? 'Collapse abstracts' : 'Expand abstracts'; });

  // ---------- cite / copy (event delegation) ----------
  doc.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target.closest('button') : null; if (!t) return;
    if (t.hasAttribute('data-copy')) copyText(t.getAttribute('data-copy'), t.getAttribute('data-copied'));
  });

  // ---------- details page ----------
  if (PAGE === 'details') {
    var sf = $('#source-filter'), eo = $('#errors-only');
    function applySourceFilter() {
      var q = (sf && sf.value || '').toLowerCase().trim(), onlyErr = eo && eo.checked;
      $$('.source').forEach(function (s) { var ok = (!q || s.getAttribute('data-name').indexOf(q) >= 0) && (!onlyErr || s.getAttribute('data-status') === 'error'); s.hidden = !ok; });
    }
    if (sf) sf.addEventListener('input', applySourceFilter);
    if (eo) eo.addEventListener('change', applySourceFilter);
  }

  // ======================= issue pages =======================
  var ISSUE = null;
  var dataEl = $('#issue-data');
  if (dataEl) { try { ISSUE = JSON.parse(dataEl.textContent); } catch (e) { ISSUE = null; } }
  var entriesEl = $('#entries'), resultsEl = $('#results'), emptyEl = $('#empty');
  var state = { sets: [], cats: [], srcs: [], picks: false, q: '', author: '', title: '', abstract: '', issue: '', journal: '', scope: 'issue' };
  var SEARCH_FIELDS = ['q', 'author', 'title', 'abstract', 'issue', 'journal'];
  var searchIndex = null;

  // ---------- boolean search ----------
  function tokenize(q) {
    var out = [], i = 0, s = q;
    while (i < s.length) {
      var c = s[i];
      if (/\s/.test(c)) { i++; continue; }
      if (c === '(' || c === ')') { out.push({ t: c }); i++; continue; }
      if (c === '"') { var j = s.indexOf('"', i + 1); if (j < 0) j = s.length; out.push({ t: 'term', v: s.slice(i + 1, j).toLowerCase() }); i = j + 1; continue; }
      var m = /^[^\s()"]+/.exec(s.slice(i)); var w = m[0]; i += w.length;
      var u = w.toUpperCase();
      if (u === 'AND' || u === 'OR' || u === 'NOT') out.push({ t: u }); else out.push({ t: 'term', v: w.toLowerCase() });
    }
    return out;
  }
  function parse(tokens) {
    var pos = 0;
    function peek() { return tokens[pos]; }
    function next() { return tokens[pos++]; }
    function parseOr() { var l = parseAnd(); while (peek() && peek().t === 'OR') { next(); var r = parseAnd(); l = { op: 'or', l: l, r: r }; } return l; }
    function parseAnd() {
      var l = parseNot();
      while (peek() && (peek().t === 'AND' || peek().t === 'NOT' || peek().t === 'term' || peek().t === '(')) {
        if (peek().t === 'AND') next();
        var r = parseNot(); l = { op: 'and', l: l, r: r };
      }
      return l;
    }
    function parseNot() { if (peek() && peek().t === 'NOT') { next(); return { op: 'not', x: parseNot() }; } return parsePrimary(); }
    function parsePrimary() {
      var tk = next();
      if (!tk) throw new Error('Unexpected end of query');
      if (tk.t === '(') { var e = parseOr(); if (!peek() || peek().t !== ')') throw new Error('Missing closing parenthesis'); next(); return e; }
      if (tk.t === 'term') { if (!tk.v) throw new Error('Empty quoted phrase'); return { op: 'term', v: tk.v }; }
      throw new Error('Unexpected "' + (tk.v || tk.t) + '"');
    }
    if (!tokens.length) return null;
    var ast = parseOr();
    if (pos < tokens.length) throw new Error('Unexpected "' + (tokens[pos].v || tokens[pos].t) + '"');
    return ast;
  }
  function evaluate(ast, text) {
    if (!ast) return true;
    switch (ast.op) {
      case 'term': return text.indexOf(ast.v) >= 0;
      case 'not': return !evaluate(ast.x, text);
      case 'and': return evaluate(ast.l, text) && evaluate(ast.r, text);
      case 'or': return evaluate(ast.l, text) || evaluate(ast.r, text);
    }
    return true;
  }
  function compile(q) { q = (q || '').trim(); if (!q) return null; return parse(tokenize(q)); }
  function docOf(a) {
    var all = [a.title, a.authors.join(' '), a.venue, a.abstract || '', a.note || '', (a.set_labels || []).join(' '), a.status_label || '', 'issue ' + a.issue_number].join(' \n ').toLowerCase();
    return { all: all, author: a.authors.join(' ').toLowerCase(), title: (a.title || '').toLowerCase(), abstract: (a.abstract || '').toLowerCase(), journal: (a.venue || '').toLowerCase(), issue: String(a.issue_number) };
  }
  function buildPredicate(st) {
    var asts = {};
    SEARCH_FIELDS.forEach(function (f) { if (f !== 'issue') asts[f] = compile(st[f]); });
    var issueNum = (st.issue || '').replace(/[^0-9]/g, '');
    return function (a) {
      var d = docOf(a);
      if (asts.q && !evaluate(asts.q, d.all)) return false;
      if (asts.author && !evaluate(asts.author, d.author)) return false;
      if (asts.title && !evaluate(asts.title, d.title)) return false;
      if (asts.abstract && !evaluate(asts.abstract, d.abstract)) return false;
      if (asts.journal && !evaluate(asts.journal, d.journal)) return false;
      if (issueNum && String(parseInt(issueNum, 10)) !== d.issue) return false;
      return true;
    };
  }
  function matchesFilters(a) {
    if (state.sets.length && !state.sets.some(function (s) { return a.sets.indexOf(s) >= 0; })) return false;
    if (state.cats.length && state.cats.indexOf(a.source_category) < 0) return false;
    if (state.srcs.length && state.srcs.indexOf(a.source_slug) < 0) return false;
    if (state.picks && !a.recommended) return false;
    return true;
  }
  function hasSearch() { return SEARCH_FIELDS.some(function (f) { return state[f]; }); }
  function filterCount() { return state.sets.length + state.cats.length + state.srcs.length + (state.picks ? 1 : 0); }

  // ---------- rendering (JS twin of _entry.html) ----------
  function entryHTML(a, ord) {
    var tags = a.sets.map(function (s, i) { return '<span class="tag tag-' + esc(s) + '">' + esc((a.set_labels || [])[i] || s) + '</span>'; }).join('');
    var abs = a.abstract ? '<details class="abstract"><summary><span class="abstract-label">Abstract</span><span class="abstract-teaser">' + esc(a.abstract) + '</span></summary><div class="abstract-full">' + esc(a.abstract) + '</div>' + (a.abstract_source ? '<p class="abstract-src">Abstract via ' + esc(a.abstract_source) + '</p>' : '') + '</details>' : '<p class="abstract abstract-none">No abstract available.</p>';
    var links = [];
    if (a.doi) links.push('<a href="https://doi.org/' + esc(a.doi) + '" target="_blank" rel="noopener">DOI</a>');
    links.push('<a href="' + REL + 'issues/' + String(a.issue_number).padStart(3, '0') + '.html#k-' + esc(a.slug) + '">Issue ' + esc(a.issue_number) + '</a>');
    if (a.doi) links.push('<button type="button" class="linkish" data-copy="' + esc(a.doi) + '" data-copied="DOI copied">Copy DOI</button>');
    return '<article class="entry' + (a.recommended ? ' is-pick' : '') + '" id="r-' + esc(a.slug) + '" data-key="' + esc(a.key) + '" data-slug="' + esc(a.slug) + '" data-sets="' + esc(a.sets.join(' ')) + '" data-cat="' + esc(a.source_category) + '" data-src="' + esc(a.source_slug) + '" data-issue="' + esc(a.issue_number) + '">' +
      '<span class="Z3988" title="' + esc(a.coins) + '"></span>' +
      '<div class="entry-ord">' + String(ord).padStart(3, '0') + '</div><div class="entry-body">' +
      '<h4 class="entry-title"><a href="' + esc(a.link) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></h4>' +
      '<p class="entry-authors">' + esc(a.authors.join(', ')) + '</p>' +
      '<p class="entry-meta"><a class="venue" href="' + REL + 'details.html#src-' + esc(a.source_slug) + '">' + esc(a.venue) + '</a>' + (a.publication_status !== 'published' ? '<span class="sep">·</span><span class="status">' + esc(a.status_label) + '</span>' : '') + (a.published_at ? '<span class="sep">·</span><span class="date">' + esc(a.published_at) + '</span>' : '') + tags + '</p>' +
      (a.note ? '<p class="entry-note">' + esc(a.note) + '</p>' : '') + abs +
      '<p class="entry-links">' + links.join('<span class="sep">·</span>') + '</p>' +
      '<div class="cite-box" hidden><p class="cite-plain">' + esc(a.plain || '') + '</p><pre class="cite-bibtex">' + esc(a.bibtex || '') + '</pre><p class="cite-actions"><button type="button" class="linkish" data-copy-sel=".cite-plain" data-copied="Citation copied">Copy citation</button><span class="sep">·</span><button type="button" class="linkish" data-copy-sel=".cite-bibtex" data-copied="BibTeX copied">Copy BibTeX</button></p></div>' +
      '</div></article>';
  }
  function notifyZotero() { try { doc.dispatchEvent(new Event('ZoteroItemUpdated', { bubbles: true, cancelable: true })); } catch (e) {} }

  // ---------- apply view ----------
  function applyView() {
    if (!entriesEl || !ISSUE) return;
    var pred = null, err = $('.search-error');
    try { pred = hasSearch() ? buildPredicate(state) : null; if (err) { err.hidden = true; err.textContent = ''; } }
    catch (e) { if (err) { err.hidden = false; err.textContent = e.message; } return; }
    if (state.scope === 'all' && hasSearch()) {
      ensureIndex().then(function (all) {
        var hits = all.filter(function (a) { return matchesFilters(a) && pred(a); });
        renderResults(hits);
      });
      return;
    }
    entriesEl.hidden = false; resultsEl.hidden = true; resultsEl.innerHTML = '';
    var byKey = {}; ISSUE.forEach(function (a) { byKey[a.key] = a; });
    var visible = 0;
    $$('.entry', entriesEl).forEach(function (el) {
      var a = byKey[el.getAttribute('data-key')];
      var ok = a ? (matchesFilters(a) && (!pred || pred(a))) : true;
      el.hidden = !ok; if (ok) visible++;
    });
    $$('section.src', entriesEl).forEach(function (s) { s.hidden = !$$('.entry', s).some(function (e) { return !e.hidden; }); });
    $$('section.cat', entriesEl).forEach(function (s) { s.hidden = !$$('section.src', s).some(function (e) { return !e.hidden; }); });
    if (emptyEl) emptyEl.hidden = visible > 0;
    var vc = $('#visible-count'); if (vc) vc.textContent = visible;
    syncBadges(); writeURL();
  }
  function renderResults(hits) {
    entriesEl.hidden = true; resultsEl.hidden = false;
    var byIssue = {}; hits.forEach(function (a) { (byIssue[a.issue_number] = byIssue[a.issue_number] || []).push(a); });
    var nums = Object.keys(byIssue).map(Number).sort(function (a, b) { return b - a; });
    var ord = 0;
    resultsEl.innerHTML = nums.map(function (n) {
      return '<section class="results-issue"><h2>Issue No. ' + String(n).padStart(3, '0') + ' <span class="count">' + byIssue[n].length + '</span></h2>' + byIssue[n].map(function (a) { return entryHTML(a, ++ord); }).join('') + '</section>';
    }).join('');
    if (emptyEl) emptyEl.hidden = hits.length > 0;
    var vc = $('#visible-count'); if (vc) vc.textContent = hits.length;
    syncBadges(); writeURL(); notifyZotero();
  }
  function ensureIndex() {
    if (searchIndex) return Promise.resolve(searchIndex);
    toast('Loading archive…');
    return fetch(REL + 'data/search.json').then(function (r) { return r.json(); }).then(function (d) {
      if (d.shards && d.shards.length) {
        return Promise.all(d.shards.map(function (s) { return fetch(REL + 'data/' + s).then(function (r) { return r.json(); }); })).then(function (parts) {
          searchIndex = [].concat.apply([], parts.map(function (p) { return p.articles; })); return searchIndex;
        });
      }
      searchIndex = d.articles; return searchIndex;
    }).catch(function () { toast('Could not load archive'); return []; });
  }
  function syncBadges() {
    var fb = $('[data-badge="filter"]'), sb = $('[data-badge="search"]');
    var fc = filterCount(); if (fb) { fb.hidden = !fc; fb.textContent = fc; }
    var sc = SEARCH_FIELDS.filter(function (f) { return state[f]; }).length; if (sb) { sb.hidden = !sc; sb.textContent = sc; }
    $$('[data-chip-set]').forEach(function (c) { c.classList.toggle('is-on', state.sets.indexOf(c.getAttribute('data-chip-set')) >= 0); });
    var ff = $('#filter-form');
    if (ff) {
      $$('input[name="sets"]', ff).forEach(function (i) { i.checked = state.sets.indexOf(i.value) >= 0; });
      $$('input[name="cats"]', ff).forEach(function (i) { i.checked = state.cats.indexOf(i.value) >= 0; });
      $$('input[name="srcs"]', ff).forEach(function (i) { i.checked = state.srcs.indexOf(i.value) >= 0; });
      var p = $('input[name="picks"]', ff); if (p) p.checked = state.picks;
    }
    var sfm = $('#search-form');
    if (sfm) { SEARCH_FIELDS.forEach(function (f) { var i = sfm.elements[f]; if (i) i.value = state[f] || ''; }); var r = sfm.querySelector('input[name="scope"][value="' + state.scope + '"]'); if (r) r.checked = true; }
  }
  function countsFromIssue() {
    if (!ISSUE) return;
    var sets = {}, cats = {}, srcs = {};
    ISSUE.forEach(function (a) { a.sets.forEach(function (s) { sets[s] = (sets[s] || 0) + 1; }); cats[a.source_category] = (cats[a.source_category] || 0) + 1; srcs[a.source_slug] = (srcs[a.source_slug] || 0) + 1; });
    $$('[data-count-set]').forEach(function (e) { e.textContent = sets[e.getAttribute('data-count-set')] || 0; });
    $$('[data-count-cat]').forEach(function (e) { e.textContent = cats[e.getAttribute('data-count-cat')] || 0; });
    $$('[data-count-src]').forEach(function (e) { var n = srcs[e.getAttribute('data-count-src')] || 0; e.textContent = n; e.closest('label').hidden = !n; });
  }

  // ---------- URL state ----------
  function readURL() {
    var p = new URLSearchParams(location.search);
    state.sets = (p.get('sets') || '').split(',').filter(Boolean);
    state.cats = (p.get('cats') || '').split(',').filter(Boolean);
    state.srcs = (p.get('src') || '').split(',').filter(Boolean);
    state.picks = p.get('picks') === '1';
    SEARCH_FIELDS.forEach(function (f) { state[f] = p.get(f) || ''; });
    state.scope = p.get('scope') === 'all' ? 'all' : 'issue';
    if (!location.search) { try { var saved = JSON.parse(store.get('digest.filters') || 'null'); if (saved) { state.sets = saved.sets || []; state.cats = saved.cats || []; state.srcs = saved.srcs || []; state.picks = !!saved.picks; } } catch (e) {} }
  }
  function writeURL() {
    var p = new URLSearchParams();
    if (state.sets.length) p.set('sets', state.sets.join(','));
    if (state.cats.length) p.set('cats', state.cats.join(','));
    if (state.srcs.length) p.set('src', state.srcs.join(','));
    if (state.picks) p.set('picks', '1');
    SEARCH_FIELDS.forEach(function (f) { if (state[f]) p.set(f, state[f]); });
    if (state.scope === 'all' && hasSearch()) p.set('scope', 'all');
    var qs = p.toString();
    history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
    store.set('digest.filters', JSON.stringify({ sets: state.sets, cats: state.cats, srcs: state.srcs, picks: state.picks }));
  }

  // ---------- forms ----------
  var filterForm = $('#filter-form'), searchForm = $('#search-form');
  if (filterForm) {
    filterForm.addEventListener('submit', function (e) {
      e.preventDefault();
      state.sets = $$('input[name="sets"]:checked', filterForm).map(function (i) { return i.value; });
      state.cats = $$('input[name="cats"]:checked', filterForm).map(function (i) { return i.value; });
      state.srcs = $$('input[name="srcs"]:checked', filterForm).map(function (i) { return i.value; });
      state.picks = !!$('input[name="picks"]:checked', filterForm);
      closePanels(); applyView();
    });
    $('[data-clear-filters]', filterForm).addEventListener('click', function () { state.sets = []; state.cats = []; state.srcs = []; state.picks = false; closePanels(); applyView(); });
    var ss = $('.source-search', filterForm);
    if (ss) ss.addEventListener('input', function () { var q = ss.value.toLowerCase().trim(); $$('.source-list label', filterForm).forEach(function (l) { l.hidden = q ? l.getAttribute('data-src-name').indexOf(q) < 0 : l.querySelector('.count').textContent === '0'; }); });
  }
  if (searchForm) {
    searchForm.addEventListener('submit', function (e) {
      e.preventDefault();
      SEARCH_FIELDS.forEach(function (f) { state[f] = (searchForm.elements[f].value || '').trim(); });
      state.scope = searchForm.querySelector('input[name="scope"]:checked').value;
      var err = $('.search-error', searchForm);
      try { buildPredicate(state); } catch (ex) { err.hidden = false; err.textContent = ex.message; return; }
      closePanels(); applyView();
    });
    $('[data-clear-search]', searchForm).addEventListener('click', function () { SEARCH_FIELDS.forEach(function (f) { state[f] = ''; }); state.scope = 'issue'; closePanels(); applyView(); });
  }
  $$('[data-chip-set]').forEach(function (c) {
    c.addEventListener('click', function () { var s = c.getAttribute('data-chip-set'), i = state.sets.indexOf(s); if (i >= 0) state.sets.splice(i, 1); else state.sets.push(s); applyView(); });
  });

  // ---------- keyboard ----------
  var focusIdx = -1;
  function visibleEntries() { return $$('.entry').filter(function (e) { return !e.hidden && e.offsetParent !== null; }); }
  function focusEntry(i) {
    var list = visibleEntries(); if (!list.length) return;
    i = Math.max(0, Math.min(list.length - 1, i)); focusIdx = i;
    $$('.entry.is-focused').forEach(function (e) { e.classList.remove('is-focused'); });
    list[i].classList.add('is-focused'); list[i].scrollIntoView({ block: 'center' });
  }
  function typing(e) { var t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable); }
  doc.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closePanels(); return; }
    if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return;
    var cur = $('.entry.is-focused');
    switch (e.key) {
      case '/': e.preventDefault(); showPanel('search'); break;
      case '?': showPanel('keys'); break;
      case 'j': focusEntry(focusIdx + 1); break;
      case 'k': focusEntry(focusIdx - 1); break;
      case 'o': if (cur) { var a = cur.querySelector('.entry-title a'); if (a) window.open(a.href, '_blank', 'noopener'); } break;
      case 'x': if (cur) { var d = cur.querySelector('details.abstract'); if (d) d.open = !d.open; } break;
    }
  });

  // ---------- init ----------
  if (PAGE === 'issue' && ISSUE) {
    readURL(); countsFromIssue(); syncBadges();
    if (hasSearch() || filterCount()) applyView();
    if (location.hash) { var target = $(location.hash.replace(/[^a-zA-Z0-9_#.-]/g, '')); if (target) { target.scrollIntoView({ block: 'center' }); var dd = target.querySelector('details.abstract'); if (dd) dd.open = true; } }
  }
})();
