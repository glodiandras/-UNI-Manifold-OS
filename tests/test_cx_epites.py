"""CX-001: az állapot tartalomra érzékeny, nem puszta fájllétezésre."""
import json
import tempfile
import unittest
from pathlib import Path
from core.epites import allapot, jegyzek


class EpitesTest(unittest.TestCase):
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
