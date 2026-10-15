"""Közös fixture a C28a tesztjeihez (`test_felkeszultseg_adat/osszesit/forras/api`): álvault a vault valós alakjaival
(felkészülési jegyzet PDF-oldalakkal és `NN` témákkal, témajegyzetek, kártya-kísérőjegyzetek), ál-naptár (EventKit-segéd),
szintetikus kártyák (a C23a valódi `szinkron`/`utemezo` útján), tracker-sorok és kvízeredmények. A valódi vaulthoz,
`var/`-hoz és `pos.sqlite`-hoz a teszt nem nyúl."""
import unittest
from datetime import datetime, timedelta, timezone

from core import naptar, szemelyes_db
from core.felkeszultseg import forrasok
from core.naptar_seged import Seged
from modulok.kartya import formatum, szinkron, utemezo
from tests import budapest_idozona
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit
from tests.naptar_segedek import AlSeged, esemeny as ev, naptar as nt

TZ = timezone(timedelta(hours=2))
MOST = datetime(2026, 10, 3, 12, 0, tzinfo=TZ)            # szombat
DOLGOZAT_NAP = "2026-10-07"

PDF = "M07 - Tankönyvek/11 - Matematika.pdf"
FELK = "X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-07 - Matematika.md"
T1 = "M06 - Exponenciális/Elmélet/01 - Hatvány.md"
T2 = "M06 - Exponenciális/Elmélet/02 - Gyökvonás.md"
T3 = "M06 - Exponenciális/Elmélet/03 - Logaritmus.md"
KARTYA_MAPPA = "ATTCHMNTS - cards"

FAJLOK = {
    FELK: ("---\nTags:\n  - Active-recall\nSource:\n  - \"[[11 - Matematika.pdf#page=18]]\"\n  - \"[[11 - Matematika.pdf#page=19]]\"\n"
           "  - \"[[11 - Matematika.pdf#page=28]]\"\nStatus:\nNN:\n  - \"[[01 - Hatvány]]\"\n  - \"[[02 - Gyökvonás]]\"\n"
           "  - \"[[03 - Logaritmus]]\"\nCanvas:\n---\n# Készülés\n"),
    T1: "# Hatvány\nA hatvány definíciója.\n",
    T2: "# Gyökvonás\nAz n-edik gyök.\n",
    T3: "# Logaritmus\nA logaritmus.\n",
    PDF: b"%PDF-1.4\n%fake\n",
}

NAPTARAK = [nt("HAT", "Deadlines & Exams"), nt("ORA", "Órarend"), nt("TAN", "Studying")]
ESEMENYEK = [ev("d1", "HAT", f"{DOLGOZAT_NAP}T10:00:00+02:00", f"{DOLGOZAT_NAP}T10:45:00+02:00", "Matek témazáró")]


def kisero(forras_ut: str, *kartyak) -> str:
    """A kísérőjegyzet szövege: `kartyak` = (azonosító, kérdés, válasz, forrás-link)."""
    return formatum.ir([formatum.Kartya(k, v, a, f) for a, k, v, f in kartyak], [forras_ut.rsplit("/", 1)[-1][:-3]])


class Alap(unittest.TestCase):
    """Álvault + index + ál-naptár. `naptar_van=False`: nincs pos.sqlite (a hiányzó adat tesztjeihez)."""
    FAJLOK = FAJLOK
    NAPTARAK = NAPTARAK
    ESEMENYEK = ESEMENYEK
    naptar_van = True

    def setUp(self):
        budapest_idozona(self)
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.al = AlSeged(self._t.name, {"naptarak": list(self.NAPTARAK), "esemenyek": [dict(e) for e in self.ESEMENYEK]})
        self.cfg, self.root, self.v = alg_core(self._t.name, **self.al.env())
        for rp, t in self.FAJLOK.items():
            ir(self.v, rp, t, "wb" if isinstance(t, bytes) else "w")
        if self.naptar_van:
            naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
            # A szinkron `vege` mezőjét a core a valós órával írja (`core/naptar.py`): a „régi naptár” tesztek a rögzített
            # `MOST`-hoz kötik, hogy ne a naptári dátum előrehaladtával változzon az eredmény.
            with szemelyes_db.iro(self.cfg) as c:
                c.execute("UPDATE import_futas SET vege=? WHERE forras=?", (MOST.isoformat(timespec="seconds"), naptar.FORRAS))
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self._forrasok = dict(forrasok._FORRASOK)
        forrasok._FORRASOK.clear()
        self.addCleanup(lambda: (forrasok._FORRASOK.clear(), forrasok._FORRASOK.update(self._forrasok)))
        self.sched = utemezo.utemezo(self.cfg, fuzz=False)

    # ---- kártyák (a C23a valódi útján)

    def kartyak(self, forras_ut: str, *kartyak, most=None) -> None:
        """Kísérőjegyzet a `forras_ut` témához + szinkron; `kartyak` = (azonosító, kérdés, válasz[, forrás-link])."""
        nev = forras_ut.rsplit("/", 1)[-1][:-3]
        sorok = [(a, k, v, (f[0] if f else f"{nev}#^m-1a2b")) for a, k, v, *f in kartyak]
        ir(self.v, f"{KARTYA_MAPPA}/{nev} — kártyák.md", kisero(forras_ut, *sorok))
        szinkron.szinkron(self.cfg, most=most or MOST.astimezone(timezone.utc))
        self.ix.frissit([f"{KARTYA_MAPPA}/{nev} — kártyák.md"])

    def valasz(self, azon: str, jegy: int, mikor: datetime) -> dict:
        return utemezo.valaszol(self.cfg, azon, jegy, most=mikor, sched=self.sched)

    # ---- tracker

    def aktiv(self, nap: str, ut: str, mp: int) -> None:
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("INSERT INTO tr_aktiv (nap, ut, tantargy, mp) VALUES (?,?,?,?) "
                      "ON CONFLICT(nap, ut) DO UPDATE SET mp = mp + excluded.mp", (nap, ut, "Matematika", mp))

    # ---- kvíz

    def kviz(self, *eredmenyek: forrasok.KvizEredmeny) -> None:
        forrasok.regisztral_kviz_forras("teszt", lambda cfg, tol, ig: list(eredmenyek))

    def adatok(self, most=MOST):
        from core.felkeszultseg import adat
        return adat.Adatok(self.cfg, self.ix, most)
