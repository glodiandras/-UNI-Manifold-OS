# 04 — Héj, build-lánc, runtime és installer-stratégia (READ-ONLY audit)

Forrás: `/Volumes/Work/Manifold-OS v2` (2026-10-15). Semmi nem módosult, a `bin/mos`, a `build.sh` nem futott; a `runtime/` és a `var/`
csak `ls`/`du -sh` szinten. Hivatkozás: `fájl:sor` (gyökér-relatív). Becslés jelölve: „~” / „becslés”.

---

## 0. Vezetői összefoglaló (a döntéshez legfontosabb tények)

1. **A héj és a core „gyökér = az `.app` szülőmappája” modellre épül** (`shell/Sources/RootLocator.swift:3-18`), a core-t a
   `{gyökér}/bin/mos core start` indítja (`CoreProcess.swift:55-57`), és a `bin/mos` a saját helyéhez képest **ír** (`var/tmp`,
   `var/cache`, `.metadata_never_index`, `bin/mos:35-54`). Egy `/Applications`-be másolt, aláírt (írásvédett pecsétű) bundle ezzel
   így nem működik; a szükséges módosítás azonban kicsi, mert **minden `[utak]` kulcs `MOS_<KULCS>`-csal, a teljes konfiguráció
   `MOS_CONFIG`-gal felülírható** (`core/config.py:3-4, 51-53, 73-74`) — a fő akadály a `bin/mos`, amely a `var/` utakat
   beégetve a `$MOS_HOME/var` alá teszi (nem a `MOS_VAR`-ból).
2. **Szabály-ütközés**: a mai rögzített döntések és a doctor kifejezetten tiltják a célmodellt — 6. döntés „telepítés nélkül”
   (`CLAUDE.md:19`), 79(d) „home alá csak a mentés és a prefs-plist” (`CLAUDE.md:92`), a doctor `SAJAT_MINTA` a `/Applications/Manifold`-ot
   (`core/doctor.py:24`), a `HOME_NEM_ENGEDETT` a `Library/Application Support`-ot jelzi (`core/doctor.py:369-370`), és a 79(a)
   feature freeze új funkciót nem enged. Az installer **új felhasználói döntést** igényel.
3. **„torch csak a dots_mocr-hoz” — NEM igaz.** A lock szerint a torch-ot a `sentence-transformers` (a hibrid keresés alapértelmezett
   bge_m3 + bge_reranker_v2_m3 párja, `config/os.toml:146-160, 552-558, 702-708`) és az `mlx-whisper` is húzza; csak a `torchvision`
   (6 MB) dots_mocr-specifikus (`config/requirements.in:15`). A torch (543 MB a venvben) a vektorkeresés-modullal együtt mozdítható.
4. **macOS-minimum ellentmondás**: `LSMinimumSystemVersion 13.0` (`shell/Info.plist:15`), `-target arm64-apple-macos13.0`
   (`shell/build.sh:30`), README „macOS 13” — de a pinelt `mlx_metal-0.32.2` wheel platformcímkéje **`macosx_26_0_arm64`**, a torch/numpy/scipy
   `macosx_14_0` (`runtime/wheels` fájlnevek). Az AI-réteg valós minimuma tehát a wheel-címkék szerint macOS 26.
5. **Friss gépen a `models pull` nem tudja letölteni a keresés beágyazóját**: a `valasztas()` a statikus `megvan = true` jelzőt
   szűri (név szerinti kérésnél is) (`core/letoltes.py:65`), és öt modell így jelölt (qwen35_9b, gemma4_12b, qwen3_vl_4b,
   whisper_turbo_mlx, **bge_m3**; `config/letoltes.toml`). Egy Setup-hoz a „megvan” a lemezről (`core/modell/revizio.py:29-61`) kell.
6. **Új vaulthoz nincs tároló-létrehozó parancs** (README 2.2; `docs/KIADAS.md:10`), pedig a `snapshot.Repo.init()` megvan
   (`core/snapshot.py:202-232`) — a Setup első lépése ezt pótolná.
7. **Aláírás**: ma önaláírt helyi tanúsítvány (`Authority=Manifold Helyi Alairas`, `TeamIdentifier=not set`), **hardened runtime nincs**
   (`CodeDirectory flags=0x0(none)`), entitlements-fájl nincs, `--timestamp=none` (`shell/build.sh:25, 38`). Disztribúcióhoz Developer ID +
   hardened runtime + notarizáció kell minden Mach-O-ra (a venv több ezer `.so`-jára is).

---

## 1. A héj (`shell/Sources/*.swift`)

### 1.1 Fájlonként

- **`App.swift`** (27 sor) — belépési pont (`@main`). Három mód: `--kuka` → `Kuka.futtat()` (`App.swift:7`); `--naptar <parancs>` →
  `Naptar.futtat()` NSApplication nélkül (`:9-11`); különben GUI, `--selftest[=<forgatókönyv>]`-vel (`kilepes, core-halal, core-ujraindul,
  kezfogas-ido, szerkesztes, lecsatolas`, `:15-21`) `.accessory` aktivációval (`:24`). Ugyanaz a bináris a GUI és két CLI-segéd
  (a core gyermekfolyamatként hívja: `core/naptar_seged.py:46-48`, `core/csatolmany.py:289-328`).

- **`RootLocator.swift`** (20 sor) — a gyökér: (1) `MOS_ROOT`, (2) `Bundle.main.bundleURL.deletingLastPathComponent()` — **az `.app`
  szülőmappája** (`:14-18`). Érvényes, ha van futtatható `bin/mos` és `config/os.toml` (`:8-12`). Nincs mentett beállítás, nincs
  telepítési hely (szándékosan, `:3-4`). Hibánál: „A Manifold.app-nak a Manifold-OS mappájában kell lennie … Az SSD nincs csatlakoztatva?”
  (`AppController.swift:91-93`).

- **`CoreProcess.swift`** (177 sor) — a core gyermekfolyamata.
  - **Melyik Python**: a héj nem választ; a `{root}/bin/mos core start`-ot futtatja (`:55-56`), `cwd = root` (`:57`); a `bin/mos` sorrendje
    `$MOS_PYTHON` → `var/venv/bin/python` → (munkafa-fő venv) → `runtime/python/bin/python3`, rendszer-Python soha (`bin/mos:58-64`).
  - **Env**: a héj teljes környezete öröklődik + `MOS_ROOT`, opcionálisan `MOS_CORE_PORT`, `MOS_API_TITOK` (`:58-62`). Finderből
    indítva a PATH minimális (`/usr/bin:/bin:…`) → a git a `/usr/bin/git` (CLT-shim; CLT nélkül telepítő-párbeszédet dob — termékkockázat).
  - **Stdin-kézfogás**: a core első stdout-sora JSON: `{"port":N,"pid":P,"titok":"…"}` → siker; `{"foglalt":true,…}` vagy 75-ös kilépés →
    másik példány fut ugyanazon a vaulton (`:114-123`, `:21-22`; core oldalon `core/server.py:3, 14, 78`). Az első sor után a stdout eldobva
    (`:102`); a stderr utolsó 8000 karaktere megmarad (`:31-32, 77-81`). Időkorlát: `MOS_KEZFOGAS_MP` (0,1–600 s, alap 25 s;
    `Eletciklus.swift:42, 133-136`), lejáratkor „Várok / Kilépés” (`AppController.swift:420-447`).
  - **Leállás**: a stdin lezárása = rendezett leállás a futó feladat végén (`:169-173`); második kérés `process.terminate()` (`:176`).
  - **API-titok**: a core sorsolja (`core/server.py:117-126`, 16–128 kar., `[A-Za-z0-9_.-]`), a héj a lapba `atDocumentStart` user-scriptként
    injektálja `window.__MOS_TITOK__`-ként, csak a főkeretbe (`Eletciklus.swift:141-146`, `AppController.swift:160-166`); újraindításkor
    ugyanazt a portot és titkot adja vissza (`AppController.swift:643-651`), hogy a lap és a mentetlen szöveg megmaradjon.
  - **Kötet-érintés**: `gyokertErint()` — a lecsatolt mount-pont a gyökér vagy fölötte van-e (`:127-132`).

