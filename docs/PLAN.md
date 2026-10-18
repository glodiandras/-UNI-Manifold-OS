# Manifold — Productization Master Plan (terv és végrehajtási napló)

Dátum: 2026-10-15. Forrás: `/Volumes/Work/Manifold-OS v2` (**csak olvasva**, a source of truth). Cél: `/Volumes/Work/[UNI] Manifold-OS` — egy önálló git-repó, amelyből a **Manifold** termék épül.

**Aktuális kiegészítés (2026-10-18):** a [PDF-audit és stabilizálási/befejezési terv](plan/2026-10-18-STABILIZALASI-TERV.md) a felhasználó 13 oldalas UI-észrevételeit összeveti a jelenlegi UNI-munkafával, és rögzíti a RAM-, macOS 27 design-, integrációs és kiadási kapukat. Az eredeti F1–F11 célok megmaradnak. A régi zöld naplók nem igazolják a mostani munkafát; először a frissen kimutatott build-/teszthibákat és a részben kész fejlesztések bekötését kell rendezni.

**Kivitelezés:** az [S0 integrációs jelentés](plan/S0-INTEGRACIO.md) követi az első javítási szakaszt és annak friss kapuit. A további PDF-, RAM- és designfeladatok a kiegészítő terv szerinti S1–S6 szakaszokban maradnak.

A részletes auditok (fájl:sor hivatkozásokkal, a terv bizonyítéka) a `docs/plan/audit/` alatt:
`01-personal-coupling.md` · `02-core-architektura.md` · `03-felulet.md` · `04-hej-build-installer.md` · `05-ai-reteg.md` · `06-tesztek-es-vault-konvenciok.md`.

---

## 0. Rögzített döntések (a felhasználó válaszai, 2026-10-15)

| # | Döntés |
|---|---|
| P1 | **DO NOT REBUILD.** A v2 kódja, architektúrája (Swift-héj → Svelte 5 felület → Python core → modell-worker → láncok), biztonsági filozófiája (atomi írás, pillanatkép, gépi-írás szolgáltatás, D9 „csak kalibrált modell”, homokozók, visszavonás, D3 „egyszeri letöltés, utána offline”) **változatlanul átkerül**. A v2 86 rögzített döntése és a D1–D12 elvei érvényben maradnak, kivéve ahol a termékesítés kifejezetten módosít (ezeket a 9. fejezet sorolja). |
| P2 | **Felületi nyelv: csak angol** az első verzióban. A kód azonosítói magyarok maradnak. A Setup „Language” lépése a **workspace tartalmi nyelvét** választja (átirat-modellek, dátumformátum, sablonok, kapuk nyelvi profilja), nem a felület nyelvét. A szövegek egy központi szótárba kerülnek (`t()`), hogy később más nyelv is jöhessen. |
| P3 | **Obsidian-követő, generikus vault-kezelés.** Indító vault-választó, ⌘, beállítás-ablak oldalsávval, core-modul kapcsolók, parancspaletta; a szerkesztő és minden részfunkció (osztott nézet, tulajdonságok, canvas, Bases, beágyazás, linkek) az Obsidian viselkedését követi. A személyes konvenciók (X01 - Napló, ATTCHMNTS, tantárgy-betűk, AI01-séma) **nem termék-alapértékek**: közönséges beállításokká válnak (napi jegyzet útja, kísérő-mappák, sablonmappa, séma), így a fejlesztő saját vaultja a beállításokkal változatlanul működik. |
| P4 | **Egy app, nem több.** Minden v2-extra modulként benne marad: kártyák (FSRS, `.apkg`), kvíz, összefoglaló, „Ask your vault”, matek CAS-ellenőrzéssel, C++ munkafelület homokozóval, füzetfotó-OCR, videóletöltő + átirat, gráf, Bases, canvas, PDF-olvasó, naptár + emlékeztetők, asszisztens, mentés + visszaállítás. **Funkcióvesztés nincs**, csak modulkapcsoló. |
| P5 | **Telepítés: DMG, beágyazott runtime-mal.** `Manifold.app` a Python-runtime + venv + ffmpeg + felület-build beágyazva; állapot `~/Library/Application Support/Manifold` alatt; a modellek és a C++ eszköztár a Setupból tölthetők le. |
| P6 | **Egyszerű app, Developer móddal.** Alapból technikai zaj nélkül; a fejlesztői infrastruktúra (logok, modellnevek, mérés, diagnosztika, tesztfuttató) a Developer mód mögött marad. |
| P7 | **A mérés (kalibráció) a felhasználó dolga**, de a felületről szakértelem nélkül indítható: AI-letöltő, „Test this model” gomb, haladás, eredmény a küszöbhöz mérve. |
| P8 | Aláírás: első körben **ad-hoc** (a Developer ID + notarizációs út előkészítve, a kiadási ellenőrzőlista kötelezőnek jelöli a nyilvános kiadáshoz). *(Feltételezés — a kérdésre nem érkezett közvetlen válasz.)* |
| P9 | Minden kód az `[UNI] Manifold-OS` repóba kerül; a v2-ből **másolat** készül, a v2 érintetlen. A modellek, a `var/`, a `runtime/`, a stagingek és az aranyhalmazok **nem** kerülnek a repóba. |
| P10 | **Egyszerű használat és megbízható engineering az első.** A felhasználó pontosítása (2026-10-16): a v2 használható, de még nem jobb az Obsidiannál; önmagában a funkciók megtartása nem elég. A napi jegyzetelés, mentés és visszaállás, keresés, navigáció, indulás és beállítások legyenek könnyen érthetők és kiszámíthatók. A fázisok készültségét végigjátszható felhasználói folyamatokkal és a hibás működés elleni regressziós kapukkal kell igazolni. Az AI meglévő képességei megmaradnak; további képességbővítésük a szerkesztő és az alapműködés minősége után következik. |
| P11 | **Automatikus tartalmi nyelvfelismerés.** A felhasználó pontosítása (2026-10-16): a szerkesztő a tényleges szövegből ismerje fel a használt nyelvet, kézi nyelvválasztás nélkül. A kezelőfelület továbbra is angol; az editor helyesírása ettől független, alapból automatikus. A felismerés helyben fut, gépelés után késleltetve, kódot/képletet nem tekint prózának; rövid vagy vegyes nyelvű szövegnél nem erőltet bizonytalan nyelvet. A workspace nyelve a sablonok és a generált tartalom alapértéke lehet, de nem írhatja felül az editor automatikus felismerését. |

