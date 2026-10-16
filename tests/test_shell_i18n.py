"""F4: az angol héjszótár és a valódi Foundation Bundle-feloldás, kizárólag ideiglenes csomagban.

A futtatási próba nem indít AppKitet, core-t, EventKit-engedélykérést vagy vaultot. A Kuka csak érvénytelen kérést kap.
"""
import collections
import json
import plistlib
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import REPO, env, tmpdir


HEJ = REPO / "shell"
EROFORRAS = HEJ / "Resources" / "en.lproj"
SZOVEG = r'"(?:[^"\\]|\\.)*"'


def szotar(ut: Path) -> list[tuple[str, str]]:
    return [(json.loads(k), json.loads(v))
            for k, v in re.findall(rf'({SZOVEG})\s*=\s*({SZOVEG})\s*;', ut.read_text(encoding="utf-8"))]


class HejSzotarTeszt(unittest.TestCase):
    def test_minden_forditasi_kulcshoz_van_nem_ures_angol_szoveg(self):
        parok = szotar(EROFORRAS / "Localizable.strings")
        angol = dict(parok)
        self.assertGreater(len(angol), 100)
        self.assertEqual(len(parok), len(angol), "ismétlődő fordítási kulcs")
        for fajl in sorted((HEJ / "Sources").glob("*.swift")):
            # A kommentben álló használati példák nem hívások.
            for n, sor in enumerate(fajl.read_text(encoding="utf-8").splitlines(), 1):
                if sor.lstrip().startswith("//"):
                    continue
                for nyers in re.findall(rf'\bL\(\s*({SZOVEG})', sor):
                    kulcs = json.loads(nyers)
                    with self.subTest(fajl=fajl.name, sor=n, kulcs=kulcs):
                        self.assertIn(kulcs, angol)
                        self.assertTrue(angol[kulcs].strip())
                        self.assertNotEqual(angol[kulcs], kulcs)

    def test_a_formatumparameterek_megmaradnak(self):
        def parameterek(szoveg):
            return collections.Counter(re.sub(r"^%\d+\$", "%", p)
                                       for p in re.findall(r"%(?:\d+\$)?[@diuoxXfFeEgGcsp%]", szoveg) if p != "%%")
        for kulcs, angol in szotar(EROFORRAS / "Localizable.strings"):
            with self.subTest(kulcs=kulcs):
                self.assertEqual(parameterek(kulcs), parameterek(angol))

    def test_a_rendszerengedelyek_angolul_es_lokalizalva_szallitanak(self):
        info = plistlib.loads((HEJ / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleDevelopmentRegion"], "en")
        self.assertEqual(info["CFBundleLocalizations"], ["en"])
        angol = dict(szotar(EROFORRAS / "InfoPlist.strings"))
        kulcsok = {k for k in info if k.endswith("UsageDescription")}
        self.assertEqual(set(angol), kulcsok)
        self.assertGreaterEqual(len(kulcsok), 5)
        for kulcs in kulcsok:
            with self.subTest(kulcs=kulcs):
                self.assertEqual(info[kulcs], angol[kulcs])
                self.assertTrue(angol[kulcs].startswith("Manifold "))
                self.assertNotRegex(angol[kulcs], "[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcrun"), "a Foundation Bundle-próba macOS-fordítót kér")
class HejAngolFutasTeszt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ideiglenes = tmpdir()
        cls.addClassCleanup(cls.ideiglenes.cleanup)
        cls.gyoker = Path(cls.ideiglenes.name)
        cls.futtathatok = {}
        for fejleszto in (False, True):
            nev = "Fejleszto" if fejleszto else "Kiadas"
            app = cls.gyoker / f"{nev}.app" / "Contents"
            (app / "MacOS").mkdir(parents=True)
            shutil.copytree(EROFORRAS, app / "Resources" / "en.lproj")
            shutil.copyfile(HEJ / "Info.plist", app / "Info.plist")
            proba = cls.gyoker / "Proba.swift"
            proba.write_text('''import Foundation
@main struct Proba {
    static func main() {
        if CommandLine.arguments.dropFirst().first == "--kuka" { exit(Kuka.futtat()) }
        let kerdes = Eletciklus.kilepesKerdes(.mentetlen([.init(ut: "Note.md", hiba: nil)]), idotullepes: false)!
        let adat: [String: String] = [
            "nyelv": Lokalizacio.nyelv,
            "menu": L("Kilépés"),
            "indulas": L("A Manifold indul…"),
            "formatum": L("• …és %d további", 12),
            "parameter": L("ismeretlen parancs: %@", "A %@\\nB"),
            "hianyzo": L("untranslated-test-key"),
            "kerdes": kerdes.cim,
            "figyelmeztetes": kerdes.szoveg,
            "kuka": Kuka.hibaSzoveg(NSError(domain: NSCocoaErrorDomain, code: NSFileNoSuchFileError)),
            "konfig": CoreProcess.konfigSzoveg(kod: "settings_toml_hibas", uzenet: "fixture"),
            "engedely": Bundle.main.object(forInfoDictionaryKey: "NSCalendarsUsageDescription") as? String ?? ""
        ]
        let json = try! JSONSerialization.data(withJSONObject: adat, options: [.sortedKeys])
        print(String(decoding: json, as: UTF8.self))
    }
}
''', encoding="utf-8")
            futtathato = app / "MacOS" / "Manifold"
            parancs = ["xcrun", "swiftc", "-swift-version", "5", "-parse-as-library", "-module-cache-path",
                       str(cls.gyoker / "cache"), "-o", str(futtathato)]
            if fejleszto:
                parancs.append("-DMOS_DEVELOPER")
            parancs += [str(HEJ / "Sources" / f) for f in
                        ("Lokalizacio.swift", "Eletciklus.swift", "Kuka.swift", "CoreProcess.swift")]
            parancs.append(str(proba))
            p = subprocess.run(parancs, capture_output=True, text=True, timeout=180,
                               env=env(HOME=str(cls.gyoker / "home"), CLANG_MODULE_CACHE_PATH=str(cls.gyoker / "cache")))
            if p.returncode:
                raise AssertionError(f"{nev} Swift-próba nem fordul:\n{p.stderr}")
            cls.futtathatok[fejleszto] = futtathato

    def futtat(self, fejleszto=False, args=(), bemenet=None, **extra):
        p = subprocess.run([str(self.futtathatok[fejleszto]), *args], input=bemenet, capture_output=True,
                           text=True, timeout=30, env=env(HOME=str(self.gyoker / "home"), **extra))
        return p, json.loads(p.stdout)

    def test_a_csomag_az_angol_szotarat_hasznalja(self):
        for fejleszto in (False, True):
            with self.subTest(fejleszto=fejleszto):
                p, adat = self.futtat(fejleszto)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(adat["nyelv"], "en")
                self.assertEqual(adat["menu"], "Quit")
                self.assertEqual(adat["indulas"], "Starting Manifold…")
                self.assertEqual(adat["formatum"], "• …and 12 more")
                self.assertEqual(adat["parameter"], "unknown command: A %@\nB")
                self.assertEqual(adat["hianyzo"], "untranslated-test-key")
                self.assertEqual(adat["kerdes"], "Not every note was saved")
                self.assertIn("unsaved changes will be lost", adat["figyelmeztetes"])
                self.assertEqual(adat["kuka"], "macOS could not move the item to the Trash: the file or folder is no longer there.")
                self.assertIn("A settings file is invalid", adat["konfig"])
                self.assertTrue(adat["konfig"].endswith("\n\nfixture"))
                self.assertTrue(adat["engedely"].startswith("Manifold reads calendar events"))

    def test_a_kiadas_nyelvet_nem_valtja_at_a_fejlesztoi_kapcsolo(self):
        p, adat = self.futtat(args=("--selftest",), MOS_UI_NYELV="hu")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(adat["nyelv"], "en")
        self.assertEqual(adat["menu"], "Quit")

    def test_a_fejlesztoi_identitas_megmarad_a_regi_selftest_tablaiban(self):
        for args, extra in (((), {"MOS_UI_NYELV": "hu"}), (("--selftest=kilepes",), {})):
            with self.subTest(args=args, extra=extra):
                p, adat = self.futtat(True, args, **extra)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(adat["nyelv"], "hu")
                self.assertEqual(adat["menu"], "Kilépés")

    def test_a_kuka_hibaja_angol_es_nem_tartalmaz_utvonalat(self):
        p, adat = self.futtat(args=("--kuka",), bemenet="invalid JSON")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(adat["kod"], "ervenytelen_keres")
        self.assertEqual(adat["hiba"], "The Trash helper received an invalid request (missing path or root).")
        self.assertNotIn(str(self.gyoker), adat["hiba"])
