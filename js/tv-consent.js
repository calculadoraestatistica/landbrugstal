/* landbrugstal.dk — indlæsning af TradingView-widgets efter klik.
 *
 * Hvorfor: widgetten kommer fra s3.tradingview.com og sætter TradingViews egne
 * cookies. Før denne fil lå scriptet direkte i HTML'en og blev hentet ved hvert
 * sidevisning, uanset hvad besøgende svarede i samtykkebanneret. Banneret
 * skrev kun i localStorage og kaldte gtag; det blokerede ingenting. Knappen
 * "Afvis" lovede altså en kontrol, der ikke fandtes.
 *
 * Nu ligger konfigurationen i et <script type="application/json">, som
 * browseren hverken henter eller kører. Det rigtige script bliver først lavet,
 * når besøgende trykker på knappen. Samtykket gælder dér, hvor dataen bliver
 * hentet, og ikke i et banner et andet sted på siden.
 *
 * Prisen for besøgende er lille: tabellen med DK-noteringer er sidens eget
 * data og vises med det samme. Kun grafen fra TradingView venter på klikket.
 *
 * Valget huskes lokalt, så den, der har trykket én gang, ikke skal trykke igen.
 * Nøglen bliver kun læst og skrevet i denne browser og sendes ingen steder.
 */
(function () {
  'use strict';

  var KEY = 'tv-samtykke';

  function harSagtJa() {
    try {
      return localStorage.getItem(KEY) === 'ja';
    } catch (_) {
      return false;                 /* privat vindue, blokeret lager */
    }
  }

  function husk() {
    try {
      localStorage.setItem(KEY, 'ja');
    } catch (_) { /* ingen grund til at fejle på det */ }
  }

  function indlæs(boks) {
    if (boks.getAttribute('data-tv-indlæst')) return;
    var cfg = boks.querySelector('script.tv-config');
    if (!cfg) return;
    var url = cfg.getAttribute('data-tv-src');
    if (!url) return;
    boks.setAttribute('data-tv-indlæst', '1');

    var port = boks.querySelector('.tv-gate');
    if (port) port.hidden = true;

    /* TradingViews loader leder selv efter sit script i DOM'en og læser
       konfigurationen fra scriptets tekstindhold. Derfor skal det nye script
       have BÅDE src og den samme tekst, og det skal ligge i samme boks. */
    var s = document.createElement('script');
    s.type = 'text/javascript';
    s.async = true;
    s.src = url;
    s.text = cfg.textContent;
    boks.appendChild(s);
  }

  function start() {
    var bokse = document.querySelectorAll('.tradingview-widget-container');
    for (var i = 0; i < bokse.length; i++) {
      (function (boks) {
        var knap = boks.querySelector('.tv-gate__knap');
        if (knap) {
          knap.addEventListener('click', function () {
            husk();
            /* alle bokse på siden, så man ikke skal klikke tre gange */
            var alle = document.querySelectorAll('.tradingview-widget-container');
            for (var j = 0; j < alle.length; j++) indlæs(alle[j]);
          });
        }
        if (harSagtJa()) indlæs(boks);
      }(bokse[i]));
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
}());
