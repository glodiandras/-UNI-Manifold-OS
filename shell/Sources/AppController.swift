import AppKit
import WebKit

/// Egy ablak, benne a felület a core-tól. Logika nincs a héjban (ARCHITECTURE 2.); a felülettől csak natív
/// kérés jön a „manifold” üzenetcsatornán: `kesz` (az első festés kész → a töltésjelző eltűnik), `tema` (a címsor is a
/// felület témáját követi), `megnyit` (külső link: csak http, https és mailto, az alapértelmezett alkalmazásban; C11a),
/// `naptar-engedely` / `naptar-allapot` (az EventKit-engedély kérése és lekérdezése a GUI-folyamatban; C29) és
/// `kenyszeritett-kilepes` (a „leáll” réteg gombja: a core azonnali leállítása és kilépés; C29.7b).
///
/// Az életciklus döntései (mi a mentési jelentés, mikor kérdezünk, mit mutat az üzenet) a tiszta `Eletciklus`-ban vannak,
/// táblázatosan tesztelve; ez az osztály csak az ablakokra és a folyamatokra köti rájuk.
@MainActor
final class AppController: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    /// Az ablak címsora. Csak a fejlesztői buildben (`-D MOS_DEVELOPER`): a kézi próbakörnyezet (`tests/kezi/proba_app.py`) a
    /// `MOS_PROBA_JELZES` változót állítja, és a címsor „PRÓBA — Manifold (klón)” lesz, hogy a klónon futó és a valódi példány ne
    /// legyen összekeverhető. A kiadott appban a címsor mindig „Manifold”.
    static let ablakCim: String = {
#if MOS_DEVELOPER
        let jel = ProcessInfo.processInfo.environment["MOS_PROBA_JELZES"] ?? ""
        return jel.isEmpty ? "Manifold" : "PRÓBA — Manifold (\(jel))"
#else
        return "Manifold"
#endif
    }()
#if MOS_DEVELOPER
    private let selftest: Bool
    /// `--selftest=<név>`: egy forgatókönyv (`kilepes`, `core-halal`, `core-ujraindul`, `kezfogas-ido`, `szerkesztes`, `lecsatolas`);
    /// nil: az alap önellenőrzés.
    private let forgatokonyv: String?
#else
    // A kiadott buildben nincs selftest: a konstans hamis, így a `selftest`-ágak kiesnek a binárisból.
    private var selftest: Bool { false }
    private var forgatokonyv: String? { nil }
#endif
    /// A folyamat indulása (C33: a „héj 2 s alatt kész” cél mérése — a selftest kiírja a `kesz` jelig eltelt időt).
    private let indulas = Date()
    private var window: NSWindow?
    private var webView: ManifoldWebView!
    private var toltesJelzo: ToltesJelzo?
    private var core: CoreProcess?
    private var origin: String?
    private var port: Int?
    /// A core API-titka (a kézfogásból): a lapba a betöltés előtt injektáljuk, újraindításkor visszaadjuk a core-nak.
    private var titok: String?
    private var gyoker: URL?
    private var shown = false
    private let naptarEngedely = NaptarEngedely()
    private var kezfogasMunka: DispatchWorkItem?
    private var coreHalalFolyamatban = false
    /// A core újraindításakor a lekért mentetlen szövegek (új porton indulva a vágólapra kerülnek).
    private var ujraindulasMentetlen: [Eletciklus.MentetlenSzoveg] = []
    private var webContentHalalok: [Date] = []
    /// A rendszerértesítések (E10): csak élő appban jön létre, a `--selftest` nem küld az Értesítési központba.
    private lazy var ertesitesKozpont: ErtesitesKozpont = {
        let k = ErtesitesKozpont()
        k.onKattintas = { [weak self] azon in
            guard let self, let js = ErtesitesLogika.kattintasJs(azon) else { return }
            self.ablakElotor()
            self.webView.evaluateJavaScript(js, completionHandler: nil)
        }
        return k
    }()
    /// A következő `kesz` után a felületen megjelenő üzenet (újratöltés, új porton újraindult core).
    private var kesobbiUzenet: (szint: String, cim: String, szoveg: String)?

#if MOS_DEVELOPER
    init(selftest: Bool, forgatokonyv: String? = nil) {
        self.selftest = selftest
        self.forgatokonyv = forgatokonyv
    }
#else
    override init() { super.init() }
#endif

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Az ablak-visszaállítás kikapcsolva: az OS ne írjon mentett ablakállapotot (Saved Application State). A héj a home alá
        // MÉGIS ír egyet: az AppKit/cfprefsd a ~/Library/Preferences/<Bundle.main.bundleIdentifier>.plist-be teszi a natív panelek (pl. a
        // helyesírás-panel) ablakkereteit — ez a megengedett kivétel a belső lemezes mentés (~/Manifold-backup) mellett;
        // a `bin/mos doctor` „home írások” tétele megnevezi, bármi mást jelez (C34, T189).
        UserDefaults.standard.register(defaults: ["NSQuitAlwaysKeepsWindows": false])
#if MOS_DEVELOPER
        if selftest {                                    // a biztonsági és életciklus-döntések táblázata (C11a, C29.7b)
            let hibak = Biztonsag.ellenorzes() + NaptarLogika.ellenorzes() + CoreProcess.ellenorzes() + Eletciklus.ellenorzes() + HelyiMenu.ellenorzes() + ErtesitesLogika.ellenorzes() + Kuka.ellenorzes()
            if !hibak.isEmpty { return finishSelftest(ok: false, note: "biztonsági próba: " + hibak.joined(separator: "; ")) }
        }
