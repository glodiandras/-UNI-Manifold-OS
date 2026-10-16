import CoreGraphics
import EventKit
import Foundation

// A naptár- és emlékeztető-segéd (C29, docs/C29-TERV.md 2. fejezet): `Manifold --naptar <parancs>`.
//
// A core ezt hívja gyermekfolyamatként: a kérés JSON-objektum a stdinen (üres = `{}`), a válasz egyetlen
// JSON-objektum a stdouton, a kilépési kód 0 (a hibát az `ok: false` és a `hiba` mező jelzi). Nincs
// NSApplication, nincs ablak, nincs hálózat, nincs fájlírás. Az EventKit-független részek (kérés-elemzés,
// dátum- és állapotleképezés, jóváhagyási őr) a `NaptarLogika`-ban élnek, hogy a `--selftest` táblázata
// ellenőrizhesse őket.

// MARK: tiszta logika

enum NaptarLogika {
    /// Az EKAuthorizationStatus nyers értéke → a protokoll állapotneve (macOS 14-en
    /// a 3 a `fullAccess`, a 4 a `writeOnly`).
    static func allapotNev(_ nyers: Int) -> String {
        switch nyers {
        case 0: return "nincs_dontes"
        case 1: return "korlatozott"
        case 2: return "megtagadva"
        case 3: return "engedelyezve"
        case 4: return "csak_iras"
        default: return "ismeretlen"
        }
    }

    static func forrasTipus(_ nyers: Int) -> String {
        switch nyers {
        case 0: return "helyi"
        case 1: return "exchange"
        case 2: return "caldav"
        case 3: return "mobileme"
        case 4: return "feliratkozas"
        case 5: return "szuletesnap"
        default: return "egyeb"
        }
    }

    static func naptarTipus(_ nyers: Int) -> String {
        switch nyers {
        case 0: return "helyi"
        case 1: return "caldav"
        case 2: return "exchange"
        case 3: return "feliratkozas"
        case 4: return "szuletesnap"
        default: return "egyeb"
        }
    }

    /// A hibaválasz alakja: `{ok: false, hiba: …}` (+ `nincs: true`, ha a keresett elem hiányzik).
    static func hiba(_ szoveg: String, nincs: Bool = false) -> [String: Any] {
        var d: [String: Any] = ["ok": false, "hiba": szoveg]
        if nincs { d["nincs"] = true }
        return d
    }

