"""A videólánc lépésének hálózat-őre (Javító 3, A3-13): a folyamat minden kimenő kapcsolatának célja ellenőrzött.

A `core/videolanc.py` a kérés idején ellenőrzi a linket (számformák, DNS, minden feloldott cím). Ez nem fogja meg, amit a yt-dlp utána tesz:
a HTTP-átirányítást egy helyi/privát címre, és a DNS-újrakötést (a név az ellenőrzéskor nyilvános címre oldódott, a letöltéskor nem). A
yt-dlp saját kérés-kezelője az átirányítást maga követi, ezért nem horgonyozható be tisztán; a lépés viszont **külön folyamat** (`python -m
modulok.ytdlp lepes letoltes`), így itt a socket-réteg a megbízható hely: a `socket.socket.connect` és `connect_ex` minden IP-célt
ellenőriz, és a nem globális cél (loopback, privát, link-local, CGNAT, multicast, nem megadott; IPv4-mapped IPv6 is) `PermissionError`.

Csak a lépés belépési pontja telepíti (`telepit()`); a core és a tesztfolyamat a saját loopback-kapcsolataival nem érintett. Idempotens,
`leszed()` visszaállítja az eredetit (a tesztek). A Unix-socket (AF_UNIX) nem IP-cél: nem érintett. Korlát: a rendszerszintű proxy
beállítás (a lépés a proxy címére kapcsolódna) privát proxycímnél hibázik — a D3 szerint a lánc közvetlen hálózatot használ.
"""
from __future__ import annotations

import ipaddress
import socket

_eredeti: dict[str, object] = {}


def _tiltott(cim) -> bool:
    try:
        ip = ipaddress.ip_address(str(cim).split("%", 1)[0])
    except ValueError:
        return False                # nem IP (pl. AF_UNIX útvonal): a kapcsolat-szint nem ellenőriz
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


def _ellenoriz(sock: socket.socket, cim) -> None:
    if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(cim, tuple) and cim and _tiltott(cim[0]):
        raise PermissionError(f"a videólánc nem kapcsolódhat helyi vagy privát címre: {cim[0]}")


def telepit() -> None:
    """A `connect`/`connect_ex` ellenőrzése a folyamatban (idempotens)."""
    if _eredeti:
        return
    _eredeti["connect"], _eredeti["connect_ex"] = socket.socket.connect, socket.socket.connect_ex
    connect, connect_ex = _eredeti["connect"], _eredeti["connect_ex"]

    def connect_orzott(self, cim):
        _ellenoriz(self, cim)
        return connect(self, cim)

    def connect_ex_orzott(self, cim):
        _ellenoriz(self, cim)
        return connect_ex(self, cim)

    socket.socket.connect, socket.socket.connect_ex = connect_orzott, connect_ex_orzott


def leszed() -> None:
    """Az eredeti `connect`/`connect_ex` visszaállítása."""
    if not _eredeti:
        return
    socket.socket.connect, socket.socket.connect_ex = _eredeti.pop("connect"), _eredeti.pop("connect_ex")
