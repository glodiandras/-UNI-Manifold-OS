"""C22a: a kvízjegyzet formátuma (`modulok/kviz/formatum.py`; `docs/C22-TERV.md` 2. fejezet) — elemző, író, a fájlnév, a
`## Kitöltések` szakasz. Tiszta függvények: fájlt nem olvasnak és nem írnak."""
import unittest
from datetime import timezone

from core import config
from core.tulajdonsagok import Tulajdonsagok
from modulok.kviz import formatum as f

FORRAS = "T03 - Az ókori Róma/Elmélet/08 - A polgárháborúk kora és Caesar"


def minta() -> f.Kviz:
    return f.Kviz(
        azon="KVIZ-20261004-203015-3fa91c", forras=FORRAS, cim="A polgárháborúk kora és Caesar", modell="qwen35_9b",
        keszult="2026-10-04 2030",
        kerdesek=[
            f.Kerdes("k1", "Kivel kötött szövetséget Caesar a senatus ellen?",
                     ["Crassusszal és Pompeiusszal", "Antoniusszal", "Brutusszal", "Sullával"], 0,
                     "A három hadvezér szövetsége az első triumvirátus.",
                     "Caesar kibékítette Crassust és Pompeiust, majd szövetséget kötött velük a senatus ellen (Kr. e. 60).",
                     "Az első triumvirátus", "Az első triumvirátus"),
            f.Kerdes("k3", "Mi az $a^2 + b^2 = c^2$ összefüggés neve?",
                     ["Pitagorasz-tétel", "Thalész-tétel", "Koszinusztétel", "Magasságtétel"], 2, "",
                     "A derékszögű háromszög befogóinak négyzetösszege egyenlő az átfogó négyzetével.", None, None)])


class IroEsElemzoTest(unittest.TestCase):
    def test_korut(self):
        k = minta()
        szoveg = f.ir(k)
        e = f.elemez(szoveg)
        self.assertEqual(e.hibak, [])
        self.assertEqual(e.kviz, k)
        self.assertEqual(f.ir(e.kviz), szoveg)                                  # az író kimenete fixpont

    def test_az_iro_alakja(self):
        szoveg = f.ir(minta())
        self.assertTrue(szoveg.startswith(
            '---\nSource:\n  - "[[' + FORRAS + ']]"\nKviz: KVIZ-20261004-203015-3fa91c\nModell: "qwen35_9b"\n'
            "Keszult: 2026-10-04 2030\n---\n"))
        self.assertIn("\n# A polgárháborúk kora és Caesar — Kvíz 2026-10-04 2030\n", szoveg)
        self.assertIn("\n## Kérdések\n", szoveg)
        self.assertIn("> [!question] 1. kérdés — Az első triumvirátus\n> Kivel kötött szövetséget Caesar a senatus ellen?\n>\n"
                      "> - A) Crassusszal és Pompeiusszal\n> - B) Antoniusszal\n", szoveg)
        self.assertIn("> [!question] 3. kérdés\n", szoveg)                       # a szakasz nélküli kérdés címsora
        self.assertIn("> [!success]- Megoldás\n> A) Crassusszal és Pompeiusszal\n>\n> Magyarázat: A három hadvezér", szoveg)
        self.assertIn(f"> A jegyzetben ([[{FORRAS}#Az első triumvirátus|Az első triumvirátus]]): Caesar kibékítette", szoveg)
        self.assertIn(f"> A jegyzetben ([[{FORRAS}|A polgárháborúk kora és Caesar]]): A derékszögű", szoveg)
        self.assertTrue(szoveg.endswith("## Kitöltések\n\n" + f.KITOLTES_MEGJ + "\n\nMég nincs kitöltés.\n"))

    def test_az_azonosito_a_cimsorbol_jon(self):
        e = f.elemez(f.ir(minta()))
        self.assertEqual([q.id for q in e.kviz.kerdesek], ["k1", "k3"])         # a törölt k2 a többit nem mozdítja

    def test_toleranciak(self):
        szoveg = f.ir(minta()).replace("\n", "\r\n").replace("[!question]", "[!QUESTION]").replace("[!success]-", "[!SUCCESS]+")
        szoveg = szoveg.replace('Source:\r\n  - "[[' + FORRAS + ']]"', 'Source: "[[' + FORRAS + ']]"')
        e = f.elemez(szoveg)
        self.assertEqual(e.hibak, [])
        self.assertEqual(e.kviz.forras, FORRAS)
        self.assertEqual(len(e.kviz.kerdesek), 2)

    def test_hianyzo_azonosito_tartalekkal(self):
        szoveg = f.ir(minta()).replace("Kviz: KVIZ-20261004-203015-3fa91c\n", "")
        e = f.elemez(szoveg)
        self.assertIsNone(e.kviz)
        self.assertEqual([h["fajta"] for h in e.hibak], ["azonosito_nelkul"])
        e2 = f.elemez(szoveg, azon_tartalek="KVIZ-KEZI-ab12cd34")
        self.assertEqual(e2.kviz.azon, "KVIZ-KEZI-ab12cd34")
        self.assertEqual(e2.hibak, [])

    def test_nem_kviz_szoveg(self):
        e = f.elemez("# Csak egy jegyzet\n\nSzöveg.\n")
        self.assertIsNone(e.kviz)
        self.assertEqual([h["fajta"] for h in e.hibak], ["azonosito_nelkul"])
        e = f.elemez("# Csak egy jegyzet\n\nSzöveg.\n", azon_tartalek="KVIZ-00000000-000000-ab12cd34")
        self.assertEqual(e.kviz.kerdesek, [])
        self.assertEqual([h["fajta"] for h in e.hibak], ["nincs_kerdes"])