- **`Eletciklus.swift`** (250 sor) — tiszta döntésfüggvények táblázatos selftesttel: a kilépés előtti mentés jelentésének értelmezése
  (`window.manifold.mentes()` → `{ok, mentetlen}`; a hiányzó válasz NEM „rendben”, `:7-19, 54-66`), a kilépési kérdés (`:68-88`), a
  core-halál szövege (`:109-131`), a kézfogás-idő, a titok-JS, a WebContent-halál (3 halál/60 s után feladja, `:158-163`), a navigációs
  hiba (`:170-175`).
  **Életciklus a vezérlőben**: ⌘Q → a felület ment (35 s korlát, `AppController.swift:535, 540-573`), mentetlen/hibás/nincs válasz →
  „Vissza a szerkesztéshez / Kilépés mentés nélkül”, majd `requestStop()` (stdin-zárás); a core a futó tétel végén áll le és a belső
  lemezre ment (`core/mentes.py:10-13`); második ⌘Q: SIGTERM (`:544`). **Kötet-lecsatolás**: `NSWorkspace.willUnmountNotification`
  (`:97-98`) → ha a gyökér kötetét érinti, `NSApp.terminate` a fenti mentési úton (`:398-402`); a valódi kihúzás nem értesít (K03).
  Core-halál futás közben: stderr-farok + mentetlen lista + „Újraindítás (régi porton) / másolás / Kilépés” (`:600-651`).

- **`Biztonsag.swift`** (54 sor) — (1) navigáció csak a core **pontos** originjére (séma+gazda+port, user/jelszó nélkül; `:9-13`),
  `decidePolicyFor`-ban `about:` is (`AppController.swift:450-455`); (2) külső cím csak `http/https/mailto` (`:16-24`) az alapértelmezett
  appban. **CSP**: nem a héjban, hanem a core fejlécében — `X-Frame-Options: SAMEORIGIN` + `Content-Security-Policy: frame-ancestors
  'self'` minden válaszon (`core/utvonalak.py:24-33`), SVG-re `sandbox; default-src 'none'` (`core/media.py:102`). WebKit-tár:
  `.nonPersistent()` (`AppController.swift:74`), ATS: csak `NSAllowsLocalNetworking` (`Info.plist:21-22`).

- **`Naptar.swift`** (688 sor) — `Manifold --naptar <allapot|kerd|olvas|emlekeztetok|emlekezteto-ir|esemeny-ir>` (`:326-336`), stdin JSON
  → egy stdout JSON, mindig 0-s kód (`:5-10`); nincs ablak, hálózat, fájlírás. EventKit-engedély: `allapot` csak lekérdez, `kerd` kér
  (`:291-311, 352-370`); írás csak jóváhagyott kéréssel (`NaptarLogika.jovahagyott`, `:91`). A GUI-folyamatban a felület is kérhet
  engedélyt (`naptar-engedely` üzenet, `AppController.swift:4-8, 299-302`). A usage-szövegek `Info.plist:25-33`. A core oldalán:
  `[utak] naptar_seged` és `hej_cli` = `{os}/Manifold.app/Contents/MacOS/Manifold` (`config/os.toml:47-48`), felülírható
  `MOS_NAPTAR_SEGED`/`MOS_HEJ_CLI`.

- **`Kuka.swift`** (106 sor) — `Manifold --kuka`: stdin `{"ut","gyoker"}` → `FileManager.trashItem` (`:9-29`); csak vaulton belüli elem,
  nem `/`, home, kötet-gyökér, maga a vault, nincs `..`, a szülő linkjei feloldva is a gyökér alatt (`:3-7, 80-105`).

- **`Ertesites.swift`** (145 sor) — `UNUserNotificationCenter`; csak csomagból futva él (`bundleURL.pathExtension == "app"` és van
  bundle id, `:98-99`); engedély az első értesítés előtt (`:105-119`), kattintás → `window.manifold.ertesitesKattintas(azon)` (`:49`).

- **`HelyiMenu.swift`** (112 sor) — a natív WebKit-helyi menü végére fűzött Manifold-parancsok; a felület listája korlátozott, egyszer
  használatos, rövid életű (`:4-11`), a választás `window.manifold.parancs(id)`-ként fut (`:49`).

- **`SelftestSzkript.swift`** (72 sor) — a `--selftest=szerkesztes` JS-törzse (`callAsyncJavaScript`), CodeMirror-gépelés mérése.

- **`AppController.swift`** (818 sor) — az ablak, a WKWebView, a menü, a fenti kötések; `UserDefaults` `NSQuitAlwaysKeepsWindows=false`
  (`:61-65`) — a home alá csak `~/Library/Preferences/local.manifold-os.app.plist` kerül (doctor „home írások”). Selftest: minden tiszta
  táblázat (`:67-69`), majd a valódi core és lap; keret 40/90 s (`:99-103`).

### 1.2 A kódtár-gyökérhez kötő feltételezések (`{os}/Manifold.app`)

| # | Feltételezés | Hol | Önálló bundle-ben |
|---|---|---|---|
| H1 | gyökér = `.app` szülője; ott `bin/mos` + `config/os.toml` | `RootLocator.swift:17` | új jelölt: `Bundle.main.resourceURL/<os>` (és App Translocation alatt is működik) |
| H2 | a core-t a `{root}/bin/mos` bash indítja, `cwd = root` | `CoreProcess.swift:55-57` | maradhat, de a `bin/mos` írásait ki kell vezetni |
| H3 | a `bin/mos` a `$MOS_HOME/var` alá ír (HF_HOME, XDG, UV/PIP cache, TMPDIR, mkdir, Spotlight-jelölő), és ott keresi a venvet | `bin/mos:35-46, 52-54, 60` | a `MOS_VAR`-t nem veszi figyelembe → módosítás kell (pl. `VAR="${MOS_VAR:-$MOS_HOME/var}"`) |
| H4 | `[utak]` relatív a `{os}`-hoz: `work = {os}/..`, `vault = {work}/Manifold`, `var = {os}/var`, `archive = {os}/archive`, `modulok`, `ytdlp = {modulok}/ytdlp` (benne a 55 GB-os `staging` és az `archive`), `app_dist = {os}/app/dist` | `config/os.toml:11-15, 24-28, 44, 52` | `MOS_CONFIG` → egy `~/Library/Application Support/Manifold/os.toml`, vagy `MOS_VAULT/MOS_VAR/MOS_ARCHIVE/MOS_YTDLP…` env; az `app_dist`, `modulok` kódja maradhat a Resources alatt, **az ytdlp munkafája nem** (állapot a kódfában) |
| H5 | a naptár/Kuka-segéd útja `{os}/Manifold.app/Contents/MacOS/Manifold` | `config/os.toml:47-48` | a héj adja át: `MOS_NAPTAR_SEGED`/`MOS_HEJ_CLI` = `Bundle.main.executablePath` |
| H6 | a lecsatolás-figyelő a **gyökér** kötetét figyeli | `AppController.swift:97-98, 398-402` | a **vault** (és a `var`) kötetét kell figyelni |
| H7 | `{tmp}` a vault kötetén (atomi `os.replace`, APFS-klón `cp -c`) | `config/os.toml:20`; `core/frame.py:273-278`; doctor „kötet” `core/doctor.py:739-744` | ha a vault külső/iCloud, a `var` pedig az Application Supportban: a tmp/próbaklón-helyet a vault kötetére kell tenni, vagy a vault a belső lemezre kötendő |
| H8 | a build-frissesség a `{root}/Manifold.app/Contents/Resources/epites.json`-t és a forrásokat veti össze; a futó core a `core`+`modulok` ujjlenyomatát git-tel vagy bejárással számolja | `core/epites.py:97-132, 32-65` | bundle-ben az ujjlenyomat a buildkor rögzítendő (nincs `.git`, ne járjon be minden induláskor) |
| H9 | szövegek: „SSD”, „Manifold-OS mappája” | `AppController.swift:92`; `Info.plist:23-24` | termék-szöveg |
| H10 | a doctor/policy tiltja a `/Applications/Manifold`-ot és az `~/Library/Application Support`-ot | `core/doctor.py:24, 367-370`; `CLAUDE.md:19, 92` | „termék-mód” a doctorban + új döntés |
| H11 | a kódtár-bundle a `{os}/.git`-ből (mentés és teljes mentés) | `core/mentes.py:134-139`; `core/teljes_mentes.py:398-407` | bundle-ben nincs `.git` → automatikusan kimarad (a kód nem igényli) |
| H12 | a `vault.git/config` `core.worktree` abszolút út | `core/snapshot.py:221-224` | a vault áthelyezésekor újra kell írni (a Setup „vault helye” lépése) |

