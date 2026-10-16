"""F9 `epites.json` befagyasztás: a csomag jegyzéke (verzió, commit, build-idő, fájl-hash-ek), a futó core összevetése
(`epites.csomag_ellenoriz`, `/api/rendszer/epites` termékben), és a Health `telepites` sora, a doctor `bundle_fajlok` sora."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import doctor, egeszseg, epites
from tests.helpers import tmpdir


def ali_csomag(tmp: str) -> Path:
    """Egy kicsi, termék-alakú kódfa: `<tmp>/M.app/Contents/Resources/manifold`."""
    root = Path(tmp) / "M.app" / "Contents" / "Resources" / "manifold"
    for rel, t in {"bin/mos": "#!/bin/sh\n", "core/a.py": "A = 1\n", "core/al/b.py": "B = 2\n", "modulok/m/x.py": "X\n",
                   "config/os.toml": "[utak]\n", "app/dist/index.html": "<html></html>", "docs/user/GETTING-STARTED.md": "# Hi\n",
                   "runtime/python/bin/python3": "py", "runtime/venv/pyvenv.cfg": "home = ../python/bin\n"}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
    (root / "app" / "dist" / "epites.json").write_text(json.dumps({"verzio": 1, "felulet": "f" * 64, "mag": "m", "hej": "h"}))
    (root / "runtime" / "venv" / "bin").mkdir()
    (root / "runtime" / "venv" / "bin" / "python").symlink_to("../../python/bin/python3")
    return root


def befagyaszt(root: Path, **kw) -> dict:
    j = epites.befagyaszt(root, termek_verzio="1.2.3", build="7", commit="c" * 40, tiszta=True, epitve="2026-10-16T00:00:00Z",
                          felulet="f" * 64, hej="h" * 64, **kw)
    epites.fagyott_ut(root).write_text(json.dumps(j), encoding="utf-8")
    return j


class BefagyasztasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = ali_csomag(self._t.name)

    def test_a_jegyzek_tartalma(self):
        j = befagyaszt(self.root)
        self.assertEqual((j["verzio"], j["felulet"], j["hej"]), (1, "f" * 64, "h" * 64))
        self.assertEqual(j["mag"], epites.ujjlenyomat(self.root, "mag"))       # ugyanaz a bejárás, mint a futó core-é
        cs = j["csomag"]
        self.assertEqual((cs["formatum"], cs["termek_verzio"], cs["build"], cs["commit"], cs["tiszta"], cs["epitve"]),
                         (1, "1.2.3", "7", "c" * 40, True, "2026-10-16T00:00:00Z"))
        self.assertIn("core/al/b.py", cs["fajlok"])
        self.assertIn("app/dist/index.html", cs["fajlok"])
        self.assertNotIn("runtime/python/bin/python3", cs["fajlok"])          # a runtime összesítve, nem fájlonként
        self.assertEqual(set(cs["runtime"]), {"python", "venv"})
        self.assertEqual(cs["runtime"]["venv"]["fajl"], 2)                     # pyvenv.cfg + a symlink (a célja számít)
        self.assertEqual(epites.fagyott(self.root), j)

    def test_ep_csomag_ellenorzes(self):
        j = befagyaszt(self.root)
        e = epites.csomag_ellenoriz(self.root, runtime=True)
        self.assertTrue(e["ok"], e)
        self.assertEqual(e["ellenorizve"], len(j["csomag"]["fajlok"]))

    def test_modositas_hiany_tobblet_es_a_runtime(self):
        befagyaszt(self.root)
        (self.root / "core" / "a.py").write_text("A = 2\n", encoding="utf-8")
        (self.root / "docs" / "user" / "GETTING-STARTED.md").unlink()
        (self.root / "modulok" / "m" / "uj.py").write_text("", encoding="utf-8")
        e = epites.csomag_ellenoriz(self.root)
        self.assertFalse(e["ok"])
        self.assertEqual((e["modositott"], e["hianyzik"], e["tobblet"]),
                         (["core/a.py"], ["docs/user/GETTING-STARTED.md"], ["modulok/m/uj.py"]))
        # a runtime csak kérésre (a Health gyors útja nem hasheli az 1,4 GB-ot)
        (self.root / "runtime" / "python" / "bin" / "python3").write_text("mas", encoding="utf-8")
        self.assertEqual(epites.csomag_ellenoriz(self.root)["runtime_elteres"], [])
        self.assertEqual(epites.csomag_ellenoriz(self.root, runtime=True)["runtime_elteres"], ["python"])

    def test_a_bajtkod_es_a_ds_store_nem_szamit(self):
        befagyaszt(self.root)
        (self.root / "core" / "__pycache__").mkdir()
        (self.root / "core" / "__pycache__" / "a.cpython-314.pyc").write_bytes(b"\0")
        (self.root / "core" / ".DS_Store").write_bytes(b"\0")
        self.assertTrue(epites.csomag_ellenoriz(self.root)["ok"])

    def test_nem_csomag_gyoker_es_hibas_jegyzek(self):
        self.assertIsNone(epites.fagyott(Path(self._t.name)))                      # nem `*.app/Contents/Resources/manifold`
        self.assertIsNone(epites.fagyott(self.root))                               # nincs jegyzék
        epites.fagyott_ut(self.root).write_text(json.dumps({"verzio": 1, "felulet": "", "mag": "", "hej": ""}))
        self.assertIsNone(epites.fagyott(self.root))                               # a héj régi jegyzéke: nincs `csomag`
        self.assertFalse(epites.csomag_ellenoriz(self.root)["jegyzek"])


class CsomagAllapotTest(unittest.TestCase):
    """`/api/rendszer/epites` termékben: a befagyasztott jegyzékhez mér, nem a (csomagban nem létező) forráshoz."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = ali_csomag(self._t.name)

    def test_friss_csomag_ok_es_a_futo_reszek(self):
        j = befagyaszt(self.root)
        a = epites.allapot(self.root)
        self.assertTrue(a["ok"], a)
        self.assertEqual([r["resz"] for r in a["reszek"]], ["felulet", "hej", "csomag"])
        self.assertEqual((a["csomag"]["termek_verzio"], a["csomag"]["commit"]), ("1.2.3", "c" * 40))
        futo = {"mag": j["mag"], "felulet": j["felulet"], "hej": j["hej"]}
        self.assertTrue(epites.allapot(self.root, futo)["ok"])
        r = epites.allapot(self.root, {**futo, "mag": "regi"})
        self.assertEqual([x["resz"] for x in r["reszek"] if not x["friss"]], ["futó mag"])
        self.assertEqual(epites.allapot(self.root, {**futo, "mag": None})["futo_ismeretlen"], ["mag"])

    def test_modositott_csomag_es_hianyzo_jegyzek(self):
        befagyaszt(self.root)
        (self.root / "core" / "a.py").write_text("x", encoding="utf-8")
        a = epites.allapot(self.root)
        self.assertFalse(a["ok"])
        self.assertEqual(a["csomag"]["modositott"], ["core/a.py"])
        epites.fagyott_ut(self.root).unlink()
        a = epites.allapot(self.root)
        self.assertEqual((a["ok"], a["csomag"]["jegyzek"]), (False, False))

    def test_elavult_felulet_build(self):
        befagyaszt(self.root)
        (self.root / "app" / "dist" / "epites.json").write_text(json.dumps({"verzio": 1, "felulet": "masik"}))
        a = epites.allapot(self.root)
        r = {x["resz"]: x for x in a["reszek"]}
        self.assertFalse(r["felulet"]["friss"])
        self.assertFalse(r["csomag"]["friss"])                                     # a dist jegyzéke is a hash-elt fájlok közt van


class HealthTelepitesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = ali_csomag(self._t.name)

    def _sor(self, root: Path) -> dict:
        s = egeszseg._futtat("telepites", egeszseg._telepites, SimpleNamespace(root=root), None)
        self.assertEqual(len(s), 1)
        return s[0]

    def test_forras_checkoutban_tajekoztato(self):
        s = self._sor(Path(self._t.name))
        self.assertEqual((s["allapot"], s["uzenet_kod"]), (egeszseg.INFO, "telepites.forras"))

    def test_ep_csomag_ok_verzioval(self):
        befagyaszt(self.root)
        s = self._sor(self.root)
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["param"]), (egeszseg.OK, "telepites.ok", {"verzio": "1.2.3"}))
        self.assertIn("1.2.3", s["uzenet"])
        r = {x["kulcs"]: x["ertek"] for x in s["reszletek"]}
        self.assertEqual((r["verzio"], r["commit"], r["epitve"]), ("1.2.3", "c" * 12, "2026-10-16T00:00:00Z"))

    def test_eltero_csomag_hiba_reszletekkel(self):
        befagyaszt(self.root)
        (self.root / "core" / "a.py").write_text("x", encoding="utf-8")
        (self.root / "core" / "uj.py").write_text("x", encoding="utf-8")
        s = self._sor(self.root)
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["param"]), (egeszseg.HIBA, "telepites.modositott", {"db": 2}))
        r = {x["kulcs"]: x["ertek"] for x in s["reszletek"]}
        self.assertEqual((r["modositott"], r["tobblet"]), ("core/a.py", "core/uj.py"))
        self.assertNotIn("{", s["uzenet"])

    def test_jegyzek_nelkul_hiba(self):
        s = self._sor(self.root)
        self.assertEqual((s["allapot"], s["uzenet_kod"]), (egeszseg.HIBA, "telepites.hianyos"))
        epites.fagyott_ut(self.root).write_text("{nem json", encoding="utf-8")
        self.assertEqual(self._sor(self.root)["uzenet_kod"], "telepites.hianyos")

    def test_a_hej_regi_jegyzeke_csak_alap_ellenorzes(self):
        epites.fagyott_ut(self.root).write_text(json.dumps({"verzio": 1, "felulet": "f", "mag": "m", "hej": "h"}))
        s = self._sor(self.root)
        self.assertEqual((s["allapot"], s["uzenet_kod"]), (egeszseg.INFO, "telepites.alap"))


class DoctorCsomagFajlokTest(unittest.TestCase):
    def test_bundle_fajlok_sor(self):
        with tmpdir() as d:
            root = ali_csomag(d)
            befagyaszt(root)
            cfg = SimpleNamespace(root=root, path=lambda k: root / "app" / "dist")
            sorok: dict = {}

            def add(allapot, nev, uzenet, kod=None, **_):
                sorok[kod] = (allapot, uzenet)
            doctor._bundle_sorok(cfg, add)
            self.assertEqual(sorok["bundle_epites"][0], doctor.OK)
            self.assertEqual(sorok["bundle_fajlok"][0], doctor.OK)
            os.remove(root / "core" / "al" / "b.py")
            sorok.clear()
            doctor._bundle_sorok(cfg, add)
            self.assertEqual(sorok["bundle_fajlok"][0], doctor.HIBA)
            self.assertIn("core/al/b.py", sorok["bundle_fajlok"][1])


if __name__ == "__main__":
    unittest.main()
