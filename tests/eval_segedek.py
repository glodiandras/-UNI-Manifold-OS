"""Az aranyhalmaz-tesztek közös segédei: a valódi `modulok/eval` betöltése álgyökérrel (álvault, ál-`var/`)."""
import sys
from pathlib import Path

from tests.helpers import REPO, alg_core

EVAL = REPO / "modulok" / "eval"
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))


def eval_cfg(tmp: str):
    """Álgyökér, amelynek a `modulok` útja a repó valódi `modulok/` mappája → (config, gyökér, álvault)."""
    return alg_core(tmp, MOS_MODULOK=str(REPO / "modulok"))


def feladat(cfg, nev: str):
    from core.modell import eval as ev
    return ev.feladat_modul(cfg, nev)


def rekord(tetel: dict, valasz, verzio: str = "teszt") -> dict:
    return {"id": tetel["id"], "verzio": verzio, "vart": tetel.get("vart"), "valasz": valasz, "mp": 0.1}