---

## 1. Teljes architektúra-térkép (összefoglaló; részletek: audit 02, 03, 04)

### 1.1 Folyamatok és rétegek (ma, v2)

```
Manifold.app (Swift, AppKit + WKWebView)  — ablak, menü, ⌘-billentyűk, EventKit-segéd (--naptar), Kuka (--kuka)
  └─ felület (Svelte 5 + TS, app/dist, 114 .svelte + 260 .ts; CodeMirror 6; pdf.js, KaTeX, Mermaid, JSXGraph)
        │ HTTP JSON + WS, 127.0.0.1, X-Manifold titok
  core (Python 3.14, saját HTTP-szerver; ~140 végpont, 20 WS-esemény; core/ 86 modul)
        ├─ vault-réteg: vaultio (atomi írás) · snapshot (git, külső GIT_DIR) · frame (kör-zár, próbaklón) · gepi_iras (a gép egyetlen írási útja, D9) · atnevezes · elozmeny · index (FTS5 + vektor + PDF-szöveg) · bazis · tulajdonsagok · sablon
        ├─ funkció-réteg: kartya · kviz · osszefoglalas · matek · grafikon · cpp · fuzet · videolanc · kereses · asszisztens · naptar/emlekezteto · felkeszultseg · tracker · mentes · teljes_mentes
        └─ modell-réteg: worker (külön folyamat, MLX, egy modell egyszerre) · router (router.sqlite, kalibrált sorok) · betolto · memóriaőr · eval/kalibracio
  modulok/ (láncok, alfolyamatként): kartya · kviz · osszefoglalas · matek · grafikon · homokozo (sandbox-exec) · cpp · fuzet · ytdlp · kapuk (forráshűség) · eval (aranyhalmazok)
```

### 1.2 Adat- és állapotrétegek (ma → termék)

| Réteg | Ma (v2) | Termék |
|---|---|---|
| **CORE (kód, csak olvasható)** | `{os}` = SSD-mappa: `core/`, `modulok/`, `app/dist`, `bin/mos`, `config/os.toml` | `Manifold.app/Contents/Resources/manifold/…` (kód + runtime + venv + ffmpeg + app/dist + alap-konfig) |
| **INSTALLATION (gépenként egy)** | `{os}/runtime`, `{os}/var/{venv,models,cache}`, `var/router.sqlite`, `state/modell.lock`, `run/worker.*` | `~/Library/Application Support/Manifold/`: `settings.toml` (termék-beállítások), `workspaces.json` (regiszter), `models/` (HF_HOME, megosztott), `router.sqlite` (kalibráció), `run/` (gépszintű modell- és worker-zár), `toolchains/` (LLVM), `logs/` |
| **USER WORKSPACE (vaultonként egy)** | `{os}/var/{vault.git,index,state,tmp,run,runs,*.sqlite,szemelyes}` + `config/vault-sema.json` + `modulok/ytdlp/staging` | `<vault>/.manifold/` (workspace.toml, schema.json; **a vault kötetén**, ezért az atomi csere és az APFS-klón működik) + `<vault>/.manifold/var/` (vault.git, index, state, tmp, run, runs, sqlite-ok, bejövő mappák, staging) — opcionálisan a felhasználó áthelyezheti a kötet egy testvérmappájába („Keep workspace data next to the vault”) |
| **USER (fiók-szintű)** | `var/state/felulet.json`, `kapcsolok.json`, `~/Manifold-backup` | `settings.toml` (megjelenés, modulok, adatvédelem), `felulet.json` workspace-enként; mentés: `~/Library/Application Support/Manifold/backups/<workspace-id>/` (alap) vagy a felhasználó választotta mappa |

A `.manifold/` mappát a pillanatkép kizárja (`[pillanat.vault] kizar`), az index és a bejárók kihagyják (mint a `.obsidian`-t), a `vaultkivul` őr pedig „vaulton kívülinek” tekinti.

---

## 2. Personal-coupling térkép (összefoglaló; részletek: audit 01 és 06)

A kód **abszolút utat nem éget be**; a kötés a konvenciókban él. A 15 legsúlyosabb, rangsorolva:

