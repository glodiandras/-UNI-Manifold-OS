import AppKit
import UserNotifications

/// Rendszerértesítés a macOS Értesítési központjába (E10, CLAUDE.md 80(f)). A felület (a `lib/ertesites/rendszer.ts` szabálya
/// szerint, csak ha az app nincs előtérben) a `{tipus: "ertesites", cim, szoveg, azon, kategoria}` üzenetet küldi; a héj
/// az engedélyt az ELSŐ értesítés előtt kéri (nem indításkor), az elutasítást tiszteli (nincs újrakérés, nincs kerülő út), és
/// a kattintásra az appot előre hozza, a felületnek pedig `window.manifold.ertesitesKattintas(azon)`-nal visszaadja az azonosítót.
///
/// A felület nem megbízható oldal (a Biztonsag-szemlélet): a szöveg hossza és tartalma korlátozott (vezérlőjel nélkül), az
/// azonosító szűk ábécéjű (a JS-be ágyazáskor ez adja a biztonságot), az ismeretlen kategória `jelzes`. A főkeret
/// origin-ellenőrzése az `AppController.userContentController`-ben van, ide csak az ellenőrzött üzenet jut.
struct RendszerErtesites: Equatable {
    let cim: String
    let szoveg: String
    let azon: String
    let kategoria: String
}

enum ErtesitesLogika {
    static let maxCim = 120
    static let maxSzoveg = 240
    static let maxAzon = 32
    static let kategoriak: Set<String> = ["hiba", "kesz", "jelzes"]

    /// A felület üzenetének törzse → érvényes értesítés, vagy nil (üres cím, hibás azonosító). A szöveg tisztított és levágott.
    static func fogad(_ body: [String: Any]) -> RendszerErtesites? {
        guard let cim = tisztit(body["cim"] as? String, max: maxCim), !cim.isEmpty,
              let azon = body["azon"] as? String, ervenyesAzon(azon) else { return nil }
        let szoveg = tisztit(body["szoveg"] as? String, max: maxSzoveg) ?? ""
        let kategoria = (body["kategoria"] as? String).flatMap { kategoriak.contains($0) ? $0 : nil } ?? "jelzes"
        return RendszerErtesites(cim: cim, szoveg: szoveg, azon: azon, kategoria: kategoria)
    }

    /// Vezérlőjelek és sortörések szóközzé, a végek levágva, a hossz korlátozva (a vágás „…”-t kap).
    static func tisztit(_ nyers: String?, max: Int) -> String? {
        guard let nyers else { return nil }
        let egysoros = String(String.UnicodeScalarView(nyers.unicodeScalars.map { CharacterSet.controlCharacters.contains($0) ? " " : $0 }))
        let szokoz = egysoros.split(whereSeparator: { $0 == " " }).joined(separator: " ")
        return szokoz.count > max ? String(szokoz.prefix(max - 1)) + "…" : szokoz
    }

    /// Az azonosító: betű, számjegy, `.`, `_`, `-`, 1–32 karakter (ASCII).
    static func ervenyesAzon(_ azon: String) -> Bool {
        guard (1...maxAzon).contains(azon.count) else { return false }
        return azon.unicodeScalars.allSatisfy { $0.isASCII && (CharacterSet.alphanumerics.contains($0) || $0 == "." || $0 == "_" || $0 == "-") }
    }

    /// A `window.manifold.ertesitesKattintas("<azon>")` hívás szövege; az azonosító alakját előbb ellenőrzi.
    static func kattintasJs(_ azon: String) -> String? {
        ervenyesAzon(azon) ? "window.manifold?.ertesitesKattintas?.(\"\(azon)\")" : nil
    }

    /// Küldhető-e az értesítés az engedély állapota szerint: az elutasított (`denied`) soha; a még nem döntött kérdezés után.
    static func kuldhet(_ allapot: UNAuthorizationStatus) -> Bool {
        switch allapot {
        case .denied: return false
        default: return true
        }
    }

