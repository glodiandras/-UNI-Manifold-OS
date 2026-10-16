"""C22m: a `kviz` aranyhalmaz és pontozó (`modulok/eval/kviz/`) — modell nélkül, hamis modellkimenettel.

A kimenetek a `j01` jegyzet fagyasztott darabjának valódi mondataiból készülnek (a kérdések és a rossz válaszok kézzel írottak);
a valódi vaulthoz és `var/`-hoz egyik teszt sem nyúl."""
import json
import unittest

from tests.eval_segedek import EVAL, aranyt_igenyel, eval_cfg, feladat, rekord
from tests.helpers import tmpdir

# (kérdés, válaszok A–D, helyes betű, idézet): a j01 5 tényének 5 kérdése; a rossz válaszok a jegyzet szókincséből vagy a
# kérdésből valók (hihető tévedések), a helyes válasz az idézetből következik
JO = [
    ("Hol mért Caesar döntő vereséget Pompeiusra?",
     ["A görögországi Pharszalosznál", "A Rubiconnál", "Hispániában", "Rómában"], "A",
     "Caesar sorra legyőzte Pompeius légióit, majd a görögországi Pharszalosznál (Kr. e. 48) döntő vereséget mért vetélytársára."),
    ("Milyen címet adott a megrémült senatus Caesarnak?",
     ["Örökös diktátor", "Triumvir", "Konzul", "Hadvezér"], "A",
     "A megrémült senatus Caesart örökös diktátorrá választotta."),
    ("Hány főre emelte Caesar a senatus létszámát?",
     ["900 főre", "600 főre", "300 főre", "450 főre"], "A",
     "A senatus létszámának 900 főre emelése, provinciabeli előkelőkkel"),
    ("Mivel biztosította Caesar a naptárreform tartósságát?",
     ["A szökőévek bevezetésével", "Egyiptomi csillagászok bevonásával", "A hónapok átnevezésével", "A senatus határozatával"], "A",
     "A kiigazítás tartósságát a szökőévek bevezetésével biztosította."),
    ("Kik vezették a Caesar elleni összeesküvést?",
     ["Brutus és Cassius", "Crassus és Pompeius", "Cassius és Pompeius", "Brutus és Crassus"], "A",
     "egy köztársaságpárti összeesküvés során Brutus és Cassius vezetésével megölték Kr. e. 44-ben"),
]


def blokk(k, a, h, idezet, magyarazat="Az idézet szerint."):
    return (f"KÉRDÉS: {k}\nA) {a[0]}\nB) {a[1]}\nC) {a[2]}\nD) {a[3]}\nHELYES: {h}\nIDÉZET: {idezet}\n"
            f"MAGYARÁZAT: {magyarazat}\n")


def kimenet(kerdesek) -> str:
    return "\n".join(blokk(*k) for k in kerdesek)


class _Alap(unittest.TestCase):
    ADAT = True          # a teszt a szállított `kviz` aranyhalmazt igényli (hiányában `[indokolt]` kihagyás)

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.vault = eval_cfg(self._t.name)
        self.m = feladat(self.cfg, "kviz", adat=self.ADAT)
        if self.ADAT:
            list(self.m.tetelek(self.cfg))               # a profil és a [kviz] beállítás betöltése (mint az eval-keretben)

    def pont(self, kerdesek):
        return self.m.pontoz_jegyzet("j01", kimenet(kerdesek))

    def rossz_kodok(self, e):
        return [h["kapu"] for h in e["hibak"]]


