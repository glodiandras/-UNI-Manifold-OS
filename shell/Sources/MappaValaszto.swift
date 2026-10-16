import AppKit
import WebKit

/// A natív mappaválasztó az import képernyőkhöz (F8): a felület `window.manifold.mappaValasztas(cim?)` hívása egy `mappaValaszto`
/// nevű, válaszképes WebKit-üzenetkezelőre megy (`{tipus: "mappa-valaszto", cim}`), a héj `NSOpenPanel`-t mutat, és EGYETLEN abszolút
/// útvonalat ad vissza (vagy `null`-t, ha a felhasználó elvetette / a kérés nem engedett).
///
/// Biztonsági szerződés (a híd nem lehet általános fájlolvasó):
/// - a panel nem ad vissza tartalmat, csak egy útvonal-szöveget; a héj semmit nem olvas a mappából;
/// - csak könyvtár választható (fájl nem, csomag — `.app`, `.bundle` — sem), egyszerre egy kijelölés;
/// - csak a core saját főkeretéből fogad kérést (ugyanaz az origin-szabály, mint a nyelvfelismerésnél);
/// - egyszerre egy panel nyílhat: a második kérés azonnal `null`-t kap, nem sorakozik;
/// - a panel csak akkor nyílik, ha az app aktív és az ablaka előtérben van (háttérből, takarásból nem);
/// - a panel szövege a héj fix szövege; a felület `cim` mezője legfeljebb a panel üzenete (vezérlőkarakter nélkül, rövidítve);
/// - a felület a kapott útvonalat kizárólag az import-előnézethez adja a core-nak (az előnézet nem ír).
/// A „csak a felhasználó kattintására” feltételt a felület oldala adja (`navigator.userActivation`), a héj ezt a fenti
/// feltételekkel egészíti ki: a natív oldal a böngészőmotor kattintás-jelzését nem látja.
enum MappaValasztoLogika {
    /// A panel üzenetének legnagyobb hossza (UTF-16 egység).
    static let maxCim = 200

    /// Egy érvényes kérés: a `cim` a panel üzenete (csak szöveg, vezérlőkarakter nélkül, rövidítve; hiányában `nil`).
    struct Kerelem: Equatable { let cim: String? }

    /// A kérés érvényessége a `tipus` mezőn múlik: csak a `mappa-valaszto` kap panelt, minden más alak `nil`.
    static func kerelem(_ body: Any) -> Kerelem? {
        guard let d = body as? [String: Any], d["tipus"] as? String == "mappa-valaszto" else { return nil }
        guard let nyers = d["cim"] as? String else { return Kerelem(cim: nil) }
        let tiszta = String(String.UnicodeScalarView(nyers.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }))
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let rovid = String(decoding: tiszta.utf16.prefix(maxCim), as: UTF16.self)
        return Kerelem(cim: rovid.isEmpty ? nil : rovid)
    }

    /// A panelen megjeleníthető / választható elem: könyvtár, de nem csomag.
    static func valaszthato(_ url: URL) -> Bool {
        guard let r = try? url.resourceValues(forKeys: [.isDirectoryKey, .isPackageKey]) else { return false }
        return r.isDirectory == true && r.isPackage != true
    }

    /// A választás eredménye a felületnek: egyetlen, normalizált, abszolút könyvtár-útvonal — különben `nil`.
    static func eredmeny(_ url: URL?) -> String? {
        guard let url, url.isFileURL else { return nil }
        let ut = url.standardizedFileURL.path
        guard ut.hasPrefix("/"), !ut.contains("\0"), valaszthato(url) else { return nil }
        return ut
    }

