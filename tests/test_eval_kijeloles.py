"""J4: az asszisztens kijelölés-módjainak aranyhalmaza (`kifejtes`, `osszefoglal_kijeloles`) — a `mos eval` szerződése, a tétel
kérése az éles kérés, a pontozó a referencián és a kézzel elrontott válaszokon, a router a saját feladaton, a fagyasztó álvaulton.
A valódi vaulthoz és `var/`-hoz egyik teszt sem nyúl."""
import hashlib
import json
import unittest

from tests.eval_segedek import EVAL, eval_cfg, feladat, rekord
from tests.helpers import ir, tmpdir

FELADATOK = {"kifejtes": "kifejt", "osszefoglal_kijeloles": "osszefoglal"}


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.vault = eval_cfg(self._t.name)

    def f(self, nev):
        return feladat(self.cfg, nev)

    def tetel(self, nev, tid):
        return next(t for t in self.f(nev).tetelek(self.cfg) if t["id"] == tid)

    def pont(self, nev, tid, valasz):
        m = self.f(nev)
        t = self.tetel(nev, tid)
        return m.pontoz([rekord(t, valasz)])


class SzerzodesTest(_Alap):
    def test_betoltheto_jovahagyott_es_a_prompthoz_kotott_verzio(self):
        """K430 (Audit 4, 2026-10-14): a két halmaz jóváhagyott; a verzió a `-vazlat` nélküli, prompthoz kötött alak."""
        from core import kiegeszites_modell as KM
        from kozos import kijeloles as K
        for nev, mod in FELADATOK.items():
            m = self.f(nev)
            self.assertEqual(m.ROUTER_FELADAT, nev)
            self.assertEqual(KM.ROUTER_FELADAT[mod], nev)
            self.assertEqual(m.ARANY.get("allapot"), "jovahagyott")
            self.assertEqual(m.VERZIO, f"{nev}-v1.p{KM.prompt_lenyomat(mod)}")
            self.assertEqual(K.verzio(nev, {**m.ARANY, "allapot": "vazlat"}, KM.prompt_lenyomat(mod)),
                             f"{nev}-v1.p{KM.prompt_lenyomat(mod)}-vazlat")
            self.assertEqual(m.pontoz([])["pontszam"], 0.0)
        self.assertNotEqual(KM.prompt_lenyomat("kifejt"), KM.prompt_lenyomat("osszefoglal"))
        self.assertEqual(K.ELOTTE_MAX, KM.ELOTTE_MAX)

    def test_a_kiegeszites_halmaza_vazlat_es_a_kerelemhez_kotott(self):
        """K382: a `kiegeszites` verziója `-vazlat` (jóváhagyásig kalibrált jel nem adható), és a kérés minden eleméhez kötött
        (prompt, `keres()`, token-keret, hőmérséklet); a kérés determinisztikus (hőmérséklet 0)."""
        from unittest import mock

        from core import kiegeszites_modell as KM
        from core.modell import kalibracio
        m = self.f("kiegeszites")
        self.assertEqual(m.ARANY.get("allapot"), "vazlat")
        self.assertRegex(m.VERZIO, r"^kiegeszites-cx-1\.p[0-9a-f]{8}-vazlat$")
        self.assertTrue(kalibracio.vazlat(m.VERZIO))
        for mod in ("folytat", "kifejt", "osszefoglal"):
            self.assertEqual(KM.keres(mod, "a", "b", "c")["temperature"], 0.0, mod)
        # a hőmérséklet, a token-keret és a prompt változása új lenyomatot ad
        eredeti = KM.prompt_lenyomat("folytat")
        with mock.patch.object(KM, "TEMPERATURA", 0.3):
            self.assertNotEqual(KM.prompt_lenyomat("folytat"), eredeti)
        with mock.patch.dict(KM.MAX_TOKEN, {"folytat": 999}):
            self.assertNotEqual(KM.prompt_lenyomat("folytat"), eredeti)
        # vázlaton a rögzítés kalibrált jelet nem fogad el
        with self.assertRaisesRegex(ValueError, "vázlat"):
            kalibracio.Tabla(self.root / "r.sqlite").rogzit("kiegeszites", "qwen35_2b", 0.9, m.VERZIO, kalibralt=True)
        # jóváhagyáskor a verzió a `-vazlat` nélküli alak, és a tétel kérése az éles kérés
        from kozos import arany as A
        self.assertEqual(A.verzio({**m.ARANY, "allapot": "jovahagyott"}), "cx-1")
        t = next(iter(m.tetelek(self.cfg)))
        self.assertEqual(t["keres"], KM.keres("folytat", t["vart"]["elotte"], t["vart"]["utana"]))

    def test_a_tetelek_a_felhasznalo_jegyzeteibol_fagyasztva(self):
        for nev in FELADATOK:
            a = self.f(nev).ARANY
            self.assertEqual(len(a["tetel"]), 12)
            self.assertEqual(len({t["id"] for t in a["tetel"]}), 12)
            self.assertGreaterEqual(len({t["targy"] for t in a["tetel"]}), 6)
            for t in a["tetel"]:
                self.assertTrue(t["kijeloles"].startswith(t["kezd"]) and t["kijeloles"].endswith(t["veg"]), t["id"])
                self.assertLessEqual(len(t["elotte"]), 1500)
                self.assertRegex(t["jegyzet_sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(t["referencia"].strip())
                if nev == "kifejtes":
                    self.assertTrue(t["tema"] and all(t["tema"]))
                    self.assertIsInstance(t["tiltott"], list)
                else:
                    self.assertGreaterEqual(len(t["kulcs"]), 4)

    def test_a_tetel_kerese_az_eles_keres(self):
        from core.kiegeszites_modell import keres
        for nev, mod in FELADATOK.items():
            for t in self.f(nev).tetelek(self.cfg):
                v = t["vart"]
                self.assertEqual(t["keres"], keres(mod, v["elotte"], "", v["kijeloles"]))
                tartalom = t["keres"]["messages"][0]["content"]
                self.assertIn(json.dumps(v["kijeloles"], ensure_ascii=False), tartalom)
                self.assertIn(json.dumps(v["elotte"], ensure_ascii=False), tartalom)

    def test_router_es_regiszter(self):
        router = set(self.cfg.section("router")["feladatok"])
        self.assertTrue({"kiegeszites", "kifejtes", "osszefoglal_kijeloles"} <= router)
        from core.modell import beallitas as B
        b = B.betolt(self.cfg)
        for nev in ("qwen3_vl_4b", "qwen35_4b"):
            m = b.modell(nev)
            self.assertLessEqual(m.csucs_gb, b.keret_gb("munka"))          # a munkakeret jelöltjei
            self.assertTrue({"kifejtes", "osszefoglal_kijeloles"} <= set(m.feladat), nev)
            for f in FELADATOK:
                self.assertIs(m.meres_beallitas(f).get("gondolkodas", b.meres["feladat"][f]["gondolkodas"]), False)

    def test_a_halmaz_verzioja_a_routerben(self):
        """A worker routere csak az aktuális (prompthoz kötött) verzión kalibrált sort fogadja el."""
        from core.modell.halmaz import Verziok
        from core.modell.router import Router, RoutingHiba
        from core.modell import beallitas as B, kalibracio
        v = Verziok(self.cfg.path("modulok"))
        t = kalibracio.megnyit(self.cfg)
        self.addCleanup(t.close)
        b = B.betolt(self.cfg)
        for nev in FELADATOK:
            akt = v(nev)
            self.assertEqual(akt, self.f(nev).VERZIO)
            t.rogzit(nev, "qwen35_4b", 0.8, akt + ".regi", True, "teszt")
            with self.assertRaises(RoutingHiba):                          # régi prompt-lenyomat: nem routol
                Router(b, t, v).valaszt(nev, b.keret_gb("munka"))
            t.rogzit(nev, "qwen35_4b", 0.8, akt + "-vazlat", False, "teszt")   # vázlaton kalibrált jel nem is adható (T050)
            with self.assertRaises(RoutingHiba):                          # a jóváhagyás előtti vázlat-verzió sora nem routol
                Router(b, t, v).valaszt(nev, b.keret_gb("munka"))
            # a jóváhagyott (K430) aktuális verzión álló sor: a mód élesedik
            t.rogzit(nev, "qwen35_4b", 0.8, akt, True, "teszt")
            d = Router(b, t, v).valaszt(nev, b.keret_gb("munka"))
            self.assertEqual(d.modell.nev, "qwen35_4b")


class PontozoTest(_Alap):
    def test_a_referencia_teljes_pont(self):
        for nev in FELADATOK:
            m = self.f(nev)
            tt = list(m.tetelek(self.cfg))
            p = m.pontoz([rekord(t, t["vart"]["referencia"]) for t in tt])
            self.assertEqual(p["pontszam"], 1.0, [x for x in p["tetelek"] if x["pont"] < 1])
            self.assertTrue(all(m.formatum_ok(t["vart"]["referencia"], t["vart"]) for t in tt))

    def test_formai_hibak_nulla(self):
        for nev in FELADATOK:
            m = self.f(nev)
            for t in m.tetelek(self.cfg):
                v = t["vart"]
                for rossz in ("", None, "```\nkód\n```", v["kijeloles"],
                              "This is a summary of the selection in English, and it is about the topic."):
                    self.assertEqual(m.pontoz([rekord(t, rossz)])["pontszam"], 0.0, (nev, t["id"], rossz))

    def test_osszefoglalas_hamis_szam_es_idegen_nev(self):
        jo = self.tetel("osszefoglal_kijeloles", "s12")["vart"]["referencia"]
        p = self.pont("osszefoglal_kijeloles", "s12", jo.replace("10 000.", "100."))
        self.assertLess(p["pontszam"], 1.0)
        self.assertIn("kenyes", " ".join(p["tetelek"][0]["okok"]))
        p = self.pont("osszefoglal_kijeloles", "s01",
                      "Széchenyi gazdasági alapon érvel, ahogy Wesselényi is: a hitel hiánya miatt nincs fejlesztés. "
                      "A kiváltság szegénységben tartja a nemességet, ez a saját érdeke.")
        self.assertLess(p["tetelek"][0]["huseg"], 1.0)

    def test_osszefoglalas_bevezetett_tagadas_es_hianyos_lefedettseg(self):
        p = self.pont("osszefoglal_kijeloles", "s07", "A ferdén ráeső fénysugár nem törik meg a lemez felületén.")
        self.assertIn("tagadas", " ".join(p["tetelek"][0]["okok"]))
        self.assertEqual(p["pontszam"], 0.25)                             # 2/4 kulcs, a mondat a kapun bukik
        p = self.pont("osszefoglal_kijeloles", "s06", "A bimetall melegítéskor ívben elhajlik, ezért termosztátokban használják.")
        self.assertAlmostEqual(p["pontszam"], 0.5 * 1 / 5 + 0.5, places=4)

    def test_kifejtes_ellentmondas_nulla(self):
        # a jegyzetben nem álló szám
        self.assertEqual(self.pont("kifejtes", "e01", "Széchenyi felajánlása 75 000 forint volt, ebből jött létre "
                                                      "az Akadémia. A tudós társaság a magyar nyelvet ápolta.")["pontszam"], 0.0)
        # a jegyzetben álló, de a felajánláshoz rossz évszám (tiltott minta)
        p = self.pont("kifejtes", "e01", "Széchenyi 1830-ban tette a felajánlást az Akadémia javára. A tudós társaság a "
                                         "magyar nyelvet és tudományt ápolta.")
        self.assertEqual(p["pontszam"], 0.0)
        self.assertTrue(p["tetelek"][0]["okok"][0].startswith("tiltott"))
        # tagadás-csere egy kijelölt mondaton
        p = self.pont("kifejtes", "e07", "Optikailag sűrűbb közegben nem kisebb sebességgel terjed a fény. Ezért a "
                                         "törésmutató mindig kisebb egynél.")
        self.assertEqual(p["pontszam"], 0.0)
        self.assertIn("tagadas", p["tetelek"][0]["okok"][0])
        # tiltott állítás; tagadott mondatban nem számít
        self.assertEqual(self.pont("kifejtes", "e07", "A sűrűbb közegben a fény gyorsabban terjed, mint a ritkábban. "
                                                      "Ezért ott a törésmutató kisebb.")["pontszam"], 0.0)
        self.assertEqual(self.pont("kifejtes", "e07", "A sűrűbb közegben a fény nem gyorsabban terjed, hanem lassabban. "
                                                      "Ezért ott nagyobb a törésmutató, és a sugár a merőlegeshez törik.")
                         ["pontszam"], 1.0)

    def test_kifejtes_tema_es_uj_tartalom(self):
        self.assertEqual(self.pont("kifejtes", "e09", "A Duna Magyarország leghosszabb folyója, sok híd ível át rajta. "
                                                      "Budapest kettészeli.")["pontszam"], 0.0)
        p = self.pont("kifejtes", "e09", "A bejárós ciklus tehát egy lista értékein lépked végig, a ciklusváltozóba töltve.")
        self.assertEqual(p["pontszam"], 0.5)
        self.assertIn("nincs_uj_tartalom", p["tetelek"][0]["okok"])

    def test_magyar_proba(self):
        from kozos import kijeloles as K
        self.assertTrue(K.magyar("Pythonban ezt a for kulcsszóval írjuk, például for elem in lista formában."))
        self.assertFalse(K.magyar("The loop stops when the list is over and it is done."))
        self.assertFalse(K.magyar("A ciklus vege."))                      # ékezet nélkül nem dönthető el: nem magyar
        self.assertTrue(K.fedi("szegénység", "szegénységben tartja") and K.fedi("híd", "a hidaknál"))
        self.assertFalse(K.fedi("10 000", "minden 100. részecske"))


class FagyasztoTest(_Alap):
    def test_kivag_es_fagyaszt_alvaulton(self):
        import kijeloles_keszit as KK
        md = "---\nTags: x\n---\n# Cím\n\nElső bekezdés 1999-ből.\n\nA **kijelölt** rész eleje, és 42 a vége.\n\nUtána.\n"
        ir(self.vault, "T01 - Próba/a.md", md)
        t = {"id": "e99", "ut": "T01 - Próba/a.md", "kezd": "A **kijelölt**", "veg": "a vége."}
        k = KK.fagyaszt_tetel(self.vault, t, True)
        self.assertEqual(k["kijeloles"], "A **kijelölt** rész eleje, és 42 a vége.")
        self.assertTrue(md.startswith(k["elotte"]) and k["elotte"].endswith("1999-ből.\n\n"))
        self.assertEqual(k["jegyzet_sha256"], hashlib.sha256(md.encode()).hexdigest())
        self.assertEqual(k["szamok"], ["42", "1999"])
        self.assertNotIn("szamok", KK.fagyaszt_tetel(self.vault, t, False))
        hosszu = "x" * 3000 + "\n\nKEZD vége."
        ir(self.vault, "T01 - Próba/b.md", hosszu)
        k = KK.fagyaszt_tetel(self.vault, {"ut": "T01 - Próba/b.md", "kezd": "KEZD", "veg": "vége."}, False)
        self.assertEqual(len(k["elotte"]), 1500)
        with self.assertRaises(ValueError):
            KK.fagyaszt_tetel(self.vault, {"ut": "T01 - Próba/a.md", "kezd": "nincs ilyen", "veg": "."}, False)

    def test_a_fagyasztott_halmaz_onmagaval_egyezik(self):
        """A fagyasztó a meglévő mezőket megtartja: az arany.json a `json_ki` alakjában áll (újraírás nem változtat rajta)."""
        from kozos import kijeloles as K
        for nev in FELADATOK:
            p = EVAL / nev / "arany.json"
            self.assertEqual(p.read_text(encoding="utf-8"), K.json_ki(json.loads(p.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    unittest.main()