class AranyTest(_Alap):
    def test_epseg_es_allapot(self):
        self.assertEqual(self.m.epseg(), [])
        self.assertTrue(self.m.VERZIO.startswith("kviz-v"))
        self.assertEqual(self.m.ROUTER_FELADAT, "kviz")
        self.assertEqual(len(self.m.ARANY["jegyzetek"]), 20)
        for j in self.m.ARANY["jegyzetek"]:
            self.assertGreaterEqual(len(j["tenyek"]), 3, j["id"])
            self.assertEqual(len(j["forras_sha256"]), 64)

    def test_jovahagyott_utotag_nelkul(self):
        # K134 (2026-10-07, a K27 koordinátori jóváhagyásával): a halmaz jóváhagyott, a verzió `-vazlat` utótag nélküli;
        # a generátor a jóváhagyást csak változatlan tartalom mellett tartja meg (lásd lent)
        self.assertEqual(self.m.ARANY["allapot"], "jovahagyott")
        self.assertEqual(self.m.VERZIO, "kviz-" + self.m.ARANY["verzio"])
        self.assertEqual(self.m.ARANY["jovahagyva"], "2026-10-07")

    def test_a_generator_determinisztikus_es_egyezik_a_fajllal(self):
        ki = self.m.keszit
        regi = json.loads((EVAL / "kviz" / "arany.json").read_text(encoding="utf-8"))
        self.assertEqual(ki.kiir(ki.epit(regi)), ki.kiir(ki.epit(regi)))
        self.assertEqual(ki.kiir(ki.epit(regi)), (EVAL / "kviz" / "arany.json").read_text(encoding="utf-8"))

    def test_a_generator_nem_hagy_jova_uj_tartalmat(self):
        ki = self.m.keszit
        regi = json.loads((EVAL / "kviz" / "arany.json").read_text(encoding="utf-8"))
        regi["allapot"], regi["jovahagyva"] = "jovahagyott", "2026-10-06"
        self.assertEqual(ki.epit(regi)["allapot"], "jovahagyott")            # változatlan tartalom: a jóváhagyás marad
        regi["jegyzetek"][0]["tenyek"].pop()
        self.assertEqual(ki.epit(regi)["allapot"], "vazlat")                 # megváltozott tartalom: újra jóváhagyandó

    def test_elcsuszott_darab_hibat_ad(self):
        self.m.jegyzet("j01")["darab"]["sha256"] = "0" * 64
        try:
            with self.assertRaises(ValueError):
                self.m.darab("j01")
            self.assertTrue(any("elcsúszott" in h for h in self.m.epseg()))
        finally:
            self.m.jegyzet("j01")["darab"]["sha256"] = self.m.keszit.A.szoveg_sha256(
                self.m.keszit.darab_szoveg(self.m.forras("j01")[0], self.m.jegyzet("j01")["ut"],
                                           self.m.jegyzet("j01")["darab"]["index"])["szoveg"])
        self.assertEqual(self.m.epseg(), [])

    def test_tetelek(self):
        t = list(self.m.tetelek(self.cfg))
        self.assertEqual([x["id"] for x in t], [f"kviz-j{n:02d}" for n in range(1, 21)])
        self.assertEqual(t[0]["keres"]["max_tokens"], 5 * 230 + 150)
        uzenet = t[0]["keres"]["messages"][0]["content"]
        self.assertIn("5 feleletválasztós kérdést", uzenet)
        self.assertIn("[A polgárháború és a hatalom]", uzenet)               # a j01 fagyasztott darabja
        self.assertEqual(t[0]["vart"], {"fajta": "kviz", "jegyzet": "j01", "prompt_verzio": self.m.PROMPT_VERZIO})


