"""Excluded files (F11, 14-appearance-06): a user-managed list of path patterns hidden from search, the graph, the quick
switcher and unlinked-mention suggestions.

**Only a visibility filter.** A matching file is never deleted, moved, re-indexed differently or hidden from the tree
(the explorer dims it); links to it still resolve and its backlinks, rename plans and snapshots are unchanged. The index
keeps every file, so removing an entry restores the file everywhere without a re-scan (data safety, CLAUDE.md).

Pattern forms (the Obsidian `userIgnoreFilters` shapes):
- `Folder/` or `Folder/Note.md`: a vault-relative path prefix on a path-segment boundary (NFC, case-insensitive).
- `/regular expression/`: searched in the vault-relative path; checked with `regex_biztonsag` (no catastrophic backtracking).
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from pathlib import Path

from .. import regex_biztonsag

MAX_DB = 200
MAX_HOSSZ = 200
MAX_APP_JSON_BAJT = 1 << 20
_VEZERLO = re.compile("[\x00-\x1f\x7f\x85  ]")


class MintaHiba(ValueError):
    """Egy kizárási minta érvénytelen; `kod` gépi azonosító (a felület angol szöveget választ hozzá)."""

    def __init__(self, kod: str):
        super().__init__(kod)
        self.kod = kod


def _regex_e(minta: str) -> bool:
    return len(minta) >= 3 and minta.startswith("/") and minta.endswith("/")


def minta_ellenoriz(minta) -> str:
    """Az érvényes minta normalizált alakja (NFC, szóköz nélkül), különben `MintaHiba`."""
    if not isinstance(minta, str):
        raise MintaHiba("tipus")
    m = unicodedata.normalize("NFC", minta.strip())
    if not m:
        raise MintaHiba("ures")
    if len(m) > MAX_HOSSZ:
        raise MintaHiba("hossz")
    if _VEZERLO.search(m):
        raise MintaHiba("vezerlo_karakter")
    if _regex_e(m):
        try:
            re.compile(m[1:-1])
        except re.error:
            raise MintaHiba("regex") from None
        if regex_biztonsag.veszelyes(m[1:-1]):
            raise MintaHiba("regex_veszelyes")
        return m
    ut = m.replace("\\", "/").lstrip("/")
    if not ut.strip("/"):
        raise MintaHiba("ures")
    if any(r == ".." for r in ut.split("/")) or "\\" in m:
        raise MintaHiba("ut")
    return ut


def lista_ellenoriz(lista) -> list[str]:
    """A beállítás értéke: legfeljebb `MAX_DB` érvényes minta, ismétlődés nélkül (a sorrend megmarad)."""
    if not isinstance(lista, list) or len(lista) > MAX_DB:
        raise MintaHiba("lista")
    ki: list[str] = []
    for x in lista:
        m = minta_ellenoriz(x)
        if m not in ki:
            ki.append(m)
    return ki


class Kizaras:
    """A lefordított minták; üres lista: semmi sincs kizárva (a gyors ág)."""

    def __init__(self, mintak: tuple[str, ...]):
        self.jel = mintak
        elok: list[str] = []
        regexek: list[re.Pattern] = []
        for m in mintak:
            if _regex_e(m):
                regexek.append(re.compile(m[1:-1]))
            else:
                elok.append(unicodedata.normalize("NFC", m).casefold())
        self._elok = tuple(elok)
        self._regexek = tuple(regexek)

    def __bool__(self) -> bool:
        return bool(self._elok or self._regexek)

    def kizart(self, ut: str) -> bool:
        if not self:
            return False
        u = unicodedata.normalize("NFC", ut).replace("\\", "/").lstrip("/")
        kis = u.casefold()
        for e in self._elok:
            if e.endswith("/"):
                if kis.startswith(e):
                    return True
            elif kis == e or kis.startswith(e + "/"):
                return True
        return any(rx.search(u) for rx in self._regexek)

    def egyezo(self, utak) -> int:
        return sum(1 for u in utak if self.kizart(u))


_ures = Kizaras(())
_gyorsitotar: dict[tuple[str, ...], Kizaras] = {}
_zar = threading.Lock()
_app_json: dict[str, tuple[tuple[int, int], tuple[str, ...]]] = {}


def fordit(lista) -> Kizaras:
    """A (már ellenőrzött vagy kézzel szerkesztett) lista lefordítva; az érvénytelen elemet kihagyja, nem dob."""
    elemek: list[str] = []
    for x in lista or ():
        try:
            m = minta_ellenoriz(x)
        except MintaHiba:
            continue
        if m not in elemek:
            elemek.append(m)
    kulcs = tuple(elemek)
    if not kulcs:
        return _ures
    with _zar:
        k = _gyorsitotar.get(kulcs)
        if k is None:
            if len(_gyorsitotar) > 32:
                _gyorsitotar.clear()
            k = _gyorsitotar[kulcs] = Kizaras(kulcs)
        return k


def obsidian_lista(vault) -> list[str]:
    """Az `.obsidian/app.json` `userIgnoreFilters` értéke (csak olvasva; hibás vagy túl nagy fájl: üres). Az érvénytelen
    elemeket kihagyja; a fájl állapota szerint gyorsítótárazva."""
    try:
        p = Path(vault) / ".obsidian" / "app.json"
        st = p.stat()
    except (OSError, TypeError):
        return []
    kulcs = (st.st_mtime_ns, st.st_size)
    hit = _app_json.get(str(p))
    if hit is not None and hit[0] == kulcs:
        return list(hit[1])
    ertek: list[str] = []
    if st.st_size <= MAX_APP_JSON_BAJT:
        try:
            with open(p, "rb") as f:
                d = json.loads(f.read(MAX_APP_JSON_BAJT + 1).decode("utf-8"))
            nyers = d.get("userIgnoreFilters") if isinstance(d, dict) else None
        except (OSError, ValueError, UnicodeError):
            nyers = None
        if isinstance(nyers, list):
            for x in nyers[:MAX_DB]:
                try:
                    m = minta_ellenoriz(x)
                except MintaHiba:
                    continue
                if m not in ertek:
                    ertek.append(m)
    with _zar:
        if len(_app_json) > 16:
            _app_json.clear()
        _app_json[str(p)] = (kulcs, tuple(ertek))
    return ertek


def hatekony_lista(cfg) -> list[str]:
    """A ténylegesen érvényes lista: a felhasználó mentett értéke, különben az Obsidian-vault `userIgnoreFilters`-e."""
    try:
        sor = cfg.section("beallitasok").get("fajlok", {}).get("kizart")
        sajat = cfg.forras("beallitasok", "fajlok", "kizart") != "os"
    except AttributeError:
        return []
    if sajat and isinstance(sor, list):
        return [x for x in sor if isinstance(x, str)]
    try:
        if "vault" in cfg.utak:
            return obsidian_lista(cfg.path("vault"))
    except Exception:  # noqa: BLE001 - a hiányzó vault nem lehet a keresés hibája
        pass
    return []


def betolt(cfg) -> Kizaras:
    return fordit(hatekony_lista(cfg))


def jel(cfg) -> tuple[str, ...]:
    """A gyorsítótár-kulcs: ha a lista változik, a gráf gyorsítótára érvénytelen."""
    return betolt(cfg).jel if cfg is not None else ()
