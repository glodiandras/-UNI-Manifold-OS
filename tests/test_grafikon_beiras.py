"""C35b-mag: a ```plot automatikus beírása a VALÓDI gépi-írás szolgáltatáson át (`core/gepi_iras.py`, álvaulton): egy jegyzet =
egy tétel = egy gépi commit (`Mos-Forras: mos-plot`), alap-hash-es csere, nyitott mentetlen dokumentumba nem ír, a visszavonás
bájtra visszaad, és a tiltólista (5. döntés): a törölt blokk képlete nem kap újat — a visszavonás és a kézi szerkesztés nem tiltólistáz."""
import unittest

from core import frame, gepi_iras, plot_allapot, snapshot, vaultio
from core.tulajdonsagok import Tulajdonsagok
from tests.grafikon_segedek import FM, F, HamisHomokozo, SzolgaltatasKliens, felismero
from tests.helpers import alg_core, ir, tmpdir

from grafikon import beiras as B  # noqa: E402

UT = "T01/Függvények.md"
JEGYZET = FM + "# Függvények\n\nA parabola:\n\n$$y = x^2$$\n\nA másik: $y = 3x - 1$ egyenes.\n\nVége.\n"


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, UT, JEGYZET)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.mentetlen: set = set()
        self.V = vaultio.Vault(self.cfg)
        self.G = gepi_iras.GepiIras(self.cfg, self.V, Tulajdonsagok(self.cfg, None), mentetlen=lambda: self.mentetlen,
                                    varakozas_mp=0.3)
        self.kliens = SzolgaltatasKliens(self.G, self.V)
        self.tilt, self.napl = plot_allapot.Tiltolista(self.cfg), plot_allapot.Beirasok(self.cfg)
        self.beiro = B.Beiro(self.kliens, felismero, self.tilt, self.napl, varakozas_mp=0.1)

    def olvas(self, ut=UT) -> str:
        return (self.v / ut).read_text(encoding="utf-8")

    def visszavont(self) -> set:
        return {c.trailers["Mos-Visszavon"] for c in self.repo.log(50) if "Mos-Visszavon" in c.trailers}


