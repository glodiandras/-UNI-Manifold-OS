"""F5: a natív indító JSON-határa és valódi aszinkron helperfolyamata, kizárólag szintetikus mappákban."""
import json
import os
import plistlib
import shutil
import shlex
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.helpers import REPO, env, tmpdir


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcrun"), "a natív indítópróba macOS-t kér")
class InditoHejTeszt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tmpdir()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.gyoker = Path(cls.tmp.name)
        app = cls.gyoker / "InditoProba.app" / "Contents"
        (app / "MacOS").mkdir(parents=True)
        shutil.copytree(REPO / "shell/Resources/en.lproj", app / "Resources/en.lproj")
        (app / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "com.manifold.tests.indito", "CFBundleExecutable": "Manifold",
            "CFBundleName": "Launcher test", "CFBundlePackageType": "APPL", "NSPrincipalClass": "NSApplication",
        }))
        proba = cls.gyoker / "Proba.swift"
        proba.write_text(r'''import AppKit
import Foundation

@main @MainActor struct Proba {
    static func kiir(_ obj: [String: Any]) {
        let adat = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
        print(String(decoding: adat, as: UTF8.self))
    }
    static func main() {
        let argumentumok = CommandLine.arguments
        let adat = FileHandle.standardInput.readDataToEndOfFile()
        if argumentumok[1] == "--sor" {
            switch InditoKliens.ertelmez(adat) {
            case .haladas(let h): kiir(["tipus": "haladas", "adat": h])
            case .eredmeny(let h): kiir(["tipus": "eredmeny", "adat": h])
            case nil: kiir(["tipus": "hiba"])
            }
            return
        }
        let bemenet = try! JSONSerialization.jsonObject(with: adat) as! [String: Any]
        let root = URL(fileURLWithPath: argumentumok[2])
        if argumentumok[1] == "--ablak" {
            let app = NSApplication.shared
            app.setActivationPolicy(.accessory)
            var ablak: InditoAblak?
            ablak = InditoAblak(gyoker: root, vanSzerkeszto: false, onMegnyit: { vault in
                kiir(["megnyit": vault]); exit(0)
            }, onMegsem: { kiir(["megsem": true]); exit(0) })
            ablak!.megjelenit(automatikus: bemenet["automatikus"] as? Bool ?? false)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.9) {
                func szovegek(_ v: NSView) -> [String] {
                    let sajat = (v as? NSTextField).map { [$0.stringValue] } ?? (v as? NSButton).map { [$0.title] } ?? []
                    return sajat + v.subviews.flatMap { szovegek($0) }
                }
                kiir(["szovegek": szovegek(ablak!.window!.contentView!), "lathato": ablak!.window!.isVisible])
                ablak!.bezar(); exit(0)
            }
            withExtendedLifetime(ablak) { app.run() }
            return
        }
        var haladas: [[String: Any]] = []
        var pipa = false
        var megszakithato: Bool? = nil
        let kliens = InditoKliens(root: root, keres: bemenet)
        kliens.indit(haladas: { e in if case .haladas(let h) = e { haladas.append(h) } }, kesz: { r in
            var obj: [String: Any] = ["haladas": haladas, "fo_szal_szabad": pipa, "fo_szal": Thread.isMainThread]
            if let megszakithato { obj["megszakithato"] = megszakithato }
            switch r {
            case .success(let adat): obj["adat"] = adat
            case .failure(let h): obj["hiba"] = String(describing: h)
            }
            kiir(obj); exit(0)
        })
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.03) { pipa = true }
        if let mp = bemenet["megszakit_mp"] as? Double {
            DispatchQueue.main.asyncAfter(deadline: .now() + mp) { megszakithato = kliens.megszakit() }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 8) { kiir(["hiba": "timeout"]); exit(2) }
        withExtendedLifetime(kliens) { RunLoop.main.run() }
    }
}
''', encoding="utf-8")
        cls.exe = app / "MacOS/Manifold"
        p = subprocess.run(["xcrun", "swiftc", "-swift-version", "5", "-parse-as-library", "-module-cache-path",
                            str(cls.gyoker / "cache"), "-o", str(cls.exe),
                            *[str(REPO / "shell/Sources" / f) for f in
                              ("InditoKliens.swift", "InditoAblak.swift", "Lokalizacio.swift")], str(proba)],
                           capture_output=True, text=True, timeout=180,
                           env=env(HOME=str(cls.gyoker / "home"), CLANG_MODULE_CACHE_PATH=str(cls.gyoker / "cache")))
        if p.returncode:
            raise AssertionError(p.stderr)
        p = subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app.parent)],
                           capture_output=True, text=True, timeout=30)
        if p.returncode:
            raise AssertionError(p.stderr)

    def setUp(self):
        self.mappa = tmpdir()
        self.addCleanup(self.mappa.cleanup)
        self.root = Path(self.mappa.name)
        (self.root / "bin").mkdir()

    def helper(self, kod):
        ut = self.root / "bin/mos"
        py = ut.with_suffix(".py")
        py.write_text(textwrap.dedent(kod), encoding="utf-8")
        ut.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -B " + shlex.quote(str(py)) + ' "$@"\n', encoding="utf-8")
        ut.chmod(0o755)

    def fut(self, adat, mod="--kliens"):
        p = subprocess.run([str(self.exe), mod, str(self.root)], input=json.dumps(adat, ensure_ascii=False),
                           capture_output=True, text=True, timeout=15,
                           env=(env(home=False, MOS_UI_NYELV="en", MOS_VAULT="/never/open/this") if mod == "--ablak"
                                else env(HOME=str(self.gyoker / "home"), MOS_UI_NYELV="en", MOS_VAULT="/never/open/this")))
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        return json.loads(p.stdout)

    def test_szigoru_json_objektum_es_valodi_logikai_ok(self):
        for adat in ([], 1, "text", {}, {"ok": 1}, {"ok": "true"}, {"haladas": []}, {"hiba": "x"}):
            with self.subTest(adat=adat):
                self.assertEqual(self.fut(adat, "--sor"), {"tipus": "hiba"})
        self.assertEqual(self.fut({"ok": True}, "--sor")["tipus"], "eredmeny")
        self.assertEqual(self.fut({"ok": False, "hiba": "No space"}, "--sor")["adat"]["hiba"], "No space")
        self.assertEqual(self.fut({"haladas": {"lepes": "pillanat"}}, "--sor")["tipus"], "haladas")

    def test_toredezett_progress_es_eredmeny_kozben_a_fo_szal_szabad(self):
        self.helper('''
            import json, os, sys, time
            r = json.load(sys.stdin)
            assert sys.argv[1:] == ['indito']
            assert 'MOS_VAULT' not in os.environ
            assert os.environ['MOS_ELRENDEZES'] == 'termek'
            print('stderr noise is not JSON', file=sys.stderr, flush=True)
            print(json.dumps({'haladas': {'lepes': 'felmeres'}}), flush=True)
            time.sleep(.12)
            sys.stdout.write('{"ok":'); sys.stdout.flush()
            time.sleep(.03)
            sys.stdout.write('true,"nev":"Saját jegyzetek"}'); sys.stdout.flush()
        ''')
        r = self.fut({"muvelet": "felmer", "vault": str(self.root / 'Notes "$(touch nope)')})
        self.assertTrue(r["fo_szal_szabad"])
        self.assertTrue(r["fo_szal"])
        self.assertEqual(r["haladas"], [{"lepes": "felmeres"}])
        self.assertEqual(r["adat"]["nev"], "Saját jegyzetek")
        self.assertFalse((self.root / "nope").exists())

    def test_a_nemnulla_hibavalasz_ertelmezheto(self):
        self.helper('''
            import json, sys
            json.load(sys.stdin)
            print(json.dumps({'ok': False, 'kod': 'lemez', 'hiba': 'Not enough space'}))
            sys.exit(1)
        ''')
        self.assertEqual(self.fut({"muvelet": "lista"})["adat"]["hiba"], "Not enough space")

    def test_hibas_dupla_tulmeretes_es_hianyzo_eredmeny_elutasitott(self):
        kodok = ["print('not json')", "print('{\"ok\":true}\\n{\"ok\":true}')",
                 "print('x' * 1048577)", "print('{\"haladas\":{}}')", "print('{\"ok\":true}'); sys.exit(3)"]
        for kod in kodok:
            with self.subTest(kod=kod):
                self.helper("import json, sys\njson.load(sys.stdin)\n" + kod + "\n")
                self.assertEqual(self.fut({"muvelet": "lista"})["hiba"], "protokoll")

    def test_a_readonly_muvelhet_megszakithato(self):
        self.helper('''
            import json, time, sys
            json.load(sys.stdin)
            print('{"haladas":{"lepes":"felmeres"}}', flush=True)
            time.sleep(4)
            print('{"ok":true}', flush=True)
        ''')
        r = self.fut({"muvelet": "felmer", "megszakit_mp": .1})
        self.assertTrue(r["megszakithato"])
        self.assertEqual(r["hiba"], "megszakitva")

    def test_az_atomi_iras_nem_szakithato_felbe(self):
        self.helper('''
            import json, time, sys
            json.load(sys.stdin)
            print('{"haladas":{"lepes":"pillanat"}}', flush=True)
            time.sleep(.25)
            print('{"ok":true}', flush=True)
        ''')
        r = self.fut({"muvelet": "letrehoz", "megszakit_mp": .1})
        self.assertFalse(r["megszakithato"])
        self.assertTrue(r["adat"]["ok"])

    def test_hianyzo_helper_ujraprobalhato_hiba(self):
        self.assertEqual(self.fut({"muvelet": "lista"})["hiba"], "inditas")

    def test_hianyzo_legutobbi_mappa_mellett_a_valaszto_hasznalhato(self):
        self.helper('''
            import json, sys
            r = json.load(sys.stdin)
            assert r['muvelet'] == 'lista'
            print(json.dumps({'ok': True, 'utolso': 'a' * 32, 'inditas': 'utolso', 'munkaterek': [
                {'id': 'a' * 32, 'nev': 'Synthetic notes', 'vault': '/missing/synthetic-notes', 'elerheto': False}]}))
        ''')
        r = self.fut({"automatikus": True}, "--ablak")
        self.assertTrue(r["lathato"])
        feliratok = "\n".join(r["szovegek"])
        self.assertIn("Create workspace…", feliratok)
        self.assertIn("Open folder…", feliratok)
        self.assertIn("Try demo", feliratok)
        self.assertIn("Unavailable; connect the volume", feliratok)
        self.assertNotIn("megnyit", r)

    def test_az_utolso_elerheto_munkater_megnyitasat_is_a_helper_validalja(self):
        self.helper('''
            import json, sys
            r = json.load(sys.stdin)
            if r['muvelet'] == 'lista':
                print(json.dumps({'ok': True, 'utolso': 'b' * 32, 'inditas': 'utolso', 'munkaterek': [
                    {'id': 'b' * 32, 'nev': 'Synthetic notes', 'vault': '/synthetic-notes', 'elerheto': True}]}))
            else:
                assert r == {'muvelet': 'megnyit', 'vault': '/synthetic-notes'}
                print(json.dumps({'ok': True, 'munkater': {'id': 'b' * 32, 'nev': 'Synthetic notes', 'vault': '/synthetic-notes'}}))
        ''')
        r = self.fut({"automatikus": True}, "--ablak")
        self.assertEqual(r["megnyit"], "/synthetic-notes")

    def test_futo_munkater_nem_indit_masodik_core_t(self):
        self.helper('''
            import json, sys
            r = json.load(sys.stdin)
            assert r['muvelet'] == 'lista'
            print(json.dumps({'ok': True, 'utolso': 'd' * 32, 'inditas': 'utolso', 'munkaterek': [
                {'id': 'd' * 32, 'nev': 'Synthetic notes', 'vault': '/synthetic-notes', 'elerheto': True,
                 'fut': True, 'pid': 12345}]}))
        ''')
        r = self.fut({"automatikus": True}, "--ablak")
        self.assertTrue(r["lathato"])
        self.assertNotIn("megnyit", r)
        self.assertIn("already open in another Manifold window", "\n".join(r["szovegek"]))

    def test_valaszto_preferencia_nem_indit_automatikusan(self):
        self.helper('''
            import json, sys
            r = json.load(sys.stdin)
            assert r['muvelet'] == 'lista'
            print(json.dumps({'ok': True, 'utolso': 'c' * 32, 'inditas': 'valaszto', 'munkaterek': [
                {'id': 'c' * 32, 'nev': 'Synthetic notes', 'vault': '/synthetic-notes', 'elerheto': True}]}))
        ''')
        r = self.fut({"automatikus": True}, "--ablak")
        self.assertTrue(r["lathato"])
        self.assertNotIn("megnyit", r)


class InditoBekotesTeszt(unittest.TestCase):
    def test_a_kifejezett_es_selftest_indulas_nem_ker_valasztot(self):
        szoveg = (REPO / "shell/Sources/AppController.swift").read_text()
        self.assertIn('hely.termek && (kornyezet["MOS_VAULT"] ?? "").isEmpty && !selftest', szoveg)
        self.assertIn('self.core === uj', szoveg)  # a régi core visszahívása nem írhatja felül az újat
        self.assertIn('Eletciklus.kilepesKerdes(j, idotullepes: idotullepes)', szoveg)
        self.assertIn('core.requestStop()', szoveg)
