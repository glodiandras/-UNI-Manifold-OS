"""Az aranyhalmaz-tesztek közös segédei: a valódi `modulok/eval` betöltése álgyökérrel (álvault, ál-`var/`).

A termék a saját jegyzetekből, fotókból és videókból épült aranyhalmazokat nem szállítja (csak a `kod`, `kiegeszites`,
`matek`, `grafikon` adata van a repóban): ott a `kozos/arany.py` egy `hianyzik` állapotú üres halmazt ad, a feladatmodul
(a prompt és a pontozó) importálható marad. A valódi adatot igénylő teszt ilyenkor `[indokolt]` kihagyással fut, az
inline fixture-ös tesztek változatlanul lefutnak (`feladat(..., adat=False)`, illetve `aranyt_igenyel`)."""
import sys
import unittest

from tests.helpers import REPO, alg_core

EVAL = REPO / "modulok" / "eval"
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))

HIANYZIK_OK = "[indokolt] a szállított aranyhalmaz az F6 fázisban készül"
HIANYZIK_UTOTAG = "-hianyzik"


def eval_cfg(tmp: str):
    """Álgyökér, amelynek a `modulok` útja a repó valódi `modulok/` mappája → (config, gyökér, álvault)."""
    return alg_core(tmp, MOS_MODULOK=str(REPO / "modulok"))


def hianyzik(modul) -> bool:
    """Igaz, ha a feladatmodul aranyhalmaza nincs a repóban: az `ARANY` szótár `hianyzik` állapotú, vagy (a csak
    `parok.json`-t vagy más modul adatát használó feladatoknál) a `VERZIO` `-hianyzik` végű."""
    arany = getattr(modul, "ARANY", None)
    if isinstance(arany, dict) and (arany.get("hianyzik") or arany.get("allapot") == "hianyzik"):
        return True
    return str(getattr(modul, "VERZIO", "")).endswith(HIANYZIK_UTOTAG)


def feladat(cfg, nev: str, adat: bool = True):
    """A `modulok/eval/<nev>/feladat.py` betöltve. `adat=True` (alap): ha a feladat aranyhalmaza hiányzik, a teszt
    `unittest.SkipTest`-tel kimarad; `adat=False`: a modul (prompt, pontozó) adat nélkül is kell a teszthez."""
    from core.modell import eval as ev
    modul = ev.feladat_modul(cfg, nev)
    if adat and hianyzik(modul):
        raise unittest.SkipTest(HIANYZIK_OK)
    return modul


def van_arany(nev: str, fajl: str = "arany.json") -> bool:
    """Igaz, ha a `modulok/eval/<nev>/<fajl>` adatfájl a repóban van (az `arany.json` vagy a keresés `parok.json`)."""
    return (EVAL / nev / fajl).is_file()


def aranyt_igenyel(*nevek: str, fajl: str = "arany.json"):
    """Dekorátor (teszt vagy osztály): kimarad, ha valamelyik megnevezett halmaz adatfájlja nincs a repóban."""
    return unittest.skipUnless(all(van_arany(n, fajl) for n in nevek), HIANYZIK_OK)


def rekord(tetel: dict, valasz, verzio: str = "teszt") -> dict:
    return {"id": tetel["id"], "verzio": verzio, "vart": tetel.get("vart"), "valasz": valasz, "mp": 0.1}