| # | Kötés | Sors a termékben |
|---|---|---|
| 1 | **Kalibráció a fejlesztő aranyhalmazain**; új telepítésen `router.sqlite` üres → minden AI-funkció 503 | INSTALLATION DATA: szállított aranyhalmazok (`kod`, `kiegeszites`, `matek*`, részben `grafikon`), anonim halmazok a többihez, „saját mérőhalmaz” varázsló; küszöb a kódba; a felhasználó mér |
| 2 | **Egyetlen `os.toml` felhasználói réteg nélkül** | három réteg: szállított alap (`config/os.toml`, read-only) ⊕ `settings.toml` (install) ⊕ `<vault>/.manifold/workspace.toml`; a `config.load` rétegez |
| 3 | **Vault-mappanevek beégetve** (`ATTCHMNTS - …`, `Média`, `_Template`, `X01`, `AI0x`) ~20 core/modul + 6 felületi tükör-konstans | egy forrású workspace-konfig (`companions.cards/quizzes/summaries/photos/videos`, `media_layer`, `templates`, `daily`); a felület a core-tól kapja (`GET /api/workspace`) |
| 4 | **Magyar forráshűség-kapu és hibrid keresés** (5–6 betűs tő, magyar stopszavak, tagadószavak) | nyelvi profil (`hu`, `en`) a kapukban és a keresésben; a küszöbök nyelvenként mérendők |
| 5 | **Frontmatter-séma mint kód** (`Tags/Source/Status/NN/Canvas`) | séma-motor „ki / tanácsadó / szigorú” mód + `null` értékkészlet; alap: szabad séma + 3 kísérő-osztály; a v2-séma importálható |
| 6 | **Diák-munkafolyamat** (tantárgy-betű, `<Betű><NN> - cím` témamappa, Dolgozatok, naptár-kulcsszavak, „magyar középiskolás diák” prompt) | `[subjects]` tábla + `subject_of()` egyetlen függvény (alap: a legfelső mappa neve); a dolgozat/felkészültség és a naptár-szótárak a „Learning” modul beállításai; `ALAP_TAGS` beolvadás megszűnik |
| 7 | **Személyes adat a kódtárban** (`vault-sema.json`, `pillanat-kivetelek-vault.json`, `kotes_modell.json`, `tortenelem-hatralevo.txt`, `tests/adat/c18_1/*ocr_kezi*`) | nem kerül át / semleges alapértékre cserélődik |
| 8 | **Legacy-híd** (`utnorm`, `MOS_LEGACY`, doctor `LEGACY_MINTA`, `tasks` `'legacy'`, `Manifold-media/-fuzet` mappanevek, `tools/mac`) | törlés |
| 9 | **SSD-s hordozható modell** (`work = {os}/..`, `vault = {work}/Manifold`, kötet-lecsatolás a gyökéren, `mentes.kodtar = {os}`, `Manifold.app` a repóban) | installation/workspace gyökér-hármas; a lecsatolás-figyelő a **vault** kötetét figyeli; kódtár-bundle kimarad |
| 10 | **Azonosító és aláírás** (`local.manifold-os.app`, `Manifold Helyi Alairas`) | `com.manifold.app` (reverse-DNS, a végleges domaint a felhasználó adja), ad-hoc → Developer ID út |
| 11 | **Fejlesztői hookok a production binárisban** (`--selftest`, `MOS_PROBA_FELADAT`, `MOS_OSSZEOMLAS`, „PRÓBA —” cím, `bin/mos test|perf|kezi`) | release-buildből build-flag mögé; a CLI fejlesztői parancsai Developer módban maradnak |
| 12 | **Memóriakeretek a 16 GB-os M4-re** (5/9 GB) | RAM-osztály szerinti profil (`hw.memsize`-ből: 8/16/24/32+ GB), felülírható a Settings › AI › Performance alatt |
| 13 | **Felületi nyelvkódok** (`hu-HU`, `Intl.Collator('hu')`, `lang="hu"`) | `locale` beállítás; a tartalmi nyelv a workspace-ből |
| 14 | **Fejlesztői hivatkozások felhasználói szövegben** (`(D9)`, `(L33)`, `K29`, „D13 - CS50”, „AI01 Workflow 2.0 protokoll”) | törlés az angolra fordítással együtt |
| 15 | **Obsidian-vault mint egyetlen forma** (`.obsidian` = „valódi vault”) | marad termék-döntésként; a workspace-létrehozás hozza létre az `.obsidian/`-t (üres `app.json`) és a `.manifold/`-t |

---

## 3. Productization függőségi gráf

```
[A] Repó-bootstrap (másolat, személyes adat nélkül, git init)
 └─► [B] Konfig-rétegezés + gyökér-hármas ({os}/{install}/{workspace}) + bin/mos → Python indító
      ├─► [C] Workspace-absztrakció (.manifold/, workspace.toml, schema mód, companions, subjects, Repo.init, .obsidian létrehozás, workspace-regiszter)
      │     ├─► [D] Angol felület + core hibakódok (t(), en.json, kod+param)
      │     │     ├─► [E] Indító (vault-választó, Swift) + Setup-varázsló (Svelte) + Settings (⌘,) + modulkapcsolók
      │     │     ├─► [F] Model Manager (regiszter-manifeszt, telepítettség, letöltés feladatként, törlés) + Calibration UI (küszöb a kódba, szállított aranyhalmazok, saját halmaz varázsló)
      │     │     └─► [G] Health · Privacy Center · Developer mód · empty state-ek · hiba-UX
      │     └─► [H] Migráció (Obsidian vault → workspace; v2 os.toml/vault-sema → workspace.toml/schema.json; régi Manifold verzió)
      ├─► [I] Demo workspace (generátor, anonim minta-adat, „Try Manifold”, reset)
      └─► [J] Installer (bundle-elrendezés, relokálható venv, hordozható git, RootLocator, DMG, aláírás, frissítés)
                 └─► [K] Tesztszintek (core / fresh-install / migráció / multi-user) → [L] Dokumentáció, demo-folyam, UX-polish → [M] RC
```

---

## 4. Fájlok és modulok, amelyeknek változniuk KELL

