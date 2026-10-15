"""A Bases paritás-próbája (C12 12. lépés, gépi rész): a `tests/kezi/bazis_proba.py` próbavaultja álvaulton, az indexen át
lekérdezve, összevetve a **dokumentációból kézzel levezetett** elvárt sorokkal (P1–P5).

Az elvárásokat NEM a kiértékelő kimenetéből másoltuk: az Obsidian Bases dokumentációjából (Bases syntax: szűrők,
`and`/`or`/`not`, dátum-aritmetika, `file.*` mezők, link-egyenlőség; Functions: `hasLink`, `inFolder`, `contains`,
`containsAny`, `split`, `replace`, `matches`, `isEmpty`, `slice`, `title`) és a próbavault ismert adataiból számoltuk
(a levezetés a `ELVART` megjegyzéseiben). Eltérés = a kiértékelő a dokumentációtól tér el: a tesztnek pirosnak kell
lennie, az elvárást ne a kimenethez igazítsd.

Az Obsidian-összevetés (CSV-export) kézi: `tests/kezi/bazis_paritas.py` (K11).

Futtatás: `bin/mos exec var/venv/bin/python -B -m unittest tests.test_bazis_paritas`
"""
import unittest

from core.bazis.api import Bazisok
from tests.helpers import alg_core, tmpdir
from tests.index_segedek import index_indit
from tests.kezi import bazis_proba

