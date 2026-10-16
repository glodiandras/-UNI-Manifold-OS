import Foundation

/// A gépszintű telepítés (F3-DESIGN §2.1, §2.6, §3.5): `{install}` = `~/Library/Application Support/Manifold`.
/// A héj itt csak OLVAS: a `workspaces.json` regiszter egyetlen írója a Python (`core/workspace.py`, atomi írással). Az F5
/// indítóig a termék vaultja a regiszter `utolso` munkaterének mappája (a `MOS_VAULT` környezeti változó felülírja).
enum Telepites {
    /// A regiszter egy munkatere, amennyit a héj használ.
    struct Munkater: Equatable {
        let id: String
        let vault: String
        let nev: String?
    }

    /// `{install}`: a `HOME` (a core is ebből számol: `core/config.py` `{home}`) alatti `Library/Application Support/Manifold`.
    static func installURL(environment: [String: String]) -> URL {
        let home = environment["HOME"].flatMap { $0.isEmpty ? nil : $0 } ?? NSHomeDirectory()
        return URL(fileURLWithPath: home, isDirectory: true)
            .appendingPathComponent("Library/Application Support/Manifold", isDirectory: true)
    }

    /// Munkatér-azonosító: 32 kisbetűs hexa jegy (`core/config.ID_MINTA`).
    static func ervenyesId(_ s: String) -> Bool {
        s.count == 32 && s.allSatisfy { ("0"..."9").contains($0) || ("a"..."f").contains($0) }
    }

    /// A regiszter (`{"formatum": 1, "utolso": "<id>", "munkaterek": {"<id>": {"vault": "/…", …}}}`) utoljára megnyitott
    /// munkatere (tiszta függvény, a `--selftest` táblázata ellenőrzi). Hibás, hiányos vagy nem abszolút vault-út: nil.
    static func utolso(regiszter: Data) -> Munkater? {
        guard let obj = try? JSONSerialization.jsonObject(with: regiszter) as? [String: Any],
              let id = obj["utolso"] as? String, ervenyesId(id),
              let munkaterek = obj["munkaterek"] as? [String: Any],
              let m = munkaterek[id] as? [String: Any],
              let vault = m["vault"] as? String, vault.hasPrefix("/") else { return nil }
        return Munkater(id: id, vault: vault, nev: m["nev"] as? String)
    }

    /// A termék vaultja: a `MOS_VAULT` (fejlesztés, tesztek), különben a regiszter `utolso` munkaterének mappája; nil, ha nincs.
    static func termekVault(environment: [String: String]) -> String? {
        if let v = environment["MOS_VAULT"], !v.isEmpty { return v }
        let regiszter = installURL(environment: environment).appendingPathComponent("workspaces.json")
        guard let adat = try? Data(contentsOf: regiszter) else { return nil }
        return utolso(regiszter: adat)?.vault
    }

    /// App Translocation: a Gatekeeper a letöltött, el nem mozdított appot egy véletlen, csak olvasható helyről futtatja
    /// (`…/AppTranslocation/…`) — minden indításkor más úton, ezért a termék előbb az Alkalmazások mappába kéri.
    static func athelyezett(_ bundle: URL) -> Bool {
        bundle.path.contains("/AppTranslocation/")
    }

#if MOS_DEVELOPER
    /// A `--selftest` táblázata → a hibás esetek leírása (üres: rendben).
    static func ellenorzes() -> [String] {
        var hibak: [String] = []
        let id = String(repeating: "ab", count: 16)
        let regiszterek: [(String, String)] = [
            ("{\"formatum\":1,\"utolso\":\"\(id)\",\"munkaterek\":{\"\(id)\":{\"vault\":\"/V/Notes\",\"nev\":\"N\"}}}", "/V/Notes"),
            ("{\"utolso\":\"\(id)\",\"munkaterek\":{\"\(id)\":{\"vault\":\"rel/ut\"}}}", "-"),
            ("{\"utolso\":\"\(id)\",\"munkaterek\":{}}", "-"),
            ("{\"utolso\":\"../x\",\"munkaterek\":{\"../x\":{\"vault\":\"/V\"}}}", "-"),
            ("{\"munkaterek\":{\"\(id)\":{\"vault\":\"/V\"}}}", "-"),
            ("{\"utolso\":\"\(id.uppercased())\",\"munkaterek\":{\"\(id.uppercased())\":{\"vault\":\"/V\"}}}", "-"),
            ("nem json", "-"), ("[]", "-"),
        ]
        for (json, vart) in regiszterek {
            let mai = utolso(regiszter: Data(json.utf8))?.vault ?? "-"
            if mai != vart { hibak.append("regiszter \(json.debugDescription): \(mai) (várt: \(vart))") }
        }
        let install = installURL(environment: ["HOME": "/Users/x y"]).path
        if install != "/Users/x y/Library/Application Support/Manifold" { hibak.append("install: \(install)") }
        if termekVault(environment: ["MOS_VAULT": "/E", "HOME": "/nincs-ilyen"]) != "/E" { hibak.append("MOS_VAULT nem nyer") }
        if termekVault(environment: ["HOME": "/nincs-ilyen-home-\(id)"]) != nil { hibak.append("regiszter nélkül is van vault") }
        let at: [(String, Bool)] = [
            ("/private/var/folders/x/AppTranslocation/1234/d/Manifold.app", true), ("/Applications/Manifold.app", false),
        ]
        for (ut, vart) in at where athelyezett(URL(fileURLWithPath: ut)) != vart { hibak.append("áthelyezett \(ut): \(!vart)") }
        return hibak
    }
#endif
}
