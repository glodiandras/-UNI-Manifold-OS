"""A kártya-lánc mérése a C18 kártya-aranyhalmazán (C23b „Kész, ha”: a kapuk utáni pontosság; `docs/C18-ARANYHALMAZOK.md`).

    python -m modulok.kartya.meres --modell qwen35_4b [--keret munka] [--ki <jelentés.json>] [--limit N]

A `szoveg` aranyhalmaz 20 fagyasztott jegyzetén (`modulok/eval/szoveg/forrasok/jNN.md`) az **éles lánc** fut
(`generalas.general`: ugyanaz a prompt, mennyiség és kapuk, mint a „Kártyák ebből”-ben) a workeren át, a `szoveg` router-feladat
kérés-beállításával (`core.modell.eval.keres_beallitas`), `auto` módban; a vaultba és a `tanulas.sqlite`-ba semmi nem ír.

A pontozás a C18 kártya-definíciójának négy lexikai kapuja (`modulok/eval/szoveg/feladat._kartya_kapuk`: kötött, igaz, atomi,
egyértelmű) — **kapuk előtt** (a modell minden jelöltje) és **kapuk után** (a lánc által elfogadott kártyák, a forrásuk a jegyzet
talált mondata); a lefedettség az arany tényeihez. Figyelem: a lánc kapui és a pontozó kapui részben azonos elvűek (lexikai), ezért a
„kapuk utáni” pontosság nem független bírálat — a független próba a kézi minta (a jelentés `minta` mezője).
Folytatható: a már mért (modell, jegyzet) pár a jelentésből jön.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from core import config

from . import generalas as G


def _arany():
    from modulok.eval.szoveg import feladat as SZ
    return SZ


def hivo_kesz(cfg, u: str, modell: str, statisztika: dict):
    from core.modell import beallitas as B
    from core.modell import eval as E
    from core.modell import kliens
    b = B.betolt(cfg)

    def hiv(prompt: str, max_tokens: int) -> str:
        k = E.keres_beallitas(b, b.modell(modell), "szoveg",
                              {"tipus": "chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens})
        uzenetek = k.pop("messages")
        k.pop("tipus", None)
        t0 = time.time()
        r = kliens.chat(u, uzenetek, feladat="szoveg", modell=modell, mod="auto", **k)
        statisztika["mp"] = statisztika.get("mp", 0.0) + time.time() - t0
        statisztika["hivas"] = statisztika.get("hivas", 0) + 1
        return r["choices"][0]["message"]["content"]
    return hiv


def pontoz(jid: str, kartyak: list[dict]) -> dict:
    """A kártyák a C18 négy kapuján: → {n, jo, minoseg, lefedettseg, bukas, hibak}."""
    SZ = _arany()
    f = SZ.forras(jid)
    tenyek = [f.keres(t["forras"])["szo"] for t in SZ.jegyzet(jid)["tenyek"]]
    elozok: list = []
    jo, bukas, hibak = [], {"kotott": 0, "igaz": 0, "atomi": 0, "egyertelmu": 0}, []
    for k in kartyak:
        kapu, t = SZ._kartya_kapuk(f, k, elozok)
        if all(kapu.values()):
            jo.append(t["szo"])
        else:
            rossz = [n for n, v in kapu.items() if not v]
            for n in rossz:
                bukas[n] += 1
            hibak.append({"kerdes": k["kerdes"], "kapu": rossz})
    n = len(kartyak)
    lef = sum(1 for t in tenyek if t and any(SZ._er(j, t) for j in jo)) / len(tenyek) if tenyek else 0.0
    return {"n": n, "jo": len(jo), "minoseg": len(jo) / n if n else 0.0, "lefedettseg": lef, "bukas": bukas, "hibak": hibak}


def mer_jegyzet(jid: str, hivo, b: G.Beallitas) -> dict:
    SZ = _arany()
    md = SZ.forras_szoveg(jid)
    n = G.mennyiseg(md, b)
    e = G.general(md, jid, hivo, hivo, max(n, 1), b=b, p=G.profil(config.load()))
    elott = [{"kerdes": k.kerdes, "valasz": k.valasz, "forras": k.idezet} for k in e.kartyak] + \
            [{"kerdes": x["kerdes"], "valasz": x["valasz"], "forras": x.get("forras", "")} for x in e.elvetett]
    utan = [{"kerdes": k.kerdes, "valasz": k.valasz, "forras": k.idezet} for k in e.kartyak]
    return {"jegyzet": jid, "kert": n, "statisztika": e.statisztika, "elott": pontoz(jid, elott), "utan": pontoz(jid, utan),
            "kartyak": [{"kerdes": k.kerdes, "valasz": k.valasz, "forras_mondat": k.forras_mondat} for k in e.kartyak],
            "elvetett": [{"kerdes": x["kerdes"], "ok": x["ok"]} for x in e.elvetett]}


def osszegez(sorok: list[dict]) -> dict:
    def atl(kulcs, resz):
        xs = [s[resz][kulcs] for s in sorok if s[resz]["n"]]
        return round(sum(xs) / len(xs), 4) if xs else None
    ossz_e = sum(s["elott"]["n"] for s in sorok)
    ossz_u = sum(s["utan"]["n"] for s in sorok)
    jo_e = sum(s["elott"]["jo"] for s in sorok)
    jo_u = sum(s["utan"]["jo"] for s in sorok)
    elvetve: dict[str, int] = {}
    for s in sorok:
        for k, v in s["statisztika"].get("elvetve", {}).items():
            elvetve[k] = elvetve.get(k, 0) + v
    lef = [s["utan"]["lefedettseg"] for s in sorok]
    return {"jegyzet": len(sorok), "jelolt": ossz_e, "elfogadott": ossz_u,
            "pontossag_kapuk_elott": round(jo_e / ossz_e, 4) if ossz_e else None,
            "pontossag_kapuk_utan": round(jo_u / ossz_u, 4) if ossz_u else None,
            "lefedettseg": round(sum(lef) / len(lef), 4) if lef else None,
            "pont_utan": round(0.6 * (jo_u / ossz_u if ossz_u else 0) + 0.4 * (sum(lef) / len(lef) if lef else 0), 4),
            "minoseg_jegyzetatlag_utan": atl("minoseg", "utan"), "elvetve": dict(sorted(elvetve.items(), key=lambda x: -x[1]))}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="kartya-meres")
    ap.add_argument("--modell", required=True)
    ap.add_argument("--keret", default=None, help="munka | tavol (saját worker a keret-felülírással)")
    ap.add_argument("--ki", required=True)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    cfg = config.load()
    from core.modell import beallitas as B
    from core.modell import kliens
    b = B.betolt(cfg)
    b.modell(a.modell)
    ki = Path(a.ki)
    adat = json.loads(ki.read_text(encoding="utf-8")) if ki.exists() else {}
    sorok = adat.get(a.modell, {}).get("sorok", [])
    kesz = {s["jegyzet"] for s in sorok}
    jidk = [j["id"] for j in _arany().ARANY["jegyzetek"]][:a.limit]
    env = {"MANIFOLD_MODELL_KERET_GB": f"{b.keret_gb(a.keret):g}"} if a.keret else None
    folyamat = kliens.Folyamat(cfg, env=env, sajat=bool(a.keret))
    stat: dict = {}
    try:
        u = folyamat.biztosit(timeout=600)
        hivo = hivo_kesz(cfg, u, a.modell, stat)
        gb = G.beallitas(cfg)
        for jid in jidk:
            if jid in kesz:
                continue
            t0 = time.time()
            try:
                s = mer_jegyzet(jid, hivo, gb)
            except G.Megall as exc:
                s = {"jegyzet": jid, "hiba": str(exc), "kert": 0, "statisztika": {}, "kartyak": [], "elvetett": [],
                     "elott": pontoz(jid, []), "utan": pontoz(jid, [])}
            s["mp"] = round(time.time() - t0, 1)
            sorok.append(s)
            adat[a.modell] = {"sorok": sorok, "osszegzes": osszegez(sorok), "prompt_verzio": G.PROMPT_VERZIO}
            tmp = ki.with_name(ki.name + ".tmp")
            tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, ki)
            print(f"[kártya-mérés] {a.modell} {jid}: {s['utan']['jo']}/{s['utan']['n']} jó a kapuk után "
                  f"({s['elott']['jo']}/{s['elott']['n']} előtte) · {s['mp']} s", flush=True)
    finally:
        folyamat.leallit()
    print(json.dumps(adat.get(a.modell, {}).get("osszegzes"), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
