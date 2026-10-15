"""A ```plot modell-ágának mérése (C35b; CHATKALAUZ C35b 3. pont; CLAUDE.md D9, 59(d), 72. javasolt döntés).

    bin/mos grafikon modell-meres --modell qwen35_4b [--keret munka|tavol] [--ki jelentes.json] [--limit N]

**Az éles blokk-író kérés fut**: ugyanaz a `modell_ag.prompt`/`javasol` (négy kapu), ugyanaz a kérés-beállítás
(`core.modell.eval.keres_beallitas`, a `grafikon` feladat), `auto` módban, a workeren át — nem a C18 JSON-kérés (azt a `mos eval
grafikon` méri). A vaultba és az állapottárakba semmi nem ír.

Két halmaz:
- **kényszerített** (a C18 `grafikon` aranyhalmaz 15 képlete): a felismerő mind a 15-öt `biztos`-ra ítéli, ezért a mérés a javaslatot
  `bizonytalan`-ra állítja, és a modell-ágnak kell blokkot adnia; a referencia a felismerő (a C35a-ban 15/15 helyes) kifejezése. A
  helyességet az aranyhalmaz `vart.kifejezes`-éhez mérjük (nem a felismerőhöz): az elfogadott blokk kifejezése egyezzen az arannyal.
- **természetes** (a C35a szintetikus halmazának „bizonytalan” függvényei: pólus, érintő, törtfüggvény, konstans): ahol a felismerő
  tényleg bizonytalan; a referencia a felismerő kifejezése.

Mérőszámok: `elfogadva` (átment a négy kapun), `referencia` (és a felismerő kifejezésével egyezik: élesben írható), `teves` (elfogadott,
de a kifejezése eltér az aranytól — **0 kell legyen**), `lefedes` (az elfogadott blokk x-ablaka tartalmazza az arany zérushelyeit és
szélsőérték-helyeit), `elvetve` okonként, a modellhibák és az idő. Folytatható: a már mért (halmaz, id) a jelentésből jön.
A „kész” feltétel (`kapu`): `teves == 0` és nincs `nem_ellenorizheto`; a kapcsoló (`[grafikon.automatika] modell_ag`) bekapcsolása a
koordinátor K-tétele a számok alapján.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import modell_ag as MA


def _arany() -> dict:
    from . import meres
    return meres._feladat_modul().ARANY


def _egyezik(kapott: str, vart: str) -> bool:
    from . import meres
    return meres._kif_szoveg_egyezik(kapott, vart)


def _lefedes(blokk: str, vart: dict) -> bool:
    from . import formatum as F
    from . import meres
    h = F.blokkok(blokk)
    if len(h) != 1 or h[0].abra.x_tartomany is None:
        return False
    import sympy as sp
    m = meres._matek
    lo, hi = (float(sp.N(m.elemez(x))) for x in h[0].abra.x_tartomany)
    helyek = list(vart.get("zerushelyek", [])) + [p["x"] for p in vart.get("szelsoertekek", [])]
    return all(lo <= float(sp.N(m.elemez(x))) <= hi for x in helyek)


def tetelek(felismer, limit: int | None = None) -> list[dict]:
    """A mérendő tételek: `{halmaz, id, javaslat, vart|None}`; a `felismer(keplet) → javaslat-szótár` hívható (homokozón át)."""
    from . import meres
    ki = []
    for k in _arany()["kepletek"]:
        j = felismer(k["keplet"])
        ki.append({"halmaz": "kenyszeritett", "id": k["id"], "javaslat": {**j, "bizonyossag": "bizonytalan"}, "vart": k["vart"]})
    for keplet, fajta, bizonyossag, _ in meres.KIEGESZITO:
        if bizonyossag != "bizonytalan" or fajta != "fuggveny":
            continue
        j = felismer(keplet)
        if j.get("bizonyossag") == "bizonytalan" and j.get("abra"):
            ki.append({"halmaz": "termeszetes", "id": keplet, "javaslat": j, "vart": None})
    return ki[:limit] if limit else ki


def mer_tetel(t: dict, hivo, homokozo=None) -> dict:
    """Egy tétel: a modell-ág `javasol`-ja és az értékelés. → szótár (JSON-ba írható)."""
    t0 = time.time()
    e = MA.javasol(t["javaslat"], hivo, homokozo=homokozo)
    s = {"halmaz": t["halmaz"], "id": t["id"], "allapot": e["allapot"], "egyeztetes": e["egyeztetes"], "ok": e["ok"],
         "blokk": e["blokk"], "mod": MA.iras_mod(e, True), "mp": round(time.time() - t0, 1)}
    if e["allapot"] == "elfogadva" and t["vart"] is not None:
        from . import formatum as F
        fv = [x.kifejezes for x in F.elemez(e["torzs"]).elemek if isinstance(x, (F.Fuggveny, F.Egyenlotlenseg))]
        s["helyes"] = len(fv) == 1 and _egyezik(fv[0], t["vart"]["kifejezes"])
        s["lefedes"] = _lefedes(e["blokk"], t["vart"])
    return s


def osszegez(sorok: list[dict]) -> dict:
    """A jelentés összegzése halmazonként és együtt; a `kapu`: 0 téves blokk és nincs ellenőrizhetetlen tétel."""
    def egy(xs: list[dict]) -> dict:
        n = len(xs)
        elf = [x for x in xs if x["allapot"] == "elfogadva"]
        ert = [x for x in elf if "helyes" in x]
        elvetve: dict[str, int] = {}
        for x in xs:
            if x["allapot"] in ("elvetve", "modell_hiba", "modell_var", "nem_ellenorizheto"):
                kulcs = x["allapot"] if x["allapot"] != "elvetve" else x["ok"][:70]
                elvetve[kulcs] = elvetve.get(kulcs, 0) + 1
        return {"n": n, "elfogadva": len(elf), "referencia": sum(1 for x in elf if x["egyeztetes"] == "referencia"),
                "eles_irhato": sum(1 for x in xs if x.get("mod") == "eles"),
                "teves": sum(1 for x in ert if not x["helyes"]), "ertekelt": len(ert),
                "lefedes": sum(1 for x in ert if x["helyes"] and x["lefedes"]),
                "nem_ellenorizheto": sum(1 for x in xs if x["allapot"] == "nem_ellenorizheto"),
                "modell_hiba": sum(1 for x in xs if x["allapot"] in ("modell_hiba", "modell_var")),
                "elvetve": dict(sorted(elvetve.items(), key=lambda t: -t[1])),
                "atlag_mp": round(sum(x["mp"] for x in xs) / n, 1) if n else None}
    ossz = egy(sorok)
    return {"osszes": ossz, **{h: egy([x for x in sorok if x["halmaz"] == h]) for h in ("kenyszeritett", "termeszetes")},
            "kapu": {"teves_0": ossz["teves"] == 0, "nincs_nem_ellenorizheto": ossz["nem_ellenorizheto"] == 0,
                     "van_ertekelt_tetel": ossz["ertekelt"] > 0}}


def hivo_kesz(cfg, u: str, modell: str, statisztika: dict):
    """Az éles kérés beállításával (a `grafikon` feladat mérés-beállítása), kifejezett modellel, `auto` módban."""
    from core.modell import beallitas as B
    from core.modell import eval as E
    from core.modell import kliens
    b = B.betolt(cfg)

    def hiv(prompt: str, max_tokens: int) -> str:
        k = E.keres_beallitas(b, b.modell(modell), "grafikon",
                              {"tipus": "chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens})
        uzenetek = k.pop("messages")
        k.pop("tipus", None)
        t0 = time.time()
        r = kliens.chat(u, uzenetek, feladat="grafikon", modell=modell, mod="auto", **k)
        statisztika["mp"] = statisztika.get("mp", 0.0) + time.time() - t0
        statisztika["hivas"] = statisztika.get("hivas", 0) + 1
        return r["choices"][0]["message"]["content"]
    return hiv


def main(argv: list[str], homokozo=None) -> int:
    ap = argparse.ArgumentParser(prog="grafikon modell-meres")
    ap.add_argument("--modell", required=True)
    ap.add_argument("--keret", default=None, help="munka | tavol (saját worker a keret-felülírással)")
    ap.add_argument("--ki", default=None, help="a jelentés JSON-ja (folytatható)")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    from core import config
    from core.modell import beallitas as B
    from core.modell import kliens
    from . import _homokozo, felismer
    cfg = config.load()
    b = B.betolt(cfg)
    b.modell(a.modell)
    hk = _homokozo(homokozo)
    ki = Path(a.ki) if a.ki else None
    adat = json.loads(ki.read_text(encoding="utf-8")) if ki and ki.exists() else {}
    sorok = adat.get(a.modell, {}).get("sorok", [])
    kesz = {(s["halmaz"], s["id"]) for s in sorok}
    env = {"MANIFOLD_MODELL_KERET_GB": f"{b.keret_gb(a.keret):g}"} if a.keret else None
    folyamat = kliens.Folyamat(cfg, env=env, sajat=bool(a.keret))
    stat: dict = {}
    try:
        u = folyamat.biztosit(timeout=600)
        hivo = hivo_kesz(cfg, u, a.modell, stat)
        for t in tetelek(lambda k: felismer(k, homokozo=hk), a.limit):
            if (t["halmaz"], t["id"]) in kesz:
                continue
            s = mer_tetel(t, hivo, hk)
            sorok.append(s)
            adat[a.modell] = {"sorok": sorok, "osszegzes": osszegez(sorok), "prompt_verzio": MA.PROMPT_VERZIO, "keret": a.keret}
            if ki:
                tmp = ki.with_name(ki.name + ".tmp")
                tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
                os.replace(tmp, ki)
            print(f"[grafikon modell-mérés] {a.modell} {t['halmaz']} {t['id']}: {s['allapot']}/{s['egyeztetes']}"
                  f"{'' if 'helyes' not in s else (' helyes' if s['helyes'] else ' TÉVES')} · {s['mp']} s", flush=True)
    finally:
        folyamat.leallit()
    ossz = adat.get(a.modell, {}).get("osszegzes")
    print(json.dumps(ossz, ensure_ascii=False, indent=1))
    return 0 if ossz and all(ossz["kapu"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
