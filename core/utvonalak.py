"""Az útvonal-regiszter (C11a, audit 8. fejezet): a modulok maguk regisztrálják a végpontjaikat.

A `server.py` kezelője csak az infrastruktúrát tartja (Host- és X-Manifold-ellenőrzés, hibatérkép,
WebSocket, statikus csomag); minden végpont egy `Regiszter`-ben él, amelybe a modulok a saját
`utvonalak(r)` függvényükkel írnak:

    def utvonalak(r: Regiszter) -> None:
        r.get("/api/vault/fajl", lambda k: k.app.vault.read(k.q.get("ut")))
        r.get(re.compile(r"/api/feladatok/([\\w.-]+)"), lambda k: …k.m.group(1)…)
        r.post("/api/vault/uj", lambda k: Valasz(201, k.app.vault.create(k.torzs())))

A kezelő (`kezelo(k: Kerees)`) JSON-t ad: egy objektum 200-zal megy, `Valasz(kod, obj)` más kóddal, `Etagos(bájtok, etag)`
előre szerializálva, feltételes kérésre 304-gyel; `KESZ`
jelzi, hogy a kezelő a választ már maga elküldte (streamelő végpontok: média). Hibát a meglévő kivételek
(`HttpError`, `vaultio.Invalid`, …) jeleznek, a szerver hibatérképe képezi le őket. A pontos út előbb
számít, mint a minta; a HEAD a GET kezelőjét kapja; az ismeretlen út vagy metódus 404 (a szerveren).
"""
from __future__ import annotations

import re
from typing import Callable

from .hibakod import angol_uzenet, json_param, kodol


FRAME_ANCESTORS = "frame-ancestors 'self'"


def biztonsagi_fejlecek(h, csp: str = "") -> None:
    """A keretezés elleni fejlécek (C29.6, T103) a core MINDEN válaszán (`_kuld`, a fájlküldő ág, a hibák): a CSP `<meta>`-ban a
    `frame-ancestors` nem hat, ezért fejlécben kell; `SAMEORIGIN`/`'self'`, mert a felület saját magát keretezi (a PDF-
    és médiabeágyazás `<iframe>`-je a core saját originjéről tölt). `csp`: a válasz saját direktívái (az SVG sandbox-a) —
    egyetlen `Content-Security-Policy` fejlécben."""
    h.send_header("X-Frame-Options", "SAMEORIGIN")
    h.send_header("Content-Security-Policy", f"{csp}; {FRAME_ANCESTORS}" if csp else FRAME_ANCESTORS)


def _json_param(param: dict) -> dict:
    """A `param` JSON-ba tehető alakja: szöveg, szám, logikai és None marad, minden más (Path, kivétel, …) szöveggé alakul."""
    return json_param(param)


class HttpError(Exception):
    """HTTP status, stable translation metadata and an English wire fallback.

    Existing Python callers keep the original exception text and data. Known
    codes use the core catalog in the public body; clients may translate again.
    """

    def __init__(self, code: int, message: str, kod: str | None = None, param: dict | None = None, **data):
        super().__init__(message)
        extra = {}
        if kod is not None:
            extra["kod"] = kod
        if param is not None:
            extra["param"] = _json_param(param)
        self.code, self.kod, self.param = code, kod, (extra["param"] if param is not None else None)
        self.data = {**extra, **data}       # a régi olvasók (`e.data.get("foglalt")`, …) változatlanul működnek

    def torzs(self) -> dict:
        """A public error body, preserving the status and every extra data field."""
        return {"hiba": angol_uzenet(self.kod, self.param, str(self)), **self.data}


def kodos(kivetel, kod: str, **param):
    """Keyword-parameter alias for `kodol`, retaining the exception type and text."""
    return kodol(kivetel, kod, param)


def hiba_torzs(kivetel, *, alap_kod: str | None = None, **extra) -> dict:
    """Translate at the public boundary; an untagged Python caller stays compatible."""
    torzs = {"hiba": str(kivetel), **extra}
    kod = getattr(kivetel, "hiba_kod", None) or alap_kod
    if isinstance(kod, str):
        param = json_param(getattr(kivetel, "hiba_param", {}))
        torzs["hiba"] = angol_uzenet(kod, param, str(kivetel))
        torzs["kod"], torzs["param"] = kod, param
    return torzs


