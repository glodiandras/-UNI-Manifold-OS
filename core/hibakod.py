"""Stable error codes, scalar parameters and English wire fallbacks (F4).

Exception text stays compatible with existing Python callers. Only a public
error body uses the English catalog; a client may translate its code again.
"""
from __future__ import annotations

import math
import re

from .hibauzenetek import ANGOL

_HELYETTESITES = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def json_param(param: dict | None) -> dict:
    """Copy scalar parameters without serializing paths, exceptions or NaN as JSON values."""
    return {str(k): (v if v is None or isinstance(v, (str, int, bool))
                     or isinstance(v, float) and math.isfinite(v) else str(v))
            for k, v in (param or {}).items()}


def angol_uzenet(kod: str | None, param: dict | None = None, tartalek: str = "") -> str:
    """Substitute once: braces inside file names or exception details stay literal."""
    sablon = ANGOL.get(kod) if isinstance(kod, str) else None
    if sablon is None:
        return tartalek
    p = json_param(param)
    if any(m[1] not in p for m in _HELYETTESITES.finditer(sablon)):
        return "The operation could not be completed. Try again."
    def csere(m):
        ertek = p.get(m[1])
        if m[1] not in p:
            return m[0]
        return str(ertek).lower() if isinstance(ertek, bool) else str(ertek)
    return _HELYETTESITES.sub(csere, sablon)


def kodol(kivetel, kod: str, param: dict | None = None):
    """Attach translation metadata without changing the exception type or text."""
    kivetel.hiba_kod = kod
    kivetel.hiba_param = json_param(param)
    return kivetel
