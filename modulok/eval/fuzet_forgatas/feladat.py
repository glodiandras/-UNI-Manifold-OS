"""A füzetlánc forgatás-próbája (C21; saját kulcs: `fuzet_forgatas`, NEM router-feladat) — az álló papírú aranyfotók × 3 irány (−90°, +90°, 0°).

A legacy `fuzet_eros._forgatas` portja a méréshez: az oldalra fordított füzet (a papírkivágás után álló papír, `fuzet.kep`) első
oldala −90°, +90°-kal elforgatva és forgatás nélkül (a C21 bővítése: 0°) egy rövid próbaolvasást kap (`modszer.FORGATAS_PROMPT`, 60 token), és a vault szókincsével
(`kep.olvashatosag`, a fagyasztott katalógus szavai) jobban egyező irány nyer. Az eval-keret tételenként egy kérést küld, ezért a
próbaolvasás külön feladat: a `fuzet_fejezet` ennek a `FORGATO` modelltől rögzített soraiból fordítja az álló oldalakat (ahogy a
`fuzet_valaszto` a `fuzet_fejezet` soraiból olvas). Élesben a lánc ugyanezt a két kérést küldi a `fuzet_fejezet` modelljének.

**Pontozó**: fotónként a döntés; a pontszám a kézzel megnézett irányokkal (`KEZI`) való egyezés aránya — ahol nincs kézi irány,
a döntés határozottsága (a legjobb irány olvashatósága szigorúan nagyobb a többinél) számít. Kalibrációs jele nincs (nem router-feladat).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
sys.path.insert(0, str(ITT.parent.parent))
from kozos import arany as A  # noqa: E402
from fuzet import kep, modszer  # noqa: E402
from fuzet.katalogus import Katalogus  # noqa: E402

OCR = ITT.parent / "ocr_kezi"
ARANY = A.betolt(OCR)
VERZIO = "fuzet_forgatas-" + A.verzio(ARANY)
ROUTER_FELADAT = "fuzet_forgatas"
FORGATO = "qwen35_9b"                    # a `fuzet_fejezet` ennek a modellnek a soraiból fordít (a legacy olvasója is a 9B volt)
# foto → a helyes irány: Claude kézzel nézte meg 2026-10-07-én (C21) a 9 álló papírú aranyfotó felső oldalképét mindhárom irányban
KEZI: dict[str, int] = {"IMG_1307.JPG": -90, "IMG_1361.JPG": -90, "IMG_1613.JPG": -90, "IMG_1703.JPG": -90,
                        "IMG_1607.JPG": 90, "IMG_1650.JPG": 90, "IMG_1656.JPG": 90,
                        "IMG_1545.JPG": 0, "IMG_1557.JPG": 0}
_kat: list = []


def katalogus() -> Katalogus:
    if not _kat:
        _kat.append(Katalogus.fagyasztott())
    return _kat[0]


def tmp_mappa(cfg) -> Path:
    return cfg.path("tmp") / "eval-fuzet-c21"


def forras(cfg, foto: str) -> Path:
    p = cfg.path("vault") / ARANY["fotomappa"] / foto
    if not p.is_file():
        raise FileNotFoundError(f"hiányzó füzetfotó a vaultban: {foto}")
    return p


def tetelek(cfg):
    for f in ARANY["fotok"]:
        src = forras(cfg, f["foto"])
        meta, _ = kep.oldalkepek(src, tmp_mappa(cfg), px=int(ARANY["kep_px"]))
        if meta["fekvo"]:
            continue
        for fok in kep.FORGATASOK:
            _, utak = kep.oldalkepek(src, tmp_mappa(cfg), forgatas=fok, px=int(ARANY["kep_px"]))
            yield {"id": f"{f['foto']}#{fok}",
                   "keres": {"messages": [{"role": "user", "content": modszer.FORGATAS_PROMPT}], "images": [str(utak[0])],
                             "max_tokens": modszer.MAX_TOKEN_FORGATAS},
                   "vart": {"foto": f["foto"], "fok": fok, "kezi": KEZI.get(f["foto"])}}


def dontesek(rekordok) -> dict[str, dict]:
    """Fotónként: {fok, pont: {irány: olvashatóság}} a rekordokból (az irányok válaszából)."""
    olv: dict[str, dict[int, str]] = {}
    for r in rekordok:
        v = r["vart"]
        olv.setdefault(v["foto"], {})[int(v["fok"])] = modszer.kimenet.tisztit(r.get("valasz"))
    szk = katalogus().szokincs()
    ki = {}
    for foto, o in olv.items():
        fok, pont = kep.forgatas_dontes(o, szk)
        ki[foto] = {"fok": fok, "pont": pont, "teljes": len(o) == len(kep.FORGATASOK)}
    return ki


def iranyok(cfg, modell: str = FORGATO) -> dict[str, int]:
    """A `modell` rögzített `fuzet_forgatas` soraiból fotónként az irány (a fájl tételenként utolsó, nem üres sora)."""
    ut = cfg.path("runs") / "eval" / modell / "fuzet_forgatas.jsonl"
    if not ut.is_file():
        return {}
    utolso: dict[str, dict] = {}
    for s in ut.read_text(encoding="utf-8").splitlines():
        if s.strip():
            r = json.loads(s)
            if isinstance(r.get("valasz"), str) and r["valasz"].strip():
                utolso[r["id"]] = r
    rek = []
    for azon, r in utolso.items():
        foto, _, fok = azon.rpartition("#")
        rek.append({"vart": {"foto": foto, "fok": int(fok)}, "valasz": r["valasz"]})
    return {foto: d["fok"] for foto, d in dontesek(rek).items() if d["teljes"]}


def pontoz(rekordok) -> dict:
    d = dontesek(rekordok)
    n = len(d)
    kezivel = {f: x for f, x in d.items() if KEZI.get(f) is not None}
    egyezik = sum(1 for f, x in kezivel.items() if x["fok"] == KEZI[f])
    hatarozott = sum(1 for x in d.values() if sorted(x["pont"].values())[-1] > sorted(x["pont"].values())[-2])
    pontszam = (egyezik / len(kezivel)) if kezivel else ((hatarozott / n) if n else 0.0)
    return {"pontszam": round(pontszam, 4), "foto": n, "kezi": len(kezivel), "kezi_egyezik": egyezik,
            "hatarozott": hatarozott, "dontesek": {f: x["fok"] for f, x in sorted(d.items())},
            "pontok": {f: x["pont"] for f, x in sorted(d.items())}}


def formatum_ok(valasz, vart) -> bool:
    return bool(modszer.kimenet.tisztit(valasz))
