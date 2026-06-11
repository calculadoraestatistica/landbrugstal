/* ==========================================================================
   app.js — Comportamento compartilhado do Kit Clínico
   Menu responsivo, ano no rodapé, anúncios, busca de calculadoras e
   utilitários de número/formatação.
   ========================================================================== */
(function () {
  'use strict';

  /* --- Menu responsivo --------------------------------------------------- */
  var toggle = document.querySelector('.nav-toggle');
  var nav = document.querySelector('.main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        nav.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && nav.classList.contains('is-open')) {
        nav.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* --- Ano no rodapé ----------------------------------------------------- */
  var y = document.querySelectorAll('[data-year]');
  for (var i = 0; i < y.length; i++) y[i].textContent = new Date().getFullYear();

  /* --- Anúncios (AdSense) ------------------------------------------------ */
  /* A biblioteca do AdSense é carregada diretamente no <head> de cada página.
     Este bloco apenas cria as unidades de anúncio manuais nos espaços
     .ad-slot quando um ID do AdSense estiver definido em config.js. */
  var cfg = window.SITE_CONFIG || {};
  if (cfg.adsenseClient) {
    var slots = document.querySelectorAll('.ad-slot');
    for (var s = 0; s < slots.length; s++) {
      var ins = document.createElement('ins');
      ins.className = 'adsbygoogle';
      ins.style.display = 'block';
      ins.setAttribute('data-ad-client', cfg.adsenseClient);
      ins.setAttribute('data-ad-format', 'auto');
      ins.setAttribute('data-full-width-responsive', 'true');
      var unit = slots[s].getAttribute('data-ad-slot');
      if (unit) ins.setAttribute('data-ad-slot', unit);
      slots[s].appendChild(ins);
      try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {}
    }
  }

  /* --- Busca de calculadoras (páginas de área) -------------------------- */
  var search = document.getElementById('calc-search');
  if (search) {
    var cats = Array.prototype.slice.call(document.querySelectorAll('.calc-category'));
    var empty = document.querySelector('.search-empty');
    function norm(t) {
      return t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    }
    search.addEventListener('input', function () {
      var terms = norm(search.value.trim()).split(/\s+/).filter(Boolean);
      var anyTotal = false;
      cats.forEach(function (cat) {
        var cards = cat.querySelectorAll('.calc-card');
        var anyCat = false;
        for (var c = 0; c < cards.length; c++) {
          var hay = norm(cards[c].textContent + ' ' +
                         (cards[c].getAttribute('data-keywords') || ''));
          var match = terms.every(function (t) { return hay.indexOf(t) > -1; });
          cards[c].style.display = match ? '' : 'none';
          if (match) { anyCat = true; anyTotal = true; }
        }
        cat.style.display = anyCat ? '' : 'none';
      });
      if (empty) empty.style.display = anyTotal ? 'none' : 'block';
    });
  }

  /* --- Utilitários de número / formatação (pt-BR) ----------------------- */
  function parseNum(v) {
    if (typeof v === 'number') return v;
    if (v == null) return NaN;
    var s = String(v).trim().replace(/\s/g, '').replace(/%/g, '');
    if (s === '') return NaN;
    if (s.indexOf(',') > -1 && s.indexOf('.') > -1) {
      s = s.replace(/\./g, '').replace(',', '.');
    } else if (s.indexOf(',') > -1) {
      s = s.replace(',', '.');
    }
    var n = parseFloat(s);
    return isNaN(n) ? NaN : n;
  }
  function fmtNum(n, dec) {
    if (dec === undefined) dec = 2;
    if (!isFinite(n)) return '—';
    return n.toLocaleString('pt-BR', {
      minimumFractionDigits: dec, maximumFractionDigits: dec
    });
  }
  function fmtInt(n) {
    return isFinite(n) ? Math.round(n).toLocaleString('pt-BR') : '—';
  }
  function radioValue(name) {
    var el = document.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : null;
  }
  window.Fmt = { parseNum: parseNum, num: fmtNum, int: fmtInt, radio: radioValue };
  window.parseNum = parseNum;
})();