| Terület | Fájlok (v2-beli név; az [UNI]-ban ugyanott) | Változás |
|---|---|---|
| Indítás, gyökér | `shell/Sources/RootLocator.swift`, `CoreProcess.swift`, `AppController.swift`, `bin/mos`, `core/config.py`, `core/__main__.py`, `core/server.py` (indulás) | gyökér-hármas, bundle-elrendezés (Resources), workspace-választás a core előtt, env a héjból, `bin/mos` írásainak kivezetése, rétegzett konfig |
| Konfig | `config/os.toml` (alapértékek semlegesítése, SZEMÉLYES szakaszok → workspace), új `config/settings-default.toml`, `config/workspace-default.toml`, `config/schema-default.json`; `config/vault-sema.json` → `presets/` | rétegek, személyes értékek ki |
| Vault-konvenciók | `core/automatika.py`, `core/index/hibrid/hasonlo.py`, `core/{kartya,kviz,osszefoglalas}_api.py`, `core/gepi_iras.py` (mozgat/behoz célmappák), `core/atirat.py`, `core/naplo.py`, `core/sablon.py`, `core/gyakorlas.py`, `core/pdfkiemeles.py` (`ALAP_TAGS`), `core/cpp_teszt.py` (váz), `core/tracker.py` (tantárgy), `core/naptar.py` (szótárak), `core/videolanc.py` (témamappa), `core/felkeszultseg/*`, `core/asszisztens/{beallitasok,emlites,szokas}.py`, `core/higienia.py`, `modulok/{kartya,kviz,osszefoglalas,fuzet,grafikon,ytdlp}/*` (mappanevek, témaminta), `app/src/{kartya,kviz,osszefoglalas}/allando.ts`, `app/src/szerkeszto/tulajdonsagok/*`, `app/src/bazis/kanban.ts` | egy forrású workspace-konfig, `subject_of()`, séma-mód |
| Séma-motor | `core/tulajdonsagok.py` | `mod: ki/tanacsado/szigoru`, `null` értékkészlet, companion-osztályok származtatása |
| Tároló-létrehozás | `core/snapshot.py` (`Repo.init` hívó), új `core/workspace.py` | új vault + `.obsidian` + `.manifold` + `vault.git` + első commit; workspace-regiszter |
| Zárak | `core/modell/zar.py`, `core/modell/worker.py`, `core/modell/kliens.py`, `core/server.py` (core.lock kulcsa) | install-szintű modell/worker-zár; core-zár a vaultra |
| Mentés | `core/mentes.py`, `core/teljes_mentes.py`, `core/visszaallitas.py`, `core/doctor.py` | workspace-azonosítós mentési almappa, cél konfigurálható, kötet-ellenőrzés a vaulthoz mérve, doctor termék-mód |
| Angol felület | `app/src/**` (211 fájl, ~2 600 szöveg), `app/index.html`, `shell/Sources/*.swift` (~308 string), `shell/Info.plist`, `core/**` hibaüzenetek (~190 raise + feladat-szövegek) → `kod` + `param` + angol szöveg | `t()` infrastruktúra, `en.json`, hibaszerződés |
| Új felületek | `app/src/setup/` (varázsló), `app/src/beallitasok/` (Settings ⌘,), `app/src/modellek/` (Model Manager + Calibration), `app/src/egeszseg/` (Health), `app/src/adatvedelem/` (Privacy), `app/src/lib/ui/{Kapcsolo,Mezo,Szegmens,UresAllapot,Haladas}.svelte`, `styles/minta.css` bővítés; Swift: `shell/Sources/Indito.swift` (vault picker ablak) | új |
| Modell-réteg | `config/letoltes.toml` + `os.toml [modellek.*]` → egy `config/models.toml` manifeszt (+ `[feladat.*] cim/leiras`, `[funkcio.*] feladatok`, `nyelvek`, `[kalibracio.*] kuszob/min_tetel`); `core/letoltes.py` (feladatként, `[manifold-progress]`, `megvan` lemezről, törlés, megszakítás), `core/modell/{eval,kalibracio,router,halmaz,revizio,attekintes}.py` (küszöb kikényszerítése, második aranyforrás `{install}/eval-sajat`, nyelv a kulcsban), `modulok/fuzet/modell.py` (409 → NincsModell), `core/modell/api.py` (új `/api/modellek/*`) | Model Manager háttér |
| Doctor → Health | `core/doctor.py` → `core/egeszseg.py` (API: `GET /api/egeszseg`, `POST /api/egeszseg/javit`), lemezhely, modul-állapot | termék-health |
| Tesztek | `tests/helpers.py` (`alg_gyoker(var=False)`, `.obsidian` nélküli állapot, `core_pelda()`), új `tests/vaultgyar.py`, `tests/preset_*` átcsoportosítás, `tests/test_dokumentacio.py` kettéválasztása, `tests/adat/c18_1/*ocr_kezi*` csere, új `tests/fresh_install/`, `tests/multi_user/`, `tests/migracio/` | tesztszintek |
| Build/installer | `shell/build.sh` → `packaging/build_app.py` (bundle-elrendezés, relokálható venv `uv venv --relocatable` / `--target`, hordozható git, codesign/notarize opció, DMG), `packaging/runtime_fetch.py` (a bash runtime fetch portja, D3), `config/runtime-pins.env` (macOS-minimum pontosítása), `shell/Info.plist` (bundle id, verzió, kategória) | új |
| Dokumentáció | új `docs/user/*` (Getting started … Troubleshooting), `docs/dev/*` (ARCHITECTURE, DESIGN, PLOT-FORMATUM átvéve és angolra/termékre igazítva), új `CLAUDE.md` az [UNI]-hoz | új |

## 5. Fájlok és modulok, amelyek NEM változnak (csak másolódnak)

