/* Gráfico das cotações a partir do histórico diário que o robô salva.
 *
 * Substituiu um mp4 renderizado: o vídeo congelava o dado no dia em que foi
 * gerado e pesava mais do que a série inteira em JSON. Aqui o gráfico é
 * desenhado no navegador a partir do mesmo arquivo que alimenta a tabela,
 * então acompanha a atualização diária sozinho.
 *
 * Uso: window.CotChart.montar(el, {
 *   historico: '/data/cotacoes-historico.json',
 *   locale: 'pt-BR', moeda: 'R$',
 *   textos: { semana:'7 dias', mes:'30 dias', ... }
 * });
 * Depois, CotChart.mostrar(slug, nome, unidade) a cada clique numa linha.
 */
(function () {
  "use strict";

  var estado = { dados: null, slug: null, nome: "", unidade: "", dias: 7, cfg: null, el: null };

  function fmtNum(v, locale) {
    var casas = Math.abs(v) >= 100 ? 2 : Math.abs(v) >= 10 ? 2 : 3;
    return v.toLocaleString(locale, { minimumFractionDigits: casas, maximumFractionDigits: casas });
  }

  function fmtDataCurta(iso) {
    var p = iso.split("-");
    return p[2] + "/" + p[1];
  }

  function janela(serie, dias) {
    if (!serie || !serie.length) return [];
    // A série guarda um ponto por dia útil coletado, não por dia de calendário.
    // Contar para trás pela DATA evita mostrar 30 pregões quando o usuário
    // pediu 30 dias.
    var fim = new Date(serie[serie.length - 1].d + "T12:00:00");
    var corte = new Date(fim.getTime() - (dias - 1) * 86400000);
    var out = serie.filter(function (p) { return new Date(p.d + "T12:00:00") >= corte; });
    return out.length >= 2 ? out : serie.slice(-Math.min(serie.length, Math.max(2, dias)));
  }

  function desenhar() {
    var c = estado.cfg, t = c.textos;
    var serie = (estado.dados || {})[estado.slug] || [];
    var pts = janela(serie, estado.dias);
    var alvo = estado.el.querySelector("[data-cot-chart-body]");
    if (!alvo) return;

    if (pts.length < 2) {
      alvo.innerHTML = '<p class="cot-chart__vazio">' + t.semDados + "</p>";
      return;
    }

    var W = 760, H = 210, ml = 14, mr = 14, mt = 16, mb = 26;
    var vs = pts.map(function (p) { return p.v; });
    var vmin = Math.min.apply(null, vs), vmax = Math.max.apply(null, vs);
    var span = vmax - vmin || Math.abs(vmax) * 0.02 || 1;
    var pad = span * 0.22;
    var x = function (i) { return ml + (i / (pts.length - 1)) * (W - ml - mr); };
    var y = function (v) { return mt + (1 - (v - vmin + pad) / (span + pad * 2)) * (H - mt - mb); };

    var linha = pts.map(function (p, i) { return x(i) + "," + y(p.v); }).join(" ");
    var area = ml + "," + (H - mb) + " " + linha + " " + x(pts.length - 1) + "," + (H - mb);

    var prim = pts[0].v, ult = pts[pts.length - 1].v;
    var varPct = prim ? ((ult - prim) / Math.abs(prim)) * 100 : 0;
    var sinal = varPct > 0.05 ? "sobe" : varPct < -0.05 ? "desce" : "estavel";
    var seta = sinal === "sobe" ? "▲" : sinal === "desce" ? "▼" : "•";

    var iMax = vs.indexOf(vmax), iMin = vs.indexOf(vmin);
    var marca = function (i, v, acima) {
      return '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="3.5" class="cot-chart__ponto"/>'
        + '<text x="' + Math.min(Math.max(x(i), 34), W - 34) + '" y="' + (acima ? y(v) - 9 : y(v) + 16)
        + '" class="cot-chart__marca" text-anchor="middle">' + fmtNum(v, c.locale) + "</text>";
    };

    alvo.innerHTML = ''
      + '<svg viewBox="0 0 ' + W + " " + H + '" class="cot-chart__svg" role="img" aria-label="'
      + estado.nome + ", " + t.ariaGrafico.replace("{n}", pts.length) + '">'
      + '  <polygon points="' + area + '" class="cot-chart__area"/>'
      + '  <polyline points="' + linha + '" class="cot-chart__linha"/>'
      + (iMax !== iMin ? marca(iMax, vmax, true) + marca(iMin, vmin, false) : "")
      + '  <circle cx="' + x(pts.length - 1) + '" cy="' + y(ult) + '" r="5" class="cot-chart__fim"/>'
      + '  <text x="' + ml + '" y="' + (H - 6) + '" class="cot-chart__eixo">' + fmtDataCurta(pts[0].d) + "</text>"
      + '  <text x="' + (W - mr) + '" y="' + (H - 6) + '" class="cot-chart__eixo" text-anchor="end">'
      + fmtDataCurta(pts[pts.length - 1].d) + "</text>"
      + "</svg>";

    var cab = estado.el.querySelector("[data-cot-chart-head]");
    if (cab) {
      cab.innerHTML = ''
        + '<div class="cot-chart__titulo"><strong>' + estado.nome + "</strong>"
        + '<span class="cot-chart__un">' + (estado.unidade || "") + "</span></div>"
        + '<div class="cot-chart__num"><span class="cot-chart__valor">' + fmtNum(ult, c.locale) + "</span>"
        + '<span class="cot-chart__var cot-chart__var--' + sinal + '">' + seta + " "
        + (varPct >= 0 ? "+" : "") + varPct.toFixed(1).replace(".", c.locale === "pt-BR" ? "," : ",") + "%"
        + '<span class="cot-chart__periodo">' + (estado.dias === 7 ? t.em7 : t.em30) + "</span></span></div>";
    }
  }

  function marcarBotoes() {
    var bs = estado.el.querySelectorAll("[data-cot-dias]");
    Array.prototype.forEach.call(bs, function (b) {
      var ativo = Number(b.getAttribute("data-cot-dias")) === estado.dias;
      b.setAttribute("aria-pressed", ativo ? "true" : "false");
      b.classList.toggle("is-ativo", ativo);
    });
  }

  var api = {
    montar: function (el, cfg) {
      estado.el = el; estado.cfg = cfg;
      var t = cfg.textos;
      el.innerHTML = ''
        + '<div class="cot-chart">'
        + '  <div class="cot-chart__top">'
        + '    <div data-cot-chart-head class="cot-chart__head"></div>'
        + '    <div class="cot-chart__btns" role="group" aria-label="' + t.periodo + '">'
        + '      <button type="button" data-cot-dias="7" aria-pressed="true" class="is-ativo">' + t.semana + "</button>"
        + '      <button type="button" data-cot-dias="30" aria-pressed="false">' + t.mes + "</button>"
        + "    </div>"
        + "  </div>"
        + '  <div data-cot-chart-body class="cot-chart__body"><p class="cot-chart__vazio">' + t.carregando + "</p></div>"
        + '  <p class="cot-chart__dica">' + t.dica + "</p>"
        + "</div>";

      el.addEventListener("click", function (ev) {
        var b = ev.target.closest("[data-cot-dias]");
        if (!b) return;
        estado.dias = Number(b.getAttribute("data-cot-dias"));
        marcarBotoes(); desenhar();
      });

      fetch(cfg.historico, { cache: "no-cache" })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (d) {
          estado.dados = d;
          if (estado.slug) desenhar();
          else {
            var body = el.querySelector("[data-cot-chart-body]");
            if (body) body.innerHTML = '<p class="cot-chart__vazio">' + t.escolha + "</p>";
          }
        })
        .catch(function () {
          var body = el.querySelector("[data-cot-chart-body]");
          if (body) body.innerHTML = '<p class="cot-chart__vazio">' + t.semDados + "</p>";
        });
    },

    mostrar: function (slug, nome, unidade) {
      estado.slug = slug; estado.nome = nome; estado.unidade = unidade || "";
      if (estado.el) {
        estado.el.scrollIntoView({ behavior: "smooth", block: "nearest" });
        if (estado.dados) desenhar();
      }
    },

    temSerie: function (slug) {
      return !!(estado.dados && estado.dados[slug] && estado.dados[slug].length >= 2);
    },
  };

  window.CotChart = api;
})();
