"""A `kviz` aranyhalmaz generátora (C22m): a `szoveg` halmaz 20 fagyasztott jegyzetéből jegyzetenként egy 5 kérdéses darab.

    bin/mos exec var/venv/bin/python -B modulok/eval/kviz/keszit.py              # az arany.json (újra)írása
    bin/mos exec var/venv/bin/python -B modulok/eval/kviz/keszit.py --ellenoriz  # csak összeveti a meglévővel

Determinisztikus: nincs véletlen, nincs hálózat, nincs modell; a `szoveg/arany.json`-t és a `szoveg/forrasok/jNN.md`
másolatokat csak olvassa. A jegyzet darabja (a lánc `generalas.darabok` egysége, `darab_max_karakter` hosszig) az a darab, amelyben
a `szoveg` halmaz *tényeinek* legtöbb forrásmondata áll (döntetlennél az első); a darab indexét, szakaszait és a szövegének
sha256-ját rögzíti, így a `[kviz]` beállítás vagy az előkészítés későbbi változása nem sodorja észrevétlenül a halmazt.

A kézi lépés: az `allapot` `vazlat`-ról `jovahagyott`-ra a felhasználó jóváhagyása után (K134) — ezt a generátor soha nem állítja
(újraíráskor a meglévő `allapot`/`jovahagyva` marad, ha a tartalom nem változott; változott tartalomnál `vazlat`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parents[2]
for _p in (str(REPO), str(ITT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from kozos import arany as A  # noqa: E402
from modulok.kapuk import forras as KF  # noqa: E402
from modulok.kviz import generalas as G  # noqa: E402
from modulok.kviz.promptok import PROMPT_VERZIO  # noqa: E402

SZOVEG = ITT.parent / "szoveg"
KERDES_CEL = 5                  # a darabból kért kérdések (= a lánc `hivas_max_kerdes`)
DARAB_MAX_KARAKTER = 2200       # a lánc `[kviz] darab_max_karakter` alapja, itt FAGYASZTVA
SZAKASZ_MIN_KARAKTER = 20       # a lánc `[kviz] szakasz_min_karakter` alapja, itt FAGYASZTVA
TOKEN_PER_KERDES = 230          # a lánc `[kviz] token_per_kerdes` alapja
TOKEN_ALAP = 150
VERZIO = "v2"


def forras_ut(jid: str) -> Path:
    return SZOVEG / "forrasok" / f"{jid}.md"


def darabok_es_szakaszok(md: str, ut: str, max_k: int = DARAB_MAX_KARAKTER, min_k: int = SZAKASZ_MIN_KARAKTER):
    """(darabok, a szakaszokból épített `ForrasSzoveg`): a lánc ugyanazon szakasz-előkészítésével és darabolásával."""
    szak = KF.elokeszit(md, min_karakter=min_k)
    return G.darabok(szak, max_k), KF.ForrasSzoveg(szak, G.cim_of(ut))


def darab_szoveg(md: str, ut: str, index: int, max_k: int = DARAB_MAX_KARAKTER, min_k: int = SZAKASZ_MIN_KARAKTER) -> dict:
    darabok, _ = darabok_es_szakaszok(md, ut, max_k, min_k)
    if not 0 <= index < len(darabok):
        raise ValueError(f"nincs {index}. darab ({len(darabok)} van)")
    return darabok[index]


def jegyzet_rekord(j: dict) -> dict:
    """A `szoveg` halmaz egy jegyzetéből a `kviz` halmaz rekordja."""
    md = forras_ut(j["id"]).read_text(encoding="utf-8")
    darabok, fs = darabok_es_szakaszok(md, j["ut"])
    szamlalo = [[] for _ in darabok]
    for t in j["tenyek"]:
        h = fs.keres(t["forras"], 0.9)
        if h is None:
            raise ValueError(f"{j['id']}: a tény forrásmondata nincs a jegyzetben: {t['forras'][:50]}")
        for i, d in enumerate(darabok):
            if h.szakasz in d["szakaszok"]:
                szamlalo[i].append({"teny": t["teny"], "forras": t["forras"]})
    index = max(range(len(darabok)), key=lambda i: (len(szamlalo[i]), -i))
    d = darabok[index]
    return {"id": j["id"], "ut": j["ut"], "cim": G.cim_of(j["ut"]), "targy": j["targy"],
            "forras_sha256": A.sha256(forras_ut(j["id"])),
            "darab": {"index": index, "darabok": len(darabok), "karakter": d["karakter"], "szakaszok": list(d["szakaszok"]),
                      "sha256": A.szoveg_sha256(d["szoveg"])},
            "tenyek": szamlalo[index]}


def epit(regi: dict | None = None) -> dict:
    szoveg = A.betolt(SZOVEG)
    jegyzetek = [jegyzet_rekord(j) for j in szoveg["jegyzetek"]]
    uj = {"verzio": VERZIO, "allapot": "vazlat", "keszult": "2026-10-05", "jovahagyva": None,
          "forras": "a `szoveg` halmaz 20 fagyasztott jegyzete (modulok/eval/szoveg/forrasok/jNN.md); jegyzetenként egy 5 kérdéses darab; "
                    "a tények a `szoveg` halmazéi (Claude vázlata, ellenőrzés: felhasználó)",
          "szabaly": "darab: a lánc darabolásának az a darabja, amelyben a legtöbb tény forrásmondata áll; tény: a darabba eső "
                     "szoveg-tény (atomi, szó szerinti forrásmondattal); a lefedettség a tények átfedése az átmenő kérdések idézetével",
          "kerdes_cel": KERDES_CEL, "darab_max_karakter": DARAB_MAX_KARAKTER, "szakasz_min_karakter": SZAKASZ_MIN_KARAKTER,
          "token_per_kerdes": TOKEN_PER_KERDES, "token_alap": TOKEN_ALAP, "prompt_verzio": PROMPT_VERZIO,
          "jegyzetek": jegyzetek}
    if regi and {k: v for k, v in regi.items() if k not in ("allapot", "jovahagyva", "keszult")} == \
            {k: v for k, v in uj.items() if k not in ("allapot", "jovahagyva", "keszult")}:
        uj.update(allapot=regi.get("allapot", "vazlat"), jovahagyva=regi.get("jovahagyva"), keszult=regi.get("keszult", uj["keszult"]))
    return uj


def kiir(adat: dict) -> str:
    return json.dumps(adat, ensure_ascii=False, indent=1) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A kviz aranyhalmaz (arany.json) generálása a szoveg halmazból.")
    ap.add_argument("--ellenoriz", action="store_true", help="csak összeveti a meglévő arany.json-nal (nem ír)")
    a = ap.parse_args(argv)
    ut = ITT / "arany.json"
    regi = json.loads(ut.read_text(encoding="utf-8")) if ut.is_file() else None
    uj = epit(regi)
    if a.ellenoriz:
        if regi is None or kiir(regi) != kiir(uj):
            print("[kviz] az arany.json nem egyezik a generátor kimenetével", file=sys.stderr)
            return 1
        print("[kviz] az arany.json egyezik a generátor kimenetével")
        return 0
    ut.write_text(kiir(uj), encoding="utf-8")
    ossz = sum(len(j["tenyek"]) for j in uj["jegyzetek"])
    print(f"[kviz] arany.json kész: {len(uj['jegyzetek'])} jegyzet, {ossz} tény ({uj['allapot']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