#endif
        if !selftest { _ = ertesitesKozpont }               // a kattintás-kezelő már indításkor él (E10)
        buildMenu()
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()      // nincs ~/Library/Caches és WebKit-tár
        config.userContentController.add(UzenetTovabbito(self), name: "manifold")
        webView = ManifoldWebView(frame: NSRect(x: 0, y: 0, width: 1240, height: 820), configuration: config)
        webView.onParancs = { [weak self] id in   // a natív helyi menü Manifold-parancsa (C32b): a híd ugyanazt a regisztert futtatja
            guard let js = HelyiMenu.parancsJs(id) else { return }
            self?.webView.evaluateJavaScript(js, completionHandler: nil)
        }
        webView.navigationDelegate = self
        // Az első festésig (és a WebContent újratöltésekor) az ablak témaszínű háttere látszik, nem fehér. A macOS-en ennek nincs
        // nyilvános megfelelője (az `underPageBackgroundColor` csak a túlgörgetett sávot színezi, az `isOpaque` csak olvasható),
        // ezért a WebKit KVC-kulcsa marad — de csak ha a setter létezik: egy jövőbeli WebKitben hiányzó kulcs ne omoljon össze
        // (`NSUndefinedKeyException`), legfeljebb az első festés előtt fehér a lap.
        if webView.responds(to: NSSelectorFromString("_setDrawsBackground:")) || webView.responds(to: NSSelectorFromString("setDrawsBackground:")) {
            webView.setValue(false, forKey: "drawsBackground")
        }
        if !selftest { buildWindow() }

        guard let root = RootLocator.locate(environment: ProcessInfo.processInfo.environment, bundle: Bundle.main.bundleURL) else {
            return fail("A Manifold alkalmazásmappája nem található. A Manifold.app-nak az alkalmazásmappájában kell lennie (bin/mos és config/os.toml mellett). A külső kötet nincs csatlakoztatva?")
        }
        self.gyoker = root
        indit(CoreProcess(root: root))
        // C29.6 (M5): a kötet lecsatolása (Finder-kiadás, diskutil) előtt mentünk és leállunk
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(kotetLecsatol(_:)),
                                                          name: NSWorkspace.willUnmountNotification, object: nil)
#if MOS_DEVELOPER
        if selftest {
            // a szkriptelt szerkesztés (C33) lépésenként saját határidővel fut: a teljes keret ehhez nagyobb
            let keret: Double = forgatokonyv == "szerkesztes" ? 90 : 40
            DispatchQueue.main.asyncAfter(deadline: .now() + keret) { [weak self] in self?.finishSelftest(ok: false, note: "időtúllépés") }
        }
