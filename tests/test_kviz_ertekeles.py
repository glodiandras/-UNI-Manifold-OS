"""C22a: a kitöltés kiértékelése és az elemzés (`modulok/kviz/ertekeles.py`) — a legacy kvíz-tesztek portja.

Determinisztikus, modell nélkül (a felület „helyes” jelzése nem számít, a pontszámot a core számolja)."""
import unittest

from modulok.kviz import ertekeles as E
from modulok.kviz import formatum as FM


def kviz() -> FM.Kviz:
    def q(i, kerdes, valaszok, helyes, szakasz, idezet):
        return FM.Kerdes(f"k{i}", kerdes, valaszok, helyes, "mert", idezet, szakasz, szakasz)
    return FM.Kviz(
        azon="KVIZ-20261004-203015-3fa91c", forras="M03 - Algebra/Elmélet/04 - Nevezetes szorzatok", cim="Nevezetes szorzatok",
        modell="org/kis", keszult="2026-10-04 2030",
        kerdesek=[q(1, "Mi a $(a+b)^2$ kifejtése?", ["$a^2 + b^2$", "$a^2 + 2ab + b^2$", "$a^2 - 2ab + b^2$", "$2a + 2b$"], 1,
                    "Elméleti alapok", "Két tag összegének négyzete: $(a+b)^2 = a^2 + 2ab + b^2$."),
                  q(2, "Mi az $a^2 - b^2$ szorzattá alakított alakja?", ["$(a-b)^2$", "$(a+b)^2$", "$(a+b)(a-b)$", "$a(a-b)$"], 2,
                    "Szorzattá alakítás", "Az $a^2 - b^2$ kifejezés szorzattá alakítva $(a+b)(a-b)$."),
                  q(3, "Minek hívjuk az $a^2 - b^2$ alakú kifejezést?", ["két négyzet különbségének", "teljes négyzetnek", "két tag összegének",
                                                                   "harmadfokú tagnak"], 0, "Szorzattá alakítás", "ezt két négyzet különbségének hívjuk")])


def rossz(k: FM.Kviz, i: int, d: int = 1) -> int:
    return (k.kerdesek[i].helyes + d) % 4


class KulcsNelkulTest(unittest.TestCase):
    def test_kitoltesre_nincs_kulcs_idezet_magyarazat(self):
        d = E.kitoltesre(kviz(), {"k2"})
        self.assertEqual(set(d), {"azon", "cim", "forras", "modell", "keszult", "kerdesek"})
        self.assertEqual(set(d["kerdesek"][0]), {"id", "kerdes", "valaszok", "szakasz", "jelolt"})
        self.assertEqual([q["jelolt"] for q in d["kerdesek"]], [False, True, False])
        self.assertNotIn("helyes", str(d))
        self.assertNotIn("Két tag összegének", str(d))                    # az idézet a válasz után jön

    def test_megoldas(self):
        k = kviz()
        m = E.megoldas(k, "k2", 0)
        self.assertEqual((m["helyes"], m["helyes_index"], m["helyes_valasz"]), (False, 2, "$(a+b)(a-b)$"))
        self.assertEqual((m["szakasz"], m["horgony"], m["jegyzet"]), ("Szorzattá alakítás", "Szorzattá alakítás", k.forras))
        self.assertIn("kifejezés szorzattá alakítva", m["idezet"])
        self.assertTrue(E.megoldas(k, "k2", 2)["helyes"])
        self.assertFalse(E.megoldas(k, "k2", None)["helyes"])
        with self.assertRaises(E.Hiba):
            E.megoldas(k, "k9", 0)