    /// A kérés elemzése: üres (vagy csak szóköz) stdin = `{}`; a kérésnek JSON-objektumnak kell lennie.
    static func kerest(_ adat: Data?) -> Result<[String: Any], NaptarHiba> {
        guard let adat, !adat.isEmpty,
              !(String(data: adat, encoding: .utf8) ?? "x").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return .success([:])
        }
        guard let objektum = try? JSONSerialization.jsonObject(with: adat, options: []) else {
            return .failure(NaptarHiba("a kérés nem érvényes JSON"))
        }
        guard let szotar = objektum as? [String: Any] else {
            return .failure(NaptarHiba("a kérésnek JSON-objektumnak kell lennie"))
        }
        return .success(szotar)
    }

    /// A parancssor elemzése (a `--naptar` utáni rész): a parancs neve, vagy `nil`.
    static func parancs(_ argumentumok: [String]) -> String? {
        guard let elso = argumentumok.first, !elso.isEmpty, !elso.hasPrefix("-") else { return nil }
        return elso
    }

    static func logikai(_ ertek: Any?) -> Bool? {
        guard let n = ertek as? NSNumber, CFGetTypeID(n) == CFBooleanGetTypeID() else { return nil }
        return n.boolValue
    }

    static func szam(_ ertek: Any?) -> Double? {
        guard let n = ertek as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() else { return nil }
        return n.doubleValue
    }

    /// A `jovahagyva.javaslat` őr: csak ha a kérésben ott a javaslat azonosítója (nem üres szöveg vagy szám).
    static func jovahagyott(_ kerdes: [String: Any]) -> Bool {
        guard let j = kerdes["jovahagyva"] as? [String: Any], let javaslat = j["javaslat"] else { return false }
        if let s = javaslat as? String { return !s.trimmingCharacters(in: .whitespaces).isEmpty }
        return szam(javaslat) != nil
    }

    private static func gregorian() -> Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone.current
        return c
    }

    /// `ÉÉÉÉ-HH-NN` → (év, hó, nap), valós dátumra; különben `nil`.
    static func napReszek(_ szoveg: String) -> (Int, Int, Int)? {
        let r = szoveg.split(separator: "-", omittingEmptySubsequences: false)
        guard r.count == 3, r[0].count == 4, r[1].count == 2, r[2].count == 2,
              let y = Int(r[0]), let m = Int(r[1]), let d = Int(r[2]) else { return nil }
        var c = DateComponents(); c.calendar = gregorian(); c.year = y; c.month = m; c.day = d
        return c.isValidDate ? (y, m, d) : nil
    }

    /// `HH:MM` (az óra egy számjeggyel is) → (óra, perc), különben `nil`.
    static func oraReszek(_ szoveg: String) -> (Int, Int)? {
        let r = szoveg.split(separator: ":", omittingEmptySubsequences: false)
        guard r.count == 2, (1...2).contains(r[0].count), r[1].count == 2,
              let h = Int(r[0]), let m = Int(r[1]), (0...23).contains(h), (0...59).contains(m) else { return nil }
        return (h, m)
    }

    /// `hatarido` (`ÉÉÉÉ-HH-NN`) + opcionális `ora` (`HH:MM`) → a határidő időkomponensei (gregorián naptár, helyi
    /// időzóna); érvénytelen dátumra vagy órára `nil`. Óra nélkül csak a nap szerepel.
    static func hataridoKomponensek(hatarido: String, ora: String?) -> DateComponents? {
        guard let (y, m, d) = napReszek(hatarido) else { return nil }
        var c = DateComponents()
        c.calendar = gregorian(); c.timeZone = TimeZone.current
        c.year = y; c.month = m; c.day = d
        if let ora {
            guard let (h, p) = oraReszek(ora) else { return nil }
            c.hour = h; c.minute = p
        }
        return c
    }

    /// A komponensekből a határidő napja (`ÉÉÉÉ-HH-NN`), vagy `nil`, ha nincs teljes dátum.
    static func hataridoSzoveg(_ c: DateComponents) -> String? {
        guard let y = c.year, let m = c.month, let d = c.day else { return nil }
        return String(format: "%04d-%02d-%02d", y, m, d)
    }

    /// A komponensekből a határidő időrésze (`HH:MM`), vagy `nil`, ha a határidő csak napot ad.
    static func oraSzoveg(_ c: DateComponents) -> String? {
        guard let h = c.hour else { return nil }
        return String(format: "%02d:%02d", h, c.minute ?? 0)
    }

    private static let isoKi: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        f.timeZone = TimeZone.current
        return f
    }()

    static func isoSzoveg(_ d: Date) -> String { isoKi.string(from: d) }

    static func napSzoveg(_ d: Date) -> String {
        let c = gregorian().dateComponents([.year, .month, .day], from: d)
        return hataridoSzoveg(c) ?? ""
    }

    /// ISO 8601 idő (zónával, tört másodperccel is), zóna nélküli helyi idő (`ÉÉÉÉ-HH-NNTÓÓ:PP[:MM]`), vagy
    /// csak nap (`ÉÉÉÉ-HH-NN`: a helyi nap kezdete) → `Date`; különben `nil`.
    static func isoDatum(_ szoveg: String) -> Date? {
        guard !szoveg.contains(where: { $0.isWhitespace }) else { return nil }   // a rendszer-elemző a farok szemetet elnézi
        if let d = isoKi.date(from: szoveg) { return d }
        let tort = ISO8601DateFormatter()
        tort.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = tort.date(from: szoveg) { return d }
        let r = szoveg.split(separator: "T", omittingEmptySubsequences: false)
        guard let (y, m, nap) = napReszek(String(r[0])) else { return nil }
        var c = DateComponents(); c.calendar = gregorian(); c.timeZone = TimeZone.current
        c.year = y; c.month = m; c.day = nap
        if r.count == 2 {
            let ido = r[1].split(separator: ":")
            guard ido.count == 2 || ido.count == 3, let h = Int(ido[0]), let p = Int(ido[1]),
                  (0...23).contains(h), (0...59).contains(p) else { return nil }
            let mp = ido.count == 3 ? Int(ido[2]) : 0
            guard let mp, (0...59).contains(mp) else { return nil }
            c.hour = h; c.minute = p; c.second = mp
        } else if r.count != 1 {
            return nil
        }
        return c.date
    }

    static func szinHex(_ c: CGColor?) -> String? {
        guard let c, let srgb = CGColorSpace(name: CGColorSpace.sRGB),
              let k = c.converted(to: srgb, intent: .defaultIntent, options: nil), let p = k.components, p.count >= 3 else { return nil }
        let r = Int((max(0, min(1, p[0])) * 255).rounded()), g = Int((max(0, min(1, p[1])) * 255).rounded()),
            b = Int((max(0, min(1, p[2])) * 255).rounded())
        return String(format: "#%02x%02x%02x", r, g, b)
    }