class HibakTest(unittest.TestCase):
    def szoveg(self):
        return f.ir(minta())

    def hibak(self, szoveg):
        return [(h["fajta"], h.get("kerdes")) for h in f.elemez(szoveg).hibak]

    def test_megoldas_nelkuli_kerdes_kimarad(self):
        s = self.szoveg()
        a = s.index("> [!success]- Megoldás")
        b = s.index("> [!question] 3. kérdés")
        e = f.elemez(s[:a] + s[b:])
        self.assertEqual(self.hibak(s[:a] + s[b:]), [("megoldas_nelkul", "k1")])
        self.assertEqual([q.id for q in e.kviz.kerdesek], ["k3"])

    def test_harom_valasz(self):
        s = self.szoveg().replace("> - D) Sullával\n", "")
        self.assertEqual(self.hibak(s), [("valasz_hiany", "k1")])

    def test_ismeretlen_helyes_betu_vagy_eltero_szoveg(self):
        s = self.szoveg().replace("> A) Crassusszal és Pompeiusszal\n>\n> Magyarázat", "> E) Crassusszal és Pompeiusszal\n>\n> Magyarázat")
        self.assertEqual(self.hibak(s), [("megoldas_ervenytelen", "k1")])
        t = self.szoveg().replace("> A) Crassusszal és Pompeiusszal\n>\n> Magyarázat", "> B) Crassusszal és Pompeiusszal\n>\n> Magyarázat")
        self.assertEqual(self.hibak(t), [("megoldas_eltero", "k1")])             # a betű és a szöveg nem egyezik: kérdés kimarad

    def test_duplikalt_es_szam_nelkuli_kerdes(self):
        s = self.szoveg().replace("3. kérdés", "1. kérdés")
        self.assertEqual(self.hibak(s), [("duplikalt", "k1")])
        t = self.szoveg().replace("> [!question] 3. kérdés", "> [!question] Kérdés")
        self.assertIn(("azonosito_nelkul", None), self.hibak(t))

    def test_kodblokkban_allo_callout_nem_kerdes(self):
        s = self.szoveg().replace("## Kitöltések", "```\n> [!question] 7. kérdés\n> Nem kérdés?\n```\n\n## Kitöltések")
        self.assertEqual(self.hibak(s), [])
        self.assertEqual(len(f.elemez(s).kviz.kerdesek), 2)


class FajlnevTest(unittest.TestCase):
    def test_fajlnev_es_h1(self):
        self.assertEqual(f.fajlnev(minta()), "A polgárháborúk kora és Caesar — Kvíz 2026-10-04 2030")

    def test_tiltott_jelek_a_cimben(self):
        k = minta()
        k.cim = 'A "$x$" szerepe: #1 [példa]/több'
        self.assertEqual(f.fajlnev(k), "A x szerepe 1 példa több — Kvíz 2026-10-04 2030")

    def test_utkozes_sorszama(self):
        self.assertEqual(f.fajlnev(minta(), 2), "A polgárháborúk kora és Caesar — Kvíz 2026-10-04 2030 (2)")

    def test_keszult_idobol(self):
        from datetime import datetime
        self.assertEqual(f.keszult(datetime(2026, 10, 4, 20, 30, 15)), "2026-10-04 2030")

    def test_azonosito_minta(self):
        for jo in ("KVIZ-20261004-203015", "KVIZ-20261004-203015-3fa91c", "KVIZ-20261004-203015-3fa91c-proba", "KVIZ-20260927-101010-2"):
            self.assertTrue(f.AZON_RE.match(jo), jo)
        for rossz in ("kviz-1", "KVIZ-2026-1", "KVIZ-20261004-203015/../x", ""):
            self.assertFalse(f.AZON_RE.match(rossz), rossz)

    def test_a_tartalom_hashe_a_kerdesekre_erzekeny(self):
        a, b = minta(), minta()
        self.assertEqual(f.tartalom_hash(a), f.tartalom_hash(b))
        b.kerdesek[0].valaszok[1] = "Másik"
        self.assertNotEqual(f.tartalom_hash(a), f.tartalom_hash(b))
        c = minta()
        c.kerdesek[0].magyarazat = "Más magyarázat"                              # a magyarázat nem tartalmi hash
        self.assertEqual(f.tartalom_hash(a), f.tartalom_hash(c))