class UtkozoUtvonal(ValueError):
    """Ugyanarra a (metódus, útra) kétszer regisztráltak."""


KESZ = object()          # a kezelő a választ maga elküldte


class Valasz:
    """Egy JSON-válasz a 200-tól eltérő kóddal."""

    def __init__(self, kod: int, obj):
        self.kod, self.obj = kod, obj


class Etagos:
    """Egy előre szerializált JSON-válasz ETag-gel (C33, T070): ha a kérés `If-None-Match` fejléce egyezik, a szerver 304-et
    küld törzs nélkül (a felület nem tölt és nem épít újra; a gráf 2,7 MB-ja mentésenként)."""

    def __init__(self, torzs: bytes, etag: str):
        self.torzs, self.etag = torzs, etag


class Kerees:
    """Egy kérés a kezelőnek: az `app` (a core állapota), az út, a lekérdezés, a mintaillesztés, a törzs."""

    def __init__(self, app, h, ut: str, q: dict, m: re.Match | None = None, torzs: dict | None = None):
        self.app, self.h, self.ut, self.q, self.m = app, h, ut, q, m
        self._torzs = torzs

    def torzs(self) -> dict:
        """A JSON-törzs (hibás hossz vagy JSON → 400, 16 MiB fölött 413); egyszer olvasódik."""
        if self._torzs is None:
            self._torzs = self.h._torzs()
        return self._torzs

    def egesz(self, kulcs: str, alap: int | None, also: int, felso: int) -> int | None:
        """Egy egész szám-paraméter a lekérdezésből (L2): hiányzik → `alap`; hibás vagy tartományon kívüli → 400."""
        return self.h._egesz(self.q, kulcs, alap, also, felso)


class Regiszter:
    def __init__(self):
        self._fix: dict[tuple[str, str], Callable] = {}
        self._minta: list[tuple[str, re.Pattern, Callable]] = []

    def _felvesz(self, metodus: str, ut: str | re.Pattern, kezelo: Callable) -> None:
        if isinstance(ut, str):
            if (metodus, ut) in self._fix:
                raise UtkozoUtvonal(f"{metodus} {ut} már regisztrálva van")
            self._fix[(metodus, ut)] = kezelo
            return
        if any(m == metodus and p.pattern == ut.pattern for m, p, _ in self._minta):
            raise UtkozoUtvonal(f"{metodus} {ut.pattern} már regisztrálva van")
        self._minta.append((metodus, ut, kezelo))

    def get(self, ut, kezelo) -> None:
        self._felvesz("GET", ut, kezelo)

    def post(self, ut, kezelo) -> None:
        self._felvesz("POST", ut, kezelo)

    def put(self, ut, kezelo) -> None:
        self._felvesz("PUT", ut, kezelo)

    def vegpontok(self) -> list[tuple[str, str, bool]]:
        """A regisztrált végpontok: `(metódus, út vagy minta-szöveg, minta-e)`, rendezve (a dokumentáció- és az
        útvonal-tábla teszt ebből olvas; a kezelők nem futnak)."""
        return sorted([(m, u, False) for (m, u) in self._fix] + [(m, p.pattern, True) for m, p, _ in self._minta])

    def keres(self, metodus: str, ut: str) -> tuple[Callable, re.Match | None] | None:
        """A kezelő és a mintaillesztés, vagy `None`. A HEAD a GET-et kapja; a pontos út előbb, mint a minta,
        a minták a regisztrálás sorrendjében (teljes illesztéssel)."""
        metodus = "GET" if metodus == "HEAD" else metodus
        k = self._fix.get((metodus, ut))
        if k is not None:
            return k, None
        for m, p, kezelo in self._minta:
            if m == metodus:
                r = p.fullmatch(ut)
                if r:
                    return kezelo, r
        return None
