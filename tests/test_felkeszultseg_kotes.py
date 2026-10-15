"""Dolgozat ↔ felkészülési jegyzet kötése (C28a; L59, a legacy `szemelyes/dolgozat.py` `kotes`-ének portja):
biztos / valószínű / áthelyezve? az eseményhez, órarend szerint / nincs a jegyzethez. Tiszta függvények."""
import unicodedata
import unittest

from core import naptar
from core.felkeszultseg import kotes

MAPPA = "Dolgozatok"
T = naptar.targyak_cfg(None)


def esemeny(azon, nap, targyak=(), fajta="dolgozat", kategoria="hatarido", cim=""):
    return {"azon": azon, "nap": nap, "kezd": nap + "T10:00:00+02:00", "targyak": list(targyak), "fajta": fajta,
            "kategoria": kategoria, "cim": cim}


def jegyzetek(*utak):
    return kotes.jegyzetek(utak, MAPPA, T)


def ut(nap, nev, ho=None):
    return f"X01 - Napló & To-Do/{ho or nap[:7]}/Dolgozatok/{nap} - {nev}.md"


class JegyzetekTest(unittest.TestCase):
    def test_csak_a_dolgozatok_mappa_datumos_jegyzetei(self):
        j = jegyzetek(ut("2026-09-18", "Matematika"), "X01 - Napló & To-Do/2026-09/Napló/2026-09 - Dolgozat kiértékelő.md",
                      "X01 - Napló & To-Do/2026-09/Dolgozatok/Recording 1.m4a",
                      "X01 - Napló & To-Do/2026-09/Dolgozatok/jegyzet datum nelkul.md",
                      "X01 - Napló & To-Do/2026-09/Dolgozatok/2026-09-18 - Matematika.pdf")
        self.assertEqual([x.ut for x in j], [ut("2026-09-18", "Matematika")])
        self.assertEqual(j[0].nap, "2026-09-18")
        self.assertEqual(j[0].targyak, ("Matematika",))

    def test_a_mappa_neve_reszstring_egyezes_mint_a_legacyben(self):
        j = jegyzetek("X01/2026-09/2026-09 - Dolgozatok/2026-09-18 - Fizika.md")
        self.assertEqual(len(j), 1)

    def test_nfd_utvonal_nfc_lesz(self):
        nfd = unicodedata.normalize("NFD", ut("2026-09-14", "Német"))
        j = jegyzetek(nfd)
        self.assertEqual(j[0].ut, unicodedata.normalize("NFC", nfd))
        self.assertEqual(j[0].targyak, ("Német",))

    def test_rendezes_nap_majd_ut(self):
        j = jegyzetek(ut("2026-09-19", "Fizika"), ut("2026-09-18", "Matematika"), ut("2026-09-18", "Fizika"))
        self.assertEqual([x.ut for x in j], [ut("2026-09-18", "Fizika"), ut("2026-09-18", "Matematika"),
                                             ut("2026-09-19", "Fizika")])

    def test_ismeretlen_tantargy_tantargy_nelkuli_jegyzet(self):
        self.assertEqual(jegyzetek(ut("2026-09-18", "Valami ismeretlen"))[0].targyak, ())

    def test_matek_rovidites_matematika(self):
        self.assertEqual(jegyzetek(ut("2026-09-18", "Matek"))[0].targyak, ("Matematika",))


