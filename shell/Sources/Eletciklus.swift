import Foundation

/// A héj életciklus-döntései tiszta függvényekben (C29.7b, 2. audit T031–T033, T121–T123), hogy a `--selftest` táblázata
/// ellenőrizhesse őket — a viselkedést az `AppController` köti rá az ablakokra és a folyamatokra. Logika a héjban csak ennyi:
/// mit jelent a felület mentési jelentése, mikor kell kérdezni, mit mutat az üzenet, mikor hagyjuk abba az újratöltést.

/// A kilépés előtti mentés jelentése (`window.manifold.mentes()` → `{ok, mentetlen: [{ut, allapot, hiba}]}`).
/// A `nincsValasz` a T033 hibaútja: a híd hiányzik, a hívás hibázott vagy nem jött jelentés — ez NEM „rendben”
/// (a korábbi `?? true` ilyenkor mentés nélkül állította le a core-t).
enum KilepesJelentes: Equatable {
    case rendben
    case mentetlen([Mentetlen])
    case nincsValasz(String)

    struct Mentetlen: Equatable {
        let ut: String
        let hiba: String?
    }
}

/// A felhasználónak szóló kérdés kilépéskor (két gomb: „Vissza a szerkesztéshez” / „Kilépés mentés nélkül”).
struct KilepesKerdes: Equatable {
    let cim: String
    let szoveg: String
}

enum WebContentLepes: Equatable {
    case ujratolt
    case feladja
}

/// A főkeret meghiúsult betöltésének kezelése (`didFailProvisionalNavigation`).
enum NavigaciosHibaLepes: Equatable {
    /// nem hiba: egy újabb betöltés megszakította, vagy a navigációs szabály (`decidePolicyFor`) tiltotta
    case figyelmenKivul
    /// „Újratöltés / Kilépés” ajánlat (nem azonnali kilépés)
    case ujratoltes
}

enum Eletciklus {
    /// A kézfogás alapértelmezett várakozása (másodperc): a core az indulási helyreállítás és az index indítása után ír portot.
    static let kezfogasAlap: TimeInterval = 25

    /// Egy `mentetlen()` elem a felületről (a core halálakor: kérdéshez és a vágólapos mentéshez).
    struct MentetlenSzoveg: Equatable {
        let ut: String
        let hiba: String?
        let szoveg: String
    }

    // MARK: a mentési jelentés

    /// A `callAsyncJavaScript` eredményéből jelentés. `hiba`: a hívás hibája (a JS kivételt dobott, a WebContent meghalt, …).
    static func ertelmez(_ jelentes: Any?, hiba: String?) -> KilepesJelentes {
        if let hiba { return .nincsValasz(hiba) }
        guard let obj = jelentes as? [String: Any] else {
            return .nincsValasz(L("a felület nem adott jelentést (a `window.manifold.mentes` hiányzik, vagy üres választ adott)"))
        }
        guard let ok = obj["ok"] as? Bool else { return .nincsValasz(L("a felület jelentése érvénytelen")) }
        if ok { return .rendben }
        let lista = (obj["mentetlen"] as? [[String: Any]] ?? []).map {
            KilepesJelentes.Mentetlen(ut: $0["ut"] as? String ?? "?", hiba: $0["hiba"] as? String)
        }
        return .mentetlen(lista)
    }

    /// Kell-e kérdezni kilépés előtt (és mit). `nil`: minden mentve, a core leállhat.
    static func kilepesKerdes(_ j: KilepesJelentes, idotullepes: Bool) -> KilepesKerdes? {
        let figyelmeztet = L("Ha most kilépsz, a mentetlen változások elvesznek. A szerkesztőben a szöveg megvan: onnan kimásolható, vagy a mentés újrapróbálható.")
        if idotullepes {
            var szoveg = ""
            if case .mentetlen(let l) = j { szoveg = mentetlenSorok(l) + "\n\n" }
            return KilepesKerdes(cim: L("A mentés nem fejeződött be időben"), szoveg: szoveg + figyelmeztet)
        }
        switch j {
        case .rendben:
            return nil
        case .mentetlen(let l):
            return KilepesKerdes(cim: L("Nem minden jegyzet mentődött"), szoveg: (l.isEmpty ? "" : mentetlenSorok(l) + "\n\n") + figyelmeztet)
        case .nincsValasz(let ok):
            return KilepesKerdes(
                cim: L("A felület nem válaszolt"),
                szoveg: L("A felület nem válaszolt a mentési kérésre (%@), ezért nem tudjuk, van-e mentetlen szöveg. Ha most kilépsz, az elveszhet. Várj egy kicsit, majd próbáld újra.", ok))
        }
    }

