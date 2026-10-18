"""12-templates-02 / 05 / 06 (Settings): sablon- és napi jegyzet-beállítások a validált, ütközésvédett íróban; a tartalmi nyelv az "Automatic"
mentés után is angol (nem magyar)."""
import tomllib
import unittest

from core import sablon, termek_beallitasok as b
from core.utvonalak import HttpError
from tests.helpers import tmpdir
from tests.multi_user import munkater, termek_cfg, termek_telepites


class SablonBeallitasTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.v, self.id = munkater(self.t.name, "Notes")
        self.cfg = termek_cfg(self.root, self.home, self.v)

    def ment(self, d):
        return b.ir(self.cfg, b.olvas(self.cfg)["rev"], d)

    def ujra(self):
        return termek_cfg(self.root, self.home, self.v)

    def test_alapertekek(self):
        f = b.olvas(self.cfg)["ertek"]["fajlok"]
        self.assertEqual((f["sablon_datum"], f["sablon_ido"], f["napi_sablon"], f["napi_inditaskor"]),
                         ("YYYY-MM-DD", "HH:mm", "", False))
        self.assertEqual((f["kivonas_utana"], f["kivonas_sablon"]), ("link", ""))

    def test_mentes_es_visszatoltes_a_motor_beallitasaiba(self):
        r = self.ment({"fajlok": {"sablon_datum": "DD.MM.YYYY", "sablon_ido": "h:mm A", "napi_sablon": "Templates/Daily.md",
                                  "napi_inditaskor": True, "kivonas_utana": "beagyazas", "kivonas_sablon": "Templates/Extract.md"}})
        f = r["ertek"]["fajlok"]
        self.assertEqual((f["sablon_datum"], f["napi_inditaskor"], f["kivonas_utana"]), ("DD.MM.YYYY", True, "beagyazas"))
        cfg = self.ujra()
        self.assertEqual(b.olvas(cfg)["ertek"]["fajlok"]["napi_sablon"], "Templates/Daily.md")
        sb = sablon.beallitasok(cfg)
        self.assertEqual((sb["datum"], sb["ido"]), ("DD.MM.YYYY", "h:mm A"))
        w = tomllib.loads((self.v / ".manifold/workspace.toml").read_text(encoding="utf-8"))
        self.assertEqual((w["sablon"]["datum"], w["sablon"]["ido"], w["naplo"]["sablon"]), ("DD.MM.YYYY", "h:mm A", "Templates/Daily.md"))
        self.assertEqual(w["beallitasok"]["fajlok"]["kivonas_sablon"], "Templates/Extract.md")

    def test_a_moment_formatum_visszaper_es_kapcsos_zarojel_szabalyos(self):
        self.ment({"fajlok": {"sablon_datum": "dddd [the] Do \\[x\\]"}})
        self.assertEqual(sablon.beallitasok(self.ujra())["datum"], "dddd [the] Do \\[x\\]")

    def test_ervenytelen_ertekek_400(self):
        for d in ({"sablon_datum": ""}, {"sablon_datum": "  "}, {"sablon_datum": "Y" * 201}, {"sablon_ido": ""},
                  {"sablon_datum": 5}, {"napi_sablon": "../Kint.md"}, {"napi_sablon": "/abs/x.md"}, {"napi_sablon": "{x}.md"},
                  {"napi_sablon": ".hidden/x.md"}, {"napi_inditaskor": "igen"}, {"napi_inditaskor": 1},
                  {"kivonas_utana": "kozepre"}, {"kivonas_sablon": "../x"}, {"kivonas_sablon": "a\nb"}):
            with self.assertRaises(HttpError, msg=str(d)) as e:
                self.ment({"fajlok": d})
            self.assertEqual(e.exception.code, 400, str(d))

    def test_a_tartalmi_nyelv_az_automatikus_mentes_utan_angol(self):
        self.ment({"altalanos": {"nyelv": "auto"}})
        self.assertEqual(sablon.tartalmi_nyelv(self.ujra()), "en")

    def test_a_kifejezett_nyelv_a_tartalmi_nyelv(self):
        self.ment({"altalanos": {"nyelv": "hu"}})
        self.assertEqual(sablon.tartalmi_nyelv(self.ujra()), "hu")
        self.ment({"altalanos": {"nyelv": "en"}})
        self.assertEqual(sablon.tartalmi_nyelv(self.ujra()), "en")


if __name__ == "__main__":
    unittest.main()
