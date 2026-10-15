"""C35b-mag: a ```plot automatikus módja — a tiszta döntések (`modulok/grafikon/automatika.py`, a C26a közös mértékével), a futás
(csak olvas, az írás a `Beiro`-n át), a feladattípus (`core/grafikon_feladat.py`: `automatikus=True`, a kapu alatt) és az API."""
import json
import os
import unittest
from types import SimpleNamespace

from core import automatika as OA
from core import grafikon_api, plot_allapot, tasks, utvonalak
from core.modell import kapu
from core.utvonalak import HttpError
from tests.grafikon_segedek import FM, F, HamisHomokozo, felismero
from tests.helpers import alg_core, ir, tmpdir
from tests.test_grafikon_beiras import Alap as GepiAlap

from grafikon import automatika as AU  # noqa: E402
from grafikon import beiras as B  # noqa: E402
from grafikon import modell_ag as MA  # noqa: E402

SZOVEG = ("A függvények vizsgálata az analízis egyik alapfeladata, amelyben a grafikon segít. "
          "Az alábbi példában a másodfokú függvényt tekintjük, és megnézzük a zérushelyeit is.\n\n$$y = x^2 - 4$$\n\nKövetkezik a folytatás.\n")
UT = "T01/A.md"
CSEND = 11 * 60


def sor_(md, **kw):
    """Egy tárbeli sor a feldolgozott `md` változatról (a `Tar.kesz` mezői)."""
    return {"hash": "regi", "alap": json.dumps(sorted(OA.mondatok(md))), "ujjlenyomat": OA.forras_ujjlenyomat(md),
            "adat": json.dumps(AU.adat(md)), **kw}


