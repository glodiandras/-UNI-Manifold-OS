import AppKit

@main
struct ManifoldApp {
    @MainActor
    static func main() {
        if CommandLine.arguments.dropFirst().first == "--kuka" { exit(Kuka.futtat()) }
        // `--naptar <parancs>`: a naptár- és emlékeztető-segéd (C29) — NSApplication és ablak nélkül, a stdin/stdout JSON
        if CommandLine.arguments.count >= 2, CommandLine.arguments[1] == "--naptar" {
            exit(Naptar.futtat(Array(CommandLine.arguments.dropFirst(2))))
        }
        let app = NSApplication.shared
#if MOS_DEVELOPER
        // Csak a fejlesztői buildben (`MOS_DEVELOPER_BUILD=1 bash shell/build.sh`): `--selftest` (alap ellenőrzés) vagy
        // `--selftest=<forgatókönyv>` (kilepes, core-halal, core-ujraindul, kezfogas-ido, szerkesztes, lecsatolas)
        let selftestArg = CommandLine.arguments.first { $0 == "--selftest" || $0.hasPrefix("--selftest=") }
        let selftest = selftestArg != nil
        let forgatokonyv = selftestArg.flatMap { $0.hasPrefix("--selftest=") ? String($0.dropFirst("--selftest=".count)) : nil }
        if let f = forgatokonyv, !["kilepes", "core-halal", "core-ujraindul", "kezfogas-ido", "szerkesztes", "lecsatolas"].contains(f) {
            print("SELFTEST HIBA: ismeretlen forgatókönyv: \(f)")
            exit(2)
        }
        let controller = AppController(selftest: selftest, forgatokonyv: forgatokonyv)
        app.delegate = controller
        app.setActivationPolicy(selftest ? .accessory : .regular)
#else
        let controller = AppController()
        app.delegate = controller
        app.setActivationPolicy(.regular)
#endif
        withExtendedLifetime(controller) { app.run() }
    }
}
