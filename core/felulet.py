"""A felület tartós állapota (C07): téma, elrendezés, nyitott fülek, legutóbbiak.

A héj nem tart meg böngészőadatot (`WKWebsiteDataStore.nonPersistent()`), ezért a felület állapota a core-on
át a `{felulet}` fájlba kerül (alapból `var/state/felulet.json`). A vaulthoz nem nyúl, pillanatkép nem kell;
az írás atomi csere, így megszakadt írás után a régi állapot marad. A tartalom a felületé: a core csak azt
ellenőrzi, hogy JSON-objektum, és nem túl nagy.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .config import Config
from .hibakod import kodol

MAX_MERET = 256 * 1024
_zar = threading.Lock()


class Hibas(ValueError):
    """Az állapot nem írható: nem objektum, vagy túl nagy."""


def _ut(cfg: Config) -> Path:
    return cfg.path("felulet")


def olvas(cfg: Config) -> dict:
    """Az utolsó mentett állapot; hiányzó vagy sérült fájlnál üres objektum (a felület az alapértékekből indul)."""
    try:
        d = json.loads(_ut(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def ir(cfg: Config, allapot) -> None:
    if not isinstance(allapot, dict):
        raise kodol(Hibas("az állapot JSON-objektum kell legyen"), "felulet.allapot_json_objektum_kell_legyen")
    adat = json.dumps(allapot, ensure_ascii=False, indent=1).encode("utf-8")
    if len(adat) > MAX_MERET:
        raise kodol(Hibas(f"túl nagy állapot ({len(adat)} bájt, legfeljebb {MAX_MERET})"), "felulet.tul_nagy_allapot_len_bajt", {"len": len(adat), "MAX_MERET": MAX_MERET})
    cel = _ut(cfg)
    with _zar:
        cel.parent.mkdir(parents=True, exist_ok=True)
        tmp = cel.with_name(f".{cel.name}.manifold-tmp")
        with open(tmp, "wb") as f:
            f.write(adat)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, cel)


def utvonalak(r) -> None:
    """A felület-állapot végpontjai az útvonal-regiszterben (C11a)."""
    r.get("/api/felulet/allapot", lambda k: {"allapot": olvas(k.app.cfg)})

    def mentes(k):
        ir(k.app.cfg, k.torzs().get("allapot"))
        return {"ok": True}
    r.put("/api/felulet/allapot", mentes)
