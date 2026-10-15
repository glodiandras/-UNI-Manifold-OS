import Foundation

/// A Python-core gyermekfolyamata. Életciklus (ARCHITECTURE 2.): a core kiírja a portját (egy JSON-sor a
/// stdoutra); a stdin lezárása = leállás a folyamatban lévő feladat végén.
///
/// Egypéldányos zár (C29.6, T027): ha ugyanazon a vaulton már fut egy core, a kézfogás sora
/// `{"foglalt": true, "pid": N, "vault": "…"}`, a core 75-tel kilép — ilyenkor a héj nem indít második ablakot.
final class CoreProcess {
    /// A sikeres kézfogás tartalma: a core portja és API-titka (35. döntés, T071): a héj a titkot a lap betöltése előtt injektálja
    /// a felületbe, és újraindításkor ugyanazt adja vissza a core-nak (`MOS_API_TITOK`), hogy a lap titka érvényes maradjon.
    struct Kezfogas: Equatable {
        let port: Int
        let titok: String?
    }

    enum StartError: Error {
        case failed(String)
        case foglalt(pid: Int?, vault: String?)
    }

    /// A core kilépési kódja, ha másik core fut ugyanazon a vaulton (`CORE_ZAR_KILEPES` a `core/server.py`-ban).
    static let foglaltKilepesiKod: Int32 = 75

    private let process = Process()
    private let stdinPipe = Pipe()
    private let stdoutPipe = Pipe()
    private let stderrPipe = Pipe()
    private let lock = NSLock()
    private var buffer = Data()
    private var errorText = ""
    /// A megtartott stderr-farok mérete (karakter).
    static let stderrMax = 8000
    private var handshake: ((Result<Kezfogas, StartError>) -> Void)?
    private(set) var stopping = false
    /// A core azt jelezte, hogy másik példány fut (kézfogás-sor vagy 75-ös kilépés): a váratlan kilépés nem hiba.
    private var foglaltJel = false
    var foglalt: Bool { lock.lock(); defer { lock.unlock() }; return foglaltJel }
    var onExit: (() -> Void)?

    var isRunning: Bool { process.isRunning }

    /// A core pid-je (nil, ha nem fut).
    var pid: Int32? { process.isRunning ? process.processIdentifier : nil }

    /// A core stderr-jének megtartott vége (az „A core leállt” és a „A core nem válaszol” üzenethez).
    func stderrSzoveg() -> String {
        lock.lock(); defer { lock.unlock() }
        return errorText
    }

    /// `port`: a core ezen a porton induljon (`MOS_CORE_PORT`) — újraindításkor a régi porton, így a lap origin-je és a benne lévő
    /// szöveg megmarad (C29.7b, T031). Nil: szabad port. `titok`: a core ezt az API-titkot használja (`MOS_API_TITOK`) — újraindításkor
    /// a régi, hogy a lapba injektált titok érvényes maradjon; nil: a core újat sorsol.
    init(root: URL, port: Int? = nil, titok: String? = nil) {
        process.executableURL = root.appendingPathComponent("bin/mos")
        process.arguments = ["core", "start"]
        process.currentDirectoryURL = root
        var env = ProcessInfo.processInfo.environment
        env["MOS_ROOT"] = root.path
        if let port { env["MOS_CORE_PORT"] = String(port) }
        if let titok { env["MOS_API_TITOK"] = titok }
        process.environment = env
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
    }

