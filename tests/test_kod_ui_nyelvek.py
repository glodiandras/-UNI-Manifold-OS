"""F10 (UI): a felület nyelvtáblája (`app/src/lib/vault/kod-nyelvek.json`) a core nyelvprofiljainak (`core/kod_nyelvek.py`) tükre.

A kód-fül, a fájlfa, az ikonok és a beágyazás a felületen szinkron kell tudják, mely fájl forráskód (a `GET /api/kod/nyelvek` aszinkron,
a fa nem várhat rá). Ez a teszt őrzi, hogy a két lista ne csússzon szét: a profilok az egyetlen forrás, a JSON származtatott másolat,
és a szerkeszthető kiterjesztések pontosan a `vaultio.IRHATO` forrás-részei."""
import json
import unittest

from core import kod_nyelvek as KN, vaultio
from tests.helpers import REPO

JSON_UT = REPO / "app" / "src" / "lib" / "vault" / "kod-nyelvek.json"


def _elemzes(p: KN.Profil) -> bool:
    """Az „ellenőrzés” lépés csak szintaxis-vizsgálat (a profil segédszkriptje, nem fordító): Python, JavaScript, TypeScript."""
    return bool(p.fordit) and any("{segedek}" in a for a in p.fordit)


class UiNyelvtablaTest(unittest.TestCase):
    def setUp(self):
        self.adat = json.loads(JSON_UT.read_text(encoding="utf-8"))

    def test_a_json_a_profilok_tukre(self):
        vart = [{"azonosito": p.azonosito, "nev": p.nev, "kiterjesztesek": list(p.kiterjesztesek), "kerites": list(p.kerites),
                 "kalibracios_kulcs": p.kalibracios_kulcs, "motor": p.motor, "hibakereso": p.motor == "cpp", "elemzes": _elemzes(p)}
                for p in KN.PROFILOK]
        self.assertEqual(self.adat["nyelvek"], vart,
                         "az app/src/lib/vault/kod-nyelvek.json elavult: generáld újra a core/kod_nyelvek.py profiljaiból")

    def test_a_szerkesztheto_kiterjesztesek_a_core_engedelylistaja(self):
        nem = set(self.adat["nem_szerkesztheto"])
        self.assertEqual(nem, set(vaultio.NEM_SZERKESZTHETO_FORRAS))
        ui = {k for n in self.adat["nyelvek"] for k in n["kiterjesztesek"]} - nem
        self.assertEqual(ui, set(vaultio.FORRAS_KITERJESZTESEK))
        self.assertEqual(ui, set(vaultio.IRHATO) - {".md", ".base", ".canvas"})

    def test_a_hibakereso_mod_csak_c_es_cpp(self):
        self.assertEqual({n["azonosito"] for n in self.adat["nyelvek"] if n["hibakereso"]}, {"cpp", "c"})

    def test_az_ertelmezett_nyelvek_szintaxis_ellenorzest_kapnak(self):
        self.assertEqual({n["azonosito"] for n in self.adat["nyelvek"] if n["elemzes"]}, {"python", "javascript", "typescript"})


if __name__ == "__main__":
    unittest.main()
