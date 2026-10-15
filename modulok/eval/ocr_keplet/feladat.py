"""Aranyhalmaz: képlet → LaTeX (router-feladat: `ocr_keplet`) — 20 füzetfotó kézzel átírt képletei.

Tételenként egy képletkivágás (a fotó határolódoboza szerint, futásidőben vágva a `{tmp}` alá); a modell
a képlet LaTeX-kódját adja. A pontozó csak az írásmódot egységesíti (szóköz, `\\left`/`\\right`, `\\dfrac`,
fölös kapcsos, szorzásjel), matematikai átalakítást nem végez: az elírt index, előjel vagy kitevő hiba.

Mit nem lát: két matematikailag azonos, de másképp leírt alakot (pl. `\\frac{1}{2}x` és `\\frac{x}{2}`)
különbözőnek vesz — a feladat az átírás, nem az átalakítás. A képek kézírásosak; a nyomtatott
képernyőkép-képlet (a router-feladat másik felhasználása) könnyebb eset, erre nincs külön halmaz.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
from kozos import arany as A  # noqa: E402
from kozos import kep, kimenet, latex, tavolsag  # noqa: E402

ARANY = A.betolt(ITT)
VERZIO = "ocr_keplet-" + A.verzio(ARANY)
ROUTER_FELADAT = "ocr_keplet"
JO_KUSZOB = 0.9

PROMPT = ("A képen egy kézzel írt matematikai vagy fizikai képlet látható egy iskolai füzetből. "
          "Írd át LaTeX-ben, pontosan úgy, ahogy a papíron áll. "
          "Csak a képlet LaTeX-kódját add vissza, magyarázat nélkül.")


def tetelek(cfg):
    mappa = cfg.path("vault") / ARANY["fotomappa"]
    tmp = cfg.path("tmp") / "eval-keplet"
    for k in ARANY["kepletek"]:
        forras = mappa / k["foto"]
        if not forras.is_file():
            raise FileNotFoundError(f"hiányzó füzetfotó a vaultban: {k['foto']}")
        kivagas = kep.kivag(forras, k["doboz"], tmp / f"{k['id']}.jpg", int(ARANY["kep_px"]), float(ARANY["szegely"]))
        yield {"id": k["id"],
               "keres": {"messages": [{"role": "user", "content": PROMPT}], "images": [str(kivagas)],
                         "max_tokens": int(ARANY["max_token"])},
               "vart": k["latex"]}


def jelolt(valasz) -> str:
    """A válasz képlete: ha a modell jelek közé tette, az első jelölt képlet; különben a teljes szöveg."""
    szoveg = kimenet.tisztit(valasz)
    talalt = latex.kepletek(szoveg)
    if talalt:
        return talalt[0]
    sorok = [s for s in szoveg.replace("```latex", "").replace("```", "").splitlines() if s.strip()]
    return sorok[0] if sorok else ""


_BINOM = re.compile(r"(?:\\left)?\(\s*\\begin\{array\}\{c*\}\s*(.+?)\s*\\\\\s*(.+?)\s*\\end\{array\}\s*(?:\\right)?\)"
                    r"|\\begin\{pmatrix\}\s*(.+?)\s*\\\\\s*(.+?)\s*\\end\{pmatrix\}", re.S)


def _szamjegyek(s: str) -> str:
    return re.sub(r"(?<=\d)\s+(?=\d)", "", s)


def binom_alak(s: str) -> str:
    """A tömbös/mátrixos binomiális együttható (`(\\begin{array}{c} 4 \\\\ 2 \\end{array})`, `\\begin{pmatrix}…`) →
    `\\binom{4}{2}` (C19 rétegzett minta: a pontozó a jelentésre azonos tömbös alakot hibának vette)."""
    def cserel(m):
        a, b = (m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(4))
        return f"\\binom{{{_szamjegyek(a)}}}{{{_szamjegyek(b)}}}"
    return _BINOM.sub(cserel, s)


def pontoz(rekordok) -> dict:
    hasonlosag, cer, pontos, jo, rossz = [], [], 0, 0, []
    for r in rekordok:
        v, k = latex.normalizal(r["vart"]), latex.normalizal(binom_alak(jelolt(r.get("valasz"))))
        h = tavolsag.hasonlosag(v, k) if k else 0.0
        hasonlosag.append(h)
        cer.append(min(1.0, tavolsag.levenshtein(v, k) / len(v)) if v else 0.0)
        pontos += v == k
        jo += h >= JO_KUSZOB
        if h < JO_KUSZOB:
            rossz.append({"id": r["id"], "vart": r["vart"], "kapott": jelolt(r.get("valasz"))[:200], "hasonlosag": round(h, 3)})
    n = len(rekordok)
    return {"pontszam": round(A.atlag(hasonlosag), 4), "pontos": round(pontos / n, 4) if n else 0.0,
            "jo": round(jo / n, 4) if n else 0.0, "cer": round(A.atlag(cer), 4), "rossz": rossz}