class ErtekelesTest(unittest.TestCase):
    def valaszok(self, k):
        # k1 biztosan jó, k2 biztosan rossz (tévképzet), k3 tippelve jó
        return [{"kerdes": "k1", "valasz": k.kerdesek[0].helyes, "tipp": False},
                {"kerdes": "k2", "valasz": rossz(k, 1), "tipp": False},
                {"kerdes": "k3", "valasz": k.kerdesek[2].helyes, "tipp": True},
                {"kerdes": "k1", "valasz": 0, "tipp": False}, {"kerdes": "nincs", "valasz": 0}]       # ismétlés, idegen: kiesik

    def test_pontszam_matrix_javaslat(self):
        k = kviz()
        e = E.kitoltes_ertekel(k, self.valaszok(k))
        o = e["osszegzes"]
        self.assertEqual((o["pont"], o["osszes"], o["szazalek"]), (2, 3, 67))
        self.assertEqual(o["matrix"], {"tudja": 1, "szerencses": 1, "tevkepzet": 1, "hiany": 0})
        j = e["javaslatok"][0]
        self.assertEqual((j["szakasz"], j["prioritas"], j["kerdesek"]), ("Szorzattá alakítás", 1, [2, 3]))
        self.assertEqual(j["tevkepzetek"][0]["helyes"], "$(a+b)(a-b)$")
        self.assertEqual(j["tevkepzetek"][0]["hitted"], k.kerdesek[1].valaszok[rossz(k, 1)])
        self.assertIn("Szorzattá alakítás", e["fo_uzenet"])
        self.assertEqual(e["ujra"], ["k2", "k3"])
        self.assertEqual([x["kerdes"] for x in e["eredmenyek"]], ["k1", "k2", "k3"])
        self.assertEqual(e["onismeret"], {"biztos": 2, "biztos_helyes": 1, "tipp": 1, "tipp_helyes": 1})

    def test_teljes_halmaz_a_meg_nem_valaszolt_hiany(self):
        """A3-04: `teljes_halmaz` mellett a nevező az összes érvényes kérdés (a hiányzó „hiány”); `hibasak` módban nem."""
        k = kviz()
        egy = [{"kerdes": "k1", "valasz": k.kerdesek[0].helyes, "tipp": False}]
        e = E.kitoltes_ertekel(k, egy, teljes_halmaz=True)
        self.assertEqual((e["osszegzes"]["pont"], e["osszegzes"]["osszes"], e["osszegzes"]["szazalek"]), (1, 3, 33))
        self.assertEqual(e["osszegzes"]["matrix"]["hiany"], 2)
        self.assertEqual([x["kerdes"] for x in e["eredmenyek"]], ["k1", "k2", "k3"])
        self.assertEqual(E.kitoltes_ertekel(k, egy)["osszegzes"]["osszes"], 1)                 # alapból a megválaszoltak
        self.assertEqual(E.kitoltes_ertekel(k, egy, "hibasak", teljes_halmaz=True)["osszegzes"]["osszes"], 1)
        j = E.kitoltes_ertekel(k, egy, teljes_halmaz=True, jelolesek={"k3"})                   # a jelölt nem számít a nevezőbe
        self.assertEqual((j["osszegzes"]["pont"], j["osszegzes"]["osszes"]), (1, 2))

    def test_a_negy_kategoria(self):
        k = kviz()
        e = E.kitoltes_ertekel(k, [{"kerdes": "k1", "valasz": 1, "tipp": False}, {"kerdes": "k2", "valasz": 2, "tipp": True},
                                   {"kerdes": "k3", "valasz": 3, "tipp": True}])
        self.assertEqual([x["kategoria"] for x in e["eredmenyek"]], ["tudja", "szerencses", "hiany"])
        e = E.kitoltes_ertekel(k, [{"kerdes": "k1", "valasz": 0, "tipp": False}, {"kerdes": "k2", "valasz": None}])
        self.assertEqual([x["kategoria"] for x in e["eredmenyek"]], ["tevkepzet", "hiany"])       # „nem tudom” tipp és hiány

    def test_hibasnak_jelolt_kerdes_nem_szamit(self):
        k = kviz()
        e = E.kitoltes_ertekel(k, self.valaszok(k)[:3], jelolesek={"k3"})
        self.assertEqual((e["osszegzes"]["pont"], e["osszegzes"]["osszes"]), (1, 2))
        self.assertEqual(e["osszegzes"]["jelolt"], [3])
        self.assertTrue([x for x in e["eredmenyek"] if x["kerdes"] == "k3"][0]["jelolt"])

    def test_tartos_hiba_es_trend(self):
        k = kviz()
        elso = E.kitoltes_ertekel(k, self.valaszok(k))
        elozmeny = [{"mod": "teljes", "osszegzes": elso["osszegzes"], "eredmenyek": elso["eredmenyek"]}]
        masodik = E.kitoltes_ertekel(k, [{"kerdes": "k2", "valasz": rossz(k, 1, 2)}], "hibasak", elozmeny)
        self.assertTrue(masodik["eredmenyek"][0]["tartos"])                 # az előző kitöltésben is rossz volt
        self.assertIsNone(masodik["trend"]["elozo_szazalek"])               # más kérdéshalmaz: nincs százalék-összevetés
        harmadik = E.kitoltes_ertekel(k, self.valaszok(k), "teljes", elozmeny)
        self.assertEqual(harmadik["trend"]["elozo_szazalek"], 67)
        self.assertEqual(harmadik["trend"]["tartos"], 1)
        self.assertIn("Az előző teljes kitöltéshez képest +0 százalékpont", harmadik["fo_uzenet"])

    def test_a_tevkepzet_megelozi_a_tobb_hianyt(self):
        """Mérve a böngészős próbán (2026-09-27): egy tévképzet (súly 3) a két hiány (2+2) mögé került, miközben „először
        ezt” címkét kapott — a sorrend mindenhol ugyanaz: előbb a prioritás, azon belül a súly."""
        k = kviz()
        e = E.kitoltes_ertekel(k, [{"kerdes": "k1", "valasz": rossz(k, 0), "tipp": False},
                                   {"kerdes": "k2", "valasz": rossz(k, 1), "tipp": True}, {"kerdes": "k3", "valasz": None}])
        self.assertEqual([j["szakasz"] for j in e["javaslatok"]], ["Elméleti alapok", "Szorzattá alakítás"])
        self.assertEqual([j["cimke"] for j in e["javaslatok"]], ["először ezt", "átnézendő"])
        self.assertEqual(e["osszegzes"]["atnezni"][0]["szakasz"], "Elméleti alapok")
        self.assertIn("Elméleti alapok (tévképzet)", e["fo_uzenet"])

    def test_hibatlan_kitoltes(self):
        k = kviz()
        e = E.kitoltes_ertekel(k, [{"kerdes": f"k{i + 1}", "valasz": q.helyes, "tipp": False} for i, q in enumerate(k.kerdesek)])
        self.assertEqual(e["osszegzes"]["szazalek"], 100)
        self.assertEqual(e["javaslatok"], [])
        self.assertEqual(e["ujra"], [])
        self.assertIn("Hibátlan és magabiztos", e["fo_uzenet"])

    def test_ures_kitoltes_es_ervenytelen_index(self):
        k = kviz()
        self.assertEqual(E.kitoltes_ertekel(k, [])["fo_uzenet"], "Nincs értékelhető válasz.")
        e = E.kitoltes_ertekel(k, [{"kerdes": "k1", "valasz": 9, "tipp": False}])
        self.assertIsNone(e["eredmenyek"][0]["valasz"])                     # érvénytelen index: nem válaszolt
        self.assertEqual(e["eredmenyek"][0]["kategoria"], "hiany")

    def test_fedetlen_szakaszok(self):
        k = kviz()
        e = E.kitoltes_ertekel(k, self.valaszok(k), szakaszok_cimei=["Elméleti alapok", "Szorzattá alakítás", "Egy harmadik"])
        self.assertEqual(e["fedetlen_szakaszok"], ["Egy harmadik"])
        self.assertEqual(E.kitoltes_ertekel(k, self.valaszok(k))["fedetlen_szakaszok"], [])

    def test_kimenet_json_alakban_szerializalhato(self):
        import json
        json.dumps(E.kitoltes_ertekel(kviz(), self.valaszok(kviz())))

    def test_kitoltes_szakasz_az_ertekelesbol(self):
        """Az értékelés `osszegzes`-e közvetlenül a `## Kitöltések` szakasz bemenete."""
        from datetime import timezone
        k = kviz()
        e = E.kitoltes_ertekel(k, self.valaszok(k))
        sz = FM.kitoltes_szakasz(k, [{"mikor": "2026-10-04T18:30:15Z", "mod": "teljes", "osszegzes": e["osszegzes"]}], {"k3"},
                                 idozona=timezone.utc)
        self.assertIn("2/3 (67 %) · tévképzet 1 · hiány 0 · szerencsés tipp 1", sz)
        self.assertIn("|Szorzattá alakítás]] (2., 3. kérdés)", sz)


if __name__ == "__main__":
    unittest.main()
