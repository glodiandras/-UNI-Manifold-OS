"""C35a: a grafikon-modul szülő-oldali burka (`modulok/grafikon/__init__.py`) és a parancssor (`bin/mos grafikon`).
A burok a SymPy-t nem importálja: a kivágás a szülőben, a felismerés és az elemzés a homokozó gyermekében fut.
A homokozó helyett hamis (a gyermek belépési pontjait folyamaton belül hívó) példány megy, így a burok logikája
sandbox nélkül is tesztelhető; a valódi `sandbox-exec` alatt futó rész csak macOS-en."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO, alg_core, tmpdir

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

import grafikon  # noqa: E402
from grafikon import __main__ as CLI  # noqa: E402
from grafikon import felismeres as R  # noqa: E402
from grafikon import muveletek as M  # noqa: E402

MACOS = sys.platform == "darwin"

JEGYZET = (
    "# Függvények\n\nA parabola:\n\n$$f(x) = x^2 - 4x + 5$$\n\n"
    "```plot\ny = x^2\n```\n\nEgyenlet: $2x+1=0$, majd $y = 2x + 1$ egyenes.\n"
)


class HamisHomokozo:
    """A gyermek belépési pontjait folyamaton belül hívja; a hívásokat naplózza."""

    def __init__(self, hiba=None):
        self.beall = {"idokorlat_s": 10.0, "lepes_idokorlat_s": 3.0}
        self.hivasok: list[dict] = []
        self.hiba = hiba

    def futtat(self, feladatok, idokorlat_s=None, memoria_mb=None):
        ki = []
        for f in feladatok:
            self.hivasok.append({**f, "_idokorlat_s": idokorlat_s})
            if self.hiba:
                ki.append({"allapot": self.hiba, "ertek": None, "uzenet": f"hamis {self.hiba}", "mp": 0.0})
                continue
            fv = {"grafikon.felismeres": M.felismeres, "grafikon.elemzes": M.elemzes}[f["nev"]]
            ki.append({"allapot": "ok", "ertek": fv(**f["args"]), "uzenet": "", "mp": 0.0})
        return ki

    def egy(self, feladat, **kw):
        return self.futtat([feladat], **kw)[0]


class BurokTest(unittest.TestCase):
    def test_felismer_egy_gyermek_feladat(self):
        hk = HamisHomokozo()
        r = grafikon.felismer("y = x^2 + 2", homokozo=hk)
        self.assertEqual((r["fajta"], r["bizonyossag"]), ("fuggveny", "biztos"))
        self.assertEqual([f["nev"] for f in hk.hivasok], ["grafikon.felismeres"])

    def test_felismer_jegyzet_egyezik_a_folyamaton_beluli_utal(self):
        """A szülő kivág, a gyermek kifejezésenként felismer; az eredmény azonos a `felismeres.felismer_jegyzet`-tel."""
        hk = HamisHomokozo()
        ki = grafikon.felismer_jegyzet(JEGYZET, homokozo=hk)
        vart = R.felismer_jegyzet(JEGYZET)
        self.assertEqual([(j["sor"], j["veg_sor"], j["blokk_kovetkezik"], j["bizonyossag"], j["blokk"], j["kulcs"])
                          for j in ki],
                         [(j.sor, j.veg_sor, j.blokk_kovetkezik, j.bizonyossag, j.blokk, j.kulcs) for j in vart])
        self.assertEqual(len(hk.hivasok), 3)                      # mind a három kivágott képlet: a `nincs` is a gyermekben dől el

    def test_mindet_a_nincs_tetelt_is_visszaadja(self):
        ki = grafikon.felismer_jegyzet(JEGYZET, mindet=True, homokozo=HamisHomokozo())
        self.assertEqual([j["bizonyossag"] for j in ki], ["biztos", "nincs", "biztos"])

    def test_ures_jegyzet_nem_inditja_a_homokozot(self):
        hk = HamisHomokozo()
        self.assertEqual(grafikon.felismer_jegyzet("nincs itt képlet", homokozo=hk), [])
        self.assertEqual(hk.hivasok, [])

    def test_homokozo_hiba_nem_ellenorizheto_es_nem_dob(self):
        for allapot in ("homokozo_hiba", "idotullepes", "memoria", "tiltott"):
            hk = HamisHomokozo(hiba=allapot)
            r = grafikon.felismer("y = x", homokozo=hk)
            self.assertEqual((r["allapot"], r["bizonyossag"]), ("nem_ellenorizheto", "ismeretlen"), allapot)
            self.assertIn(allapot, r["ok"])
            self.assertEqual((r["blokk"], r["abra"]), ("", None))
            e = grafikon.elemzes("x^2", ["-1", "1"], homokozo=hk)
            self.assertEqual(e["allapot"], "homokozo_hiba", allapot)
            self.assertIn("homokozó", e["uzenet"])

    def test_elemzes_idokorlata_a_lepes_tobbszorose(self):
        hk = HamisHomokozo()
        e = grafikon.elemzes("x^2-4", ["-3", "3"], homokozo=hk)
        self.assertEqual(e["allapot"], "ok")
        self.assertEqual(hk.hivasok[0]["args"]["lepes_idokorlat_s"], 3.0)
        self.assertGreater(hk.hivasok[0]["_idokorlat_s"], 3.0 * 4)

    def test_elemzesek_egy_kotegben(self):
        hk = HamisHomokozo()
        ki = grafikon.elemzesek(["x^2-4", "1/x"], ["-3", "3"], homokozo=hk)
        self.assertEqual([k["allapot"] for k in ki], ["ok", "ok"])
        self.assertEqual(len(hk.hivasok), 2)

    def test_a_burok_nem_importal_sympyt(self):
        forras = (MODULOK / "grafikon" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("sympy", forras)
        self.assertNotIn("from . import felismeres", forras)


class ParancsorTest(unittest.TestCase):
    def fut(self, *argv, stdin: str = "", hk=None):
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            kod = CLI.main(list(argv), hk=hk if hk is not None else HamisHomokozo(), stdin=io.StringIO(stdin))
        return kod, ki.getvalue()

    def test_felismer(self):
        kod, ki = self.fut("felismer", "y = x^2")
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(ki)["bizonyossag"], "biztos")

    def test_elemez(self):
        kod, ki = self.fut("elemez", "x^2-4", "-3", "3")
        self.assertEqual(kod, 0)
        self.assertEqual([p["x"] for p in json.loads(ki)["zerushelyek"]], ["-2", "2"])

    def test_jegyzet_fajlbol(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "j.md"
            f.write_text(JEGYZET, encoding="utf-8")
            kod, ki = self.fut("jegyzet", str(f))
        self.assertEqual(kod, 0)
        self.assertEqual([j["sor"] for j in json.loads(ki)], [5, 11])

    def test_elemez_json_stdin_stdout(self):
        kerdes = {"fuggvenyek": ["x^2-4", "abs(x)"], "ablak": ["-3", "3"]}
        kod, ki = self.fut("elemez-json", stdin=json.dumps(kerdes))
        self.assertEqual(kod, 0)
        v = json.loads(ki)
        self.assertEqual([f["kifejezes"] for f in v["fuggvenyek"]], ["x**2 - 4", "Abs(x)"])
        self.assertEqual([f["allapot"] for f in v["fuggvenyek"]], ["ok", "ok"])

    def test_elemez_json_hibas_bemenet(self):
        for torzs in ("nem json", json.dumps({"fuggvenyek": "x", "ablak": [0, 1]}), json.dumps({"fuggvenyek": ["x"]}),
                      json.dumps({"fuggvenyek": ["x"] * 99, "ablak": [0, 1]})):
            kod, ki = self.fut("elemez-json", stdin=torzs)
            self.assertEqual(kod, 64, torzs)
            self.assertIn("hiba", json.loads(ki))

    def test_homokozo_hiba_a_json_ban_nem_kilepesi_kodban(self):
        """A core a JSON-ból dönt (503): a CLI ilyenkor is 0-val lép ki és a tételenkénti állapotot adja."""
        kod, ki = self.fut("elemez-json", stdin=json.dumps({"fuggvenyek": ["x"], "ablak": [0, 1]}),
                           hk=HamisHomokozo(hiba="homokozo_hiba"))
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(ki)["fuggvenyek"][0]["allapot"], "homokozo_hiba")


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class ValodiHomokozoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.cfg, _, _ = alg_core(cls._t.name)

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def test_vegponttol_vegpontig_a_sandbox_alatt(self):
        from homokozo import Homokozo
        hk = Homokozo(self.cfg)
        r = grafikon.felismer("f(x) = x^3 - 3x", homokozo=hk)
        self.assertEqual(r["bizonyossag"], "biztos")
        e = grafikon.elemzes(r["abra"]["elemek"][0]["kifejezes"], ["-3", "3"], homokozo=hk)
        self.assertEqual(e["allapot"], "ok", e)
        self.assertEqual([p["x"] for p in e["zerushelyek"]], ["-sqrt(3)", "0", "sqrt(3)"])
        self.assertEqual([(p["x"], p["tipus"]) for p in e["szelsoertekek"]], [("-1", "maximum"), ("1", "minimum")])

    def test_sandbox_nelkul_zarva_hibazik(self):
        from homokozo import Homokozo
        hk = Homokozo(self.cfg, sandbox_exec=str(Path(self._t.name) / "nincs-ilyen"))
        e = grafikon.elemzes("x", ["-1", "1"], homokozo=hk)
        self.assertEqual(e["allapot"], "homokozo_hiba")
        r = grafikon.felismer("y = x", homokozo=hk)
        self.assertEqual(r["allapot"], "nem_ellenorizheto")


if __name__ == "__main__":
    unittest.main()
