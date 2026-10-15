import Foundation

/// `Manifold --kuka` (CX-004, 80(c)): egy vaultbeli fájl vagy mappa a macOS Kukába. stdin: `{"ut": "<abszolút>", "gyoker": "<a vault gyökere>"}`;
/// stdout: `{"ok": true}`, vagy hibánál `{"ok": false, "kod": …, "hiba": "<magyar szöveg>"}` (`valasz`).
/// A core már ellenőrizte az utat; a segéd ettől függetlenül is csak a megadott vault gyökerén BELÜLI elemet mozgat:
/// nem `/`, nem a home, nem kötet-gyökér, nem maga a vault, nincs `..` szegmens, és a szülőmappa szimbolikus linkjei
/// feloldva is a gyökér alatt maradnak (maga az elem lehet link: akkor a link kerül a Kukába, nem a célja).
enum Kuka {
    static func futtat() -> Int32 {
        let adat = FileHandle.standardInput.readDataToEndOfFile()
        guard let d = (try? JSONSerialization.jsonObject(with: adat)) as? [String: Any],
              let ut = d["ut"] as? String, let gyoker = d["gyoker"] as? String else {
            print(valasz(kod: "ervenytelen_keres", hiba: "A Kuka-segéd érvénytelen kérést kapott (hiányzó út vagy gyökér)."))
            return 2
        }
        guard let elem = ellenoriz(ut: ut, gyoker: gyoker) else {
            print(valasz(kod: "tiltott_ut", hiba: "Ez az elem nem tehető a Kukába: csak a vaulton belüli, létező fájl vagy mappa "
                         + "mehet (maga a vault, egy kötet gyökere vagy a vaulton kívüli út nem)."))
            return 2
        }
        do {
            try FileManager.default.trashItem(at: elem, resultingItemURL: nil)
            print(valasz(kod: nil, hiba: nil))
            return 0
        } catch {
            print(valasz(kod: "kuka_hiba", hiba: hibaSzoveg(error)))
            return 1
        }
    }

    /// A segéd egysoros JSON-válasza: `{"ok": true}`, vagy `{"ok": false, "kod": "<gépi>", "hiba": "<magyar szöveg>"}` — a core a
    /// `hiba` szövegét adhatja tovább a felületnek. A szerializálót a rendszer adja: idézőjel, sortörés a szövegben sem töri a JSON-t.
    static func valasz(kod: String?, hiba: String?) -> String {
        var adat: [String: Any] = ["ok": kod == nil]
        if let kod { adat["kod"] = kod; adat["hiba"] = hiba ?? "A Kukába helyezés nem sikerült." }
        guard let json = try? JSONSerialization.data(withJSONObject: adat, options: [.sortedKeys]),
              let s = String(data: json, encoding: .utf8) else { return "{\"ok\":false,\"kod\":\"kuka_hiba\"}" }
        return s
    }

    /// A `trashItem` hibájának szövege a felhasználónak: a rendszer (lokalizált) leírása, az ismert esetekre magyar magyarázattal.
    /// Abszolút utat nem tesz bele (a rendszer leírása csak a fájl nevét idézi).
    static func hibaSzoveg(_ error: Error) -> String {
        let e = error as NSError
        let ok: String
        switch (e.domain, e.code) {
        case (NSCocoaErrorDomain, NSFileNoSuchFileError), (NSCocoaErrorDomain, NSFileReadNoSuchFileError):
            ok = "a fájl vagy mappa már nincs a helyén"
        case (NSCocoaErrorDomain, NSFileWriteNoPermissionError), (NSCocoaErrorDomain, NSFileReadNoPermissionError):
            ok = "nincs hozzá jogosultság"
        case (NSCocoaErrorDomain, NSFileWriteVolumeReadOnlyError):
            ok = "a kötet csak olvasható"
        case (NSCocoaErrorDomain, NSFeatureUnsupportedError):
            ok = "ezen a köteten nincs Kuka"
        default:
            ok = e.localizedDescription
        }
        return "A macOS nem tette a Kukába: \(ok)."
    }

    /// A `--selftest` táblázata → a hibás esetek leírása (üres: rendben).
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        func olvas(_ s: String) -> [String: Any]? { (try? JSONSerialization.jsonObject(with: Data(s.utf8))) as? [String: Any] }
        if let v = olvas(valasz(kod: nil, hiba: nil)) {
            if v["ok"] as? Bool != true || v["hiba"] != nil { hibak.append("Kuka siker: \(v)") }
        } else { hibak.append("Kuka siker: nem JSON") }
        let szoveg = "Idéző\"jel és\nsortörés"
        if let v = olvas(valasz(kod: "kuka_hiba", hiba: szoveg)) {
            if v["ok"] as? Bool != false || v["kod"] as? String != "kuka_hiba" || v["hiba"] as? String != szoveg { hibak.append("Kuka hiba: \(v)") }
        } else { hibak.append("Kuka hiba: nem JSON") }
        let nemLetezik = NSError(domain: NSCocoaErrorDomain, code: NSFileNoSuchFileError)
        if hibaSzoveg(nemLetezik) != "A macOS nem tette a Kukába: a fájl vagy mappa már nincs a helyén." {
            hibak.append("Kuka hibaszöveg: \(hibaSzoveg(nemLetezik))")
        }
        return hibak
    }

    /// → a Kukába tehető elem URL-je, vagy nil, ha az út tiltott.
    static func ellenoriz(ut: String, gyoker: String) -> URL? {
        func ervenyes(_ s: String) -> Bool {
            s.hasPrefix("/") && !s.contains("\0") && !s.split(separator: "/").contains("..") && !s.split(separator: "/").contains(".")
        }
        guard ervenyes(ut), ervenyes(gyoker) else { return nil }
        let fm = FileManager.default
        let home = URL(fileURLWithPath: NSHomeDirectory()).resolvingSymlinksInPath().path
        func vedett(_ u: URL) -> Bool {
            let p = u.path
            if p == "/" || p == home || p == "/Volumes" || p == "/Users" { return true }
            return (try? u.resourceValues(forKeys: [.isVolumeKey]))?.isVolume == true
        }
        var mappa: ObjCBool = false
        let g = URL(fileURLWithPath: gyoker).resolvingSymlinksInPath()
        guard fm.fileExists(atPath: g.path, isDirectory: &mappa), mappa.boolValue, !vedett(g) else { return nil }
        let nyers = URL(fileURLWithPath: ut)
        let nev = nyers.lastPathComponent
        guard !nev.isEmpty, nev != "/" else { return nil }
        let szulo = nyers.deletingLastPathComponent().resolvingSymlinksInPath()
        let elem = szulo.appendingPathComponent(nev)
        let gp = g.path.hasSuffix("/") ? g.path : g.path + "/"
        guard (szulo.path + "/").hasPrefix(gp) || szulo.path == g.path else { return nil }
        guard elem.path != g.path, elem.path.hasPrefix(gp), !vedett(elem) else { return nil }
        guard (try? fm.attributesOfItem(atPath: elem.path)) != nil else { return nil }   // lstat: a törött link is létező elem
        return elem
    }
}