class PontozoTest(_Alap):
    def test_ures_futas_nulla(self):
        self.assertEqual(self.m.pontoz([])["pontszam"], 0.0)
        self.assertEqual(self.m.pontoz([{"id": "kviz-j01", "vart": {"jegyzet": "j01"}, "valasz": None}])["pontszam"], 0.0)

    def test_jo_kviz_teljes_pont(self):
        e = self.pont(JO)
        self.assertEqual(e["hibak"], [], e["hibak"])
        self.assertEqual((e["atment"], e["jeloltek"]), (5, 5))
        self.assertEqual(e["lefedettseg"], 1.0)
        self.assertAlmostEqual(e["pont"], 1.0)

    def test_kodkerites_szamozas_es_gondolkodas_nem_zavar(self):
        s = "<think>hmm</think>\n" + "\n".join(f"{i}. " + blokk(*k) for i, k in enumerate(JO, 1))
        self.assertEqual(self.m.pontoz_jegyzet("j01", s)["atment"], 5)
        self.assertTrue(self.m.formatum_ok(s, None))

    def test_tobb_helyes_valasz(self):
        k = list(JO)
        k[0] = (JO[0][0], ["A görögországi Pharszalosznál", "Görögországban, Pharszalosznál", "Hispániában", "Rómában"], "A", JO[0][3])
        e = self.pont(k)
        self.assertEqual(self.rossz_kodok(e), ["tobb_helyes"])
        self.assertEqual(e["atment"], 4)
        self.assertAlmostEqual(e["kerdesek"], 0.8)
        self.assertLess(e["lefedettseg"], 1.0)                               # a Pharszaloszi tény idézete kiesett

    def test_hihetetlen_rossz_opcio(self):
        k = list(JO)
        k[1] = (JO[1][0], ["Örökös diktátor", "Banán", "Űrhajó", "Zongora"], "A", JO[1][3])
        e = self.pont(k)
        self.assertEqual(self.rossz_kodok(e), ["hihetetlen"])
        self.assertIn("Banán", e["hibak"][0]["reszlet"])
        self.assertEqual(e["atment"], 4)

    def test_egyetlen_jegyzeten_kivuli_rossz_valasz_elmegy(self):
        k = list(JO)
        k[1] = (JO[1][0], ["Örökös diktátor", "Triumvir", "Konzul", "Hadvezér"], "A", JO[1][3])    # a Konzul nincs a jegyzetben
        self.assertEqual(self.pont(k)["hibak"], [])

    def test_duplikatum(self):
        k = list(JO) + [("Hol mért Caesar döntő vereséget Pompeiusra, melyik helyszínen?",
                         ["A görögországi Pharszalosznál", "A Rubiconnál", "Hispániában", "Itáliában"], "A", JO[0][3])]
        e = self.pont(k)
        self.assertEqual(self.rossz_kodok(e), ["duplikatum"])
        self.assertEqual((e["atment"], e["jeloltek"]), (5, 6))
        self.assertAlmostEqual(e["kerdesek"], 5 / 6)                         # nevező: az értékelt jelöltek száma

    def test_forras_nelkuli_kulcs(self):
        k = list(JO)
        k[2] = (JO[2][0], JO[2][1], "A", "Caesar a Rubicont átlépve egyetlen nap alatt elfoglalta az egész Itáliát és Rómát.")
        e = self.pont(k)
        self.assertEqual(self.rossz_kodok(e), ["idezet"])

    def test_a_helyes_valasz_nem_kovetkezik_az_idezetbol(self):
        k = list(JO)
        k[2] = (JO[2][0], ["300 főre", "900 főre", "600 főre", "450 főre"], "A", JO[2][3])       # a kulcs a hibás válasz
        e = self.pont(k)
        self.assertIn(self.rossz_kodok(e)[0], ("kenyes", "tamogatas"))

    def test_mechanikus_hiba(self):
        k = list(JO)
        k[3] = (JO[3][0], ["A szökőévek bevezetésével", "Mindegyik", "A hónapok átnevezésével", "A senatus határozatával"], "A", JO[3][3])
        self.assertEqual(self.rossz_kodok(self.pont(k)), ["tiltott_valasz"])

    def test_levagott_kimenet(self):
        s = kimenet(JO[:4]) + "\nKÉRDÉS: Kik vezették a Caesar elleni\nA) Brutus és Cassius\nB) Crassus"
        e = self.m.pontoz_jegyzet("j01", s)
        self.assertEqual(e["atment"], 4)
        self.assertEqual(self.rossz_kodok(e), ["szerkezet"])                 # az utolsó, félbemaradt jelölt
        self.assertTrue(self.m.formatum_ok(s, None))
        self.assertFalse(self.m.formatum_ok("KÉRDÉS: Kik vezették a\nA) Brutus", None))
        self.assertFalse(self.m.formatum_ok("", None))
        self.assertFalse(self.m.formatum_ok(None, None))

    def test_kevesebb_mint_ot_kerdes_rontja_a_pontot(self):
        e = self.pont(JO[:2])
        self.assertEqual(e["atment"], 2)
        self.assertAlmostEqual(e["kerdesek"], 2 / 5)                         # a nevező legalább a kért 5

    def test_a_felesleg_nem_szamit(self):
        extra = ("Mikor ölték meg Caesart?", ["Kr. e. 44-ben", "Kr. e. 48-ban", "Kr. e. 49-ben", "Kr. e. 60-ban"], "A", JO[4][3])
        e = self.pont(JO + [extra] * 4)
        self.assertEqual(e["jeloltek"], 7)                                   # k + 2

    def test_a_pontszam_a_ket_reszbol_all(self):
        r = rekord(next(self.m.tetelek(self.cfg)), kimenet(JO[:3]), self.m.VERZIO)
        o = self.m.pontoz([r])
        e = o["reszletek"][0]
        self.assertAlmostEqual(o["pontszam"], 0.6 * e["kerdesek"] + 0.4 * e["lefedettseg"], places=3)
        self.assertEqual(o["kviz"]["jeloltek"], 3)

    def test_ervenyesseg_levagott_tetelre(self):
        from core.modell import ervenyesseg
        t = next(self.m.tetelek(self.cfg))
        r = rekord(t, kimenet(JO[:4]))
        r["keres_beallitas"] = {"max_tokens": t["keres"]["max_tokens"]}
        r["usage"] = {"completion_tokens": t["keres"]["max_tokens"]}
        e = ervenyesseg.vizsgal([r], 0.1, self.m.formatum_ok)
        self.assertEqual(e["levagott"], 1)
        self.assertFalse(e["ervenyes"])
        r["usage"] = {"completion_tokens": 700}
        self.assertTrue(ervenyesseg.vizsgal([r], 0.1, self.m.formatum_ok)["ervenyes"])
        ures = rekord(t, "")
        self.assertEqual(ervenyesseg.vizsgal([ures], 0.1, self.m.formatum_ok)["ures"], 1)


