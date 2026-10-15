"""C23a: a kártya-kísérőjegyzet formátuma (`modulok/kartya/formatum.py`; `docs/C23-TERV.md` 1. fejezet)."""
import unittest

from modulok.kartya import formatum as f


class IroEsElemzoTest(unittest.TestCase):
    def test_korut(self):
        kartyak = [f.Kartya("Mi a mértani sorozat hányadosa?", "Az egymást követő tagok hányadosa:\n\n$q = a_{n+1}/a_n$.",
                            "c-7f3a9e21", "Mértani sorozat#^m-3f2a"),
                   f.Kartya("Kérdés forrás nélkül?", "egy sor", "c-0000aaaa"),
                   f.Kartya("Válasz nélkül?", "", "c-0000bbbb", "X")]
        szoveg = f.ir(kartyak, ["Mértani sorozat"], "qwen3_8b", "2026-10-04")
        e = f.elemez(szoveg)
        self.assertEqual(e.hibak, [])
        self.assertEqual(e.source, ["Mértani sorozat"])
        self.assertEqual((e.modell, e.keszult), ("qwen3_8b", "2026-10-04"))
        self.assertEqual([(k.kerdes, k.valasz, k.azon, k.forras, k.nyitas) for k in e.kartyak],
                         [(k.kerdes, k.valasz, k.azon, k.forras, "-") for k in kartyak])
        self.assertEqual(f.ir(e.kartyak, e.source, e.modell, e.keszult), szoveg)       # az író kimenete fixpont

    def test_az_iro_alakja(self):
        szoveg = f.ir([f.Kartya("K?", "V", "c-12345678", "Jegyzet#^m-1a2b")], [], "", "")
        self.assertEqual(szoveg, "---\nSource: []\nModell:\nKeszult:\n---\n"
                                 "> [!card]- K?\n> V\n> — [[Jegyzet#^m-1a2b]]\n\n^c-12345678\n")

    def test_valtozatok(self):
        szoveg = ("Bevezető szöveg.\n\n"
                  "> [!CARD]+ Nagybetűs, nyitott\n> válasz ^c-aaaa1111\n\n"                      # sorvégi azonosító
                  "> [!card] Címsor azonosítóval ^c-bbbb2222\n\n"                               # törzs nélkül
                  "> [!card]- Alias a forrásban\n> v\n> — [[Cél#^m-1|szép név]]\n\n\n^c-cccc3333\n\n"   # több üres sor
                  "> [!note] Nem kártya\n> semmi\n\n"
                  "```\n> [!card]- Kódban\n> nem kártya\n\n^c-dddd4444\n```\n\n"
                  "> [!card]- Azonosító nélkül\n> v\n")
        e = f.elemez(szoveg)
        self.assertEqual([(k.kerdes, k.valasz, k.azon, k.forras, k.nyitas) for k in e.kartyak], [
            ("Nagybetűs, nyitott", "válasz", "c-aaaa1111", None, "+"),
            ("Címsor azonosítóval", "", "c-bbbb2222", None, ""),
            ("Alias a forrásban", "v", "c-cccc3333", "Cél#^m-1", "-"),
            ("Azonosító nélkül", "v", None, None, "-")])
        self.assertEqual([h["fajta"] for h in e.hibak], ["azonosito_nelkul"])
        self.assertEqual([k.azon for k in f.ervenyes(e)], ["c-aaaa1111", "c-bbbb2222", "c-cccc3333"])

    def test_nem_kartya_azonosito_a_szoveg_resze(self):
        e = f.elemez("> [!card]- Mennyi x ^2?\n> négy ^2\n\n^blokk1\n")
        self.assertEqual((e.kartyak[0].kerdes, e.kartyak[0].valasz, e.kartyak[0].azon), ("Mennyi x ^2?", "négy ^2", None))

    def test_duplikalt_es_kerdes_nelkuli(self):
        e = f.elemez("> [!card]- A\n> 1\n\n^c-aaaa0000\n\n> [!card]- B\n> 2\n\n^c-aaaa0000\n\n> [!card]-\n> 3\n\n^c-bbbb0000\n")
        self.assertEqual(sorted(h["fajta"] for h in e.hibak), ["duplikalt", "kerdes_nelkul"])
        self.assertEqual([k.kerdes for k in f.ervenyes(e)], ["A"])

    def test_crlf_es_frontmatter_lista(self):
        szoveg = '---\r\nSource:\r\n  - "[[A]]"\r\n  - "[[B|b]]"\r\n---\r\n> [!card]- K\r\n> V\r\n\r\n^c-abcd1234\r\n'
        e = f.elemez(szoveg)
        self.assertEqual(e.source, ["A", "B"])
        self.assertEqual((e.kartyak[0].kerdes, e.kartyak[0].valasz, e.kartyak[0].azon), ("K", "V", "c-abcd1234"))

    def test_tobbsoros_kerdes_tilos(self):
        with self.assertRaises(ValueError):
            f.ir_kartya(f.Kartya("egy\nketto", "v", "c-12345678"))

    def test_szoveg_hash_es_ujjlenyomat_normalizal(self):
        self.assertEqual(f.szoveg_hash("Mi  a\nq?", "v "), f.szoveg_hash("Mi a q?", "v"))
        self.assertNotEqual(f.szoveg_hash("Mi a q?", "v"), f.szoveg_hash("Mi a q?", "w"))
        self.assertEqual(f.ujjlenyomat("KÉRDÉS", "X"), f.ujjlenyomat("kérdés", "x"))

    def test_uj_azon_utkozesmentes(self):
        foglalt = {f"c-{i:08x}" for i in range(50)}
        a = f.uj_azon(foglalt)
        self.assertRegex(a, r"^c-[0-9a-f]{8}$")
        self.assertNotIn(a, foglalt)


class KiseronevTest(unittest.TestCase):
    def test_szabad_nev(self):
        self.assertEqual(f.kiseronev("M01 - Algebra/Mértani sorozat.md", ["M01 - Algebra/Mértani sorozat.md"]),
                         "Mértani sorozat — kártyák")

    def test_azonos_alapnev_szulomappaval(self):
        utak = ["X02/Studium Generale - 1.md", "X03/Studium Generale - 1.md"]
        self.assertEqual(f.kiseronev("X02/Studium Generale - 1.md", utak), "Studium Generale - 1 (X02) — kártyák")
        self.assertEqual(f.kiseronev("X03/Studium Generale - 1.md", utak), "Studium Generale - 1 (X03) — kártyák")

    def test_foglalt_nev_es_hex(self):
        utak = ["A/Téma.md", "ATTCHMNTS - cards/Téma — kártyák.md", "ATTCHMNTS - cards/téma (A) — KÁRTYÁK.md"]
        nev = f.kiseronev("A/Téma.md", utak)
        self.assertRegex(nev, r"^Téma \(A\) [0-9a-f]{4} — kártyák$")
        self.assertEqual(nev, f.kiseronev("A/Téma.md", utak))                                  # determinisztikus

    def test_sajat_kiseronev_nem_utkozik(self):
        utak = ["A/Téma.md", "ATTCHMNTS - cards/Téma — kártyák.md"]
        self.assertEqual(f.kiseronev("A/Téma.md", utak, sajat="ATTCHMNTS - cards/Téma — kártyák.md"), "Téma — kártyák")

    def test_nfc(self):
        nfd = "A/Mértani.md"
        self.assertEqual(f.kiseronev(nfd, [nfd]), "Mértani — kártyák")


if __name__ == "__main__":
    unittest.main()
