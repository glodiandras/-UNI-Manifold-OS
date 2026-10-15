"""A tracker útvonalainak átnevezés-követése (C28a, T063): olvasáskor, a vault pillanatkép-tárolójának átnevezés-
commitjaiból. A `tr_*` táblák nem módosulnak; a régi néven rögzített idő a jegyzet mai útjához számít."""
import os
import unicodedata
import unittest
from datetime import date, timedelta

from core import atnevezes, snapshot, vaultio
from core.felkeszultseg import atnevezes as kovetes
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit

KEZDET = "2000-01-01"


class Alap(unittest.TestCase):
    def setUp(self):
        kovetes._GYORSITOTAR.clear()
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()

    def commit(self, ut_lista, uzenet="x", kor="SZERK-20261002-100000"):
        return self.repo.commit_machine(uzenet, {"Mos-Kor": kor, "Mos-Forras": "pult-szerkeszto"}, ut_lista)

    def ir(self, ut, szoveg="a\n"):
        ir(self.v, ut, szoveg)
        return self.commit([ut])

    def nevez(self, regi, uj, szoveg=None):
        (self.v / uj).parent.mkdir(parents=True, exist_ok=True)
        os.rename(self.v / regi, self.v / uj)
        return self.commit([regi, uj], kor="ATNEV-20261002-120000")


class TerkepTest(Alap):
    def test_nincs_tarolo_ures_terkep_figyelmeztetessel(self):
        t2 = tmpdir()
        self.addCleanup(t2.cleanup)
        cfg, _, _ = alg_core(t2.name)                          # a tároló nincs létrehozva
        t = kovetes.terkep(cfg, KEZDET)
        self.assertEqual(t.aliasok("J.md"), {"J.md"})
        self.assertIn("pillanatkép-tároló", t.figyelmeztetes)

    def test_nincs_kezdet_ures_terkep(self):
        self.ir("Regi.md")
        self.nevez("Regi.md", "Uj.md")
        t = kovetes.terkep(self.cfg, None)
        self.assertEqual(t.aliasok("Uj.md"), {"Uj.md"})
        self.assertIsNone(t.figyelmeztetes)

    def test_egyszeru_atnevezes(self):
        self.ir("Regi.md")
        self.nevez("Regi.md", "Uj.md")
        t = kovetes.terkep(self.cfg, KEZDET)
        self.assertEqual(t.korabbi("Uj.md"), ["Regi.md"])
        self.assertEqual(t.aliasok("Uj.md"), {"Regi.md", "Uj.md"})
        self.assertEqual(t.aliasok("Regi.md"), {"Regi.md"})        # a régi úton már nincs jegyzet

    def test_lanc_a_b_c(self):
        self.ir("A.md")
        self.nevez("A.md", "B.md")
        self.nevez("B.md", "C.md")
        self.assertEqual(kovetes.terkep(self.cfg, KEZDET).aliasok("C.md"), {"A.md", "B.md", "C.md"})

    def test_visszavonas_a_b_a(self):
        """Az átnevezés visszavonása revert-commit, ami visszanevezi: a B alatt rögzített idő is az A-hoz tartozik."""
        self.ir("A.md")
        sha = self.nevez("A.md", "B.md")
        self.repo.undo_commit(sha)
        self.assertTrue((self.v / "A.md").exists())
        t = kovetes.terkep(self.cfg, KEZDET)
        self.assertEqual(t.aliasok("A.md"), {"A.md", "B.md"})

    def test_mappa_atnevezes_minden_fajl(self):
        self.ir("Regi mappa/X.md", "x\n")
        self.ir("Regi mappa/Y.md", "y\n")
        os.rename(self.v / "Regi mappa", self.v / "Uj mappa")
        self.commit(["Regi mappa/X.md", "Regi mappa/Y.md", "Uj mappa/X.md", "Uj mappa/Y.md"], kor="ATNEV-20261002-130000")
        t = kovetes.terkep(self.cfg, KEZDET)
        self.assertEqual(t.korabbi("Uj mappa/X.md"), ["Regi mappa/X.md"])
        self.assertEqual(t.korabbi("Uj mappa/Y.md"), ["Regi mappa/Y.md"])

    def test_nem_atnevezes_commit_nem_szamit(self):
        self.ir("J.md", "egy\n")
        self.ir("J.md", "kettő\n")
        self.ir("M.md")
        self.assertEqual(kovetes.terkep(self.cfg, KEZDET).aliasok("J.md"), {"J.md"})

    def test_a_kezdet_elotti_atnevezes_kimarad(self):
        self.ir("Regi.md")
        self.nevez("Regi.md", "Uj.md")
        jovo = (date.today() + timedelta(days=400)).isoformat()      # a git dátum-elemzője a távoli jövőt nem szereti
        self.assertEqual(kovetes.terkep(self.cfg, jovo).aliasok("Uj.md"), {"Uj.md"})

    def test_nfd_nev_nfc_lesz(self):
        regi = unicodedata.normalize("NFD", "Ütőér.md")
        self.ir(regi)
        self.nevez(regi, "Uj.md")
        t = kovetes.terkep(self.cfg, KEZDET)
        self.assertEqual(t.korabbi("Uj.md"), [unicodedata.normalize("NFC", "Ütőér.md")])

    def test_a_gyorsitotar_a_head_valtozasara_frissul(self):
        self.ir("A.md")
        self.nevez("A.md", "B.md")
        elso = kovetes.terkep(self.cfg, KEZDET)
        self.assertEqual(elso.aliasok("B.md"), {"A.md", "B.md"})
        self.assertIs(kovetes.terkep(self.cfg, KEZDET), elso)              # azonos HEAD: ugyanaz a térkép
        self.nevez("B.md", "C.md")
        self.assertEqual(kovetes.terkep(self.cfg, KEZDET).aliasok("C.md"), {"A.md", "B.md", "C.md"})

    def test_olvasas_nem_ir_a_vaultba(self):
        self.ir("A.md")
        self.nevez("A.md", "B.md")
        elotte = {p.name: p.read_bytes() for p in self.v.rglob("*.md")}
        kovetes.terkep(self.cfg, KEZDET)
        self.assertEqual({p.name: p.read_bytes() for p in self.v.rglob("*.md")}, elotte)
        self.assertEqual(self.repo.dirty(), [])