# (a .base útja, a nézet neve) → a sorok `file.path` szerint, a nézet sorrendjében.
#
# P1  `file.tags == ["Book"]`: pontosan egy [Book] címke. Konyvek-ből kiesik a Meditations és a Godel Escher Bach
#     (két címke) és az Ulysses ([Novel]); bejön a Jegyzetek/Olvasonaplo ([Book]); a mellékletek, `.base`, `.canvas`
#     fájloknak nincs címkéjük (`[]`).
# P2  or[ and[Konyvek, or[Rating>=4.5, and[Rating>=4, Pages<400]], not[Status=="Dropped"]],
#         and[Csatolmanyok, size>100, ext!="pdf"], not[ext=="md", Csatolmanyok] ]; a `not` = "egyik sem igaz".
#     Konyvek: Atomic 4.5 ✓, Deep Work 4/300 ✓, Meditations 5 ✓, Sapiens 5 ✓, Thinking Fast 4/499 ✗ (Pages), Godel 4.5
#     de Dropped ✗, Ulysses 4/730 ✗, Zero to One 3.5 ✗, Walden 2 ✗, Dune nincs Rating ✗.
#     Csatolmanyok: abra-b (150), abra-c (300) ✓; abra-a (90) ✗, a két PDF ✗.
#     3. ág: nem md és nem Csatolmanyok: az 5 .base és a Naplo/Plan.canvas.
# P3  Lejarat: Due-"1M" >= Start: Beta, Gamma, Epsilon, Zeta ✓ (Alpha 01-09<01-10, Delta, Eta, Theta ✗);
#     Start+"30d" < 2026-08-01: Beta (02-27), Gamma (03-17), Epsilon (05-20) ✓; Zeta 07-02+30d = 08-01, nem kisebb ✗.
#     Idopont: (Ido+"4h").day != Ido.day: Kedd 22:15 → 03-04 02:15 ✓, Szerda 23:45 → 03-05 03:45 ✓,
#     Hetfo 13:30 ✗, Csutortok 12:00 ✗; Ido.hour >= 9: Kedd 22, Szerda 23 ✓.
# P4  Kapcsolat: NN tartalmazza a Fizika-linket: Mechanika, Optika, Vektor; hasLink("Algebra") (a frontmatter-link is
#     link): Analizis (törzs), Halmaz, Matrix, Vektor (NN) → az unió. Formula-szuro: NN.length >= 2: Integral, Optika,
#     Vektor; fizikas: Mechanika, Optika, Vektor → az unió.
# P5  Szoveg: a kisbetűs név tartalmaz "ar"-t vagy "er"-t: James Clear (clEAR), Yuval Harari, Frank Herbert,
#     Peter Thiel (pETER); a második szó hossza != 5: Clear (5) ✗, Thiel (5) ✗ → Harari, Herbert.
#     Regex: van Email és /@example\.(com|org)$/: Cal (.org), Frank (.com), James (.com); Peter .net ✗; Yuval, Daniel
#     nincs Email.
#     Limit: !Bio.isEmpty() || Country.isEmpty(): James, Yuval, Frank, Daniel (Bio), Peter (nincs Country; Bio üres);
#     Cal ✗ (Bio "" és van Country). Born csökkenően: 1986, 1976, 1967, 1934, 1920 → limit 3: James, Yuval, Peter.
ELVART = {
    ("Bases/P1 Konyvek.base", "Konyvek"): [
        "Jegyzetek/Olvasonaplo.md", "Konyvek/Atomic Habits.md", "Konyvek/Deep Work.md", "Konyvek/Dune.md",
        "Konyvek/Sapiens.md", "Konyvek/Thinking Fast.md", "Konyvek/Walden.md", "Konyvek/Zero to One.md"],
    ("Bases/P2 Szuro.base", "Szuro"): [
        "Bases/P1 Konyvek.base", "Bases/P2 Szuro.base", "Bases/P3 Datum.base", "Bases/P4 Kapcsolat.base",
        "Bases/P5 Fuggveny.base", "Csatolmanyok/abra-b.png", "Csatolmanyok/abra-c.png",
        "Konyvek/Atomic Habits.md", "Konyvek/Deep Work.md", "Konyvek/Meditations.md", "Konyvek/Sapiens.md",
        "Naplo/Plan.canvas"],
    ("Bases/P3 Datum.base", "Lejarat"): ["Projektek/Beta.md", "Projektek/Epsilon.md", "Projektek/Gamma.md"],
    ("Bases/P3 Datum.base", "Idopont"): ["Naplo/Kedd.md", "Naplo/Szerda.md"],
    ("Bases/P4 Kapcsolat.base", "Kapcsolat"): [
        "Jegyzetek/Analizis.md", "Jegyzetek/Halmaz.md", "Jegyzetek/Matrix.md", "Jegyzetek/Mechanika.md",
        "Jegyzetek/Optika.md", "Jegyzetek/Vektor.md"],
    ("Bases/P4 Kapcsolat.base", "Formula-szuro"): [
        "Jegyzetek/Integral.md", "Jegyzetek/Mechanika.md", "Jegyzetek/Optika.md", "Jegyzetek/Vektor.md"],
    ("Bases/P5 Fuggveny.base", "Szoveg"): ["Szemelyek/Frank Herbert.md", "Szemelyek/Yuval Harari.md"],
    ("Bases/P5 Fuggveny.base", "Regex"): [
        "Szemelyek/Cal Newport.md", "Szemelyek/Frank Herbert.md", "Szemelyek/James Clear.md"],
    ("Bases/P5 Fuggveny.base", "Limit"): [
        "Szemelyek/James Clear.md", "Szemelyek/Yuval Harari.md", "Szemelyek/Peter Thiel.md"],
}