**Mi kell egy `/Applications`-be másolható bundle-hez** (csak tények, nem döntés):
- `Contents/Resources/os/` (vagy hasonló): `bin/`, `core/`, `modulok/` (az ytdlp `staging/archive` nélkül), `config/`, `app/dist/`,
  `runtime/python/` (75 MB), a venv tartalma (lásd 3.), `runtime/ffmpeg/` (47 MB), opcionálisan `runtime/node/bin/node` (116 MB).
- A venv **nem relokálható** alapból (a `pyvenv.cfg home=` és a shebangek abszolút utak; a doctor is ezt ellenőrzi, `core/doctor.py:765-781`);
  bundle-ben vagy `uv venv --relocatable`, vagy a csomagok közvetlenül a hordozható Python `site-packages`-ébe / egy `PYTHONPATH`-os
  könyvtárba (`uv pip install --target`), a `bin/mos` pedig a Pythont közvetlenül hívja.
- Állapot: `~/Library/Application Support/Manifold/{var,state,models,…}` → `MOS_CONFIG`/`MOS_*` env a héjból (`CoreProcess.init`-ben).
- Semmi nem írhat a bundle-be (a pecsét sérülne): `PYTHONDONTWRITEBYTECODE=1` már van (`bin/mos:38`), de `core/__pycache__` létezik a
  kódtárban — a build előtt ki kell zárni.

---

## 2. Build-lánc

### 2.1 `shell/build.sh` (46 sor)

| Lépés | Sor |
|---|---|
| `TMPDIR`, clang/swift module-cache a `var/` alatt | `:16-17` |
| aláíró identitás: `MOS_ALAIRAS_IDENTITAS` (különben ad-hoc `-`); létezés-ellenőrzés `security find-identity -p codesigning` | `:18-24` |
| önaláírtnál `--timestamp=none` (hálózat nélkül) | `:25` |
| `xcrun --find swiftc` (Command Line Tools kell) | `:28` |
| `bin/mos epites --swift > EpitesAzonosito.swift` — **a héj buildjéhez a Python-runtime/venv kell** | `:29` |
| `xcrun swiftc -O -swift-version 5 -parse-as-library -target arm64-apple-macos13.0 -module-cache-path …` (csak arm64, nincs universal, nincs Xcode-projekt) | `:30-31` |
| `Info.plist` statikus másolat | `:32` |
| `AppIcon.icns` másolat (a generálás külön, kézi: `shell/ikon/keszit.sh` + `rasztero.swift`) | `:33-36` |
| `bin/mos epites > Contents/Resources/epites.json` | `:37` |
| `codesign --force --deep --sign "$IDENTITAS"` — **nincs `--options runtime`, nincs `--entitlements`, nincs secure timestamp** | `:38` |
| `codesign --verify --deep --strict` | `:39` |
| a kész `.app` a kódtár gyökerébe (`$MOS_HOME/Manifold.app`), a repo követi a binárist | `:3, 15, 45` |

**`Info.plist`** (`shell/Info.plist`): bundle id `local.manifold-os.app` (`:10`), verzió `0.0.1`/`1` statikus (`:12-13`), `LSMinimumSystemVersion
13.0` (`:15`), `NSSupportsAutomaticTermination/SuddenTermination = false` (`:18-19`), ATS local networking (`:21-22`), usage-szövegek:
eltávolítható kötet, Naptár (full + régi), Emlékeztetők (full + régi) (`:23-33`). Nincs `LSApplicationCategoryType`, nincs
`NSHumanReadableCopyright`, nincs Sparkle-kulcs.

**A mai `Manifold.app`** (`codesign -dvv`): `Identifier=local.manifold-os.app`, `Authority=Manifold Helyi Alairas`, `TeamIdentifier=not set`,
`CodeDirectory … flags=0x0(none)` (hardened runtime nincs), 672 KB; `Resources/epites.json` = `{"verzio":1,"felulet":"91aa…","mag":"3355…",
"hej":"7a6f…"}`.

### 2.2 `bin/mos app build` (vite)

`bin/mos:223-250`: `PATH` elejére a `runtime/node/bin`, npm-cache a `var/cache/npm` alatt; `install` alapból `npm ci --offline --ignore-scripts`,
`--online` egyszer (`:228-236`), utána az `@napi-rs/canvas*` törlése (`:237-243`); `build` = `npm run check` (svelte-check `--fail-on-warnings`)
+ `vite build` (`:245-246`; `app/package.json:7-12`). A vite-plugin a buildazonosítót a `../bin/mos epites` hívással kapja
(`app/vite.config.ts:11-25`), és `dist/epites.json`-t + `<meta name="manifold-epites">`-t ír → a felület buildjéhez is kell a Python-runtime.

### 2.3 `core/epites.py` (148 sor)

- Három rész: `felulet` (app forrásai), `mag` (`core`, `modulok`), `hej` (`shell/Sources`, `Info.plist`, `build.sh`) (`:18-23`).
- Ujjlenyomat: a git által látott fájlok (`git ls-files -z --cached --others --exclude-standard`), git nélkül bejárás a
  `KIHAGY_MAPPAK` nélkül, 64 MB fölött csak méret (`:32-94`).
- Elavultság: `allapot()` a lemezen álló `app/dist/epites.json` és `Manifold.app/Contents/Resources/epites.json` részét a forráshoz veti; a
  futó core és lap azonosítója opcionális (`:101-132`); API: `GET /api/rendszer/epites` (`:135-142`); a héj a saját azonosítóját
  `window.__manifoldHejEpites`-ként injektálja (`:145-148`, `AppController.swift:169`).
- Termék-szempont: a „forráshoz mért frissesség” fejlesztői fogalom; termékben a build-azonosító + verzió elég, az ujjlenyomatot buildkor kell befagyasztani.

### 2.4 Ami ma kézi, a fejlesztő gépéhez kötött

| Elem | Hol | Megjegyzés |
|---|---|---|
| Xcode Command Line Tools (`swiftc`, `xcrun`, `codesign`, `security`, **rendszer-git**, SDK) | `shell/build.sh:28`; README 1. fejezet; `core/doctor.py:860` | a rendszer-git futásidőben is függőség |
| Önaláírt tanúsítvány `Manifold Helyi Alairas` a login kulcskarikában, „Always Trust” | `docs/KIADAS.md:63-80` | csak ezen a gépen ad stabil TCC-identitást |
| Ikon raszterezése | `shell/ikon/keszit.sh` | kézi |
| `bin/mos runtime fetch` (online), `app install --online`, `models pull` | `bin/mos:148-164, 234, 208-214` | D3: kifejezett igen |
| macOS SDK másolat a C++-hoz (`xcrun --show-sdk-path`) | `modulok/cpp/telepites.py:106-113, 254-285` | CLT kell |
| GitHub-feltöltés GitHub Desktopból (terminál-push 403) | `docs/MAC-FUTTATO.md:5`; `tools/mac/_kozos.sh:15-21` | `tools/mac/*` csak fejlesztői folyamat (push/fetch/ff-merge, `hash-object/mktree/commit-tree/update-ref`), termékben nincs szerepük |
| A kész `Manifold.app` a repóba commitolva | `shell/build.sh:3` | disztribúcióhoz build-artefakt kell |
| Megjegyzés: a `core/naptar_seged.py:46` a „`bin/mos shell build`” parancsot ajánlja, ilyen alparancs nincs a `bin/mos`-ban (`bin/mos:190-291`) | | apró doksi-hiba |