class RegisztracioTest(_Alap):
    ADAT = False         # a regiszter-ellenőrzések adat nélkül is futnak; a tételt igénylők külön jelöltek

    def test_router_feladat_csak_konfiguracioban(self):
        self.assertIn("kviz", self.cfg.section("router")["feladatok"])
        meres = self.cfg.section("meres", "feladat", "kviz")
        self.assertEqual(dict(meres), {"gondolkodas": False})

    @aranyt_igenyel("kviz")
    def test_a_kerest_a_regiszter_egesziti_ki(self):
        from core.modell import beallitas as B
        from core.modell import eval as ev
        b = B.betolt(self.cfg)
        t = next(self.m.tetelek(self.cfg))
        k = ev.keres_beallitas(b, b.modellek["gemma4_12b"], "kviz", t["keres"])
        self.assertEqual(k["max_tokens"], 1300)                              # 5 × 230 + 150, szorzó és gondolkodási pótlék nélkül
        self.assertIs(k["gondolkodas"], False)
        q = ev.keres_beallitas(b, b.modellek["qwen35_9b"], "kviz", t["keres"])
        self.assertEqual(q["max_tokens"], 2080)                              # K135 (C19): a Qwen3.5 modell-szintű 1,6-os szorzója

    def test_a_szoveg_kepes_modellek_kvizt_is_kapnak(self):
        from core.modell import beallitas as B
        for nev, m in B.betolt(self.cfg).modellek.items():
            self.assertEqual("kviz" in m.feladat, "szoveg" in m.feladat, nev)

    def test_a_felado_nem_ker_core_valtoztatast(self):
        # a betöltő a mappából találja: nincs külön regisztrációs sor a `core/modell/`-ben
        from core.modell import eval as ev
        self.assertEqual(ev.feladat_modul(self.cfg, "kviz").ROUTER_FELADAT, "kviz")

    @aranyt_igenyel("kviz")
    def test_parancslista(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("parancslista", EVAL / "parancslista.py")
        p = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(p)
        from core.modell import beallitas as B
        mod = B.betolt(self.cfg).modellek
        self.assertEqual(p.tetelszamok(self.cfg)["kviz"], 20)
        self.assertIn("kviz", p.feladatai(mod["qwen35_9b"]))
        self.assertNotIn("kviz", p.feladatai(mod["bge_m3"]))
        self.assertLess(p.SORREND.index("szoveg"), p.SORREND.index("kviz"))
        fut, _ = p.sorok(self.cfg)
        kesz = (EVAL.parent.parent / "docs" / "MERES-PARANCSOK.md").read_text(encoding="utf-8")
        kviz_sorok = [s["parancs"] for s in fut if "kviz" in s["feladatok"]]
        self.assertGreaterEqual(len(kviz_sorok), 4)
        for s in kviz_sorok:
            self.assertIn(s, kesz)


if __name__ == "__main__":
    unittest.main()
