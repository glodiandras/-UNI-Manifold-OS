"""`GET /api/higienia` (C30a): alak, `ut` szűrés, hibakódok — a core-ral együtt, álvaulton."""
import unittest
from unittest import mock

from tests.test_index_api import IndexApiAlap


class HigieniaApiTest(IndexApiAlap):
    def setUp(self):
        # A háttérszolgáltatás helyesen szünetel, ha a valódi felhasználó másik appban gépel.
        # Az API-próba tétlen tesztgépet modellez; az aktivitáskapu saját tesztekben él.
        tetlen = mock.patch('core.modell.aktivitas.Aktivitas.allapot', return_value='tetlen')
        tetlen.start()
        self.addCleanup(tetlen.stop)
        super().setUp()

    def test_teljes_riport(self):
        # A3-25: `ut` nélkül a háttérszolgáltatás gyorsítótára válaszol (először 409, amíg nincs kész riport).
        from tests.index_segedek import var_ra
        self.assertTrue(var_ra(lambda: self.get("/api/higienia")[0] == 200, 15, 0.1))
        s, r = self.get("/api/higienia")
        self.assertEqual(s, 200)
        self.assertTrue(r["kesz"])
        self.assertEqual(set(r), {"kesz", "jegyzetek", "tetelek", "osszesites", "jegyzetenkent"})
        # az ALAP álvaultban van törött link (Linkek.md → „nincs ilyen”) és hiányzó forráshorgony (doc.pdf#page=3 létezik)
        torott = [t for t in r["tetelek"] if t["fajta"] == "torott_link" and t["ut"] == "Linkek.md"]
        self.assertTrue(any("nincs ilyen" in t["uzenet"] for t in torott))
        self.assertEqual(r["osszesites"]["ossz"], len(r["tetelek"]))

    def test_ut_szures(self):
        s, r = self.get("/api/higienia", ut="Linkek.md")
        self.assertEqual(s, 200)
        self.assertEqual({t["ut"] for t in r["tetelek"]}, {"Linkek.md"})

    def test_ismeretlen_ut_404(self):
        self.assertEqual(self.get("/api/higienia", ut="nincs.md")[0], 404)

    def test_csak_get(self):
        self.assertEqual(self.k("POST", "/api/higienia", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
