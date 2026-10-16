import Foundation

/// Hol van a Manifold kódfája (`{os}`), és milyen elrendezésben fut (F3-DESIGN §2.1, §2.6)?
/// Jelöltek sorrendben: a `MOS_ROOT` környezeti változó (fejlesztéshez és tesztekhez), a csomag saját
/// `Contents/Resources/manifold`-ja (termék), végül az app szülőmappája (hordozható: a `Manifold.app` a checkout gyökerében
/// él). Beégetett út, mentett beállítás és kötet-átnézés nincs (CLAUDE.md §4). A termék-elrendezést az út alakja dönti el,
/// pontosan úgy, mint a `core/config.elrendezes` (`*.app/Contents/Resources/manifold`).
enum RootLocator {
    /// Érvényes gyökér: van benne futtatható `bin/mos` és `config/os.toml`.
    static func isValid(_ url: URL) -> Bool {
        let fm = FileManager.default
        return fm.isExecutableFile(atPath: url.appendingPathComponent("bin/mos").path)
            && fm.fileExists(atPath: url.appendingPathComponent("config/os.toml").path)
    }

    /// Termék-alakú-e a gyökér: `<X>.app/Contents/Resources/manifold` (tiszta függvény, a `--selftest` táblázata ellenőrzi).
    static func termekGyoker(_ url: URL) -> Bool {
        let c = url.standardizedFileURL.pathComponents
        guard c.count >= 4 else { return false }
        let n = c.count
        return c[n - 1] == "manifold" && c[n - 2] == "Resources" && c[n - 3] == "Contents" && c[n - 4].hasSuffix(".app")
    }

    /// A jelöltek a felfedezés sorrendjében (tiszta függvény): a `MOS_ROOT`, a csomag `Contents/Resources/manifold`-ja, az app
    /// szülőmappája.
    static func jeloltek(environment: [String: String], bundle: URL) -> [URL] {
        var candidates: [URL] = []
        if let env = environment["MOS_ROOT"], !env.isEmpty { candidates.append(URL(fileURLWithPath: env)) }
        candidates.append(bundle.appendingPathComponent("Contents/Resources/manifold", isDirectory: true))
        candidates.append(bundle.deletingLastPathComponent())
        return candidates
    }

    /// Az első érvényes jelölt és az elrendezése (`termek`: a gyökér csomag-alakú).
    static func locate(environment: [String: String], bundle: URL) -> (root: URL, termek: Bool)? {
        for jelolt in jeloltek(environment: environment, bundle: bundle) {
            let root = jelolt.resolvingSymlinksInPath()
            if isValid(root) { return (root, termekGyoker(root)) }
        }
        return nil
    }

#if MOS_DEVELOPER
    /// A `--selftest` táblázata → a hibás esetek leírása (üres: rendben).
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        let alakok: [(String, Bool)] = [
            ("/Applications/Manifold.app/Contents/Resources/manifold", true),
            ("/Applications/Manifold.app/Contents/Resources/manifold/", true),
            ("/Users/x/Downloads/Manifold 2.app/Contents/Resources/manifold", true),
            ("/Volumes/Work/Manifold-OS", false), ("/Volumes/Work/Manifold.app", false),
            ("/X.app/Contents/Resources/Manifold", false), ("/X/Contents/Resources/manifold", false),
            ("/X.app/Contents/Resources/manifold/sub", false), ("/manifold", false), ("/", false),
        ]
        for (ut, vart) in alakok where termekGyoker(URL(fileURLWithPath: ut)) != vart {
            hibak.append("termék-gyökér \(ut): \(!vart) (várt: \(vart))")
        }
        let b = URL(fileURLWithPath: "/A/Manifold.app")
        let j = jeloltek(environment: ["MOS_ROOT": "/R"], bundle: b).map(\.path)
        if j != ["/R", "/A/Manifold.app/Contents/Resources/manifold", "/A"] { hibak.append("gyökér-jelöltek: \(j)") }
        let j2 = jeloltek(environment: ["MOS_ROOT": ""], bundle: b).map(\.path)
        if j2 != ["/A/Manifold.app/Contents/Resources/manifold", "/A"] { hibak.append("gyökér-jelöltek MOS_ROOT nélkül: \(j2)") }
        return hibak
    }
#endif
}