    static func mentetlenSorok(_ l: [KilepesJelentes.Mentetlen]) -> String {
        var sorok = l.prefix(8).map { "• \($0.ut)" + ($0.hiba.map { " — \($0)" } ?? "") }
        if l.count > 8 { sorok.append(L("• …és %d további", l.count - 8)) }
        return sorok.joined(separator: "\n")
    }

    // MARK: a core halála és a kézfogás

    /// A stderr utolsó sorai (az üres sorok nélkül), legfeljebb `karakter` karakter — a végét tartjuk meg, mert az összeomlás
    /// oka ott áll (a korábbi „első 2000 karakter” az indulási zajt mutatta).
    static func farok(_ szoveg: String, sorok: Int = 12, karakter: Int = 1500) -> String {
        let s = szoveg.split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        var ki = s.suffix(sorok).joined(separator: "\n")
        if ki.count > karakter { ki = "…" + String(ki.suffix(karakter)) }
        return ki
    }

    /// Az „A core leállt” üzenet törzse: mi történt, a stderr vége, a mentetlen jegyzetek, és mi a teendő.
    static func coreHalalSzoveg(farok: String, mentetlen: [MentetlenSzoveg]) -> String {
        var s = L("A háttérfolyamat (a core) váratlanul leállt. Az Újraindítás ugyanazon a porton indítja újra, így az ablak és a benne lévő szöveg megmarad, a szerkesztő magától újra próbálja a mentést.")
        if !mentetlen.isEmpty {
            s += "\n\n" + L("Mentetlen jegyzet (a szerkesztőben a szöveg megvan):") + "\n"
                + mentetlenSorok(mentetlen.map { KilepesJelentes.Mentetlen(ut: $0.ut, hiba: $0.hiba) })
        }
        s += farok.isEmpty ? "\n\n" + L("A core nem írt hibaüzenetet.") : "\n\n" + L("A core utolsó sorai:") + "\n" + farok
        return s
    }

    /// A vágólapra másolt mentetlen szövegek (jegyzetenként fejléccel).
    static func masolatSzoveg(_ elemek: [MentetlenSzoveg]) -> String {
        elemek.map { "── \($0.ut) ──\n\($0.szoveg)" }.joined(separator: "\n\n")
    }

    /// A `window.manifold.mentetlen()` visszatérési értékének értelmezése (érvénytelen elem kimarad).
    static func mentetlenElemek(_ v: Any?) -> [MentetlenSzoveg] {
        (v as? [[String: Any]] ?? []).compactMap {
            guard let ut = $0["ut"] as? String, let szoveg = $0["szoveg"] as? String else { return nil }
            return MentetlenSzoveg(ut: ut, hiba: $0["hiba"] as? String, szoveg: szoveg)
        }
    }

    /// A kézfogásra várás ideje (`MOS_KEZFOGAS_MP`, 0,1–600 s; alapból 25 s).
    static func kezfogasIdo(_ env: [String: String]) -> TimeInterval {
        if let s = env["MOS_KEZFOGAS_MP"], let v = Double(s), v >= 0.1, v <= 600 { return v }
        return kezfogasAlap
    }

    // MARK: az API-titok injektálása (35. döntés, T071)

    /// A lapba injektált szkript forrása (`window.__MOS_TITOK__`), vagy nil, ha a titok alakja nem fogadható el (a core csak betűt,
    /// számot, `_`, `.`, `-` jelet sorsol, 16–128 karakterben: a forrásba így idézőjel vagy escape nem kerülhet).
    static func titokJs(_ titok: String?) -> String? {
        guard let t = titok, (16...128).contains(t.count),
              t.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_" || $0 == "." || $0 == "-") }) else { return nil }
        return "window.__MOS_TITOK__ = \"\(t)\";"
    }

    // MARK: a WebContent-folyamat halála

    struct WebContentDonto: Equatable {
        let lepes: WebContentLepes
        let halalok: [Date]
    }

    /// A WebContent-folyamat halála (`webViewWebContentProcessDidTerminate`): újratöltés — de ha `ablak` másodpercen belül a
    /// `max`-adik halál jön, nincs végtelen újratöltés (a felület nyilván nem indul el).
    static func webContentHalal(korabbi: [Date], most: Date, ablak: TimeInterval = 60, max: Int = 3) -> WebContentDonto {
        let friss = korabbi.filter { most.timeIntervalSince($0) < ablak } + [most]
        return WebContentDonto(lepes: friss.count >= max ? .feladja : .ujratolt, halalok: friss)
    }