---

## 3. Runtime-méret és -tartalom

### 3.1 Mért méretek (`du -sh`)

| Út | Méret | Kell-e a termékben |
|---|---|---|
| `runtime/python` | 75 MB | **kötelező** (python-build-standalone 3.14.7, relokálható) |
| `var/venv` | 1,4 GB | részben (lásd 3.2) |
| `runtime/ffmpeg` | 47 MB | átirat (mlx-whisper betöltő, `core/modell/hatter.py:235`) + videólánc |
| `runtime/node` | 199 MB (ebből `bin/node` 116 MB) | csak a yt-dlp JS-kihívás (`config/os.toml:38`; `modulok/ytdlp/src/msp/downloader.py:236-245`) és a felület buildje → futásidőben **csak a videó-modulhoz** |
| `runtime/uv` + `uvx` | 35 MB + 0,3 MB | csak telepítéshez (B opcióban kell) |
| `runtime/wheels` | 387 MB (81 wheel) | csak offline venv-építéshez |
| `runtime/dl` | 982 MB (benne az LLVM archívum 873 MB) | letöltési gyorsítótár, termékben nem |
| `runtime/llvm` | 7,6 GB | C++ munkafelület (opcionális modul) |
| `runtime/sdk` | 964 MB | C++ (a gépről másolva, CLT kell) |
| `app/dist` | 16 MB | **kötelező** |
| `app/node_modules` | 472 MB | csak build |
| `core` | 2,3 MB; `modulok` (staging nélkül) ~5 MB | **kötelező** |
| `modulok/ytdlp/staging` | 55 GB | felhasználói állapot a kódfában (!) |
| `var/models/hub` | 87 GB (33 repó) | modell-letöltés |
| `var/cache` | 2,4 GB (uv 1,4 G, pip 391 M, npm 362 M, clang 235 M) | fejlesztői gyorsítótár |
| `Manifold.app` | 672 KB | kötelező |

### 3.2 A venv csomagjai méret szerint (`site-packages`, `du -sk`) és a használójuk

A „Ki húzza” oszlop a `config/requirements.lock` `# via` soraiból; a „Kódbeli import” a `core/` + `modulok/` (tesztek és staging nélkül) grepje.

| Csomag | Méret | Ki húzza (lock) | Kódbeli import | Lánc / modul-jelölt |
|---|---|---|---|---|
| torch (+torchgen 2,5, sympy* 42, networkx 8) | 543 MB | `.in`, **mlx-whisper, sentence-transformers**, torchvision | `core/modell/hatter.py:213` (csak `mps.empty_cache`) | vektorkeresés + rerank (bge_m3, bge_reranker; `config/os.toml:552-558, 702-708`), dots_mocr (torchvision) — **nem csak dots_mocr** |
| mlx (+mlx-metal) | 202 MB | `.in` | `hatter.py:30-47, 102, 153, 277` | minden helyi AI (alap AI-modul) |
| llvmlite + numba | 124 + 13 MB | mlx-whisper (és `.in`) | nincs | átirat (mlx-whisper) |
| cv2 (opencv-python) | 119 MB | `.in`, **mlx-vlm** | **nincs közvetlen import** | mlx-vlm tranzitív (kép/videó-előfeldolgozás) — nem a füzetlánc |
| scipy | 70 MB | `.in`, mlx-audio, mlx-whisper, scikit-learn, sentence-transformers | `modulok/fuzet/kep.py:95` (`ndimage`) | füzetlánc + átirat + keresés |
| pymupdf | 58 MB | `.in` | `core/index/pdf_gyerek.py` | **alap** (PDF-szöveg az indexben) |
| transformers | 52 MB | `.in`, mlx-lm, mlx-vlm, mlx-audio, sentence-transformers | `core/modell/beallitas.py`, `hatter.py` | alap AI |
| sympy | 42 MB | torch | `modulok/matek/*`, `modulok/grafikon/*`, `modulok/homokozo/*` | matek/grafikon (modell nélküli CAS) → ha a torch kimarad, a sympy-t közvetlenül kell kérni |
| scikit-learn | 31 MB | sentence-transformers | nincs | keresés |
| numpy | 24 MB | — | `core/index/hibrid/vektortar.py`, `fuzet/kep.py` … | alap |
| mlx_vlm | 14 MB | `.in` | `hatter.py:103-114` | alap AI (OCR, szöveg, kép) |
| PIL | 13 MB | `.in` | `core/kepek.py`, `fuzet/kep.py` | **alap** (kép-előnézet) |
| yt_dlp (+yt-dlp-ejs) | 12 MB | `.in` | `modulok/ytdlp/src/msp/downloader.py:428-477` | videólánc |
| tokenizers, safetensors, huggingface_hub, hf_xet | 9 + 1 + 5 + 7,5 MB | `.in` | `core/letoltes.py`, `hatter.py:327` | alap AI + letöltő |
| mlx_audio | 9 MB | **mlx-vlm** | nincs (a `mlx-audio` háttér „később”, `hatter.py:309`) | tranzitív |
| llguidance | 8 MB | mlx-vlm | nincs | tranzitív |
| torchvision | 6 MB | `.in` | nincs | dots_mocr (`requirements.in:15`) |
| fastapi, uvicorn, starlette, pydantic(-core) | ~8 MB | `.in`, mlx-vlm | **nincs** (a core saját http-szervere) | mlx-vlm szerver-tranzitív |
| pypdf | 1,7 MB | `.in` | **nincs** | kiesésre jelölt |
| tiktoken | 2,9 MB | `.in`, mlx-whisper | nincs | átirat |
| sentence-transformers | 2,9 MB | `.in` | `hatter.py:203-206` | keresés |
| mlx-lm, mlx-whisper | 1,8 + 1,7 MB | `.in` | `hatter.py` | alap AI / átirat |
| fsrs | kicsi | `.in` | `modulok/kartya/utemezo.py`, `core/felkeszultseg/adat.py` | kártya (alap) |
| pytest (+pluggy, iniconfig, _pytest 1,4 MB) | ~2 MB | `.in` | — | **fejlesztői**, termékből ki |
| sounddevice, miniaudio | ~2 MB | mlx-audio | — | tranzitív |

Wheel-méretek (tömörített, letöltési méret): torch 121 MB, mlx_metal 61 MB, opencv 46 MB, llvmlite 39 MB, pymupdf 23 MB, scipy 20 MB,
transformers 12 MB, scikit-learn 8 MB, sympy 6 MB, numpy 5 MB, pillow 5 MB, hf_xet 4 MB, yt_dlp 3 MB; összesen 387 MB.

### 3.3 Modul-bontás (becslés, kicsomagolt méret; döntés nélkül)