A biztonsági mag és a szerkesztő: `core/tartos.py`, `core/frame.py` (a kör-zár logikája; csak az útvonal-feloldás változik), `core/snapshot.py` (git-műveletek), `core/lepes_kapu.py`, `core/utkapu.py`, `core/vaultkivul.py`, `core/websocket.py`, `core/events.py`, `core/index/{feloldas,maszk,elemzo,linkek,kereses,tar,olvaso,indexelo,figyelo,pdfszoveg,pdf_gyerek}.py` + `pdf_profil.sb`, `core/bazis/*`, `modulok/homokozo/*` (profilok), `modulok/kapuk/*` (csak nyelvi profil kerül köré), `modulok/matek/*`, `modulok/grafikon/*` (csak mappanév), `modulok/cpp/*` (csak hivatkozások), a FSRS-ütemező (`modulok/kartya/utemezo.py`, `apkg.py`), a kvíz-értékelő, a CodeMirror-szerkesztő egésze (`app/src/szerkeszto/**`), Live Preview, Notion-réteg, canvas, Bases-felület, gráf-fizika, PDF-olvasó, lejátszó, design-tokenek (`tokens.css`, `alap.css`, `minta.css`), a tesztek túlnyomó része (~110 konvenció-független fájl + a Bases/index/homokozó/mentés-mag tesztjei). A v2 döntéseinek listája (CLAUDE.md 1–86) hivatkozásként átkerül a `docs/dev/DECISIONS.md`-be.

---

## 6. Migrációs stratégia

| Forrás | Eljárás |
|---|---|
| **Meglévő Obsidian-vault** („Open folder as workspace”) | (1) validálás: olvasási/írási jog, kötet típusa (APFS ajánlott; exFAT/hálózati: figyelmeztetés, csökkentett mód), szabad hely, Markdown-fájlok száma, `.obsidian/app.json` (`attachmentFolderPath`, `newFileLocation`), `templates.json`, `daily-notes.json` **felolvasása** a workspace-beállításokba; (2) **dry-run** jelentés („ezt hozom létre: `.manifold/`, `vault.git`; a vault fájljaihoz nem nyúlok”); (3) `.manifold/workspace.toml` + `var/` létrehozása, `Repo.init()` + első `Mos-Forras: kezi` commit; (4) háttérindexelés (lexikai azonnal, PDF/vektor később, progresszíven); (5) naplózott, visszafordítható: a `.manifold/` törlésével a vault bájtra az eredeti marad. |
| **Meglévő Manifold-OS v2 telepítés** (a fejlesztő esete) | Developer mód › „Import from Manifold-OS v2 folder”: az `os.toml` W-szakaszait (`[naplo]`, `[kartya/kviz/osszefoglalas] mappa`, `[fuzet]`, `[media]`, `[pdf.tags]`, `[asszisztens.*]`) → `workspace.toml`; `vault-sema.json` → `.manifold/schema.json` (mód: szigorú); `var/vault.git`, `*.sqlite`, `state/*.json`, `szemelyes/pos.sqlite` → `.manifold/var/` (másolat, az eredeti érintetlen); `var/models` → a közös modelltár (másolás vagy hivatkozás); `router.sqlite` → install-kalibráció (a szállított aranyverziókkal nem egyező sorok „helyi mérés” jelölést kapnak). Dry-run + napló + visszavonhatóság. |
| **Régi Manifold (termék) verzió** | `workspace.toml` `format` mező; migrációs lépések sorban, mindegyik előtt állapotmásolat (`mentes.migracio_elott` mintája), hiba esetén automatikus visszaállítás az állapotmásolatból. |

A Markdown marad az igazság; a `.manifold/` bármikor törölhető, a vault Obsidianban tovább használható (visszaút).

---

## 7. Installer-stratégia (A opció, részletek: audit 04 §8)

- **Bundle:** `Manifold.app/Contents/Resources/manifold/{bin,core,modulok,config,app/dist,runtime/python,runtime/site-packages (relokálható),runtime/ffmpeg,runtime/git (RUNTIME_PREFIX, forrásból),runtime/node/bin/node (csak a videó-modulhoz)}`. Kód-ujjlenyomat buildkor befagyasztva (`epites.json`). Semmi nem ír a bundle-be.
- **Méret:** mag + AI-alap + keresés + átirat + videó ≈ 1,9 GB kicsomagolva (DMG ~1 GB); modellek (első kör ≈ 15–50 GB, a felhasználó választ) és C++ eszköztár (8,6 GB) a Setupból.
- **Gyökér-feloldás:** `MOS_ROOT` env → `Bundle.main.resourceURL/manifold` → (fejlesztői) az `.app` szülőmappája. App Translocation alatt is működik.
- **Állapot:** `~/Library/Application Support/Manifold/` (install) + `<vault>/.manifold/` (workspace). A doctor/health termék-módban ezeket engedi.
- **Git:** hordozható git a bundle-ben (`NO_GETTEXT NO_TCLTK NO_PERL NO_PYTHON NO_CURL NO_EXPAT NO_OPENSSL`, `RUNTIME_PREFIX=YesPlease`); a `bin/mos` ma is előre teszi a PATH-on. Kapu: a klónos próbák (`apfs_proba`, `szerkeszto_mentes`, `atnevezes_proba`) a hordozható git alatt RENDBEN.
- **Aláírás:** `packaging/sign.sh`: ad-hoc (alap) vagy `MANIFOLD_SIGN_IDENTITY` (Developer ID, `--options runtime --timestamp`, entitlements: `allow-jit` a Node-hoz, `allow-unsigned-executable-memory` a numba-hoz, `disable-library-validation` a Pythonhoz) + `notarytool` + `stapler`. Ad-hoc esetén a dokumentáció a Gatekeeper-utat írja le (Rendszerbeállítások › Adatvédelem és biztonság › Megnyitás mégis).
- **macOS-minimum:** a pinelt wheelek (`mlx_metal … macosx_26_0`) szerint **macOS 26, Apple Silicon**; az Info.plist és a README ehhez igazodik (a 13.0 téves). Intel nem támogatott.
- **Frissítés:** teljes `.app`-csere (v1: kézi letöltés + a Health „Update available” jelzése; Sparkle-appcast a V1.1-ben); minden frissítés előtt: workspace-integritás → állapotmásolat → verzió- és migrációs ellenőrzés → frissítés → utóellenőrzés; migrációs hibánál automatikus visszaállítás.

---

## 8. Tesztstratégia

