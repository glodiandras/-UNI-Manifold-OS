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
        // `--selftest` (alap ellenőrzés) vagy `--selftest=<forgatókönyv>` (C29.7b: kilepes, core-halal, core-ujraindul, kezfogas-ido;
        // C33: szerkesztes — megnyitás, beágyazás, gépelés, mentés, link a valódi WebKitben —, lecsatolas — a kötet lecsatolása)
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
        withExtendedLifetime(controller) { app.run() }
    }
}
