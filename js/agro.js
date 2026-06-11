/* ==========================================================================
   agro.js — Núcleo de cálculo do Agro do Dia
   Funções puras, sem DOM. Roda no navegador e no Node (para testes).

   Coeficientes baseados em referências técnicas (Embrapa, IAC, Conab,
   universidades). São estimativas — variam com manejo, cultivar, região e
   condições. As calculadoras são orientativas.
   ========================================================================== */
(function (global) {
  'use strict';

  var num = function (x) { return typeof x === 'number' && isFinite(x); };

  function parseData(s) {
    if (typeof s !== 'string') return null;
    var m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    var dt = new Date(Date.UTC(y, mo - 1, d));
    if (dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
    return dt;
  }
  function formatarData(dt) {
    function p(x) { return (x < 10 ? '0' : '') + x; }
    return p(dt.getUTCDate()) + '/' + p(dt.getUTCMonth() + 1) + '/' + dt.getUTCFullYear();
  }

  /* ======================================================================
     PECUÁRIA
     ====================================================================== */

  // 1. Taxa de lotação da pastagem — Unidade Animal (1 UA = 450 kg de PV)
  function lotacaoPastagem(o) {
    var n = o.numAnimais, p = o.pesoMedio, a = o.area;
    if (!num(n) || !num(p) || !num(a) || n <= 0 || p <= 0 || a <= 0)
      return { error: 'Informe o número de animais, o peso médio e a área (ha).' };
    var pesoTotal = n * p;
    var ua = pesoTotal / 450;
    return { pesoTotal: pesoTotal, ua: ua, uaPorHa: ua / a };
  }

  // 2. Ganho médio diário (GMD) e previsão de abate
  function ganhoPeso(o) {
    var pi = o.pesoInicial, pf = o.pesoFinal, d = o.dias;
    if (!num(pi) || !num(pf) || !num(d) || pi <= 0 || pf <= 0 || d <= 0)
      return { error: 'Informe o peso inicial, o peso final e o número de dias.' };
    if (pf < pi) return { error: 'O peso final deve ser maior que o peso inicial.' };
    var gmd = (pf - pi) / d;
    var out = { gmd: gmd };
    if (num(o.pesoAbate) && o.pesoAbate > 0) {
      out.diasAteAbate = o.pesoAbate <= pf ? 0 : (o.pesoAbate - pf) / gmd;
    }
    return out;
  }

  // 3. Período de gestação e previsão de parto
  var GESTACAO = { bovino: 285, bufalo: 310, equino: 340, ovino: 150, caprino: 150, suino: 114 };
  function gestacao(o) {
    var dias = GESTACAO[o.especie];
    if (!dias) return { error: 'Selecione a espécie do animal.' };
    var d = parseData(o.dataCobertura);
    if (!d) return { error: 'Informe uma data de cobertura válida.' };
    var parto = new Date(d.getTime() + dias * 86400000);
    return { dias: dias, dataParto: formatarData(parto) };
  }

  // 4. Consumo do rebanho — matéria seca (% do peso vivo) e sal mineral
  function consumoRebanho(o) {
    var n = o.numAnimais, p = o.pesoMedio;
    if (!num(n) || !num(p) || n <= 0 || p <= 0)
      return { error: 'Informe o número de animais e o peso médio.' };
    var pct = o.tipo === 'leite' ? 3.1 : 2.3;       // % do peso vivo em MS
    var msAnimal = p * pct / 100;
    var msDia = msAnimal * n;
    var salAnimal = num(o.salDia) && o.salDia > 0 ? o.salDia : 0.1; // kg/animal/dia
    var salDia = salAnimal * n;
    var out = { pct: pct, consumoMSPorAnimal: msAnimal, consumoMSDia: msDia, salDia: salDia };
    if (num(o.diasEstoque) && o.diasEstoque > 0) {
      out.estoqueMS = msDia * o.diasEstoque;
      out.estoqueSal = salDia * o.diasEstoque;
    }
    return out;
  }

  // 5. Dimensionamento de cocho e bebedouro
  var COCHO = { controlado: 60, avontade: 30, mineral: 5, proteinado: 10 }; // cm/animal
  function cocho(o) {
    var n = o.numAnimais;
    if (!num(n) || n <= 0) return { error: 'Informe o número de animais.' };
    var esp = COCHO[o.manejo];
    if (!esp) return { error: 'Selecione o tipo de manejo do cocho.' };
    return {
      espacoPorAnimal: esp,
      comprimentoCocho: esp * n / 100,        // m
      comprimentoBebedouro: 5 * n / 100       // m (~5 cm/animal)
    };
  }

  /* ======================================================================
     LAVOURA
     ====================================================================== */

  // 6. Conversão de sacas, toneladas e kg
  function conversaoSacas(o) {
    var v = o.quantidade;
    if (!num(v) || v < 0) return { error: 'Informe a quantidade.' };
    var ps = num(o.pesoSaca) && o.pesoSaca > 0 ? o.pesoSaca : 60;
    var emKg;
    if (o.de === 'sacas') emKg = v * ps;
    else if (o.de === 't') emKg = v * 1000;
    else if (o.de === 'kg') emKg = v;
    else return { error: 'Selecione a unidade de origem.' };
    var r;
    if (o.para === 'sacas') r = emKg / ps;
    else if (o.para === 't') r = emKg / 1000;
    else if (o.para === 'kg') r = emKg;
    else return { error: 'Selecione a unidade de destino.' };
    return { resultado: r, emKg: emKg };
  }

  // 7. População de plantas e taxa de semeadura
  function populacaoPlantas(o) {
    var eL = o.espacamentoLinhas;
    if (!num(eL) || eL <= 0) return { error: 'Informe o espaçamento entre linhas (m).' };
    var out = {};
    if (num(o.espacamentoPlantas) && o.espacamentoPlantas > 0)
      out.plantasPorHa = 10000 / (eL * o.espacamentoPlantas);
    if (num(o.populacaoDesejada) && o.populacaoDesejada > 0)
      out.sementesPorMetro = (o.populacaoDesejada * eL) / 10000;
    if (out.plantasPorHa === undefined && out.sementesPorMetro === undefined)
      return { error: 'Informe o espaçamento entre plantas ou a população desejada.' };
    return out;
  }

  // 8. Adubação NPK — converte recomendação técnica em adubo comercial
  function adubacaoNPK(o) {
    var pN = o.pctN, pP = o.pctP, pK = o.pctK;
    if (!num(pN) || !num(pP) || !num(pK))
      return { error: 'Informe a fórmula do adubo (% de N, P₂O₅ e K₂O).' };
    function ad(rec, pct) {
      return (num(rec) && rec > 0 && num(pct) && pct > 0) ? rec / pct * 100 : null;
    }
    var aN = ad(o.recN, pN), aP = ad(o.recP, pP), aK = ad(o.recK, pK);
    var vals = [aN, aP, aK].filter(function (x) { return x !== null; });
    if (!vals.length)
      return { error: 'Informe pelo menos uma recomendação (N, P ou K).' };
    return { aduboN: aN, aduboP: aP, aduboK: aK, aduboLimitante: Math.max.apply(null, vals) };
  }

  // 9. Quantidade de sementes (kg/ha)
  function quantidadeSementes(o) {
    var pop = o.populacaoDesejada, pms = o.pms, germ = o.germinacao;
    if (!num(pop) || !num(pms) || !num(germ) || pop <= 0 || pms <= 0 || germ <= 0 || germ > 100)
      return { error: 'Informe a população desejada, o peso de mil sementes e a germinação (1 a 100%).' };
    var pureza = num(o.pureza) && o.pureza > 0 && o.pureza <= 100 ? o.pureza : 98;
    var vc = germ * pureza / 100;                       // valor cultural (%)
    var sementesPorHa = pop / (vc / 100);
    var margem = num(o.margem) && o.margem >= 0 ? o.margem : 0;
    sementesPorHa *= (1 + margem / 100);
    return { vc: vc, sementesPorHa: sementesPorHa, kgPorHa: sementesPorHa * pms / 1e6 };
  }

  // 10. Necessidade de calagem — método da saturação por bases
  function calagem(o) {
    var v1 = o.v1, v2 = o.v2, ctc = o.ctc, prnt = o.prnt;
    if (!num(v1) || !num(v2) || !num(ctc) || !num(prnt))
      return { error: 'Informe V1, V2, CTC e PRNT.' };
    if (prnt <= 0) return { error: 'O PRNT deve ser maior que zero.' };
    if (ctc <= 0) return { error: 'A CTC deve ser maior que zero.' };
    if (v2 <= v1) return { error: 'A saturação desejada (V2) deve ser maior que a atual (V1).' };
    return { nc: (v2 - v1) * ctc / prnt };              // t/ha
  }

  // 11. Conversão de produtividade
  function produtividade(o) {
    var v = o.valor;
    if (!num(v) || v < 0) return { error: 'Informe o valor da produtividade.' };
    var ps = num(o.pesoSaca) && o.pesoSaca > 0 ? o.pesoSaca : 60;
    var kgHa;
    if (o.de === 'sacas_ha') kgHa = v * ps;
    else if (o.de === 'kg_ha') kgHa = v;
    else if (o.de === 't_ha') kgHa = v * 1000;
    else return { error: 'Selecione a unidade de origem.' };
    var r;
    if (o.para === 'sacas_ha') r = kgHa / ps;
    else if (o.para === 'kg_ha') r = kgHa;
    else if (o.para === 't_ha') r = kgHa / 1000;
    else return { error: 'Selecione a unidade de destino.' };
    return { resultado: r };
  }

  /* ======================================================================
     INSUMOS E ARMAZENAGEM
     ====================================================================== */

  // 12. Calda de pulverização
  function caldaPulverizacao(o) {
    var area = o.area, taxa = o.taxaAplicacao, tanque = o.capacidadeTanque, dose = o.dose;
    if (!num(area) || !num(taxa) || area <= 0 || taxa <= 0)
      return { error: 'Informe a área (ha) e a taxa de aplicação (L/ha).' };
    if (!num(tanque) || tanque <= 0) return { error: 'Informe a capacidade do tanque (L).' };
    if (!num(dose) || dose <= 0) return { error: 'Informe a dose do produto.' };
    var volumeTotal = taxa * area;
    var hectaresPorTanque = tanque / taxa;
    var produtoPorTanque, produtoTotal;
    if (o.doseModo === '100L') {
      produtoPorTanque = tanque / 100 * dose;
      produtoTotal = volumeTotal / 100 * dose;
    } else {
      produtoPorTanque = hectaresPorTanque * dose;
      produtoTotal = dose * area;
    }
    return {
      volumeTotalCalda: volumeTotal,
      numTanques: volumeTotal / tanque,
      hectaresPorTanque: hectaresPorTanque,
      produtoPorTanque: produtoPorTanque,
      produtoTotal: produtoTotal
    };
  }

  // 13. Volume de silagem e dimensionamento de silo
  function silagem(o) {
    var c = o.comprimento, lt = o.larguraTopo, alt = o.altura;
    if (!num(c) || !num(lt) || !num(alt) || c <= 0 || lt <= 0 || alt <= 0)
      return { error: 'Informe o comprimento, a largura e a altura do silo.' };
    var lb = num(o.larguraBase) && o.larguraBase > 0 ? o.larguraBase : lt;
    var dens = num(o.densidade) && o.densidade > 0 ? o.densidade : 600; // kg/m³
    var volume = ((lt + lb) / 2) * alt * c;
    var capacidadeKg = volume * dens;
    return { volume: volume, capacidadeKg: capacidadeKg, capacidadeT: capacidadeKg / 1000 };
  }

  // 14. Correcao de umidade de graos
  function umidadeGraos(o) {
    var peso = o.pesoInicial, ui = o.umidadeInicial, uf = o.umidadeFinal;
    if (!num(peso) || !num(ui) || !num(uf) || peso <= 0 || ui <= 0 || uf <= 0)
      return { error: 'Informe o peso, a umidade inicial e a umidade final.' };
    if (ui >= 100 || uf >= 100) return { error: 'As umidades devem ser menores que 100%.' };
    if (ui <= uf) return { error: 'A umidade inicial deve ser maior que a umidade final desejada.' };
    var pesoFinal = peso * (100 - ui) / (100 - uf);
    var aguaRemovida = peso - pesoFinal;
    return {
      pesoFinal: pesoFinal,
      aguaRemovida: aguaRemovida,
      quebraPercentual: aguaRemovida / peso * 100
    };
  }

  // 15. Perda na colheita por amostragem de massa no solo
  function perdaColheita(o) {
    var pesoAmostra = o.pesoAmostra, areaAmostra = o.areaAmostra;
    if (!num(pesoAmostra) || !num(areaAmostra) || pesoAmostra < 0 || areaAmostra <= 0)
      return { error: 'Informe o peso coletado na amostra e a area amostrada.' };
    var ps = num(o.pesoSaca) && o.pesoSaca > 0 ? o.pesoSaca : 60;
    var perdaKgHa = (pesoAmostra / areaAmostra) * 10; // g/m2 para kg/ha
    var perdaSacasHa = perdaKgHa / ps;
    var out = { perdaKgHa: perdaKgHa, perdaSacasHa: perdaSacasHa };
    if (num(o.precoSaca) && o.precoSaca > 0) out.perdaReaisHa = perdaSacasHa * o.precoSaca;
    if (num(o.areaTalhao) && o.areaTalhao > 0) {
      out.perdaKgTotal = perdaKgHa * o.areaTalhao;
      out.perdaSacasTotal = perdaSacasHa * o.areaTalhao;
      if (out.perdaReaisHa !== undefined) out.perdaReaisTotal = out.perdaReaisHa * o.areaTalhao;
    }
    return out;
  }

  // 16. Custo de secagem
  function custoSecagem(o) {
    var pesoEntrada = o.pesoEntrada, ui = o.umidadeInicial, uf = o.umidadeFinal;
    if (!num(pesoEntrada) || !num(ui) || !num(uf) || pesoEntrada <= 0 || ui <= 0 || uf <= 0)
      return { error: 'Informe a quantidade de entrada e as umidades.' };
    if (ui >= 100 || uf >= 100) return { error: 'As umidades devem ser menores que 100%.' };
    if (ui <= uf) return { error: 'A umidade inicial deve ser maior que a umidade final.' };
    var ps = num(o.pesoSaca) && o.pesoSaca > 0 ? o.pesoSaca : 60;
    var entradaT = o.unidade === 'sacas' ? pesoEntrada * ps / 1000 : pesoEntrada;
    var saidaT = entradaT * (100 - ui) / (100 - uf);
    var aguaT = entradaT - saidaT;
    var custoUnit = num(o.custoUnitario) && o.custoUnitario >= 0 ? o.custoUnitario : 0;
    var modo = o.modoCusto || 'tonelada_entrada';
    var custoTotal = modo === 'tonelada_agua' ? aguaT * custoUnit : entradaT * custoUnit;
    return {
      entradaT: entradaT,
      saidaT: saidaT,
      aguaRemovidaT: aguaT,
      custoTotal: custoTotal,
      custoPorTFinal: saidaT > 0 ? custoTotal / saidaT : 0,
      custoPorSacaFinal: saidaT > 0 ? custoTotal / (saidaT * 1000 / ps) : 0
    };
  }

  /* ======================================================================
     MEDIDAS E GESTÃO
     ====================================================================== */

  // 14. Conversão de medidas de área rural
  var AREA_M2 = {
    hectare: 10000, metro: 1, are: 100,
    alqueire_paulista: 24200, alqueire_mineiro: 48400,
    alqueire_goiano: 48400, alqueire_baiano: 96800,
    alqueire_norte: 27225, tarefa_ba: 4356
  };
  function conversaoArea(o) {
    var v = o.valor;
    if (!num(v) || v < 0) return { error: 'Informe o valor da área.' };
    var fDe = AREA_M2[o.de], fPara = AREA_M2[o.para];
    if (!fDe || !fPara) return { error: 'Selecione as unidades de origem e destino.' };
    var emM2 = v * fDe;
    return { resultado: emM2 / fPara, emM2: emM2, emHectares: emM2 / 10000 };
  }

  // 15. Custo de produção e ponto de equilíbrio
  function custoProducao(o) {
    var ct = o.custoTotal, prod = o.producao;
    if (!num(ct) || !num(prod) || ct <= 0 || prod <= 0)
      return { error: 'Informe o custo total e a quantidade produzida.' };
    var custoUnitario = ct / prod;
    var out = { custoUnitario: custoUnitario, pontoEquilibrio: custoUnitario };
    if (num(o.precoVenda) && o.precoVenda > 0) {
      out.receita = o.precoVenda * prod;
      out.lucro = out.receita - ct;
      out.margem = out.lucro / out.receita * 100;
    }
    return out;
  }

  // 19. Frete agricola
  function freteAgricola(o) {
    var dist = o.distancia, carga = o.carga, valor = o.valorTonKm;
    if (!num(dist) || !num(carga) || !num(valor) || dist <= 0 || carga <= 0 || valor < 0)
      return { error: 'Informe a distancia, a carga e o valor do frete por tonelada-km.' };
    var extras = 0;
    if (num(o.pedagio)) extras += o.pedagio;
    if (num(o.cargaDescarga)) extras += o.cargaDescarga;
    if (num(o.outrosCustos)) extras += o.outrosCustos;
    var total = dist * carga * valor + extras;
    var ps = num(o.pesoSaca) && o.pesoSaca > 0 ? o.pesoSaca : 60;
    return {
      custoTotal: total,
      custoPorT: total / carga,
      custoPorSaca: total / (carga * 1000 / ps),
      extras: extras
    };
  }

  // 20. Margem bruta por hectare
  function margemBruta(o) {
    var prod = o.produtividade, preco = o.preco, custoVar = o.custoVariavel;
    if (!num(prod) || !num(preco) || !num(custoVar) || prod <= 0 || preco <= 0 || custoVar < 0)
      return { error: 'Informe a produtividade, o preco de venda e o custo variavel por hectare.' };
    var receitaHa = prod * preco;
    var margemHa = receitaHa - custoVar;
    var custoFixo = num(o.custoFixo) && o.custoFixo >= 0 ? o.custoFixo : 0;
    var lucroHa = margemHa - custoFixo;
    var area = num(o.area) && o.area > 0 ? o.area : null;
    var out = {
      receitaHa: receitaHa,
      margemBrutaHa: margemHa,
      lucroHa: lucroHa,
      margemPercentual: receitaHa > 0 ? margemHa / receitaHa * 100 : 0,
      precoEquilibrioVariavel: custoVar / prod,
      precoEquilibrioTotal: (custoVar + custoFixo) / prod
    };
    if (area) {
      out.receitaTotal = receitaHa * area;
      out.margemBrutaTotal = margemHa * area;
      out.lucroTotal = lucroHa * area;
    }
    return out;
  }

  // 21. Custo de armazenagem
  function custoArmazenagem(o) {
    var q = o.quantidade, meses = o.meses, custoMes = o.custoMensal;
    if (!num(q) || !num(meses) || !num(custoMes) || q <= 0 || meses <= 0 || custoMes < 0)
      return { error: 'Informe a quantidade, o periodo e o custo mensal.' };
    var ps = num(o.pesoSaca) && o.pesoSaca > 0 ? o.pesoSaca : 60;
    var sacas = o.unidade === 't' ? q * 1000 / ps : q;
    var toneladas = sacas * ps / 1000;
    var custoBase = o.baseCusto === 't_mes' ? toneladas * meses * custoMes : sacas * meses * custoMes;
    var custoFixo = num(o.custoFixo) && o.custoFixo >= 0 ? o.custoFixo : 0;
    var custoTotal = custoBase + custoFixo;
    var out = {
      sacas: sacas,
      toneladas: toneladas,
      custoTotal: custoTotal,
      custoPorSaca: custoTotal / sacas,
      custoPorT: custoTotal / toneladas
    };
    if (num(o.precoSaca) && o.precoSaca > 0) {
      out.percentualDoValor = custoTotal / (sacas * o.precoSaca) * 100;
    }
    return out;
  }

  // 22. Comparacao vender agora vs armazenar
  function vendaArmazenagem(o) {
    var q = o.quantidadeSacas, hoje = o.precoHoje, futuro = o.precoFuturo, meses = o.meses;
    if (!num(q) || !num(hoje) || !num(futuro) || !num(meses) || q <= 0 || hoje <= 0 || futuro <= 0 || meses <= 0)
      return { error: 'Informe quantidade, preco atual, preco futuro e periodo.' };
    var custoMes = num(o.custoMensalSaca) && o.custoMensalSaca >= 0 ? o.custoMensalSaca : 0;
    var juros = num(o.jurosMes) && o.jurosMes >= 0 ? o.jurosMes : 0;
    var quebra = num(o.quebraPct) && o.quebraPct >= 0 ? o.quebraPct : 0;
    if (quebra >= 100) return { error: 'A quebra deve ser menor que 100%.' };
    var qFinal = q * (1 - quebra / 100);
    var receitaHoje = q * hoje;
    var custoArm = q * custoMes * meses;
    var custoOportunidade = receitaHoje * (Math.pow(1 + juros / 100, meses) - 1);
    var receitaFutura = qFinal * futuro;
    var resultadoLiquido = receitaFutura - custoArm - custoOportunidade - receitaHoje;
    var precoMinimoFuturo = (receitaHoje + custoArm + custoOportunidade) / qFinal;
    return {
      quantidadeFinal: qFinal,
      receitaHoje: receitaHoje,
      receitaFutura: receitaFutura,
      custoArmazenagem: custoArm,
      custoOportunidade: custoOportunidade,
      resultadoLiquido: resultadoLiquido,
      precoMinimoFuturo: precoMinimoFuturo,
      diferencaPrecoNecessaria: precoMinimoFuturo - hoje
    };
  }

  /* ----------------------------------------------------------------------
     Exportação
     ---------------------------------------------------------------------- */
  var Agro = {
    lotacaoPastagem: lotacaoPastagem, ganhoPeso: ganhoPeso, gestacao: gestacao,
    consumoRebanho: consumoRebanho, cocho: cocho,
    conversaoSacas: conversaoSacas, populacaoPlantas: populacaoPlantas,
    adubacaoNPK: adubacaoNPK, quantidadeSementes: quantidadeSementes,
    calagem: calagem, produtividade: produtividade,
    caldaPulverizacao: caldaPulverizacao, silagem: silagem,
    umidadeGraos: umidadeGraos, perdaColheita: perdaColheita,
    custoSecagem: custoSecagem,
    conversaoArea: conversaoArea, custoProducao: custoProducao,
    freteAgricola: freteAgricola, margemBruta: margemBruta,
    custoArmazenagem: custoArmazenagem, vendaArmazenagem: vendaArmazenagem,
    GESTACAO: GESTACAO, AREA_M2: AREA_M2
  };
  global.Agro = Agro;
  if (typeof module !== 'undefined' && module.exports) module.exports = Agro;

})(typeof window !== 'undefined' ? window : globalThis);
