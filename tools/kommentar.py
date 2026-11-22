#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genererer dansk kommentar til prissiden ud fra sitets EGEN tidsserie.

HVORFOR DEN FINDES

Prissiden viste tal hentet fra SEGES/DST, Arla, Danish Crown og
Nationalbanken, med en fast forklarende tekst ved siden af. Tallene er andres;
teksten ændrede sig ikke, uanset hvad tallene gjorde. Google AdSense afviste
sitet 21/11/2026 med "Conteúdo de baixo valor", og programpolitikken siger at
annoncer ikke må vises på skærme "with embedded or copied content from others
without additional commentary, curation, or otherwise adding value to that
content".

Det, sitet har og ingen andre har, er sammenstillingen: en daglig serie for
mælk, gris, kreatur og valuta, kørt siden juni 2026, i samme fil. Denne fil
læser den serie og skriver sætninger, der kun kan skrives af den, der har
serien. Det er tilføjet værdi, og det er sandt.

HVAD DEN IKKE GØR

Den påstår intet, serien ikke kan bære. Konkret:

  * Et ekstrem hedder "højeste i serien siden <startdato>", aldrig "højeste
    nogensinde". Serien begynder i juni 2026 og ved intet om tiden før.
  * En ændring i procent beregnes kun, når begge endepunkter findes. Ingen
    interpolation, intet gæt.
  * En serie med for få punkter får ingen sætning. Tavshed er et gyldigt svar.
  * Tallene afrundes til visning, men sammenlignes råt, så en "uændret" ikke
    skyldes afrunding.

MÅLT PÅ SERIEN 22/11/2026, og det er derfor "uændret siden" er den bærende
oplysning i stedet for en kadence-etiket:

  eur_dkk, usd_dkk   ændrer sig hver dag
  kreaturnotering    ændrer sig hver ~14. dag
  hvede, byg, raps   ændrer sig hver ~31. dag (DST er en månedsstatistik)
  maelkepris         ændrer sig hver ~30. dag
  grisenotering      ændrede sig 2 gange på 5 måneder

Siden lovede "opdateret hver dag" om dem alle. Det passer på to af ni.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORIK = ROOT / "data" / "noteringer-historik.json"
AKTUELLE = ROOT / "data" / "noteringer-dk-completas.json"
UD = ROOT / "data" / "kommentar-dk.json"

# Mindste antal punkter før en serie overhovedet kommenteres.
MIN_PUNKTER = 8
# Under denne forskel i procent regnes to tal som det samme tal.
UBETYDELIG_PCT = 0.05

NAVNE = {
    "maelkepris": ("Mælkeprisen", "øre/kg"),
    "grisenotering": ("Grisenoteringen", "DKK/kg"),
    "kreaturnotering": ("Kreaturnoteringen", "DKK/kg"),
    "eur_dkk": ("EUR/DKK", "DKK"),
    "usd_dkk": ("USD/DKK", "DKK"),
    "hvede": ("Hvedeprisen", "DKK/hkg"),
    "byg": ("Bygprisen", "DKK/hkg"),
    "raps": ("Rapsprisen", "DKK/hkg"),
}

MAANED = ["januar", "februar", "marts", "april", "maj", "juni", "juli",
          "august", "september", "oktober", "november", "december"]


def dk_dato(d: date) -> str:
    """5. juni — den form en dansk læser forventer i løbende tekst."""
    return "%d. %s" % (d.day, MAANED[d.month - 1])


def dk_tal(v: float) -> str:
    """Komma som decimaltegn. To decimaler, men ingen hale af nuller."""
    s = ("%.2f" % v).rstrip("0").rstrip(".")
    return s.replace(".", ",")


def i_loebende_tekst(navn: str) -> str:
    """Navnet midt i en sætning.

    Et almindeligt ord skrives med lille, men en forkortelse beholder sine
    versaler: ".lower()" lavede "USD/DKK" om til "usd/dkk" i første udgave.
    """
    if navn.upper() == navn:
        return navn
    return navn[0].lower() + navn[1:]


def laes_serie(raa: list) -> list[tuple[date, float]]:
    ud = []
    for p in raa or []:
        try:
            ud.append((date.fromisoformat(p["d"]), float(p["v"])))
        except (KeyError, TypeError, ValueError):
            continue
    ud.sort()
    return ud


def pct(fra: float, til: float) -> float | None:
    if not fra:
        return None
    return 100.0 * (til - fra) / fra