class Dontes(unittest.TestCase):
    """A döntés a közös ütemezőé (`core.automatika.dont`); a grafikon fogyasztó két kampója: van képlet, új képlet."""

    def setUp(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        self.cfg, _, _ = alg_core(t.name)
        self.f = AU.fogyaszto(self.cfg)

    def dont(self, md=FM + SZOVEG, sor=None, mtime=0.0, most=CSEND, ut=UT, hash_="uj"):
        return OA.dont(self.f, ut, hash_, mtime, most, sor, lambda u: md)

    def test_fogyaszto_a_kozos_mertekkel(self):
        b = AU.Beallitas()
        self.assertEqual((self.f.nev, self.f.feladattipus, self.f.kuszob, self.f.csend_perc, self.f.min_hossz, self.f.koteg),
                         ("grafikon", "grafikon_automatikus", b.kuszob, b.csend_perc, b.min_hossz, b.max_jegyzet))
        self.assertFalse(self.f.onallo)                                               # az ütemező az utakat adja (K309)
        regi = dict(OA.REGISZTER)
        self.addCleanup(lambda: (OA.REGISZTER.clear(), OA.REGISZTER.update(regi)))
        OA.alap_fogyasztok(self.cfg)
        self.assertNotIn("grafikon", OA.REGISZTER)                                    # 80(a): alapból nem automatikus
        self.cfg.data.setdefault("grafikon", {}).setdefault("automatika", {})["be"] = True
        OA.alap_fogyasztok(self.cfg)
        self.assertNotIn("grafikon", OA.REGISZTER)  # CX-011: régi flag sem indíthat AI-t.
        self.assertEqual(self.f.tartalom_szuro.__name__, "van_keplet")
        self.assertEqual(self.f.kiegeszito.__name__, "uj_keplet")

    def test_uj_jegyzet_csend_utan(self):
        st, j = self.dont()
        self.assertEqual((st, j.ok), ("jelolt", "uj"))

    def test_sorrend_es_kizarasok(self):
        for kw, st in (({"ut": "T01/ATTCHMNTS - cards/X — kártyák.md"}, "szuro"),
                       ({"ut": ".obsidian/x.md"}, "szuro"),
                       ({"md": FM + "# T\n\nCsak szöveg, képlet nélkül, elég hosszan, hogy ne a rövidség döntsön róla.\n"}, "nem_kell"),
                       ({"md": "$y=x$"}, "rovid"),
                       ({"mtime": CSEND - 9 * 60 + 1}, "csend"),
                       ({"sor": {"tiltva": "x"}}, "tiltva")):
            self.assertEqual(self.dont(**kw)[0], st, kw)
        self.assertEqual(self.dont(mtime=CSEND - 10 * 60)[0], "jelolt")

    def test_alap_utan_valtozas(self):
        md = FM + SZOVEG
        sor = sor_(md)
        self.assertEqual(self.dont(md + "\nKicsi, rövid kiegészítés.\n", sor)[0], "nem_eleg")
        nagy = md + "\n".join(f"Új, hosszú magyarázó mondat száma {i}, amely sok új karaktert hoz a jegyzetbe." for i in range(12)) + "\n"
        st, j = self.dont(nagy, sor)
        self.assertEqual((st, j.ok), ("jelolt", "erosen_modosult"))

    def test_egyetlen_uj_keplet_hosszu_jegyzetben_is_elegendo(self):
        """A mondathalmaz-távolság egy új képletre kicsi: ezért van külön „új képlet” ok (a feldolgozott képletkulcsok az `adat`-ban)."""
        hosszu = FM + SZOVEG + "\n".join(f"Hosszú, tartalmas mondat a jegyzet többi részéről, sorszám {i}, amely változatlan." for i in range(30)) + "\n"
        sor = sor_(hosszu)
        uj = hosszu + "\n$$y = 3x - 1$$\n"
        v = OA.valtozas(frozenset(OA.mondatok(hosszu)), uj)
        self.assertLess(v.tavolsag, AU.Beallitas().kuszob)
        self.assertLess(v.uj_karakter, AU.Beallitas().uj_karakter)
        st, j = self.dont(uj, sor)
        self.assertEqual((st, j.ok), ("jelolt", "uj_keplet"))
        self.assertEqual(self.dont(hosszu + "\nUgyanaz a képlet marad.\n", sor)[0], "nem_eleg")

    def test_adat_nelkuli_atvett_sor_nem_ad_uj_keplet_okot(self):
        md = FM + SZOVEG
        sor = sor_(md)
        sor.pop("adat")
        self.assertIsNone(AU.uj_keplet(md + "\n$$y = 3x - 1$$\n", sor))
        self.assertEqual(AU.uj_keplet(md + "\n$$y = 3x - 1$$\n", sor_(md)), "uj_keplet")

    def test_mar_kesz(self):
        md = FM + SZOVEG
        self.assertEqual(self.dont(md, sor_(md))[0], "mar_kesz")

    def test_beallitas(self):
        self.assertEqual(AU.beallitas(self.cfg), AU.Beallitas())                      # az os.toml értékei az alapok
        self.assertFalse(AU.beallitas(self.cfg).modell_ag)                            # a modell-ág éles írása alapból kikapcsolt
        self.cfg.data["grafikon"]["automatika"]["nem_ismert"] = 1
        with self.assertRaises(ValueError):
            AU.beallitas(self.cfg)


class Futas(GepiAlap):
    def setUp(self):
        super().setUp()
        (self.v / "T01/Függvények.md").unlink()                                       # az ős-osztály jegyzete nem tárgya ennek a halmaznak
        self.ido = 1_000_000_000.0
        for rp, t in (("T01/A.md", FM + SZOVEG), ("T01/B.md", FM + "# B\n\nSima jegyzet képlet nélkül, elegendően hosszú szöveggel megtöltve.\n"),
                      ("ATTCHMNTS - x/C.md", FM + SZOVEG), (".obsidian/D.md", SZOVEG), ("T01/kep.png", "x")):
            ir(self.v, rp, t)
        self.repo.commit("jegyzetek", {"Mos-Forras": "kezi"})
        self.regi(self.ido - CSEND)
        self.tar = OA.Tar(self.cfg)

    def regi(self, mt):
        for p in self.v.rglob("*.md"):
            os.utime(p, (mt, mt))

    def futas(self, utak, beiro=None, **kw):
        return AU.futas(self.cfg, beiro or self.beiro, self.tar, utak, **kw)

    def jeloltek(self, **kw):
        return AU.jeloltek(self.cfg, self.tar, ido=lambda: self.ido, **kw)

    def test_kezi_mod_a_kozos_dontest_hivja_es_nem_ir(self):
        r = self.jeloltek()
        self.assertEqual([d["ut"] for d in r["dontesek"]], ["T01/A.md"])             # az ATTCHMNTS-, a rejtett és a nem .md kihagyva
        self.assertEqual(r["szamlalo"].get("nem_kell"), 1)                            # a képlet nélküli jegyzet
        self.assertEqual((self.tar.sorok("grafikon"), self.kliens.hivasok), ({}, []))
        self.assertEqual(self.jeloltek(kapcsolo_be=False)["szamlalo"], {"kapcsolo_ki": 1})
        self.assertEqual(AU.jeloltek(self.cfg, self.tar, ido=lambda: self.ido - CSEND + 60)["dontesek"], [])      # még szerkesztik

    def test_futas_ir_es_a_tarba_jegyez(self):
        r = self.futas(["T01/A.md"])
        self.assertEqual([(j["ut"], j["allapot"], j["beirt"]) for j in r["jegyzetek"]], [("T01/A.md", "kesz", 1)])
        self.assertEqual(len(F.blokkok((self.v / "T01/A.md").read_text(encoding="utf-8"))), 1)
        sor = self.tar.sor("grafikon", "T01/A.md")
        self.assertTrue(sor["alap"] and sor["ujjlenyomat"] and sor["feldolgozva"])
        self.assertEqual(json.loads(sor["adat"])["kepletek"], sorted(AU.kepletkulcsok(FM + SZOVEG)))
        self.assertEqual(sor["hash"], self.V.read("T01/A.md")["hash"])                # a saját írás nem számít új változásnak
        fej = self.repo.git("rev-parse", "HEAD").stdout
        self.assertEqual(self.futas(["T01/A.md"])["jegyzetek"][0]["allapot"], "nincs_teendo")
        self.assertEqual(self.repo.git("rev-parse", "HEAD").stdout, fej)

    def test_proba_es_szaraz_a_tarhoz_nem_nyul(self):
        self.futas(["T01/A.md"], szaraz=True)
        self.assertEqual((self.tar.sorok("grafikon"), self.kliens.hivasok), ({}, []))
        self.futas(["T01/A.md"], proba=True)
        self.assertEqual(self.tar.sorok("grafikon"), {})

    def test_limit_stop_es_elhalasztas(self):
        utak = []
        for i in range(4):
            utak.append(f"T01/N{i}.md")
            ir(self.v, utak[-1], FM + SZOVEG.replace("x^2 - 4", f"x^2 - {i + 5}"))
        self.repo.commit("több", {"Mos-Forras": "kezi"})
        self.assertEqual(len(self.futas(utak, max_jegyzet=2)["jegyzetek"]), 2)
        stop = os.path.join(self._t.name, "stop")
        open(stop, "w").close()
        r = self.futas(utak, stop_fajl=stop)
        self.assertEqual((r["jegyzetek"], r["megallt"]), ([], "stop"))
        os.unlink(stop)
        self.mentetlen = {"T01/N2.md", "T01/N3.md"}
        r = self.futas(utak[2:])
        self.assertEqual({j["allapot"] for j in r["jegyzetek"]}, {"elhalasztva"})
        self.assertEqual(self.tar.sorok("grafikon").keys() & {"T01/N2.md", "T01/N3.md"}, set())     # az elhalasztott nem számít feldolgozottnak

    def test_homokozo_hiba_megallitja_a_futast(self):
        b = B.Beiro(self.kliens, lambda sz: [{"allapot": "nem_ellenorizheto", "bizonyossag": "ismeretlen", "ok": "nincs sandbox"}],
                    self.tilt, self.napl)
        r = self.futas(["T01/A.md", "T01/B.md"], b)
        self.assertEqual((r["megallt"], [j["allapot"] for j in r["jegyzetek"]]), ("homokozo", ["nem_ellenorizheto"]))
        self.assertNotIn("T01/A.md", self.tar.sorok("grafikon"))

    def test_modellre_varo_kepletu_jegyzet_nem_kesz(self):
        """Nem elérhető modell (nincs kalibrált / a távol-keretre vár): a bizonytalan képlet nem dőlt el, a jegyzet később újra sorra kerül."""
        ir(self.v, "T01/P.md", FM + SZOVEG.replace("y = x^2 - 4", r"y = \frac{1}{x}"))
        self.repo.commit("pólus", {"Mos-Forras": "kezi"})

        def hivo(prompt, max_tokens):
            raise MA.ModellNemElerheto("a távol-keretre vár")
        b = B.Beiro(self.kliens, felismero, self.tilt, self.napl, varakozas_mp=0.1, modell=hivo, homokozo=HamisHomokozo())
        r = self.futas(["T01/P.md"], b)
        j = r["jegyzetek"][0]
        self.assertEqual((j["allapot"], j["fuggoben"]), ("nincs_teendo", 1))
        self.assertNotIn("T01/P.md", self.tar.sorok("grafikon"))                         # nem jegyezte feldolgozottnak
        b2 = B.Beiro(self.kliens, felismero, self.tilt, self.napl, varakozas_mp=0.1)       # modell nélkül (modell_ag = hamis): lezárul
        self.assertEqual(self.futas(["T01/P.md"], b2)["jegyzetek"][0]["fuggoben"], 0)
        self.assertIn("T01/P.md", self.tar.sorok("grafikon"))


class RegiAllapotAtvetele(unittest.TestCase):
    def test_plot_automatika_json_atvetele_a_kozos_tarba(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = alg_core(t.name)
        regi = plot_allapot.Automatika(cfg)
        md = FM + SZOVEG
        regi.ment("T01/A.md", 5.0, OA.mondatok(md), AU.kepletkulcsok(md), OA.forras_ujjlenyomat(md))
        regi.ment("T01/B.md", 6.0)                                                      # képlet nélküli: csak mtime, nem veszi át
        tar = OA.Tar(cfg)
        self.assertEqual(regi.atvesz(tar), 1)
        sor = tar.sor("grafikon", "T01/A.md")
        self.assertEqual((json.loads(sor["alap"]), sor["ujjlenyomat"]), (sorted(OA.mondatok(md)), OA.forras_ujjlenyomat(md)))
        self.assertEqual(json.loads(sor["adat"])["kepletek"], sorted(AU.kepletkulcsok(md)))
        self.assertIsNone(sor["hash"])
        self.assertFalse((cfg.path("state") / "plot-automatika.json").exists())
        self.assertTrue((cfg.path("state") / "plot-automatika.json.atvett").exists())    # nem törlődik
        self.assertEqual(regi.atvesz(tar), 0)                                            # egyszeri
        # az átvett sor a döntésben: az ujjlenyomat egyezik → mar_kesz, nem dolgoztatjuk fel újra
        self.assertEqual(OA.dont(AU.fogyaszto(cfg), "T01/A.md", "h", 0.0, 1e6, tar.sor("grafikon", "T01/A.md"), lambda u: md)[0], "mar_kesz")


class Feladat(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        from core import grafikon_feladat
        grafikon_feladat.regisztral()
        self.t = tasks.REGISTRY["grafikon_automatikus"]

    def test_tipus(self):
        self.assertTrue(self.t.automatikus)                                           # a kapu alatt indul (D8, aktív használat, memória)
        self.assertFalse(tasks.REGISTRY["grafikon_beiras"].automatikus)               # 80(a): a kézi parancs típusa nem automatikus
        self.assertEqual(self.t.resources, frozenset({"modell", "vault"}))          # a modell-ág a workert használja (a determinisztikus ág nem)

    def test_terv(self):
        lepesek, osszegzes, fig = self.t.plan(self.cfg, {}, "/tmp/stop")
        (l,) = lepesek
        self.assertTrue(l.argv[2].endswith("modulok/grafikon/__main__.py"))
        self.assertEqual(l.argv[3:], ["automatikus", "--eles", "--stop-fajl", "/tmp/stop"])
        self.assertEqual(fig, [])
        l, _, fig = self.t.plan(self.cfg, {"proba": True, "max": 3}, "/tmp/stop")
        self.assertEqual(l[0].argv[-3:], ["--proba", "--max", "3"])
        self.assertEqual(len(fig), 1)
        l, _, _ = self.t.plan(self.cfg, {"utak": ["T01/A.md", "T02/B.md"]}, "/tmp/stop")
        self.assertEqual(l[0].argv[3:], ["automatikus", "--eles", "--stop-fajl", "/tmp/stop", "--ut", "T01/A.md", "--ut", "T02/B.md"])
        l, _, _ = self.t.plan(self.cfg, {"proba": True, "modell_ag": True}, "/tmp/stop")
        self.assertEqual(l[0].argv[-2:], ["--proba", "--modell-ag"])
        for rossz in ({"max": 0}, {"max": 99}, {"max": True}, {"max": "3"}, {"proba": "igen"}, {"modell_ag": True}, {"modell_ag": 1, "proba": True},
                      {"utak": []}, {"utak": "T01/A.md"}, {"utak": ["/abs.md"]}, {"utak": ["../x.md"]}, {"utak": ["T01/a.txt"]},
                      {"utak": ["T01/ATTCHMNTS - cards/x.md"]}, {"utak": ["T01/A.md"] * 21}):
            with self.assertRaises(tasks.Invalid):
                self.t.plan(self.cfg, rossz, "/tmp/stop")

    def test_kapu_aktiv_hasznalatnal_es_indulaskor_visszatart(self):
        """A feladat a meglévő kapun át indul: D8 indulási szünet, aktív használat, kevés memória → nem; tétlenségben igen."""
        ora, allapot, mem = [0.0], ["tetlen"], [50]
        k = kapu.Kapu(SimpleNamespace(allapot=lambda: allapot[0]), 20, 300, mem=lambda: mem[0], ido=lambda: ora[0])
        self.assertFalse(k.admit(self.t))                                              # az app épp elindult (D8)
        ora[0] = 301
        self.assertTrue(k.admit(self.t))
        allapot[0] = "aktiv"
        self.assertFalse(k.admit(self.t))                                              # aktív használat alatt nem
        allapot[0], mem[0] = "tetlen", 5
        self.assertFalse(k.admit(self.t))                                              # kevés szabad memória

    def test_az_asszisztens_kapcsolo_nem_tiltja_a_feladatot(self):
        """80(a): a vezérlő kapcsolója az asszisztenst kapcsolja; a (kézi) grafikon-feladatot nem tiltja."""
        from core import vezerlo
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": False})
        k = SimpleNamespace(admit=lambda t: True, utolso_ok="")
        self.assertTrue(vezerlo.admit_lanc(self.cfg, k)(tasks.REGISTRY["grafikon_beiras"]))


class TiltolistaApi(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.app = SimpleNamespace(cfg=self.cfg)

    def test_lista_es_levetel(self):
        self.assertEqual(grafikon_api.tiltolista(self.app), {"ok": True, "tiltott": []})
        plot_allapot.Tiltolista(self.cfg).felvesz("0123456789abcdef", "A.md", "törölve")
        (t,) = grafikon_api.tiltolista(self.app)["tiltott"]
        self.assertEqual((t["kulcs"], t["ut"], t["ok"]), ("0123456789abcdef", "A.md", "törölve"))
        self.assertEqual(grafikon_api.tiltolista_levesz(self.app, {"kulcs": "0123456789abcdef"})["ok"], True)
        self.assertEqual(grafikon_api.tiltolista(self.app)["tiltott"], [])

    def test_hibak(self):
        for torzs, kod in (({}, 400), ({"kulcs": 5}, 400), ({"kulcs": "nem-hexa"}, 400), ({"kulcs": "0" * 16}, 404), ([], 400)):
            with self.assertRaises(HttpError) as cm:
                grafikon_api.tiltolista_levesz(self.app, torzs)
            self.assertEqual(cm.exception.code, kod, torzs)
        (self.cfg.path("state") / "plot-tiltolista.json").write_text("{", encoding="utf-8")
        with self.assertRaises(HttpError) as cm:
            grafikon_api.tiltolista(self.app)
        self.assertEqual(cm.exception.code, 500)

    def test_utvonalak_regisztralva(self):
        r = utvonalak.Regiszter()
        grafikon_api.utvonalak(r)
        self.assertIn(("GET", "/api/grafikon/tiltolista", False), r.vegpontok())
        self.assertIn(("POST", "/api/grafikon/tiltolista/levesz", False), r.vegpontok())


if __name__ == "__main__":
    unittest.main()
