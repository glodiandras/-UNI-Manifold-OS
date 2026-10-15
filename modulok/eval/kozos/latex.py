"""LaTeX-képletek kinyerése a modellválaszból és normalizálása az összevetéshez.

A normalizálás csak írásmódot egységesít (szóköz, `\\left`/`\\right`, `\\dfrac`, fölös kapcsos zárójel,
szorzásjel, Unicode-jelek): matematikai átalakítást nem végez, két különböző képlet nem válik azonossá.
"""
from __future__ import annotations

import re

from . import tavolsag

_KERET = [
    re.compile(r"\$\$(.+?)\$\$", re.S),
    re.compile(r"\\\[(.+?)\\\]", re.S),
    re.compile(r"\\\((.+?)\\\)", re.S),
    re.compile(r"(?<![\\$])\$(?!\$)(.+?)(?<![\\$])\$(?!\$)", re.S),
]
_KERITES = re.compile(r"```(?:math|latex|tex)\s*\n(.+?)```", re.S)

_CSERE = [
    (r"\\(?:dfrac|tfrac|cfrac)\b", r"\\frac"),
    (r"\\(?:left|right|big|Big|bigg|Bigg|displaystyle|textstyle|limits)\b", ""),
    (r"\\(?:,|;|:|!|quad|qquad| )", ""),
    (r"\\(?:cdot|times|ast)\b", "*"),
    (r"\\(?:le|leqslant)\b", r"\\leq"),
    (r"\\(?:ge|geqslant)\b", r"\\geq"),
    (r"\\ne\b", r"\\neq"),
    (r"\\(?:to|longrightarrow)\b", r"\\rightarrow"),
    (r"\\(?:Rightarrow|implies|Longrightarrow)\b", r"\\Rightarrow"),
    (r"\\(?:Leftrightarrow|iff|Longleftrightarrow)\b", r"\\Leftrightarrow"),
    (r"\^\s*\{?\s*\\circ\s*\}?", "°"),
    (r"\\degree\b", "°"),
    (r"\\(?:lvert|rvert|vert|mid)\b", "|"),
    (r"\\%", "%"),
    (r"\{,\}", ","),
    (r"\\(?:text|mathrm|mathbf|mathit|operatorname|textbf|mathsf|boldsymbol)\s*\{([^{}]*)\}", r"\1"),
    (r"\\(?:tg)\b", r"\\tan"),
    (r"\\(?:ctg)\b", r"\\cot"),
]
_UNICODE = {"²": "^2", "³": "^3", "×": "*", "·": "*", "⋅": "*", "−": "-", "–": "-", "—": "-", "√": "\\sqrt",
            "≤": "\\leq", "≥": "\\geq", "≠": "\\neq", "π": "\\pi", "α": "\\alpha", "β": "\\beta", "γ": "\\gamma",
            "Δ": "\\Delta", "→": "\\rightarrow", "⇒": "\\Rightarrow", "⇔": "\\Leftrightarrow", "∞": "\\infty",
            "±": "\\pm", "∈": "\\in", "÷": "/", "’": "'", "′": "'"}
_EGYKAPCSOS = re.compile(r"([\^_])\{([^{}\\])\}")


def kepletek(szoveg: str) -> list[str]:
    """A válaszban álló képletek (`$…$`, `$$…$$`, `\\(…\\)`, `\\[…\\]`, ```` ```math ````), előfordulási sorrendben."""
    szoveg = szoveg or ""
    talalat: list[tuple[int, str]] = []
    foglalt: list[tuple[int, int]] = []
    for minta in [_KERITES] + _KERET:
        for m in minta.finditer(szoveg):
            if any(m.start() < v and m.end() > k for k, v in foglalt):
                continue
            foglalt.append((m.start(), m.end()))
            for sor in re.split(r"\\\\|\n", m.group(1)) if minta is _KERITES else [m.group(1)]:
                if sor.strip():
                    talalat.append((m.start(), sor.strip()))
    return [k for _, k in sorted(talalat, key=lambda t: t[0])]


def normalizal(latex: str) -> str:
    s = tavolsag.nfc(latex or "").strip().strip("$").strip()
    for k, v in _UNICODE.items():
        s = s.replace(k, v)
    for minta, csere in _CSERE:
        s = re.sub(minta, csere, s)
    s = re.sub(r"\\begin\{(?:aligned|align\*?|equation\*?|gathered)\}|\\end\{(?:aligned|align\*?|equation\*?|gathered)\}",
               "", s)
    s = s.replace("&", "")
    s = re.sub(r"\s+", "", s)
    for _ in range(3):
        s = _EGYKAPCSOS.sub(r"\1\2", s)
    return s.rstrip(".,;")


def hasonlosag(vart: str, kapott: str) -> float:
    return tavolsag.hasonlosag(normalizal(vart), normalizal(kapott))


def cer(vart: str, kapott: str) -> float:
    v, k = normalizal(vart), normalizal(kapott)
    return tavolsag.levenshtein(v, k) / len(v) if v else float(bool(k))


def legjobb(vart: str, jeloltek: list[str]) -> tuple[float, str | None]:
    """A várt képlethez leginkább hasonló jelölt: (hasonlóság, jelölt). A jelölt részlete is számít,
    ha a modell több képletet írt egy sorba (`=`-lánc)."""
    v = normalizal(vart)
    legj, melyik = 0.0, None
    for j in jeloltek:
        n = normalizal(j)
        h = tavolsag.hasonlosag(v, n)
        if v and len(n) > len(v) and v in n:
            h = max(h, 1.0)
        if h > legj:
            legj, melyik = h, j
    return legj, melyik
