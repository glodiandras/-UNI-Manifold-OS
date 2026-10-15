import Foundation

/// Hol van a Manifold-OS? A `Manifold.app` a gyökérben él, ezért a gyökér az app szülőmappája.
/// Beégetett út nincs, telepítéskori hely nincs, nincs mentett beállítás és kötet-átnézés (CLAUDE.md §4).
/// A `MOS_ROOT` környezeti változó felülírja (fejlesztéshez és tesztekhez).
enum RootLocator {
    /// Érvényes gyökér: van benne futtatható `bin/mos` és `config/os.toml`.
    static func isValid(_ url: URL) -> Bool {
        let fm = FileManager.default
        return fm.isExecutableFile(atPath: url.appendingPathComponent("bin/mos").path)
            && fm.fileExists(atPath: url.appendingPathComponent("config/os.toml").path)
    }

    static func locate(environment: [String: String], bundle: URL) -> URL? {
        var candidates: [URL] = []
        if let env = environment["MOS_ROOT"], !env.isEmpty { candidates.append(URL(fileURLWithPath: env)) }
        candidates.append(bundle.deletingLastPathComponent())
        return candidates.map { $0.resolvingSymlinksInPath() }.first(where: isValid)
    }
}