#if MOS_DEVELOPER
    /// A `--selftest` táblázata: → a hibás esetek leírása (üres: rendben). EventKit-et nem érint.
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        func varj<T: Equatable>(_ nev: String, _ kapott: T, _ vart: T) {
            if kapott != vart { hibak.append("naptár/\(nev): \(kapott) (várt: \(vart))") }
        }
        // állapotnevek
        for (n, v) in [(0, "nincs_dontes"), (1, "korlatozott"), (2, "megtagadva"), (3, "engedelyezve"), (4, "csak_iras"),
                       (5, "ismeretlen"), (-1, "ismeretlen")] {
            varj("állapot \(n)", allapotNev(n), v)
        }
        varj("forrás 2", forrasTipus(2), "caldav"); varj("forrás 9", forrasTipus(9), "egyeb")
        varj("naptár 4", naptarTipus(4), "szuletesnap"); varj("naptár 7", naptarTipus(7), "egyeb")
        // kérés-elemzés
        for (nev, adat) in [("nil", nil), ("üres", Data()), ("szóköz", Data(" \n ".utf8)), ("üres objektum", Data("{}".utf8))] as [(String, Data?)] {
            if case .success(let d) = kerest(adat), d.isEmpty { continue }
            hibak.append("naptár/kérés \(nev): nem üres sikeres kérés kellene")
        }
        if case .success(let d) = kerest(Data(#"{"a": 1, "b": [true]}"#.utf8)) { varj("kérés kulcsok", d.count, 2) }
        else { hibak.append("naptár/kérés: érvényes objektum elutasítva") }
        for (nev, szoveg) in [("hibás JSON", "{"), ("tömb", "[1]"), ("szám", "7"), ("szöveg", "\"x\"")] {
            if case .success = kerest(Data(szoveg.utf8)) { hibak.append("naptár/kérés \(nev): elfogadva") }
        }
        // parancssor
        varj("parancs olvas", parancs(["olvas"]) ?? "-", "olvas")
        varj("parancs üres", parancs([]) ?? "-", "-")
        varj("parancs kapcsoló", parancs(["--x"]) ?? "-", "-")
        varj("parancs üres szöveg", parancs([""]) ?? "-", "-")
        // hibaválasz alakja
        let h = hiba("x")
        varj("hiba ok", h["ok"] as? Bool ?? true, false); varj("hiba szöveg", h["hiba"] as? String ?? "", "x")
        varj("hiba nincs nélkül", h["nincs"] == nil, true)
        varj("hiba nincs", hiba("x", nincs: true)["nincs"] as? Bool ?? false, true)
        // jóváhagyási őr
        let jovahagyasok: [(String, [String: Any], Bool)] = [
            ("nincs", [:], false), ("üres obj", ["jovahagyva": [String: Any]()], false),
            ("null", ["jovahagyva": ["javaslat": NSNull()]], false), ("üres szöveg", ["jovahagyva": ["javaslat": " "]], false),
            ("logikai", ["jovahagyva": ["javaslat": true]], false), ("nem objektum", ["jovahagyva": "igen"], false),
            ("szöveg", ["jovahagyva": ["javaslat": "j-12"]], true), ("szám", ["jovahagyva": ["javaslat": 12]], true),
        ]
        for (nev, k, vart) in jovahagyasok { varj("jóváhagyás \(nev)", jovahagyott(k), vart) }
        // dátumleképezés
        if let c = hataridoKomponensek(hatarido: "2026-10-03", ora: "14:05") {
            varj("komp év", c.year ?? 0, 2026); varj("komp hó", c.month ?? 0, 10); varj("komp nap", c.day ?? 0, 3)
            varj("komp óra", c.hour ?? -1, 14); varj("komp perc", c.minute ?? -1, 5)
            varj("komp vissza nap", hataridoSzoveg(c) ?? "-", "2026-10-03"); varj("komp vissza óra", oraSzoveg(c) ?? "-", "14:05")
            varj("komp időzóna", c.timeZone == TimeZone.current, true)
        } else { hibak.append("naptár/komponensek: érvényes dátum elutasítva") }
        if let c = hataridoKomponensek(hatarido: "2028-02-29", ora: nil) {
            varj("komp óra nélkül", c.hour == nil, true); varj("komp óra nélkül ora", oraSzoveg(c) ?? "null", "null")
            varj("komp szökőnap", hataridoSzoveg(c) ?? "-", "2028-02-29")
        } else { hibak.append("naptár/komponensek: szökőnap elutasítva") }
        if let c = hataridoKomponensek(hatarido: "2026-01-02", ora: "9:30") { varj("komp egy számjegyű óra", oraSzoveg(c) ?? "-", "09:30") }
        else { hibak.append("naptár/komponensek: 9:30 elutasítva") }
        for (nap, ora) in [("2026-02-30", nil), ("2026-13-01", nil), ("2026-1-1", nil), ("26-10-03", nil), ("", nil), ("2026-10-03", "24:00"),
                           ("2026-10-03", "12:60"), ("2026-10-03", "12"), ("2026-10-03", "ab:cd")] as [(String, String?)] {
            if hataridoKomponensek(hatarido: nap, ora: ora) != nil { hibak.append("naptár/komponensek: \(nap) \(ora ?? "-") elfogadva") }
        }
        varj("részleges komp", hataridoSzoveg(DateComponents(year: 2026, month: 5)) ?? "null", "null")
        varj("részleges óra", oraSzoveg(DateComponents(hour: 7)) ?? "-", "07:00")
        // ISO-idő: oda-vissza és a változatok
        let most = Date(timeIntervalSince1970: 1_790_000_000)
        varj("iso oda-vissza", isoDatum(isoSzoveg(most)).map { Int($0.timeIntervalSince1970) } ?? 0, 1_790_000_000)
        varj("iso zóna", isoDatum("2026-10-03T12:00:00+02:00").map { Int($0.timeIntervalSince1970) } ?? 0,
             Int(ISO8601DateFormatter().date(from: "2026-10-03T10:00:00Z")!.timeIntervalSince1970))
        varj("iso tört másodperc", isoDatum("2026-10-03T12:00:00.500Z") != nil, true)
        varj("iso helyi", isoDatum("2026-10-03T12:00") != nil, true)
        varj("iso nap", isoDatum("2026-10-03").map { napSzoveg($0) } ?? "-", "2026-10-03")
        for rossz in ["", "x", "2026-10-03T25:00", "2026-10-03T12", "2026-13-03", "2026-10-03T12:00:00Z extra"] {
            if isoDatum(rossz) != nil { hibak.append("naptár/iso: \(rossz.debugDescription) elfogadva") }
        }
        return hibak
    }
#endif
}

