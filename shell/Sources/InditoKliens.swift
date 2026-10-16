import Foundation
import CoreFoundation

/// Az indító a core előtt is működik. Kizárólag a stdout NDJSON-protokollját olvassa; a stderr nem felületi adat.
/// A csöveket egy háttérsor üríti, a visszahívások a főszálon futnak. Nincs shell-interpoláció.
final class InditoKliens {
    enum Hiba: Error { case protokoll, megszakitva, inditas }
    enum Esemeny { case haladas([String: Any]), eredmeny([String: Any]) }
    static let sorKorlat = 1_048_576
    private let folyamat = Process()
    private let bemenet = Pipe()
    private let kimenet = Pipe()
    private let hibak = Pipe()
    private let zar = NSLock()
    private var puffer = Data()
    private var vegso: [String: Any]?
    private var lezart = false
    private var megszakitva = false
    private var protokollHiba = false
    private var fogad: ((Esemeny) -> Void)?
    private var kesz: ((Result<[String: Any], Hiba>) -> Void)?
    let iras: Bool

    init(root: URL, keres: [String: Any], environment: [String: String] = ProcessInfo.processInfo.environment) {
        iras = ["letrehoz", "demo", "megnyit", "elfelejt"].contains(keres["muvelet"] as? String ?? "")
        folyamat.executableURL = root.appendingPathComponent("bin/mos")
        folyamat.arguments = ["indito"]
        folyamat.currentDirectoryURL = root
        var env = environment
        env["MOS_ROOT"] = root.path
        env["MOS_ELRENDEZES"] = "termek"
        // A választott mappát a JSON-kérés adja, nem egy korábbi core rögzített útvonalai.
        for kulcs in ["MOS_VAULT", "MOS_WORKSPACE", "MOS_WORKSPACE_ID", "MOS_VAR", "MOS_CORE_PORT", "MOS_API_TITOK"] {
            env.removeValue(forKey: kulcs)
        }
        folyamat.environment = env
        folyamat.standardInput = bemenet
        folyamat.standardOutput = kimenet
        folyamat.standardError = hibak
        self.keres = keres
    }
    private let keres: [String: Any]

    /// Tiszta, szigorú sorhatár: egyetlen JSON-objektum, kizárólag progress vagy záró eredmény.
    static func ertelmez(_ adat: Data) -> Esemeny? {
        guard adat.count <= sorKorlat,
              let obj = try? JSONSerialization.jsonObject(with: adat) as? [String: Any] else { return nil }
        if let h = obj["haladas"] as? [String: Any], obj["ok"] == nil { return .haladas(h) }
        guard let ok = obj["ok"] as? NSNumber, CFGetTypeID(ok) == CFBooleanGetTypeID() else { return nil }
        return .eredmeny(obj)
    }

    func indit(haladas: @escaping (Esemeny) -> Void, kesz: @escaping (Result<[String: Any], Hiba>) -> Void) {
        self.fogad = haladas
        self.kesz = kesz
        hibak.fileHandleForReading.readabilityHandler = { h in if h.availableData.isEmpty { h.readabilityHandler = nil } }
        do {
            let adat = try JSONSerialization.data(withJSONObject: keres)
            guard adat.count <= Self.sorKorlat else { throw Hiba.protokoll }
            try folyamat.run()
            // A teljes cső- és folyamatvárás háttérszálon fut; az EOF biztosan az összes eredménysor után jön.
            DispatchQueue.global(qos: .userInitiated).async { [self] in
                do { try bemenet.fileHandleForWriting.write(contentsOf: adat + Data([10])); try bemenet.fileHandleForWriting.close() }
                catch { protokollHiba = true; if folyamat.isRunning { folyamat.terminate() } }
                while true {
                    let resz = kimenet.fileHandleForReading.availableData
                    if resz.isEmpty { break }
                    olvas(resz)
                }
                folyamat.waitUntilExit()
                befejez()
            }
        } catch {
            kimenet.fileHandleForReading.readabilityHandler = nil
            hibak.fileHandleForReading.readabilityHandler = nil
            lezart = true
            kesz(.failure(.inditas))
        }
    }

    private func olvas(_ adat: Data) {
        guard !lezart else { return }
        puffer.append(adat)
        while let nl = puffer.firstIndex(of: 10) {
            let line = Data(puffer[..<nl]); puffer.removeSubrange(...nl)
            guard !line.isEmpty else { continue }
            guard vegso == nil, let e = Self.ertelmez(line) else { protokollHiba = true; continue }
            switch e {
            case .eredmeny(let obj): vegso = obj
            case .haladas: DispatchQueue.main.async { [weak self] in self?.fogad?(e) }
            }
        }
        if puffer.count > Self.sorKorlat { protokollHiba = true; puffer.removeAll(); if folyamat.isRunning { folyamat.terminate() } }
    }

    private func befejez() {
        guard !lezart else { return }
        // A záró JSON-sor végén a newline opcionális; minden egyéb protokollhiba végleges.
        if !puffer.isEmpty { olvas(Data([10])) }
        zar.lock(); lezart = true; let megszakitva = self.megszakitva; zar.unlock()
        hibak.fileHandleForReading.readabilityHandler = nil
        let eredmeny: Result<[String: Any], Hiba>
        if megszakitva { eredmeny = .failure(.megszakitva) }
        else if protokollHiba || vegso == nil || (vegso?["ok"] as? Bool == true && folyamat.terminationStatus != 0) { eredmeny = .failure(.protokoll) }
        else { eredmeny = .success(vegso!) }
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.kesz?(eredmeny); self.kesz = nil; self.fogad = nil
        }
    }

    /// Írás közben nem küldünk SIGTERM-et: a workspace tranzakciója végigfut, utána lehet visszatérni.
    @discardableResult func megszakit() -> Bool {
        guard !iras else { return false }
        zar.lock()
        if lezart { zar.unlock(); return true }
        megszakitva = true
        zar.unlock()
        if folyamat.isRunning { folyamat.terminate() }
        return true
    }
}