    // MARK: a lap betöltésének hibája

    /// A WebKit tartományának „a betöltést a szabály megszakította” kódja (`WebKitErrorFrameLoadInterruptedByPolicyChange`).
    static let webKitSzabalyMegszakitas = 102

    /// A meghiúsult főkeret-betöltés: a megszakítás (`NSURLErrorCancelled`: egy újabb `load`/`reload` váltotta) és a navigációs
    /// szabály tiltása (WebKit 102: pl. külső link a lapon) nem hiba; minden más (a core nem érhető el, időtúllépés) újratöltés-ajánlat.
    static func navigaciosHiba(tartomany: String, kod: Int) -> NavigaciosHibaLepes {
        if tartomany == NSURLErrorDomain, kod == NSURLErrorCancelled { return .figyelmenKivul }
        if tartomany == "WebKitErrorDomain", kod == webKitSzabalyMegszakitas { return .figyelmenKivul }
        return .ujratoltes
    }

    // MARK: a --selftest táblázata

#if MOS_DEVELOPER
    /// → a hibás esetek leírása (üres: rendben).
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        func egyez<T: Equatable>(_ nev: String, _ mai: T, _ vart: T) {
            if mai != vart { hibak.append("\(nev): \(mai) (várt: \(vart))") }
        }
        // a mentési jelentés — a hiányzó híd NEM „rendben” (T033)
        egyez("jelentés nil", ertelmez(nil, hiba: nil), .nincsValasz("a felület nem adott jelentést (a `window.manifold.mentes` hiányzik, vagy üres választ adott)"))
        egyez("jelentés hiba", ertelmez(nil, hiba: "kivétel"), .nincsValasz("kivétel"))
        egyez("jelentés üres objektum", ertelmez([String: Any](), hiba: nil), .nincsValasz("a felület jelentése érvénytelen"))
        egyez("jelentés szöveges ok", ertelmez(["ok": "igen"], hiba: nil), .nincsValasz("a felület jelentése érvénytelen"))
        egyez("jelentés tömb", ertelmez([1], hiba: nil), .nincsValasz("a felület nem adott jelentést (a `window.manifold.mentes` hiányzik, vagy üres választ adott)"))
        egyez("jelentés rendben", ertelmez(["ok": true, "mentetlen": [Any]()], hiba: nil), .rendben)
        egyez("jelentés mentetlen",
              ertelmez(["ok": false, "mentetlen": [["ut": "A.md", "hiba": "tele a lemez"], ["allapot": "piszkos"]]], hiba: nil),
              .mentetlen([.init(ut: "A.md", hiba: "tele a lemez"), .init(ut: "?", hiba: nil)]))
        // a kérdés
        egyez("kérdés rendben", kilepesKerdes(.rendben, idotullepes: false), nil)
        egyez("kérdés időtúllépés (rendben jelentéssel is)", kilepesKerdes(.rendben, idotullepes: true)?.cim, "A mentés nem fejeződött be időben")
        egyez("kérdés mentetlen", kilepesKerdes(.mentetlen([.init(ut: "A.md", hiba: nil)]), idotullepes: false)?.cim, "Nem minden jegyzet mentődött")
        egyez("kérdés nincs válasz", kilepesKerdes(.nincsValasz("x"), idotullepes: false)?.cim, "A felület nem válaszolt")
        if kilepesKerdes(.nincsValasz("x"), idotullepes: false)?.szoveg.contains("Nem minden jegyzet mentődött") == true {
            hibak.append("a „felület nem válaszolt” kérdés a mentetlen-jegyzetes szöveget használja")
        }
        let sok = (1...10).map { KilepesJelentes.Mentetlen(ut: "J\($0).md", hiba: nil) }
        egyez("mentetlen lista levágva", mentetlenSorok(sok).split(separator: "\n").count, 9)
        egyez("mentetlen lista vége", mentetlenSorok(sok).split(separator: "\n").last.map(String.init), "• …és 2 további")
        // a stderr vége
        let naplo = (1...20).map { "sor \($0)" }.joined(separator: "\n") + "\n\n   \n"
        egyez("farok sorok", farok(naplo, sorok: 3), "sor 18\nsor 19\nsor 20")
        egyez("farok üres", farok("\n \n"), "")
        egyez("farok karakterkorlát", farok(String(repeating: "x", count: 50) + "\nvég", sorok: 5, karakter: 10), "…xxxxxx\nvég")
        // a core halála
        let halal = coreHalalSzoveg(farok: "Traceback…\nboom", mentetlen: [.init(ut: "A.md", hiba: nil, szoveg: "x")])
        for resz in ["váratlanul leállt", "A.md", "A core utolsó sorai:\nTraceback…\nboom", "ugyanazon a porton"] where !halal.contains(resz) {
            hibak.append("a core-halál szövege nem tartalmazza: \(resz)")
        }
        if !coreHalalSzoveg(farok: "", mentetlen: []).contains("nem írt hibaüzenetet") { hibak.append("üres stderr jelzése hiányzik") }
        egyez("másolat", masolatSzoveg([.init(ut: "A.md", hiba: nil, szoveg: "x"), .init(ut: "B.md", hiba: nil, szoveg: "y\nz")]),
              "── A.md ──\nx\n\n── B.md ──\ny\nz")
        egyez("mentetlen elemek", mentetlenElemek([["ut": "A.md", "szoveg": "x", "hiba": "h"], ["ut": "rossz"], ["szoveg": "z"]]),
              [.init(ut: "A.md", hiba: "h", szoveg: "x")])
        egyez("mentetlen elemek nem lista", mentetlenElemek("x"), [])
        // az API-titok injektálása
        egyez("titok szkript", titokJs("abc-DEF_123.xyz-0123"), "window.__MOS_TITOK__ = \"abc-DEF_123.xyz-0123\";")
        egyez("titok rövid", titokJs("rovid"), nil)
        egyez("titok idézőjellel", titokJs("abcdefghijklmnop\"; alert(1); \""), nil)
        egyez("titok ékezettel", titokJs("ékezetes-titok-0123456789"), nil)
        egyez("titok szóközzel", titokJs("van szóköz 0123456789"), nil)
        egyez("titok hiányzik", titokJs(nil), nil)
        egyez("titok túl hosszú", titokJs(String(repeating: "a", count: 129)), nil)
        // a kézfogás ideje
        egyez("kézfogás alap", kezfogasIdo([:]), kezfogasAlap)
        egyez("kézfogás env", kezfogasIdo(["MOS_KEZFOGAS_MP": "1"]), 1)
        egyez("kézfogás env túl kicsi", kezfogasIdo(["MOS_KEZFOGAS_MP": "0"]), kezfogasAlap)
        egyez("kézfogás env szemét", kezfogasIdo(["MOS_KEZFOGAS_MP": "gyors"]), kezfogasAlap)
        // a WebContent halála
        let t0 = Date(timeIntervalSince1970: 1_000_000)
        let d1 = webContentHalal(korabbi: [], most: t0)
        egyez("WebContent első halál", d1.lepes, .ujratolt)
        let d2 = webContentHalal(korabbi: d1.halalok, most: t0.addingTimeInterval(10))
        egyez("WebContent második halál", d2.lepes, .ujratolt)
        egyez("WebContent harmadik halál 60 s-on belül", webContentHalal(korabbi: d2.halalok, most: t0.addingTimeInterval(20)).lepes, .feladja)
        // a lap betöltésének hibája (nem azonnali kilépés; a megszakítás nem hiba)
        egyez("betöltés megszakítva", navigaciosHiba(tartomany: NSURLErrorDomain, kod: NSURLErrorCancelled), .figyelmenKivul)
        egyez("betöltés szabály tiltotta", navigaciosHiba(tartomany: "WebKitErrorDomain", kod: 102), .figyelmenKivul)
        egyez("betöltés: a core nem érhető el", navigaciosHiba(tartomany: NSURLErrorDomain, kod: NSURLErrorCannotConnectToHost), .ujratoltes)
        egyez("betöltés időtúllépés", navigaciosHiba(tartomany: NSURLErrorDomain, kod: NSURLErrorTimedOut), .ujratoltes)
        egyez("betöltés: más tartomány 102-es kódja", navigaciosHiba(tartomany: NSURLErrorDomain, kod: 102), .ujratoltes)
        egyez("WebContent harmadik halál 60 s után", webContentHalal(korabbi: d2.halalok, most: t0.addingTimeInterval(75)).lepes, .ujratolt)
        return hibak
    }
#endif
}
