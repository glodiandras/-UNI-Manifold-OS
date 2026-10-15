"""A médiatársítás szöveg-alapjai (C20b) — a legacy `vaultlib.py` azon része, amelyre a `media_match` és a `media_link` épül,
**viselkedésre azonosan** (a verifikátor súlyait ezekre a jegyekre illesztették: egy eltérő tokenizálás a kalibrációt csendben
érvénytelenítené, I4).

    fix_ligatures, words, norm_word        a szóhatárra bontás ELŐBB, a normalizálás UTÁNA (2026-08-05)
    longwords(s), stem_list(s)             a visszakeresés egysége (≥ N betű) és a szótő-lista (K betűs előtag)
    mask_code(szoveg)                      a kód kitakarása (hossztartó)
    split_note, parse_fm, media_anchors    a frontmatter lapos olvasása és a `#t=` horgonyok
    cuek(vtt_szoveg)                       WebVTT/SRT → [(kezdet, vég, szöveg)], tag-törléssel és görgő-dedupplal
    ablak_szoveg(cuek, t)                  a `t` körüli [t−20, t+40] ablak szövege (t=None: az egész)

A modul tiszta: fájlt nem olvas (a hívó adja a szöveget), a vaultba nem ír.
"""
from __future__ import annotations

import collections
import re
import unicodedata

K = 7                       # szótő-előtag (legacy calibration.json normalizalas.szoto_prefix_hossz)
N = 7                       # a visszakeresés minimális szóhossza (horgony_visszakereses.min_szohossz)
ABLAK_ELOTTE_S = 20         # media.atirat.ablak_elotte_s
ABLAK_UTANA_S = 40          # media.atirat.ablak_utana_s
GORGO_DEDUP = True          # media.atirat.gorgo_dedup

_LIG_JOIN = re.compile(r"(?i)\b(\w*?f[fil])\s+(\w)")     # normalizalas.ligatura_minta
MEDIA_KITERJESZTES = (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".opus", ".wav")   # media.video_ext + audio_ext
_MEDIA_HORGONY = re.compile(r"\[\[([^\]#]+(?:" + "|".join(re.escape(e) for e in MEDIA_KITERJESZTES) + r"))#t=(\d+)\]\]", re.I)
FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)
_VTT_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*--?>\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")
_VTT_TAG = re.compile(r"<[^>]+>")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def fix_ligatures(s: str) -> str:
    """A PDF-kinyerő „eff ektív” hibájának javítása (a legacy alkalmazza; a videó szövegén ritkán hat, de a jegyek így azonosak)."""
    prev = None
    while prev != s:
        prev = s
        s = _LIG_JOIN.sub(r"\1\2", s)
    return s.replace("/f_i", "fi").replace("/f_l", "fl")


def words(s: str) -> list[str]:
    return [w for w in re.split(r"\s+", s) if w]


def norm_word(w: str) -> str:
    return "".join(ch for ch in w.lower() if ch.isalpha())


def longwords(s: str) -> set[str]:
    """A visszakeresés egysége: normalizált szó, legalább `N` betű."""
    return {w for w in (norm_word(x) for x in words(fix_ligatures(s))) if len(w) >= N}


def stem_list(s: str) -> list[str]:
    return [w[:K] for w in (norm_word(x) for x in words(fix_ligatures(s))) if len(w) >= K]


def mask_code(szoveg: str) -> str:
    szoveg = re.sub(r"```.*?```", lambda m: " " * len(m.group(0)), szoveg, flags=re.S)
    return re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), szoveg)


def split_note(text: str) -> tuple[str | None, str]:
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def parse_fm(fmtext: str | None) -> tuple[dict, list[str]]:
    """Lapos YAML-részhalmaz: kulcs → nyers szöveg (a folytatósorok `\\n`-nel), és a kulcssorrend."""
    d: dict = collections.OrderedDict()
    order: list[str] = []
    cur = None
    if fmtext is None:
        return d, order
    for line in fmtext.split("\n"):
        m = re.match(r"^([A-Za-z_][\w -]*):(.*)$", line)
        if m:
            cur = m.group(1)
            if cur not in d:
                order.append(cur)
                d[cur] = ""
            d[cur] += m.group(2)
        elif cur is not None:
            d[cur] += "\n" + line
    return d, order


def media_anchors(value: str) -> list[tuple[str, int]]:
    """[(médiafájl, másodperc)] egy mezőértékből (a PDF `#page=` analogonja)."""
    return [(nfc(f), int(t)) for f, t in _MEDIA_HORGONY.findall(value or "")]


def _hms(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def cuek(nyers: str) -> tuple[tuple[float, float, str], ...]:
    """[(kezdet_s, vég_s, szöveg)] — WebVTT és SRT; inline tagek törölve, a közvetlenül előző cue ismétlődő sora kimarad (görgő-dedup)."""
    out, prev = [], set()
    for blk in re.split(r"\r?\n\r?\n", nyers or ""):
        m = _VTT_TS.search(blk)
        if not m:
            continue
        start, end = _hms(*m.groups()[:4]), _hms(*m.groups()[4:])
        lines = []
        for ln in blk[m.end():].split("\n"):
            ln = _VTT_TAG.sub("", ln).strip()
            if not ln or ln.isdigit():
                continue
            if GORGO_DEDUP and ln in prev:
                continue
            lines.append(ln)
        prev = set(lines) if lines else prev
        if lines:
            out.append((start, end, " ".join(lines)))
    return tuple(out)


def ablak_szoveg(c: tuple, t: float | None = None) -> str:
    """A szövegréteg szövege — az egészé (`t=None`) vagy a [t−20, t+40] ablaké (a legacy `media_text`)."""
    if t is None:
        return " ".join(x[2] for x in c)
    lo, hi = t - ABLAK_ELOTTE_S, t + ABLAK_UTANA_S
    return " ".join(x[2] for x in c if x[1] >= lo and x[0] <= hi)
