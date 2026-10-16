import Foundation
import NaturalLanguage
import WebKit

/// Csak nyelvi jel a helyesírás-ellenőrzéshez: a szöveg nem kerül fájlba, naplóba vagy hálózatra.
/// Minden kérés saját felismerőt használ; az Apple modelljét nem kötjük a felület vagy a workspace nyelvéhez.
enum NyelvFelismero {
    static let maxKarakter = 8000
    static let minBetu = 40
    static let minBizalom = 0.80
    static let minKulonbseg = 0.20

    struct Eredmeny {
        let nyelv: String?
        let bizalom: Double
        var kevert = false

        var json: [String: Any] {
            ["nyelv": nyelv as Any? ?? NSNull(), "bizalom": bizalom, "kevert": kevert]
        }
    }

    static var ismeretlen: Eredmeny { Eredmeny(nyelv: nil, bizalom: 0) }

    /// A UTF-16-korlát a nagyon hosszú kombinálókarakter-sorozatokat is levágja (egy graphema is lehetne óriási).
    static func keresSzoveg(_ body: Any) -> String? {
        guard let d = body as? [String: Any], let szoveg = d["szoveg"] as? String else { return nil }
        return String(decoding: szoveg.utf16.prefix(maxKarakter), as: UTF16.self)
    }

    /// Csak a core főkerete: az iframe, másik port, HTTPS vagy egy korábbi core-origin nem kap nyelvi szolgáltatást.
    static func engedelyezett(foKeret: Bool, sema: String, gazda: String, port: Int, origin: String?) -> Bool {
        guard foKeret, sema == "http", gazda == "127.0.0.1", let origin else { return false }
        return "http://127.0.0.1:\(port)" == origin
    }

    /// A küszöb és a második jelölt távolsága is kell: bizonytalan szövegnél az OS automatikus ellenőrzése dönt.
    static func valaszt(_ jeloltek: [String: Double]) -> Eredmeny {
        let sor = jeloltek.filter { !$0.key.isEmpty && $0.key != "und" && $0.value.isFinite && (0...1).contains($0.value) }
            .sorted { $0.value > $1.value }
        guard let elso = sor.first, elso.value >= minBizalom,
              elso.value - (sor.dropFirst().first?.value ?? 0) >= minKulonbseg else { return ismeretlen }
        return Eredmeny(nyelv: elso.key, bizalom: elso.value)
    }

    private static func betuk(_ s: String) -> Int {
        s.unicodeScalars.reduce(0) { $0 + (CharacterSet.letters.contains($1) ? 1 : 0) }
    }

    /// A kliens is prózát küld, de a natív határ önállóan sem tekinti a kódot angol jegyzetnek.
    private static func proza(_ nyers: String) -> String {
        var kerites: Character?
        var keritesHossz = 0
        var frontmatter = false
        var matek = false
        var sorok: [String] = []
        let egysoros = nyers.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
        for (i, sor) in egysoros.components(separatedBy: "\n").enumerated() {
            let s = sor.trimmingCharacters(in: .whitespaces)
            if i == 0 && s == "---" { frontmatter = true; continue }
            if frontmatter {
                if s == "---" || s == "..." { frontmatter = false }
                continue
            }
            if let elso = s.first, elso == "`" || elso == "~" {
                let n = s.prefix(while: { $0 == elso }).count
                if n >= 3 {
                    if kerites == nil { kerites = elso; keritesHossz = n }
                    else if kerites == elso && n >= keritesHossz { kerites = nil }
                    continue
                }
            }
            if kerites != nil { continue }
            if s.hasPrefix("$$") { if s == "$$" { matek.toggle() }; continue }
            if matek { continue }
            // Programkód, JSON, HTML, shell és képlet-sorok. A rendes Markdown-címsorok/listák megmaradnak.
            if s.range(of: #"^(?:#(?:include|define|pragma)\b|(?:import|from|using|return|def|class|struct|func|function|let|var|const|int|float|double|void|bool|public|private|echo|printf|export)\b|(?:if|for|while|switch)\s*\(|[\w.]+\s*\(|[\w.]+\s*=|[{}]|[\"'][^\"']*[\"']\s*:|</?[A-Za-z])"#, options: .regularExpression) != nil
                || s.hasSuffix(";") || s.hasSuffix("{") || s.hasSuffix("}") { continue }
            sorok.append(sor)
        }
        return sorok.joined(separator: "\n")
            .replacingOccurrences(of: #"`+[^`]*`+|\$[^$\n]+\$|https?://\S+|!?\[\[[^\]]*\]\]"#, with: " ", options: .regularExpression)
    }

    static func felismer(_ szoveg: String) -> Eredmeny {
        let korlatozott = String(decoding: szoveg.utf16.prefix(maxKarakter), as: UTF16.self)
        let szoveg = proza(korlatozott)
        guard betuk(szoveg) >= minBetu else { return ismeretlen }
        let szavazo = NLTokenizer(unit: .word)
        szavazo.string = szoveg
        var szavak = Set<String>()
        szavazo.enumerateTokens(in: szoveg.startIndex..<szoveg.endIndex) { tartomany, _ in
            let szo = String(szoveg[tartomany])
            if betuk(szo) > 0 { szavak.insert(szo.lowercased()) }
            return szavak.count < 4
        }
        guard szavak.count >= 4 else { return ismeretlen }
        let felismero = NLLanguageRecognizer()
        func jel(_ s: String) -> Eredmeny {
            felismero.reset()
            felismero.processString(s)
            return valaszt(Dictionary(uniqueKeysWithValues: felismero.languageHypotheses(withMaximum: 2).map { ($0.key.rawValue, $0.value) }))
        }
        // A többnyelvű jegyzetet ne rögzítsük a hosszabb bekezdés nyelvére: az OS bekezdésenként ismer fel.
        let bekezdesek = szoveg.replacingOccurrences(of: #"\n\s*\n"#, with: "\u{001E}", options: .regularExpression)
            .components(separatedBy: "\u{001E}").filter { betuk($0) >= 24 }.prefix(6)
        var nyelvek = Set<String>()
        for bekezdes in bekezdesek {
            if let nyelv = jel(bekezdes).nyelv { nyelvek.insert(nyelv) }
            if nyelvek.count > 1 { return Eredmeny(nyelv: nil, bizalom: 0, kevert: true) }
        }
        return jel(szoveg)
    }
}

/// A WebKit erősen tartja a kezelőt, a gyenge owner-closure viszont nem tartja életben az AppControllert.
@MainActor
final class NyelvUzenetKezelo: NSObject, WKScriptMessageHandlerWithReply {
    private let origin: () -> String?
    private let sor = DispatchQueue(label: "com.manifold.nyelv-felismeres", qos: .userInitiated)

    init(origin: @escaping () -> String?) { self.origin = origin }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        let eredet = message.frameInfo.securityOrigin
        guard NyelvFelismero.engedelyezett(foKeret: message.frameInfo.isMainFrame, sema: eredet.protocol,
                                          gazda: eredet.host, port: eredet.port, origin: origin()),
              let szoveg = NyelvFelismero.keresSzoveg(message.body) else {
            replyHandler(NyelvFelismero.ismeretlen.json, nil)
            return
        }
        sor.async {
            let eredmeny = NyelvFelismero.felismer(szoveg)
            DispatchQueue.main.async { replyHandler(eredmeny.json, nil) }
        }
    }
}
