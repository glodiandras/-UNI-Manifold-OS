"""Az összefoglaló-lánc mérése a C18 `szoveg` aranyhalmazán (C26b „Kész, ha”: a kapuk utáni hűség és lefedettség; `docs/C26-TERV.md` 4., 9.).

    bin/mos osszefoglalas meres --modell qwen35_4b [--keret munka] --ki <jelentés.json> [--limit N]

A `szoveg` aranyhalmaz 20 fagyasztott jegyzetén (`modulok/eval/szoveg/forrasok/jNN.md`) az **éles lánc** fut (`lanc.osszefoglal`:
ugyanaz a darabolás, prompt — `promptok.darab_prompt` —, kérés-beállítás és kapuk, mint a „Összefoglalás” parancsban) a workeren át, a
`szoveg` router-feladat kérés-beállításával (`core.modell.eval.keres_beallitas`), `auto` módban; a vaultba és az adatbázisokba semmi nem ír.

A pontozás a C18 összefoglalás-definíciója (`modulok/eval/szoveg/feladat.pontoz_ossz`: idézet-hűség, alátámasztás, lefedettség; pont =
0,4 · hűség + 0,2 · alátámasztás + 0,4 · lefedettség) két helyen:

- **kapuk előtt**: a modell minden jelöltje, a modell *saját* idézetével (ez az, amit a C19 `szoveg`-kalibrációja a teljes jegyzet
  promptján mért, darabokra bontva);
- **kapuk után**: a lánc által elfogadott állítások, idézetként a *jegyzet* mondatával (az összefoglalóban megjelenő forma).

Figyelem: a lánc kapui és a pontozó részben azonos elvűek (lexikai), ezért a „kapuk utáni” szám nem független bírálat — a független
próba a rétegzett kézi minta (a jelentés `minta` mezője: jegyzetenként a legelső és a legutolsó elfogadott állítás, K-tétel). A
`nem_keszult` jegyzet (a kapuk után kevesebb, mint `allitas_min` állítás) 0 ponttal szerepel az átlagban, és külön is látszik.
Folytatható: a már mért (modell, jegyzet) pár a jelentésből jön.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from core import config
from core.index import elemzo

from . import formatum as FM
from . import lanc as L
from .promptok import PROMPT_VERZIO


def _arany():
    from modulok.eval.szoveg import feladat as SZ
    return SZ


def _pontoz(jid: str, allitasok: list[dict]) -> dict:
    SZ = _arany()
    if not allitasok:
        return {"pont": 0.0, "huseg": 0.0, "alatamasztas": 0.0, "lefedettseg": 0.0, "allitasok": 0, "hibak": []}
    return SZ.pontoz_ossz(jid, json.dumps(allitasok, ensure_ascii=False))


def mer_jegyzet(jid: str, hivo, gb: L.Beallitas, p) -> dict:
    SZ = _arany()
    md = SZ.forras_szoveg(jid)
    t = elemzo.elemez(md)
    from . import szakaszolas
    bem = szakaszolas.jegyzet_bemenet(md, jid, jid, t.fejezetek, t.blokkok, gb.darab_max_karakter, gb.szakasz_min_karakter)
    valaszok: list[str] = []

    def rogzito(prompt: str, max_tokens: int) -> str:
        v = hivo(prompt, max_tokens)
        valaszok.append(v)
        return v

    jeloltek = lambda: [{"allitas": j.allitas, "idezet": j.idezet} for v in valaszok for j in L.jeloltek(v)]    # noqa: E731
    try:
        e = L.osszefoglal(bem, rogzito, "meres", jid, forrasok=[jid], b=gb, p=p)
    except L.Megall as exc:
        return {"jegyzet": jid, "nem_keszult": str(exc)[:300], "darab": len(bem.darabok), "elott": _pontoz(jid, jeloltek()),
                "utan": _pontoz(jid, []), "allitasok": [], "elvetett": []}
    utan = [{"allitas": a.szoveg, "idezet": a.idezet} for a in e.osszefoglalo.allitasok]
    return {"jegyzet": jid, "darab": len(bem.darabok), "statisztika": e.statisztika, "elott": _pontoz(jid, jeloltek()),
            "utan": _pontoz(jid, utan), "allitasok": [{"allitas": a.szoveg, "idezet": a.idezet, "horgony": a.horgony.link()}
                                                      for a in e.osszefoglalo.allitasok],
            "elvetett": [{"allitas": x["allitas"], "ok": x["ok"]} for x in e.elvetett]}


def minta(sorok: list[dict]) -> list[dict]:
    """A rétegzett kézi minta: jegyzetenként a legelső és a legutolsó elfogadott állítás (a független bírálathoz; `jo`: kitöltendő)."""
    ki = []
    for s in sorok:
        al = s.get("allitasok") or []
        for a in ([al[0], al[-1]] if len(al) > 1 else al):
            ki.append({"jegyzet": s["jegyzet"], "allitas": a["allitas"], "idezet": a["idezet"], "jo": None})
    return ki


def osszegez(sorok: list[dict]) -> dict:
    def atl(resz, kulcs, csak_kesz=False):
        xs = [s[resz][kulcs] for s in sorok if not (csak_kesz and s.get("nem_keszult"))]
        return round(sum(xs) / len(xs), 4) if xs else None
    elvetve: dict[str, int] = {}
    for s in sorok:
        for k, v in (s.get("statisztika") or {}).get("elvetve", {}).items():
            elvetve[k] = elvetve.get(k, 0) + v
    ossz_jelolt = sum((s.get("statisztika") or {}).get("jelolt", 0) for s in sorok)
    ossz_elfog = sum(len(s.get("allitasok") or []) for s in sorok)
    return {"jegyzet": len(sorok), "nem_keszult": sum(1 for s in sorok if s.get("nem_keszult")),
            "jelolt": ossz_jelolt, "elfogadott": ossz_elfog,
            "pont_kapuk_elott": atl("elott", "pont"), "pont_kapuk_utan": atl("utan", "pont"),
            "pont_kapuk_utan_csak_elkeszult": atl("utan", "pont", True),
            "huseg_utan": atl("utan", "huseg", True), "alatamasztas_utan": atl("utan", "alatamasztas", True),
            "lefedettseg_elott": atl("elott", "lefedettseg"), "lefedettseg_utan": atl("utan", "lefedettseg"),
            "huseg_elott": atl("elott", "huseg"), "alatamasztas_elott": atl("elott", "alatamasztas"),
            "elvetve": dict(sorted(elvetve.items(), key=lambda x: -x[1])), "prompt_verzio": PROMPT_VERZIO}


def main(a) -> int:
    cfg = config.load()
    from core.modell import beallitas as B
    from core.modell import kliens

    from modulok.kartya.meres import hivo_kesz
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
    gb, p = L.beallitas(cfg), L.profil(cfg)
    try:
        u = folyamat.biztosit(timeout=600)
        hivo = hivo_kesz(cfg, u, a.modell, stat)
        for jid in jidk:
            if jid in kesz:
                continue
            t0 = time.time()
            s = mer_jegyzet(jid, hivo, gb, p)
            s["mp"] = round(time.time() - t0, 1)
            sorok.append(s)
            adat[a.modell] = {"sorok": sorok, "osszegzes": osszegez(sorok), "minta": minta(sorok), "prompt_verzio": PROMPT_VERZIO,
                              "mp_modell": round(stat.get("mp", 0.0), 1), "hivas": stat.get("hivas", 0)}
            tmp = ki.with_name(ki.name + ".tmp")
            tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, ki)
            print(f"[összefoglaló-mérés] {a.modell} {jid}: kapuk után {s['utan']['pont']:.3f} ({len(s['allitasok'])} állítás"
                  f"{', NEM KÉSZÜLT EL' if s.get('nem_keszult') else ''}), előtte {s['elott']['pont']:.3f} · {s['mp']} s", flush=True)
    finally:
        folyamat.leallit()
    print(json.dumps(adat.get(a.modell, {}).get("osszegzes"), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="osszefoglalas-meres")
    ap.add_argument("--modell", required=True)
    ap.add_argument("--keret", default=None)
    ap.add_argument("--ki", required=True)
    ap.add_argument("--limit", type=int)
    raise SystemExit(main(ap.parse_args(sys.argv[1:])))
