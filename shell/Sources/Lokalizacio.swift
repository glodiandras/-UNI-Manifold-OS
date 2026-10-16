import Foundation

/// A héj szövegei (F4, PLAN P2: a felület nyelve angol). A KULCS a mai magyar szöveg, mint a felületen (`t()`): az angol az
/// `Resources/en.lproj/Localizable.strings`-ben áll (`"<magyar>" = "<English>";`), a build az `.lproj` mappákat a csomagba másolja.
/// Hiányzó kulcs: a magyar szöveg, vagyis a kulcs — a lefedettségi teszt minden hívás fordítását ellenőrzi.
///
///     L("Kilépés")                          → "Quit"
///     L("%d jegyzet nem mentődött", n)      → `String(format:)` a lefordított formátummal (`%@`, `%d`; sorrendváltáshoz `%1$@`)
///
/// A kiadott felület kizárólag angol (a macOS és a workspace tartalmi nyelvétől függetlenül). Csak a fejlesztői buildben:
/// a selftest (`--selftest`) és a `MOS_UI_NYELV=hu` a magyar identitást adja a régi viselkedési táblákhoz. Az angol csomagot
/// a külön lokalizációs teszt valódi Bundle-feloldással ellenőrzi.
enum Lokalizacio {
    /// A `hu` identitás csak fejlesztői teszteszköz; nem szállított felületi nyelv.
#if MOS_DEVELOPER
    static let tamogatott = ["en", "hu"]
#else
    static let tamogatott = ["en"]
#endif

    /// Az aktív nyelv. Ismeretlen kód nem állítható be.
    nonisolated(unsafe) static var nyelv: String = indulo() {
        didSet {
            if !tamogatott.contains(nyelv) { nyelv = oldValue; return }
            csomag = csomagBetolt(nyelv)
        }
    }

    /// Az aktív nyelv `.lproj` csomagja; `nil`: identitás (`hu`, vagy hiányzó `.lproj`).
    nonisolated(unsafe) private(set) static var csomag: Bundle? = csomagBetolt(indulo())

    private static func indulo() -> String {
#if MOS_DEVELOPER
        if CommandLine.arguments.contains(where: { $0 == "--selftest" || $0.hasPrefix("--selftest=") }) { return "hu" }
        if let kert = ProcessInfo.processInfo.environment["MOS_UI_NYELV"], tamogatott.contains(kert) { return kert }
#endif
        return "en"
    }

    private static func csomagBetolt(_ nyelv: String) -> Bundle? {
        guard nyelv != "hu", let ut = Bundle.main.path(forResource: nyelv, ofType: "lproj") else { return nil }
        return Bundle(path: ut)
    }

    /// A kulcs fordítása az aktív nyelven (hiányzó fordítás: a kulcs).
    static func fordit(_ kulcs: String) -> String {
        guard let csomag else { return kulcs }
        return NSLocalizedString(kulcs, tableName: nil, bundle: csomag, value: kulcs, comment: "")
    }
}

/// Egy felirat az aktív nyelven; a kulcs a magyar szöveg. Lásd `Lokalizacio`.
func L(_ kulcs: String) -> String {
    Lokalizacio.fordit(kulcs)
}

/// Paraméteres felirat: a lefordított szöveg `String(format:)` formátum (`%@`, `%d`, `%1$@`).
func L(_ kulcs: String, _ args: CVarArg...) -> String {
    String(format: Lokalizacio.fordit(kulcs), arguments: args)
}
