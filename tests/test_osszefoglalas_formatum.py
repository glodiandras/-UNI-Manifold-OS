"""C26a: az összefoglaló kísérőjegyzet formátuma (`modulok/osszefoglalas/formatum.py`) — tiszta függvények."""
import unittest
from datetime import datetime

from modulok.osszefoglalas import formatum as FM

CEL = "T03 - Az ókori Róma/Elmélet/08 - A polgárháborúk kora és Caesar"


def minta() -> FM.Osszefoglalo:
    return FM.Osszefoglalo(
        "OSSZ-20261005-101530-3fa91c", "jegyzet", [CEL], "A polgárháborúk kora és Caesar", "qwen35_9b", "2026-10-05 1015",
        [FM.Allitas("Caesar szövetséget kötött a senatus ellen.", FM.Horgony(CEL, "^m-3f2a"), "Caesar szövetséget kötött velük a senatus ellen (Kr. e. 60)."),
         FM.Allitas("Átlépte a Rubicont.", FM.Horgony(CEL, "A Rubicon"), "katonáival átlépte az Itália határát jelentő Rubicont.")])


class IroElemzo(unittest.TestCase):
    def test_koruljaras(self):
        o = minta()
        e = FM.elemez(FM.ir(o))
        self.assertEqual(e.hibak, [])
        r = e.osszefoglalo
        self.assertEqual((r.azon, r.szint, r.forrasok, r.cim, r.modell, r.keszult),
                         (o.azon, "jegyzet", [CEL], o.cim, "qwen35_9b", "2026-10-05 1015"))
        self.assertEqual([(a.szoveg, a.horgony, a.idezet, a.id) for a in r.allitasok],
                         [(a.szoveg, a.horgony, a.idezet, f"a{i}") for i, a in enumerate(o.allitasok, 1)])

    def test_az_iras_alakja(self):
        sz = FM.ir(minta())
        self.assertTrue(sz.startswith('---\nSource:\n  - "[[' + CEL + ']]"\nOsszefoglalas: OSSZ-20261005-101530-3fa91c\nSzint: jegyzet\n'))
        self.assertIn(f"1. Caesar szövetséget kötött a senatus ellen. [[{CEL}#^m-3f2a|forrás]]\n   > „Caesar", sz)
        self.assertIn("# A polgárháborúk kora és Caesar — Összefoglaló\n", sz)
        self.assertNotIn("Status", sz)                                       # gép nem tölti (L33)
        self.assertEqual(FM.torzs(minta()).splitlines()[0], "## Állítások")

    def test_forras_nelkuli_allitas_nem_irhato(self):
        o = minta()
        o.allitasok[0].idezet = ""
        with self.assertRaises(ValueError):
            FM.ir(o)
        o = minta()
        o.allitasok[0].horgony = FM.Horgony("")
        with self.assertRaises(ValueError):
            FM.ir(o)

    def test_tiltott_jeloles_es_tobbsoros(self):
        for rossz in ("A [[Rubicon]] átlépése.", "A ==Rubicon== átlépése.", "Két\nsor."):
            o = minta()
            o.allitasok[0].szoveg = rossz
            with self.assertRaises(ValueError):
                FM.ir(o)
        o = minta()
        o.allitasok = []
        with self.assertRaises(ValueError):
            FM.ir(o)

    def test_ervenytelen_szint_es_azonosito(self):
        for mezo, ertek in (("szint", "ismeretlen"), ("azon", "KVIZ-20261005-101530-aa")):
            o = minta()
            setattr(o, mezo, ertek)
            with self.assertRaises(ValueError):
                FM.ir(o)

    def test_az_elemzo_a_hibas_allitast_kihagyja_es_jelenti(self):
        sz = FM.ir(minta()) + (
            "3. Link nélküli állítás.\n   > „idézet”\n"
            f"4. Idézet nélküli állítás. [[{CEL}|forrás]]\n"
            f"5. Üres idézet. [[{CEL}|forrás]]\n   > „”\n"
            f"6. Jó állítás. [[{CEL}#Fejezet|forrás]]\n   > „Jó idézet a jegyzetből.”\n")
        e = FM.elemez(sz)
        self.assertEqual(sorted(h["fajta"] for h in e.hibak), ["allitas_forras_nelkul", "idezet_hiany", "idezet_hiany"])
        self.assertEqual([a.id for a in e.osszefoglalo.allitasok], ["a1", "a2", "a6"])

    def test_kodkeritesben_allo_lista_nem_allitas(self):
        sz = FM.ir(minta()) + "\n```\n7. Kódban álló sor.\n```\n"
        e = FM.elemez(sz)
        self.assertEqual(e.hibak, [])
        self.assertEqual(len(e.osszefoglalo.allitasok), 2)

    def test_az_allitasok_szakaszon_kivuli_szamozott_lista_nem_hiba(self):
        sz = FM.ir(minta()) + "\n## Saját jegyzet\n\n1. Valami kézzel írt.\n"
        self.assertEqual(FM.elemez(sz).hibak, [])

    def test_frontmatter_hibak(self):
        e = FM.elemez("# Cím\n\n## Állítások\n\n1. x. [[A]]\n   > „y”\n")
        self.assertIn("frontmatter_hiba", [h["fajta"] for h in e.hibak])
        e = FM.elemez("---\nSource: []\nSzint: xx\n---\n\n# C\n")
        self.assertEqual(sorted(h["fajta"] for h in e.hibak), ["forras_hiany", "nincs_allitas", "szint_ervenytelen"])
        e = FM.elemez("---\n: : :\n  - [\n---\n")
        self.assertEqual(e.hibak[0]["fajta"], "frontmatter_hiba")

    def test_crlf_es_nfd(self):
        import unicodedata
        sz = unicodedata.normalize("NFD", FM.ir(minta())).replace("\n", "\r\n")
        e = FM.elemez(sz)
        self.assertEqual(e.hibak, [])
        self.assertEqual(e.osszefoglalo.allitasok[0].horgony.cel, CEL)        # NFC-re hozva

    def test_source_sztring_alak(self):
        e = FM.elemez('---\nSource: "[[Cél]]"\n---\n\n## Állítások\n\n1. Állítás szöveg. [[Cél#X|forrás]]\n   > „idézet szöveg”\n')
        self.assertEqual(e.osszefoglalo.forrasok, ["Cél"])