class ValodiAtnevezesTest(unittest.TestCase):
    """Végponttól végpontig: a core saját átnevezése (link-átírással, gépi committal) követhető."""

    def test_a_core_atnevezese_koveto(self):
        kovetes._GYORSITOTAR.clear()
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, root, v = alg_core(t.name)
        ir(v, "Téma.md", "# Téma\n")
        ir(v, "Hivo.md", "[[Téma]]\n")
        repo = snapshot.repos(cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        a = atnevezes.Atnevezes(cfg, vaultio.Vault(cfg), ix, busy=lambda: False, publish=lambda e, **k: None)
        terv = a.terv("Téma.md", "Új téma.md")
        a.vegrehajt("Téma.md", "Új téma.md", terv["terv_hash"])
        self.assertEqual(kovetes.terkep(cfg, KEZDET).aliasok("Új téma.md"), {"Téma.md", "Új téma.md"})



class TrackerJegyzetListaTest(Alap):
    """C33 (T180): a statisztika jegyzet-listája a mostani úton csoportosít (olvasáskor, 50(c)): a régi néven gyűjtött idő
    az új névhez adódik, a `tr_aktiv` sorai nem íródnak át."""

    def test_a_regi_neven_gyujtott_ido_az_uj_nevhez_adodik(self):
        from datetime import datetime

        from core import tracker
        self.ir("M01 - Matek/Regi.md")
        tr = tracker.Tracker(self.cfg, mikor=lambda: datetime(2026, 10, 3, 10, 0))
        tr.fogad({"aktiv": [{"ut": "M01 - Matek/Regi.md", "mp": 40}]})
        self.nevez("M01 - Matek/Regi.md", "M01 - Matek/Uj.md")
        tr.fogad({"aktiv": [{"ut": "M01 - Matek/Uj.md", "mp": 25}, {"ut": "M01 - Matek/Mas.md", "mp": 50}]})
        j = tr.statisztika("2026-10-03", "2026-10-03")["jegyzetek"]
        self.assertEqual(j[0], {"ut": "M01 - Matek/Uj.md", "tantargy": "Mathematics", "aktiv_mp": 65,
                                "korabbi": ["M01 - Matek/Regi.md"]})
        self.assertEqual(j[1]["ut"], "M01 - Matek/Mas.md")
        with tr._olvaso() as c:                                       # a tr_aktiv érintetlen (50(c))
            utak = {r[0] for r in c.execute("SELECT ut FROM tr_aktiv")}
        self.assertIn("M01 - Matek/Regi.md", utak)


if __name__ == "__main__":
    unittest.main()