class EsemenyKotesTest(unittest.TestCase):
    def kot(self, jegy, esem):
        return kotes.kot(jegyzetek(*jegy), esem)

    def test_biztos_azonos_nap_es_tantargy(self):
        k = self.kot([ut("2026-09-18", "Matematika")], [esemeny("e1", "2026-09-18", ["Matematika"])])
        self.assertEqual(k.esemenyek["e1"].fok, "biztos")
        self.assertEqual(k.esemenyek["e1"].jegyzet, ut("2026-09-18", "Matematika"))
        self.assertEqual(k.jegyzetek[ut("2026-09-18", "Matematika")], "biztos")
        self.assertIn("Matematika", k.esemenyek["e1"].ok)

    def test_matek_cimu_esemeny_matematika_jegyzet(self):
        """A tantárgy-halmaz a kanonikus név: „Matek témazáró” (esemény) ↔ „Matematika” (jegyzet)."""
        e = esemeny("e1", "2026-09-18", naptar.targy("Matek témazáró", T))
        self.assertEqual(e["targyak"], ["Matematika"])
        self.assertEqual(self.kot([ut("2026-09-18", "Matematika")], [e]).esemenyek["e1"].fok, "biztos")

    def test_ket_jegyzet_ugyanazon_a_napon_mindegyik_a_sajat_esemenyehez(self):
        k = self.kot([ut("2026-09-18", "Matematika"), ut("2026-09-18", "Fizika")],
                     [esemeny("f", "2026-09-18", ["Fizika"]), esemeny("m", "2026-09-18", ["Matematika"])])
        self.assertEqual(k.esemenyek["m"].jegyzet, ut("2026-09-18", "Matematika"))
        self.assertEqual(k.esemenyek["f"].jegyzet, ut("2026-09-18", "Fizika"))

    def test_egy_esemeny_egy_jegyzet(self):
        k = self.kot([ut("2026-09-18", "Matematika"), ut("2026-09-18", "Matek")], [esemeny("m", "2026-09-18", ["Matematika"])])
        self.assertEqual(len(k.esemenyek), 1)
        self.assertEqual(sorted(k.jegyzetek.values()), ["biztos", "nincs"])

    def test_valoszinu_egyetlen_tantargy_nelkuli_dolgozat_aznap(self):
        k = self.kot([ut("2026-09-30", "Német")], [esemeny("t", "2026-09-30", [], cim="Témazáró")])
        self.assertEqual(k.esemenyek["t"].fok, "valoszinu")

    def test_nem_valoszinu_ha_ket_tantargy_nelkuli_esemeny_van(self):
        k = self.kot([ut("2026-09-30", "Német")],
                     [esemeny("a", "2026-09-30", []), esemeny("b", "2026-09-30", [], fajta="hatarido")])
        self.assertEqual(k.esemenyek, {})
        self.assertEqual(k.jegyzetek[ut("2026-09-30", "Német")], "nincs")

    def test_tantargyas_esemeny_masik_tantargyu_jegyzettel_nem_kotheto(self):
        k = self.kot([ut("2026-09-18", "Fizika")], [esemeny("m", "2026-09-18", ["Matematika"])])
        self.assertEqual(k.esemenyek, {})

    def test_athelyezve_azonos_tantargyu_dolgozat_nehany_napra(self):
        k = self.kot([ut("2026-09-18", "Matematika")], [esemeny("m", "2026-09-21", ["Matematika"])])
        e = k.esemenyek["m"]
        self.assertEqual((e.fok, e.jegyzet), ("athelyezve", ut("2026-09-18", "Matematika")))
        self.assertIn("3", e.ok)

    def test_athelyezve_csak_het_napon_belul_es_a_legkozelebbi(self):
        self.assertEqual(self.kot([ut("2026-09-18", "Matematika")], [esemeny("m", "2026-09-26", ["Matematika"])]).esemenyek, {})
        k = self.kot([ut("2026-09-18", "Matematika")],
                     [esemeny("tavoli", "2026-09-24", ["Matematika"]), esemeny("kozeli", "2026-09-20", ["Matematika"])])
        self.assertEqual(list(k.esemenyek), ["kozeli"])

    def test_biztos_kotes_elonyt_elvez_az_athelyezessel_szemben(self):
        k = self.kot([ut("2026-09-18", "Matematika")],
                     [esemeny("ma", "2026-09-18", ["Matematika"]), esemeny("kesobb", "2026-09-20", ["Matematika"])])
        self.assertEqual(list(k.esemenyek), ["ma"])

    def test_orarend_szerint_ha_nincs_dolgozat_de_van_ora(self):
        ora = esemeny("o", "2026-09-18", ["Matematika"], fajta=None, kategoria="orarend")
        k = self.kot([ut("2026-09-18", "Matematika")], [ora])
        self.assertEqual(k.esemenyek, {})
        self.assertEqual(k.jegyzetek[ut("2026-09-18", "Matematika")], "orarend")

    def test_nincs_kotes(self):
        k = self.kot([ut("2026-09-18", "Matematika")], [])
        self.assertEqual(k.esemenyek, {})
        self.assertEqual(k.jegyzetek[ut("2026-09-18", "Matematika")], "nincs")

    def test_hatarido_nem_biztos_kotes(self):
        """A határidő (nem dolgozat) a tantárgy-egyezésnél nem köt: a biztos kötéshez `fajta == dolgozat` kell."""
        k = self.kot([ut("2026-09-18", "Matematika")], [esemeny("h", "2026-09-18", ["Matematika"], fajta="hatarido")])
        self.assertEqual(k.esemenyek, {})

    def test_nap_a_kezdetbol_ha_nincs_nap_mezo(self):
        e = esemeny("m", "2026-09-18", ["Matematika"])
        del e["nap"]
        self.assertEqual(self.kot([ut("2026-09-18", "Matematika")], [e]).esemenyek["m"].fok, "biztos")


if __name__ == "__main__":
    unittest.main()
