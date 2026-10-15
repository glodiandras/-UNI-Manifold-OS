"""C35b-mag: a ```plot automatikus beírásának tiszta része (`modulok/grafikon/beiras.py`, `tiltolista.py`, `jegyzet.tarolo_veg_sor`):
hová kerül a blokk (a képlet tárolója UTÁN), mi marad ki, és mikor számít a blokk eltűnése törlésnek. Folyamaton belüli felismerő."""
import unittest

from tests.grafikon_segedek import FM, F, R, felismero

from grafikon import beiras as B  # noqa: E402
from grafikon import jegyzet as J  # noqa: E402
from grafikon import tiltolista as T  # noqa: E402


def terv(szoveg, tiltott=frozenset(), **kw):
    return B.terv(szoveg, felismero(szoveg), tiltott, **kw)


def okok(ki):
    return [k["ok"] for k in ki]


class Hely(unittest.TestCase):
    def test_tobbsoros_display_keplet_utan_nem_belul(self):
        """A `jeloltek` a képlet BELSEJÉT adja: a `$$…$$` záró jele után kell írni, különben a blokk a képletet törné szét."""
        sz = "# T\n\n$$\ny = x^2 + 1\n$$\n\nvége\n"
        besz, ki = terv(sz)
        self.assertEqual((len(besz), ki), (1, []))
        uj = B.beszur(sz, besz)
        self.assertEqual(uj, "# T\n\n$$\ny = x^2 + 1\n$$\n\n" + besz[0].blokk + "\nvége\n")
        self.assertLess(uj.index("$$\ny"), uj.index("```plot"))
        self.assertEqual(uj.count("$$"), 2)

    def test_math_kerites_a_zaro_kerites_utan(self):
        sz = "# T\n\n```math\ny = 2x + 1\n```\n\nvége\n"
        besz, ki = terv(sz)
        self.assertEqual((len(besz), besz[0].veg_sor, ki), (1, 5, []))
        uj = B.beszur(sz, besz)
        self.assertTrue(uj.startswith("# T\n\n```math\ny = 2x + 1\n```\n\n```plot\n"))
        self.assertEqual(F.blokkok(uj)[0].abra, F.elemez(besz[0].torzs))

    def test_sorkozi_keplet_ures_sorral_elvalasztva(self):
        sz = "# T\n\nA parabola: $y = x^2$ a példa.\nKövetkező sor.\n"
        besz, _ = terv(sz)
        self.assertEqual(B.beszur(sz, besz), "# T\n\nA parabola: $y = x^2$ a példa.\n\n" + besz[0].blokk + "\nKövetkező sor.\n")

    def test_fajl_vegi_keplet_sorveg_nelkul(self):
        sz = "# T\n\n$$y = x^2$$"
        besz, _ = terv(sz)
        uj = B.beszur(sz, besz)
        self.assertEqual(uj, "# T\n\n$$y = x^2$$\n\n" + besz[0].blokk)
        self.assertTrue(uj.endswith("```\n"))

    def test_crlf_hu(self):
        sz = "# T\r\n\r\n$$y = x^2$$\r\n\r\nvége\r\n"
        besz, _ = terv(sz)
        uj = B.beszur(sz, besz)
        self.assertNotRegex(uj.replace("\r\n", ""), r"[\r\n]")           # nincs magányos \n vagy \r
        self.assertIn("```plot\r\n", uj)

    def test_tobb_keplet_alulrol_felfele_nem_csuszik(self):
        sz = "# T\n\n$$y = x^2$$\n\nközben\n\n$$y = 3x - 1$$\n\nvége\n"
        besz, ki = terv(sz)
        self.assertEqual((len(besz), ki), (2, []))
        uj = B.beszur(sz, besz)
        self.assertEqual(len(F.blokkok(uj)), 2)
        self.assertEqual([b.abra.elemek[0].kifejezes for b in F.blokkok(uj)], ["x^2", "3x - 1"])
        self.assertLess(uj.index("```plot"), uj.index("közben"))

    def test_idempotens_masodik_futas_nem_ir(self):
        sz = FM + "# T\n\n$$y = x^2$$\n\n$$\ny = 3x - 1\n$$\n\n```math\ny = 2x\n```\n"
        besz, ki = terv(sz)
        self.assertEqual(len(besz), 3, ki)
        uj = B.beszur(sz, besz)
        besz2, ki2 = terv(uj)
        self.assertEqual(besz2, [])
        self.assertEqual(okok(ki2), ["van_blokk"] * 3)