| Szint | Mi | Futtatás |
|---|---|---|
| **Core** | a v2 ~3 985 Python- és 1 765 vitest-tesztje; a ~40 konvenció-definiáló fájl `tests/preset_ai01/` alá (a „v2-import” profil tesztjei), a ~40–60 fixture-függő fájl a `tests/vaultgyar.py` generátorra paraméterezve; a generikus alapsémához új párok | `bin/mos test`, `bin/mos app test` (unittest + vitest, mint ma); `MOS_SZIGORU=1` |
| **Fresh-install** | tiszta ál-home + bundle-elrendezésű gyökér, `var/` és vault nélkül: Indító → Create workspace → jegyzet → keresés → mentés → visszaállítás; AI nélkül (503-ak helyett termék-üzenetek); modell-letöltés mockolt HF-fel | `tests/fresh_install/`, alfolyamat-alapú `core_pelda()` |
| **Migráció** | szintetikus Obsidian-vault (`vaultgyar(preset="obsidian")`): Import → index → keresés → szerkesztés → AI-mock → backup → restore, dry-run bájt-azonosság | `tests/migracio/` |
| **Multi-user** | 5 profil (Student, Developer, Researcher, Writer, Knowledge worker) külön workspace-szel, párhuzamosan két core: diszjunkt fák, a másik titka 403, a másik vaultjára mutató út elutasítva, közös modelltár + egy modellzár | `tests/multi_user/` |
| **Regresszió-őrök** | token-őr, kontraszt, `i18n` ratchet (nincs új nyers magyar literál), `lepes_kapu` döntéstábla, `test_dokumentacio` két része (fejlesztői / felhasználói) | CI (macOS-runner) |
| **Kézi kapuk** | klónos próbák a hordozható git alatt; a valódi appos kör (Kézi kör 2 mintájára) a kiadás előtt | `bin/mos kapu` (Developer mód) |

---

## 9. Kockázati regiszter

| # | Kockázat | Súly | Kezelés |
|---|---|---|---|
| R1 | **AI nélkül indul az új telepítés** (nincs kalibrált modell) — a termék AI-fele üresnek tűnik | magas | szállított aranyhalmazok + egyszerű „Test this model” + világos üzenetek („needs a local model”); a felhasználó mér; a szállított kalibráció V1.1-ben |
| R2 | **Küszöb nélküli kalibráció**: egy gyenge modell élesen futna | magas | `[kalibracio.<f>] kuszob, min_tetel` kódban kikényszerítve; a saját halmaz jelölt |
| R3 | **Kötet-feltétel**: `var/` és vault egy APFS-köteten | magas | workspace-var a vault kötetén (`<vault>/.manifold/var`); nem-APFS vault → figyelmeztetés + csökkentett mód (próbaklón nélkül) |
| R4 | **Angolra fordítás** (~2 600 felületi + ~500 core + ~300 Swift szöveg) regressziót hoz | közepes | `t()` kulcs = a mai magyar szöveg (a tesztek változatlanok maradnak), ratchet-teszt, a core `kod+param` fallbackkel |
| R5 | **Hordozható git** aláírása/relokációja | közepes | `RUNTIME_PREFIX`, klónos kapuk; tartalék: CLT-detektálás + útmutató |
| R6 | **Notarizáció** több ezer `.so`-n | közepes | a v1 ad-hoc; a signing-szkript előkészítve; a lista a kiadási ellenőrzőlistán |
| R7 | **Magyar nyelvi profil marad az egyetlen mért** — angol tartalomhoz a promptok és kapuk mérés nélkül „próba” | közepes | D9 védi; az angol halmazok és a mérés a felhasználó/közösség feladata; a felület kimondja |
| R8 | **Többworkspace + egy worker**: a worker az első core konfigjából indul | közepes | install-szintű worker, kérésenként workspace-azonosító; v1: egyszerre egy nyitott workspace (mint az Obsidian több ablaka, de egy core-ral), a második workspace új core-folyamat + gépszintű modellzár |
| R9 | **Személyes adat kiszivárgása** a repóban (audit-dokumentumok, fixture-ök) | magas | a `docs/plan/audit/*` belső anyag: a nyilvános repóból kizárva (`.gitattributes export-ignore` + a kiadás előtti ellenőrző lista); a fixture-ök cseréje az 1. fázisban |
| R10 | **macOS 26 minimum** szűkíti a célközönséget | közepes | elfogadva v1-re (a pin-váltás újramérést igényelne); V1.1: régebbi wheel-pin kísérlet |
| R11 | **A Developer-infrastruktúra elrejtése közben funkció sérül** (feature freeze szelleme) | közepes | semmit nem törlünk, csak kapcsolunk; a teljes tesztkészlet minden fázis után |
| R12 | **Feature-freeze ütközés** (79. döntés) | alacsony | ez a terv a felhasználó kifejezett döntése (CLAUDE.md-kivétel), a NAPLO-ba kerül |
| R13 | **Éles láncok az eval-modulokból veszik a promptot** (a füzetlánc a `modulok/eval/ocr_kezi/feladat.py`-t importálja, amely importkor az aranyhalmazt töltötte) — friss telepítésen minden fotó hibát adott | magas (F1-ben toleráns betöltővel kezelve) | F6: a promptok és a pontozók kerüljenek az eval-adattól független modulba; az aranyhalmaz csak a méréshez töltődjön |

A termékesítés **módosítja** a v2 döntéseit: 6. (telepítés nélkül), 79(d) (home alá nem írunk), a doctor `/Applications` és Application Support tiltása, 2.2 „var a vault kötetén” (marad, de a vault alatt), `local.manifold-os.app`. Minden más döntés marad.

---

## 10. Fázisterv (végrehajtási sorrend, agent-kiosztással)

