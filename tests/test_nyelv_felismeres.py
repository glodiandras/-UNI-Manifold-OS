"""Automatikus, helyi jegyzetnyelv-felismerés: valódi Apple-modell, szintetikus szövegek, vault és AppKit-indítás nélkül."""
import json
import http.server
import plistlib
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from tests.helpers import REPO, env, tmpdir


MAGYAR = ("A mai órán a folyók kialakulásáról tanultunk. A hegyekből érkező víz lassan alakítja a tájat, "
          "miközben hordalékot szállít a völgyek felé. A következő fejezetben a növények és az állatok kapcsolatát vizsgáljuk.")
ANGOL = ("During today's lesson we learned how rivers shape the landscape. Water flowing from the mountains "
         "carries sediment through the valleys and changes the surrounding environment. The next chapter examines "
         "the relationship between plants and animals in this ecosystem.")


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcrun"), "az Apple NaturalLanguage-próba macOS-t kér")
class NyelvFelismeresTeszt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tmpdir()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.gyoker = Path(cls.tmp.name)
        cls.csomag = cls.gyoker / "NyelvProba.app"
        cls.exe = cls.csomag / "Contents/MacOS/Manifold"
        cls.exe.parent.mkdir(parents=True)
        (cls.csomag / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "com.manifold.tests.nyelv", "CFBundleExecutable": "Manifold",
            "CFBundleName": "Language test", "CFBundlePackageType": "APPL", "NSPrincipalClass": "NSApplication",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        }))
        proba = cls.gyoker / "Proba.swift"
        proba.write_text('''import AppKit
import Foundation
import WebKit

@MainActor final class HidProba: NSObject, NSApplicationDelegate, WKScriptMessageHandler {
    let url: URL
    var webView: WKWebView?
    init(_ url: URL) { self.url = url }
    func applicationDidFinishLaunching(_ notification: Notification) {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let origin = "http://127.0.0.1:\\(url.port!)"
        config.userContentController.addScriptMessageHandler(NyelvUzenetKezelo(origin: { origin }),
                                                             contentWorld: .page, name: "nyelv")
        config.userContentController.add(self, name: "eredmeny")
        webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 640, height: 480), configuration: config)
        webView!.load(URLRequest(url: url))
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) {
            Proba.kiir(["hiba": "WebKit language reply timed out"])
            exit(1)
        }
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        Proba.kiir(message.body)
        exit(0)
    }
}

@main @MainActor struct Proba {
    static func kiir(_ eredmeny: Any) {
        let json = try! JSONSerialization.data(withJSONObject: eredmeny, options: [.sortedKeys])
        FileHandle.standardOutput.write(json)
        FileHandle.standardOutput.write(Data("\\n".utf8))
    }
    static func main() {
        if CommandLine.arguments.count == 3 && CommandLine.arguments[1] == "--webview" {
            let app = NSApplication.shared
            let kezelo = HidProba(URL(string: CommandLine.arguments[2])!)
            app.delegate = kezelo
            app.setActivationPolicy(.accessory)
            withExtendedLifetime(kezelo) { app.run() }
            return
        }
        let adat = FileHandle.standardInput.readDataToEndOfFile()
        let body = (try? JSONSerialization.jsonObject(with: adat, options: [.fragmentsAllowed])) ?? NSNull()
        let d = body as? [String: Any] ?? [:]
        let eredmeny: [String: Any]
        if d["tipus"] as? String == "eredet" {
            eredmeny = ["ok": NyelvFelismero.engedelyezett(foKeret: d["foKeret"] as? Bool ?? false,
                sema: d["sema"] as? String ?? "", gazda: d["gazda"] as? String ?? "", port: d["port"] as? Int ?? 0,
                origin: d["origin"] as? String)]
        } else if d["tipus"] as? String == "jeloltek" {
            eredmeny = NyelvFelismero.valaszt(d["jeloltek"] as? [String: Double] ?? [:]).json
        } else if let szoveg = NyelvFelismero.keresSzoveg(body) {
            var e = NyelvFelismero.felismer(szoveg).json
            e["hossz"] = szoveg.utf16.count
            eredmeny = e
        } else {
            eredmeny = NyelvFelismero.ismeretlen.json
        }
        kiir(eredmeny)
    }
}
''', encoding="utf-8")
        p = subprocess.run(["xcrun", "swiftc", "-swift-version", "5", "-parse-as-library", "-module-cache-path",
                            str(cls.gyoker / "cache"), "-o", str(cls.exe),
                            str(REPO / "shell/Sources/NyelvFelismero.swift"), str(proba)],
                           capture_output=True, text=True, timeout=180,
                           env=env(HOME=str(cls.gyoker / "home"), CLANG_MODULE_CACHE_PATH=str(cls.gyoker / "cache")))
        if p.returncode:
            raise AssertionError(p.stderr)
        p = subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(cls.csomag)],
                           capture_output=True, text=True, timeout=30)
        if p.returncode:
            raise AssertionError(p.stderr)

    def kerdez(self, body):
        p = subprocess.run([str(self.exe)], input=json.dumps(body, ensure_ascii=False), capture_output=True,
                           text=True, timeout=20, env=env(HOME=str(self.gyoker / "home")))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_magyar_es_angol_proza_a_valodi_modellen(self):
        for kod, szoveg in (("hu", MAGYAR), ("en", ANGOL)):
            with self.subTest(kod=kod):
                r = self.kerdez({"szoveg": szoveg})
                self.assertEqual(r["nyelv"], kod)
                self.assertGreaterEqual(r["bizalom"], 0.80)
                self.assertFalse(r["kevert"])

    def test_kevert_bekezdesek_az_os_automatikus_ellenorzesere_maradnak(self):
        for elvalaszto in ("\n\n", "\r\n\r\n"):
            with self.subTest(elvalaszto=repr(elvalaszto)):
                r = self.kerdez({"szoveg": MAGYAR + elvalaszto + ANGOL})
                self.assertIsNone(r["nyelv"])
                self.assertEqual(r["bizalom"], 0)
                self.assertTrue(r["kevert"])

    def test_ures_rovid_es_kod_szoveg_nem_eros_nyelvi_jel(self):
        kodok = ["", "123 + 456 = 579", "Hello world", "Szia, világ!", "alpha beta gamma",
                 "word " * 100,
                 f"```python\nprint({ANGOL!r})\n```",
                 f"const sentence = {json.dumps(ANGOL)};",
                 'int main() { std::cout << "This is a fairly long explanation of programming in English."; return 0; }',
                 f"---\ntitle: {ANGOL}\n---",
                 f"`{ANGOL}`", f"$$\n{ANGOL}\n$$", "https://example.com/" + "explanation/" * 40]
        for szoveg in kodok:
            with self.subTest(szoveg=szoveg[:80]):
                r = self.kerdez({"szoveg": szoveg})
                self.assertIsNone(r["nyelv"])
                self.assertEqual(r["bizalom"], 0)

    def test_a_kodot_nem_nezi_a_magyar_jegyzet_masodik_nyelvenek(self):
        r = self.kerdez({"szoveg": MAGYAR + '\n\n```javascript\nconst text = ' + json.dumps(ANGOL) + ';\n```'})
        self.assertEqual(r["nyelv"], "hu")
        self.assertFalse(r["kevert"])

    def test_a_bizonytalan_felismeres_nem_allit_nyelvet(self):
        for jeloltek in ({}, {"en": 0.6, "hu": 0.4}, {"en": 0.85, "hu": 0.8}, {"und": 1}, {"en": -1}):
            with self.subTest(jeloltek=jeloltek):
                r = self.kerdez({"tipus": "jeloltek", "jeloltek": jeloltek})
                self.assertIsNone(r["nyelv"])
                self.assertEqual(r["bizalom"], 0)

    def test_hibas_payload_biztonsagos_ismeretlen_valaszt_ad(self):
        for body in (None, 42, [], "text", {}, {"szoveg": None}, {"szoveg": 17}, {"szoveg": [ANGOL]}):
            with self.subTest(body=body):
                self.assertEqual(self.kerdez(body), {"nyelv": None, "bizalom": 0, "kevert": False})

    def test_a_minta_korlatozott_az_utana_jovo_szoveg_nem_befolyasol(self):
        # A második nyelv már a mintán kívül van; a kombináló karakterek sem kerülik meg a korlátot.
        r = self.kerdez({"szoveg": (MAGYAR + " ") * 50 + "\n\n" + ANGOL})
        self.assertEqual(r["hossz"], 8000)
        self.assertEqual(r["nyelv"], "hu")
        r = self.kerdez({"szoveg": "a" + "\u0301" * 12000})
        self.assertEqual(r["hossz"], 8000)
        self.assertIsNone(r["nyelv"])

    def test_csak_a_core_pontos_fokeret_originje_engedett(self):
        jo = {"tipus": "eredet", "foKeret": True, "sema": "http", "gazda": "127.0.0.1", "port": 5000,
              "origin": "http://127.0.0.1:5000"}
        self.assertTrue(self.kerdez(jo)["ok"])
        for csere in ({"foKeret": False}, {"sema": "https"}, {"gazda": "localhost"}, {"gazda": "evil.example"},
                      {"port": 50001}, {"origin": None}, {"origin": "http://127.0.0.1:5000@evil.example"}):
            with self.subTest(csere=csere):
                self.assertFalse(self.kerdez({**jo, **csere})["ok"])

    def test_a_hid_engedelye_es_automatikus_os_ellenorzes_be_van_kotve(self):
        controller = (REPO / "shell/Sources/AppController.swift").read_text(encoding="utf-8")
        self.assertIn("NSSpellChecker.shared.automaticallyIdentifiesLanguages = true", controller)
        self.assertIn("addScriptMessageHandler(NyelvUzenetKezelo", controller)
        self.assertIn('contentWorld: .page, name: "nyelv"', controller)
        self.assertIn("[weak self] in self?.origin", controller)
        kepesseg = (REPO / "shell/Sources/HelyiMenu.swift").read_text(encoding="utf-8")
        self.assertIn("nyelvFelismeres: true", kepesseg)

    def test_a_valodi_webkit_promise_valasz_es_iframe_vedelem(self):
        # A próba saját .app-ot, memóriabeli oldalt és szabad localhost-portot használ; sem core, sem vault nem indul.
        class Kezelo(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.path == "/frame":
                    js = ("window.webkit.messageHandlers.nyelv.postMessage({szoveg:" + json.dumps(ANGOL) + "})"
                          ".then(r => parent.postMessage({tipus:'iframe-valasz',r}, '*'))")
                else:
                    js = """(async () => {
                        const felismer = body => window.webkit.messageHandlers.nyelv.postMessage(body);
                        const hu = await felismer({szoveg: MAGYAR_SZOVEG});
                        const en = await felismer({szoveg: ANGOL_SZOVEG});
                        const hibas = await felismer({szoveg: 42});
                        const iframe = await new Promise(resolve => {
                            const f = document.createElement('iframe');
                            window.addEventListener('message', e => {
                                if (e.source === f.contentWindow && e.data?.tipus === 'iframe-valasz') resolve(e.data.r);
                            });
                            f.src = '/frame'; document.body.append(f);
                        });
                        window.webkit.messageHandlers.eredmeny.postMessage({hu,en,hibas,iframe});
                    })().catch(e => window.webkit.messageHandlers.eredmeny.postMessage({hiba:String(e)}));"""
                    js = js.replace("MAGYAR_SZOVEG", json.dumps(MAGYAR)).replace("ANGOL_SZOVEG", json.dumps(ANGOL))
                html = ("<!doctype html><html><body><script>" + js + "</script></body></html>").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Kezelo)
        szal = threading.Thread(target=server.serve_forever, daemon=True)
        szal.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            p = subprocess.run([str(self.exe), "--webview", url], capture_output=True, text=True, timeout=35,
                               env=env(HOME=str(self.gyoker / "home")))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            r = json.loads(p.stdout)
            self.assertNotIn("hiba", r)
            self.assertEqual(r["hu"]["nyelv"], "hu")
            self.assertEqual(r["en"]["nyelv"], "en")
            self.assertGreaterEqual(r["hu"]["bizalom"], 0.80)
            self.assertGreaterEqual(r["en"]["bizalom"], 0.80)
            self.assertEqual(r["hibas"], {"nyelv": None, "bizalom": 0, "kevert": False})
            self.assertEqual(r["iframe"], {"nyelv": None, "bizalom": 0, "kevert": False})
        finally:
            server.shutdown()
            server.server_close()
            szal.join(timeout=3)
