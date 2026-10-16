import AppKit

/// Az első indítás és a munkatérváltás natív, core-tól független belépője. A Python az egyetlen lemezíró.
@MainActor
final class InditoAblak: NSWindowController, NSWindowDelegate {
    private let gyoker: URL
    private let onMegnyit: (String) -> Void
    private let onMegsem: () -> Void
    private let jelenlegiVault: String?
    private var futoUtak = Set<String>()
    private var kliens: InditoKliens?
    private var muvelet: [String: Any]?
    private var vissza: (() -> Void)?
    private var megszakitasKerdes = false
    private var kesz = false
    private let tartalom = NSStackView()
    private let lista = NSStackView()
    private let allapot = NSTextField(wrappingLabelWithString: "")
    private let jelzo = NSProgressIndicator()
    private let ujra = NSButton(title: L("Újrapróbálás"), target: nil, action: nil)
    private let megsem = NSButton(title: L("Mégse"), target: nil, action: nil)
    private var vezerlok: [NSControl] = []
    private var frissites: NSButton!

    init(gyoker: URL, vanSzerkeszto: Bool, jelenlegiVault: String? = nil,
         onMegnyit: @escaping (String) -> Void, onMegsem: @escaping () -> Void) {
        self.gyoker = gyoker; self.onMegnyit = onMegnyit; self.onMegsem = onMegsem
        self.jelenlegiVault = jelenlegiVault.map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path }
        let ablak = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 650, height: 610),
                             styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        ablak.title = L("Munkatér megnyitása")
        super.init(window: ablak)
        ablak.delegate = self
        ablak.isReleasedWhenClosed = false
        ablak.contentMinSize = NSSize(width: 560, height: 480)
        let tarto = NSView()
        ablak.contentView = tarto
        tartalom.orientation = .vertical; tartalom.alignment = .leading; tartalom.spacing = 16
        tartalom.translatesAutoresizingMaskIntoConstraints = false
        tarto.addSubview(tartalom)
        NSLayoutConstraint.activate([
            tartalom.leadingAnchor.constraint(equalTo: tarto.leadingAnchor, constant: 28),
            tartalom.trailingAnchor.constraint(equalTo: tarto.trailingAnchor, constant: -28),
            tartalom.topAnchor.constraint(equalTo: tarto.topAnchor, constant: 28),
            tartalom.bottomAnchor.constraint(equalTo: tarto.bottomAnchor, constant: -24),
        ])
        let cim = NSTextField(labelWithString: "Manifold")
        cim.font = .systemFont(ofSize: 29, weight: .semibold)
        tartalom.addArrangedSubview(cim)
        let leiras = NSTextField(wrappingLabelWithString: L("A jegyzeteid a saját mappádban maradnak. Hozz létre vagy nyiss meg egy munkateret, vagy próbáld ki az offline demót."))
        leiras.textColor = .secondaryLabelColor
        tartalom.addArrangedSubview(leiras)
        let gombok = NSStackView(); gombok.orientation = .horizontal; gombok.spacing = 10
        for (cim, muvelet) in [(L("Munkatér létrehozása…"), #selector(letrehoz)), (L("Mappa megnyitása…"), #selector(mappaMegnyit)),
                                (L("Demó kipróbálása"), #selector(demo))] {
            let gomb = NSButton(title: cim, target: self, action: muvelet)
            gomb.bezelStyle = .rounded; gombok.addArrangedSubview(gomb); vezerlok.append(gomb)
        }
        tartalom.addArrangedSubview(gombok)
        let elozok = NSStackView(); elozok.orientation = .horizontal; elozok.spacing = 12
        let felirat = NSTextField(labelWithString: L("Legutóbbi munkaterek")); felirat.font = .systemFont(ofSize: 13, weight: .semibold)
        elozok.addArrangedSubview(felirat)
        frissites = NSButton(title: L("Frissítés"), target: self, action: #selector(frissit))
        frissites.bezelStyle = .rounded; elozok.addArrangedSubview(frissites); vezerlok.append(frissites)
        tartalom.addArrangedSubview(elozok)
        lista.orientation = .vertical; lista.alignment = .leading; lista.spacing = 10
        let gorgeto = NSScrollView(); gorgeto.hasVerticalScroller = true; gorgeto.drawsBackground = false
        gorgeto.documentView = lista; lista.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([lista.leadingAnchor.constraint(equalTo: gorgeto.contentView.leadingAnchor),
            lista.trailingAnchor.constraint(equalTo: gorgeto.contentView.trailingAnchor),
            lista.topAnchor.constraint(equalTo: gorgeto.contentView.topAnchor)])
        tartalom.addArrangedSubview(gorgeto)
        gorgeto.widthAnchor.constraint(equalTo: tartalom.widthAnchor).isActive = true
        gorgeto.heightAnchor.constraint(greaterThanOrEqualToConstant: 100).isActive = true
        gorgeto.setContentHuggingPriority(.defaultLow, for: .vertical)
        let also = NSStackView(); also.orientation = .horizontal; also.alignment = .centerY; also.spacing = 10
        jelzo.style = .spinning; jelzo.controlSize = .small; jelzo.isDisplayedWhenStopped = false
        also.addArrangedSubview(jelzo)
        allapot.setContentHuggingPriority(.defaultLow, for: .horizontal)
        allapot.setAccessibilityRole(.staticText)
        also.addArrangedSubview(allapot)
        ujra.target = self; ujra.action = #selector(ujraprobal); ujra.isHidden = true; also.addArrangedSubview(ujra)
        megsem.target = self; megsem.action = #selector(megsemKattint); megsem.keyEquivalent = "\u{1b}"
        megsem.title = vanSzerkeszto ? L("Vissza a szerkesztéshez") : L("Kilépés")
        also.addArrangedSubview(megsem)
        tartalom.addArrangedSubview(also)
        also.widthAnchor.constraint(equalTo: tartalom.widthAnchor).isActive = true
        ablak.center()
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func megjelenit(automatikus: Bool = false) {
        showWindow(nil); window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        betolt(automatikus: automatikus)
    }
    func eloterbe() { window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    func bezar() { kesz = true; window?.close() }
    func windowShouldClose(_ sender: NSWindow) -> Bool { megsemKattint(); return false }
    func folyamat(_ szoveg: String) {
        vezerles(enged: false); allapot.stringValue = szoveg; allapot.textColor = .secondaryLabelColor; jelzo.startAnimation(nil)
    }
    func hiba(_ szoveg: String, ujra ujraproba: (() -> Void)? = nil) {
        if let ujraproba { muvelet = [:]; vissza = ujraproba }
        kliens = nil; jelzo.stopAnimation(nil); vezerles(enged: true)
        allapot.stringValue = "⚠ " + szoveg; allapot.textColor = .labelColor
        ujra.isHidden = muvelet == nil
        NSAccessibility.post(element: allapot, notification: .valueChanged)
    }
    private func vezerles(enged: Bool) {
        for v in vezerlok { v.isEnabled = enged }
        func allit(_ nez: NSView) {
            if let v = nez as? NSControl { v.isEnabled = enged }
            for v in nez.subviews { allit(v) }
        }
        allit(lista)
        ujra.isHidden = true
    }
    private func ker(_ keres: [String: Any], szoveg: String, eredmeny: @escaping ([String: Any]) -> Void) {
        guard kliens == nil else { return }
        muvelet = keres
        vissza = { [weak self] in self?.ker(keres, szoveg: szoveg, eredmeny: eredmeny) }
        folyamat(szoveg)
        let kliens = InditoKliens(root: gyoker, keres: keres)
        self.kliens = kliens
        kliens.indit(haladas: { [weak self] e in
            guard let self, case .haladas(let h) = e else { return }
            self.allapot.stringValue = Self.haladasSzoveg(h)
        }, kesz: { [weak self] r in
            guard let self else { return }
            self.kliens = nil
            if self.megszakitasKerdes { self.megszakitasKerdes = false; self.onMegsem(); return }
            self.jelzo.stopAnimation(nil); self.vezerles(enged: true)
            switch r {
            case .success(let obj):
                if obj["ok"] as? Bool == true { self.allapot.stringValue = ""; eredmeny(obj) }
                else { self.hiba(obj["hiba"] as? String ?? L("A művelet nem sikerült. Próbáld újra.")) }
            case .failure(.megszakitva): self.onMegsem()
            case .failure: self.hiba(L("Az indító nem kapott érvényes választ. Próbáld újra."))
            }
        })
    }
    static func haladasSzoveg(_ h: [String: Any]) -> String {
        if let u = h["uzenet"] as? String, !u.isEmpty { return u }
        switch h["lepes"] as? String {
        case "felmer", "felmeres": return L("Mappa ellenőrzése…")
        case "pillanat", "snapshot": return L("Biztonsági pillanatkép készítése…")
        case "regiszter": return L("Munkatér regisztrálása…")
        case "kesz": return L("Munkatér készen áll.")
        default: return L("Munkatér előkészítése…")
        }
    }
    private func betolt(automatikus: Bool) {
        ker(["muvelet": "lista"], szoveg: L("Munkaterek betöltése…")) { [weak self] obj in
            guard let self else { return }
            let elemek = obj["munkaterek"] as? [[String: Any]] ?? []
            self.listaKitolt(elemek)
            if automatikus, obj["inditas"] as? String == "utolso", let id = obj["utolso"] as? String,
               let m = elemek.first(where: { $0["id"] as? String == id && $0["elerheto"] as? Bool == true }),
               let vault = m["vault"] as? String { self.megnyit(vault) }
        }
    }
    private func listaKitolt(_ elemek: [[String: Any]]) {
        futoUtak.removeAll()
        for v in lista.arrangedSubviews { lista.removeArrangedSubview(v); v.removeFromSuperview() }
        if elemek.isEmpty {
            let ures = NSTextField(wrappingLabelWithString: L("Még nincs munkatered. Kezdd egy új mappával, vagy nyisd meg a meglévő Markdown-jegyzeteidet."))
            ures.textColor = .secondaryLabelColor; lista.addArrangedSubview(ures); return
        }
        for elem in elemek {
            guard let vault = elem["vault"] as? String, vault.hasPrefix("/") else { continue }
            let sor = NSStackView(); sor.orientation = .horizontal; sor.spacing = 8
            let oszlop = NSStackView(); oszlop.orientation = .vertical; oszlop.alignment = .leading; oszlop.spacing = 2
            let nev = (elem["nev"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? URL(fileURLWithPath: vault).lastPathComponent
            let megnyit = NSButton(title: nev, target: self, action: #selector(elozoMegnyit(_:)))
            megnyit.bezelStyle = .rounded; megnyit.identifier = NSUserInterfaceItemIdentifier(vault)
            oszlop.addArrangedSubview(megnyit)
            let elerheto = elem["elerheto"] as? Bool == true
            let kanonikus = URL(fileURLWithPath: vault).resolvingSymlinksInPath().path
            let jelenlegi = kanonikus == jelenlegiVault
            let fut = elem["fut"] as? Bool == true && !jelenlegi
            if fut { futoUtak.insert(kanonikus) }
            let jelzes = !elerheto ? L("Nem érhető el; csatlakoztasd a kötetet, vagy keress másik mappát.")
                : jelenlegi ? L("Jelenlegi munkatér") : fut ? L("Már nyitva egy másik ablakban") : ""
            let hely = NSTextField(wrappingLabelWithString: vault + (jelzes.isEmpty ? "" : " — " + jelzes))
            hely.font = .systemFont(ofSize: 11); hely.textColor = .secondaryLabelColor; oszlop.addArrangedSubview(hely)
            sor.addArrangedSubview(oszlop)
            if let id = elem["id"] as? String {
                let felejt = NSButton(title: L("Eltávolítás a listáról"), target: self, action: #selector(elfelejt(_:)))
                felejt.identifier = NSUserInterfaceItemIdentifier(id); felejt.bezelStyle = .inline; sor.addArrangedSubview(felejt)
            }
            lista.addArrangedSubview(sor)
            sor.widthAnchor.constraint(equalTo: lista.widthAnchor).isActive = true
        }
    }
    @objc private func frissit() { betolt(automatikus: false) }
    @objc private func elozoMegnyit(_ gomb: NSButton) { if let vault = gomb.identifier?.rawValue { megnyit(vault) } }
    @objc private func elfelejt(_ gomb: NSButton) {
        guard let id = gomb.identifier?.rawValue else { return }
        ker(["muvelet": "elfelejt", "id": id], szoveg: L("Lista frissítése…")) { [weak self] _ in self?.betolt(automatikus: false) }
    }
    @objc private func ujraprobal() { vissza?() }
    @objc private func demo() {
        ker(["muvelet": "demo"], szoveg: L("Offline demó előkészítése…")) { [weak self] obj in self?.megnyitasValasz(obj) }
    }
    @objc private func mappaMegnyit() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.allowsMultipleSelection = false; panel.canCreateDirectories = false; panel.prompt = L("Mappa kiválasztása")
        panel.message = L("Válaszd ki a jegyzeteid mappáját. Az ellenőrzés nem változtat meg fájlokat.")
        guard let window else { return }
        panel.beginSheetModal(for: window) { [weak self] valasz in
            guard valasz == .OK, let url = panel.url else { return }
            self?.felmer(url.path, uj: false)
        }
    }
    @objc private func letrehoz() {
        let panel = NSSavePanel(); panel.canCreateDirectories = false; panel.title = L("Munkatér létrehozása")
        panel.prompt = L("Mappa ellenőrzése"); panel.nameFieldStringValue = L("Saját jegyzetek")
        panel.message = L("Adj nevet az új jegyzetmappának. A létrehozás előtt megmutatjuk a változtatásokat.")
        guard let window else { return }
        panel.beginSheetModal(for: window) { [weak self] valasz in
            guard valasz == .OK, let url = panel.url else { return }
            self?.felmer(url.path, uj: true)
        }
    }
    private func felmer(_ vault: String, uj: Bool) {
        ker(["muvelet": "felmer", "vault": vault, "uj_mappa": uj], szoveg: L("Mappa ellenőrzése…")) { [weak self] obj in
            guard let self, let f = obj["felmeres"] as? [String: Any] else { return }
            let tiltott = f["eredmeny"] as? String == "tilos"
            let meglevo = f["meglevo_id"] as? String != nil
            let uzenetek = obj["uzenetek"] as? [String] ?? []
            if tiltott { self.hiba(uzenetek.joined(separator: "\n")); return }
            if meglevo { self.megnyit(vault); return }
            let valtozasok = obj["valtozasok"] as? [String] ?? []
            let alert = NSAlert(); alert.messageText = L("Manifold-munkatér beállítása")
            alert.informativeText = vault + "\n\n" + L("A jegyzeteid és az Obsidian-beállításaid megmaradnak.") + "\n\n"
                + (uzenetek + valtozasok).joined(separator: "\n")
            alert.addButton(withTitle: L("Munkatér létrehozása")); alert.addButton(withTitle: L("Mégse"))
            guard let window = self.window else { return }
            alert.beginSheetModal(for: window) { [weak self] valasz in
                guard valasz == .alertFirstButtonReturn else { return }
                self?.ker(["muvelet": "letrehoz", "vault": vault, "uj_mappa": uj, "elfogad": true],
                          szoveg: L("Munkatér előkészítése…")) { [weak self] obj in self?.megnyitasValasz(obj) }
            }
        }
    }
    private func megnyit(_ vault: String) {
        if futoUtak.contains(URL(fileURLWithPath: vault).resolvingSymlinksInPath().path) {
            muvelet = nil; vissza = nil
            hiba(L("A munkatér már nyitva van egy másik Manifold-ablakban.")); return
        }
        ker(["muvelet": "megnyit", "vault": vault], szoveg: L("Munkatér megnyitása…")) { [weak self] obj in self?.megnyitasValasz(obj) }
    }
    private func megnyitasValasz(_ obj: [String: Any]) {
        guard let m = obj["munkater"] as? [String: Any], let vault = m["vault"] as? String, vault.hasPrefix("/") else {
            hiba(L("Az indító nem kapott érvényes választ. Próbáld újra.")); return
        }
        muvelet = nil; vissza = nil; folyamat(L("Munkatér megnyitása…")); onMegnyit(vault)
    }
    @objc private func megsemKattint() {
        guard !kesz else { return }
        if let kliens {
            megszakitasKerdes = true
            if !kliens.megszakit() {
                allapot.stringValue = L("A biztonságos előkészítés befejezése után visszatérünk.")
            }
            return
        }
        onMegsem()
    }
}
