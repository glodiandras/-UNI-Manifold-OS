"""F11: a Health „Learn more” a beépített útmutató oldalát adja (`core/doku.szakasz`, `learn_valasz`, `GET /api/doku/learn`): minden
`LEARN_MORE` téma szakasza kinyerhető (a Health-ellenőrzésekre is), a szakasz határa a következő azonos/magasabb szintű fejléc,
a kódblokk fejlécnek tűnő sora nem vág, és ha a munkatér tartalmazza az útmutatót (demo), a jegyzet útja is megjön."""
import unittest
from urllib.parse import quote

from core import doku, egeszseg
from tests.helpers import ir
from tests.test_core_api import _Szerver


class SzakaszTest(unittest.TestCase):
    def test_minden_learn_more_tema_szakasza_kinyerheto_es_nem_ures(self):
        for tema, (azonosito, hely) in doku.LEARN_MORE.items():
            with self.subTest(tema=tema):
                fejlec, szoveg = doku.szakasz(azonosito, hely)
                self.assertEqual(doku.horgony(fejlec), hely)
                self.assertGreater(len(szoveg.split()), 5, "a szakasz nem lehet üres")
                self.assertNotIn("<!--", szoveg)

    def test_a_health_szakaszok_hatara_a_kovetkezo_azonos_szintu_fejlec(self):
        _, index = doku.szakasz("health", "search-index")
        self.assertIn("rebuilds it from your Markdown files", index)
        self.assertNotIn("Before each change Manifold stores a snapshot", index)      # a következő (## Snapshots) szakasz
        _, ellenorzesek = doku.szakasz("health", "what-the-checks-do")
        self.assertIn("**Healthy**", ellenorzesek)                                      # a táblázat a szakaszban van
        self.assertNotIn("## Search index", ellenorzesek)

    def test_a_szakasz_hatara_a_kodblokk_kamu_fejlecevel_nem_vagodik(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "HEALTH-AND-TROUBLESHOOTING.md").write_text(
                "# T\n\n## A\n\nelső\n\n```\n## nem fejléc\n```\n\n### Alszakasz\n\nbenne\n\n## B\n\nmásik\n", encoding="utf-8")
            with mock.patch.object(doku, "mappa", lambda: Path(t)):
                fejlec, szoveg = doku.szakasz("health", "a")
        self.assertEqual(fejlec, "A")
        self.assertIn("## nem fejléc", szoveg)
        self.assertIn("### Alszakasz", szoveg)
        self.assertIn("benne", szoveg)
        self.assertNotIn("másik", szoveg)

    def test_ismeretlen_horgony_vagy_oldal_keyerror(self):
        with self.assertRaises(KeyError):
            doku.szakasz("health", "nincs-ilyen")
        with self.assertRaises(KeyError):
            doku.szakasz("nincs-oldal", "x")

    def test_a_health_ellenorzesek_mind_kapnak_szakaszt(self):
        for kod, _ in egeszseg.ELLENORZESEK:
            if f"health.{kod}" not in doku.LEARN_MORE:          # a hiányzó téma hibáját a `test_felhasznaloi_doku` jelzi, itt a felület 404-es tartaléka él
                continue
            with self.subTest(ellenorzes=kod):
                v = doku.learn_valasz(f"health.{kod}")
                self.assertEqual((v["oldal"]["azonosito"], v["munkater_ut"]), ("health", None))
                self.assertTrue(v["szakasz"])


class VegpontTest(_Szerver):
    def elokeszit(self):
        ir(self.v, "Manifold Guide/Health and troubleshooting.md", "# Health and troubleshooting\n")

    def test_learn_valasz_a_szakasszal_es_a_munkater_masolatval(self):
        kod, d = self.k("GET", "/api/doku/learn?tema=health.index")
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["oldal"]["azonosito"], d["oldal"]["cim"], d["horgony"], d["fejlec"]),
                         ("health", "Health & troubleshooting", "search-index", "Search index"))
        self.assertIn("search index is a fast lookup", d["szakasz"])
        self.assertEqual(d["munkater_ut"], "Manifold Guide/Health and troubleshooting.md")        # a demo másolata megvan

    def test_masolat_nelkuli_munkateren_nincs_munkater_ut(self):
        (self.v / "Manifold Guide" / "Health and troubleshooting.md").unlink()
        kod, d = self.k("GET", "/api/doku/learn?tema=health.pillanatkep")
        self.assertEqual((kod, d["munkater_ut"]), (200, None))
        self.assertIn("snapshot", d["szakasz"])

    def test_hibas_kerdes(self):
        kod, d = self.k("GET", "/api/doku/learn")
        self.assertEqual((kod, d["kod"]), (400, "doku.hianyzik_tema"))
        kod, d = self.k("GET", "/api/doku/learn?tema=" + quote("../x"))
        self.assertEqual((kod, d["kod"]), (404, "doku.ismeretlen_tema"))
        kod, d = self.k("GET", "/api/doku/learn?tema=health.nincs")
        self.assertEqual(kod, 404)

    def test_csak_olvas_a_post_nem_fogadott_el(self):
        self.assertIn(self.k("POST", "/api/doku/learn", {})[0], (404, 405))
        self.assertTrue((self.v / "Manifold Guide" / "Health and troubleshooting.md").is_file())     # semmi nem íródott


if __name__ == "__main__":
    unittest.main()
