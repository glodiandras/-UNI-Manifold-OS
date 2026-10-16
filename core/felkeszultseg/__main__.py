"""`bin/mos felkeszultseg …` — a felkészültség CLI-je (C28b). **Csak olvas** (a vaultot, a `tanulas.sqlite`-ot és a `pos.sqlite`-ot
nem módosítja), kivéve a `kalibral --rogzit`, amely az `os.toml` `[felkeszultseg]` szakaszát írja.

    bin/mos felkeszultseg eredmeny [--json]        a „Dolgozat kiértékelő” jegyzetek szakaszai és a belőlük kinyert eredmény (a kézi
                                                   összevetéshez: mit talált a kinyerő, mit zárt ki és miért); indexet nem épít
    bin/mos felkeszultseg kalibral [--datum D] [--json] [--rogzit]
                                                   az önkalibráció jelentése (pontok, hibák, javasolt súlyok); az index egy
                                                   ideiglenes mappába épül (a valódi `var/index` érintetlen); `--rogzit`: a
                                                   javasolt súlyok az `os.toml`-ba (csak `javasolt` állapotban)

A szöveges értékelés a felületről indul (`POST /api/felkeszultseg/ertekeles`): ahhoz a worker és a kalibrált modell kell.
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import sys
import tempfile
from datetime import datetime, time
from pathlib import Path

from .. import config, naplo
from . import eredmeny, kalibracio
from .adat import Adatok, Menet


def _kiertekelo_fajlok(cfg) -> list[str]:
    from .. import naptar
    nevek = [naptar.norm(x) for x in Menet.cfg_bol(cfg).kiertekelo_nevek]
    vault = Path(cfg.path("vault"))
    ki = []
    for dp, mappak, fajlok in os.walk(vault):
        mappak[:] = sorted(m for m in mappak if not m.startswith("."))
        for f in sorted(fajlok):
            if f.lower().endswith(".md") and any(n in naptar.norm(f) for n in nevek):
                ki.append(os.path.relpath(os.path.join(dp, f), vault))
    return ki


def eredmeny_parancs(cfg, args) -> int:
    vault = Path(cfg.path("vault"))
    ki = []
    for rp in _kiertekelo_fajlok(cfg):
        szoveg = (vault / rp).read_text(encoding="utf-8", errors="replace")
        for se in eredmeny.szakasz_eredmenyek(szoveg, rp):
            k = se.kinyeres
            ki.append({"fajl": rp, "sor": se.szakasz.sor, "cim": se.szakasz.cim, "link": se.szakasz.link, "eredmeny": k.eredmeny,
                       "ellentmondas": k.ellentmondas, "eredet": k.eredet,
                       "kizart": [{"forras": t.forras, "ok": t.ok} for t in k.talalatok if not t.elfogadva]})
    if args.json:
        print(json.dumps(ki, ensure_ascii=False, indent=2))
        return 0
    van = sum(1 for x in ki if x["eredmeny"])
    mezos = sum(1 for x in ki if x["eredet"] == "mezo")
    print(f"{len(ki)} szakasz, ebből {van} egyértelmű eredménnyel, {sum(1 for x in ki if x['ellentmondas'])} ellentmondó; "
          f"{mezos} szakaszban szabott „{eredmeny.MEZO_KULCS}::” mező")
    for x in ki:
        e = x["eredmeny"]
        allapot = (f"{e['forras']} → {e['szazalek']}%" if e else ("ELLENTMONDÁS: " + ", ".join(j["forras"] for j in x["ellentmondas"]["jeloltek"])
                                                                     if x["ellentmondas"] else "—"))
        jel = " (mező)" if x["eredet"] == "mezo" else ""
        print(f"{posixpath.basename(x['fajl'])}:{x['sor']}  {x['cim']}  [{x['link'] or 'nincs link'}]  {allapot}{jel}")
        for z in x["kizart"]:
            print(f"      kizárva: {z['forras']} — {z['ok']}")
    return 0


class _IdeiglenesIndex:
    """Az index egy ideiglenes mappába (a vaultot csak olvassa); a kilépéskor a saját ideiglenes mappa törlődik."""

    def __init__(self, cfg):
        self._tmp = tempfile.TemporaryDirectory(prefix="felkeszultseg-index-", dir=str(cfg.path("tmp")))
        env = dict(os.environ)
        env["MOS_INDEX"] = self._tmp.name
        self.cfg = config.load(env)
        from ..index import indexelo
        self.index = indexelo.Index(self.cfg)
        self.index.indit()
        if not self.index.var(300):
            raise RuntimeError("az index nem készült el időben")

    def zar(self):
        try:
            self.index.leallit()
        finally:
            self._tmp.cleanup()


def kalibral_parancs(cfg, args) -> int:
    Path(cfg.path("tmp")).mkdir(parents=True, exist_ok=True)
    nap = naplo.datum_ertek(args.datum) if args.datum else None
    most = datetime.combine(nap, time(12, 0)).astimezone() if args.datum else None
    vault = Path(cfg.path("vault"))
    ix = _IdeiglenesIndex(cfg)
    try:
        olvas = lambda rp: (vault / rp).read_text(encoding="utf-8")        # noqa: E731
        j = kalibracio.jelentes_adatbol(cfg, ix.index, olvas, most)
    finally:
        ix.zar()
    if args.json:
        print(json.dumps(j, ensure_ascii=False, indent=2))
    else:
        print(f"Állapot: {j['allapot']}")
        print(j["ok"])
        print(f"Pontok: {j['pontok']} / {j['kell']}  (lezárt dolgozat: {j.get('lezart')}, eredménnyel: {j.get('eredmennyel')})")
        a = j["alap"]
        if a.get("rmse") is not None:
            print(f"Az induló súlyok hibája: RMSE {a['rmse']}, MAE {a['mae']}, torzítás {a['torzitas']}" + ("  (kis minta: tájékoztató)" if j.get("kis_minta") else ""))
        if j.get("loo", {}).get("rmse") is not None:
            print(f"Leave-one-out hiba: RMSE {j['loo']['rmse']}, MAE {j['loo']['mae']}; javulás {j.get('javulas')}")
        if j.get("illesztett"):
            print("Illesztett súlyok:", ", ".join(f"{k.replace('suly_', '')} {v}" for k, v in j["illesztett"]["suly"].items()))
        for p in j.get("pontok_reszlet", []):
            print(f"  {p['nap']}  {p['cim']}: eredmény {p['eredmeny']}, becslés {p['becsles']}, hiba {p['hiba']}")
        for k in j.get("kihagyott", []):
            print(f"  kihagyva: {k['nap']} {k['cim']} — {k['ok']}")
    if args.rogzit:
        try:
            r = kalibracio.config_ir(cfg, j)
        except ValueError as e:
            print(f"kalibral: nem rögzíthető: {e}", file=sys.stderr)
            return 2
        print(f"Rögzítve: {r['fajl']} (napló: {r['naplo']}). A futó core a következő indulásakor olvassa újra.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mos felkeszultseg", description="A felkészültség-becslés kiértékelője.")
    sub = ap.add_subparsers(dest="parancs", required=True)
    e = sub.add_parser("eredmeny", help="a kiértékelő jegyzetek eredményei (csak olvas)")
    e.add_argument("--json", action="store_true")
    k = sub.add_parser("kalibral", help="az önkalibráció jelentése; --rogzit: a javasolt súlyok az os.toml-ba")
    k.add_argument("--datum", help="a „ma” felülírása (ÉÉÉÉ-HH-NN)")
    k.add_argument("--json", action="store_true")
    k.add_argument("--rogzit", action="store_true", help="csak `javasolt` állapotban: a súlyok az os.toml-ba")
    a = ap.parse_args(argv)
    cfg = config.load()
    return {"eredmeny": eredmeny_parancs, "kalibral": kalibral_parancs}[a.parancs](cfg, a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
