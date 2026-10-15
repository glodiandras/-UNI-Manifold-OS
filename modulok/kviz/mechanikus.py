"""A jelölt kérdés mechanikus kapuja (a legacy kvízlánc 1. kapuja): szerkezet, jelölés, tiltott válasz, kiszivárgás.

Modell nélkül, szabályalapon. Az a kérdés, amelyet ez kiejt, a további kapukra (idézet a jegyzetből, vak ellenőrzés) el
sem jut. A jelölési szabályok a vault `style` próbájáéi (nincs `==kiemelés`, páros `$`, nincs link/megjegyzés/HTML/sortörés,
nincs tiltott szimbólum): a kvízjegyzet sem sértheti őket, és a megjelenítő sem kaphat HTML-t.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

BETUK = "ABCD"
ENGEDETT_JELEK = ("✓", "✗", "▸")        # a vault stílus-szabályának engedett szimbólumai (legacy calibration.json stilus.engedett_jelek)
KERDES_MIN, KERDES_MAX, VALASZ_MAX = 8, 600, 300
KISZIVARGAS_MIN = 8                       # ennél rövidebb helyes válasz „benne áll a kérdésben” nem számít kiszivárgásnak

_TILTOTT_VALASZ = re.compile(r"(?i)\b(mindegyik|egyik\s+sem|egyik\s+fenti\s+sem|a\s+fentiek|mind\s+a\s+(?:három|négy|kettő))\b")
_BETU_KOMBO = re.compile(r"^\s*[ABCD]\s*(?:és|vagy|,)\s*[ABCD]\s*\.?\s*$")


@dataclass
class Jelolt:
    """A modell egy kérdése, ahogy a válaszából kiolvasható (ítélet nélkül)."""
    kerdes: str = ""
    valaszok: dict[str, str] = field(default_factory=dict)       # 'A'..'D' → szöveg
    helyes: str | None = None                                    # a helyes válasz betűje
    idezet: str = ""                                             # a modell szó szerinti idézete a jegyzetből
    magyarazat: str = ""


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _dollar_paratlan(s: str) -> bool:
    return len(re.findall(r"(?<!\\)\$", s)) % 2 == 1 or s.count("$$") % 2 == 1


def jelhiba(s: str, engedett=ENGEDETT_JELEK) -> str | None:
    """A vault `style` próbájának szabályai egy mezőn: az ok, vagy `None`."""
    if "==" in s:
        return "==kiemelés"
    if _dollar_paratlan(s):
        return "páratlan $"
    if any(x in s for x in ("[[", "]]", "%%", "\n")):
        return "link, megjegyzés vagy sortörés"
    if re.search(r"<[A-Za-z/!]", s):
        return "HTML-jelölés"
    for ch in s:
        if ord(ch) > 0x2500 and ch not in engedett and unicodedata.category(ch) == "So":
            return f"tiltott jel: {ch!r}"
    return None


def _norm(s: str) -> str:
    """Összevetési alak a válaszokhoz: kisbetű, szóköz és a záró írásjel nélkül — a műveleti jel és a zárójel MARAD (a
    `$a^2+2ab+b^2$` és az `$a^2-2ab+b^2$` két különböző válasz)."""
    return re.sub(r"\s+", "", nfc(s).lower()).strip(".,;:!?")


def kapu(j: Jelolt, engedett=ENGEDETT_JELEK) -> tuple[str, str] | None:
    """`None`, ha a jelölt átment; különben `(kód, ok)`."""
    k, v = j.kerdes or "", j.valaszok or {}
    if len(k) < KERDES_MIN or len(k) > KERDES_MAX:
        return "szerkezet", "a kérdés hiányzik vagy túl hosszú"
    if set(v) != set(BETUK) or any(not (v[b] or "").strip() or len(v[b]) > VALASZ_MAX for b in BETUK):
        return "szerkezet", "nem pontosan négy, kitöltött válasz"
    if not j.helyes or len(j.helyes) != 1 or j.helyes not in BETUK:
        return "szerkezet", "nincs helyes betű"
    if len({_norm(v[b]) for b in BETUK}) < 4:
        return "valaszok", "két válasz azonos"
    for b in BETUK:
        if _TILTOTT_VALASZ.search(v[b]) or _BETU_KOMBO.match(v[b]):
            return "tiltott_valasz", f"a sorrendre utaló válasz: {v[b][:40]}"
    for mezo in [k, j.magyarazat or ""] + [v[b] for b in BETUK]:
        h = jelhiba(mezo, engedett)
        if h:
            return "jeloles", h
    helyes = _norm(v[j.helyes])
    if len(helyes) >= KISZIVARGAS_MIN and helyes in _norm(k):
        return "kiszivargas", "a helyes válasz szó szerint benne áll a kérdésben"
    return None