class HorgonyNev(unittest.TestCase):
    def test_ido_horgony(self):
        h = FM.ido_horgony("T/Média/Előadás.mp4", 125)
        self.assertEqual(h.link(), "[[T/Média/Előadás.mp4#t=125|2:05]]")
        self.assertEqual(FM.ido_felirat(3725), "1:02:05")
        self.assertEqual(FM.ido_felirat(-3), "0:00")

    def test_horgony_ertek(self):
        self.assertEqual(FM.horgony_ertek("A/B#^m-1|forrás"), FM.Horgony("A/B", "^m-1", "forrás"))
        self.assertEqual(FM.horgony_ertek("A/B"), FM.Horgony("A/B", None, "forrás"))

    def test_azonosito_es_cim(self):
        a = FM.uj_azon(datetime(2026, 10, 5, 10, 15, 30), "3fa91c")
        self.assertEqual(a, "OSSZ-20261005-101530-3fa91c")
        self.assertTrue(FM.AZON_RE.match(a))
        self.assertTrue(FM.AZON_RE.match(FM.uj_azon(datetime(2026, 10, 5, 10, 15, 30))))
        self.assertEqual(FM.cim_of("T03/08 - Caesar.md"), "Caesar")
        self.assertEqual(FM.keszult(datetime(2026, 10, 5, 10, 15)), "2026-10-05 1015")

    def test_kisero_nev_utkozes(self):
        utak = ["A/Mértani sorozat.md", "B/Más.md"]
        self.assertEqual(FM.kisero_nev("A/Mértani sorozat.md", utak), "Mértani sorozat — összefoglaló")
        self.assertEqual(FM.kisero_ut("A/Mértani sorozat.md", utak), "ATTCHMNTS - summaries/Mértani sorozat — összefoglaló.md")
        dupla = utak + ["C/Mértani sorozat.md"]
        self.assertEqual(FM.kisero_nev("A/Mértani sorozat.md", dupla), "Mértani sorozat (A) — összefoglaló")
        # a mappa-szint: a mappa útja `.md`-vel
        self.assertEqual(FM.kisero_nev("T03/Elmélet.md", utak), "Elmélet — összefoglaló")


if __name__ == "__main__":
    unittest.main()