struct NaptarHiba: Error {
    let uzenet: String
    init(_ uzenet: String) { self.uzenet = uzenet }
}

// MARK: EventKit-segéd (CLI)

/// Szálbiztos doboz az EventKit háttérszálon érkező visszahívásainak.
private final class Doboz<T>: @unchecked Sendable {
    private let zar = NSLock()
    private var _ertek: T?
    private var _kesz = false
    var kesz: Bool { zar.lock(); defer { zar.unlock() }; return _kesz }
    var ertek: T? { zar.lock(); defer { zar.unlock() }; return _ertek }
    func beallit(_ e: T?) { zar.lock(); _ertek = e; _kesz = true; zar.unlock() }
}

enum Naptar {
    static let alapLista = "Manifold"

    // MARK: engedély

    /// Egy entitás (esemény vagy emlékeztető) engedély-állapotának nyers értéke.
    static func allapotNyers(_ tipus: EKEntityType) -> Int { EKEventStore.authorizationStatus(for: tipus).rawValue }

    static func allapotNevEntitas(_ tipus: EKEntityType) -> String { NaptarLogika.allapotNev(allapotNyers(tipus)) }

    /// Az engedély kérése (a rendszer párbeszédablakot mutat). A `vege` tetszőleges szálon hívódik; a hibaszöveg
    /// `nil`, ha a kérés lefutott (az eredmény az állapotból olvasható). macOS 14-től a teljes hozzáférést kéri,
    /// 13-on a régi `requestAccess(to:)` útra esik vissza.
    static func engedelyKeres(_ store: EKEventStore, _ tipus: EKEntityType, vege: @escaping @Sendable (String?) -> Void) {
        if #available(macOS 14.0, *) {
            let visszahivas: @Sendable (Bool, Error?) -> Void = { _, hiba in vege(hiba?.localizedDescription) }
            if tipus == .event { store.requestFullAccessToEvents(completion: visszahivas) }
            else { store.requestFullAccessToReminders(completion: visszahivas) }
        } else {
            store.requestAccess(to: tipus) { _, hiba in vege(hiba?.localizedDescription) }
        }
    }

    // MARK: belépési pont

    /// A `--naptar <parancs>` futtatása: a stdinről olvas, a stdoutra ír, a kilépési kód mindig 0.
    static func futtat(_ argumentumok: [String]) -> Int32 {
        let valasz: [String: Any]
        if let parancs = NaptarLogika.parancs(argumentumok) {
            let adat = isatty(0) != 0 ? Data() : FileHandle.standardInput.readDataToEndOfFile()
            switch NaptarLogika.kerest(adat) {
            case .success(let kerdes): valasz = vegrehajt(parancs, kerdes)
            case .failure(let h): valasz = NaptarLogika.hiba(h.uzenet)
            }
        } else {
            valasz = NaptarLogika.hiba("hiányzó parancs (allapot, kerd, olvas, emlekeztetok, emlekezteto-ir, esemeny-ir)")
        }
        kiir(valasz)
        return 0
    }

    static func vegrehajt(_ parancs: String, _ kerdes: [String: Any]) -> [String: Any] {
        switch parancs {
        case "allapot": return allapot()
        case "kerd": return kerd(kerdes)
        case "olvas": return olvas(kerdes)
        case "emlekeztetok": return emlekeztetok(kerdes)
        case "emlekezteto-ir": return emlekeztetoIr(kerdes)
        case "esemeny-ir": return esemenyIr(kerdes)
        default: return NaptarLogika.hiba("ismeretlen parancs: \(parancs)")
        }
    }

    private static func kiir(_ adat: [String: Any]) {
        let json = (try? JSONSerialization.data(withJSONObject: adat, options: [.sortedKeys, .withoutEscapingSlashes]))
            ?? Data(#"{"ok":false,"hiba":"a válasz nem szerializálható"}"#.utf8)
        FileHandle.standardOutput.write(json)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }

    private static func varakozas(_ doboz: Doboz<some Any>, legfeljebb mp: TimeInterval) {
        let hatar = Date().addingTimeInterval(mp)
        while !doboz.kesz && Date() < hatar { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
    }

    // MARK: allapot, kerd

    static func allapot() -> [String: Any] {
        ["ok": true, "esemeny": allapotNevEntitas(.event), "emlekezteto": allapotNevEntitas(.reminder)]
    }

    /// A kérés csak a `nincs_dontes` állapotú entitásra megy, a megadott időkorláttal (alap: 150 mp).
    static func kerd(_ kerdes: [String: Any]) -> [String: Any] {
        let mp = max(1, min(600, NaptarLogika.szam(kerdes["varakozas"]) ?? 150))
        let hatar = Date().addingTimeInterval(mp)
        let kero = EKEventStore()
        for (kulcs, tipus) in [("esemeny", EKEntityType.event), ("emlekezteto", EKEntityType.reminder)] {
            guard NaptarLogika.logikai(kerdes[kulcs]) == true, allapotNyers(tipus) == 0 else { continue }
            let doboz = Doboz<String>()
            engedelyKeres(kero, tipus) { hiba in doboz.beallit(hiba) }
            varakozas(doboz, legfeljebb: max(0.5, hatar.timeIntervalSinceNow))
        }
        return allapot()
    }

    // MARK: olvas

    static func olvas(_ kerdes: [String: Any]) -> [String: Any] {
        let most = Date()
        let tol = (kerdes["tol"] as? String).flatMap { NaptarLogika.isoDatum($0) } ?? most.addingTimeInterval(-90 * 86400)
        let ig = (kerdes["ig"] as? String).flatMap { NaptarLogika.isoDatum($0) } ?? most.addingTimeInterval(180 * 86400)
        let nyers = allapotNyers(.event)
        var valasz: [String: Any] = ["ok": true, "verzio": 2, "allapot": NaptarLogika.allapotNev(nyers),
                                     "most": NaptarLogika.isoSzoveg(most), "tol": NaptarLogika.isoSzoveg(tol),
                                     "ig": NaptarLogika.isoSzoveg(ig), "idozona": TimeZone.current.identifier,
                                     "naptarak": [Any](), "esemenyek": [Any]()]
        guard nyers == 3 else { return valasz }
        let store = EKEventStore()                  // az engedély után friss tár
        valasz["naptarak"] = store.calendars(for: .event).map(naptarJson)
        // az EventKit legfeljebb ~4 éves ablakot kérdez egyszerre; a hívó ennél jóval kisebbet kér
        let pred = store.predicateForEvents(withStart: tol, end: ig, calendars: nil)
        valasz["esemenyek"] = store.events(matching: pred).map { esemenyJson($0, tartalek: most) }
        return valasz
    }

    private static func naptarJson(_ c: EKCalendar) -> [String: Any] {
        var d: [String: Any] = ["azon": c.calendarIdentifier, "nev": c.title, "tipus": NaptarLogika.naptarTipus(c.type.rawValue),
                                "forras": c.source?.title ?? "",
                                "forras_tipus": c.source.map { NaptarLogika.forrasTipus($0.sourceType.rawValue) } ?? "",
                                "forras_azon": c.source?.sourceIdentifier ?? "", "irhato": c.allowsContentModifications,
                                "feliratkozas": c.isSubscribed]
        if let h = NaptarLogika.szinHex(c.cgColor) { d["szin"] = h }
        return d
    }

    /// Az esemény kulcsa: `külső azonosító|előfordulás ISO`
    private static func esemenyKulcs(_ e: EKEvent, elofordulas: Date) -> String {
        let kulso = e.calendarItemExternalIdentifier
        let alap = (kulso?.isEmpty == false ? kulso! : e.calendarItemIdentifier)
        return alap + "|" + NaptarLogika.isoSzoveg(elofordulas)
    }

    private static func esemenyJson(_ e: EKEvent, tartalek: Date) -> [String: Any] {
        let elofordulas = e.occurrenceDate ?? e.startDate ?? tartalek
        var d: [String: Any] = [
            "azon": esemenyKulcs(e, elofordulas: elofordulas),
            "naptar": e.calendar?.calendarIdentifier ?? "",
            "cim": e.title ?? "",
            "kezd": NaptarLogika.isoSzoveg(e.startDate ?? elofordulas),
            "veg": NaptarLogika.isoSzoveg(e.endDate ?? e.startDate ?? elofordulas),
            "nap": NaptarLogika.napSzoveg(e.startDate ?? elofordulas),
            "egesznap": e.isAllDay,
            "ismetlodo": e.hasRecurrenceRules,
            "leszakitott": e.isDetached,
            "allapot": e.status.rawValue,
        ]
        if let h = e.location, !h.isEmpty { d["hely"] = h }
        if let n = e.notes, !n.isEmpty { d["jegyzet"] = String(n.prefix(1500)) }
        if let m = e.lastModifiedDate { d["modositva"] = NaptarLogika.isoSzoveg(m) }
        if let u = e.url { d["url"] = u.absoluteString }
        return d
    }

    // MARK: esemeny-ir

    static func esemenyIr(_ kerdes: [String: Any]) -> [String: Any] {
        guard NaptarLogika.jovahagyott(kerdes) else {
            return NaptarLogika.hiba("naptáresemény csak jóváhagyott javaslatra íródik (jovahagyva.javaslat hiányzik)")
        }
        guard allapotNyers(.event) == 3 else { return NaptarLogika.hiba("nincs naptár-engedély") }
        guard let naptarAzon = kerdes["naptar"] as? String, !naptarAzon.isEmpty else { return NaptarLogika.hiba("hiányzó naptár") }
        guard let cim = (kerdes["cim"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !cim.isEmpty else {
            return NaptarLogika.hiba("hiányzó cím")
        }
        guard let kezd = (kerdes["kezd"] as? String).flatMap({ NaptarLogika.isoDatum($0) }) else { return NaptarLogika.hiba("hiányzó vagy érvénytelen kezdés") }
        guard let veg = (kerdes["veg"] as? String).flatMap({ NaptarLogika.isoDatum($0) }) else { return NaptarLogika.hiba("hiányzó vagy érvénytelen vég") }
        guard veg >= kezd else { return NaptarLogika.hiba("a vég a kezdés előtt van") }
        let store = EKEventStore()
        guard let naptar = store.calendar(withIdentifier: naptarAzon) else { return NaptarLogika.hiba("nincs ilyen naptár", nincs: true) }
        guard naptar.allowsContentModifications else { return NaptarLogika.hiba("a naptár nem írható") }
        let esemeny = EKEvent(eventStore: store)
        esemeny.calendar = naptar
        esemeny.title = cim
        esemeny.startDate = kezd
        esemeny.endDate = veg
        if let j = kerdes["jegyzet"] as? String, !j.isEmpty { esemeny.notes = j }
        do { try store.save(esemeny, span: .thisEvent, commit: true) }
        catch { return NaptarLogika.hiba("az esemény mentése nem sikerült: \(error.localizedDescription)") }
        var valasz: [String: Any] = ["ok": true, "azon": esemenyKulcs(esemeny, elofordulas: kezd), "naptar": naptar.calendarIdentifier,
                                     "belso_azon": esemeny.calendarItemIdentifier]
        if let k = esemeny.calendarItemExternalIdentifier, !k.isEmpty { valasz["kulso"] = k }
        return valasz
    }

    // MARK: emlékeztetők

    private static func emlekeztetoJson(_ r: EKReminder) -> [String: Any] {
        let c = r.dueDateComponents
        return ["azon": r.calendarItemIdentifier,
                "kulso": r.calendarItemExternalIdentifier ?? "",
                "cim": r.title ?? "",
                "hatarido": c.flatMap { NaptarLogika.hataridoSzoveg($0) } as Any? ?? NSNull(),
                "ora": c.flatMap { NaptarLogika.oraSzoveg($0) } as Any? ?? NSNull(),
                "kesz": r.isCompleted,
                "kesz_ido": r.completionDate.map { NaptarLogika.isoSzoveg($0) } as Any? ?? NSNull(),
                "modositva": r.lastModifiedDate.map { NaptarLogika.isoSzoveg($0) } as Any? ?? NSNull(),
                "jegyzet": r.notes ?? ""]
    }

    private static func listaJson(_ l: EKCalendar, uj: Bool? = nil) -> [String: Any] {
        var d: [String: Any] = ["azon": l.calendarIdentifier, "nev": l.title, "forras": l.source?.title ?? ""]
        if let uj { d["uj"] = uj }
        return d
    }

    /// A megnevezett emlékeztető-lista (a `forras` szerint szűkítve, ha több azonos nevű van), vagy `nil`.
    private static func keresLista(_ store: EKEventStore, nev: String, forras: String?) -> EKCalendar? {
        let talalatok = store.calendars(for: .reminder).filter { $0.title == nev }
        if let forras, !forras.isEmpty, let pontos = talalatok.first(where: { $0.source?.title == forras }) { return pontos }
        return talalatok.first
    }

    private static func lekerEmlekeztetok(_ store: EKEventStore, lista: EKCalendar) -> [EKReminder]? {
        let doboz = Doboz<[EKReminder]>()
        _ = store.fetchReminders(matching: store.predicateForReminders(in: [lista])) { doboz.beallit($0 ?? []) }
        varakozas(doboz, legfeljebb: 30)
        return doboz.kesz ? doboz.ertek : nil
    }

    static func emlekeztetok(_ kerdes: [String: Any]) -> [String: Any] {
        let nyers = allapotNyers(.reminder)
        var valasz: [String: Any] = ["ok": true, "allapot": NaptarLogika.allapotNev(nyers), "lista": NSNull(), "emlekeztetok": [Any]()]
        guard nyers == 3 else { return valasz }
        let nev = (kerdes["lista"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? alapLista
        let store = EKEventStore()
        guard let lista = keresLista(store, nev: nev, forras: kerdes["forras"] as? String) else { return valasz }
        guard let elemek = lekerEmlekeztetok(store, lista: lista) else {
            return NaptarLogika.hiba("az emlékeztetők lekérése időtúllépés miatt megszakadt")
        }
        valasz["lista"] = listaJson(lista)
        valasz["emlekeztetok"] = elemek.map(emlekeztetoJson)
        return valasz
    }

    /// Az EKSource a lista létrehozásához: név szerint; üres → a rendszer alapértelmezett emlékeztető-listájának
    /// forrása; ennek hiányában az első forrás, amelyben emlékeztető-lista van (nincs név szerinti előny), majd a helyi, a CalDAV.
    private static func keresForras(_ store: EKEventStore, nev: String?) -> EKSource? {
        if let nev, !nev.isEmpty {
            let talalatok = store.sources.filter { $0.title == nev }
            return talalatok.first(where: { !$0.calendars(for: .reminder).isEmpty }) ?? talalatok.first
        }
        if let alap = store.defaultCalendarForNewReminders()?.source { return alap }
        return store.sources.first(where: { !$0.calendars(for: .reminder).isEmpty })
            ?? store.sources.first(where: { $0.sourceType.rawValue == 0 })
            ?? store.sources.first(where: { $0.sourceType.rawValue == 2 })
    }

    /// Egy `uj`/`modosit` művelet határidő-komponensei: a művelet `ora`, a kérés `ora`, végül a meglévő óra.
    private static func hataridoBeallit(_ r: EKReminder, hatarido: String?, ora: String?) throws {
        guard let hatarido else { return }
        guard let c = NaptarLogika.hataridoKomponensek(hatarido: hatarido, ora: ora) else {
            throw NaptarHiba("érvénytelen határidő vagy óra (\(hatarido) \(ora ?? "-"))")
        }
        r.dueDateComponents = c
    }

    /// Abszolút riasztás a határidő pillanatára; óra nélküli határidőnél 09:00-ra. A meglévő abszolút riasztások cserélődnek.
    private static func riasztasBeallit(_ r: EKReminder) {
        for a in r.alarms ?? [] where a.absoluteDate != nil { r.removeAlarm(a) }
        guard let c = r.dueDateComponents else { return }
        var kompok = c
        if kompok.hour == nil { kompok.hour = 9; kompok.minute = 0 }
        if kompok.calendar == nil { kompok.calendar = Calendar(identifier: .gregorian) }
        if kompok.timeZone == nil { kompok.timeZone = TimeZone.current }
        if let datum = kompok.date { r.addAlarm(EKAlarm(absoluteDate: datum)) }
    }

    static func emlekeztetoIr(_ kerdes: [String: Any]) -> [String: Any] {
        guard allapotNyers(.reminder) == 3 else { return NaptarLogika.hiba("nincs emlékeztető-engedély") }
        guard let muveletek = kerdes["muveletek"] as? [[String: Any]] else { return NaptarLogika.hiba("hiányzó vagy hibás műveletlista") }
        let nev = (kerdes["lista"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? alapLista
        let forrasNev = kerdes["forras"] as? String
        let alapOra = kerdes["ora"] as? String
        let alapRiasztas = NaptarLogika.logikai(kerdes["riasztas"]) ?? false
        let store = EKEventStore()
        var ujLista = false
        var lista: EKCalendar
        if let l = keresLista(store, nev: nev, forras: forrasNev) {
            lista = l
        } else {
            guard let forras = keresForras(store, nev: forrasNev) else {
                return NaptarLogika.hiba("nincs emlékeztető-forrás a lista létrehozásához" + (forrasNev.map { " (\($0))" } ?? ""))
            }
            let uj = EKCalendar(for: .reminder, eventStore: store)
            uj.title = nev
            uj.source = forras
            do { try store.saveCalendar(uj, commit: true) }   // a lista előbb létezzen, mint az elemei
            catch { return NaptarLogika.hiba("a lista létrehozása nem sikerült: \(error.localizedDescription)") }
            lista = uj
            ujLista = true
        }

        var eredmenyek: [[String: Any]] = []
        var ujak: [(index: Int, reminder: EKReminder)] = []
        var valtozott = false
        for m in muveletek {
            let kulcs: Any = m["kulcs"] ?? NSNull()
            var e: [String: Any] = ["kulcs": kulcs, "ok": false]
            let op = m["op"] as? String ?? ""
            let ora = (m["ora"] as? String) ?? alapOra
            let riasztas = NaptarLogika.logikai(m["riasztas"]) ?? alapRiasztas
            do {
                switch op {
                case "uj":
                    guard let cim = (m["cim"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !cim.isEmpty,
                          let hatarido = m["hatarido"] as? String else { throw NaptarHiba("az új emlékeztetőhöz cím és határidő kell") }
                    let r = EKReminder(eventStore: store)
                    r.calendar = lista
                    r.title = cim
                    try hataridoBeallit(r, hatarido: hatarido, ora: ora)
                    if let j = m["jegyzet"] as? String, !j.isEmpty { r.notes = j }
                    if riasztas { riasztasBeallit(r) }
                    try store.save(r, commit: false)
                    valtozott = true
                    e["ok"] = true
                    ujak.append((eredmenyek.count, r))
                case "modosit", "kesz", "nyit", "torol":
                    guard let azon = m["azon"] as? String, !azon.isEmpty,
                          let r = store.calendarItem(withIdentifier: azon) as? EKReminder else {
                        e["nincs"] = true; throw NaptarHiba("nincs ilyen emlékeztető")
                    }
                    guard r.calendar?.calendarIdentifier == lista.calendarIdentifier else {
                        throw NaptarHiba("az emlékeztető nem a(z) „\(nev)” listában van")
                    }
                    switch op {
                    case "modosit":
                        if let cim = m["cim"] as? String {
                            guard !cim.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw NaptarHiba("üres cím") }
                            r.title = cim
                        }
                        if m["jegyzet"] != nil { r.notes = (m["jegyzet"] as? String).flatMap { $0.isEmpty ? nil : $0 } }
                        if let hatarido = m["hatarido"] as? String {
                            let marad = r.dueDateComponents.flatMap { NaptarLogika.oraSzoveg($0) }
                            try hataridoBeallit(r, hatarido: hatarido, ora: ora ?? marad)
                            // a riasztás a határidővel igazodik: a meglévő cserélődik, vagy kérésre új készül
                            if riasztas || (r.alarms ?? []).contains(where: { $0.absoluteDate != nil }) { riasztasBeallit(r) }
                        }
                        try store.save(r, commit: false)
                    case "kesz":
                        r.isCompleted = true
                        r.completionDate = Date()
                        try store.save(r, commit: false)
                    case "nyit":
                        r.isCompleted = false
                        try store.save(r, commit: false)
                    default:                                  // torol
                        try store.remove(r, commit: false)
                    }
                    valtozott = true
                    e["ok"] = true
                    e["azon"] = azon
                default:
                    throw NaptarHiba("ismeretlen művelet: \(op.isEmpty ? "(üres)" : op)")
                }
            } catch let h as NaptarHiba {
                e["ok"] = false; e["hiba"] = h.uzenet
            } catch {
                e["ok"] = false; e["hiba"] = error.localizedDescription
            }
            eredmenyek.append(e)
        }
        if valtozott {
            do { try store.commit() }
            catch { return NaptarLogika.hiba("a változások mentése (commit) nem sikerült: \(error.localizedDescription)") }
            for (i, r) in ujak {                              // az azonosítók a commit után véglegesek
                eredmenyek[i]["azon"] = r.calendarItemIdentifier
                eredmenyek[i]["kulso"] = r.calendarItemExternalIdentifier ?? ""
            }
        }
        return ["ok": true, "lista": listaJson(lista, uj: ujLista), "eredmeny": eredmenyek]
    }
}

// MARK: engedélykérés a GUI-folyamatban

/// A felület kérésére (`naptar-engedely`, `naptar-allapot`) a GUI-folyamat kéri az EventKit-engedélyt, hogy a
/// rendszer a Manifold.app-nak tulajdonítsa. A fő szálat nem blokkolja: az eredmény a visszahívásban érkezik, és
/// a fő szálon adódik át. Az egyetlen hely, ahol a héj engedélyt kér (a CLI-s `kerd` tartalék).
@MainActor
final class NaptarEngedely {
    private let store = EKEventStore()
    private var folyamatban = false

    /// A két állapotnév: `{esemeny: S, emlekezteto: S}`.
    func allapot() -> [String: Any] {
        ["esemeny": Naptar.allapotNevEntitas(.event), "emlekezteto": Naptar.allapotNevEntitas(.reminder)]
    }

    /// Kéri a megadott entitások engedélyét (csak a `nincs_dontes` állapotúakét, sorban), majd `vege`-vel jelenti
    /// az eredményt. Hiba: `{hiba: "…"}`. Párhuzamos hívás az éppen futó kérés alatt nem indít újat.
    func kerd(esemeny: Bool, emlekezteto: Bool, vege: @escaping @MainActor ([String: Any]) -> Void) {
        guard !folyamatban else { return vege(allapot()) }
        var sor: [EKEntityType] = []
        if esemeny, Naptar.allapotNyers(.event) == 0 { sor.append(.event) }
        if emlekezteto, Naptar.allapotNyers(.reminder) == 0 { sor.append(.reminder) }
        folyamatban = true
        kovetkezo(sor, hiba: nil, vege: vege)
    }

    private func kovetkezo(_ sor: [EKEntityType], hiba: String?, vege: @escaping @MainActor ([String: Any]) -> Void) {
        guard let elso = sor.first else {
            folyamatban = false
            var eredmeny = allapot()
            if let hiba { eredmeny["hiba"] = hiba }
            return vege(eredmeny)
        }
        let maradek = Array(sor.dropFirst())
        Naptar.engedelyKeres(store, elso) { [weak self] h in
            DispatchQueue.main.async {
                MainActor.assumeIsolated { self?.kovetkezo(maradek, hiba: hiba ?? h, vege: vege) }
            }
        }
    }
}
