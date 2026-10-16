"""F5: valódi AppController + WebKit mentési/váltási életciklus, szintetikus helperrel és HTTP-core-ral.

A fixture az alkalmazás minden fájlírását a saját temp mappájába irányítja, és nem indít valódi core-t/modellt.
"""
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


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcrun"), "a WebKit munkatérváltás macOS-t kér")
class InditoValtasHejTeszt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tmpdir()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.gyoker = Path(cls.tmp.name)
        app = cls.gyoker / "ValtasProba.app/Contents"
        (app / "MacOS").mkdir(parents=True)
        shutil.copytree(REPO / "shell/Resources/en.lproj", app / "Resources/en.lproj")
        (app / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "com.manifold.tests.valtas", "CFBundleExecutable": "Manifold",
            "CFBundleName": "Workspace switching test", "CFBundlePackageType": "APPL", "NSPrincipalClass": "NSApplication",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        }))
        proba = cls.gyoker / "Proba.swift"
        proba.write_text(r'''import AppKit
import WebKit

@MainActor final class Proba: NSObject {
    let root: URL
    let mod: String
    var allapot = 0
    var kerdez = false
    var megszakitva = false
    var timer: Timer?
    init(root: URL, mod: String) { self.root = root; self.mod = mod }
    func kiir(_ obj: [String: Any], kod: Int32 = 0) {
        let adat = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
        print(String(decoding: adat, as: UTF8.self)); fflush(stdout)
        exit(kod)
    }
    func nezok(_ v: NSView) -> [NSView] { [v] + v.subviews.flatMap { nezok($0) } }
    func indit() {
        timer = Timer.scheduledTimer(withTimeInterval: 0.08, repeats: true) { [weak self] _ in self?.lep() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 18) { [weak self] in self?.kiir(["hiba": "timeout", "allapot": self?.allapot ?? -1], kod: 2) }
    }
    func lep() {
        guard !kerdez else { return }
        let osszes = NSApp.windows.compactMap(\.contentView).flatMap { nezok($0) }
        guard let web = osszes.compactMap({ $0 as? WKWebView }).first else { return }
        if allapot == 0 {
            kerdez = true
            web.evaluateJavaScript("window.ready === true") { [weak self] v, _ in
                guard let self else { return }; self.kerdez = false
                guard v as? Bool == true else { return }
                self.allapot = 1
                web.evaluateJavaScript("window.keepMe = 'cursor-and-history';")
                let elem = NSApp.mainMenu!.items.compactMap(\.submenu).flatMap(\.items).first { $0.title == "Open workspace…" }!
                NSApp.sendAction(elem.action!, to: elem.target, from: elem)
            }
        } else if allapot == 1 {
            if let gomb = osszes.compactMap({ $0 as? NSButton }).first(where: { $0.title == "Second workspace" && $0.isEnabled }) {
                allapot = 2; gomb.performClick(nil)
            }
        } else if allapot == 2 {
            let adat = (try? String(contentsOf: root.appendingPathComponent("events.ndjson"), encoding: .utf8)) ?? ""
            let esemenyek = adat.split(separator: "\n").compactMap { try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any] }
            let indul = esemenyek.filter { $0["tipus"] as? String == "indul" }
            let feliratok = osszes.compactMap { ($0 as? NSTextField)?.stringValue }.joined(separator: "\n")
            if mod == "cancel" && !megszakitva && esemenyek.contains(where: { $0["tipus"] as? String == "mentes" }) {
                if let vissza = osszes.compactMap({ $0 as? NSButton }).first(where: { $0.title == "Back to editing" }) {
                    megszakitva = true; vissza.performClick(nil)
                }
            }
            let teljes: Bool
            if mod == "cancel" { teljes = megszakitva && indul.count >= 2 }
            else if mod == "save-error" { teljes = feliratok.contains("previous workspace is still open") }
            else if mod == "fail-second" { teljes = indul.count >= 2 && feliratok.contains("synthetic startup failure") }
            else { teljes = indul.contains { ($0["vault"] as? String)?.hasSuffix("/B") == true } }
            guard teljes else { return }
            kerdez = true
            web.evaluateJavaScript("({ready: window.ready === true, vault: document.body.dataset.vault || '', keep: window.keepMe || '', leall: document.body.dataset.leall || ''})") { [weak self] v, _ in
                guard let self else { return }; self.kerdez = false
                guard let obj = v as? [String: Any], obj["ready"] as? Bool == true else { return }
                if self.mod == "cancel" && obj["leall"] as? String != "" { return }
                if self.mod != "save-error" && self.mod != "fail-second" && self.mod != "cancel", !(obj["vault"] as? String ?? "").hasSuffix("/B") { return }
                // A futó szintetikus core stdin-jét a szülő teszt lezárása előtt az app saját, mentő kilépése zárja.
                self.allapot = 3
                let kimenet: [String: Any] = ["oldal": obj, "esemenyek": esemenyek]
                let json = try! JSONSerialization.data(withJSONObject: kimenet, options: [.sortedKeys])
                try! json.write(to: self.root.appendingPathComponent("result.json"))
                if self.mod == "save-error" { exit(0) } // a szándékos mentési hibánál nincs felhasználói kilépési párbeszéd
                NSApp.terminate(nil)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { NSApp.terminate(nil) }
            }
        }
    }
}

@main @MainActor struct Futtato {
    static func main() {
        let app = NSApplication.shared
        let controller = AppController()
        app.delegate = controller; app.setActivationPolicy(.accessory)
        let proba = Proba(root: URL(fileURLWithPath: CommandLine.arguments[1]), mod: CommandLine.arguments[2])
        proba.indit()
        withExtendedLifetime((controller, proba)) { app.run() }
    }
}
''', encoding="utf-8")
        epites = cls.gyoker / "EpitesAzonosito.swift"
        epites.write_text('enum EpitesAzonosito { static let js = "" }\n')
        cls.exe = app / "MacOS/Manifold"
        fajlok = [str(p) for p in (REPO / "shell/Sources").glob("*.swift") if p.name != "App.swift"]
        p = subprocess.run(["xcrun", "swiftc", "-swift-version", "5", "-parse-as-library", "-module-cache-path",
                            str(cls.gyoker / "cache"), "-o", str(cls.exe), *fajlok, str(epites), str(proba)],
                           capture_output=True, text=True, timeout=180,
                           env=env(HOME=str(cls.gyoker / "home"), CLANG_MODULE_CACHE_PATH=str(cls.gyoker / "cache")))
        if p.returncode:
            raise AssertionError(p.stderr)
        p = subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app.parent)],
                           capture_output=True, text=True, timeout=30)
        if p.returncode:
            raise AssertionError(p.stderr)

    def setUp(self):
        self.tmp_case = tmpdir()
        self.addCleanup(self.tmp_case.cleanup)
        self.root = Path(self.tmp_case.name)
        (self.root / "bin").mkdir()
        (self.root / "config").mkdir()
        (self.root / "config/os.toml").write_text("")
        for nev in ("A", "B"):
            (self.root / nev).mkdir()
            (self.root / nev / "Note.md").write_text(f"Synthetic {nev}\n")
        script = self.root / "bin/mos"
        script.with_suffix(".py").write_text(textwrap.dedent(r'''
            import http.server, json, os, pathlib, sys, threading, time
            root = pathlib.Path(__file__).resolve().parents[1]
            mod = (root / 'mode').read_text()
            def jel(tipus, **adat):
                with (root / 'events.ndjson').open('a') as f:
                    f.write(json.dumps(dict(tipus=tipus, **adat)) + '\n')
            if sys.argv[1:] == ['indito']:
                r = json.load(sys.stdin)
                if r['muvelet'] == 'lista':
                    print(json.dumps({'ok': True, 'inditas': 'valaszto', 'utolso': None, 'munkaterek': [
                        {'id': 'b' * 32, 'nev': 'Second workspace', 'vault': str(root / 'B'), 'elerheto': True}]}))
                elif r['muvelet'] == 'megnyit':
                    print(json.dumps({'ok': True, 'munkater': {'id': 'b' * 32, 'nev': 'Second workspace', 'vault': str(root / 'B')}}))
                else: raise AssertionError(r)
                sys.exit(0)
            assert sys.argv[1:] == ['core', 'start']
            vault = os.environ['MOS_VAULT']
            if vault.endswith('/B') and mod == 'fail-second':
                jel('hiba', vault=vault)
                print(json.dumps({'hiba': 'synthetic_startup', 'uzenet': 'synthetic startup failure'}), flush=True)
                sys.exit(78)
            class Kezelo(http.server.BaseHTTPRequestHandler):
                def log_message(self, *a): pass
                def do_GET(self):
                    report = {'ok': False, 'mentetlen': [{'ut': 'Note.md', 'hiba': 'synthetic save error'}]} if mod == 'save-error' else {'ok': True, 'mentetlen': []}
                    html = '<!doctype html><html><body data-vault=' + json.dumps(vault) + '><script>'
                    html += 'window.ready=true;window.manifold={fokusz(){},hejUzenet(){},leallAllapot(v){document.body.dataset.leall=v||""},'
                    html += 'async mentes(){await fetch("/save",{method:"POST"});return ' + json.dumps(report) + '}};'
                    html += 'window.webkit.messageHandlers.manifold.postMessage({tipus:"kesz"});</script></body></html>'
                    b = html.encode(); self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
                def do_POST(self):
                    jel('mentes', vault=vault)
                    if mod != 'save-error': (pathlib.Path(vault) / 'Note.md').write_text('Synthetic saved edit\n')
                    self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers()
            class Szerver(http.server.HTTPServer): allow_reuse_address = True
            server = Szerver(('127.0.0.1', int(os.environ.get('MOS_CORE_PORT', 0))), Kezelo)
            port = server.server_address[1]
            jel('indul', vault=vault, port=port, munkater_valtas=os.environ.get('MOS_MUNKATER_VALTAS'))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print(json.dumps({'port': port, 'titok': os.environ.get('MOS_API_TITOK', 'synthetic-token-1234567890'), 'vault': vault}), flush=True)
            sys.stdin.buffer.read()
            if mod == 'cancel': time.sleep(.4)
            server.shutdown(); server.server_close(); jel('leall', vault=vault)
        '''), encoding="utf-8")
        script.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -B " + shlex.quote(str(script.with_suffix(".py"))) + ' "$@"\n')
        script.chmod(0o755)

    def fut(self, mod):
        (self.root / "mode").write_text(mod)
        p = subprocess.run([str(self.exe), str(self.root), mod], capture_output=True, text=True, timeout=25,
                           env=env(home=False, MOS_ROOT=str(self.root), MOS_VAULT=str(self.root / "A"),
                                   MOS_SETTINGS="", MOS_UI_NYELV="en"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue((self.root / "result.json").exists(), p.stdout + p.stderr)
        return json.loads((self.root / "result.json").read_text())

    def test_valtas_elott_ment_es_megvarja_a_regi_core_leallasat(self):
        r = self.fut("success")
        es = r["esemenyek"]
        a = str(self.root / "A")
        b = str(self.root / "B")
        self.assertEqual([(e["tipus"], e["vault"]) for e in es],
                         [("indul", a), ("mentes", a), ("leall", a), ("indul", b)])
        self.assertEqual((self.root / "A/Note.md").read_text(), "Synthetic saved edit\n")
        self.assertEqual(r["oldal"]["vault"], b)
        self.assertIsNone(es[0]["munkater_valtas"])
        self.assertEqual(es[-1]["munkater_valtas"], "1")

    def test_mentesi_hibanal_nem_indit_masik_core_t_es_megmarad_a_dom(self):
        r = self.fut("save-error")
        self.assertEqual([e["tipus"] for e in r["esemenyek"]], ["indul", "mentes"])
        self.assertEqual((self.root / "A/Note.md").read_text(), "Synthetic A\n")
        self.assertEqual((self.root / "B/Note.md").read_text(), "Synthetic B\n")
        self.assertEqual(r["oldal"]["keep"], "cursor-and-history")
        self.assertEqual(r["oldal"]["leall"], "")

    def test_uj_core_hiba_visszaallitja_a_regit_azonos_porton_dom_ujratoltes_nelkul(self):
        r = self.fut("fail-second")
        es = r["esemenyek"]
        self.assertEqual([e["tipus"] for e in es], ["indul", "mentes", "leall", "hiba", "indul"])
        self.assertEqual(es[0]["port"], es[-1]["port"])
        self.assertIsNone(es[-1]["munkater_valtas"])
        self.assertEqual(r["oldal"]["vault"], str(self.root / "A"))
        self.assertEqual(r["oldal"]["keep"], "cursor-and-history")
        self.assertEqual(r["oldal"]["leall"], "")

    def test_megsem_a_leallasi_varakozas_kozben_visszahozza_a_regi_munkateret(self):
        r = self.fut("cancel")
        es = r["esemenyek"]
        self.assertEqual([e["tipus"] for e in es], ["indul", "mentes", "leall", "indul"])
        self.assertTrue(all(e["vault"] == str(self.root / "A") for e in es))
        self.assertEqual(es[0]["port"], es[-1]["port"])
        self.assertEqual(r["oldal"]["keep"], "cursor-and-history")
        self.assertEqual(r["oldal"]["leall"], "")