| Modul | Tartalom | ~Méret |
|---|---|---|
| **Mag (kötelező)** | héj 0,7 MB, kód ~10 MB, `app/dist` 16 MB, Python 75 MB, pymupdf 58, numpy 24, PIL 13, sympy 42, fsrs, certifi, pyyaml … | **~250 MB** |
| AI-alap | mlx 202, transformers 52, mlx-vlm/mlx-lm 16, tokenizers/safetensors/hf_hub/hf_xet 23, + mlx-vlm tranzitívek (opencv 119, mlx-audio 9, llguidance 8, fastapi/uvicorn ~8, scipy 70) | ~500 MB (opencv nélkül, ha `--no-deps`-szel/`opencv-python-headless`-szel megoldható: ~380 MB — ellenőrizendő) |
| Keresés (vektor + rerank) | sentence-transformers, **torch 543** (+sympy már a magban), scikit-learn 31, scipy | ~600 MB + modellek (bge_m3 2,3 GB, bge_reranker 2,29 GB) |
| Átirat | mlx-whisper, numba+llvmlite 137, tiktoken 3, ffmpeg 47 (+ a lock szerint torch) | ~190 MB (+torch, ha a függőség nem kerülhető meg) + whisper modell (1,61–6,18 GB) |
| Videólánc | yt-dlp 12, node 116 (csak a bináris), ffmpeg (közös) | ~130 MB |
| dots_mocr | torchvision 6 MB (+torch) + modell 3,54 GB | |
| C++ | LLVM 7,6 GB + SDK 964 MB | ~8,6 GB |
| Fejlesztői (termékből ki) | uv, wheels, node_modules, npm, pytest, `var/cache` | |

Modellek (`config/letoltes.toml`, `meret_gb` összege): teljes lista **103,4 GB** (31 modell); `kor = "elso"` **51,7 GB**; `megvan = true` 19,8 GB
(nem letölthető a mai kóddal, lásd 4.3). A lemezen ma 87 GB.

### 3.4 Platform-címkék

`mlx_metal-0.32.2-py3-none-macosx_26_0_arm64.whl`, `torch-2.14.0-cp314-cp314-macosx_14_0_arm64.whl`, `scipy/numpy … macosx_14_0`, `opencv … macosx_13_0`
→ a pinelt AI-réteg macOS 26-ot feltételez, a héj és a README 13-at. Az installer minimum-verzióját ehhez kell igazítani, vagy az AI-modult
OS-verzióhoz kötni.

---

## 4. Hálózati lépések

### 4.1 Minden hely, ahol internet van

| # | Hol | Mit tölt | Pin / ellenőrzés |
|---|---|---|---|
| N1 | `bin/mos runtime fetch` → `letolt()` `curl -fsSL --retry 2` (`bin/mos:71-88, 153-155`) | uv, Python, Node (`config/runtime-pins.env:2-10`) | sha256 a pin-fájlból; `.resz` név, hibánál törlés (`:77-85`); kibontás után `--version` ellenőrzés (`:91-117`); a régi a `runtime/regi/` alá (`:98-104`) |
| N2 | `bin/mos:160-161` `pip download --no-deps --only-binary=:all: --require-hashes -r config/requirements.lock` | 81 wheel PyPI-ról | a lock sha256-jai (`config/requirements.lock`) |
| N3 | `ffmpeg_telepit` (`bin/mos:131-146`) | imageio-ffmpeg wheel (PyPI) | a wheel ÉS a kicsomagolt bináris sha256-ja (`runtime-pins.env:16-20`) |
| N4 | `bin/mos app install --online` → `npm ci --ignore-scripts` (`bin/mos:228-236`) | npm-csomagok | `package-lock.json` integrity (sha512) |
| N5 | `bin/mos models pull` / `letoltes` → `core/letoltes.py` `huggingface_hub.snapshot_download` (`:79-108`) | HF-repók a `{models}/hub` alá | **`revizio` commit-pin** (`:88-94`): a letöltött pillanatkép-mappa neve = a rögzített sha, különben hiba; `refs/main` eltérés csak figyelmeztetés (`:95-98`); a `minta` (allow_patterns) szűkít. HF_HUB_OFFLINE=0 csak ennél a parancsnál (`bin/mos:207, 211`), egyébként 1 (`bin/mos:36-37`) |
| N6 | videólánc: `modulok/ytdlp/src/msp/downloader.py:428-477` (YoutubeDL), `crawl.py:95-100` (urllib bejárás); a core feladatként indítja (`core/videolanc.py:159-170, 194`) | videók | nincs pin (tartalom); hálózat-őr: `modulok/ytdlp/halozat_orzo.py` (`core/videolanc.py:15`); node a JS-kihíváshoz |
| N7 | `bin/mos cpp telepit` → `modulok/cpp/telepites.py:51-55` `curl -fL --retry 3 -C - -#` | LLVM 23.1.2 (873 MB) | bájt-szám + sha256 (`config/cpp-pins.env:4-8`; `telepites.py:172-179`); az SDK nem letöltés, hanem `xcrun` másolat |
| — | `core/modell/kliens.py:82-85`, `core/gepi_kliens.py:80-83`, `core/kereses_modell.py:136-139` | csak 127.0.0.1 (worker, core) | nem internet |

TLS: `SSL_CERT_FILE=/etc/ssl/cert.pem` (`bin/mos:47`).

### 4.2 Programból hívható felület (Setup háttér-szolgáltatáshoz)

| Funkció | Programból hívható? | Folyamat-jelzés | Megszakítás |
|---|---|---|---|
| Modell-letöltés | igen: `jeloltek_betoltese(ut)`, `valasztas(modellek, kerdes)`, `lista_szoveg()`, `letolt(modellek, nevek, cache_dir, naplo, letolto=None, token=None) → {név: 'kész'\|hiba}` (`core/letoltes.py:44-108`); a `main()` interaktív, de a `bemenet`/`jelszokero` injektálható (`:120`) | csak modellenkénti `print("[i/N] …")` (`:87`) és a HF tqdm a stderr-en; **nincs `[manifold-progress] N%`** sor, amit a feladatsor értene (`core/tasks.py:8, 44`); a `letolto` paraméter becsomagolható (a `snapshot_download` `tqdm_class`-t fogad) | `KeyboardInterrupt` → napló + újradobás (`:100-103`); a feladatsor azonnali leállítása SIGTERM a folyamatcsoportnak (`core/tasks.py:448-480`) — a HF a `.incomplete` fájlokból folytat; a helyellenőrzés (`:146-151`) csak a `main()`-ben |
| „Megvan-e” állapot | igen: `core/modell/revizio.py:29-61` (`van_pillanatkep`, `ellenoriz`) | — | — |
| Runtime fetch/install | **nem** (bash-függvények a `bin/mos`-ban) | nincs (`curl -fsSL` néma) | csak folyamat-ölés; az atomi `.resz`/`.uj` lépések miatt biztonságos |
| C++ telepítő | igen: `modulok/cpp/telepites.py:125-285` `Telepito(cfg, letolto=, pinek=, sdk_forras=, kiir=)`; `lista()`, `llvm(igen)`, `sdk()` | `kiir` visszahívás; a `curl -#` sávja a terminálra | `-C -` folytatható `.part` |
| Videó-letöltés | feladatként (`video_letoltes`, `core/videolanc.py:32`) | a lépés-protokoll | feladat-stop |
| Feladatsor (keret) | `TaskType` + `register()` (`core/tasks.py:100-123`), `submit()`, `stop(fid, immediate)` (`:420-480`) | `[manifold-progress] <szám>%` sor (`:44`), WS-esemény | kulturált (stop-fájl) vagy azonnali |

Javasolt minta (tényként: ilyen már van): a `mentes` és a `teljes_mentes` is `TaskType` (`core/tasks.py:125-147`); egy `modell_letoltes`
TaskType ugyanígy `python -m core.letoltes --igen <nevek>` lépést futtathatna, ha a letöltő `[manifold-progress]` sorokat írna.

### 4.3 Akadályok a Setup előtt

- **`megvan` statikus jelző**: `valasztas()` a `megvan = true` modelleket név szerinti kérésnél is kiszűri (`core/letoltes.py:65`) → friss gépen
  a bge_m3 (alapértelmezett vektorkereső) és négy másik modell nem tölthető le.
- `letoltes.toml` és `os.toml` kettős modelllista (`[modell.*]` vs `[modellek.*]`) — a Setup egyetlen katalógust igényelne.
- Az `mlx-embeddings` futtatót az `os.toml` két modellhez használja (`config/os.toml:776, 784`), de nincs a lockban és nincs háttér hozzá
  (`core/modell/hatter.py:305-309`).
- A HF-token csak `getpass`-szal, memóriában (`core/letoltes.py:159-164`) — UI-ban a Keychain lenne a hely.