class Beiras(Alap):
    def test_egy_tetel_egy_gepi_commit(self):
        r = self.beiro.jegyzet(UT)
        self.assertEqual((r["allapot"], len(r["beirt"]), r["kihagyva"]), ("kesz", 2, []))
        uj = self.olvas()
        self.assertEqual([b.abra.elemek[0].kifejezes for b in F.blokkok(uj)], ["x^2", "3x - 1"])
        self.assertTrue(uj.startswith(FM))                                       # a frontmatter bájtra ugyanaz
        c = self.repo.log(2)[0]
        self.assertEqual(c.sha, r["sha"])
        self.assertEqual(self.repo.changed_files(c.sha), [UT])
        self.assertEqual((c.trailers["Mos-Forras"], c.trailers["Mos-Tetel"]), ("mos-plot", UT))
        self.assertRegex(c.trailers["Mos-Kor"], r"^PLOT-\d{8}-\d{6}")
        self.assertEqual(self.repo.log(2)[1].trailers["Mos-Forras"], "kezi")     # az alap külön commit: egy új gépi commit született
        self.assertEqual([x["kulcs"] for x in self.napl.lista()], [b["kulcs"] for b in r["beirt"]])
        self.assertTrue(all(x["sha"] == r["sha"] for x in self.napl.lista()))

    def test_masodszor_nem_ir(self):
        self.beiro.jegyzet(UT)
        fej = self.repo.git("rev-parse", "HEAD").stdout
        r = self.beiro.jegyzet(UT)
        self.assertEqual(r["allapot"], "nincs_teendo")
        self.assertEqual(self.repo.git("rev-parse", "HEAD").stdout, fej)
        self.assertEqual({k["ok"] for k in r["kihagyva"]}, {"van_blokk"})

    def test_visszavonas_bajtra_visszaad(self):
        eredeti = (self.v / UT).read_bytes()
        r = self.beiro.jegyzet(UT)
        self.repo.undo_commit(r["sha"])
        self.assertEqual((self.v / UT).read_bytes(), eredeti)

    def test_status_es_frontmatter_erintetlen(self):
        ut = "T01/Kesz.md"
        ir(self.v, ut, "---\nTags:\nSource:\nStatus: Completed\nNN:\nCanvas:\n---\n# K\n\n$$y = x^2$$\n")
        self.repo.commit("kesz", {"Mos-Forras": "kezi"})
        r = self.beiro.jegyzet(ut)
        self.assertEqual(r["allapot"], "kesz")
        self.assertIn("Status: Completed\n", self.olvas(ut))

    def test_nyitott_mentetlen_dokumentumba_nem_ir(self):
        self.mentetlen = {UT}
        elotte = self.olvas()
        r = self.beiro.jegyzet(UT)
        self.assertEqual(r["allapot"], "elhalasztva")
        self.assertEqual((self.olvas(), self.napl.lista()), (elotte, []))
        self.mentetlen = set()                                                     # a felhasználó mentett: a következő futás ír
        self.assertEqual(self.beiro.jegyzet(UT)["allapot"], "kesz")

    def test_kozben_megvaltozott_fajl_utkozes(self):
        def zavaro(szoveg):
            (self.v / UT).write_text(szoveg + "\nközben írt sor\n", encoding="utf-8")
            return felismero(szoveg)
        b = B.Beiro(self.kliens, zavaro, self.tilt, self.napl, varakozas_mp=0.1)
        r = b.jegyzet(UT)
        self.assertEqual(r["allapot"], "utkozes")
        self.assertEqual(F.blokkok(self.olvas()), [])
        self.assertEqual(self.napl.lista(), [])

    def test_nincs_ellenorizheto_nem_ir(self):
        b = B.Beiro(self.kliens, lambda sz: [{"allapot": "nem_ellenorizheto", "bizonyossag": "ismeretlen", "ok": "homokozó: tiltott"}],
                    self.tilt, self.napl)
        r = b.jegyzet(UT)
        self.assertEqual(r["allapot"], "nem_ellenorizheto")
        self.assertEqual(self.kliens.hivasok, [])

    def test_nincs_jegyzet(self):
        self.assertEqual(self.beiro.jegyzet("T01/Nincs.md")["allapot"], "nincs_jegyzet")

    def test_proba_mod_nem_naploz(self):
        class Proba(SzolgaltatasKliens):                                           # Linuxon nincs APFS-klón: a hívás paramétere a tárgy
            def ir(self, *a, proba=None, **k):
                self.hivasok.append({"proba": proba})
                return {"ok": True, "valtozas": True, "sha": "x" * 40, "proba": True}
        b = B.Beiro(Proba(self.G, self.V), felismero, self.tilt, self.napl, proba=True)
        r = b.jegyzet(UT)
        self.assertEqual((r["allapot"], b.kliens.hivasok), ("kesz", [{"proba": True}]))
        self.assertEqual(self.napl.lista(), [])                                    # a próba nem a valódi vault: nincs napló
        self.assertEqual(F.blokkok(self.olvas()), [])