OSSZEGZES = {"pont": 8, "osszes": 10, "szazalek": 80, "matrix": {"tudja": 6, "szerencses": 2, "tevkepzet": 1, "hiany": 1},
             "atnezni": [{"szakasz": "Az első triumvirátus", "horgony": "Az első triumvirátus", "kerdesek": [1, 4]},
                         {"szakasz": "Polgárháború", "horgony": None, "kerdesek": [7]}]}


class KitoltesSzakaszTest(unittest.TestCase):
    def test_kitoltes_nelkul(self):
        self.assertEqual(f.kitoltes_szakasz(minta(), []), f"## Kitöltések\n\n{f.KITOLTES_MEGJ}\n\nMég nincs kitöltés.\n")

    def test_kitoltesek_es_jelolesek(self):
        kit = [{"mikor": "2026-10-04T18:30:15Z", "mod": "teljes", "osszegzes": OSSZEGZES},
               {"mikor": "2026-10-05T07:01:00Z", "mod": "hibasak", "osszegzes": {**OSSZEGZES, "pont": 2, "osszes": 2, "szazalek": 100, "atnezni": []}}]
        sz = f.kitoltes_szakasz(minta(), kit, jelolesek={"k2", "k10"}, idozona=timezone.utc)
        self.assertIn("- 2026-10-04 18:30 — 8/10 (80 %) · tévképzet 1 · hiány 1 · szerencsés tipp 2\n", sz)
        self.assertIn(f"\t- Nézd át: [[{FORRAS}#Az első triumvirátus|Az első triumvirátus]] (1., 4. kérdés); "
                      f"[[{FORRAS}|Polgárháború]] (7. kérdés)\n", sz)
        self.assertIn("- 2026-10-05 07:01 — 2/2 (100 %) · csak az előzőleg hibás kérdések · tévképzet 1", sz)
        self.assertIn("Hibásnak jelölt kérdés: 2., 10. — a pontszámba nem számít.\n", sz)

    def test_csere_meglevo_szakaszra(self):
        k = minta()
        szoveg = f.ir(k)
        uj = f.kitoltes_szakasz(k, [{"mikor": "2026-10-04T18:30:15Z", "mod": "teljes", "osszegzes": OSSZEGZES}], idozona=timezone.utc)
        kesz = f.kitoltes_csere(szoveg, uj)
        self.assertIn("8/10 (80 %)", kesz)
        self.assertNotIn("Még nincs kitöltés", kesz)
        self.assertEqual(kesz.count("## Kitöltések"), 1)
        self.assertEqual(f.kitoltes_csere(kesz, uj), kesz)                       # idempotens
        self.assertTrue(kesz.startswith(szoveg[:szoveg.index("## Kitöltések")]))  # a kvízjegyzet többi része érintetlen

    def test_csere_a_kovetkezo_fejezetig_es_hianyzo_szakasznal_a_vegere(self):
        k = minta()
        uj = f.kitoltes_szakasz(k, [])
        elotte = "# C\n\n## Kitöltések\n\nrégi sor\n\n## Saját jegyzetem\n\nEz marad.\n"
        self.assertEqual(f.kitoltes_csere(elotte, uj), "# C\n\n" + uj.rstrip("\n") + "\n\n## Saját jegyzetem\n\nEz marad.\n")
        self.assertTrue(f.kitoltes_csere("# C\n\nSzöveg.\n", uj).endswith("\n\n" + uj))


class SemaKapuTest(unittest.TestCase):
    def test_az_iro_kimenete_atmegy_a_kviz_sema_osztalyon(self):
        """A C22b `uj` művelete `osztaly: "kviz"`-zal ír: az író frontmatterének hibátlannak kell lennie."""
        tul = Tulajdonsagok(config.load(), None)
        szoveg = f.ir(minta())
        fm = szoveg[:szoveg.index("---\n", 4) + 4]
        ut = "ATTCHMNTS - quizes/" + f.fajlnev(minta()) + ".md"
        r = tul.elemez(ut, fm)
        self.assertEqual(r["osztaly"], "kviz")
        self.assertEqual(r["problemak"], [], r["problemak"])


if __name__ == "__main__":
    unittest.main()
