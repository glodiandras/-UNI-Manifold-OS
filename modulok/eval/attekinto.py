"""Az aranyhalmazok áttekintő oldala a jóváhagyáshoz: `{tmp}/c18-attekinto/index.html` (helyi, hálózat nélkül).

    bin/mos exec var/venv/bin/python -B modulok/eval/attekinto.py

A képleteket a felület vendorált KaTeX-e rajzolja (az `app/node_modules/katex` másolata az oldal mellé);
a képletkivágások a vault fotóiból készülnek a `{tmp}` alá. A vaultot és a fotókat csak olvassa.
"""
from __future__ import annotations

import html
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT))
from kozos import arany as A  # noqa: E402
from kozos import kep  # noqa: E402

CSS = """
:root{--h:#fbf8f3;--sz:#231f1c;--halk:#6e655c;--vonal:#e2d9cc;--jel:#5a1828;--kartya:#fff;--piros:#a3261f;--zold:#2c6e3f}
@media(prefers-color-scheme:dark){:root{--h:#1b1716;--sz:#ece4d9;--halk:#a2978b;--vonal:#3a322e;--jel:#e0909e;--kartya:#241f1d;--piros:#ef8f86;--zold:#8fce9f}}
*{box-sizing:border-box}body{margin:0;background:var(--h);color:var(--sz);font:15px/1.55 -apple-system,"SF Pro Text",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 20px 80px}h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:44px 0 6px;padding-top:14px;border-top:1px solid var(--vonal)}
h3{font-size:15px;margin:24px 0 8px;color:var(--jel)}p.le{color:var(--halk);margin:2px 0 14px;max-width:80ch}
nav{position:sticky;top:0;background:var(--h);border-bottom:1px solid var(--vonal);padding:8px 20px;display:flex;gap:16px;flex-wrap:wrap;font-size:13px;z-index:2}
nav a{color:var(--jel);text-decoration:none}table{border-collapse:collapse;width:100%;font-size:14px}
td,th{border-bottom:1px solid var(--vonal);padding:7px 8px;text-align:left;vertical-align:top}th{color:var(--halk);font-weight:500;font-size:12px}
.t{overflow-x:auto}code{font:12px ui-monospace,Menlo,monospace;color:var(--halk);word-break:break-all}
img.k{max-width:340px;max-height:120px;border:1px solid var(--vonal);border-radius:4px;background:#fff}
.b{color:var(--piros);font-size:12px}.ok{color:var(--zold)}.hib{background:color-mix(in srgb,var(--piros) 14%,transparent)}
.kartya{background:var(--kartya);border:1px solid var(--vonal);border-radius:8px;padding:12px 14px;margin:10px 0}
.kis{font-size:12px;color:var(--halk)}ol{margin:6px 0;padding-left:22px}details{margin:6px 0}summary{cursor:pointer;color:var(--jel)}
"""


def e(s) -> str:
    return html.escape(str(s), quote=True)


def keplet(latex: str) -> str:
    return f'<span class="tex" data-tex="{e(latex)}"></span>'