Minden fázis végén: tesztek futnak, a változott fájlok és a maradék kockázatok a fázis-jelentésben (a `docs/plan/NAPLO.md`-ben), a következő fázis csak a jelentés után indul.

| Fázis | Tartalom | Agent(ek) / modell | Kapu |
|---|---|---|---|
| **F1 Bootstrap** | másolat a v2-ből személyes adat, modellek, `var/`, `runtime/`, staging, aranyhalmaz-adatok, `tests/kezi`, `tools/mac`, dev-docs nélkül; `git init`; új `CLAUDE.md`, README, `.gitignore`; a „ki van zárva” lista a `docs/plan/F1-masolat.md`-ben | koordinátor (Bash) + 1 ellenőrző agent (sonnet): személyes-adat-szkennelés az [UNI]-n | `grep` tiszta a 7. kötésre; a repó commitolva |
| **F2 Személyes kötések** | legacy-híd törlése; fejlesztői hivatkozások (`(D9)`, `K29`…) ki a felhasználói szövegekből; `ALAP_TAGS`, `TEMAMAPPA_MINTA`, `KISERO_ELOTAG` → konfig; `tests/adat` csere; selftest release-flag mögé; bundle id | 3 agent párhuzamosan (sonnet: core+modulok; sonnet: app; opus: shell+doctor) | `bin/mos test` + `app test` zöld |
| **F3 Konfig + workspace** | gyökér-hármas, rétegzett `config.load`, `bin/mos` → `bin/mos.py`, `core/workspace.py` (létrehozás, regiszter, `Repo.init`, `.obsidian`), séma-mód, `subject_of()`, companions egy forrásból, install-szintű zárak, mentés workspace-azonosítóval, doctor termék-mód | 2 agent (opus: core config/workspace/zárak; sonnet: konvenció-helyek átírása a workspace-konfigra) + tesztek | tesztek zöld; `fresh_install` alapteszt (workspace létrehozás) zöld |
| **F4 Angol felület** | `lib/i18n` (`t()`, `en.json`), parancsregiszter, értesítések, hibaszerződés (`kod`+`param`) a core-ban, Swift `.lproj`, ratchet-teszt; a magyar szövegek kulcsként maradnak | 4 agent (sonnet ×3 a felület mappáira; opus a core-hibaszerződésre) | vitest zöld; ratchet 0 új; a felület angolul fut |
| **F5 Indító + Setup + Settings** | Swift vault-választó ablak (Create / Open / Try demo, recent), Svelte Setup-varázsló (Welcome → Workspace → Language → Experience preset → AI (opcionális) → Privacy), Settings (⌘,) Obsidian-struktúrával, modulkapcsolók, közös UI-minták (`m-kapcsolo`, `m-mezo`, `UresAllapot`) | 3 agent (opus: Swift indító + core workspace-API; opus: Settings; sonnet: Setup-varázsló + UI-minták) | fresh-install végigjátszható |
| **F6 Model Manager + mérés** | `config/models.toml` manifeszt, `/api/modellek/*`, letöltés feladatként progress-szel és megszakítással, telepítettség lemezről, törlés, `[kalibracio.*]` küszöb, „Test this model” (előpróba → mérés → jel), szállított aranyhalmazok (`kod`, `kiegeszites`, `matek*`), saját-halmaz varázsló, nyelv-mező, hibaszerződés az AI-funkciókban, füzetlánc 409-javítás | 3 agent (opus: modell-háttér; sonnet: Model Manager UI; sonnet: aranyhalmaz-csomagolás + eval-illesztés) | mockolt HF-letöltés teszt; mérés-folyam teszt ál-modellel |
| **F7 Health, Privacy, Developer** | `core/egeszseg.py` + Health oldal (Diagnose/Fix/Learn more), Privacy Center (hálózat, modellek, tárolt adat, AI-memória, tracker, integrációk, engedélyek), Developer mód kapcsoló + a technikai nézetek mögé, hiba-UX („What happened / Fix / [Fix automatically] [Open diagnostics]”), empty state-ek CTA-val | 2 agent (sonnet, sonnet) | UX-audit: nincs fejlesztői szó normál módban |
| **F8 Migráció + demo + doku** | Obsidian-import dry-run/napló/visszafordítás; v2-import (Developer mód); demo workspace generátor (50–100 anonim jegyzet, PDF, kód, matek, kártyák, kvíz, források, gráf, naptár-példák, AI-memóriák), „Try Manifold”, reset; beépített dokumentáció (16 oldal) a demo workspace-ben is | 3 agent (opus: migráció; sonnet: demo-generátor; sonnet: doku) | migrációs teszt zöld; demo 7 folyam reprodukálható |
| **F9 Installer + tesztszintek + RC** | `packaging/` (bundle, relokálható venv, hordozható git, DMG, sign/notarize opció, `runtime_fetch.py`), RootLocator, `epites.json` befagyasztás; fresh-install / multi-user / migráció tesztszintek; biztonsági + mentés/visszaállítás audit; UX-polish; `v1.0.0-rc1` | 3 agent (opus: packaging; opus: tesztszintek; sonnet: polish) | a 32. pont auditjai; DoD-lista |