class Tiltolista(Alap):
    def ellenoriz(self):
        return B.torles_ellenorzes(self.kliens, self.tilt, self.napl, self.visszavont())

    def test_torolt_blokk_tiltolistara_kerul_es_nem_ir_ujat(self):
        eredeti = self.olvas()
        self.beiro.jegyzet(UT)
        (self.v / UT).write_text(eredeti, encoding="utf-8")                        # a felhasználó törölte mindkét blokkot
        self.assertEqual({d["dontes"] for d in self.ellenoriz()}, {"torolve"})
        self.assertEqual(len(self.tilt.lista()), 2)
        self.assertEqual(self.napl.lista(), [])
        self.assertTrue(all(t["ut"] == UT for t in self.tilt.lista()))
        r = self.beiro.jegyzet(UT)                                                 # a törölt képlet nem kap újat
        self.assertEqual((r["allapot"], {k["ok"] for k in r["kihagyva"]}), ("nincs_teendo", {"tiltolista"}))
        self.assertEqual(self.olvas(), eredeti)

    def test_egy_blokk_torlese_csak_azt_tiltja(self):
        r = self.beiro.jegyzet(UT)
        uj = self.olvas()
        masodik = F.blokkok(uj)[1]
        (self.v / UT).write_text(uj[:masodik.kezdo] + uj[masodik.veg:].lstrip("\n"), encoding="utf-8")
        d = {x["kulcs"]: x["dontes"] for x in self.ellenoriz()}
        self.assertEqual(sorted(d.values()), ["megvan", "torolve"])
        (tiltott,) = self.tilt.lista()
        self.assertEqual(tiltott["kulcs"], r["beirt"][1]["kulcs"])
        self.assertEqual([x["kulcs"] for x in self.napl.lista()], [r["beirt"][0]["kulcs"]])     # az érintetlen blokk naplóban marad

    def test_visszavonas_nem_tiltolistaz(self):
        r = self.beiro.jegyzet(UT)
        self.repo.undo_commit(r["sha"])
        self.assertEqual({d["dontes"] for d in self.ellenoriz()}, {"visszavonva"})
        self.assertEqual((self.tilt.lista(), self.napl.lista()), ([], []))
        self.assertEqual(self.beiro.jegyzet(UT)["allapot"], "kesz")                # a visszavont blokk újra beírható

    def test_kezi_szerkesztes_nem_torles(self):
        self.beiro.jegyzet(UT)
        uj = self.olvas().replace("y = x^2\n```", "y = x^2 + 5\n```")
        (self.v / UT).write_text(uj, encoding="utf-8")
        self.assertIn("szerkesztve", {d["dontes"] for d in self.ellenoriz()})
        self.assertEqual(self.tilt.lista(), [])

    def test_levetel_a_tiltolistarol_visszaengedi(self):
        eredeti = self.olvas()
        self.beiro.jegyzet(UT)
        (self.v / UT).write_text(eredeti, encoding="utf-8")
        self.ellenoriz()
        for t in self.tilt.lista():
            self.assertTrue(self.tilt.levesz(t["kulcs"]))
        self.assertEqual(self.beiro.jegyzet(UT)["allapot"], "kesz")

    def test_atnevezett_jegyzet_rekordja_marad(self):
        self.beiro.jegyzet(UT)
        (self.v / UT).rename(self.v / "T01/Új név.md")
        self.assertEqual({d["dontes"] for d in self.ellenoriz()}, {"nincs_jegyzet"})
        self.assertEqual(len(self.napl.lista()), 2)                                # nem döntünk törlésről


class Allapot(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)

    def test_tiltolista_alakja_es_ujrafelvetel(self):
        t = plot_allapot.Tiltolista(self.cfg)
        self.assertTrue(t.felvesz("0123456789abcdef", "A.md"))
        self.assertFalse(t.felvesz("0123456789abcdef", "B.md"))                    # a meglévő rekord nem íródik át
        self.assertEqual([(x["kulcs"], x["ut"]) for x in t.lista()], [("0123456789abcdef", "A.md")])
        self.assertEqual(t.kulcsok(), frozenset({"0123456789abcdef"}))
        with self.assertRaises(ValueError):
            t.felvesz("nem-hexa", "A.md")
        self.assertEqual(sorted(p.name for p in self.cfg.path("state").glob("*manifold-tmp")), [])   # nem marad ideiglenes fájl

    def test_serult_allapot_zarva_hibazik(self):
        (self.cfg.path("state") / "plot-tiltolista.json").write_text("{nem json", encoding="utf-8")
        t = plot_allapot.Tiltolista(self.cfg)
        with self.assertRaises(plot_allapot.AllapotHiba):
            t.kulcsok()
        with self.assertRaises(plot_allapot.AllapotHiba):
            t.felvesz("0123456789abcdef", "A.md")                                  # nem írja felül a sérültet üres listával
        self.assertEqual((self.cfg.path("state") / "plot-tiltolista.json").read_text(encoding="utf-8"), "{nem json")
        (self.cfg.path("state") / "plot-tiltolista.json").write_text("[]", encoding="utf-8")      # rossz alak
        with self.assertRaises(plot_allapot.AllapotHiba):
            t.lista()

    def test_beirasok_korlat_es_csere(self):
        n = plot_allapot.Beirasok(self.cfg)
        n.hozzaad([{"ut": "A.md", "kulcs": "a" * 16, "blokk": "y = x", "sha": "1"}])
        n.hozzaad([{"ut": "A.md", "kulcs": "a" * 16, "blokk": "y = x", "sha": "2"}])           # ugyanaz a (út, kulcs): csere
        self.assertEqual([x["sha"] for x in n.lista()], ["2"])
        n.torol("A.md", "a" * 16)
        self.assertEqual(n.lista(), [])

    def test_automatika_allapot(self):
        a = plot_allapot.Automatika(self.cfg)
        a.ment("A.md", 12.5, ["mondat"], ["k" * 16], "u")
        self.assertEqual(a.olvas()["A.md"]["mtime"], 12.5)
        a.elfelejt("A.md")
        self.assertEqual(a.olvas(), {})


if __name__ == "__main__":
    unittest.main()