def _modul(nev: str):
    spec = importlib.util.spec_from_file_location(f"attekinto_{nev}", ITT / nev / "feladat.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _allapot(a: dict) -> str:
    return f'<span class="kis">verzió: {e(A.verzio(a))} · készült: {e(a.get("keszult"))}</span>'


def resz_fuzet(cfg, ki: Path) -> str:
    a = A.betolt(ITT / "ocr_kezi")
    plafon = _modul("ocr_kezi").plafon()
    sorok = "".join(f"<tr><td>{e(f['foto'])}</td><td>{e(f['leiras'])}</td><td>{e(f['helyes'][0])}"
                    f"{'<br><span class=kis>+' + str(len(f['helyes']) - 1 + len(f.get('elfogadhato_utolag', []))) + ' további elfogadott</span>' if len(f['helyes']) > 1 or f.get('elfogadhato_utolag') else ''}</td></tr>"
                    for f in a["fotok"])
    return (f'<h2 id="fuzet">1. Füzetfotók: kötési arany (97 fotó)</h2>{_allapot(a)}'
            '<p class="le">A legacy kézzel olvasott halmaza változatlanul. Két feladat használja: <b>ocr_kezi</b> '
            '(átirat → lexikai bíró) és <b>fuzet_fejezet</b> (zárt fejezetlista). A bíró plafonja a kézi leírásokon: '
            f'<b>{plafon["szam"]["jegyzet5"]}/97</b> a helyes jegyzet az első ötben, {plafon["szam"]["fejezet1"]}/97 az első '
            'találat fejezete.</p>'
            f'<details><summary>A 97 fotó listája</summary><div class="t"><table><tr><th>Fotó</th><th>Kézi leírás</th>'
            f'<th>Fő jegyzet</th></tr>{sorok}</table></div></details>')


def resz_keplet(cfg, ki: Path) -> str:
    a = A.betolt(ITT / "ocr_keplet")
    mappa = cfg.path("vault") / a["fotomappa"]
    kepek = ki / "kepletek"
    ki_html = [f'<h2 id="keplet">2. Képletek kézi LaTeX-átirata (20 fotó)</h2>{_allapot(a)}'
               f'<p class="le"><b>{len(a["kepletek"])}</b> biztos olvasatú képlet kerül a pontozott halmazba; '
               f'<b>{len(a["bizonytalan"])}</b> bizonytalan (piros) külön listán áll, pontozás nélkül. Az átirat azt adja, '
               'ami a papíron áll (a diák hibái megmaradnak). Kérlek, a zöld sorokat nézd át: ha a renderelt képlet '
               'eltér a kivágástól, írd meg a tétel azonosítóját; a pirosak közül azt jelezd, amelyiket biztosnak látod.</p>']
    fotok: dict[str, list] = {}
    for fajta in ("kepletek", "bizonytalan"):
        for k in a[fajta]:
            fotok.setdefault(k["foto"], []).append((fajta == "kepletek", k))
    for foto, tetelek in sorted(fotok.items()):
        ki_html.append(f'<h3>{e(foto)} — {sum(1 for b, _ in tetelek if b)} biztos, {sum(1 for b, _ in tetelek if not b)} bizonytalan</h3>'
                       '<div class="t"><table><tr><th>Azonosító</th><th>Kivágás</th><th>Renderelve</th><th>LaTeX</th></tr>')
        for biztos, k in sorted(tetelek, key=lambda t: t[1]["id"]):
            f = kep.kivag(mappa / foto, k["doboz"], kepek / f"{k['id']}.jpg", 700, float(a["szegely"]))
            megj = f'<br><span class="b">{e(k["megjegyzes"])}</span>' if k.get("megjegyzes") else ""
            ki_html.append(f'<tr><td class="{"ok" if biztos else "b"}">{e(k["id"][4:])}<br>{"biztos" if biztos else "bizonytalan"}</td>'
                           f'<td><img class="k" loading="lazy" src="kepletek/{e(f.name)}"></td><td>{keplet(k["latex"])}</td>'
                           f'<td><code>{e(k["latex"])}</code>{megj}</td></tr>')
        ki_html.append("</table></div>")
    return "".join(ki_html)


def _vart(v: dict) -> str:
    t = v["tipus"]
    if t == "halmaz":
        return "{" + "; ".join(v["ertekek"]) + "}" if v["ertekek"] else "nincs megoldás"
    if t == "par":
        return "; ".join(f"{k} = {x}" for k, x in v["ertekek"].items())
    return str(v["ertek"]) + (f" (tűrés: {v['tures']})" if v.get("tures") else "")


def resz_matek(cfg, ki: Path) -> str:
    a = A.betolt(ITT / "matek")
    ki_html = [f'<h2 id="matek">3. Matek: 40 feladat, 10 lépéses megoldás, 10 hibás levezetés</h2>{_allapot(a)}'
               '<p class="le">A végeredményeket sympy újraszámolta. Az érettségi feladatok saját szavakkal újrafogalmazva '
               'állnak, a forrás megjelölésével. A hibás levezetésekben a beültetett hiba sora pirossal jelölt.</p>'
               '<div class="t"><table><tr><th>Az.</th><th>Téma</th><th>Feladat</th><th>Várt eredmény</th><th>Forrás</th></tr>']
    for f in a["feladatok"]:
        ki_html.append(f'<tr><td>{e(f["id"])}{"<br><span class=kis>lépéses</span>" if f.get("lepesek") else ""}</td><td>{e(f["tema"])}</td>'
                       f'<td class="szoveg">{e(f["szoveg"])}</td><td><code>{e(_vart(f["vart"]))}</code></td><td class="kis">{e(f["forras"])}</td></tr>')
    ki_html.append("</table></div><h3>Lépéses megoldások (a levezetés-ellenőrzés helyes kontrolljai)</h3>")
    for f in a["feladatok"]:
        if f.get("lepesek"):
            ki_html.append(f'<div class="kartya"><b>{e(f["id"])}</b> <span class="szoveg">{e(f["szoveg"])}</span><ol>'
                           + "".join(f"<li>{keplet(s['latex'])}</li>" for s in f["lepesek"]) + "</ol></div>")
    ki_html.append("<h3>Hibás levezetések</h3>")
    for h in a["levezetesek"]:
        ki_html.append(f'<div class="kartya"><b>{e(h["id"])}</b> · alap: {e(h["alap"])} · hiba: <b>{e(h["hiba"])}</b> a(z) '
                       f'{h["hibas_sor"]}. sorban<ol>'
                       + "".join(f'<li class="{"hib" if i == h["hibas_sor"] else ""}">{keplet(s["latex"])}</li>'
                                 for i, s in enumerate(h["sorok"], 1))
                       + f'</ol><span class="kis">{e(h.get("magyarazat", ""))}</span></div>')
    return "".join(ki_html)


def resz_grafikon(cfg, ki: Path) -> str:
    a = A.betolt(ITT / "grafikon")
    sorok = "".join(
        f'<tr><td>{e(k["id"])}</td><td>{keplet(k["keplet"])}</td><td><code>{e(k["vart"]["kifejezes"])}</code></td>'
        f'<td>{e(k["vart"]["ablak"])}</td><td>{e(", ".join(k["vart"]["zerushelyek"]) or "–")}</td>'
        f'<td>{e("; ".join(f"({s["x"]}; {s["y"]}) {s["tipus"]}" for s in k["vart"]["szelsoertekek"]) or "–")}</td>'
        f'<td>{e(", ".join(k["vart"]["aszimptotak"]) or "–")}</td><td class="kis">{e(k["forras"])}</td></tr>'
        for k in a["kepletek"])
    return (f'<h2 id="grafikon">4. Grafikon: 15 képlet (C35)</h2>{_allapot(a)}'
            '<p class="le">A nevezetes pontok az ablakon belül értendők; szélsőértéknek a belső pont és a töréspont számít.</p>'
            '<div class="t"><table><tr><th>Az.</th><th>Képlet</th><th>Kifejezés</th><th>Ablak</th><th>Zérushelyek</th>'
            f'<th>Szélsőértékek</th><th>Aszimptoták</th><th>Forrás</th></tr>{sorok}</table></div>')


def resz_szoveg(cfg, ki: Path) -> str:
    a = A.betolt(ITT / "szoveg")
    ki_html = [f'<h2 id="szoveg">5. Összefoglalás és kártya: 20 jegyzet</h2>{_allapot(a)}'
               '<p class="le">Jegyzetenként a <b>kulcsrészek</b> (amelyek nélkül az összefoglalás hiányos) és a '
               '<b>kártyázható tények</b> (a forrásmondatukkal). Minden idézet géppel ellenőrzötten megvan a forrásban. '
               'Azt nézd: hiányzik-e fontos kulcsrész, és van-e gyenge vagy kétes tény.</p>']
    for j in a["jegyzetek"]:
        ki_html.append(f'<details><summary><b>{e(j["id"])}</b> · {e(j["cim"])} <span class="kis">({e(j["ut"].split("/")[0])}; '
                       f'{len(j["kulcsreszek"])} kulcsrész, {len(j["tenyek"])} tény)</span></summary><div class="kartya"><b>Kulcsrészek</b><ol>'
                       + "".join(f'<li>{e(k["megnevezes"])}<br><span class="kis">„{e(k["idezet"])}”</span></li>' for k in j["kulcsreszek"])
                       + "</ol><b>Kártyázható tények</b><ol>"
                       + "".join(f'<li>{e(t["teny"])}<br><span class="kis">„{e(t["forras"])}”</span></li>' for t in j["tenyek"])
                       + "</ol></div></details>")
    return "".join(ki_html)


def resz_kviz(cfg, ki: Path) -> str:
    a = A.betolt(ITT / "kviz")
    ki_html = [f'<h2 id="kviz">8. Kvíz: 20 jegyzet, jegyzetenként egy 5 kérdéses darab (C22m)</h2>{_allapot(a)}'
               '<p class="le">A halmaz a Szöveg-rész jegyzeteire épül: jegyzetenként az a darab, amelyben a legtöbb kártyázható '
               'tény forrásmondata áll; a pontozó a kérdések átmenő arányát (0,6) és e tények lefedettségét (0,4) méri. '
               'Azt nézd: a darabba eső tények értelmes kérdésekre adnak-e alapot, és nem marad-e ki fontos rész. A '
               '„hihetetlen rossz válasz” és a „több helyes” szabály lexikai közelítés; a küszöbét a felülvizsgálat után '
               'erősítsd meg vagy módosítsd.</p>']
    for j in a["jegyzetek"]:
        d = j["darab"]
        ki_html.append(f'<details><summary><b>{e(j["id"])}</b> · {e(j["cim"])} <span class="kis">({d["index"] + 1}. darab a '
                       f'{d["darabok"]}-ból, {d["karakter"]} karakter, {len(j["tenyek"])} tény)</span></summary><div class="kartya">'
                       "<b>A darabba eső tények</b><ol>"
                       + "".join(f'<li>{e(t["teny"])}<br><span class="kis">„{e(t["forras"])}”</span></li>' for t in j["tenyek"])
                       + "</ol></div></details>")
    return "".join(ki_html)


def resz_kereses(cfg, ki: Path) -> str:
    a = A.betolt(ITT / "kereses", "parok.json")
    sorok = "".join(f'<tr><td>{e(p["id"])}</td><td>{e(p["tipus"])}</td><td>{e(p["kerdes"])}</td><td>{e(p["cel"])}'
                    f'<br><span class="kis">„{e(p["idezet"])}”</span></td></tr>' for p in a["parok"])
    return (f'<h2 id="kereses">6. Keresés: 50 kérdés–jegyzet pár</h2>{_allapot(a)}'
            '<p class="le">A kérdés nem tartalmazza a jegyzet címének szavait. Azt nézd: a kérdésre tényleg ez a jegyzet '
            'a jó válasz-e, és nincs-e másik jegyzet, amely ugyanúgy megfelelne.</p>'
            f'<div class="t"><table><tr><th>Az.</th><th>Típus</th><th>Kérdés</th><th>Céljegyzet és a választ adó rész</th></tr>{sorok}</table></div>')


def resz_atirat(cfg, ki: Path) -> str:
    a = A.betolt(ITT / "atirat")
    ki_html = [f'<h2 id="atirat">7. Átirat: 2 videó (kb. 10 perc)</h2>{_allapot(a)}'
               '<p class="le">Az elvárt szöveg a vault „— Átirat” jegyzetéből képződik (a kiadó szövege, a kiejtési betoldások '
               'nélkül). A gépi felirattal összevetve a legtöbb eltérés a gép hibája; az alábbi helyeket viszont csak a '
               'hang dönti el: ezeket kérlek, hallgasd meg. A mérés a C20 (Whisper-háttér) után futtatható.</p>']
    for v in a["videok"]:
        ki_html.append(f'<div class="kartya"><b>{e(v["id"])}</b> · {e(v["cim"])} <span class="kis">({v["szavak"]} szó)</span>'
                       '<br><b>Meghallgatandó</b><ol>'
                       + "".join(f'<li><b>{e(m["ido"])}</b> — {e(m["kerdes"])}</li>' for m in v.get("meghallgatando", []))
                       + "</ol><b>Javasolt javítások</b><ol>"
                       + ("".join(f'<li>„{e(j["mit"])}” → „{e(j["mire"])}” <span class="kis">({e(j.get("indok", ""))})</span></li>'
                                  for j in v.get("javitasok", [])) or "<li>nincs</li>") + "</ol></div>")
    ki_html.append('<p class="kis">Azonosnak vett írásmódok: '
                   + "; ".join(f"{e(x)} = {e(y)}" for x, y in a.get("egyenertek", [])) + "</p>")
    return "".join(ki_html)


RESZEK = (("fuzet", "Füzetfotók", resz_fuzet), ("keplet", "Képletek", resz_keplet), ("matek", "Matek", resz_matek),
          ("grafikon", "Grafikon", resz_grafikon), ("szoveg", "Szöveg", resz_szoveg), ("kereses", "Keresés", resz_kereses),
          ("atirat", "Átirat", resz_atirat), ("kviz", "Kvíz", resz_kviz))

SZKRIPT = """
document.querySelectorAll('.tex').forEach(function(el){try{katex.render(el.dataset.tex,el,{throwOnError:false,displayMode:false});}
catch(x){el.textContent=el.dataset.tex;}});
renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],
ignoredClasses:['tex'],throwOnError:false});
"""


def epit(cfg) -> Path:
    ki = cfg.path("tmp") / "c18-attekinto"
    ki.mkdir(parents=True, exist_ok=True)
    katex = Path(cfg.expand("{os}")) / "app" / "node_modules" / "katex" / "dist"
    for nev in ("katex.min.js", "katex.min.css"):
        shutil.copy(katex / nev, ki / nev)
    shutil.copy(katex / "contrib" / "auto-render.min.js", ki / "auto-render.min.js")
    shutil.copytree(katex / "fonts", ki / "fonts", dirs_exist_ok=True)
    torzs = "".join(f(cfg, ki) for _, _, f in RESZEK)
    nav = "".join(f'<a href="#{a}">{e(n)}</a>' for a, n, _ in RESZEK)
    oldal = (f'<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
             f'initial-scale=1"><title>C18 aranyhalmazok</title><link rel="stylesheet" href="katex.min.css"><style>{CSS}</style>'
             f'</head><body><nav>{nav}</nav><main><h1>C18 — aranyhalmazok, jóváhagyásra</h1>'
             '<p class="le">Nyolc halmaz vázlata. Ami rendben van, arra elég egy „jóváhagyom”; a javítandót a tétel '
             f'azonosítójával jelezd a chatben.</p>{torzs}</main><script src="katex.min.js"></script>'
             f'<script src="auto-render.min.js"></script><script>{SZKRIPT}</script></body></html>')
    (ki / "index.html").write_text(oldal, encoding="utf-8")
    return ki / "index.html"


if __name__ == "__main__":
    from core import config
    print(epit(config.load()))