    /// A `--selftest` táblázata: → a hibás esetek leírása (üres: rendben).
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        func egyez<T: Equatable>(_ nev: String, _ kapott: T, _ vart: T) {
            if kapott != vart { hibak.append("értesítés: \(nev): \(kapott) (várt: \(vart))") }
        }
        let jo: [String: Any] = ["cim": "Kész: kártyák", "szoveg": "12 új kártya", "azon": "e7", "kategoria": "kesz"]
        egyez("jó üzenet", fogad(jo), RendszerErtesites(cim: "Kész: kártyák", szoveg: "12 új kártya", azon: "e7", kategoria: "kesz"))
        egyez("szöveg nélkül", fogad(["cim": "a", "azon": "e1"])?.szoveg, "")
        egyez("üres cím", fogad(["cim": "  ", "azon": "e1"]), nil)
        egyez("nincs azonosító", fogad(["cim": "a"]), nil)
        egyez("azonosító idézőjellel", fogad(["cim": "a", "azon": "a\"); x(\""]), nil)
        egyez("hosszú azonosító", fogad(["cim": "a", "azon": String(repeating: "a", count: 33)]), nil)
        egyez("ékezetes azonosító", fogad(["cim": "a", "azon": "é1"]), nil)
        egyez("ismeretlen kategória", fogad(["cim": "a", "azon": "e1", "kategoria": "x"])?.kategoria, "jelzes")
        egyez("sortörés a címben", fogad(["cim": "a\nb\tc", "azon": "e1"])?.cim, "a b c")
        egyez("hosszú cím levágva", fogad(["cim": String(repeating: "é", count: 300), "azon": "e1"])?.cim.count, maxCim)
        egyez("hosszú szöveg levágva", fogad(["cim": "a", "szoveg": String(repeating: "x", count: 900), "azon": "e1"])?.szoveg.count, maxSzoveg)
        egyez("nem szöveg a címben", fogad(["cim": 3, "azon": "e1"]), nil)
        egyez("kattintás-JS", kattintasJs("e7"), "window.manifold?.ertesitesKattintas?.(\"e7\")")
        egyez("kattintás-JS hibás azonosítóval", kattintasJs("a\"b"), nil)
        egyez("elutasított engedély", kuldhet(.denied), false)
        egyez("még nem döntött", kuldhet(.notDetermined), true)
        egyez("engedélyezett", kuldhet(.authorized), true)
        return hibak
    }
}

/// A rendszerértesítések küldője és a kattintás-kezelő. Csak app-csomagból futtatva él (a `UNUserNotificationCenter` csomag nélkül
/// kivételt dob), és a `--selftest` alatt nem indul (a próba nem küldhet a felhasználó Értesítési központjába).
final class ErtesitesKozpont: NSObject, UNUserNotificationCenterDelegate {
    /// A kattintás: az azonosító (az app előrehozását a hívó végzi).
    var onKattintas: ((String) -> Void)?
    private let kozpont: UNUserNotificationCenter?

    override init() {
        // csomag nélkül (pl. a fordítás utáni közvetlen futtatás) a rendszer-központ nem érhető el
        let van = Bundle.main.bundleURL.pathExtension == "app" && Bundle.main.bundleIdentifier != nil
        kozpont = van ? UNUserNotificationCenter.current() : nil
        super.init()
        kozpont?.delegate = self
    }

    /// Egy értesítés küldése: az engedély állapota szerint (az első küldés előtt kér), a hiba némán marad (az app nem függ tőle).
    func kuld(_ e: RendszerErtesites) {
        guard let kozpont else { return }
        kozpont.getNotificationSettings { beallitas in
            switch beallitas.authorizationStatus {
            case .denied:
                return
            case .notDetermined:
                kozpont.requestAuthorization(options: [.alert, .sound]) { megadva, _ in
                    if megadva { self.kikuld(e) }
                }
            default:
                self.kikuld(e)
            }
        }
    }

    private func kikuld(_ e: RendszerErtesites) {
        let tartalom = UNMutableNotificationContent()
        tartalom.title = e.cim
        tartalom.body = e.szoveg
        tartalom.threadIdentifier = "manifold-\(e.kategoria)"
        if e.kategoria == "hiba" { tartalom.sound = .default }
        // azonos azonosító: a még nyitott értesítés helyben frissül (a kulcsos belső értesítés megfelelője)
        kozpont?.add(UNNotificationRequest(identifier: e.azon, content: tartalom, trigger: nil), withCompletionHandler: nil)
    }

    /// Előtérben az app nem mutat rendszerbuborékot (a belső értesítés a dolga); a felület amúgy sem küld ilyenkor.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let azon = response.notification.request.identifier
        DispatchQueue.main.async { [weak self] in
            if response.actionIdentifier == UNNotificationDefaultActionIdentifier { self?.onKattintas?(azon) }
            completionHandler()
        }
    }
}
