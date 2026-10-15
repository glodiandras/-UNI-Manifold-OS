"""A riport és az Asszisztens nem érinti a szerkesztő útját (C30a; 2. döntés, D8, CHATKALAUZ C30): az írási és az indexelő út
nem importálja őket, az Asszisztens nem ír a vaultba és nem tölt modellt, a végpontok nem számolnak soron belül. A gépelési
késleltetés mérése a valódi appban a C30b kapuja (`tests/perf_asszisztens.py`: az írási út késleltetése számítás közben)."""
import ast
import unittest
from pathlib import Path

from core.asszisztens.szolgalat import HigieniaSzolgalat
from core.asszisztens.allapot import Allapot
from core.higienia import Higienia
from core.tulajdonsagok import Tulajdonsagok
from tests.helpers import REPO, tmpdir
from tests.index_segedek import alvault, index_indit

CORE = REPO / "core"
# a szerkesztő mentési és indexelő útja, a gépi írás és a pillanatkép-keret: ezek nem függhetnek az Asszisztenstől
SZERKESZTO_UTJA = ["vaultio.py", "gepi_iras.py", "frame.py", "snapshot.py", "mentes.py", "atnevezes.py", "tartos.py", "events.py",
                   "websocket.py", "utkapu.py", "tulajdonsagok.py", "elozmeny.py", *(f"index/{p.name}" for p in (CORE / "index").glob("*.py"))]
ASSZISZTENS = sorted((CORE / "asszisztens").glob("*.py")) + [CORE / "higienia.py"]


def importok(p: Path) -> set[str]:
    ki = set()
    for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            ki |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            if n.module == "vaultio" and n.level == 1 and [a.name for a in n.names] == ["NotFound"]:
                continue                                    # csak a 404-es kivétel osztálya (a riport ismeretlen útja)
            ki.add(("." * n.level) + (n.module or ""))
            ki |= {("." * n.level) + (n.module or "") + "." + a.name for a in n.names}
    return ki


class ImportGrafTest(unittest.TestCase):
    def test_a_szerkeszto_utja_nem_importalja_az_asszisztenst_es_a_higieniat(self):
        for ut in SZERKESZTO_UTJA:
            for i in importok(CORE / ut):
                self.assertNotIn("asszisztens", i, f"{ut} importálja: {i}")
                self.assertNotIn("higienia", i, f"{ut} importálja: {i}")

    def test_a_ma_oldal_csak_getattr_en_at_er_el_az_asszisztenshez(self):
        self.assertFalse([i for i in importok(CORE / "ma.py") if "asszisztens" in i or "higienia" in i])

    def test_az_asszisztens_nem_ir_a_vaultba_es_nem_tolt_modellt(self):
        tiltott = ("vaultio", "gepi_iras", "gepi_kliens", "frame", "snapshot", "atnevezes", "modell.betolto", "modell.kliens",
                   "modell.worker", "modell.motor", "tasks")
        for p in ASSZISZTENS:
            for i in importok(p):
                resz = i.lstrip(".")
                self.assertFalse(any(resz == t or resz.startswith(t + ".") or resz.endswith("." + t) for t in tiltott),
                                 f"{p.name} importálja: {i}")

    def test_nincs_sajat_adatbazis_kapcsolat_es_nincs_fajlirasi_hivas(self):
        for p in ASSZISZTENS:
            forras = p.read_text(encoding="utf-8")
            if p.name == "higienia.py":                         # a CLI csak olvasva nyitja az indexet (`tar.nyit`)
                continue
            self.assertNotIn("sqlite3.connect", forras, p.name)
            self.assertNotIn(".write_text(", forras, p.name)
            self.assertNotIn("os.replace(", forras, p.name)

    def test_az_allapotfajl_az_egyetlen_fajlirasi_hely(self):
        """A `tartos.atomi_ir` hívása csak az `allapot.py`-ban van: minden más modul a `Allapot.modosit`-on át ír."""
        hivok = [p.name for p in ASSZISZTENS if "atomi_ir(" in p.read_text(encoding="utf-8")]
        self.assertEqual(hivok, ["allapot.py"])


class NemSzamolSoronBelulTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        cfg, self.v = alvault(self._t.name, {"A.md": "[[Nincs]]\n"})
        self.cfg = cfg
        self.ix, _ = index_indit(cfg)
        self.addCleanup(self.ix.leallit)
        h = Higienia(cfg, self.ix, Tulajdonsagok(cfg, self.ix))
        self.szamolasok = 0
        eredeti = h.riport

        def riport(*a, **k):
            self.szamolasok += 1
            return eredeti(*a, **k)
        h.riport = riport
        self.sz = HigieniaSzolgalat(cfg, self.ix, h, Allapot(cfg), aktiv=lambda: False)

    def test_az_osszegzes_es_a_ma_szakasz_nem_szamol(self):
        for _ in range(5):
            self.sz.osszegzes()
            self.sz.ma()
        self.assertEqual(self.szamolasok, 0)

    def test_az_indexeles_nem_inditja_a_szamitast(self):
        """Az index írása (mentés → `generacio`) csak a szolgáltatás következő *tickjén* számít: a számítás nem a mentés szálán fut."""
        from tests.helpers import ir
        ir(self.v, "B.md", "[[A]]\n")
        self.assertTrue(self.ix.frissit(["B.md"]))
        self.assertEqual(self.szamolasok, 0)

    def test_aktiv_hasznalat_alatt_a_tick_nem_szamol(self):
        self.sz.aktiv = lambda: True
        for _ in range(3):
            self.assertEqual(self.sz.tick(), "aktiv")
        self.assertEqual(self.szamolasok, 0)


if __name__ == "__main__":
    unittest.main()
