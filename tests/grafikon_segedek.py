"""Közös segédek a C35b-mag tesztjeihez: a grafikon-csomag import-útja, folyamaton belüli felismerő (SymPy a tesztfolyamatban —
éles úton a CAS-homokozó gyermekében fut), és a gépi-írás szolgáltatást hívó kliens-illesztő."""
import sys

from tests.helpers import REPO

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from core import gepi_kliens, vaultio  # noqa: E402
from core.utvonalak import HttpError  # noqa: E402
from grafikon import felismeres as R  # noqa: E402
from grafikon import formatum as F  # noqa: E402
from grafikon import muveletek as M  # noqa: E402

FM = "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"


def javaslat_szotar(j) -> dict:
    """A `felismeres.Javaslat` a burok (`grafikon.felismer_jegyzet`) alakjában: szótár a jegyzetbeli hellyel."""
    return {**M.javaslat_szotar(j), "sor": j.sor, "veg_sor": j.veg_sor, "blokk_kovetkezik": j.blokk_kovetkezik}


def felismero(szoveg: str) -> list[dict]:
    return [javaslat_szotar(j) for j in R.felismer_jegyzet(szoveg)]


def kimenet_blokk(*sorok: str) -> str:
    return "```plot\n" + "".join(s + "\n" for s in sorok) + "```\n"


class SzolgaltatasKliens:
    """A `core.gepi_kliens` felülete a valódi `GepiIras` szolgáltatásra kötve (HTTP nélkül): ugyanazok a hibakódok és adatok."""
    GepiHiba = gepi_kliens.GepiHiba
    csere = staticmethod(gepi_kliens.csere)
    uj = staticmethod(gepi_kliens.uj)

    def __init__(self, gepi, vault, proba_hiba=None):
        self.G, self.V = gepi, vault
        self.hivasok: list[dict] = []
        self.proba_hiba = proba_hiba

    def uj_kor(self, elotag):
        return gepi_kliens.uj_kor(elotag)

    def olvas(self, ut):
        try:
            return self.V.read(ut)
        except vaultio.NotFound as e:
            raise self.GepiHiba(404, str(e)) from None

    def ir(self, kor, tetel, forras, muveletek, uzenet=None, proba=None, *, modell, dontes=None, varakozas_mp=30, url=None,
           esemeny=None):
        # a valódi kliens szerződése (C29.8, D9): a `modell` kulcsszó kötelező, és a kérésbe kerül (determinisztikusan `None`)
        body = {"kor": kor, "tetel": tetel, "forras": forras, "muveletek": muveletek, "proba": bool(proba), "modell": modell}
        if uzenet:
            body["uzenet"] = uzenet
        if dontes:
            body["dontes"] = dontes
        if esemeny is not None:             # C20b: a tétel tracker-eseménye (a core a commit után rögzíti)
            body["esemeny"] = esemeny
        self.hivasok.append(body)
        if proba and self.proba_hiba:
            raise self.proba_hiba
        try:
            return self.G.ir(body)
        except HttpError as e:
            raise self.GepiHiba(e.code, str(e), e.data) from None
        except vaultio.Conflict as e:
            raise self.GepiHiba(409, str(e), {"utkozes": True}) from None
        except vaultio.NotFound as e:
            raise self.GepiHiba(404, str(e)) from None
        except vaultio.Invalid as e:
            raise self.GepiHiba(400, str(e)) from None


class HamisHomokozo:
    """A homokozó gyermekének belépési pontjait folyamaton belül hívja (a valódi `sandbox-exec` csak macOS-en); naplóz."""

    def __init__(self, hiba=None):
        self.beall = {"idokorlat_s": 10.0, "lepes_idokorlat_s": 3.0}
        self.hivasok: list[dict] = []
        self.hiba = hiba

    def futtat(self, feladatok, idokorlat_s=None, memoria_mb=None):
        ki = []
        for f in feladatok:
            self.hivasok.append(dict(f))
            if self.hiba:
                ki.append({"allapot": self.hiba, "ertek": None, "uzenet": f"hamis {self.hiba}", "mp": 0.0})
                continue
            fv = {"grafikon.felismeres": M.felismeres, "grafikon.elemzes": M.elemzes, "grafikon.egyezes": M.egyezes}[f["nev"]]
            try:
                ki.append({"allapot": "ok", "ertek": fv(**f["args"]), "uzenet": "", "mp": 0.0})
            except Exception as e:                       # a gyermek a hibát `hiba` állapotban adja
                ki.append({"allapot": "hiba", "ertek": None, "uzenet": f"{type(e).__name__}: {e}", "mp": 0.0})
        return ki
