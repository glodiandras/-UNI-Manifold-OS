import Foundation

/// A héj két biztonsági döntése tiszta függvényekben (C11a, audit L3 és M8), hogy a `--selftest` táblázattal
/// ellenőrizhesse őket: (1) a WebView csak a core saját originjére navigálhat — **pontos** séma-, gazda- és
/// portegyezéssel, nem előtaggal (a `http://127.0.0.1:PORT@evil/` és a `…:PORT0/` nem illik); (2) a felület
/// kérésére külső cím csak `http`, `https` és `mailto` sémával nyílik meg (a felület nem megbízható oldal).
enum Biztonsag {
    /// Az `url` a core `origin`-jével azonos séma+gazda+port, felhasználónév és jelszó nélkül.
    static func azonosOrigin(_ url: URL, _ origin: String?) -> Bool {
        guard let origin, let o = URL(string: origin), let s = o.scheme?.lowercased(), let h = o.host?.lowercased() else { return false }
        return url.scheme?.lowercased() == s && url.host?.lowercased() == h && url.port == o.port
            && url.user == nil && url.password == nil
    }

    /// A megnyitható külső cím, vagy `nil` (ismeretlen vagy tiltott séma, gazda nélküli cím).
    static func megnyithatoKulsoCim(_ szoveg: String) -> URL? {
        guard let u = URL(string: szoveg.trimmingCharacters(in: .whitespacesAndNewlines)),
              let sema = u.scheme?.lowercased() else { return nil }
        switch sema {
        case "http", "https": return (u.host?.isEmpty == false) ? u : nil
        case "mailto": return u.absoluteString.count > "mailto:".count ? u : nil
        default: return nil
        }
    }

    /// A `--selftest` táblázata: → a hibás esetek leírása (üres: rendben).
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        let origin = "http://127.0.0.1:5000"
        let navigacio: [(String, Bool)] = [
            ("http://127.0.0.1:5000/", true), ("http://127.0.0.1:5000/a?b=1#c", true), ("http://127.0.0.1:5000", true),
            ("http://127.0.0.1:50001/", false), ("http://127.0.0.1:500/", false), ("http://127.0.0.1:5000@evil.example/", false),
            ("http://127.0.0.1:5000.evil.example/", false), ("http://user:pw@127.0.0.1:5000/", false),
            ("https://127.0.0.1:5000/", false), ("http://localhost:5000/", false), ("http://127.0.0.1/", false),
            ("https://pelda.hu/", false), ("file:///etc/passwd", false), ("javascript:alert(1)", false),
        ]
        for (cim, vart) in navigacio {
            let ok = URL(string: cim).map { azonosOrigin($0, origin) } ?? false
            if ok != vart { hibak.append("navigáció \(cim): \(ok) (várt: \(vart))") }
        }
        if azonosOrigin(URL(string: "http://127.0.0.1:5000/")!, nil) { hibak.append("navigáció: nincs origin, mégis engedett") }
        let kulso: [(String, Bool)] = [
            ("https://pelda.hu/x?y=1#z", true), ("http://pelda.hu", true), ("HTTPS://PELDA.HU", true), ("mailto:a@b.hu", true),
            ("javascript:alert(1)", false), ("file:///etc/passwd", false), ("data:text/html,x", false), ("ftp://pelda.hu", false),
            ("x-apple.systempreferences:", false), ("tel:+36123", false), ("https://", false), ("http:///x", false),
            ("mailto:", false), ("Jegyzet.md", false), ("", false), ("   ", false),
        ]
        for (cim, vart) in kulso {
            let ok = megnyithatoKulsoCim(cim) != nil
            if ok != vart { hibak.append("külső cím \(cim.debugDescription): \(ok) (várt: \(vart))") }
        }
        return hibak
    }
}