# (a .base útja, nézet, sor útja, oszlop-azonosító) → a cella kimeneti értéke. Dokumentált példákból:
#   `date("2024-12-01") + "1M" + "4h" + "3m"` = 2025-01-01 04:03:00 (Bases syntax);
#   `date + "30d"`, két dátum különbsége ezredmásodpercben (Bases syntax: Date arithmetic);
#   `"John Smith".replace(/(\w+) (\w+)/, "$2, $1")` = "Smith, John" (Functions: replace; a g jelző nélkül az első);
#   `"hello world".title()`, `"hello".slice(1, 4)`, a szöveges `replace` minden előfordulást cserél.
CELLAK = {
    ("Bases/P3 Datum.base", "Lejarat", "Projektek/Beta.md", "formula.hatarido"):
        {"t": "datum", "iso": "2026-02-27", "ido": False},                  # 2026-01-28 + 30 nap
    ("Bases/P3 Datum.base", "Lejarat", "Projektek/Beta.md", "formula.hossz_nap"): 31,    # (02-28 − 01-28) ms-ben / 86 400 000
    ("Bases/P3 Datum.base", "Lejarat", "Projektek/Beta.md", "formula.doksi"):
        {"t": "datum", "iso": "2025-01-01T04:03:00", "ido": True},
    ("Bases/P3 Datum.base", "Idopont", "Naplo/Kedd.md", "formula.zaras"):
        {"t": "datum", "iso": "2026-03-04T02:15:00", "ido": True},          # 03-03 22:15 + 4 óra
    ("Bases/P5 Fuggveny.base", "Szoveg", "Szemelyek/Frank Herbert.md", "formula.fordit"): "Herbert, Frank",
    ("Bases/P5 Fuggveny.base", "Szoveg", "Szemelyek/Frank Herbert.md", "formula.cim"): "Frank Herbert",
    ("Bases/P5 Fuggveny.base", "Szoveg", "Szemelyek/Frank Herbert.md", "formula.rovid"): "Fra",
    ("Bases/P5 Fuggveny.base", "Szoveg", "Szemelyek/Frank Herbert.md", "formula.betuk"): 12,     # "FrankHerbert"
    ("Bases/P5 Fuggveny.base", "Szoveg", "Szemelyek/Yuval Harari.md", "formula.fordit"): "Harari, Yuval",
    ("Bases/P5 Fuggveny.base", "Szoveg", "Szemelyek/Yuval Harari.md", "formula.cim"): "Yuval Harari",
    ("Bases/P5 Fuggveny.base", "Szoveg", "Szemelyek/Yuval Harari.md", "formula.rovid"): "Yuv",
    ("Bases/P5 Fuggveny.base", "Szoveg", "Szemelyek/Yuval Harari.md", "formula.betuk"): 11,      # "YuvalHarari"
}


class ParitasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cfg, _, cls.v = alg_core(cls._t.name)
        cls.proba = bazis_proba.general(cls.v)
        cls.ix, _ = index_indit(cfg)
        cls.b = Bazisok(cfg, cls.ix)

    @classmethod
    def tearDownClass(cls):
        cls.ix.leallit()
        cls._t.cleanup()

    def lekerdez(self, fajl: str, nezet: str) -> dict:
        szoveg = (self.v / fajl).read_text(encoding="utf-8")
        v = self.b.lekerdez({"szoveg": szoveg, "ez": fajl, "nezet": nezet})
        self.assertTrue(v["ok"], v["hibak"])
        self.assertEqual(v["nezet"]["nev"], nezet)
        self.assertEqual([h for h in v["hibak"] if "db" not in h], [], "betöltési hiba a próba-nézetben")
        return v

    def test_a_probavault_alakja(self):
        self.assertEqual(len(self.proba["jegyzetek"]), 40)
        self.assertEqual(len(self.proba["csatolmanyok"]), 5)
        self.assertEqual(len(self.proba["bazisok"]), 5)
        self.assertEqual(sorted(p.name for p in (self.v / "Csatolmanyok").iterdir() if p.suffix == ".pdf"),
                         ["doc-a.pdf", "doc-b.pdf"])
        self.assertEqual((self.v / "Csatolmanyok" / "abra-b.png").stat().st_size, 150)

    def test_minden_nezetnek_van_elvart_sorhalmaza(self):
        """A generátor nézetlistája, a `.base` fájlok tényleges nézetei és az elvárások ugyanazt a halmazt adják."""
        tenyleges = set()
        for fajl in bazis_proba.BAZISOK:
            v = self.b.lekerdez({"szoveg": (self.v / fajl).read_text(encoding="utf-8"), "ez": fajl})
            tenyleges |= {(fajl, n["nev"]) for n in v["nezetek"]}
        self.assertEqual(tenyleges, set(ELVART))
        self.assertEqual(set(bazis_proba.NEZETEK), set(ELVART))

    def _sorok_egyeznek(self, kulcs):
        fajl, nezet = kulcs
        v = self.lekerdez(fajl, nezet)
        kapott = [s["ut"] for s in v["sorok"]]
        vart = ELVART[kulcs]
        self.assertEqual(
            kapott, vart,
            f"{fajl} / {nezet}: hiányzik {[u for u in vart if u not in kapott]}, többlet "
            f"{[u for u in kapott if u not in vart]}, a halmaz azonos (csak a sorrend más): {sorted(kapott) == sorted(vart)}")
        self.assertEqual(v["osszes"], len(vart))
        self.assertFalse(v["levagva"])

    def test_p1_konyvek_kartyak_file_tags_egyenlo_book(self):
        self._sorok_egyeznek(("Bases/P1 Konyvek.base", "Konyvek"))
        v = self.lekerdez("Bases/P1 Konyvek.base", "Konyvek")
        self.assertEqual((v["nezet"]["tipus"], v["nezet"]["nev"]), ("cards", "Konyvek"))
        self.assertEqual((v["nezet"]["beallitas"]["imageFit"], v["nezet"]["beallitas"]["cardSize"]), ("contain", 420))
        self.assertEqual([o["id"] for o in v["oszlopok"]][0], "file.path")

    def test_p2_egymasba_agyazott_and_or_not_infolder_szamok_csatolmanyok(self):
        self._sorok_egyeznek(("Bases/P2 Szuro.base", "Szuro"))

    def test_p3_datum_aritmetika_lejarat(self):
        self._sorok_egyeznek(("Bases/P3 Datum.base", "Lejarat"))

    def test_p3_datum_aritmetika_idopont(self):
        self._sorok_egyeznek(("Bases/P3 Datum.base", "Idopont"))

    def test_p4_kapcsolat_nn_contains_link_es_hashlink(self):
        self._sorok_egyeznek(("Bases/P4 Kapcsolat.base", "Kapcsolat"))

    def test_p4_szuroben_hasznalt_keplet(self):
        self._sorok_egyeznek(("Bases/P4 Kapcsolat.base", "Formula-szuro"))

    def test_p5_szoveg_fuggvenyek(self):
        self._sorok_egyeznek(("Bases/P5 Fuggveny.base", "Szoveg"))

    def test_p5_regex(self):
        self._sorok_egyeznek(("Bases/P5 Fuggveny.base", "Regex"))

    def test_p5_isempty_rendezes_es_limit(self):
        self._sorok_egyeznek(("Bases/P5 Fuggveny.base", "Limit"))

    def test_dokumentalt_cellaertekek(self):
        gyujt = {}
        for (fajl, nezet, ut, oszlop), vart in CELLAK.items():
            if (fajl, nezet) not in gyujt:
                gyujt[(fajl, nezet)] = self.lekerdez(fajl, nezet)
            v = gyujt[(fajl, nezet)]
            idx = [o["id"] for o in v["oszlopok"]].index(oszlop)
            sor = next((s for s in v["sorok"] if s["ut"] == ut), None)
            self.assertIsNotNone(sor, f"{fajl} / {nezet}: nincs sor: {ut}")
            self.assertEqual(sor["cellak"][idx], vart, f"{fajl} / {nezet} / {ut} / {oszlop}")

    def test_az_elvart_sorok_nem_trivialisak(self):
        """Őrszem a próbavault ellen: minden nézet valódi szűrést végez (se üres, se a teljes halmaz)."""
        osszes = len(self.proba["jegyzetek"]) + len(self.proba["csatolmanyok"]) + len(self.proba["bazisok"]) + 1
        for kulcs, sorok in ELVART.items():
            self.assertTrue(0 < len(sorok) < osszes, kulcs)


if __name__ == "__main__":
    unittest.main()
