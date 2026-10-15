"""A felkészültség javaslat-forrása a C29 horgán (C28a; D12): a napi terv napjaiból tanulásiblokk-javaslat.

A forrás **csak `Javaslat` objektumokat ad** — a naptárba a jóváhagyott `esemeny-ir` út ír, más nem (`naptar_javaslat`).
Ha a vault indexe nem áll rendelkezésre (a `ctx.index` hiányzik vagy még épül), a forrás üres, és a beépített `alap`
forrás dolgozik; ha a forrás javasol egy dolgozatra, a beépített arra a dolgozatra elnémul (`Javaslatok.frissit`).
A javasolt blokk a dolgozat napi tervének egy napja: a hossza a nap percei (legalább 30), a sávot a meglévő
`szabad_sav` adja a naptár időzített eseményeit kikerülve; ahol a tantárgyhoz már van tanulási blokk, ott nincs javaslat.
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from .. import naptar_javaslat
from ..naptar_javaslat import Javaslat
from . import osszesit
from .adat import Adatok, Hiany

NEV = "felkeszultseg"
MIN_PERC = 30
CIM_TEMA_MAX = 3


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _indok(d: dict, e: dict, b) -> str:
    gyenge = [f"{t['nev']} ({_pct(t['szam'])})" for t in sorted((t for t in e["temak"] if t["szam"] is not None and t["szam"] < b.gyenge),
                                                               key=lambda t: t["szam"])]
    nincs = [t["nev"] for t in e["temak"] if t["szam"] is None]
    szoveg = [f"{d['cim']} {d['nap']}-án ({d['napok']} nap múlva): felkészültség "
              + (_pct(e["szam"]) if e["szam"] is not None else "nincs adat")
              + f", {e['lefedettseg']['van']} / {e['lefedettseg']['osszes']} témára van mért adat."]
    if gyenge:
        szoveg.append("Gyenge: " + ", ".join(gyenge) + ".")
    if nincs:
        szoveg.append("Nincs adat: " + ", ".join(nincs) + ".")
    return " ".join(szoveg)


def felkeszultseg_forras(ctx: SimpleNamespace) -> list[Javaslat]:
    if getattr(ctx, "index", None) is None:
        return []
    a = Adatok(ctx.cfg, ctx.index, ctx.most)
    if not a.index_kesz():
        return []
    b = ctx.beallitasok
    foglalt = naptar_javaslat._foglalt(ctx.esemenyek)
    tanulasok = [x for x in ctx.esemenyek if x.get("kategoria") == "tanulas" and not x.get("egesznap")]
    ki: list[Javaslat] = []
    try:
        dolgozatok = a.dolgozatok()
    except Hiany:
        return []
    for d in dolgozatok:
        if d["lezart"] or d["napok"] <= 0 or d["napok"] > b["elorenezes_nap"] or d["kotes"] is None:
            continue
        e = osszesit.ertekel(a, d)
        terv = osszesit.terv_szamolas(a, d, e)
        tantargy = d["tantargy"]
        for nap in terv.napok:
            if not nap.szeletek or any(
                    (t.get("nap") or t.get("kezd") or "")[:10] == nap.nap and (not d["targyak"] or set(t.get("targyak") or ()) & set(d["targyak"]))
                    for t in tanulasok):
                continue
            perc = nap.perc  # a közös keret kiosztott szeletét nem növeljük meg
            sav = naptar_javaslat.szabad_sav(date.fromisoformat(nap.nap), foglalt, {**b, "perc": perc}, ctx.most)
            if sav is None:
                continue
            veg = sav + timedelta(minutes=perc)
            nevek = [s.tema for s in nap.szeletek if s.tema_ut]
            tema = ", ".join(nevek[:CIM_TEMA_MAX]) + ("…" if len(nevek) > CIM_TEMA_MAX else "")
            cim = f"Tanulás: {tantargy} — {tema}" if tantargy else f"Tanulás: {d['cim']} — {tema}"
            ki.append(Javaslat(forras=NEV, azon=f"{d['azon']}|{nap.nap}", nap=nap.nap, kezd=sav.isoformat(timespec="seconds"),
                               veg=veg.isoformat(timespec="seconds"), perc=perc, cim=cim, tantargy=tantargy, tema=tema or None,
                               indok=_indok(d, e, a.b), dolgozat=d["azon"]))
            foglalt.append((sav, veg))                    # a következő nap / dolgozat javaslata ne ugyanabba a sávba kerüljön
    return sorted(ki, key=lambda j: (j.nap, j.azon))


naptar_javaslat.regisztral_forras(NEV, felkeszultseg_forras)
