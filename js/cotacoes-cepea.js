/* Spot-noteringer (DK) — renderiza tabela a partir de /data/cotacoes.json
 * Mostra: produto, valor (DKK), unidade, data. Auto-detecta containers com
 * data-cotacoes-cepea e renderiza tabela compacta. Safe no-op se o JSON 404.
 *
 * Indicadores DK suportados via campo "icon":
 *   hvede (trigo), majs (milho), sojabønner (soja), raps (colza),
 *   byg (cevada), eur_dkk, usd_dkk
 *
 * Uso no HTML:
 *   <div data-cotacoes-cepea></div>
 *   <div data-cotacoes-cepea="completas"></div>
 */
(function () {
  'use strict';

  var ICONS = {
    hvede:      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v18"/><path d="M12 7c-2 0-3-2-3-2M12 7c2 0 3-2 3-2"/><path d="M12 11c-2 0-3-2-3-2M12 11c2 0 3-2 3-2"/><path d="M12 15c-2 0-3-2-3-2M12 15c2 0 3-2 3-2"/></svg>',
    majs:       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3c-2 0-3 1.5-3 3 0 1 .3 2 .8 3-.5 1-.8 2-.8 3 0 1.5 1 3 3 3s3-1.5 3-3c0-1-.3-2-.8-3 .5-1 .8-2 .8-3 0-1.5-1-3-3-3z"/><path d="M9 20l3-3 3 3"/></svg>',
    sojaboenner:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="3"/><circle cx="16" cy="12" r="3"/><circle cx="9" cy="17" r="3"/></svg>',
    raps:       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="3"/><path d="M12 11v9"/><path d="M8 17l4-2 4 2"/></svg>',
    byg:        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v18"/><path d="M10 6l-2 1M14 6l2 1"/><path d="M10 10l-2 1M14 10l2 1"/><path d="M10 14l-2 1M14 14l2 1"/></svg>',
    eur_dkk:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M14 8a4 4 0 0 0-4 4 4 4 0 0 0 4 4"/><path d="M7 11h6M7 13h6"/></svg>',
    usd_dkk:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 6v12"/><path d="M15 9a3 3 0 0 0-3-2c-1.7 0-3 1-3 2.3 0 1.3 1 2 3 2.4 2 .4 3 1.1 3 2.4 0 1.3-1.3 2.3-3 2.3a3 3 0 0 1-3-2"/></svg>'
  };

  // Aliases para chaves com caracteres especiais nos JSONs
  ICONS['sojabønner'] = ICONS.sojaboenner;

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
      var val  = it.value_display || it.value || '';
      return ''
        + '<tr>'
        + '  <td class="cot-cell-prod">'
        + '    <span class="cot-icon" aria-hidden="true">' + icon + '</span>'
        + '    <span><strong>' + name + '</strong><br><span class="cot-unit">' + unit + '</span></span>'
        + '  </td>'
        + '  <td class="cot-cell-val">' + val + '</td>'
        + '  <td class="cot-cell-date">' + formatDate(it.date) + '</td>'
        + '</tr>';
    }).join('');

    var srcUrl = data.source_url || 'https://www.landbrugsinfo.dk/';
    var srcName = data.source || 'SEGES Innovation';

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

  function showError(container) {
    container.innerHTML = ''
      + '<div class="cot-card cot-card--err">'
      + '  <p>Spot-noteringer er ikke tilgængelige lige nu. Se <a href="https://www.landbrugsinfo.dk/" target="_blank" rel="noopener nofollow">landbrugsinfo.dk</a>.</p>'
      + '</div>';
  }

  function render(container) {
    container.innerHTML = '<div class="cot-card cot-card--loading">Indlæser noteringer…</div>';
    var variant = container.getAttribute('data-cotacoes-cepea') || '';
    var url = variant === 'completas' ? '/data/cotacoes-completas.json' : '/data/cotacoes.json';
    if (typeof fetch !== 'function') { showError(container); return; }
    fetch(url, { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then(function (data) {
        if (!data || !data.items || !data.items.length) throw new Error('no items');
        container.innerHTML = buildTable(data);
      })
      .catch(function () { showError(container); });
  }

  function init() {
    var containers = document.querySelectorAll('[data-cotacoes-cepea]');
    if (!containers || !containers.length) return;
    Array.prototype.forEach.call(containers, render);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