    func start(_ completion: @escaping (Result<Kezfogas, StartError>) -> Void) {
        handshake = completion
        stdoutPipe.fileHandleForReading.readabilityHandler = { [weak self] h in self?.stdout(h.availableData) }
        stderrPipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            // EOF (a core kilépett): a kezelő le, különben a rendszer üres adattal újra és újra hívja (egy háttérszál pörögne
            // az „A core leállt” párbeszéd alatt is) — a stdout kezelője ugyanígy áll le
            if d.isEmpty { h.readabilityHandler = nil; return }
            guard let self else { return }
            // a stderr VÉGÉT tartjuk meg (az összeomlás oka ott áll): az „A core leállt” üzenet és az indulási hiba is ebből mutat
            self.lock.lock()
            self.errorText += String(decoding: d, as: UTF8.self)
            if self.errorText.count > CoreProcess.stderrMax { self.errorText = String(self.errorText.suffix(CoreProcess.stderrMax)) }
            self.lock.unlock()
        }
        process.terminationHandler = { [weak self] p in
            guard let self else { return }
            self.lock.lock()
            if p.terminationStatus == CoreProcess.foglaltKilepesiKod { self.foglaltJel = true }
            let pending = self.handshake; self.handshake = nil; let err = self.errorText; let foglalt = self.foglaltJel
            self.lock.unlock()
            if foglalt { pending?(.failure(.foglalt(pid: nil, vault: nil))) }
            else { pending?(.failure(.failed(err.isEmpty ? "a core kilépett az indulás előtt" : Eletciklus.farok(err)))) }
            DispatchQueue.main.async { self.onExit?() }
        }
        do { try process.run() } catch {
            handshake = nil
            completion(.failure(.failed("a core nem indítható: \(error.localizedDescription)")))
        }
    }

    private func stdout(_ data: Data) {
        if data.isEmpty { stdoutPipe.fileHandleForReading.readabilityHandler = nil; return }
        lock.lock(); defer { lock.unlock() }
        guard handshake != nil else { return }      // az első sor után a kimenetet eldobjuk (a cső ne teljen meg)
        buffer.append(data)
        guard let nl = buffer.firstIndex(of: 0x0A) else { return }
        let line = buffer[..<nl]
        let done = handshake; handshake = nil
        let eredmeny = CoreProcess.kezfogas(Data(line))
        if case .failure(.foglalt) = eredmeny { foglaltJel = true }
        done?(eredmeny)
    }

    /// A kézfogás sorának értelmezése (tiszta függvény, a `--selftest` táblázata ellenőrzi): port (és a `titok`) → siker,
    /// `foglalt: true` → másik példány fut, minden más → hiba.
    static func kezfogas(_ sor: Data) -> Result<Kezfogas, StartError> {
        guard let obj = try? JSONSerialization.jsonObject(with: sor) as? [String: Any] else {
            return .failure(.failed("érvénytelen kézfogás: \(String(decoding: sor, as: UTF8.self))"))
        }
        if obj["foglalt"] as? Bool == true {
            return .failure(.foglalt(pid: obj["pid"] as? Int, vault: obj["vault"] as? String))
        }
        if let port = obj["port"] as? Int { return .success(Kezfogas(port: port, titok: obj["titok"] as? String)) }
        return .failure(.failed("érvénytelen kézfogás: \(String(decoding: sor, as: UTF8.self))"))
    }

    /// A kötet lecsatolásának értesítése (`NSWorkspace.willUnmountNotification`, `NSDevicePath`) a Manifold-OS
    /// gyökerét érinti-e: a lecsatolt mount-pont maga a gyökér, vagy a gyökér alatta áll (C29.6, M5).
    static func gyokertErint(devicePath: String?, gyoker: String) -> Bool {
        guard let d = devicePath, !d.isEmpty else { return false }
        let mount = d.hasSuffix("/") ? String(d.dropLast()) : d
        let g = gyoker.hasSuffix("/") ? String(gyoker.dropLast()) : gyoker
        return mount == "" ? true : (g == mount || g.hasPrefix(mount + "/"))
    }

    /// A `--selftest` táblázata → a hibás esetek leírása (üres: rendben).
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        let kezfogasok: [(String, String)] = [
            ("{\"port\": 5000, \"pid\": 1}", "port:5000:-"),
            ("{\"port\": 5000, \"pid\": 1, \"titok\": \"abc-DEF_123.xyz-0123\"}", "port:5000:abc-DEF_123.xyz-0123"),
            ("{\"port\": 5000, \"titok\": 42}", "port:5000:-"),
            ("{\"foglalt\": true, \"pid\": 42, \"vault\": \"/V/Manifold\"}", "foglalt:42:/V/Manifold"),
            ("{\"foglalt\": true}", "foglalt:-:-"),
            ("{\"foglalt\": false, \"port\": 7}", "port:7:-"),
            ("{}", "hiba"), ("{\"port\": \"5000\"}", "hiba"), ("nem json", "hiba"), ("", "hiba"), ("[1]", "hiba"),
        ]
        for (sor, vart) in kezfogasok {
            let mai: String
            switch kezfogas(Data(sor.utf8)) {
            case .success(let k): mai = "port:\(k.port):\(k.titok ?? "-")"
            case .failure(.foglalt(let pid, let vault)): mai = "foglalt:\(pid.map(String.init) ?? "-"):\(vault ?? "-")"
            case .failure: mai = "hiba"
            }
            if mai != vart { hibak.append("kézfogás \(sor.debugDescription): \(mai) (várt: \(vart))") }
        }
        let lecsatolas: [(String?, String, Bool)] = [
            ("/Volumes/Work", "/Volumes/Work/Manifold-OS v2", true), ("/Volumes/Work/", "/Volumes/Work/Manifold-OS v2", true),
            ("/Volumes/Work/Manifold-OS v2", "/Volumes/Work/Manifold-OS v2", true),
            ("/Volumes/Other", "/Volumes/Work/Manifold-OS v2", false), ("/Volumes/Wor", "/Volumes/Work/Manifold-OS v2", false),
            ("/Volumes/Work/Manifold-OS v2/x", "/Volumes/Work/Manifold-OS v2", false), (nil, "/Volumes/Work/x", false),
            ("", "/Volumes/Work/x", false),
        ]
        for (dev, gyoker, vart) in lecsatolas {
            let mai = gyokertErint(devicePath: dev, gyoker: gyoker)
            if mai != vart { hibak.append("lecsatolás \(dev.debugDescription) / \(gyoker): \(mai) (várt: \(vart))") }
        }
        return hibak
    }

    /// Leállítás a folyamatban lévő feladat végén: a stdin lezárása.
    func requestStop() {
        stopping = true
        try? stdinPipe.fileHandleForWriting.close()
    }

    /// Kényszerített leállítás (második kilépési kérés).
    func terminateNow() { if process.isRunning { process.terminate() } }
}
