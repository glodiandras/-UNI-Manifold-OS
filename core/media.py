"""Vault-média kiszolgálása (C10; C11a-tól az útvonal-regiszterben): `GET|HEAD /media/<token>/<út>`.

A böngészőelemek (`<img>`, `<video>`, `<iframe>`) nem küldhetnek `X-Manifold` fejlécet, ezért az URL maga
hitelesít: a `token` a core indulásakor sorsolt. Csak a vaulton belüli, rejtett szegmens nélküli, engedélylistás
fájl jön; a `Content-Type` a listából jön, nem találgatott. Range/206 (a WebKit videója enélkül nem játszik),
ETag/304, SVG-nél sandbox-CSP. A képek `?w=N` paramétere kicsinyített változatot kér, a videók `?poster=1[&t=mp]` előnézeti képet (`kepek.py`).
"""
from __future__ import annotations

import hmac
import math
import re

from . import kepek
from .utvonalak import KESZ, HttpError, biztonsagi_fejlecek


def utvonalak(r) -> None:
    r.get(re.compile(r"/media/.*", re.S), media)


def media(k):
    h, app = k.h, k.app
    _, _, token, rel = (k.ut.split("/", 3) + ["", ""])[:4]
    if not hmac.compare_digest(token.encode(), app.media_token.encode()):
        raise HttpError(403, "érvénytelen média-token")
    p, tipus = app.vault.media_path(rel)
    if k.q.get("poster") not in (None, ""):     # `?poster=1[&t=mp]`: a videó előnézeti képe (E14); hiba → 404, a felület poszter nélkül marad
        if not tipus.startswith("video/"):
            raise HttpError(400, "a poszter csak videóhoz kérhető")
        try:
            t = float(k.q["t"]) if k.q.get("t") not in (None, "") else None
            if t is not None and not math.isfinite(t):
                raise ValueError(t)
        except ValueError:
            raise HttpError(400, "hibás t") from None
        eredmeny = kepek.poszter(app.cfg, p, t)
        if eredmeny is None:
            raise HttpError(404, "a poszter nem készíthető")
        fajl_kuld(h, *eredmeny)
        return KESZ
    if k.q.get("w") not in (None, ""):          # `?w=N`: a megjelenített szélességű változat (C11a, M9)
        n = k.egesz("w", None, 64, 4096)
        p, tipus = kepek.kicsinyitett(app.cfg, p, tipus, n)
    # A-javító (2026-10-14): a folyó küldés (egy lejátszás alatt álló videó streamje) nyilvántartva: a leállás (`close_ws`)
    # lezárja a socketet, így nem tartja vissza a rendezett kilépést; leálláskor új küldés nem indul (503)
    kuldes = getattr(app, "media_kuldes", None)
    if kuldes is None:
        fajl_kuld(h, p, tipus)
        return KESZ
    with kuldes(h.connection):
        try:
            fajl_kuld(h, p, tipus)
        except OSError:
            if not getattr(app, "closing", False):
                raise
            h.close_connection = True       # a leállás zárta le a socketet: nincs kinek válaszolni
    return KESZ


def fajl_kuld(h, p, tipus: str) -> None:
    """Egy fájl a kezelőn át: ETag/304, Range 206/416, SVG-CSP, HEAD (a törzs nélkül)."""
    st = p.stat()
    etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
    if h.headers.get("If-None-Match") == etag:
        h.send_response(304)
        h.send_header("ETag", etag)
        biztonsagi_fejlecek(h)
        h.send_header("Connection", "close")
        h.end_headers()
        return
    meret, kezd, veg, kod = st.st_size, 0, st.st_size - 1, 200
    r = (h.headers.get("Range") or "").strip()
    if r:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", r)
        if not m or not (m.group(1) or m.group(2)):
            raise HttpError(416, "hibás Range")
        if m.group(1):
            kezd = int(m.group(1))
            veg = min(int(m.group(2)), meret - 1) if m.group(2) else meret - 1
        else:
            kezd = max(0, meret - int(m.group(2)))
        if kezd >= meret or kezd > veg:
            h.send_response(416)
            h.send_header("Content-Range", f"bytes */{meret}")
            h.send_header("Content-Length", "0")
            biztonsagi_fejlecek(h)
            h.send_header("Connection", "close")
            h.end_headers()
            return
        kod = 206
    hossz = max(0, veg - kezd + 1) if meret else 0
    h.send_response(kod)
    h.send_header("Content-Type", tipus)
    h.send_header("Content-Length", str(hossz))
    h.send_header("Accept-Ranges", "bytes")
    if kod == 206:
        h.send_header("Content-Range", f"bytes {kezd}-{veg}/{meret}")
    h.send_header("ETag", etag)
    h.send_header("Cache-Control", "private, no-cache")
    h.send_header("X-Content-Type-Options", "nosniff")
    biztonsagi_fejlecek(h, "sandbox; default-src 'none'; style-src 'unsafe-inline'" if tipus == "image/svg+xml" else "")
    h.send_header("Connection", "close")
    h.end_headers()
    if h.command == "HEAD" or not hossz:
        return
    with open(p, "rb") as fh:
        fh.seek(kezd)
        marad = hossz
        while marad > 0:
            adag = fh.read(min(262144, marad))
            if not adag:
                break
            h.wfile.write(adag)
            marad -= len(adag)
