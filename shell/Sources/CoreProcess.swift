import Foundation

/// A Python-core gyermekfolyamata. Életciklus (ARCHITECTURE 2.): a core kiírja a portját (egy JSON-sor a
/// stdoutra); a stdin lezárása = leállás a folyamatban lévő feladat végén.
///
/// Egypéldányos zár (C29.6, T027; F3-DESIGN §4): ha ugyanazon a vaulton már fut egy core, a kézfogás sora
/// `{"foglalt": true, "pid": N, "vault": "…"}`, a core 75-tel kilép — ilyenkor a héj nem indít második ablakot.
/// Konfigurációs hiba (nincs vault, nem munkatér, hibás beállításfájl, újabb formátumú munkatér): a sor
/// `{"hiba": "<kod>", "param": …, "uzenet": "…"}`, a kilépési kód 78 — a héj a `kod`-hoz tartozó üzenetet mutatja.
final class CoreProcess {
    /// A sikeres kézfogás tartalma: a core portja és API-titka (35. döntés, T071): a héj a titkot a lap betöltése előtt injektálja
    /// a felületbe, és újraindításkor ugyanazt adja vissza a core-nak (`MOS_API_TITOK`), hogy a lap titka érvényes maradjon.
    /// F3 (additív): a vault kanonikus útja (ennek a kötetét figyeli a lecsatolás), a munkatér azonosítója és az elrendezés.
    struct Kezfogas: Equatable {
        let port: Int
        let titok: String?
        var vault: String? = nil
        var munkaterId: String? = nil
        var elrendezes: String? = nil
    }

    enum StartError: Error {
        case failed(String)
        case foglalt(pid: Int?, vault: String?)
        case konfig(kod: String, uzenet: String)
    }

    /// A core kilépési kódja, ha másik core fut ugyanazon a vaulton (`CORE_ZAR_KILEPES` a `core/server.py`-ban).
    static let foglaltKilepesiKod: Int32 = 75
    /// A core kilépési kódja konfigurációs hibánál (`KONFIG_HIBA_KILEPES`, EX_CONFIG).
    static let konfigKilepesiKod: Int32 = 78

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
    /// `vault`: a megnyitandó vault (`MOS_VAULT`; termékben a regiszterből). `termek` (F3-DESIGN §2.6): `MOS_ELRENDEZES=termek`, és a
    /// héj futtathatója a naptár-segéd és a CLI-mód (`MOS_NAPTAR_SEGED`, `MOS_HEJ_CLI`), ha a környezet nem adja meg.
    init(root: URL, vault: String? = nil, termek: Bool = false, port: Int? = nil, titok: String? = nil,
         munkaterValasztas: Bool = false) {
        process.executableURL = root.appendingPathComponent("bin/mos")
        process.arguments = ["core", "start"]
        process.currentDirectoryURL = root
        process.environment = CoreProcess.kornyezet(alap: ProcessInfo.processInfo.environment, root: root, vault: vault,
                                                    termek: termek, port: port, titok: titok,
                                                    futtathato: Bundle.main.executablePath, munkaterValasztas: munkaterValasztas)
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
    }