class Kihagyas(unittest.TestCase):
    def test_nem_beszurhato_sorok(self):
        for sor in ("> $y = x^2$", "| $y = x^2$ | b |", "- $y = x^2$", "1. $y = x^2$", "    $y = x^2$"):
            besz, ki = terv(f"# T\n\n{sor}\n")
            self.assertEqual((besz, okok(ki)), ([], ["nem_beszurhato_sor"]), sor)

    def test_kod_es_frontmatter_nem(self):
        besz, ki = terv("# T\n\n```python\nx = $y = x^2$\n```\n")
        self.assertEqual(besz, [])
        self.assertEqual(B.kodos_sorok("---\na: 1\n---\n# T\n```py\nx\n```\n```math\ny\n```\n"), {1, 2, 3, 5, 6, 7})

    def test_meglevo_blokk_nem_duplazodik(self):
        sz = "# T\n\n$$y = x^2$$\n\n```plot\ny = x^2\n```\n"
        besz, ki = terv(sz)
        self.assertEqual((besz, okok(ki)), ([], ["van_blokk"]))

    def test_tiltolista(self):
        sz = "# T\n\n$$y = x^2$$\n"
        (j,) = felismero(sz)
        besz, ki = terv(sz, tiltott={j["kulcs"]})
        self.assertEqual((besz, okok(ki)), ([], ["tiltolista"]))

    def test_bizonytalan_es_ismetlodo_es_korlat(self):
        besz, ki = terv("# T\n\n$$y = a x + b$$\n")
        self.assertEqual((besz, okok(ki)), ([], ["nem_biztos"]))
        besz, ki = terv("# T\n\n$$y = x^2$$\n\n$$y = x^2$$\n")
        self.assertEqual((len(besz), okok(ki)), (1, ["ismetlodo"]))
        sz = "# T\n\n" + "".join(f"$$y = x + {i}$$\n\n" for i in range(5))
        besz, ki = terv(sz, max_db=3)
        self.assertEqual((len(besz), okok(ki)), (3, ["tul_sok"] * 2))

    def test_hamis_javaslat_nem_iras(self):
        sz = "# T\n\n$$y = x^2$$\n"
        (j,) = felismero(sz)
        for hiba, ok in (({"blokk": "```plot\ny = x^2\nfoo bar\n```\n"}, "rossz_blokk"),
                         ({"blokk": "```plot\ny = x^3\n```\n"}, "rossz_blokk"),         # nem a felismerő ábrája
                         ({"blokk": "```plot\n# csak megjegyzés\n```\n"}, "rossz_blokk"),
                         ({"blokk": "```plot\ny   =   x^2\n```\n"}, "rossz_blokk"),           # nem kanonikus
                         ({"kulcs": "0123456789abcdef"}, "kulcs_elteres"),
                         ({"forras_keplet": "y = x^3"}, "nincs_hely"),
                         ({"veg_sor": 99}, "nincs_hely"),
                         ({"bizonyossag": "ismeretlen"}, "nem_biztos")):
            besz, ki = B.terv(sz, [{**j, **hiba}], frozenset())
            self.assertEqual((besz, okok(ki)), ([], [ok]), hiba)

    def test_kulcs_szoveg_egyezik_a_felismerovel(self):
        for k in (r"y = x^2", r"f(x) = \dfrac{1}{x}", r"\addplot[domain=0:3]{x^2};"):
            self.assertEqual(T.kulcs_szoveg(k), R.kulcs(k))


class TorlesDontes(unittest.TestCase):
    def rekord(self, sz):
        besz, _ = terv(sz)
        uj = B.beszur(sz, besz)
        return {"ut": "T.md", "kulcs": besz[0].kulcs, "blokk": besz[0].torzs, "sha": "abc123"}, uj, sz

    def test_dontesek(self):
        r, uj, eredeti = self.rekord("# T\n\nbevezető\n\n$$y = x^2$$\n\nvége\n")
        self.assertEqual(T.torles_dontes(r, uj), T.MEGVAN)
        self.assertEqual(T.torles_dontes(r, eredeti), T.TORLES)                       # a blokk eltűnt, a képlet marad
        self.assertEqual(T.torles_dontes(r, eredeti, visszavonva=True), T.VISSZAVONVA)
        self.assertEqual(T.torles_dontes(r, None), T.NINCS_JEGYZET)
        self.assertEqual(T.torles_dontes(r, "# T\n\nbevezető\n"), T.KEPLET_ELTUNT)
        szerk = uj.replace("y = x^2\n```", "y = x^2 + 1\n```")
        self.assertEqual(T.torles_dontes(r, szerk), T.SZERKESZTVE)                    # a kézi szerkesztés nem törlés
        athely = eredeti.replace("vége", "vége\n\n```plot\n" + r["blokk"] + "\n```")
        self.assertEqual(T.torles_dontes(r, athely), T.ATHELYEZVE)

    def test_atnevezes_allo_kulcs(self):
        """A kulcs a képletből jön, nem az útból: másik jegyzetben ugyanaz a képlet ugyanazt a kulcsot adja."""
        a = T.keplet_helyek("# A\n\n$$y = x^2$$\n")[0]["kulcs"]
        b = T.keplet_helyek("# Teljesen más cím\n\nszöveg\n\n$$ y=x^2 $$\n")[0]["kulcs"]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