---

## 5. Git-függőség

### 5.1 A hívott git-parancsok (futásidő)

Környezet: `hermetikus_env()` — `GIT_*` törölve, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_ATTR_NOSYSTEM=1`,
`GIT_TERMINAL_PROMPT=0`, `LC_ALL=C` (`core/snapshot.py:123-133`); a `Repo._env` ehhez `GIT_DIR`, `GIT_WORK_TREE`, szerző,
`GIT_LITERAL_PATHSPECS=1` (`:153-167`); minden hívás `git -c core.quotepath=false …` (`:169-185`), 120 s / bundle 1800 s időkorlát (`:138-139`).
Kivétel: a `git init --bare` (`:210`) és a `frame.py:287, 290` `config` hívása **nem** hermetikus környezetben fut.

| Parancs | Hol |
|---|---|
| `init --bare -q` | `core/snapshot.py:210` |
| `config` (core.ignorecase, core.bare, core.worktree, core.precomposeunicode, core.autocrlf, core.quotepath, commit.gpgsign, user.*; `--get`) | `core/snapshot.py:219-230, 280-281`; `core/frame.py:287, 290`; `core/mentes.py:129`; `core/teljes_mentes.py:560` |
| `add` (útlistával) | `core/snapshot.py:261` |
| `status --porcelain=v1` | `core/snapshot.py:290, 296`; `core/mentes.py:99` |
| `diff --cached` / `--quiet` / `--binary` | `core/snapshot.py:316, 468, 496, 539, 635-636, 753` |
| `ls-files --cached` | `core/snapshot.py:318`; `core/epites.py:42-43` (`-z --others --exclude-standard`, fejlesztői) |
| `commit -q` | `core/snapshot.py:320, 469, 541` |
| `rev-parse --verify` / `HEAD` / `--show-toplevel` | `core/snapshot.py:284, 321, 549, 689, 750`; `core/mentes.py:115, 153, 167`; `core/visszaallitas.py:118, 137`; `core/teljes_mentes.py:405`; `core/epites.py:38` |
| `log` (`-z`, `-1`, `--follow`, `--no-walk=unsorted`) | `core/snapshot.py:354, 381, 402, 627, 690, 715` |
| `show` (`-s`, `--name-only`, `--name-status`, `--numstat`, `<sha>:<út>`) | `core/snapshot.py:434, 441, 448, 504, 669, 736`; `core/elozmeny.py:140` |
| `cat-file -e` | `core/elozmeny.py:64`; `core/visszaallitas.py:147, 152` |
| `update-index --force-remove` / `-q --refresh` | `core/snapshot.py:430, 476`; `core/visszaallitas.py:160` |
| `reset -q` (csak index, nem `--hard`) | `core/snapshot.py:467` |
| `apply --index` / `-R` / `--numstat` (a visszavonás magja: revert patch-csel) | `core/snapshot.py:531, 536, 558, 568, 573, 633-634` |
| `bundle create` (`--all`) / `list-heads` / `verify` | `core/snapshot.py:767`; `core/mentes.py:121, 161, 172`; `core/teljes_mentes.py:400`; `core/visszaallitas.py:115` |
| `for-each-ref` | `core/mentes.py:151` |
| `clone --bare`, `fsck --connectivity-only`, `remote remove`, `ls-tree`, `read-tree` | `core/visszaallitas.py:114, 116, 117, 76, 159` |
| `--version`, kódtár-lekérdezések (kapu) | `core/doctor.py:534, 856` |
| `rev-parse --git-common-dir` (munkafa-mód) | `bin/mos:27` |
| (fejlesztői) push/fetch/merge --ff-only/branch/hash-object/mktree/commit-tree/update-ref | `tools/mac/01_feltoltes.sh`, `03_kapuk.sh:56-59`, `04_main_frissites.sh` |

Hordozható git ma: a `bin/mos:48-50` a `runtime/git/bin/git`-et a PATH elejére teszi, ha létezik; a doctor „git függőség” sora kimondja, melyik
fut (`core/doctor.py:420-429`). A KIADAS 6. fejezete két opciót ír: A = rendszer-git (CLT), B = forrásból építve `NO_GETTEXT NO_TCLTK NO_PERL
NO_PYTHON NO_CURL NO_EXPAT NO_OPENSSL` (`docs/KIADAS.md:82-93`).

### 5.2 Kockázatok (döntés nélkül)

- **Rendszer-git (CLT)**: termékgépen nem feltételezhető; a `/usr/bin/git` CLT nélkül egy shim, amely a „parancssori fejlesztőeszközök
  telepítése” párbeszédet dobja — a core első commitjánál a felhasználó elé kerül. Az Apple git verziója is változik az OS-sel.
- **Bundle-be csomagolt git**: kell `RUNTIME_PREFIX=YesPlease` (különben a prefix beégetett, az `.app` mozgatásakor a `libexec/git-core`
  helperek nem találhatók); minden helper-bináris (git-core alatt több tucat) Developer ID + hardened runtime aláírást igényel; a sablon-
  könyvtár (`templates`) és a `GIT_EXEC_PATH` kezelése; méret becslés szerint néhányszor tíz MB. A használt parancsok (5.1) mind helyiek,
  a felsorolt NO_* kapcsolók mellett elérhetők (a `apply`, `bundle`, `fsck`, `clone` helyi bundle-ből curl nélkül megy).
- **Pure-Python (dulwich)**: a magas kockázatú pontok: a `git apply --index/-R` (bináris diff-fel; a visszavonás alapja) — dulwichban
  nincs egyenértékű; `log --follow` (átnevezés-követés); `status`/`diff` a `core.precomposeunicode`/`core.ignorecase` szemantikájával
  (NFD a macOS-en); `bundle create/verify/list-heads` és `fsck --connectivity-only` támogatottsága ellenőrizendő; ~40 hívási hely és a
  klónos kapuk (`apfs_proba`, `szerkeszto_mentes`, `atnevezes_proba`) erre a viselkedésre vannak hangolva. A `git apply` kiváltása
  átírást jelent, nem csere.
- A `vault.git` formátuma (bare + `core.worktree`) bármelyik úttal kompatibilis marad.

---

## 6. `doctor` → Manifold Health

A `core/doctor.py:729-928` `ellenoriz(cfg, environment, home, futo_python) → list[Eredmeny]` programból hívható, de **nincs API-útja**
(csak `python -m core doctor`, `core/__main__.py:24-26`), és lassú alfolyamatokat futtat (`codesign`, `uv pip freeze`, `git`). Lemezhely-
ellenőrzés a doctorban **nincs**; a szabad hely a `/api/vezerlo/rendszer` `_ssd()`-jében (`core/vezerlo.py:127-136`) és a letöltőben van.

| Tétel | Függvény / sor | Osztály |
|---|---|---|
| gyökér | `:737-738` | fejlesztői (bundle-ben triviális) |
| kötet (var és vault ugyanazon a köteten) | `:739-744` | **termék** (atomi csere, klón) |
| var symlink (munkafa) | `:746-757` | fejlesztői |
| vault, vault .gitattributes, vault ideiglenes fájlok | `_vault` `:153-182` | **termék** |
| pillanatkép-tárolók állapota (vault.git, ytdlp.git, index.lock) | `_tarolok_allapota` `:184-215`; `:862-864` | **termék** |
| tárolt bináris a HEAD-ben; pillanatkép kód (ytdlp) | `_tarolt_binaris` `:217-245` | termék (karbantartás) |
| python (pyvenv.cfg, shebangek, futó Python az SSD-n) | `:759-790` | fejlesztői |
| ~/Applications, ~/.cache; régi appok | `:792-825` | fejlesztői / policy (bundle-ben ütközik, H10) |
| legacy var/ | `:827-847` | fejlesztői (átállási) |
| vault-séma | `_sema_ellenor` `:65-89`, `:850-851` | termék |
| git, git függőség | `:852-861`, `_git_fuggoseg` `:420-429` | termék (megléte) / fejlesztői (honnan) |
| offline (HF_HUB_OFFLINE) | `:866-868` | fejlesztői |
| runtime (uv, Python, Node) | `:870-876` | fejlesztői (termékben: a bundle integritása) |
| lock (venv = requirements.lock) | `:877-890` | fejlesztői |
| runtime verzió (pin) | `_runtime_verziok` `:307-333` | fejlesztői |
| requirements.in a lockban | `_kovetelmenyek` `:335-354` | fejlesztői |
| ffmpeg (pin, tiltott hely, sha256) | `_video_ffmpeg` `:247-274` | termék (modul-health); a „home alatti út tiltott” szabály (`:255-258`) B opcióban ütközik |
| modell-revízió, kalibráció-pillanatkép | `_modell_reviziok` `:611-645` | **termék** (modellek) |
| Manifold.app aláírása érvényes; aláírás fajtája | `:897-902`; `_alairas` `:405-418` | termék (integritás) / fejlesztői (stabil helyi tanúsítvány) |
| naptár-segéd, naptár-engedély | `_naptar` `:647-662` | **termék** |
| home írások | `_home_irasok` `:373-392` | policy (célmodellben átírandó) |
| @napi-rs/canvas | `_napi_canvas` `:276-290` | fejlesztői |
| Spotlight (`var/.metadata_never_index`) | `_never_index` `:356-371` | termék |
| build-felulet / build-hej (forrással egyező) | `:904-916` | fejlesztői |
| mentés, mentés (kódtár), mentés (állapot), mentés hiba | `_mentes` `:106-151` | **termék** (a kódtár-sor fejlesztői) |
| index, index (félretett) | `_index` `:576-609` | **termék** |
| kapu (klónos kézi próbák) | `_kapu` `:541-574` | fejlesztői |
| C++ eszköztár / linker / SDK | `_cpp` `:690-727` | modul-health |
| próbaklónok | `_proba_klonok` `:465-511` | termék (karbantartás) |
| core fut | `_core_fut` `:432-450` | termék |
| összeomlás-horog | `:923-926` | fejlesztői |

Health-oldal alapja (termék): vault, kötet, tárolók, vault-séma, mentés(ek), teljes mentés (`core/teljes_mentes.py:576-584`, `/api/mentes/teljes`),
index, modellek (revízió + megvan), naptár, Spotlight, core, git megléte, **+ hiányzó: szabad lemezhely, modul-állapot (melyik modul telepítve)**.
Részben már API-n van: `/api/vezerlo/rendszer` (memória, modellzár, SSD, utolsó mentés; `core/vezerlo.py:6, 158-170, 219`).

---

## 7. Mentés / visszaállítás

### 7.1 `core/mentes.py` (belső, `{backup}`)

- **Bemenet**: `cfg`; `ment(cfg, csak_ha_valtozott=False, log=…, hibak=None, …)` (`:415-421`); triggerek: core rendezett leállása, gépi kör
  vége, 30 percenkénti időzítő, `mentes` feladat (`core/tasks.py:125-130`), második ⌘Q 1 s-os kerettel (`:10-13`).
- **Formátum** a `{backup}` alatt: `<tár>-<idő>.bundle` (vault, ytdlp: `git bundle`), `mos-kodtar-<idő>.bundle` (csak ha `{os}/.git` van,
  `:134-139, 165-181`), `mos-allapot-<idő>/` (SQLite-ok `VACUUM INTO`, `{state}` JSON/JSONL, füzet- és videóállapot; változatlan fájl hard
  linkkel az előzőből, `:186-377`), `mos-migracio-<fájl>-v<N>-<idő>.sqlite` (`:384-410`); megtartás `[mentes].megtartott_bundle`,
  `allapot_megtartott`, `allapot_napi`, `megtartott_migracio`. Frissesség: `git bundle list-heads` (`:111-125`); hibák: `{state}/mentes-hiba.json`.
- **Fix hely**: `config/os.toml:53` `backup = "{home}/Manifold-backup"`; felülírható `MOS_BACKUP` (`core/config.py:53`; a munkafa-mód is
  ezt használja: `bin/mos:26`) és `MOS_CONFIG`. A fix helyet feltételező szövegek: `core/doctor.py:373-392` („home írások” kivétel),
  `core/visszaallitas.py:5`, `docs/KIADAS.md:9, 100, 127`, README 2.2, `CLAUDE.md:19, 92`.
- **Termék-szempont**: a belső mentés célja az „SSD-hiba elleni védelem”; ha az állapot is a belső lemezen él, ugyanazon a lemezen
  ugyanaz a hibatartomány → a célt át kell értelmezni (helyi verziótár) vagy külső/Time Machine-célra konfigurálni (a kulcs már
  konfigurálható, a UI és a policy-szöveg nem).

### 7.2 `core/teljes_mentes.py` (külső, inkrementális)

- **Bemenet**: `ment(cfg, cel, proba=False, log=print)` (`:329`); a cél létező mappa **külön köteten** (`:332-340`; próba kivételével);
  feladatként `teljes_mentes` a `cel` paraméterrel (`core/tasks.py:133-147`); opcionális `LemezFigyelo` (`[teljes_mentes] figyelo_be`, `cel`,
  `figyelo_ora`; `:587-…`).
- **Források**: `{os}` + az `EXTRAK` kulcsok közül a gyökéren kívüliek (`:41-44, 83-91`) — a bundle-modellben a kód a Resources-ban
  maradna, az állapot-kulcsok (vault, var, state, …) külön gyökérként kerülnek be: a mechanizmus ezt már kezeli.
- **Formátum** (`FORMATUM = 2`): `<cel>/Manifold-ÉÉÉÉHHNN-ÓÓPPMM-ffffff/` (készítés közben `.resz`, a `kesz` jelölő az utolsó írás), benne
  `adat/<kulcs>/…`, `jegyzek.json` + `jegyzek.sha256`, `kodtar.bundle` (ha `.git` van), `aktiv-os.toml` (`:1-17, 398-436`); változatlan fájl
  hard linkkel (`:261-270`); kimarad: models, venv, runtime, index, staging, archive (`KIHAGYOTT`, `:45-…`, `[teljes_mentes] kihagy`).
- **Visszaállítás** csak üres célba, és a gyökereket **`Manifold-OS` és `Manifold` testvérmappákként** írja vissza (`:490-506`) — az SSD-elrendezéshez
  kötött; a termékben a célt (kód nem kell, állapot → Application Support, vault → választott hely) kulcsonként kellene leképezni.
- Állapot: `{state}/teljes-mentes.json`, `GET /api/mentes/teljes` (`:576-584, 649-650`).

### 7.3 `core/visszaallitas.py`

- `bin/mos visszaallit <bundle> [--tar vault|ytdlp] [--igen]` → `visszaallit(cfg, bundle, tar, log) → dict` (`:87-168`).
- Előfeltétel: a core nem fut (`{run}/core.lock`), a `{vault_git}` hiányzik vagy üres (`:8-9, 42-64`); `clone --bare` ideiglenes testvérbe,
  `bundle verify`, `fsck`, `remote remove`, `Repo.init`, a HEAD fájából csak a hiányzó fájlok íródnak ki (`kizaro_ir`), majd `read-tree` +
  `update-index --refresh` (`:10-18, 114-160`). A munkafa csak akkor jön létre, ha a szülője létezik (`:12-13`).
- Hiányzik: új, üres vault + tároló létrehozása (README 2.2) — a Setupnak ez kell; a `Repo.init()` (`core/snapshot.py:202-232`) a mag.

### 7.4 A cél konfigurálhatóvá tétele (tények)

A belső mentés célja ma is egy `[utak]` kulcs (`backup`), a külsőé egy `[teljes_mentes] cel` beállítás + feladat-paraméter. Hiányzik: (1) egy
írható, felhasználói beállítás-réteg (a `config/os.toml` a kódtár része; bundle-ben írásvédett — `MOS_CONFIG` egy Application Support-beli
felülíró fájlra mutathatna, de a `config.load` egyetlen fájlt olvas, rétegzést nem: `core/config.py:71-74`); (2) a doctor/policy-szövegek
átírása; (3) a teljes visszaállítás kulcs-alapú leképezése.

---

## 8. Installer-opciók

Közös tények mindhárom opcióhoz:
- **Developer ID + notarizáció** nélkül egy letöltött (karanténos) `.app`-ot a Gatekeeper blokkol (macOS 15+ alatt a jobb-klikk-Megnyitás
  kerülő is megszűnt, csak a Rendszerbeállításokból engedhető). Notarizációhoz: Apple Developer Program, „Developer ID Application”
  tanúsítvány, **hardened runtime minden Mach-O-n** (`codesign --options runtime --timestamp`), `notarytool submit` + `stapler staple` a DMG-re.
- Valószínűleg szükséges entitlements (ellenőrizendő): Node (V8 JIT) `com.apple.security.cs.allow-jit`; numba/llvmlite JIT
  `allow-unsigned-executable-memory` vagy `allow-jit`; ha a Python futás közben letöltött (nem a mi csapatazonosítónkkal aláírt) `.so`-t
  tölt be: `com.apple.security.cs.disable-library-validation` a Python binárisán.
- **`sandbox-exec`** (`/usr/bin/sandbox-exec`, `config/os.toml:49`; a PDF-gyermek `core/index/pdf_profil.sb` és a CAS-homokozó profiljai
  paraméterezettek, beégetett út nélkül) nem-sandboxolt Developer ID appból működik (elavult, de jelen van); **App Sandbox / Mac App Store
  kizárt** (beágyazott sandbox nem engedett).
- **EventKit/TCC**: az engedély a kód-identitáshoz (bundle id + designated requirement) kötött. Developer ID-vel frissítések után is
  megmarad; a bundle id cseréje (`local.manifold-os.app` → fordított DNS) egyszeri újrakérdezés. A `--naptar` CLI-mód a core
  gyermekfolyamataként fut; a felelős folyamat az app (a GUI indította a core-t), a usage-szövegek a bundle Info.plist-jéből jönnek.
  Ha a vault a `~/Documents`/`~/Desktop`/iCloud Drive alatt van, a mappa-TCC kérdés is az appra száll (a Python-gyermekekkel együtt).
- **App Translocation**: a DMG-ből vagy a Letöltésekből közvetlenül futtatott karanténos app véletlen, írásvédett útról fut — a mai
  `RootLocator` (szülőmappa) ott nem talál gyökeret; az `/Applications`-be húzás vagy a Resources-alapú keresés kell.
- Az `~/Library/Application Support/Manifold` használata engedélyt nem igényel; a mai policy (79(d)) és a doctor viszont tiltja.

| | **A — vastag `.app` beágyazott runtime-mal + DMG; modellek első indításkor** | **B — könnyű `.app`; első indításkor runtime letöltése pin szerint** | **C — a mai SSD-modell „portable” módban marad + A** |
|---|---|---|---|
| Letöltési méret | mag ~250 MB; mag + AI-alap ~0,75 GB; minden modul (keresés, átirat, videó) ~1,7–1,9 GB kicsomagolva (a DMG tömörítve becslés szerint kb. 40–50%) | `.app` + kód + `app/dist` ~30 MB; a runtime (Python 75 MB + modulonként a wheel-ek: ma összesen 387 MB tömörítve) első indításkor | mint A; a portable példány a mai 1,5 GB+ runtime |
| Aláírás / notarizáció | Developer ID + hardened runtime + notarizáció **a teljes venvre** (több ezer `.so`, torch dylibjei) — a legnagyobb aláírási munka, de egyszer, a buildben | csak a kis `.app` notarizált; a letöltött Python/wheel-ek **nem a mi aláírásunk** (a python-build-standalone ad-hoc aláírt; PyPI-wheelek dylibjei aláíratlanok vagy idegenek) → library validation miatt `disable-library-validation` kell, vagy a gyermek-Python nem hardened | A-ra mint A; a portable példány továbbra is helyi tanúsítvány/ad-hoc (csak a fejlesztő gépén) |
| Gatekeeper | a DMG stapled → első indítás egy kérdés | az `.app` mint A; a runtime-ot az app maga tölti (`URLSession`/`curl` alapból nem tesz `com.apple.quarantine`-t) → a Gatekeeper nem nézi, de az integritást a sha256-pin adja (a mai `letolt()` mechanizmus) | mint A; a portable az SSD-ről nem karanténos |
| `sandbox-exec` | működik (nem-sandboxolt app) | működik | működik |
| EventKit | stabil (Developer ID DR) | stabil (az `.app` identitása) | két identitás (helyi tanúsítvány vs Developer ID) → két külön engedély-kör; azonos bundle id + eltérő DR ütközhet |
| `~/Library/Application Support` | állapot, modellek, venv-módosítás nélkül; a kód a bundle-ben | állapot + runtime + venv is ott (a doctor ffmpeg/python szabályai home alatti runtime-ot ma tiltanak: `core/doctor.py:255-258, 763`) | A: AS; portable: `{os}/var` mint ma (a `RootLocator` sorrendje dönti el: env → szülőmappa → Resources) |
| Offline / D3 | a mag és a runtime offline települ; csak a modellek kérnek hálózatot | az első indítás hálózatot igényel (D3: kifejezett igen kell a runtime-ra is) | mint A |
| Frissítés útja | teljes `.app` csere (pl. Sparkle EdDSA-aláírt appcast, delta-frissítéssel); a modellek és az állapot érintetlen | kis `.app`-frissítés; a pin-változáskor runtime/wheel újratöltés a meglévő `regi/`-félretevő logikával (`bin/mos:98-117`); a venv újraépítése a háttérben | A: Sparkle; portable: `git pull` + `shell/build.sh` + `runtime fetch/install` (mai út) |
| Fő kockázat | aláírási munka a venv minden Mach-O-ján; minden runtime-pin-váltás új app-kiadás; macOS-minimum (3.4) | futásidejű letöltött natív kód hardened runtime mellett; hálózati hibák első indításkor; a runtime-telepítő ma bash (`bin/mos`), Pythonba/Swiftbe kellene portolni (minta: `modulok/cpp/telepites.py`) | két üzemmód tesztmátrixa; a policy (6., 79(d)) kettős érvényessége |

---

## 9. Nyitott kérdések / talált hibák (döntés nélkül)

1. `core/letoltes.py:65` — `megvan` statikus jelző miatt friss telepítésen 5 modell (köztük a bge_m3) nem tölthető le.
2. `shell/Info.plist:15`, `shell/build.sh:30`, README 1. fejezet (macOS 13) ↔ `mlx_metal … macosx_26_0` wheel.
3. `config/requirements.in:38` — `pytest` a termék-lockban; `pypdf`, `fastapi`, `uvicorn` a `.in`-ben, de a kód nem importálja (a fastapi/uvicorn
   az mlx-vlm miatt úgyis bejön).
4. `core/naptar_seged.py:46` — nem létező `bin/mos shell build` alparancsra hivatkozik.
5. `core/snapshot.py:210`, `core/frame.py:287, 290` — git-hívás a hermetikus környezet nélkül.
6. A `bin/mos` a `var/` utakat a `$MOS_HOME/var`-ból számolja (`:35-54, 60`), a `MOS_VAR`-t figyelmen kívül hagyja — a `config.py` felülírási
   ígérete (L49) itt nem teljes.
7. Állapot a kódfában: `ytdlp = {modulok}/ytdlp` (+`staging`, `archive`, 55 GB), `archive = {os}/archive` (`config/os.toml:24-28, 52`).
8. `config.load` egyetlen konfigfájlt olvas (`core/config.py:71-74`): a felhasználói beállítások (vault helye, mentési cél) egy írásvédett
   bundle mellett felülíró réteget igényelnének.
