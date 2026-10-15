"""Aranyhalmaz: magyar beszéd átirata (router-feladat: `atirat`) — 2 oktatóvideó, kb. 10 perc.

Az arany a vault `— Átirat.md` jegyzetére **hivatkozik** (a kiadó szövege; út + sha256), a repóban csak a
tisztítás szabálya és a meghallgatás alapján jóváhagyott javítások állnak: a `(ejtsd: …)` betoldások
törlődnek, a `javitasok` szócseréi pedig azt rögzítik, ahol a hang eltér a kiadott szövegtől.

Pontozás: WER és CER kisbetűs, írásjel nélküli szövegen; külön az írásjelek F1-e. A pontszám 1 − WER.

A kérés `tipus: "atirat"`: ezt a futtató a C20 (Whisper-háttér, hang-kérés) előtt nem ismeri, addig a
mérés nem indítható; a pontozó és a tételek már most ellenőrizhetők.

Mit nem lát: a számok és rövidítések írásmódját hibának veszi, ha eltér („49-ben” ↔ „negyvenkilencben”).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
from kozos import arany as A  # noqa: E402
from kozos import kimenet, tavolsag  # noqa: E402

ARANY = A.betolt(ITT)
VERZIO = "atirat-" + A.verzio(ARANY)
ROUTER_FELADAT = "atirat"
_EJTSD = re.compile(r"\s*\((?:ejtsd|kiejtve)\s*:[^)]*\)")


def _fajl(vault: Path, rel: str) -> Path:
    for alak in ("NFC", "NFD"):
        p = vault / unicodedata.normalize(alak, rel)
        if p.is_file():
            return p
    szulo = vault / rel.rsplit("/", 1)[0]
    if szulo.is_dir():
        for f in szulo.iterdir():
            if unicodedata.normalize("NFC", f.name) == unicodedata.normalize("NFC", rel.rsplit("/", 1)[1]):
                return f
    raise FileNotFoundError(f"nincs a vaultban: {rel}")


def kiado_szoveg(jegyzet: str) -> str:
    """Az átirat-jegyzet törzse: frontmatter, címsor és a két bevezető bekezdés nélkül."""
    if jegyzet.startswith("---"):
        jegyzet = jegyzet[jegyzet.find("\n---", 3) + 4:]
    bekezdesek = [b.strip() for b in re.split(r"\n\s*\n", jegyzet) if b.strip()]
    torzs = [b for b in bekezdesek if not b.startswith("#") and not b.startswith("Ez a jegyzet")
             and not b.startswith("Az átirat **nem") and not b.startswith("Az átirat nem")]
    return "\n\n".join(torzs)


def arany_szoveg(jegyzet: str, javitasok: list[dict]) -> str:
    """A mérés elvárt szövege: a kiadó szövege a kiejtési betoldások nélkül, a jóváhagyott javításokkal."""
    szoveg = _EJTSD.sub("", kiado_szoveg(jegyzet))
    for j in javitasok:
        if j["mit"] not in szoveg:
            raise ValueError(f"a javítás helye nincs a szövegben: {j['mit']!r}")
        szoveg = szoveg.replace(j["mit"], j["mire"], 1)
    return szoveg


def tetelek(cfg):
    vault = cfg.path("vault")
    for v in ARANY["videok"]:
        jegyzet = _fajl(vault, v["atirat"]).read_text(encoding="utf-8")
        if A.szoveg_sha256(jegyzet) != v["atirat_sha256"]:
            raise ValueError(f"az átirat-jegyzet megváltozott az arany rögzítése óta: {v['atirat']}")
        yield {"id": v["id"],
               "keres": {"tipus": "atirat", "audio": str(_fajl(vault, v["media"])), "nyelv": "hu"},
               "vart": arany_szoveg(jegyzet, v.get("javitasok", []))}


def egyseges(szoveg: str) -> str:
    """Kisbetűs, írásjel nélküli szöveg, az írásmód-változatok (`egyenertek`) közös alakra hozva."""
    s = " " + " ".join(tavolsag.szavak(szoveg)) + " "
    for kozos, valtozat in ARANY.get("egyenertek", []):
        s = s.replace(f" {valtozat} ", f" {kozos} ")
    return s.strip()


def pontoz(rekordok) -> dict:
    sorok = []
    for r in rekordok:
        kapott = kimenet.tisztit(r.get("valasz"))
        v, k = egyseges(r["vart"]), egyseges(kapott)
        sorok.append({"id": r["id"], "wer": round(min(1.0, tavolsag.wer(v, k)), 4),
                      "cer": round(min(1.0, tavolsag.cer(v, k)), 4),
                      "irasjel_f1": round(tavolsag.irasjel_f1(r["vart"], kapott), 4)})
    wer = A.atlag(s["wer"] for s in sorok)
    return {"pontszam": round(1 - wer, 4) if sorok else 0.0, "wer": round(wer, 4),
            "cer": round(A.atlag(s["cer"] for s in sorok), 4),
            "irasjel_f1": round(A.atlag(s["irasjel_f1"] for s in sorok), 4), "videok": sorok}