#endif
    }

    /// A core indítása és a kézfogás (időkorláttal, T123). Az első indulás és az újraindítás ugyanezt használja.
    private func indit(_ uj: CoreProcess) {
        self.core = uj
        uj.onExit = { [weak self] in self?.coreExited() }
        uj.start { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                self.kezfogasMunka?.cancel()
                self.kezfogasMunka = nil
                switch result {
                case .success(let k):
                    self.coreElindult(port: k.port, titok: k.titok)
                case .failure(.failed(let msg)):
                    if self.coreHalalFolyamatban { self.ujraindulasHiba("A core nem indult el újra.\n\n\(msg)") }
                    else { self.fail("A core nem indult el.\n\n\(msg)") }
                case .failure(.foglalt(let pid, let vault)):
                    self.masikPeldany(pid: pid, vault: vault)
                }
            }
        }
        kezfogasVarakozas()
    }

    private func coreElindult(port p: Int, titok ujTitok: String?) {
        guard Eletciklus.titokJs(ujTitok) != nil else {
            return fail("A core nem adott érvényes API-titkot a kézfogásban (régi core, vagy hibás `MOS_API_TITOK`?), a felület nem érné el.")
        }
        let ujOrigin = "http://127.0.0.1:\(p)"
        let ujraindulas = coreHalalFolyamatban
        coreHalalFolyamatban = false
        if selftest, ujraindulas {                        // `--selftest=core-ujraindul`: az újraindítás a régi porton kell hogy menjen
            return finishSelftest(ok: p == port, note: p == port ? "a core újraindult ugyanazon a porton (\(p))"
                                                                  : "a core új porton indult (\(p)), a régi: \(port.map(String.init) ?? "?")")
        }
        if ujraindulas, p == port, ujTitok == titok {
            // ugyanazon a porton és titokkal indult újra: a lap és a benne lévő mentetlen szöveg megmarad, a WS magától újracsatlakozik
            kesobbiUzenet = nil
            webView.evaluateJavaScript(uzenetJs(szint: "info", cim: "A core újraindult",
                                                szoveg: "A szerkesztő újra próbálja a mentést; ha valami nem mentődött, jelezni fog."), completionHandler: nil)
            return
        }
        if ujraindulas, !ujraindulasMentetlen.isEmpty {
            // új porton indult: az új origin a lapot újratölti, a mentetlen szöveg elveszne → előbb a vágólapra
            vagolapra(Eletciklus.masolatSzoveg(ujraindulasMentetlen))
            kesobbiUzenet = ("figyelmeztetes", "A core új porton indult újra",
                             "A lap újratöltődött. A mentetlen szöveg a vágólapon van (\(ujraindulasMentetlen.count) jegyzet).")
        } else if ujraindulas {
            // mentetlen szöveg nélkül is szól (nem modális, a lap értesítése a `kesz` után): a lap ne töltődjön újra szó nélkül
            kesobbiUzenet = ("info", "A core új porton indult újra",
                             "A lap újratöltődött. Mentetlen jegyzetet a felület nem jelzett; a nyitott fülek a mentett állapotból töltődtek be.")
        }
        ujraindulasMentetlen = []
        port = p
        titok = ujTitok
        origin = ujOrigin
        // az API-titok a lapba a betöltés ELŐTT, a főkeretbe (az iframe-ek nem kapják): a felület ezzel hitelesít (35. döntés)
        let tartalom = webView.configuration.userContentController
        tartalom.removeAllUserScripts()
        if let js = Eletciklus.titokJs(ujTitok) {
            tartalom.addUserScript(WKUserScript(source: js, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        }
        // a héj képességei (C32b): a lap csak ennek láttán hagyja a natív helyi menüt nyitni, a régebbi héj a lap saját menüjét kapja
        tartalom.addUserScript(WKUserScript(source: HelyiMenu.kepessegekJs, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        tartalom.addUserScript(WKUserScript(source: EpitesAzonosito.js, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        webView.load(URLRequest(url: URL(string: "\(ujOrigin)/")!))
        // tartalék: ha a felület nem jelez (pl. nincs app/dist), a töltésjelző így is eltűnik
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) { [weak self] in self?.toltesJelzoElrejt() }
    }

    // MARK: felület

    private func buildWindow() {
        let w = NSWindow(contentRect: webView.frame, styleMask: [.titled, .closable, .miniaturizable, .resizable],
                         backing: .buffered, defer: false)
        w.title = AppController.ablakCim
        let tarto = NSView(frame: webView.frame)
        webView.frame = tarto.bounds
        webView.autoresizingMask = [.width, .height]
        tarto.addSubview(webView)
        let jelzo = ToltesJelzo(frame: tarto.bounds)
        tarto.addSubview(jelzo)
        toltesJelzo = jelzo
        w.contentView = tarto
        w.contentMinSize = NSSize(width: 760, height: 480)
        w.collectionBehavior.insert(.fullScreenPrimary)  // a zöld gomb és az Ablak menü „Teljes képernyő” (⌃⌘F) pontja
        w.isReleasedWhenClosed = false
        w.initialFirstResponder = webView
        w.delegate = self
        w.center()
        window = w
        showWindow()                                     // azonnal megjelenik a töltésjelzővel (T123), nem a `kesz` jelre
    }

    private func showWindow() {
        guard !shown, let window else { return }
        shown = true
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        fokuszVissza()
    }

    /// Az ablak (újra) az előtérbe: a kilépési kérdés „Vissza a szerkesztéshez” ága és a Dock-kattintás (T032). A `showWindow`
    /// csak az első megjelenítésre jó (a `shown` őr miatt egy bezárt vagy elrejtett ablakot nem hoz vissza).
    private func ablakElotor() {
        guard let window else { return }
        if window.isMiniaturized { window.deminiaturize(nil) }
        NSApp.unhide(nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        fokuszVissza()
    }

    private func toltesJelzoElrejt() {
        toltesJelzo?.removeFromSuperview()
        toltesJelzo = nil
    }

    // MARK: fókusz (C10.7, F3)

    /// Az ablak visszajöttekor (rejtés → visszahozás, appváltás, az ablak újra kulcsablak) a billentyűk a
    /// felülethez menjenek: a `WKWebView` legyen a first responder, és a lapon az elveszett fókusz álljon vissza
    /// (`window.manifold.fokusz`: a szerkesztő vagy a gyorskereső). Az AppKit saját visszaállítása után fut.
    private func fokuszVissza() {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.shown, let window = self.window, window.isVisible, !NSApp.isHidden else { return }
            let birtokolja = (window.firstResponder as? NSView).map { $0 === self.webView || $0.isDescendant(of: self.webView) } ?? false
            if !birtokolja { window.makeFirstResponder(self.webView) }
            self.webView.evaluateJavaScript("window.manifold?.fokusz?.()", completionHandler: nil)
        }
    }

    func applicationDidBecomeActive(_ notification: Notification) { fokuszVissza() }
    func applicationDidUnhide(_ notification: Notification) { fokuszVissza() }
    func windowDidBecomeKey(_ notification: Notification) { fokuszVissza() }

    /// Dock-kattintás, miközben nincs látható ablak (a felhasználó bezárta, de a kilépési kérdésre a „Vissza”-t választotta, vagy
    /// a kilépés még függőben): az ablak visszajön (T032).
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { ablakElotor() }
        return true
    }

    // MARK: a felület üzenetei (csak natív képesség)

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let origin, message.frameInfo.isMainFrame,
              message.frameInfo.securityOrigin.host == "127.0.0.1",
              "http://127.0.0.1:\(message.frameInfo.securityOrigin.port)" == origin,
              let body = message.body as? [String: Any], let tipus = body["tipus"] as? String else { return }
        switch tipus {
        case "kesz":
            if selftest { return selftestKesz("a felület kész") }
            toltesJelzoElrejt()
            if let u = kesobbiUzenet {
                kesobbiUzenet = nil
                webView.evaluateJavaScript(uzenetJs(szint: u.szint, cim: u.cim, szoveg: u.szoveg), completionHandler: nil)
            }
        case "tema":
            switch body["ertek"] as? String {
            case "vilagos": NSApp.appearance = NSAppearance(named: .aqua)
            case "sotet": NSApp.appearance = NSAppearance(named: .darkAqua)
            default: NSApp.appearance = nil
            }
        case "megnyit":
            // külső link a felülettől (C11a): csak http, https, mailto; a navigációs szabály a WebView-ban nem engedi
            if let szoveg = body["url"] as? String, let url = Biztonsag.megnyithatoKulsoCim(szoveg) {
                NSWorkspace.shared.open(url)
            }
        case "kenyszeritett-kilepes":
            // a „leáll” réteg gombja: a második ⌘Q megfelelője (a core SIGTERM-et kap, a futó lépések azonnal leállnak)
            quitRequests = max(quitRequests, 1)
            NSApp.terminate(nil)
        case "naptar-engedely":
            // az EventKit-engedélyt a GUI-folyamat kéri (a rendszer így a Manifold.app-nak tulajdonítja); a fő szál
            // nem blokkol: az eredmény a visszahívásban megy a felületnek
            naptarEngedely.kerd(esemeny: body["esemeny"] as? Bool ?? false, emlekezteto: body["emlekezteto"] as? Bool ?? false) { [weak self] eredmeny in
                self?.naptarJelez(eredmeny)
            }
        case "naptar-allapot":
            naptarJelez(naptarEngedely.allapot())
        case "ertesites":
            // rendszerértesítés (E10): a felület csak háttérben küldi; a szöveget és az azonosítót a héj ellenőrzi
            if !selftest, let e = ErtesitesLogika.fogad(body) { ertesitesKozpont.kuld(e) }
        case "helyi-menu":
            // a jegyzet natív helyi menüjének Manifold-parancsai (C32b): a lista a következő natív menü végére kerül
            webView.helyiMenuElemek(HelyiMenu.elemek(body["elemek"]))
        default:
            break
        }
    }

    /// A naptár-engedély állapotának jelzése a felületnek: `window.manifold.naptarEngedely({esemeny, emlekezteto})`
    /// (hiba esetén `{hiba}` is). A JSON a rendszer szerializálójából jön, így a JS-be ágyazás biztonságos.
    private func naptarJelez(_ adat: [String: Any]) {
        guard let json = try? JSONSerialization.data(withJSONObject: adat, options: [.sortedKeys]),
              let szoveg = String(data: json, encoding: .utf8) else { return }
        webView.evaluateJavaScript("window.manifold?.naptarEngedely?.(\(szoveg))", completionHandler: nil)
    }

    /// `window.manifold.hejUzenet({szint, cim, szoveg})` hívása (a JSON-ba szerializált szöveg a JS-be ágyazáskor biztonságos).
    private func uzenetJs(szint: String, cim: String, szoveg: String) -> String {
        let adat: [String: String] = ["szint": szint, "cim": cim, "szoveg": szoveg]
        guard let json = try? JSONSerialization.data(withJSONObject: adat, options: [.sortedKeys]),
              let t = String(data: json, encoding: .utf8) else { return "0" }
        return "window.manifold?.hejUzenet?.(\(t))"
    }

    /// A „leáll” réteg szövege a felületen (`window.manifold.leallAllapot`); nil: vissza a szerkesztéshez.
    private func leallAllapot(_ szoveg: String?) {
        guard let szoveg else { return webView.evaluateJavaScript("window.manifold?.leallAllapot?.(null)", completionHandler: nil) }
        guard let json = try? JSONSerialization.data(withJSONObject: [szoveg]), let t = String(data: json, encoding: .utf8) else { return }
        webView.evaluateJavaScript("window.manifold?.leallAllapot?.(\(t)[0])", completionHandler: nil)
    }

    private func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "A Manifold névjegye", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Manifold elrejtése", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let tobbiElrejt = appMenu.addItem(withTitle: "Többi elrejtése", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        tobbiElrejt.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(withTitle: "Összes megjelenítése", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Kilépés", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "Szerkesztés"); editItem.submenu = edit
        // Visszavonás / Újra (`undo:`/`redo:` a first responderre): a WKWebView a gyorsbillentyűt ELŐBB a lapnak adja — a CodeMirror
        // saját ⌘Z-je ott lefut és `preventDefault`-ot hív, ilyenkor a menüpont nem fut; ha mégis eljut a WebKithez (pl. üres
        // előzmény), a lap `beforeinput` `historyUndo` eseményt kap, amelyet a CodeMirror a saját előzményére köt — nincs
        // kettőzés. A sima `input`/`textarea` mezők (paletta, Bevitel, tulajdonságok) ⌘Z-je e menüpont nélkül nem működne.
        edit.addItem(withTitle: "Visszavonás", action: Selector(("undo:")), keyEquivalent: "z")
        let ujra = edit.addItem(withTitle: "Újra", action: Selector(("redo:")), keyEquivalent: "z")
        ujra.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(.separator())
        edit.addItem(withTitle: "Kivágás", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Másolás", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Beillesztés", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Összes kijelölése", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        // Nézet: a felület parancsregiszterének néhány parancsa (gyorsbillentyű nélkül: azt a felület kezeli,
        // így a ⌘P/⌘O/⇧⌘M egy helyen él; a menü a felfedezhetőségé).
        let viewItem = NSMenuItem(); main.addItem(viewItem)
        let view = NSMenu(title: "Nézet"); viewItem.submenu = view
        for (cim, id) in [("Parancspaletta", "hej.paletta"), ("Fájl megnyitása", "hej.valto"),
                          ("Manifold áttekintő", "manifold.vezerlo"), ("-", ""),
                          ("Oldalsáv", "hej.oldalsav"), ("Jobb panel", "hej.jobb-panel"),
                          ("Állapotsor", "hej.allapotsor"), ("Csend mód be/ki", "hej.csend"), ("-", ""),
                          ("Téma: a rendszer szerint", "tema.rendszer"), ("Téma: világos", "tema.vilagos"),
                          ("Téma: sötét", "tema.sotet")] {
            if cim == "-" { view.addItem(.separator()); continue }
            let item = NSMenuItem(title: cim, action: #selector(parancs(_:)), keyEquivalent: "")
            item.representedObject = id
            item.target = self
            view.addItem(item)
        }
        // Ablak (szabványos macOS-menü): kicsinyítés, nagyítás, teljes képernyő, „Hozd előre mind”; az ablaklistát az AppKit
        // tölti (`windowsMenu`). A ⌘W szándékosan nincs itt: a lap a fül bezárására használja, a menüpont az ablakot (és
        // az utolsó ablakkal az appot) zárná be.
        let ablakItem = NSMenuItem(); main.addItem(ablakItem)
        let ablak = NSMenu(title: "Ablak"); ablakItem.submenu = ablak
        ablak.addItem(withTitle: "Kicsinyítés", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        ablak.addItem(withTitle: "Nagyítás", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        let teljes = ablak.addItem(withTitle: "Teljes képernyő", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        teljes.keyEquivalentModifierMask = [.command, .control]
        ablak.addItem(.separator())
        ablak.addItem(withTitle: "Hozd előre mind", action: #selector(NSApplication.arrangeInFront(_:)), keyEquivalent: "")
        NSApp.mainMenu = main
        NSApp.windowsMenu = ablak
    }

    @objc private func parancs(_ sender: NSMenuItem) {
        guard let id = sender.representedObject as? String, id.allSatisfy({ $0.isLetter || $0 == "." || $0 == "-" }) else { return }
        webView.evaluateJavaScript("window.manifold?.parancs('\(id)')", completionHandler: nil)
    }

    /// Másik core fut ugyanezen a vaulton (T027): üzenet, **ablak nélkül**, és kilépés — második ablakot nem indítunk.
    private func masikPeldany(pid: Int?, vault: String?) {
        let uzenet = "Ugyanezen a vaulton már fut egy Manifold" + (pid.map { " (a core pid-je: \($0))" } ?? "")
            + (vault.map { " — \($0)" } ?? "") + ". Zárd be a másik Manifold-ablakot, és indítsd újra."
        if selftest { return finishSelftest(ok: false, note: uzenet) }
        window?.orderOut(nil)                            // a töltésjelzős ablak se maradjon a háttérben (az üzenet ablak nélküli)
        let alert = NSAlert()
        alert.messageText = "A Manifold már fut"
        alert.informativeText = uzenet
        alert.addButton(withTitle: "Kilépés")
        alert.runModal()
        NSApp.terminate(nil)
    }

    /// A Manifold-OS gyökerét hordozó kötet lecsatolására: a meglévő kilépési út (a felület ment, a core a futó
    /// feladat végén leáll és a belső lemezre menti a HEAD-et). A valódi kihúzás (K03) nem értesít: az az összeomlás-ág.
    @objc private func kotetLecsatol(_ n: Notification) {
        guard !selftest || forgatokonyv == "lecsatolas", let gyoker,
              CoreProcess.gyokertErint(devicePath: n.userInfo?["NSDevicePath"] as? String, gyoker: gyoker.path) else { return }
        NSApp.terminate(nil)
    }

    private func fail(_ message: String) {
        if selftest { return finishSelftest(ok: false, note: message) }
        ablakElotor()
        let alert = NSAlert()
        alert.messageText = "A Manifold nem indul"
        alert.informativeText = message
        alert.addButton(withTitle: "Kilépés")
        alert.runModal()
        core?.terminateNow()
        NSApp.terminate(nil)
    }

    // MARK: kézfogás-időkorlát (T123)

    /// A core a portját az indulási helyreállítás és az index indítása után írja ki; ha ez a határidőn belül nem történik meg,
    /// az ablak nem marad üresen és némán: „A core nem válaszol” a stderr végével, „Várok / Kilépés” választással.
    private func kezfogasVarakozas() {
        let mp = Eletciklus.kezfogasIdo(ProcessInfo.processInfo.environment)
        let munka = DispatchWorkItem { [weak self] in self?.kezfogasLejart(mp: mp) }
        kezfogasMunka = munka
        DispatchQueue.main.asyncAfter(deadline: .now() + mp, execute: munka)
    }

    private func kezfogasLejart(mp: TimeInterval) {
        kezfogasMunka = nil
        let farok = Eletciklus.farok(core?.stderrSzoveg() ?? "")
        let szoveg = "A core \(Int(mp.rounded(.up))) másodperce nem jelentkezett (nagy vaultnál vagy lassú lemeznél az indulás tovább tarthat)."
            + (farok.isEmpty ? "\n\nA core nem írt hibaüzenetet." : "\n\nA core utolsó sorai:\n" + farok)
        if selftest { return finishSelftest(ok: forgatokonyv == "kezfogas-ido", note: "A core nem válaszol: " + szoveg, kill: true) }
        ablakElotor()
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "A core nem válaszol"
        alert.informativeText = szoveg
        alert.addButton(withTitle: "Várok")
        alert.addButton(withTitle: "Kilépés")
        if alert.runModal() == .alertFirstButtonReturn {
            kezfogasVarakozas()
        } else {
            core?.terminateNow()
            NSApp.terminate(nil)
        }
    }

    // MARK: navigáció: csak a core saját címe

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        // pontos séma+gazda+port egyezés (nem előtag, audit L3): a `http://127.0.0.1:PORT@evil/` és a `…:PORT0/` nem illik
        let ok = action.request.url.map { Biztonsag.azonosOrigin($0, origin) || $0.scheme == "about" } ?? false
        decisionHandler(ok ? .allow : .cancel)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard selftest else { return }
        // app/dist nélkül a core üres lapot ad: az is rendben. Ha van felület, a `kesz` jelét várjuk.
        webView.evaluateJavaScript("document.body.children.length + '|' + document.title") { [weak self] value, _ in
            let v = value as? String
            if v == "0|Manifold" { self?.selftestKesz("üres lap (nincs app/dist)", ures: true) }
            else if v?.hasSuffix("|Manifold") != true { self?.finishSelftest(ok: false, note: "ismeretlen lap: \(v ?? "nincs válasz")") }
        }
    }

    /// A főkeret betöltése nem indult el (megszakítás, a core egy pillanatig nem elérhető, a navigációs szabály tiltása). A
    /// megszakítás és a szabály tiltása nem hiba (egy újabb betöltés vagy a `decidePolicyFor` váltja ki); a többinél
    /// „Újratöltés / Kilépés” — nem azonnali kilépés: a core fut, a már betöltött lap (és benne a szöveg) a helyén marad. A core
    /// halála és a kilépés a saját útján jelez, ide nem fut be. Az első indulás kézfogás-hibája továbbra is „A Manifold nem indul”.
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let e = error as NSError
        guard Eletciklus.navigaciosHiba(tartomany: e.domain, kod: e.code) == .ujratoltes else { return }
        if selftest { return finishSelftest(ok: false, note: "A lap nem töltődik be: \(e.localizedDescription)") }
        // rövid türelmi idő: ha a hibát a core halála okozta, a `coreExited` addigra jelez, és nem nyílik két párbeszéd
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.betoltesiHibaKerdes(e.localizedDescription) }
    }

    private var betoltesiHibaNyitva = false

    private func betoltesiHibaKerdes(_ ok: String) {
        guard !betoltesiHibaNyitva, quitRequests == 0, !coreHalalFolyamatban, core?.isRunning == true, let origin,
              let url = URL(string: "\(origin)/") else { return }
        betoltesiHibaNyitva = true
        defer { betoltesiHibaNyitva = false }
        ablakElotor()
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "A lap nem töltődött be"
        alert.informativeText = "A felület betöltése megszakadt (\(ok)). A core fut; az Újratöltés újra kéri a lapot. "
            + "Ha a hiba ismétlődik, lépj ki, és indítsd újra a Manifoldot."
        alert.addButton(withTitle: "Újratöltés")
        alert.addButton(withTitle: "Kilépés")
        if alert.runModal() == .alertFirstButtonReturn {
            webView.load(URLRequest(url: url))
        } else {
            NSApp.terminate(nil)                         // a szokásos kilépési út: ha a régi lap él, előbb ment
        }
    }

    /// A WebContent-folyamat meghalt (T122): az ablak különben üres maradna. A core, a port változatlan: újratöltés, és a
    /// felület értesít (a mentetlen szöveg ilyenkor elveszhetett — a mentés a szerkesztés közben folyamatos). Ha rövid időn
    /// belül sokadszor hal meg, nincs végtelen újratöltés.
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        let d = Eletciklus.webContentHalal(korabbi: webContentHalalok, most: Date())
        webContentHalalok = d.halalok
        if selftest { return finishSelftest(ok: false, note: "a WebContent-folyamat meghalt") }
        switch d.lepes {
        case .ujratolt:
            kesobbiUzenet = ("figyelmeztetes", "A felület újratöltődött",
                             "A felület folyamata váratlanul leállt. A mentetlen szöveg elveszhetett; a mentés a szerkesztés közben folyamatos.")
            webView.reload()
        case .feladja:
            ablakElotor()
            let alert = NSAlert()
            alert.alertStyle = .critical
            alert.messageText = "A felület többször leállt"
            alert.informativeText = "A felület folyamata rövid időn belül többször összeomlott, ezért nem töltöm újra magától. "
                + "A core és a mentett jegyzetek épek. Újratöltés után folytathatod, vagy kilépsz."
            alert.addButton(withTitle: "Újratöltés")
            alert.addButton(withTitle: "Kilépés")
            if alert.runModal() == .alertFirstButtonReturn {
                webContentHalalok = []
                webView.reload()
            } else {
                NSApp.terminate(nil)
            }
        }
    }

    // MARK: életciklus

    private var quitRequests = 0
    /// A kilépés előtti mentés legfeljebb ennyit vár (a felület egy mentési kérése 30 s-os korláttal fut).
    private let mentesKorlat: TimeInterval = 35

    /// Kilépés (H6): előbb a felület ment (és „leáll” állapotba kerül: nem szerkeszthető, T121), a jelentését megvárjuk
    /// (`{ok, mentetlen}`); ha maradt mentetlen vagy hibás jegyzet, a felület nem válaszolt, vagy a mentés nem végzett időben,
    /// kérdezünk, mielőtt a core leáll. A második ⌘Q kényszerít: SIGTERM — a core a folyamatban lévő írást így is befejezi.
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let core, core.isRunning else { return .terminateNow }
        quitRequests += 1
        if quitRequests > 1 { core.terminateNow(); return .terminateNow }   // második ⌘Q: kényszerítés
        let cim = window?.title ?? "Manifold"
        window?.title = AppController.ablakCim + " — mentés a kilépés előtt…"
        var eldontve = false
        let dont = { [weak self] (jelentes: Any?, hiba: String?, idotullepes: Bool) in
            guard let self, !eldontve else { return }
            eldontve = true
            var j = Eletciklus.ertelmez(jelentes, hiba: hiba)
            if idotullepes { j = .nincsValasz("a mentés nem fejeződött be \(Int(self.mentesKorlat)) másodperc alatt") }
            if let kerdes = Eletciklus.kilepesKerdes(j, idotullepes: idotullepes), !self.kilepesMentesNelkul(kerdes) {
                self.quitRequests = 0
                self.window?.title = cim
                self.leallAllapot(nil)                    // vissza a szerkesztéshez: a felület újra szerkeszthető
                NSApp.reply(toApplicationShouldTerminate: false)
                return
            }
            self.window?.title = AppController.ablakCim + " — leállítás a futó feladat végén…"
            self.leallAllapot("Leállítás a futó feladat végén…")
            self.core?.requestStop()
        }
        webView.callAsyncJavaScript("return await window.manifold?.mentes?.() ?? null", arguments: [:], in: nil,
                                    in: .page) { eredmeny in
            switch eredmeny {
            case .success(let v): dont(v, nil, false)
            case .failure(let e): dont(nil, "a felület hibát jelzett: \(e.localizedDescription)", false)
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + mentesKorlat) { dont(nil, nil, true) }
        return .terminateLater
    }

    /// A kérdés mentetlen jegyzetnél: true = kilépés mentés nélkül, false = vissza a szerkesztéshez (az ablak előjön: T032).
    private func kilepesMentesNelkul(_ kerdes: KilepesKerdes) -> Bool {
        if selftest {                                    // a selftestben nincs modális ablak: a kérdés maga a hiba
            finishSelftest(ok: false, note: "kilépéskor kérdés jött: \(kerdes.cim) — \(kerdes.szoveg)")
            return false
        }
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = kerdes.cim
        alert.informativeText = kerdes.szoveg
        alert.addButton(withTitle: "Vissza a szerkesztéshez")
        alert.addButton(withTitle: "Kilépés mentés nélkül")
        ablakElotor()
        return alert.runModal() == .alertSecondButtonReturn
    }

    private func coreExited() {
        if core?.foglalt == true { return }         // másik példány fut: az indító visszahívása már üzent és kilép
        if core?.stopping == true { NSApp.reply(toApplicationShouldTerminate: true); return }
        coreLeallt()
    }

    // MARK: a core váratlan halála (T031)

    /// A core futás közben meghalt. Nem a „nem indul” ablak: a stderr utolsó sorai, a mentetlen jegyzetek listája, és
    /// „Újraindítás” (a régi porton: a lap és a benne lévő szöveg megmarad) / „Mentetlen szöveg másolása” / „Kilépés”.
    private func coreLeallt() {
        guard !coreHalalFolyamatban else { return }
        coreHalalFolyamatban = true
        kezfogasMunka?.cancel()
        kezfogasMunka = nil
        let farok = Eletciklus.farok(core?.stderrSzoveg() ?? "")
        if selftest {
            if forgatokonyv == "core-ujraindul" { return coreUjraindit(mentetlen: []) }   // a gomb helyett: az újraindítás útja
            return finishSelftest(ok: forgatokonyv == "core-halal", note: "A core leállt: " + (farok.isEmpty ? "(nincs stderr)" : farok))
        }
        // a mentetlen szövegek a lapról (a core halott: nem ment, csak olvas); a lap sem válaszolhat → rövid időkorlát
        var kesz = false
        let tovabb = { [weak self] (elemek: [Eletciklus.MentetlenSzoveg]) in
            guard !kesz else { return }
            kesz = true
            self?.coreHalalKerdes(farok: farok, mentetlen: elemek)
        }
        webView.callAsyncJavaScript("return window.manifold?.mentetlen?.() ?? []", arguments: [:], in: nil, in: .page) { eredmeny in
            if case .success(let v) = eredmeny { tovabb(Eletciklus.mentetlenElemek(v)) } else { tovabb([]) }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { tovabb([]) }
    }

    private func coreHalalKerdes(farok: String, mentetlen: [Eletciklus.MentetlenSzoveg]) {
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = "A core leállt"
        alert.informativeText = Eletciklus.coreHalalSzoveg(farok: farok, mentetlen: mentetlen)
        alert.addButton(withTitle: "Újraindítás")
        if !mentetlen.isEmpty { alert.addButton(withTitle: "Mentetlen szöveg másolása") }
        alert.addButton(withTitle: "Kilépés")
        ablakElotor()
        let valasz = alert.runModal()
        if valasz == .alertFirstButtonReturn {
            coreUjraindit(mentetlen: mentetlen)
        } else if valasz == .alertSecondButtonReturn, !mentetlen.isEmpty {
            vagolapra(Eletciklus.masolatSzoveg(mentetlen))
            coreHalalKerdes(farok: farok, mentetlen: mentetlen)
        } else {
            NSApp.terminate(nil)                         // a core halott: az `applicationShouldTerminate` azonnal enged
        }
    }

    /// Újraindítás ugyanazon a porton (`MOS_CORE_PORT`): a lap origin-je változatlan, ezért a benne lévő mentetlen szöveg megmarad,
    /// a WS magától újracsatlakozik, a szerkesztő újra próbálja a mentést. Ha a port nem foglalható és a core új porton indul, a lap
    /// újratöltődik — ilyenkor a mentetlen szöveg előbb a vágólapra kerül (`coreElindult`), hogy ne vesszen el.
    private func coreUjraindit(mentetlen: [Eletciklus.MentetlenSzoveg]) {
        guard let gyoker else { return NSApp.terminate(nil) }
        ujraindulasMentetlen = mentetlen
        coreHalalFolyamatban = true                       // a `coreElindult` ebből tudja, hogy újraindításról van szó
        indit(CoreProcess(root: gyoker, port: port, titok: titok))
    }

    private func ujraindulasHiba(_ uzenet: String) {
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = "Az újraindítás nem sikerült"
        alert.informativeText = uzenet
        alert.addButton(withTitle: "Vissza")
        ablakElotor()
        alert.runModal()
        coreHalalKerdes(farok: Eletciklus.farok(core?.stderrSzoveg() ?? uzenet), mentetlen: ujraindulasMentetlen)
    }

    private func vagolapra(_ szoveg: String) {
        let p = NSPasteboard.general
        p.clearContents()
        p.setString(szoveg, forType: .string)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool { false }

    func applicationWillTerminate(_ notification: Notification) {
#if MOS_DEVELOPER
        if selftest, forgatokonyv == "kilepes" || forgatokonyv == "lecsatolas", !selftestDone {
            selftestDone = true
            print(forgatokonyv == "lecsatolas" ? "SELFTEST OK: a kötet lecsatolásának értesítésére a mentés után, rendezetten állt le"
                                               : "SELFTEST OK: a kilépés a mentés után, rendezetten ért véget")
        }
#endif
    }

#if !MOS_DEVELOPER
    // A kiadott buildben a selftest nincs: a hívóhelyek (`if selftest { … }`) konstans hamis ágak, ezek az üres törzsek tartják őket fordíthatóvá.
    private func finishSelftest(ok: Bool, note: String, kill: Bool = false) {}
    private func selftestKesz(_ megjegyzes: String, ures: Bool = false) {}
#else
    // MARK: --selftest: fejetlen ellenőrzés (kilépési kód 0/1) — csak a fejlesztői buildben

    private var selftestDone = false

    /// A felület kész (`kesz` jel, vagy üres lap app/dist nélkül): az alap önellenőrzés itt végez, a forgatókönyv itt indul.
    private func selftestKesz(_ megjegyzes: String, ures: Bool = false) {
        // C33 (1. cél): a héj indulásától a felület `kesz` jeléig (a core indulása, a kézfogás, a lap betöltése és első festése)
        print("SELFTEST IDŐ: a felület kész \(Int(Date().timeIntervalSince(indulas) * 1000)) ms")
        switch forgatokonyv {
        case "kilepes", "lecsatolas":
            if ures { return finishSelftest(ok: false, note: "a forgatókönyv felületet kér (nincs app/dist)") }
            kilepesForgatokonyv()
        case "szerkesztes":
            if ures { return finishSelftest(ok: false, note: "a szerkesztés forgatókönyve felületet kér (nincs app/dist)") }
            szerkesztesForgatokonyv()
        case "core-halal", "core-ujraindul":
            // a héj maga öli meg a core-t; a `coreExited` → `coreLeallt` ágnak kell jeleznie (vagy újraindítania)
            if let pid = core?.pid { kill(pid, SIGKILL) } else { finishSelftest(ok: false, note: "nincs core, amit megölhetnénk") }
        case "kezfogas-ido":
            finishSelftest(ok: false, note: "a core jelentkezett, pedig a kézfogás időtúllépését vártuk")
        default:
            finishSelftest(ok: true, note: megjegyzes)
        }
    }

    /// `--selftest=kilepes`: a megnyitott jegyzet szerkesztőjébe szöveg kerül (mint a gépelés), majd a valódi kilépési út
    /// (`NSApp.terminate` → `applicationShouldTerminate` → `window.manifold.mentes()` → a core leállítása) fut le. A Python teszt a
    /// kilépési kódot és a fájl bájtjait ellenőrzi. A szerkesztő nézetét a CodeMirror `cmView` jelén át érjük el.
    private func kilepesForgatokonyv() {
        let jel = ProcessInfo.processInfo.environment["MOS_SELFTEST_JEL"] ?? "KILEPES-PROBA"
        guard let json = try? JSONSerialization.data(withJSONObject: [jel]), let t = String(data: json, encoding: .utf8) else {
            return finishSelftest(ok: false, note: "a jel nem szerializálható")
        }
        let js = """
        (() => { if (!document.querySelector('.cm-content')) document.querySelector('[role=tab][title$=\".md\"]')?.click(); const c = document.querySelector('.cm-content'); const v = c && (c.cmTile?.root?.view || c.cmView?.view || c.cmView?.rootView?.view);
        if (!v) return 'nincs szerkesztő (' + (c ? 'a .cm-content megvan, de nincs cmTile/cmView' : 'nincs .cm-content') + '; fülek: ' + document.querySelectorAll('[role=tab]').length + '; oldal: ' + document.body.innerText.replace(/\\s+/g, ' ').slice(0, 160) + ')'; v.dispatch({changes: {from: 0, insert: \(t)[0]}, userEvent: 'input.type'}); return 'ok'; })()
        """
        var probak = 0
        func proba() {
            webView.evaluateJavaScript(js) { [weak self] value, _ in
                guard let self else { return }
                if value as? String == "ok" {
                    // a gépelés után azonnal kilépünk: a mentés a kilépés útján kell hogy megtörténjen, nem az 1 s-os autosave-en.
                    // Nem GCD-blokkból: a `terminate:` egymásba ágyazott eseményhurkot forgat, amíg a `terminateLater` válasza nem
                    // jön, és egy futó fő-sor blokkban a fő sorba küldött további blokkok (a core kilépésének jelzése) nem futnának le.
                    // A valódi ⌘Q is eseményből jön, nem GCD-blokkból. C33 (`lecsatolas`): a kötet lecsatolásának értesítése
                    // (a Finder-kiadás, diskutil) — ugyanaz a rendezett út, a héj saját megfigyelőjén át.
                    let lecsatolas = self.forgatokonyv == "lecsatolas"
                    let gyokerUt = self.gyoker?.path ?? ""
                    let idozito = Timer(timeInterval: 0.2, repeats: false) { _ in
                        if lecsatolas {
                            NSWorkspace.shared.notificationCenter.post(name: NSWorkspace.willUnmountNotification, object: NSWorkspace.shared,
                                                                       userInfo: ["NSDevicePath": gyokerUt])
                        } else {
                            NSApp.terminate(nil)
                        }
                    }
                    RunLoop.main.add(idozito, forMode: .common)
                } else if probak < 100 {
                    probak += 1
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { proba() }
                } else {
                    self.finishSelftest(ok: false, note: "a szerkesztő nem jelent meg: \(String(describing: value))")
                }
            }
        }
        proba()
    }

    /// `--selftest=szerkesztes` (C33, 3. pont): szkriptelt forgatókönyv a VALÓDI WebKitben — a mentett állapotból megnyílt jegyzet
    /// (megnyitás), a `![[…]]` beágyazás tartalma (a core feloldásával), gépelés (20 beszúrás, mindegyik a következő képkockáig
    /// mérve), az automatikus mentés (a core API-ján visszaolvasva), és egy ⌘-kattintás a kirajzolt `[[…]]` linkre (a célja
    /// megnyílik). A Python teszt készíti elő a vaultot (`PROBA-JEL`, `CEL-JEL`, alias `celhivatkozas`) és ellenőrzi a lemezt.
    private func szerkesztesForgatokonyv() {
        let jel = ProcessInfo.processInfo.environment["MOS_SELFTEST_JEL"] ?? "SZERKESZTES-PROBA"
        guard let titok, Eletciklus.titokJs(titok) != nil else { return finishSelftest(ok: false, note: "nincs érvényes API-titok") }
        webView.callAsyncJavaScript(SelftestSzkript.szerkesztes, arguments: ["jel": jel, "titok": titok], in: nil, in: .page) { [weak self] r in
            switch r {
            case .success(let v):
                self?.finishSelftest(ok: true, note: "szerkesztés: \(v as? String ?? "?")")
            case .failure(let e):
                self?.finishSelftest(ok: false, note: "szerkesztés: \(e.localizedDescription)")
            }
        }
    }

    private func finishSelftest(ok: Bool, note: String, kill: Bool = false) {
        guard !selftestDone else { return }
        selftestDone = true
        print(ok ? "SELFTEST OK: \(note)" : "SELFTEST HIBA: \(note)")
        guard let core, core.isRunning else { exit(ok ? 0 : 1) }
        core.onExit = { exit(ok ? 0 : 1) }
        if kill { core.terminateNow() } else { core.requestStop() }
    }
#endif
}

/// A töltésjelző (T123): az ablak azonnal megjelenik, amíg a core indul és a felület betöltődik — nem üres, fehér lap.
private final class ToltesJelzo: NSView {
    private let jelzo = NSProgressIndicator()
    private let felirat = NSTextField(labelWithString: "A Manifold indul…")

    override init(frame: NSRect) {
        super.init(frame: frame)
        autoresizingMask = [.width, .height]
        wantsLayer = true
        jelzo.style = .spinning
        jelzo.isIndeterminate = true
        jelzo.startAnimation(nil)
        felirat.textColor = .secondaryLabelColor
        felirat.font = .systemFont(ofSize: 13)
        addSubview(jelzo)
        addSubview(felirat)
    }

    required init?(coder: NSCoder) { fatalError("nem használt") }

    override var wantsUpdateLayer: Bool { true }

    override func updateLayer() {
        layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
    }

    override func layout() {
        super.layout()
        jelzo.frame = NSRect(x: (bounds.width - 32) / 2, y: bounds.height / 2, width: 32, height: 32)
        felirat.sizeToFit()
        felirat.frame.origin = NSPoint(x: (bounds.width - felirat.frame.width) / 2, y: bounds.height / 2 - 28)
    }
}

/// A WKUserContentController erősen tartja a kezelőt; ez a gyenge továbbító megszakítja a kört.
private final class UzenetTovabbito: NSObject, WKScriptMessageHandler {
    private weak var cel: (any WKScriptMessageHandler)?
    init(_ cel: any WKScriptMessageHandler) { self.cel = cel }
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        cel?.userContentController(c, didReceive: m)
    }
}
