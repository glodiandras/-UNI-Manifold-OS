import AppKit
import WebKit

/// A jegyzet natív helyi menüje (C32b, a CLAUDE.md 27(d) módosítása). A felület (a Markdown-szerkesztő) jobb klikkre a natív
/// WebKit-menüt hagyja nyitni (Szó keresése, helyesírás-javaslat, Kivágás/Másolás/Beillesztés, Szolgáltatások), és a
/// `contextmenu` esemény közben elküldi a Manifold-parancsok listáját (`{tipus: "helyi-menu", elemek: [{id, nev, letiltva}]}`).
/// A `ManifoldWebView.willOpenMenu` a natív menü VÉGÉRE fűzi őket; a választás a `window.manifold.parancs(id)` hídon fut
/// (ugyanaz a regiszter, mint a ⌘P-ben és a lap saját menüjében: egy parancslista).
///
/// A felület nem megbízható oldal (a Biztonsag-szemlélet): a lista kemény korlátok közt fogadható el (elemszám, az azonosító
/// alakja, a név hossza), a fogadott lista **egyszer használatos és rövid életű** (a menü nyitásáig legfeljebb `elettartam`
/// másodperc), így egy elmaradt jobb klikk listája nem ragad egy későbbi menüre.
struct HelyiMenuElem: Equatable {
    let id: String
    let nev: String
    let letiltva: Bool
}

enum HelyiMenu {
    static let maxElem = 16
    static let maxNev = 60
    static let elettartam: TimeInterval = 2

    /// A héj képességeinek bejelentése a lapnak (a betöltés előtt injektálva): csak ahol ez a héj tényleg fűzi a parancsokat,
    /// kapcsol be a natív menü; a régebbi héj mellett a lap a saját menüjét tartja meg.
    static let kepessegekJs = "window.__MOS_HEJ__ = Object.freeze({ helyiMenu: true });"

    /// A felület üzenetének `elemek` tömbje → az érvényes elemek (a hibás elem kimarad, a lista a korlátnál csonkul).
    static func elemek(_ nyers: Any?) -> [HelyiMenuElem] {
        guard let lista = nyers as? [Any] else { return [] }
        var ki: [HelyiMenuElem] = []
        for x in lista.prefix(maxElem) {
            guard let d = x as? [String: Any], let id = d["id"] as? String, ervenyesId(id),
                  let nev = (d["nev"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !nev.isEmpty, nev.count <= maxNev, !nev.contains("\n") else { continue }
            ki.append(HelyiMenuElem(id: id, nev: nev, letiltva: (d["letiltva"] as? Bool) ?? false))
        }
        return ki
    }

    /// A parancs-azonosító: kisbetű, számjegy, `.`, `_`, `-`, legfeljebb 64 karakter (a regiszter azonosítóinak alakja).
    static func ervenyesId(_ id: String) -> Bool {
        guard (1...64).contains(id.count), let elso = id.unicodeScalars.first,
              CharacterSet.lowercaseLetters.union(.decimalDigits).contains(elso), elso.isASCII else { return false }
        return id.unicodeScalars.allSatisfy { $0.isASCII && (CharacterSet.lowercaseLetters.contains($0) || CharacterSet.decimalDigits.contains($0) || $0 == "." || $0 == "_" || $0 == "-") }
    }

    /// A `window.manifold.parancs(<id>)` hívás szövege; az azonosító alakját előbb ellenőrzi, így a JS-be ágyazás biztonságos.
    static func parancsJs(_ id: String) -> String? {
        ervenyesId(id) ? "window.manifold?.parancs?.(\"\(id)\")" : nil
    }

#if MOS_DEVELOPER
    /// A `--selftest` táblázata: → a hibás esetek leírása (üres: rendben).
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        func egyez<T: Equatable>(_ nev: String, _ kapott: T, _ vart: T) {
            if kapott != vart { hibak.append("helyi menü: \(nev): \(kapott) (várt: \(vart))") }
        }
        let jo: [String: Any] = ["id": "kartya.ebbol", "nev": "Kártyák ebből", "letiltva": false]
        egyez("egy jó elem", elemek([jo]), [HelyiMenuElem(id: "kartya.ebbol", nev: "Kártyák ebből", letiltva: false)])
        egyez("letiltva", elemek([["id": "a", "nev": "A", "letiltva": true]]).first?.letiltva, true)
        egyez("letiltva hiányzik", elemek([["id": "a", "nev": "A"]]).first?.letiltva, false)
        egyez("nem lista", elemek("x"), [])
        egyez("nil", elemek(nil), [])
        egyez("hibás elem kimarad", elemek([jo, "x", ["id": 3], ["nev": "x"], ["id": "A.b", "nev": "n"], ["id": "a b", "nev": "n"]]).count, 1)
        egyez("üres név", elemek([["id": "a", "nev": "  "]]), [])
        egyez("hosszú név", elemek([["id": "a", "nev": String(repeating: "é", count: 61)]]), [])
        egyez("sortörés a névben", elemek([["id": "a", "nev": "a\nb"]]), [])
        egyez("korlát", elemek((0..<40).map { ["id": "p\($0)", "nev": "P\($0)"] as [String: Any] }).count, maxElem)
        egyez("azonosító idézőjellel", ervenyesId("a\"); alert(1); (\""), false)
        egyez("azonosító ékezettel", ervenyesId("kártya.ebbol"), false)
        egyez("azonosító szám-kezdet", ervenyesId("1.a"), true)
        egyez("azonosító pont-kezdet", ervenyesId(".a"), false)
        egyez("azonosító üres", ervenyesId(""), false)
        egyez("azonosító hosszú", ervenyesId(String(repeating: "a", count: 65)), false)
        egyez("parancs JS", parancsJs("kviz.ebbol"), "window.manifold?.parancs?.(\"kviz.ebbol\")")
        egyez("parancs JS hibás", parancsJs("a\")"), nil)
        return hibak
    }
#endif
}

/// A `WKWebView`, amely a natív helyi menü végére fűzi a felület által küldött Manifold-parancsokat.
final class ManifoldWebView: WKWebView {
    private var fuggoElemek: [HelyiMenuElem] = []
    private var fuggoIdeje: Date?
    /// A választott parancs azonosítója (a vezérlő a hídon át futtatja).
    var onParancs: ((String) -> Void)?

    /// A felület listája a következő natív menühöz; egyszer használatos, rövid életű.
    func helyiMenuElemek(_ elemek: [HelyiMenuElem]) {
        fuggoElemek = elemek
        fuggoIdeje = Date()
    }

    override func willOpenMenu(_ menu: NSMenu, with event: NSEvent) {
        super.willOpenMenu(menu, with: event)
        defer { fuggoElemek = []; fuggoIdeje = nil }
        guard let t = fuggoIdeje, Date().timeIntervalSince(t) < HelyiMenu.elettartam, !fuggoElemek.isEmpty else { return }
        if let utolso = menu.items.last, !utolso.isSeparatorItem { menu.addItem(.separator()) }
        for e in fuggoElemek {
            let elem = NSMenuItem(title: e.nev, action: e.letiltva ? nil : #selector(manifoldParancs(_:)), keyEquivalent: "")
            elem.target = self
            elem.representedObject = e.id
            elem.isEnabled = !e.letiltva
            menu.addItem(elem)
        }
    }

    @objc private func manifoldParancs(_ elem: NSMenuItem) {
        if let id = elem.representedObject as? String { onParancs?(id) }
    }
}