def vaerdi_for(serie, dage_siden: int, idag: date) -> tuple[date, float] | None:
    """Det nyeste punkt, der er mindst ``dage_siden`` gammelt.

    Returnerer None, når serien ikke går så langt tilbage. Så udelades
    sætningen helt i stedet for at sammenligne med serien start og kalde det
    en måned.
    """
    graense = idag.toordinal() - dage_siden
    kandidater = [p for p in serie if p[0].toordinal() <= graense]
    return kandidater[-1] if kandidater else None


def analyser(key: str, serie: list[tuple[date, float]], idag: date) -> dict | None:
    if len(serie) < MIN_PUNKTER:
        return None

    navn, enhed = NAVNE.get(key, (key, ""))
    start_dato, _ = serie[0]
    sidste_dato, sidste = serie[-1]

    # Hvornår ændrede tallet sig sidst? Bagfra, indtil et andet tal.
    sidst_aendret = None
    forrige_vaerdi = None
    for d, v in reversed(serie):
        if v != sidste:
            forrige_vaerdi = v
            break
        sidst_aendret = d
    dage_uaendret = (sidste_dato - sidst_aendret).days if sidst_aendret else None

    # Ekstremer, altid målt inden for serien og aldrig derudover.
    vaerdier = [v for _, v in serie]
    er_hoejeste = sidste >= max(vaerdier) - 1e-9
    er_laveste = sidste <= min(vaerdier) + 1e-9

    # Ændring over 30 dage, kun når serien rækker så langt tilbage.
    maaned = vaerdi_for(serie, 30, idag)
    aendring_30 = pct(maaned[1], sidste) if maaned else None

    saetninger: list[str] = []

    # 1. Niveauet nu, og hvor længe det har stået stille.
    #
    # "ændrede sig fra 7,47 til 7,47" er noget vrøvl, og det opstod, fordi
    # bevægelsen var mindre end de to decimaler, tabellen viser. Når de to
    # tal ser ens ud for læseren, skal sætningen heller ikke påstå et skift.
    ser_ens_ud = (forrige_vaerdi is not None
                  and dk_tal(forrige_vaerdi) == dk_tal(sidste))

    if dage_uaendret is not None and dage_uaendret >= 7:
        saetninger.append(
            "%s har stået uændret på %s %s siden %s, altså %d dage."
            % (navn, dk_tal(sidste), enhed, dk_dato(sidst_aendret),
               dage_uaendret))
    elif forrige_vaerdi is not None and sidst_aendret and not ser_ens_ud:
        retning = "op" if sidste > forrige_vaerdi else "ned"
        saetninger.append(
            "%s gik %s den %s, fra %s til %s %s."
            % (navn, retning, dk_dato(sidst_aendret), dk_tal(forrige_vaerdi),
               dk_tal(sidste), enhed))
    else:
        saetninger.append("%s er %s %s." % (navn, dk_tal(sidste), enhed))

    # 2. Retningen over en måned.
    #
    # To fælder, begge set i den første udgave af filen:
    #
    #   Har tallet stået stille i 30 dage eller mere, ER månedsændringen nul.
    #   At tilføje "stort set uændret" gentager bare sætning 1.
    #
    #   Har det stået stille i f.eks. 22 dage, men ændret sig for 25 dage
    #   siden, så er begge sætninger sande og læses alligevel som en
    #   modsigelse: "uændret siden 30. oktober" plus "faldet 1,08 procent
    #   den seneste måned". Så siges det i stedet, hvad der faktisk skete:
    #   ét spring, på én dato.
    staaet_stille_hele_maaneden = (dage_uaendret is not None
                                   and dage_uaendret >= 30)
    et_enkelt_spring = (dage_uaendret is not None and 7 <= dage_uaendret < 30
                        and forrige_vaerdi is not None)

    if aendring_30 is None or staaet_stille_hele_maaneden:
        pass
    elif et_enkelt_spring and abs(aendring_30) >= UBETYDELIG_PCT:
        # Retningen SKAL med. Første udgave skrev "springet var på 1,08
        # procent" om et fald, fordi den tog absolutværdien, og et fald
        # læses så som en stigning.
        saetninger.append(
            "Det var %s på %s procent, og det er hele bevægelsen den "
            "seneste måned."
            % ("en stigning" if aendring_30 > 0 else "et fald",
               dk_tal(abs(aendring_30))))
    elif abs(aendring_30) >= UBETYDELIG_PCT:
        saetninger.append(
            "Over den seneste måned er den %s %s procent."
            % ("steget" if aendring_30 > 0 else "faldet",
               dk_tal(abs(aendring_30))))
    else:
        saetninger.append("Over den seneste måned er den stort set uændret.")

    # 3. Ekstrem, altid med seriens startdato, så påstanden kan efterprøves.
    if er_hoejeste and len(serie) >= 20:
        saetninger.append(
            "Det er det højeste niveau, siden serien her begyndte %s."
            % dk_dato(start_dato))
    elif er_laveste and len(serie) >= 20:
        saetninger.append(
            "Det er det laveste niveau, siden serien her begyndte %s."
            % dk_dato(start_dato))

    return {
        "key": key,
        "navn": navn,
        "enhed": enhed,
        "vaerdi": sidste,
        "serie_start": start_dato.isoformat(),
        "serie_punkter": len(serie),
        "sidst_aendret": sidst_aendret.isoformat() if sidst_aendret else None,
        "dage_uaendret": dage_uaendret,
        "aendring_30d_pct": round(aendring_30, 2) if aendring_30 is not None else None,
        "hoejeste_i_serien": er_hoejeste,
        "laveste_i_serien": er_laveste,
        "tekst": " ".join(saetninger),
    }


