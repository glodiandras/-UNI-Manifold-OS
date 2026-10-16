"""F11: az md-link regex (`feloldas.MD_RE`) a cél zárójeleit CommonMark szerint kezeli: a `<…>` forma és a kiegyensúlyozott
zárójelek (`[x](a (b).md)`) egy célt adnak, nem érnek véget az első `)`-nél. Ugyanazt a halmazt látja a gráf (`jegyzet_celok`), az
elemző (`elemzo.elemez`), az átírás (`linkek.jegyzet_talalatok`: a cél-szakasz pontos helye), a kereső és az említés-maszk.
A célok szöveges felbontását (`md_reszek` ↔ a felület `markdownCel`) a közös `md-cel-vektorok.json` őrzi (`test_f11_linkek`)."""
import time
import unittest

from core.index import elemzo, feloldas, linkek
from core.index.feloldas import MD_RE


def celok(sz: str) -> list[str]:
    return [m.group(1) for m in MD_RE.finditer(sz)]


class RegexTest(unittest.TestCase):
    def test_zarojeles_cel_egy_egesz(self):
        self.assertEqual(celok("[x](a (b).md)"), ["a (b).md"])
        self.assertEqual(celok("[x](C (1) (2).md#h)"), ["C (1) (2).md#h"])
        self.assertEqual(celok("[x](Mappa (1)/Cél (2).md#Fej (3))"), ["Mappa (1)/Cél (2).md#Fej (3)"])
        self.assertEqual(celok("[x](b(c(d)).md)"), ["b(c(d)).md"])

    def test_burkolt_cel_zarojellel_es_szokozzel(self):
        self.assertEqual(celok("[x](<a (b).md>)"), ["<a (b).md>"])
        self.assertEqual(celok("[x](<a b.md#H (2)>)"), ["<a b.md#H (2)>"])
        self.assertEqual(celok("[x](<a ) b.md>)"), ["<a ) b.md>"])           # a burokban a záró zárójel is tartalom
        self.assertEqual(celok("[x](<a \\> b.md>)"), ["<a \\> b.md>"])        # `\>` escape

    def test_tobb_link_egy_sorban_nem_olvad_ossze(self):
        self.assertEqual(celok("[x](a (b).md) és [y](c.md) meg [z](<d (e).md>)"), ["a (b).md", "c.md", "<d (e).md>"])
        self.assertEqual(celok("(lásd [x](a.md)) és [y](b.md)"), ["a.md", "b.md"])       # a link utáni zárójel nem része

    def test_a_regi_alakok_valtozatlanok(self):
        self.assertEqual(celok("[x](y.md#z)"), ["y.md#z"])
        self.assertEqual(celok("[w](https://q.example/a_(b))"), ["https://q.example/a_(b)"])
        self.assertEqual(celok("![i](p.png)"), ["p.png"])
        self.assertEqual(celok("[x](A%20B.md)"), ["A%20B.md"])
        self.assertEqual(celok("[x](A B.md)"), ["A B.md"])                    # a szóközös, burok nélküli alak továbbra is cél
        self.assertEqual(celok("[x](a.md \"cím\")"), ["a.md \"cím\""])

    def test_escapelt_zarojel_a_celben(self):
        self.assertEqual(celok("[x](a\\).md)"), ["a\\).md"])
        self.assertEqual(celok("[x](a\\(b.md)"), ["a\\(b.md"])

    def test_nem_link(self):
        for sz in ("[x]()", "[x](a(b.md)", "[x](\n)", "[x](a\nb.md)", "[x] (a.md)", "[[x]](a.md" ):
            self.assertEqual(celok(sz), [], sz)

    def test_a_beagyazas_melysege_korlatos_de_hat_szint_megy(self):
        self.assertEqual(celok("[x](a" + "(b" * 6 + ")" * 6 + ".md)"), ["a" + "(b" * 6 + ")" * 6 + ".md"])
        self.assertEqual(celok("[x](a" + "(" * 30 + ")" * 30 + ".md)"), [])      # belátható mélységen túl nem link, és nem is fagy

    def test_nincs_katasztrofalis_visszalepes(self):
        for rossz in ("[x](" + "(a" * 4000, "[x](" + "a(" * 5000, "[x](<" + "a" * 20000, "[x](" + "\\" * 20000, "[x](" + "(" * 20000):
            t0 = time.perf_counter()
            celok(rossz * 3)
            self.assertLess(time.perf_counter() - t0, 3.0, rossz[:20])


class FogyasztokTest(unittest.TestCase):
    SZ = "Lásd [Cél](Mappa/Cél (2).md#Fej (1)) és [másik](<Másik (x).md>) meg [külső](https://example.com/a_(b)).\n"

    def test_a_graf_celjai(self):
        self.assertEqual(feloldas.jegyzet_celok(self.SZ), ["Mappa/Cél (2).md", "Másik (x).md"])

    def test_az_elemzo_linkjei_a_teljes_link_hosszaval(self):
        j = elemzo.elemez(self.SZ)
        md = [l for l in j.linkek if l.fajta == "md"]
        self.assertEqual([(l.cel, l.alcel, l.alias) for l in md], [("Mappa/Cél (2).md", "Fej (1)", "Cél"), ("Másik (x).md", None, "másik")])
        self.assertEqual([l.hossz for l in md], [len("[Cél](Mappa/Cél (2).md#Fej (1))"), len("[másik](<Másik (x).md>)")])

    def test_az_atiras_a_cel_szakasz_pontos_helyet_adja(self):
        t = linkek.jegyzet_talalatok(self.SZ)
        self.assertEqual([(x.cel, self.SZ[x.kezd:x.veg], x.burok) for x in t],
                         [("Mappa/Cél (2).md", "Mappa/Cél (2).md", False), ("Másik (x).md", "Másik (x).md", True)])
        self.assertEqual([x.cel for x in t], feloldas.jegyzet_celok(self.SZ))

    def test_a_kereso_es_az_emlites_maszk_a_teljes_linket_kitakarja(self):
        from core.asszisztens import emlites
        ki = emlites.kitakar("Cél (2) szó [Cél (2)](Cél (2).md) vége\n")
        self.assertEqual(ki.count("Cél"), 1)                 # csak a szövegbeli említés marad, a link egésze kitakarva
        self.assertEqual(len(ki), len("Cél (2) szó [Cél (2)](Cél (2).md) vége\n"))


if __name__ == "__main__":
    unittest.main()
