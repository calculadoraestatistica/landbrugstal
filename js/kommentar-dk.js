/* Kommentar til noteringerne, skrevet ud fra sitets egen tidsserie.
 *
 * Tallene i tabellen ovenfor er andres: Danmarks Statistik, Arla, Danish
 * Crown og Nationalbanken udgiver dem hver for sig. Det, dette site har, er
 * serien: de samme noteringer hentet flere gange hver hverdag siden juni
 * 2026 og lagt i samme fil. tools/kommentar.py læser den serie og regner
 * ud, hvor længe hvert tal har stået stille, hvad der skete sidst det
 * flyttede sig, og hvordan det ser ud over en måned.
 *
 * Hver påstand kan efterprøves mod data/noteringer-historik.json, og ingen
 * påstand rækker ud over serien: et "højeste" hedder altid "højeste siden
 * serien begyndte", med datoen nævnt.
 *
 * Fejler hentningen, vises intet. En tom blok er bedre end en forkert.
 */
(function () {
  'use strict';

  var KILDE = '/data/kommentar-dk.json';

  function tekst(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function datoDK(iso) {
    if (!iso) return '';
    var p = String(iso).split('-');
    return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : iso;
  }

  function byg(data) {
    var serier = (data && data.serier) || [];
    if (!serier.length) return '';

    var punkter = serier.reduce(function (n, s) {
      return n + (s.serie_punkter || 0);
    }, 0);
    var start = serier.map(function (s) { return s.serie_start; })
      .filter(Boolean).sort()[0];

    var lead = data.tvaers
      ? '<p class="kom__lead">' + tekst(data.tvaers) + '</p>'
      : '';

    var punkterHtml = serier.map(function (s) {
      return '<li class="kom__punkt">' + tekst(s.tekst) + '</li>';
    }).join('');

    return ''
      + '<section class="kom" aria-labelledby="kom-titel">'
      + '  <h2 id="kom-titel" class="kom__titel">Sådan har tallene bevæget sig</h2>'
      + lead
      + '  <ul class="kom__liste">' + punkterHtml + '</ul>'
      + '  <p class="kom__kilde">Udregnet på sitets egen serie: '
      + tekst(String(punkter)) + ' målinger siden ' + tekst(datoDK(start))
      + ', opgjort til og med ' + tekst(datoDK(data.data_til_og_med))
      + '. Selve noteringerne kommer fra Danmarks Statistik, Arla, Danish '
      + 'Crown og Nationalbanken; sammenstillingen og udregningen er sitets '
      + 'egen. Tallene kan efterprøves i '
      + '<a href="/data/noteringer-historik.json">historikfilen</a>.</p>'
      + '</section>';
  }

  function start() {
    var vaerter = document.querySelectorAll('[data-kommentar-dk]');
    if (!vaerter.length) return;
    fetch(KILDE, { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var html = byg(data);
        if (!html) return;
        Array.prototype.forEach.call(vaerter, function (v) {
          v.innerHTML = html;
        });
      })
      .catch(function () { /* en tom blok er bedre end en forkert */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
}());
