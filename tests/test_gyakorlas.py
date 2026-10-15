"""C22a: a forrásjegyzet „## Gyakorlás” beágyazó sora (`core/gyakorlas.py`; TERV 5.2) — formátum és az összeállító segéd,
a valódi `gepi_iras.szakasz_beszur`-ral. Az írás (gépi írás) a C22b és a C23b dolga."""
import unittest

from core import gepi_iras, gyakorlas
from core.vaultio import Invalid

JEGYZET = "---\nTags: Mathematics\n---\n# Mértani sorozat\n\nA sorozat tagjai.\n"
KARTYA = "Mértani sorozat — kártyák"
KVIZ = "Mértani sorozat — Kvíz 2026-10-04 2030"


def beszur(txt: str, nev: str) -> str:
    m = gyakorlas.beszuras_muvelet("Mértani sorozat.md", nev)
    return gepi_iras.szakasz_beszur(txt, m["szakasz"], m["szoveg"], m["hova"], m["letrehoz"])


class SorTest(unittest.TestCase):
    def test_beagyazo_sor(self):
        self.assertEqual(gyakorlas.beagyazo_sor(KVIZ), "![[Mértani sorozat — Kvíz 2026-10-04 2030]]")
        import unicodedata
        self.assertEqual(gyakorlas.beagyazo_sor(unicodedata.normalize("NFD", "Ábra")), "![[Ábra]]")        # NFC

    def test_tiltott_nev(self):
        for rossz in ("", "  ", "A|B", "A]B", "A[B", "A#B", "A^B", "A\nB", "mappa/Név", "Név.md"):
            with self.assertRaises(ValueError, msg=repr(rossz)):
                gyakorlas.beagyazo_sor(rossz)


class MuveletTest(unittest.TestCase):
    def test_a_muvelet_alakja(self):
        self.assertEqual(gyakorlas.beszuras_muvelet("T03/Mértani sorozat.md", KVIZ),
                         {"tipus": "beszuras", "ut": "T03/Mértani sorozat.md", "szakasz": "## Gyakorlás",
                          "szoveg": "![[Mértani sorozat — Kvíz 2026-10-04 2030]]", "hova": "vege", "letrehoz": True})
        self.assertEqual(gyakorlas.beszuras_muvelet("a.md", "N", alap="abc123")["alap"], "abc123")

    def test_a_gepi_iras_elfogadja_a_kerest(self):
        k = gepi_iras._keres({"kor": "KVIZ-20261004-203015", "tetel": "Mértani sorozat", "forras": "mos-kviz", "modell": None,
                              "muveletek": [gyakorlas.beszuras_muvelet("T03/Mértani sorozat.md", KVIZ)]})
        self.assertEqual(k.muveletek[0]["tipus"], "beszuras")

    def test_az_ut_szoveges_md_kell(self):
        with self.assertRaises(ValueError):
            gyakorlas.beszuras_muvelet("kep.png", KVIZ)
        with self.assertRaises(ValueError):
            gyakorlas.beszuras_muvelet("", KVIZ)


class BeszurasTest(unittest.TestCase):
    def test_hianyzo_szakasz_letrejon_a_vegen(self):
        self.assertEqual(beszur(JEGYZET, KVIZ), JEGYZET + f"\n## Gyakorlás\n![[{KVIZ}]]\n")

    def test_a_kvizsor_a_kartyabeagyazas_utan_kerul(self):
        elso = beszur(JEGYZET, KARTYA)
        masodik = beszur(elso, KVIZ)
        self.assertTrue(masodik.endswith(f"## Gyakorlás\n![[{KARTYA}]]\n![[{KVIZ}]]\n"), masodik)       # TERV 5.2 sorrend

    def test_ismetlesre_nincs_valtozas(self):
        egyszer = beszur(JEGYZET, KVIZ)
        self.assertEqual(beszur(egyszer, KVIZ), egyszer)

    def test_a_szakasz_utan_masik_fejezet_marad(self):
        szoveg = JEGYZET + f"\n## Gyakorlás\n![[{KARTYA}]]\n\n## Források\n\n- könyv\n"
        ki = beszur(szoveg, KVIZ)
        self.assertEqual(ki, JEGYZET + f"\n## Gyakorlás\n![[{KARTYA}]]\n![[{KVIZ}]]\n\n## Források\n\n- könyv\n")

    def test_crlf_marad(self):
        ki = beszur(JEGYZET.replace("\n", "\r\n"), KVIZ)
        self.assertNotIn("\r\r", ki)
        self.assertTrue(ki.endswith(f"## Gyakorlás\r\n![[{KVIZ}]]\r\n"))
        self.assertEqual(ki.count("\n"), ki.count("\r\n"))

    def test_vegyes_sorveg_hiba(self):
        with self.assertRaises(Invalid):
            beszur("a\r\nb\nc\n", KVIZ)


if __name__ == "__main__":
    unittest.main()