def tvaers(analyser_: list[dict]) -> str | None:
    """Én sætning om det, ingen af serierne siger alene.

    Kun når to serier peger hver sin vej over samme måned. Det er den
    sammenstilling, sitet har og kilderne ikke har, fordi kilderne udgiver
    hver for sig.
    """
    med = [a for a in analyser_
           if a.get("aendring_30d_pct") is not None
           and abs(a["aendring_30d_pct"]) >= 1.0]
    if len(med) < 2:
        return None
    op = [a for a in med if a["aendring_30d_pct"] > 0]
    ned = [a for a in med if a["aendring_30d_pct"] < 0]
    if not op or not ned:
        return None
    a = max(op, key=lambda x: x["aendring_30d_pct"])
    b = min(ned, key=lambda x: x["aendring_30d_pct"])
    return ("Den seneste måned er %s steget %s procent, mens %s er faldet %s "
            "procent." % (i_loebende_tekst(a["navn"]),
                          dk_tal(a["aendring_30d_pct"]),
                          i_loebende_tekst(b["navn"]),
                          dk_tal(abs(b["aendring_30d_pct"]))))


def main() -> int:
    if not HISTORIK.exists():
        print("mangler %s" % HISTORIK, file=sys.stderr)
        return 1
    historik = json.loads(HISTORIK.read_text(encoding="utf-8"))

    # "I dag" tages fra seriens nyeste punkt, ikke fra uret: så giver en
    # genkørsel samme resultat, og en fil, der ikke er opdateret, lyver ikke
    # om hvor gammel den er.
    alle_datoer = [d for v in historik.values() if isinstance(v, list)
                   for d in (laes_serie(v) or [])]
    if not alle_datoer:
        print("ingen brugbare punkter i historikken", file=sys.stderr)
        return 1
    idag = max(d for d, _ in alle_datoer)

    ud = []
    for key, raa in historik.items():
        if not isinstance(raa, list):
            continue
        a = analyser(key, laes_serie(raa), idag)
        if a:
            ud.append(a)

    payload = {
        "genereret": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_til_og_med": idag.isoformat(),
        "kilde": ("Beregnet af landbrugstal.dk ud fra sitets egen tidsserie. "
                  "Tallene stammer fra Danmarks Statistik, Arla, Danish Crown "
                  "og Nationalbanken; sammenstillingen og udregningen er "
                  "sitets egen."),
        "tvaers": tvaers(ud),
        "serier": ud,
    }

    # Skriv kun, når indholdet faktisk er et andet, så en genkørsel ikke
    # laver en tom commit. "genereret" tælles ikke med i sammenligningen,
    # af samme grund som i scrape_country.py.
    if UD.exists():
        try:
            gammel = json.loads(UD.read_text(encoding="utf-8"))
            if ({k: v for k, v in gammel.items() if k != "genereret"}
                    == {k: v for k, v in payload.items() if k != "genereret"}):
                print("kommentar uændret, skriver ikke")
                return 0
        except (ValueError, OSError):
            pass

    UD.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
    print("skrev %s (%d serier, data til og med %s)"
          % (UD.name, len(ud), idag))
    for a in ud:
        print("  %-18s %s" % (a["key"], a["tekst"]))
    if payload["tvaers"]:
        print("  %-18s %s" % ("(på tværs)", payload["tvaers"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