#if MOS_DEVELOPER
    /// A `--selftest` táblázata: → a hibás esetek leírása (üres: rendben). Csak a héj tiszta döntései; panel nem nyílik.
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        func cim(_ b: Any) -> String { guard let k = kerelem(b) else { return "<elutasít>" }; return k.cim ?? "<nincs cím>" }
        let kerelmek: [(Any, String)] = [
            (["tipus": "mappa-valaszto", "cim": "Choose the vault folder"], "Choose the vault folder"),
            (["tipus": "mappa-valaszto"], "<nincs cím>"),
            (["tipus": "mappa-valaszto", "cim": 5], "<nincs cím>"),
            (["tipus": "mappa-valaszto", "cim": "  A\u{0}B\nC\u{7}  "], "ABC"),
            (["tipus": "mappa-valaszto", "cim": String(repeating: "x", count: 500)], String(repeating: "x", count: maxCim)),
            (["tipus": "mas", "cim": "x"], "<elutasít>"), (["cim": "x"], "<elutasít>"), ("mappa-valaszto", "<elutasít>"), ([1, 2], "<elutasít>"),
        ]
        for (k, vart) in kerelmek where cim(k) != vart { hibak.append("mappa-valaszto kérés \(k): \(cim(k)) (várt: \(vart))") }
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("mos-mappa-valaszto-\(UUID().uuidString)")
        let mappa = tmp.appendingPathComponent("Mappa"), csomag = tmp.appendingPathComponent("Valami.app"), fajl = tmp.appendingPathComponent("a.md")
        defer { try? FileManager.default.removeItem(at: tmp) }
        do {
            try FileManager.default.createDirectory(at: mappa, withIntermediateDirectories: true)
            try FileManager.default.createDirectory(at: csomag.appendingPathComponent("Contents"), withIntermediateDirectories: true)
            try Data().write(to: fajl)
        } catch { return hibak + ["mappa-valaszto próba: nem készült tesztmappa (\(error))"] }
        if eredmeny(mappa) != mappa.standardizedFileURL.path { hibak.append("mappa-valaszto: a könyvtár nem választható") }
        if eredmeny(mappa.appendingPathComponent("..").appendingPathComponent("Mappa")) != mappa.standardizedFileURL.path { hibak.append("mappa-valaszto: a `..` nem normalizálódik") }
        if eredmeny(csomag) != nil { hibak.append("mappa-valaszto: a csomag választható") }
        if eredmeny(fajl) != nil { hibak.append("mappa-valaszto: a fájl választható") }
        if eredmeny(tmp.appendingPathComponent("nincs")) != nil { hibak.append("mappa-valaszto: a nem létező útvonal választható") }
        if eredmeny(nil) != nil { hibak.append("mappa-valaszto: nil eredmény") }
        if eredmeny(URL(string: "https://pelda.hu/mappa")) != nil { hibak.append("mappa-valaszto: nem fájl URL választható") }
        return hibak
    }
#endif
}

/// A panel delegáltja: a csomagok és a fájlok szürkék, nem választhatók.
@MainActor
private final class MappaPanelDelegalt: NSObject, NSOpenSavePanelDelegate {
    func panel(_ sender: Any, shouldEnable url: URL) -> Bool { MappaValasztoLogika.valaszthato(url) }
}

/// A WebKit erősen tartja a kezelőt, a gyenge closure-ök nem tartják életben az AppControllert.
@MainActor
final class MappaValasztoKezelo: NSObject, WKScriptMessageHandlerWithReply {
    private let origin: () -> String?
    private let ablak: () -> NSWindow?
    private var nyitva = false
    private let delegalt = MappaPanelDelegalt()

    init(origin: @escaping () -> String?, ablak: @escaping () -> NSWindow?) {
        self.origin = origin
        self.ablak = ablak
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        let eredet = message.frameInfo.securityOrigin
        guard NyelvFelismero.engedelyezett(foKeret: message.frameInfo.isMainFrame, sema: eredet.protocol,
                                          gazda: eredet.host, port: eredet.port, origin: origin()),
              let kerelem = MappaValasztoLogika.kerelem(message.body),
              !nyitva, NSApp.isActive, let ablak = ablak(), ablak.isKeyWindow, ablak.attachedSheet == nil else {
            replyHandler(NSNull(), nil)
            return
        }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = true          // az import célmappája lehet új is
        panel.treatsFilePackagesAsDirectories = false
        panel.resolvesAliases = true
        panel.delegate = delegalt
        panel.prompt = L("Mappa kiválasztása")
        if let cim = kerelem.cim { panel.message = cim }
        nyitva = true
        panel.beginSheetModal(for: ablak) { [weak self] valasz in
            self?.nyitva = false
            replyHandler(valasz == .OK ? (MappaValasztoLogika.eredmeny(panel.url) ?? NSNull()) : NSNull(), nil)
        }
    }
}
