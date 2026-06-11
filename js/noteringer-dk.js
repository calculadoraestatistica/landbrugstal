/* Spot-noteringer (DK) — renderer tabel ud fra /data/noteringer-dk.json
 * Viser: produkt, værdi (DKK), enhed, dato. Auto-detekterer containere med
 * data-cotacoes-noteringer-dk og renderer kompakt tabel. Safe no-op hvis JSON 404.
 *
 * DK-indikatorer understøttet via "icon"-feltet:
 *   hvede, byg, raps, majs, maelk, gris/grisenotering, kreatur/kreaturnotering,
 *   eur_dkk, usd_dkk
 *
 * Brug i HTML:
 *   <div data-cotacoes-noteringer-dk></div>
 *   <div data-cotacoes-noteringer-dk="komplet"></div>
 */
(function () {
  'use strict';

  var ICONS = {
    hvede:      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v18"/><path d="M12 7c-2 0-3-2-3-2M12 7c2 0 3-2 3-2"/><path d="M12 11c-2 0-3-2-3-2M12 11c2 0 3-2 3-2"/><path d="M12 15c-2 0-3-2-3-2M12 15c2 0 3-2 3-2"/></svg>',
    byg:        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v18"/><path d="M10 6l-2 1M14 6l2 1"/><path d="M10 10l-2 1M14 10l2 1"/><path d="M10 14l-2 1M14 14l2 1"/></svg>',
    raps:       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="3"/><path d="M12 11v9"/><path d="M8 17l4-2 4 2"/></svg>',
    majs:       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3c-2 0-3 1.5-3 3 0 1 .3 2 .8 3-.5 1-.8 2-.8 3 0 1.5 1 3 3 3s3-1.5 3-3c0-1-.3-2-.8-3 .5-1 .8-2 .8-3 0-1.5-1-3-3-3z"/><path d="M9 20l3-3 3 3"/></svg>',
    maelk:      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 2h8v4l2 4v12H6V10l2-4V2z"/><path d="M8 6h8"/><path d="M9 14h6"/></svg>',
    gris:       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="13" r="7"/><path d="M9 11h.01M15 11h.01"/><path d="M10 16c.7.6 1.3.8 2 .8s1.3-.2 2-.8"/><path d="M8 7l1.5 2M16 7l-1.5 2"/></svg>',
    kreatur:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9c-1.5-2-3-2-3-4 2 0 3 1 4 2"/><path d="M18 9c1.5-2 3-2 3-4-2 0-3 1-4 2"/><ellipse cx="12" cy="14" rx="6" ry="5"/><path d="M10 13h.01M14 13h.01"/><path d="M10 17c.7.4 1.3.5 2 .5s1.3-.1 2-.5"/></svg>',
    eur_dkk:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M14 8a4 4 0 0 0-4 4 4 4 0 0 0 4 4"/><path d="M7 11h6M7 13h6"/></svg>',
    usd_dkk:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 6v12"/><path d="M15 9a3 3 0 0 0-3-2c-1.7 0-3 1-3 2.3 0 1.3 1 2 3 2.4 2 .4 3 1.1 3 2.4 0 1.3-1.3 2.3-3 2.3a3 3 0 0 1-3-2"/></svg>'
  };

  // Aliases for alternative key spellings used in the scraper JSON
  ICONS.maelkepris       = ICONS.maelk;
  ICONS['mælk']          = ICONS.maelk;
  ICONS['mælkepris']     = ICONS.maelk;
  ICONS.grisenotering    = ICONS.gris;
  ICONS.svinenotering    = ICONS.gris;
  ICONS.kreaturnotering  = ICONS.kreatur;
  ICONS.oksenotering     = ICONS.kreatur;

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function formatRelative(updatedAt) {
    if (!updatedAt) return '';
    try {
      var d = new Date(updatedAt);
      return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1)
        + ' kl. ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
    } catch (e) {
      return updatedAt;
    }
  }

  function formatDate(iso) {
    if (!iso) return '';
    var p = String(iso).split('-');
    if (p.length === 3) return p[2] + '/' + p[1] + '/' + p[0];
    return iso;
  }

  function buildTable(data) {
    var rows = (data.items || []).map(function (it) {
      var icon = ICONS[it.icon] || '';
      var name = it.name || '';
      var unit = it.unit || '';
      var hasValue = it.value !== null && it.value !== undefined;
      var val;
      if (it.stale && !hasValue) {
        var src = it.source_url || data.source_url || '#';
        val = '<a class="cot-source-link" href="' + src + '" target="_blank" rel="noopener nofollow">Se kilde →</a>';
      } else {
        val = it.value_display || it.value || '—';
      }
      var staleBadge = (it.stale && hasValue)
        ? ' <span class="cot-stale" title="Seneste kendte værdi (live-scrape mislykkedes)">·</span>'
        : '';
      var dateCell;
      if (it.stale && !hasValue) {
        dateCell = '<span class="cot-unit">live ej tilgængelig</span>';
      } else if (it.stale && hasValue) {
        var seen = formatDate(it.last_seen_date || it.date);
        dateCell = '<span class="cot-unit" title="Live-scrape mislykkedes; viser seneste kendte værdi">Senest set: ' + seen + '</span>';
      } else {
        dateCell = formatDate(it.date);
      }
      return ''
        + '<tr' + (it.stale ? ' class="cot-row-stale"' : '') + '>'
        + '  <td class="cot-cell-prod">'
        + '    <span class="cot-icon" aria-hidden="true">' + icon + '</span>'
        + '    <span><strong>' + name + '</strong>' + staleBadge + '<br><span class="cot-unit">' + unit + '</span></span>'
        + '  </td>'
        + '  <td class="cot-cell-val">' + val + '</td>'
        + '  <td class="cot-cell-date">' + dateCell + '</td>'
        + '</tr>';
    }).join('');

    var srcUrl = data.source_url || 'https://farmtalonline.dlbr.dk/';
    var srcName = data.source || 'SEGES Farmtal Online';

    return ''
      + '<div class="cot-card">'
      + '  <table class="cot-table" aria-label="Spot-noteringer">'
      + '    <thead><tr>'
      + '      <th>Produkt</th><th>Pris</th><th>Dato</th>'
      + '    </tr></thead>'
      + '    <tbody>' + rows + '</tbody>'
      + '  </table>'
      + '  <div class="cot-footer">'
      + '    <span>Opdateret: <strong>' + formatRelative(data.updated_at) + '</strong></span>'
      + '    <span>Kilde: <a href="' + srcUrl + '" target="_blank" rel="noopener nofollow">' + srcName + '</a></span>'
      + '  </div>'
      + '</div>';
  }

  function showPlaceholder(container) {
    container.innerHTML = ''
      + '<div class="cot-card cot-card--err">'
      + '  <p>Noteringer indlæses snart. Se <a href="https://farmtalonline.dlbr.dk/" target="_blank" rel="noopener nofollow">farmtalonline.dlbr.dk</a>.</p>'
      + '</div>';
  }

  function render(container) {
    container.innerHTML = '<div class="cot-card cot-card--loading">Indlæser noteringer…</div>';
    var variant = container.getAttribute('data-cotacoes-noteringer-dk') || '';
    var url = variant === 'komplet' ? '/data/noteringer-dk-completas.json' : '/data/noteringer-dk.json';
    if (typeof fetch !== 'function') { showPlaceholder(container); return; }
    fetch(url, { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then(function (data) {
        if (!data || !data.items || !data.items.length) throw new Error('no items');
        container.innerHTML = buildTable(data);
      })
      .catch(function () { showPlaceholder(container); });
  }

  function init() {
    var containers = document.querySelectorAll('[data-cotacoes-noteringer-dk]');
    if (!containers || !containers.length) return;
    Array.prototype.forEach.call(containers, render);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