    /// A core környezete (tiszta függvény, a `--selftest` táblázata ellenőrzi).
    static func kornyezet(alap: [String: String], root: URL, vault: String?, termek: Bool, port: Int?, titok: String?,
                          futtathato: String?, munkaterValasztas: Bool = false) -> [String: String] {
        var env = alap
        env["MOS_ROOT"] = root.path
        if munkaterValasztas { env["MOS_MUNKATER_VALTAS"] = "1" }
        else { env.removeValue(forKey: "MOS_MUNKATER_VALTAS") }
        if let vault, !vault.isEmpty { env["MOS_VAULT"] = vault }
        if termek {
            env["MOS_ELRENDEZES"] = "termek"
            if let futtathato {
                for kulcs in ["MOS_HEJ_CLI", "MOS_NAPTAR_SEGED"] where (env[kulcs] ?? "").isEmpty { env[kulcs] = futtathato }
            }
        }
        if let port { env["MOS_CORE_PORT"] = String(port) }
        if let titok { env["MOS_API_TITOK"] = titok }
        return env
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
            else if p.terminationStatus == CoreProcess.konfigKilepesiKod {
                // a `{"hiba"}` sor a kilépés után is beérkezhet a stdout kezelőjébe: a stderr `(kod)`-ja ugyanazt mondja
                pending?(.failure(.konfig(kod: CoreProcess.stderrKod(err) ?? "konfig_hiba", uzenet: Eletciklus.farok(err))))
            }
            else { pending?(.failure(.failed(err.isEmpty ? L("a core kilépett az indulás előtt") : Eletciklus.farok(err)))) }
            DispatchQueue.main.async { self.onExit?() }
        }
        do { try process.run() } catch {
            handshake = nil
            completion(.failure(.failed(L("a core nem indítható: %@", error.localizedDescription))))
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

    /// A kézfogás sorának értelmezése (tiszta függvény, a `--selftest` táblázata ellenőrzi): port (és a `titok`, `vault`,
    /// `munkater_id`, `elrendezes`) → siker, `foglalt: true` → másik példány fut, `hiba: "<kod>"` → konfigurációs hiba,
    /// minden más → hiba.
    static func kezfogas(_ sor: Data) -> Result<Kezfogas, StartError> {
        guard let obj = try? JSONSerialization.jsonObject(with: sor) as? [String: Any] else {
            return .failure(.failed(L("érvénytelen kézfogás: %@", String(decoding: sor, as: UTF8.self))))
        }
        if obj["foglalt"] as? Bool == true {
            return .failure(.foglalt(pid: obj["pid"] as? Int, vault: obj["vault"] as? String))
        }
        if let kod = obj["hiba"] as? String, !kod.isEmpty {
            return .failure(.konfig(kod: kod, uzenet: obj["uzenet"] as? String ?? ""))
        }
        if let port = obj["port"] as? Int {
            let vault = (obj["vault"] as? String).flatMap { $0.hasPrefix("/") ? $0 : nil }
            return .success(Kezfogas(port: port, titok: obj["titok"] as? String, vault: vault,
                                     munkaterId: obj["munkater_id"] as? String, elrendezes: obj["elrendezes"] as? String))
        }
        return .failure(.failed(L("érvénytelen kézfogás: %@", String(decoding: sor, as: UTF8.self))))
    }

    /// A stderr `[core] … (<kod>): …` sorából a hibakód (a 78-as kilépésnél, ha a kézfogás-sor nem ért be).
    static func stderrKod(_ szoveg: String) -> String? {
        for sor in szoveg.split(separator: "\n").reversed() where sor.hasPrefix("[core]") {
            guard let nyit = sor.firstIndex(of: "("), let zar = sor[nyit...].firstIndex(of: ")") else { continue }
            let kod = sor[sor.index(after: nyit)..<zar]
            if !kod.isEmpty, kod.allSatisfy({ $0.isASCII && ($0.isLowercase || $0.isNumber || $0 == "_") }) { return String(kod) }
        }
        return nil
    }

    /// A konfigurációs hiba szövege a felhasználónak (a `kod` szerint; tiszta függvény).
    static func konfigSzoveg(kod: String, uzenet: String) -> String {
        let reszlet = uzenet.isEmpty ? "" : "\n\n\(uzenet)"
        switch kod {
        case "nincs_vault":
            return L("Nincs megadva a vault (a jegyzetek mappája). Fejlesztői checkoutban: bin/mos portable init --vault <mappa>.") + reszlet
        case "nem_workspace", "nincs_workspace":
            return L("A mappa még nem Manifold-munkatér. Létrehozása: mos workspace letrehoz <mappa>.") + reszlet
        case "vault_nem_elerheto":
            return L("A munkatér mappája nem érhető el. Csatlakoztatva van a kötet?") + reszlet
        case "workspace_ujabb":
            return L("Ezt a munkateret a Manifold egy újabb változata hozta létre. Frissítsd az alkalmazást.") + reszlet
        case "settings_toml_hibas", "workspace_toml_hibas", "config_toml_hibas":
            return L("Egy beállításfájl hibás, ezért a Manifold nem indul (%@).", kod) + reszlet
        case "iras_a_kodba":
            return L("A beállítások az alkalmazás csak olvasható mappájába írnának (%@).", kod) + reszlet
        default:
            return L("A konfiguráció nem tölthető be (%@).", kod) + reszlet
        }
    }

    /// A kötet lecsatolásának értesítése a figyelt utak (a vault a kézfogásból, és a kódfa) bármelyikét érinti-e.
    static func barmelyiketErinti(devicePath: String?, utak: [String]) -> Bool {
        utak.contains { gyokertErint(devicePath: devicePath, gyoker: $0) }
    }

    /// A kötet lecsatolásának értesítése (`NSWorkspace.willUnmountNotification`, `NSDevicePath`) a Manifold-OS
    /// gyökerét érinti-e: a lecsatolt mount-pont maga a gyökér, vagy a gyökér alatta áll (C29.6, M5).
    static func gyokertErint(devicePath: String?, gyoker: String) -> Bool {
        guard let d = devicePath, !d.isEmpty else { return false }
        let mount = d.hasSuffix("/") ? String(d.dropLast()) : d
        let g = gyoker.hasSuffix("/") ? String(gyoker.dropLast()) : gyoker
        return mount == "" ? true : (g == mount || g.hasPrefix(mount + "/"))
    }

#if MOS_DEVELOPER
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
            ("{\"port\": 5000, \"titok\": \"t\", \"vault\": \"/V/N\", \"munkater_id\": \"ab\", \"elrendezes\": \"termek\"}",
             "port:5000:t:/V/N:ab:termek"),
            ("{\"port\": 5000, \"vault\": \"rel\"}", "port:5000:-"),
            ("{\"hiba\": \"nem_workspace\", \"param\": {}, \"uzenet\": \"x\"}", "konfig:nem_workspace:x"),
            ("{\"hiba\": \"\"}", "hiba"),
        ]
        for (sor, vart) in kezfogasok {
            let mai: String
            switch kezfogas(Data(sor.utf8)) {
            case .success(let k):
                let extra = [k.vault, k.munkaterId, k.elrendezes].compactMap { $0 }
                mai = (["port:\(k.port):\(k.titok ?? "-")"] + extra).joined(separator: ":")
            case .failure(.foglalt(let pid, let vault)): mai = "foglalt:\(pid.map(String.init) ?? "-"):\(vault ?? "-")"
            case .failure(.konfig(let kod, let uzenet)): mai = "konfig:\(kod):\(uzenet)"
            case .failure: mai = "hiba"
            }
            if mai != vart { hibak.append("kézfogás \(sor.debugDescription): \(mai) (várt: \(vart))") }
        }
        let stderrek: [(String, String?)] = [
            ("[core] a core nem indul (nincs_vault): x\n", "nincs_vault"),
            ("zaj\n[core] a konfiguráció nem tölthető be (settings_toml_hibas): y", "settings_toml_hibas"),
            ("[core] valami (Nem Kod)", nil), ("Traceback (most recent call last)", nil),
        ]
        for (szoveg, vart) in stderrek where stderrKod(szoveg) != vart {
            hibak.append("stderr-kód \(szoveg.debugDescription): \(stderrKod(szoveg) ?? "-") (várt: \(vart ?? "-"))")
        }
        if !konfigSzoveg(kod: "ismeretlen_x", uzenet: "").contains("ismeretlen_x") { hibak.append("konfigSzoveg: a kód hiányzik") }
        let r = URL(fileURLWithPath: "/R")
        let e1 = kornyezet(alap: ["MOS_NAPTAR_SEGED": "/al"], root: r, vault: "/V", termek: true, port: 7, titok: "t",
                           futtathato: "/A.app/Contents/MacOS/Manifold")
        let e1vart = ["MOS_NAPTAR_SEGED": "/al", "MOS_ROOT": "/R", "MOS_VAULT": "/V", "MOS_ELRENDEZES": "termek",
                      "MOS_HEJ_CLI": "/A.app/Contents/MacOS/Manifold", "MOS_CORE_PORT": "7", "MOS_API_TITOK": "t"]
        if e1 != e1vart { hibak.append("termék-környezet: \(e1)") }
        let e2 = kornyezet(alap: ["MOS_VAULT": "/E"], root: r, vault: nil, termek: false, port: nil, titok: nil, futtathato: "/x")
        if e2 != ["MOS_VAULT": "/E", "MOS_ROOT": "/R"] { hibak.append("hordozható környezet: \(e2)") }
        let e3 = kornyezet(alap: ["MOS_VAR": "/regi/var"], root: r, vault: "/uj", termek: true, port: nil, titok: nil,
                           futtathato: nil, munkaterValasztas: true)
        if e3["MOS_MUNKATER_VALTAS"] != "1" || e3["MOS_VAULT"] != "/uj" { hibak.append("választott workspace jelölése") }
        let e4 = kornyezet(alap: ["MOS_MUNKATER_VALTAS": "1"], root: r, vault: "/regi", termek: false,
                           port: nil, titok: nil, futtathato: nil)
        if e4["MOS_MUNKATER_VALTAS"] != nil { hibak.append("régi indítási környezet visszaállítása") }
        let lecsatolas: [(String?, String, Bool)] = [
            ("/Volumes/Disk", "/Volumes/Disk/Manifold", true), ("/Volumes/Disk/", "/Volumes/Disk/Manifold", true),
            ("/Volumes/Disk/Manifold", "/Volumes/Disk/Manifold", true),
            ("/Volumes/Other", "/Volumes/Disk/Manifold", false), ("/Volumes/Dis", "/Volumes/Disk/Manifold", false),
            ("/Volumes/Disk/Manifold/x", "/Volumes/Disk/Manifold", false), (nil, "/Volumes/Disk/x", false),
            ("", "/Volumes/Disk/x", false),
        ]
        for (dev, gyoker, vart) in lecsatolas {
            let mai = gyokertErint(devicePath: dev, gyoker: gyoker)
            if mai != vart { hibak.append("lecsatolás \(dev.debugDescription) / \(gyoker): \(mai) (várt: \(vart))") }
        }
        if !barmelyiketErinti(devicePath: "/Volumes/Jegyzet", utak: ["/Volumes/Jegyzet/Notes", "/Applications/M.app/x"])
            || barmelyiketErinti(devicePath: "/Volumes/Mas", utak: ["/Volumes/Jegyzet/Notes", "/Applications/M.app/x"]) {
            hibak.append("lecsatolás: a vault kötete")
        }
        return hibak
    }
#endif

    /// Leállítás a folyamatban lévő feladat végén: a stdin lezárása.
    func requestStop() {
        stopping = true
        try? stdinPipe.fileHandleForWriting.close()
    }

    /// Kényszerített leállítás (második kilépési kérés).
    func terminateNow() { if process.isRunning { process.terminate() } }
}
