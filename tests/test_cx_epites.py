"""CX-001: az állapot tartalomra érzékeny, nem puszta fájllétezésre."""
import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock
from core.epites import RESZEK, allapot, befagyaszt, fo, jegyzek


class EpitesTest(unittest.TestCase):
    def test_a_hej_valtozat_explicit_es_nem_valtoztatja_a_forrasujjlenyomatokat(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "core").mkdir()
            (root / "core/a.py").write_text("fixture", encoding="utf-8")
            alap = jegyzek(root)
            # A felület jegyzékét a buildet indító környezet sem minősíti fejlesztői héjnak.
            with mock.patch.dict("os.environ", {"MOS_DEVELOPER_BUILD": "1"}):
                self.assertEqual(jegyzek(root), alap)
            self.assertNotIn("hej_valtozat", alap)
            for valtozat in ("fejlesztoi", "kiadasi"):
                with self.subTest(valtozat=valtozat):
                    j = jegyzek(root, hej_valtozat=valtozat)
                    self.assertEqual(j.pop("hej_valtozat"), valtozat)
                    self.assertEqual(j, alap)
            with self.assertRaises(ValueError):
                jegyzek(root, hej_valtozat="ismeretlen")

    def test_a_json_es_a_swiftbe_agyazott_js_azonos_valtozatot_es_hash_eket_kap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for resz, utak in RESZEK.items():
                f = root / utak[0] / "fixture.txt"
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(resz, encoding="utf-8")
            with mock.patch("core.epites.__file__", str(root / "core/epites.py")):
                for valtozat in ("fejlesztoi", "kiadasi"):
                    with self.subTest(valtozat=valtozat):
                        json_ki, swift_ki = io.StringIO(), io.StringIO()
                        with redirect_stdout(json_ki):
                            fo(["--hej-valtozat", valtozat])
                        with redirect_stdout(swift_ki):
                            fo(["--swift", "--hej-valtozat", valtozat])
                        swift = swift_ki.getvalue().strip()
                        eleje = "enum EpitesAzonosito { static let js = "
                        self.assertTrue(swift.startswith(eleje))
                        self.assertTrue(swift.endswith(" }"))
                        js = json.loads(swift[len(eleje):-2])
                        prefix = "window.__manifoldHejEpites = "
                        self.assertTrue(js.startswith(prefix))
                        j = json.loads(json_ki.getvalue())
                        self.assertEqual(json.loads(js[len(prefix):]), j)
                        self.assertEqual(j["hej_valtozat"], valtozat)
                        self.assertEqual({r: j[r] for r in RESZEK}, {r: jegyzek(root)[r] for r in RESZEK})
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as hiba:
                fo(["--hej-valtozat", "ismeretlen"])
            self.assertEqual(hiba.exception.code, 2)

    def test_az_allapot_a_hej_valtozatat_metaadatkent_adja_nem_hashkent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            j = jegyzek(root)
            felulet = root / "app/dist/epites.json"
            hej = root / "Manifold.app/Contents/Resources/epites.json"
            felulet.parent.mkdir(parents=True)
            hej.parent.mkdir(parents=True)
            felulet.write_text(json.dumps(j), encoding="utf-8")
            for v in ("fejlesztoi", "kiadasi", None, "ismeretlen"):
                with self.subTest(valtozat=v):
                    hej.write_text(json.dumps({**j, **({"hej_valtozat": v} if v else {})}), encoding="utf-8")
                    a = allapot(root)
                    self.assertTrue(a["ok"])
                    sorok = {r["resz"]: r for r in a["reszek"]}
                    self.assertNotIn("hej_valtozat", sorok["felulet"])
                    if v in ("fejlesztoi", "kiadasi"):
                        self.assertEqual(sorok["hej"]["hej_valtozat"], v)
                    else:
                        self.assertNotIn("hej_valtozat", sorok["hej"])

    def test_a_csomag_jegyzeke_top_level_mezorol_orzi_a_hej_valtozatat(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Manifold.app/Contents/Resources/manifold"
            dist = root / "app/dist/epites.json"
            dist.parent.mkdir(parents=True)
            dist.write_text(json.dumps({"felulet": "f"}), encoding="utf-8")
            args = dict(termek_verzio="1", build="1", commit="fixture", tiszta=True, epitve="2026-10-18T00:00:00Z",
                        felulet="f", hej="h", runtime=False)
            for v in ("fejlesztoi", "kiadasi"):
                with self.subTest(valtozat=v):
                    j = befagyaszt(root, **args, hej_valtozat=v)
                    self.assertEqual(j["hej_valtozat"], v)
                    self.assertNotIn("hej_valtozat", j["csomag"])
                    (root.parent / "epites.json").write_text(json.dumps(j), encoding="utf-8")
                    a = allapot(root)
                    self.assertTrue(a["ok"])
                    self.assertEqual(next(r for r in a["reszek"] if r["resz"] == "hej")["hej_valtozat"], v)
            self.assertNotIn("hej_valtozat", befagyaszt(root, **args))
            with self.assertRaises(ValueError):
                befagyaszt(root, **args, hej_valtozat="ismeretlen")

    def test_a_lokalizacio_valtozasa_elavultta_teszi_a_hejat(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            szotar = root / 'shell/Resources/en.lproj/Localizable.strings'
            szotar.parent.mkdir(parents=True)
            szotar.write_text('"Kilépés" = "Quit";\n', encoding='utf-8')
            j = jegyzek(root)
            for p in ('app/dist/epites.json', 'Manifold.app/Contents/Resources/epites.json'):
                f = root / p
                f.parent.mkdir(parents=True)
                f.write_text(json.dumps(j))
            self.assertTrue(allapot(root)['ok'])
            szotar.write_text('"Kilépés" = "Quit Manifold";\n', encoding='utf-8')
            r = {x['resz']: x for x in allapot(root)['reszek']}
            self.assertFalse(r['hej']['friss'])
            self.assertTrue(r['felulet']['friss'])

    def test_valtozas_es_hianyzo_jegyzek(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "core").mkdir()
            (root / "core/a.py").write_text("eredeti")
            self.assertFalse(allapot(root)["ok"])
            j = jegyzek(root)
            for p in ("app/dist/epites.json", "Manifold.app/Contents/Resources/epites.json"):
                f = root / p
                f.parent.mkdir(parents=True)
                f.write_text(json.dumps(j))
            self.assertTrue(allapot(root)["ok"])
            self.assertFalse(allapot(root, {'felulet': 'régi lap', 'hej': j['hej'], 'mag': j['mag']})['ok'])
            self.assertTrue(allapot(root, {r: j[r] for r in ('felulet', 'hej', 'mag')})['ok'])
            (root / "core/a.py").write_text("módosított")
            # a mag változása nem teszi elavulttá a felület- és a héj-buildet; csak a futó core-t
            self.assertTrue(allapot(root)["ok"])
            futo = {r: j[r] for r in ('felulet', 'hej', 'mag')}
            r = allapot(root, futo)
            self.assertFalse(r["ok"])
            self.assertEqual([x["resz"] for x in r["reszek"] if not x["friss"]], ["futó mag"])

    def test_minden_resz_csak_a_sajat_forrasahoz_merodik(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for f in ("core/a.py", "app/src/a.ts", "shell/Sources/A.swift"):
                (root / f).parent.mkdir(parents=True, exist_ok=True)
                (root / f).write_text("eredeti")
            j = jegyzek(root)
            for p in ("app/dist/epites.json", "Manifold.app/Contents/Resources/epites.json"):
                (root / p).parent.mkdir(parents=True)
                (root / p).write_text(json.dumps(j))
            (root / "app/src/a.ts").write_text("módosított")
            r = {x["resz"]: x for x in allapot(root)["reszek"]}
            self.assertEqual((r["felulet"]["friss"], r["felulet"]["elteres"]), (False, ["felulet"]))
            self.assertTrue(r["hej"]["friss"])
            (root / "app/src/a.ts").write_text("eredeti")
            (root / "shell/Sources/A.swift").write_text("módosított")
            r = {x["resz"]: x for x in allapot(root)["reszek"]}
            self.assertTrue(r["felulet"]["friss"])
            self.assertEqual((r["hej"]["friss"], r["hej"]["elteres"]), (False, ["hej"]))
