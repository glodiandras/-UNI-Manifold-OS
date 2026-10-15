"""C35b: a ```plot modell-ágának mérése (`modulok/grafikon/modell_meres.py`) álhívóval és folyamaton belüli felismerővel — modellt nem
tölt. Az éles blokk-író kérés (`modell_ag.javasol`) fut a C18 `grafikon` aranyhalmaz 15 képletén (kényszerítetten `bizonytalan`-ra
állítva) és a természetesen bizonytalan szintetikus függvényeken; a kapu: 0 téves blokk."""
import unittest
from pathlib import Path

from tests.grafikon_segedek import HamisHomokozo, R, javaslat_szotar

from grafikon import modell_meres as MM  # noqa: E402


def felismer(keplet):
    return javaslat_szotar(R.felismer(keplet))


class Hivo:
    def __init__(self, valaszok):
        self.valaszok, self.hivasok = valaszok, []

    def __call__(self, prompt, max_tokens):
        self.hivasok.append(prompt)
        return self.valaszok(prompt) if callable(self.valaszok) else self.valaszok


class Tetelek(unittest.TestCase):
    def test_halmazok(self):
        t = MM.tetelek(felismer)
        k = [x for x in t if x["halmaz"] == "kenyszeritett"]
        n = [x for x in t if x["halmaz"] == "termeszetes"]
        self.assertEqual(len(k), 15)
        self.assertTrue(all(x["javaslat"]["bizonyossag"] == "bizonytalan" and x["vart"] for x in k))     # a felismerő biztos volt: kényszerítve
        self.assertGreaterEqual(len(n), 3)
        self.assertTrue(all(x["vart"] is None and x["javaslat"]["abra"] for x in n))                      # természetesen bizonytalan, van referencia
        self.assertEqual(len(MM.tetelek(felismer, limit=4)), 4)


class Mérés(unittest.TestCase):
    def setUp(self):
        self.hk = HamisHomokozo()
        self.t = next(x for x in MM.tetelek(felismer) if x["id"] == "g01")                 # y = -x^2, ablak [-4, 4], zérushely 0

    def test_helyes_blokk_elfogadva_helyes_lefedett(self):
        s = MM.mer_tetel(self.t, Hivo("```plot\nx in [-4, 4]\ny in [-16, 4]\ny = -x^2\n```"), self.hk)
        self.assertEqual((s["allapot"], s["egyeztetes"], s["mod"], s["helyes"], s["lefedes"]), ("elfogadva", "referencia", "eles", True, True))
        self.assertIn("y = -x^2", s["blokk"])

    def test_szuk_ablak_nem_fedi_le(self):
        s = MM.mer_tetel(self.t, Hivo("```plot\nx in [1, 4]\ny in [-16, 0]\ny = -x^2\n```"), self.hk)
        self.assertEqual((s["allapot"], s["helyes"], s["lefedes"]), ("elfogadva", True, False))        # a 0 zérushely az ablakon kívül

    def test_masik_fuggveny_elvetve(self):
        s = MM.mer_tetel(self.t, Hivo("```plot\nx in [-4, 4]\ny = x^2\n```"), self.hk)
        self.assertEqual(s["allapot"], "elvetve")
        self.assertNotIn("helyes", s)

    def test_modell_hiba_es_ures_valasz(self):
        def hiba(p, m):
            raise RuntimeError("worker")
        self.assertEqual(MM.mer_tetel(self.t, hiba, self.hk)["allapot"], "modell_hiba")
        self.assertEqual(MM.mer_tetel(self.t, Hivo(""), self.hk)["allapot"], "elvetve")

    def test_teves_blokk_a_kapun_fennakad(self):
        """Ha a felismerő és az arany eltér (a felismerő tévedett), az elfogadott blokk téves: a kapu nem teljesül."""
        t = {**self.t, "vart": {**self.t["vart"], "kifejezes": "x^3"}}
        sorok = [MM.mer_tetel(t, Hivo("```plot\nx in [-4, 4]\ny = -x^2\n```"), self.hk)]
        self.assertFalse(sorok[0]["helyes"])
        o = MM.osszegez(sorok)
        self.assertEqual(o["osszes"]["teves"], 1)
        self.assertFalse(o["kapu"]["teves_0"])

    def test_osszegzes_es_kapu(self):
        helyes = Hivo("```plot\nx in [-4, 4]\ny in [-16, 4]\ny = -x^2\n```")
        sorok = [MM.mer_tetel(self.t, helyes, self.hk), MM.mer_tetel(self.t, Hivo("nem blokk ```"), self.hk)]
        o = MM.osszegez(sorok)
        self.assertEqual((o["osszes"]["n"], o["osszes"]["elfogadva"], o["osszes"]["referencia"], o["osszes"]["teves"],
                          o["osszes"]["lefedes"], o["osszes"]["eles_irhato"]), (2, 1, 1, 0, 1, 1))
        self.assertEqual(o["kenyszeritett"]["n"], 2)
        self.assertEqual(o["termeszetes"]["n"], 0)
        self.assertTrue(all(o["kapu"].values()))
        self.assertEqual(sum(o["osszes"]["elvetve"].values()), 1)
        self.assertFalse(MM.osszegez([])["kapu"]["van_ertekelt_tetel"])                              # értékelt tétel nélkül nincs kapu


class Main(unittest.TestCase):
    """A teljes mérés-parancs álworkerrel: folytatható jelentés, az összegzés és a kilépési kód a kapuból."""

    def fut(self, ki, valasz, *argv):
        import contextlib
        import io
        from unittest import mock
        from core.modell import kliens

        class Folyamat:
            def __init__(self, *a, **k):
                self.k = k

            def biztosit(self, timeout=0):
                return "http://worker"

            def leallit(self, *a, **k):
                pass
        with mock.patch.object(kliens, "Folyamat", Folyamat), \
                mock.patch.object(kliens, "chat", lambda u, m, **kw: {"choices": [{"message": {"content": valasz}}]}), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            kod = MM.main(["--modell", "qwen35_4b", "--ki", str(ki), *argv], homokozo=HamisHomokozo())
        return kod, out.getvalue()

    def test_main_jelentes_folytatas_es_kilepesi_kod(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            ki = Path(t) / "j.json"
            kod, _ = self.fut(ki, "```plot\nx in [-4, 4]\ny in [-16, 4]\ny = -x^2\n```", "--limit", "1")
            d = json.loads(ki.read_text(encoding="utf-8"))["qwen35_4b"]
            self.assertEqual((kod, len(d["sorok"]), d["osszegzes"]["osszes"]["teves"], d["prompt_verzio"]), (0, 1, 0, "grafikon-plot-1"))
            kod, _ = self.fut(ki, "```plot\nx in [-4, 4]\ny in [-16, 4]\ny = -x^2\n```", "--limit", "1")      # folytatás: a mért tétel kimarad
            self.assertEqual(len(json.loads(ki.read_text(encoding="utf-8"))["qwen35_4b"]["sorok"]), 1)
            kod, _ = self.fut(ki, "semmi", "--limit", "2")
            self.assertEqual(len(json.loads(ki.read_text(encoding="utf-8"))["qwen35_4b"]["sorok"]), 2)


if __name__ == "__main__":
    unittest.main()