| **F10 Többnyelvű kód-munkafelület** | a C++ munkafelület általánosítása nyelvi profilokra (`modulok/kod` + nyelvi adapterek): homokozott fordítás/futtatás, tesztblokkok, sorhoz kötött diagnosztika, az öt AI-mód nyelv-paraméterrel és saját kalibrációval; v1: C/C++ (LLVM), Python és JavaScript/TypeScript (a beágyazott runtime-ból), letölthető/rendszer-eszközlánc: Java, Go, Rust, Swift; a `.cpp` jegyzetek változatlanul működnek. A részletes terv: `docs/plan/parity/CODE-WORKBENCH.md` (tervezői panel + bírálat eredménye) | 3 agent (opus: nyelvi profil-réteg + homokozó; sonnet: adapterek + tesztek; sonnet: UI) | minden v1 nyelvre: fordít/fut/tesztel homokozóban, AI-módok kalibrálatlan modellnél „próba” |
| **F11 Szerkesztő-paritás az Obsidiannal** | az Obsidian-paritás audit (`docs/plan/parity/`, 14 alrendszer, cáfolással ellenőrzött hiánylista) „must” és „should” tételeinek megvalósítása, a kritikus top-25 sorrendjében; minden tétel egy ellenőrzőlista-sor, teszttel | 4–6 agent alrendszerenként (opus a szerkesztő-magra: élő nézet, linkek, tulajdonságok; sonnet a többire) | a „must” lista 100 %, a „should” ≥ 80 %, a meglévő Manifold-erősségek sértetlenek (regressziós kapu) |

A F6 mérési része **a felhasználó feladata** (valódi modellekkel, tétlen gépen); a kód csak a folyamatot teszi egyszerűvé. Az F10 és az F11 az F5 után, az F6-tal párhuzamosan is futhat (diszjunkt fájlok).

**P10 szerinti prioritás (2026-10-16):** az elkezdett F4 lezárása után F5, majd F11 napi szerkesztési és navigációs hiányai következnek. A kiadáshoz szükséges F6 modelltelepítés és mérési biztonság továbbra is a terv része; új AI-képesség nem előzi meg az editor minőségi kapuit. A fázisok számozása és tartalma megmarad, a függőségi sorrend ennek megfelelően F5 után a szerkesztőre összpontosít.

---

## 11. Termék-felépítés (Obsidian-struktúra leképezése)

**Indító ablak** (Swift, core nélkül): „Create new workspace” · „Open folder as workspace” · „Try the demo workspace” · recent list · alul: Appearance (System/Light/Dark), Developer mode (rejtett: ⌥-kattintás). A választás után indul a core a workspace-szel (`MOS_VAULT`, `MOS_WORKSPACE`, `MOS_INSTALL` env).

**Setup-varázsló** (első workspace-nél, később Settings › General › „Run setup again”): Welcome (local-first, Markdown, AI inside, no lock-in) → Workspace (létrehozás/megnyitás + validálás) → Language of your notes (hu/en…: átirat-modell ajánlás, dátum, sablonok) → Choose experience (Student / Knowledge worker / Developer / Research / Custom = modulkapcsolók) → AI (opcionális: „Install recommended models now” → Model Manager; „Continue without AI”) → Privacy (tracker, assistant, system notifications, calendar access: mind kapcsoló, alapból a v2 10. döntése szerint be, de itt látható) → Done.

**Settings (⌘,)**, oldalsáv:
- *Options:* General (content language, startup workspace, updates, run setup again) · Editor (live preview, readable line length, spellcheck, tab size, slash menu, vim: nincs) · Files & links (new note location, attachment folder, trash, link format, excluded files, templates folder, daily notes folder/format) · Appearance (theme, base font size, quiet mode, accent: burgundy fix) · Hotkeys (a parancsregiszterből) · Modules (= core plugins: Backlinks, Outline, Properties, Quick switcher, Search, Slash commands, Tags, Templates, Daily notes, Canvas, Bases, Graph, PDF reader, Media player, Cards, Quiz, Summaries, Math, Code workbench, Notebook photos, Video & transcripts, Ask your vault, Assistant, Calendar & Reminders, Readiness, Tracker)
- *AI:* Models (Model Manager) · Calibration (model tests, gold sets) · Memory (what Manifold learned, törölhető) · Assistant · Performance (RAM profile)
- *Learning:* Cards (FSRS) · Quiz · Readiness (exam notes, subjects)
- *Backup:* Snapshots · Local backup · External backup · Restore
- *Privacy:* Network · Telemetry · Data · Integrations · Permissions
- *Developer:* Logs · Diagnostics · Sandbox · Model details · Test runner · Git
- *About:* MANIFOLD · Local Knowledge OS · version · build · licensing (Community / Pro réteg: a v1-ben minden Community; a Pro-kapu absztrakció csak a `settings.toml` `license` mezője és egy `is_pro()` függvény, feature-gating nélkül) · Advanced information (expandable).

**Parancspaletta (⌘P)** marad a központi navigáció; minden Settings-sor egy parancs.

---

## 12. Definition of Done (33. pont) — mérőlista a RC előtt

1. telepít (DMG) · 2. elindít · 3. workspace-t hoz létre · 4. megérti a fő működést (Welcome + doku) · 5. Obsidian-vaultot importál · 6. jegyzetet ír · 7. keres · 8. AI-t használ (modell letöltése + teszt + egy funkció) · 9. kártya/kvíz · 10. PDF · 11. matek-ellenőrzés · 12. C++ homokozó · 13. mentés · 14. visszaállítás · 15. fejlesztői segítség nélkül. Minden pont egy `tests/fresh_install/` vagy kézi kapu-tétel.

---

## 13. Nyitott kérdések a felhasználónak (nem blokkolók; feltételezéssel haladunk)

| Kérdés | Feltételezés |
|---|---|
| Bundle id / domain (`com.manifold.app`?) | `com.manifold.app` ideiglenesen |
| Licenc a repóra (nyílt forrás? melyik? vagy zárt) | nincs LICENSE fájl, amíg nincs döntés; a README „All rights reserved” |
| Developer ID | nincs; ad-hoc |
| Community vs Pro: mely funkciók fizetősek | v1: minden elérhető; a licensing-réteg csak absztrakció |
| A v2 `docs/` naplói: kell-e belőlük valami a termék-repóba | csak ARCHITECTURE, DESIGN, PLOT-FORMATUM, LEGACY-SZERZODESEK (dev-referencia), a többi nem |
