# 01 — Personal-coupling térkép (Manifold-OS 2.0)

Forrás: `/Volumes/Work/Manifold-OS v2` (csak olvasva). Vizsgált könyvtárak: `core/`, `app/src/`, `app/tests/`, `shell/`, `modulok/` (.py, a `modulok/ytdlp/tests` és `modulok/ytdlp/src/msp` csak érintőlegesen), `bin/`, `config/`, `tools/`, `tests/`. Kihagyva: `var/`, `runtime/`, `archive/`, `node_modules`, `dist`, staging/archive, `modulok/eval/*/` adatfájlok (aranyhalmazok), `.git`.

Jelmagyarázat a „javasolt sors” oszlophoz:
- **CONFIG** — felhasználó/telepítés által állítható érték legyen (`os.toml` / felhasználói réteg / MOS_* env), a kódban csak semleges alapérték marad.
- **USER DATA** — a felhasználó vaultjához/szokásaihoz tartozó adat; a felhasználó adja meg (első indítási varázsló vagy vault-felismerés), nem a kódtár része.
- **INSTALLATION DATA** — telepítésenként/gépenként keletkező állapot (`var/`, kalibráció, aláírás, mérés).
- **PRESET** — a termékkel szállított, de cserélhető sablon-készlet (pl. nyelvi profil, tantárgy-készlet, modell-regiszter).
- **TÖRLÉS** — fejlesztői/legacy/Claude-munkafolyamati maradvány; a kiadott termékből kimarad.
- **MARAD** — nem személyes kötés (platform-követelmény, termék-döntés vagy általános viselkedés); legfeljebb dokumentálni kell.

Fontos általános megfigyelések, mielőtt a táblázatok jönnek:
1. A kód **abszolút utat nem éget be** (L49; `core/config.py:1`, `doctor.py:23` őrzi). A `/Volumes/…` és `/Users/…` találatok szinte kivétel nélkül kommentek, tesztadatok vagy a `modulok/ytdlp/utnorm.py` legacy-úttisztítója. Az igazi kötés a **konvenciókban** van (vault-mappanevek, frontmatter, tantárgyak, nyelv, kalibráció), nem az útvonalakban.
2. Az `config/os.toml` (998 sor) egyetlen, a kódtárban követett fájl: nincs felhasználói felülírási réteg, csak `MOS_<KULCS>` env az `[utak]`-ra (`core/config.py:46-80`) és `MOS_CONFIG` (teljes fájlcsere). A személyes értékek (`[fuzet] mappak`, `[naplo] ut`, `[pdf.tags]`, `[emlekezteto] lista`…) tehát ugyanabban a fájlban élnek, mint a termék-alapértékek.
3. A tesztek (264 + 166 fájl) többnyire szintetikus álvaultot építenek; a valódi fejlesztői vaultot csak a `tests/kezi/` eszközök igénylik.

---

## 1. Abszolút / személyes utak

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| core/visszaallitas.py:5 | docstring: „…`git bundle`-ből (`~/Manifold-backup/`…” | MARAD (komment; a backup útja `[utak] backup`) |
| core/doctor.py:23 | `LEGACY_MINTA = re.compile(r"Manifold-OS legacy|/Volumes/[^/\s\"']+/Manifold-OS/(?!v2)")` | TÖRLÉS (a legacy-ellenőrzés a fejlesztő migrációját őrzi; új telepítésen értelmetlen) |
| core/doctor.py:24 | `SAJAT_MINTA … ~/Applications|/Applications/Manifold|~/.cache|Library/Caches` | MARAD (a „home alá nem írunk” elv ellenőrzése) |
| core/doctor.py:366-370 | `APP_AZONOSITO = "local.manifold-os.app"`, `HOME_KIVETEL = "Library/Preferences/local.manifold-os.app.plist"`, `HOME_NEM_ENGEDETT = (Library/Saved Application State, Library/Caches, Library/WebKit …)` | CONFIG (bundle id-ból származtatott; lásd 3. kategória) |
| core/doctor.py:376-380 | „~/Manifold-backup … megengedett kivétel” üzenet | CONFIG (a `{backup}` útból képezve) |
| core/doctor.py:254 | `tiltott = [home, "/opt/homebrew/", "/usr/local/", "/usr/bin/"]` | MARAD (hordozható runtime-elv) |
| config/os.toml:11-12 | `work = "{os}/.."` · `vault = "{work}/Manifold"` (a vault a kódtár melletti „Manifold” mappa) | USER DATA (a vault helye a felhasználó választása; MOS_VAULT már felülírja) |
| config/os.toml:53 | `backup = "{home}/Manifold-backup"` | CONFIG (alapérték marad, a név termék-név) |
| config/os.toml:77 | `".obsidian/workspace*.json", ".obsidian/cache"` a pillanatkép `kizar` listában | PRESET (Obsidian-profil) |
| config/os.toml:203 | `forras = ""  # a lista fiókja (pl. iCloud)` | CONFIG (üres alap, jó) |
| config/os.toml:370 | `mappak = ["{work}/Notebooks - digitalized", "{work}/Rendezetlen"]` — a fejlesztő saját füzetfotó-mappái | USER DATA (üres alapérték; a felhasználó adja meg) |
| core/server.py:234,245 | „Csak valódi vaulton (`.obsidian`)…” / `print(… nincs .obsidian …)` | CONFIG (a „valódi vault” kritérium legyen állítható; lásd Obsidian-függés) |
| core/frame.py:129-132 | `vault_letezik(cfg)`: `(cfg.path("vault") / ".obsidian").is_dir()` | CONFIG / MARAD (Obsidian-vault feltétel: termék-döntés) |
| core/frame.py:164 | `if not (root / ".obsidian").is_dir()` (TMP_MINTA takarítás) | MARAD |
| core/vaultio.py:155,184 | rejtett szegmens tiltása; `if not (v / ".obsidian").is_dir()` | MARAD |
| core/vaultio.py:403-406 | az új-jegyzet helye `.obsidian/app.json`-ból (`newFileLocation`) | MARAD (Obsidian-kompatibilitás; a hiányzó fájl elegánsan kezelendő) |
| core/csatolmany.py:110-114 | `attachmentFolderPath` a `.obsidian/app.json`-ból | MARAD (Obsidian-kompatibilitás) |
| core/doctor.py:165-166 | „… nincs .obsidian mappája: nem valódi vault” | MARAD |
| core/index/indexelo.py:394,492 | `.obsidian/types.json` változás kezelése | MARAD |
| core/index/elemzo.py:328,445-448 | `os.path.join(vault, ".obsidian", "types.json")` | MARAD |
| core/index/graf_meta.py:75-80 | `.obsidian/graph.json` olvasása | MARAD |
| core/index/feloldas.py:38 | `SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}` | MARAD |
| core/binaris_naplo.py:55 | `KIHAGY = {".obsidian", ".trash", ".git"}` | MARAD |
| core/bazis/adat.py:115 | `tipusok` a `.obsidian/types.json`-ból | MARAD |
| modulok/ytdlp/elhelyezes.py:23 | `KIHAGY_MAPPAK = {".obsidian", ".git", ".trash"}` | MARAD |
| modulok/ytdlp/egyezes.py:39 | `SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}` | MARAD |
| app/src/lib/graf/beallitasok.ts:2-3 | gráf-alapok a `.obsidian/graph.json`-ból (komment + logika) | MARAD |
| app/src/hej/vezerlo/TeljesMentes.svelte:48 | `placeholder="/Volumes/Mentés/Manifold"` (felületi minta-út) | CONFIG (semleges placeholder, pl. „/Volumes/<lemez>/…”) |
| shell/Sources/CoreProcess.swift:156-160 | selftest-táblázat: `("/Volumes/Work", "/Volumes/Work/Manifold-OS v2", true) …` | TÖRLÉS (selftest-adat, a fejlesztő SSD-neve; paraméterezett álútra cserélendő) |
| shell/Sources/Naptar.swift:510-517 | „…ennek hiányában az iCloud, majd az első helyi forrás” — `store.sources.first(where: { $0.title == "iCloud" })` | CONFIG (alapértelmezett naptárfiók-választás: `[naptar]`/`[emlekezteto] forras`) |
| shell/Info.plist:31,33 | EventKit-engedély szövegei: „a saját „Manifold” listáját kezeli” | MARAD (termék-név) |
| shell/Sources/AppController.swift:63-64 | komment: `~/Library/Preferences/local.manifold-os.app.plist` | MARAD |
| modulok/ytdlp/utnorm.py:8-12 | docstring: `/Users/<u>/Library/Application Support/Manifold-media/…`, `/Users/<u>/Library/Mobile Documents/iCloud~md~obsidian/Documents/ytdlp/staging/…`, `/Volumes/Work/Manifold-OS/var/state/…`, `/Volumes/Work/Obsidian/ytdlp/…`, `…/Manifold-OS legacy/Legacy/…` | TÖRLÉS (a fejlesztő régi gépeinek úttáblája) |
| modulok/ytdlp/utnorm.py:24,40-50 | `JOBS_HORGONY = "/Manifold-media/jobs/"`, `"/Mobile Documents/iCloud~md~obsidian/"`, `u.startswith("/Volumes/Work/Obsidian/")`, `u.startswith("/Volumes/Work/Manifold-OS/")`, `"/Manifold-OS legacy/"` | TÖRLÉS (legacy út-normalizáló; csak a fejlesztő 264 régi job-állapotához kell) |
| modulok/ytdlp/lanc.py (utnorm hívások), `bin/mos video utnorm` (bin/mos:275) | a CLI-parancs | TÖRLÉS |
| modulok/kartya/apkg.py:4 | `/Volumes/Work/anki-main` (komment: a fejlesztő Anki-repó klónja) | TÖRLÉS (komment) |
| tools/mac/02_legacy_referencia.sh:4 | `/Volumes/Work/Manifold-OS legacy/Legacy` a szokásos `MOS_LEGACY` érték | TÖRLÉS |
| tests/test_cpp_diagnosztika.py:16,31,36,37,39 | `/Volumes/Work/Manifold-OS v2/runtime/sdk/…` szintetikus ASan-kimenet | CONFIG (teszt-fixture: generikus gyökér) |
| tests/test_video_staging.py:19 találat | `/Users/…`, `/Volumes/Work/…` útminták az `utnorm` tesztjében | TÖRLÉS (az utnorm-mal együtt) |
| tests/test_doctor.py:10 találat | `LEGACY_MINTA`-minták, `Manifold-backup` | TÖRLÉS/CONFIG (a doctor legacy-ágával együtt) |
| tests/test_index_graf_meta.py:9, test_vaultio.py:5, test_atnevezes.py:4 stb. | `.obsidian` mappa szintetikus álvaultban | MARAD |
| tests/test_mentes.py, test_mos_es_shell.py:163-164, test_kezi_kornyezet.py:224-226,449,455, test_visszaallitas.py, test_kiadas_mentes.py:2 | `{home}/Manifold-backup` álhelyek | MARAD (álhome; ellenőrzik, hogy a valódi `~/Manifold-backup`-hoz nem nyúlnak) |
| tests/test_dokumentacio.py:168 | elvárt szöveg: `local.manifold-os.app.plist`, `~/Manifold-backup`, `docs/KIADAS.md` | CONFIG (a dok-teszt kövesse a bundle id-t) |
| tests/test_ma.py:90, app/tests/vezerlo-naptar.svelte.test.ts:31-33, app/tests/naptar-hid.test.ts:227-228, tests/naptar_segedek.py:39, tests/naptar_seged_alarm.py:92 | naptár-fixture: `forras: 'iCloud'`, „Órarend”, „Matek-felkészülés”, „Edzés” | CONFIG (generikus fixture-nevek) |
| tests/kezi/video_proba.py:3 | `MOS_VAULT=/Volumes/Work/Manifold MOS_VAULT_GIT=…` használati példa | TÖRLÉS |
| tests/kezi/* (obsidian_link_proba.py:3, notion_obsidian.py:3, bazis_proba.py:3, atallas_riport.py:3, atallas_probavault.py:5, kor2_olvaso.py:2, graf_paritas.py:2, _kornyezet.py:5, nagy_vault_meres.py, index_meres.py) | `.obsidian` ál-vaultok, a fejlesztő valódi vaultjának klónja (`MOS_VAULT`) | TÖRLÉS (a kiadott termékből; fejlesztői kézi kapuk) |
| app/tests/kezi/linkek.kezi.ts:18, kepletek.kezi.ts:4,18 | a valódi vault bejárása (`.obsidian` kihagy) | TÖRLÉS (kézi mérés a fejlesztő vaultján; `vitest.kezi.config.ts` is) |

---

## 2. A vault-struktúra beégetett konvenciói

### 2.1 Mappanevek és előtagok (`ATTCHMNTS - …`, `X01`, `AI0x`, `_Template`, `Média`, `Elmélet`)

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| core/automatika.py:47,117-119 | `KISERO_ELOTAG = "ATTCHMNTS - "` — a gépi kísérőjegyzet-mappák felismerése | CONFIG (egy közös „kísérő-mappa előtag”, a `[kartya]/[kviz]/[osszefoglalas] mappa` kulcsokból képezve) |
| core/index/hibrid/hasonlo.py:23,32 | `KISERO_ELOTAG = "ATTCHMNTS - "` (hasonlóság-szűrő) | CONFIG |
| core/osszefoglalas_api.py:43,147 | `get("mappa", "ATTCHMNTS - summaries")`, `startswith("ATTCHMNTS - ")` | CONFIG |
| core/kviz_api.py:36 | `MAPPA_ALAP = "ATTCHMNTS - quizes"` | CONFIG |
| core/kartya_api.py:52 | `get("mappa", "ATTCHMNTS - cards")` | CONFIG |
| core/gepi_iras.py:818,821 | `… or "ATTCHMNTS - Videos"` / `or "ATTCHMNTS - photos"` | CONFIG |
| core/atirat.py:24-25 | `ALAP_VIDEO_MAPPA = "ATTCHMNTS - Videos"`, `ALAP_RETEG = "Média"` | CONFIG (a `[media]` szakasz már olvassa; az alapérték személyes) |
| core/higienia.py:303 · core/asszisztens/emlites.py:132 | `section("media").get("reteg_mappa", "Média")` | CONFIG (alapérték PRESET) |
| core/modell/bench.py:111 | `cfg.path("vault") / "ATTCHMNTS - photos"` `IMG_*.JPG` — a fejlesztő füzetfotói | TÖRLÉS (mérési segéd) |
| core/asszisztens/beallitasok.py:7,18,44 | `higienia_arva_kizart`/`emlites_kizart`/`kartya_kizart` = `["X01 - Napló & To-Do/", "AI02 - Log/", "_Template/", "ATTCHMNTS - "]` | PRESET (üres/semleges alap + a felhasználó vaultjából javasolt lista) |
| config/os.toml:919,929 | ugyanez a két lista az `[asszisztens]`-ben | USER DATA |
| core/sablon.py:36 · config/os.toml:174 | `ALAP_MAPPA = "_Template"`; `mappa = "_Template"` | CONFIG (Obsidian `templates.json`-ból is kiolvasható) |
| core/naplo.py:25 · config/os.toml:181 | `ALAP_UT = "[X01 - Napló & To-Do]/YYYY-MM/[Napló]/YYYY-MM-DD"` — a napi jegyzet útja | CONFIG + USER DATA (a felhasználó vaultjának konvenciója; Obsidian „Daily notes” beállításából is átvehető) |
| core/naplo.py:27 · os.toml:182 | `ALAP_SABLON = "Napi jegyzet"` | CONFIG |
| core/naplo.py:3-4,74 | váz: `Tags:\n  - Napló\nSource:\nStatus:\nNN:\n{cv}` + `# Napló` | PRESET (váz a sémából generálandó) |
| core/naplo.py:34 · os.toml:184 · core/felkeszultseg/adat.py:36,59-60 · core/ma.py:8,145 · core/felkeszultseg/kotes.py:4-5,54-57 · core/felkeszultseg/osszesit.py:231 | `dolgozat_mappa = "Dolgozatok"`; a felkészülési jegyzet `ÉÉÉÉ-HH-NN - Tantárgy.md` (L59) | PRESET (az egész „Dolgozat” munkafolyamat diák-specifikus; modul-szintű kikapcsolás kell) |
| config/os.toml:186 · core/felkeszultseg/adat.py:42,63-64,218 · core/felkeszultseg/__main__.py:29-45 | `kiertekelo_nevek = ["Dolgozat kiértékelő", "Dolgozat Napló"]` | USER DATA / CONFIG (üres alap) |
| core/felkeszultseg/eredmeny.py:1,23,338 · kalibracio.py:3,223 · osszesit.py:63 · __init__.py:16 | „Dolgozat kiértékelő” jegyzet szerkezete (docstring + felhasználói szöveg) | CONFIG (a névrészletből képezve) |
| core/felkeszultseg/eredmeny.py:220-225 | `MEZO_KULCS = "Eredmény"`, `_MEZO_SOR` (`eredm[eé]ny::`) | PRESET |
| core/videolanc.py:207 | `TEMAMAPPA_MINTA = r"^([A-Z]{1,3})(\d{2}) - \S.*$"` — a „téma-mappa” a `<Betű><két szám> - <cím>` alakú (pl. `D13 - CS50`) | USER DATA / PRESET (a felhasználó vault-taxonómiája) |
| core/videolanc.py:219-237 | `TemamappaHiba(… „D13 - CS50” …, „…00 - ” vizuális mappa …, nincs tárgy-címkéje a [pdf.tags]-ben)` — **felhasználói hibaüzenet** a fejlesztő saját mappájával | TÖRLÉS (a példa) / CONFIG (a minta) |
| core/videolanc.py:310-315 | felhasználói összegzés: „…az „ATTCHMNTS - Videos” alá…, a téma „Média” rétegébe…” | CONFIG (a mappanevet a `[video] vault_mappa`-ból kell behelyettesíteni) |
| app/src/hej/vezerlo/Bevitel.svelte:374,401,416 | `placeholder="pl. D13 - CS50"`; „…„{cel}/Média” rétegbe…”, „…az „ATTCHMNTS - Videos” alá…” (felületi szöveg a fejlesztő mappanevével) | CONFIG (placeholder + a core-ból kapott mappanév) |
| core/fuzet_feladat.py:62-64 | „…„## Füzet” szakaszába…”, „…„ATTCHMNTS - photos” alá költözik…” (felületi összegzés) | CONFIG |
| core/teljes_mentes.py:54 | `'staging': '…a bevitt videó a vaultban van (ATTCHMNTS - Videos)…'` | CONFIG |
| core/binaris_naplo.py:261-262 | `ARCHIV_INDOK` szöveg: „(`ATTCHMNTS - Videos/`)” | CONFIG |
| modulok/ytdlp/elhelyezes.py:19-20 | `ALAP_VIDEO_MAPPA = "ATTCHMNTS - Videos"`, `ALAP_RETEG = "Média"` | CONFIG |
| modulok/ytdlp/egyezes.py:37-38,68 | `TEMA_MINTA = r"^[A-Z]{1,3}\d{2} - .+"`; `KIZART_MAPPAK = ("AI01","AI02","AI03","_Template","X01","Prjct01","Napló","ATTCHMNTS - quizes")` | USER DATA (a felhasználó vaultjának mappa-taxonómiája) |
| modulok/ytdlp/egyezes.py:8,183,198 | `parts[1] != "Elmélet"` — a tananyag-jegyzetek az `<Téma>/Elmélet/` alatt | USER DATA / CONFIG |
| modulok/ytdlp/integralas.py:8-9,32,79,268 | `ATTCHMNTS - Videos/` alá, `<Téma>/Média/` réteg, `naplo (AI02 - Log)` | CONFIG |
| modulok/ytdlp/itelet.py:133 | `re.sub(r"^[A-Z]+\d\d - ", "", …)` témanév-tisztítás | CONFIG (a TEMA_MINTÁVAL együtt) |
| modulok/ytdlp/__main__.py:385 | help: `„D13 - CS50”` | TÖRLÉS (példa) |
| modulok/fuzet/lanc.py:95 | `fz.get("cel_mappa") or "ATTCHMNTS - photos"` | CONFIG |
| modulok/fuzet/katalogus.py:6,87 | „tárgyi fejezetmappa `Elmélet/` alatti, `^\d+ - ` nevű jegyzet” | USER DATA / CONFIG |
| modulok/kartya/szinkron.py:40 | `get("mappa", "ATTCHMNTS - cards")` | CONFIG |
| modulok/kviz/lanc.py:171 | `get("mappa", "ATTCHMNTS - quizes")` | CONFIG |
| modulok/osszefoglalas/lanc.py:45 · formatum.py:141 | `mappa: str = "ATTCHMNTS - summaries"` | CONFIG |
| modulok/grafikon/automatika.py:99 | `KIZART_MAPPA = (".", "ATTCHMNTS - ")` | CONFIG |
| app/src/kartya/allando.ts:4 | `KARTYA_MAPPA = 'ATTCHMNTS - cards'` (a felület a core `[kartya] mappa` tükre, teszt őrzi a paritást) | CONFIG (a core adja át: `/api/config`) |
| app/src/kviz/allando.ts:4 | `KVIZ_MAPPA = 'ATTCHMNTS - quizes'` | CONFIG |
| app/src/osszefoglalas/allando.ts:4 | `OSSZEFOGLALO_MAPPA = 'ATTCHMNTS - summaries'` | CONFIG |
| app/src/osszefoglalas/parancsok.ts:18 · app/src/kviz/index.ts:13 | `KISERO_ELOTAG = 'ATTCHMNTS - '` | CONFIG |
| app/src/szerkeszto/renderelok/plot/beiras.ts:16 | `!u.startsWith('ATTCHMNTS - ')` | CONFIG |
| app/src/szerkeszto/notion/sablonok.ts:229 | `jelzo: '_Template'` | CONFIG |
| config/os.toml:233 | `[video] vault_mappa = "ATTCHMNTS - Videos"` | CONFIG (alapérték PRESET) |
| config/os.toml:256,316,335,370(cel_mappa),381 | `[kartya] mappa`, `[kviz] mappa`, `[osszefoglalas] mappa`, `[fuzet] cel_mappa = "ATTCHMNTS - photos"`, `[media] video_mappa/reteg_mappa` | CONFIG (már konfigurálható; az alapértékek a fejlesztő vaultjának nevei → PRESET) |
| app/src/hej/vezerlo/FeladatReszlet.svelte:131, app/src/ma/index.ts:25,33, app/src/naptar/index.ts:63,67, app/src/media/index.ts:70 | „Napló” / „Média” kategória-címkék a parancspalettában | MARAD (felületi szöveg) |
| modulok/ytdlp/config/config.yaml:66,489 | „Fidelity requirement (AI01 #14)”, „the vault's AI01 Workflow 2.0 protocol” | TÖRLÉS (komment: a fejlesztő saját AI01 protokolljára hivatkozik) |
| modulok/ytdlp/src/msp/{schema.py:82,108, manifest.py:8, validation.py:256, transcription/__init__.py:7}, modulok/ytdlp/integralas.py:20 | „AI01 #9/#14” szabályhivatkozások | TÖRLÉS (komment/leírás) |
| app/src/szerkeszto/formazas.ts:5,94-101 | **felületi szöveg**: „Az AI01 Workflow 2.0 protokoll nem engedi a == jelölést; a vault-ellenőrző jelezni fogja.” | TÖRLÉS/CONFIG (a `==kiemelés==` tiltás a fejlesztő vault-szabálya; legyen szabály-profil) |
| app/src/media/beszuras.ts:49 | komment: „időkód-link … (AI01 PB07)” | MARAD (komment) |

### 2.2 Frontmatter-séma (`Tags` / `Source` / `Status` / `NN` / `Canvas`) és a `config/vault-sema.json`

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| config/vault-sema.json:5 | `"mezosorrend": ["Tags", "Source", "Status", "NN", "Canvas"]` | PRESET (a séma a felhasználó vaultjából / választott profilból jöjjön) |
| config/vault-sema.json:8 | `tags_ertekkeszlet`: History, Literature, Mathematics, Physics, Informatics, Grammar, English, Íráskészség, AI, Workflow, Projekt-1, Napló | USER DATA |
| config/vault-sema.json:9-11 | `status_ertekkeszlet`: Completed / In progress / Review; `status_gazdai: true` | PRESET / CONFIG |
| config/vault-sema.json:13-42 | `kivetel_osztalyok`: kviz, kartya, osszefoglalo (`ATTCHMNTS - …`), `konyv-jegyzet` (`X03 - Books/`: `Szerző`, `Műfaj`, `Rate`, `Status`) | USER DATA (a „konyv-jegyzet” a fejlesztő saját osztálya) |
| config/vault-sema.json:44-54 | `h1`: `sorszam_elotag "^\\d+[A-Z]? - "`, `kivetel_utvonalak: AI01 - Workflow System/2.0/, AI02 - Log/, AI03 - Memória/, Prjct01 - Obsidian/, X01 - Napló & To-Do/, _Template/`; `megoldas-sorszamos` (`Megoldások`, „feladat” minta), `erettsegi-temakor-cim` (`emelt matematika témakörök.pdf`), `sablon-vaz` | USER DATA (a legszemélyesebb fájl a repóban) |
| config/vault-sema.json:55-56 | `sema_nelkuli_utak: ["AI01 - Workflow System/CLAUDE.md", "AI01 - Workflow System/MEMORY.md"]` | USER DATA / TÖRLÉS |
| config/pillanat-kivetelek-vault.json:3-14 | két commit-hash (`4b72aca…`, `dba2729…`) a **fejlesztő vault.git-jéből** + `X01 - Napló & To-Do/*`, `AI01 - Workflow System/2.0/01 - Master/00 - MASTER.md`, `AI02 - Log/00 - Log Index.md` | TÖRLÉS (installációs adat; új telepítésen üres `{}`) |
| core/pdfkiemeles.py:4-5,71-72 | kiemelés-fájl váz: `Tags:\n  - {tag}\nSource:\nStatus:\nNN:\nCanvas:` | PRESET (a séma-profilból) |
| core/cpp_teszt.py:249-252 | C++ feladat-jegyzet váza: `Tags/Source/Status/NN/Canvas` | PRESET |
| modulok/ytdlp/vaultoldal.py:238-241 | forrásleíró jegyzet váza: `["---", "Tags:", … "Source:", "Status:", "NN:", "Canvas:", "---"]` | PRESET |
| modulok/ytdlp/horgony.py:1,26,38-55 | a `#t=` horgony a `Source:` lista végére (I27 formátum, hibák: „a Source: nem lista-alakú”) | PRESET / CONFIG |
| modulok/kviz/formatum.py:8,164,258 · modulok/kartya/formatum.py:65,101,213-216 · modulok/osszefoglalas/formatum.py:8,186,233 · kontextus.py:85-93 | kísérőjegyzet-frontmatter: `Source`, `Kviz`, `Modell`, `Keszult`, `Osszefoglalas`, `Szint` (magyar mezőnevek) | MARAD (a termék saját formátuma; de a mezőnevek dokumentálandók) |
| core/higienia.py:269-281,343 | `tul == "Source"`; `t.kulcs IN ('Tags', 'Status')` | CONFIG (a séma „link”/„címke” mezőszerepei) |
| core/asszisztens/beallitasok.py:8 · config/os.toml:~921 | `higienia_arva_tulajdonsag_kizart = ["Canvas", "Source"]` | CONFIG |
| core/gepi_iras.py:747,785,809 | `t["kulcs"].casefold() == "status"`; „A Status mezőt csak a felhasználó tölti, gép nem (L33).” | PRESET (a „gazdai mező” a séma része, nem kód) |
| core/tulajdonsagok.py:349-359,472,510,614 | `ertekek.get("Tags")`, `"Status"`, `Source` a séma-ellenőrzésben | PRESET |
| core/felkeszultseg/temak.py:1-5 · adat.py:252,289 · __init__.py:3,11 | a felkészülési jegyzet témái a `Source` + `NN` linkjeiből | PRESET |
| app/src/szerkeszto/tulajdonsagok/ertek.ts:40,80,82 | `LISTA_KULCSOK = ['Tags','Source','NN']`, `LINK_KULCSOK = ['Source','NN','Canvas']` | PRESET (a core sémájából) |
| app/src/szerkeszto/tulajdonsagok/Tulajdonsagok.svelte:99,206 | `t.kulcs === 'Status'`, `e.ertek === 'Tags'` | PRESET |
| app/src/szerkeszto/tulajdonsagok/javaslat.ts:150-153 | `kulcs === 'Canvas'` → vászon, `'Source'` → PDF/jegyzet (fájltípus-előny) | PRESET |
| app/src/szerkeszto/tulajdonsagok/fmKiegeszites.ts:4-6 · tipusok.ts:76 · api.ts:39 | `Tags:`, `Status`, `Source:/NN:/Canvas:` kiegészítés | PRESET |
| app/src/bazis/kanban.ts:2,20,40,51 · bazis/Kanban.svelte:2,33 · bazis/cellaErtek.ts:9-11 | `Status`-oszlopok sorrendje a séma szerint, mindig választó | PRESET |
| app/src/lib/asszisztens/kartya.svelte.ts:61 | `const kulcs = t?.kulcs ?? 'Tags'` | PRESET |
| app/src/graf/GrafVezerlo.svelte:66 | `placeholder="path:mappa  tag:#címke  [Status:kész]"` | CONFIG (semleges placeholder) |
| app/src/dolgozat/Dolgozat.svelte:251 | felületi szöveg: „…a felkészülési jegyzet `Source` és `NN` mezője nem hivatkozik jegyzetre.” | PRESET |
| app/src/media/beszuras.ts:1-113 · media/pdf/PdfFul.svelte:5 | PDF-idézet `Source`-horgonnyal; `Source` séma-kapu | PRESET |
| core/index/olvaso.py:375 | `Tags` + `#címke` (Obsidian-viselkedés) | MARAD |
| core/vaultio.py:59 · core/tulajdonsagok.py:41 · modulok/osszefoglalas/formatum.py:123 · modulok/kviz/formatum.py:265 · modulok/kviz/generalas.py:251 | `^\d+[A-Z]? - ` sorszám-előtag regex (a vault `NN - Cím` fájlnév-konvenciója, H1-szabály) | PRESET / CONFIG (a `vault-sema.json h1.sorszam_elotag` már tartalmazza, a kód duplikálja) |
| core/asszisztens/emlites.py:13-23,51,72 | `NN - Cím` és `NNF - Cím — Feladattár` fájlnév-alakok, `_UTOTAG_JEL = " — "` | PRESET |
| modulok/ytdlp/itelet.py:134 | `"Feladattár" not in idx.notes[rp]["cim"]` | PRESET |

### 2.3 Blokk-/jelölő-konvenciók (`^m-`, `^c-`, `%%manifold-…%%`, `## Gyakorlás`, `## Füzet`, `[!card]`)

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| core/gyakorlas.py:1,5,20,34 | `SZAKASZ = "Gyakorlás"`; a forrásjegyzet `## Gyakorlás` szakasza a beágyazó sornak | PRESET (szakaszcím konfigurálható; a felhasználó vaultjában más nyelv/név lehet) |
| modulok/kartya/horgony.py:1-2 · modulok/kartya/lanc.py:7-8,177,190 · modulok/osszefoglalas/futtat.py:10-11,221,232 · modulok/kviz/lanc.py:7 · modulok/kviz/__init__.py:4 · modulok/osszefoglalas/__init__.py:5 | `^m-…` forrás-blokkazonosító + `## Gyakorlás` | PRESET |
| core/tracker.py:81 | `_KARTYA_ID = re.compile(r"c-[0-9a-z]{4,16}")` (`^c-` azonosító) | MARAD (a termék saját azonosító-formátuma) |
| modulok/kartya/formatum.py:4-8,53,202 | `> [!card]- …`, `— [[Forrás#^m-3f2a]]`, `^c-7f3a9e21` | MARAD (saját formátum; dokumentálandó) |
| modulok/kartya/apkg.py:443-446 | `[!card]` escape az Anki-importnál | MARAD |
| core/pdfkiemeles.py:8,38,155 | `%%manifold-kiemeles k-1a2b3c …%%` jelölősor | MARAD (saját formátum) |
| app/src/szerkeszto/notion/blokkmodell.ts:8,91 | `KIEMELES_JELOLO = /^%%manifold-kiemeles\b.*%%/` | MARAD |
| app/src/kartya/beagyazas.ts:1-3 · osszefoglalas/beagyazas.ts:1 | „`## Gyakorlás` alatt” beágyazás | PRESET |
| modulok/fuzet/formatum.py:1,88,117,142 | `szakasz: str = "## Füzet"` (alap 3 függvényben) | PRESET (config `[fuzet] szakasz` már él: os.toml:372) |
| core/fuzet_feladat.py:62-63 | „## Füzet” szakasz felületi szövegben | CONFIG |
| modulok/kapuk/forras.py:26 | `KIHAGYOTT_SZAKASZOK = ("Füzet", "Gyakorlás", "Kitöltések")` | PRESET |
| modulok/eval/ocr_kezi/epit_katalogus.py:6,39 · modulok/eval/kereses/korpusz.py:110 | `re.split(r"\n## Füzet\s*\n", …)` | PRESET (eval-eszköz) |

### 2.4 Tantárgy-térkép (`[pdf.tags]`) és a „diák-munkafolyamat”

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| config/os.toml:387-395 | `[pdf.tags]`: `M=Mathematics, F=Physics, T=History, I=Literature, D=Informatics, N=Grammar, E=English` (a legfelső vaultmappa első betűje) | USER DATA (a betű→címke térkép a felhasználó vaultjából) |
| core/pdfkiemeles.py:32,56-58 | `ALAP_TAGS = {"M": "Mathematics", "F": "Physics", "T": "History", "I": "Literature", "D": "Informatics", …}` — kód-tartalék a `[pdf.tags]` mellett | TÖRLÉS (az alapérték legyen üres) |
| core/tracker.py:60,177-180 | `EGYEB = "Egyéb"`; `tantargy(cfg, ut)` a legfelső mappa első betűje | CONFIG |
| core/asszisztens/szokas.py:24-27,73,91 | `EGYEB = "Egyéb"`, `NAPOK`/`NAPON` magyar nap-nevek („szerda este matek”) | PRESET (nyelvi profil) |
| core/asszisztens/beallitasok.py:45-46 · config/os.toml:962 | `tantargy_nevek`: History→„történelem”, Literature→„irodalom”, Mathematics→„matematika”, … | USER DATA / PRESET |
| core/videolanc.py:219,237,302 · modulok/ytdlp/integralas.py:164 · core/osszefoglalas_feladat.py:122 · core/kartya_feladat.py:102 | `[pdf.tags]` használata téma-mappa és automatika-szűrés szabályaként (a workflow-, napló-, projekt-, sablonmappák kizárása) | CONFIG |
| modulok/ytdlp/integralas.py:59-60,75 | `TARGY_TERKEP = {"Történelem": "T", "Irodalom": "I", "Magyar nyelv": "N", "Nyelvtan": "N", "Matematika": "M", "Fizika": "F", "Digitális kultúra": "D", "Angol": "E"}` | USER DATA / PRESET (a `[pdf.tags]` fordítottja — duplikált igazság) |
| core/naptar.py:63-78 | `TARGYAK` (Matematika, Fizika, Történelem, Irodalom, Nyelvtan, Német, Angol, Digitális kultúra, Biológia, Kémia, Földrajz, Programozás) + `CSOPORTOK = {"magyar": [...]}` | PRESET (a komment szerint `[naptar.targyak]` bővítheti, de az alap magyar középiskolai készlet) |
| core/naptar.py:33-50 | `KATEGORIAK`: „Me-time és programok”, „Tanulás”, „Órarend”, „Edzés”, „Határidők és dolgozatok”, „Egyéb”, „Kizárva” + magyar/angol kulcsszavak (`konditerem`, `kondi`, `suli`, `tanora`, `nevnap`, `siri`…) | PRESET |
| core/naptar.py:55-58 | `DOLGOZAT_SZAVAK = ["dolgozat", …, "tz", "ropdolgozat", "ropi", "zh", …]`, `HATARIDO_SZAVAK` (`ropi`/`ropdolgozat` a fejlesztő iskolai szóhasználata) | PRESET / USER DATA |
| core/naptar.py:139 | `("dolgozat", "temazaro", "vizsga")` összetett szavas felismerés | PRESET |
| modulok/fuzet/lanc.py + katalogus.py + modszer.py (FEJEZET_PROMPT:33-36) | „A tantárgyak és fejezeteik (kód – cím)” — a füzetlánc a tárgy-/fejezetmappa struktúrát feltételezi | USER DATA |
| modulok/ytdlp/config/config.yaml:119-200 | `subjects.taxonomy`: Történelem, Irodalom, Magyar nyelv, Matematika, Filozófia, Etika, Társadalomismeret, Testnevelés és sport, Fizika, Informatika, Angol …; `aliases` (tortenelem, matek, tori …); `provider_names` zanza.tv→„Zanza”, `cs50.harvard.edu`→„CS50” | USER DATA / PRESET |
| modulok/ytdlp/src/msp/subjects.py:3-9 | „The subject name should match the Manifold vault's own taxonomy character for character” | USER DATA |
| modulok/ytdlp/tortenelem-hatralevo.txt:1-20 | zanza.tv „Történelem” 17 témakör URL-lista a fejlesztő folytatandó letöltéséhez | TÖRLÉS |
| modulok/ytdlp/kotes_modell.json:1-4 | logisztikus verifikátor-együtthatók: „1140 olvasott pár, 106 videó, mind T tárgy” a fejlesztő vaultján tanítva | INSTALLATION DATA / PRESET (újratanítandó vagy semleges alap) |
| modulok/ytdlp/kotes.py:30,33 · egyezes.py:15 · itelet.py:4 · szovegreteg.py:20 | a legacy `calibration.json` mért küszöbei (`tema_besorolas`, `jeloltallitas`, `szoto_prefix_hossz`) a fejlesztő magyar történelem-vaultján mérve | INSTALLATION DATA (a küszöbök kalibrációja gép/vault-függő) |

---

## 3. Személyes identitás

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| shell/Info.plist:10 | `CFBundleIdentifier = local.manifold-os.app` (nem valódi, regisztrálható azonosító) | CONFIG (valódi reverse-DNS bundle id a kiadáshoz) |
| shell/Info.plist:5 | `CFBundleDevelopmentRegion = hu` | MARAD (felületi nyelv; lásd 4. kategória) |
| core/doctor.py:367-368 | `APP_AZONOSITO = "local.manifold-os.app"`, `HOME_KIVETEL = "Library/Preferences/local.manifold-os.app.plist"` | CONFIG (a bundle id-ből képezve) |
| core/doctor.py:394-409,899 | `alairas_tipus(codesign -dv …)`, `codesign --verify --deep --strict` | MARAD (az aláírás-ellenőrzés általános) |
| shell/build.sh:6,18-22,38-43 | `MOS_ALAIRAS_IDENTITAS="Manifold Helyi Alairas"`; a `security find-identity -p codesigning` a helyi önaláírt tanúsítványt keresi | INSTALLATION DATA (a tanúsítvány gépenkénti; kiadáshoz Developer ID + notarizálás kell) |
| docs/KIADAS.md:63-80 | a `Manifold Helyi Alairas` önaláírt tanúsítvány létrehozásának lépései („a *te* tanúsítványoddal íródik alá”) | TÖRLÉS/CONFIG (fejlesztői leírás) |
| shell/build.sh:30 | `-target "arm64-apple-macos13.0"` | PRESET (cél-architektúra/min. macOS) |
| core/snapshot.py:44,162-163,227-228 | `AUTHOR = ("Manifold-OS", "mos@localhost")` — a pillanatkép git-identitása | MARAD (generikus, nem személyes) |
| tools/mac/02_legacy_referencia.sh:42 | `git -c user.name="Manifold Mac-szkript" -c user.email="mac@localhost"` | TÖRLÉS |
| tools/mac/_kozos.sh:12-21 | `origin` remote, `gh auth login`, „szólj a cloud-chatnek”, GitHub Desktop útmutató | TÖRLÉS (a fejlesztő Claude-chat + GitHub Desktop munkafolyamata) |
| tools/mac/README.md · 01_feltoltes.sh · 03_kapuk.sh:47 · 04_main_frissites.sh | `origin/mac-main`, `origin/mac-ag/<név>`, `origin/mac-jelentes/<idő>` ágak | TÖRLÉS |
| core/emlekezteto.py:1,44 · config/os.toml:190,202 · shell/Sources/Naptar.swift:286 | Emlékeztetők „Manifold” lista: `lista = "Manifold"`, `static let alapLista = "Manifold"` | CONFIG (alap marad, a felhasználó átnevezheti — már konfigurálható) |
| config/os.toml:203 | `forras = ""` (fiók, pl. iCloud) | CONFIG (jó alapérték) |
| config/os.toml:198 | `tanulas_naptar = ""` (a naptár azonosítója/neve) | USER DATA |
| modulok/kartya/apkg.py:57 | `PAKLI_ALAP = "Manifold"` (Anki-pakli neve) | MARAD (termék-név) |
| config/os.toml:504-826 (modell-repók), config/letoltes.toml:27,110,145,156,167,272,363 | `mlx-community/Qwen3.5-9B-MLX-4bit`, `1qh/chandra-ocr-2-4bit-mlx`, `Trendency/whisper-large-v3-hu` stb. (a repók kétszer: os.toml regiszter + letoltes.toml; a tesztek ellenőrzik az egyezést) | PRESET (a modell-regiszter szállítható, de egy forrásból; a `letoltes.toml` a repó-azonosítók helye) |
| modulok/ytdlp/config/config.yaml:80,86 | `model: "mlx-community/whisper-large-v3-turbo"`, `large-v3-turbo` | PRESET |
| core/doctor.py:30,816 | `ENV_UTAS = ("UV_", "PIP_", "XDG_", "HF_", "TMPDIR", "MOS_", …)` | MARAD |
| (nincs találat) | Apple ID, e-mail-cím, valódi naptár-azonosító a kódban | — (tiszta) |

---

## 4. Nyelvi kötés (magyar a logikában, nem a felületi szövegekben)

### 4.1 Core / modulok logika

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| core/sablon.py:37,40-57 | `ALAP_NYELV = "hu"`; `"hu": {"honap": ["január", …], "nap": ["hétfő", …], "nap_rovid": ["hét","kedd","sze",…], "honap_rovid": ["jan.","feb.","márc.",…]}` + `"en"` | PRESET (a `[sablon] nyelv` már konfigurálható: os.toml:177; alapérték nyelv-függő legyen) |
| core/felkeszultseg/ertekeles.py:47-54 | `HONAPOK = ("január", …)`; `„október 7.” — az év nélküli magyar dátum` | PRESET (nyelvi profil) |
| core/felkeszultseg/ertekeles.py:130-138 | `PROMPT = """Te egy tanulási asszisztens vagy. Egy diák dolgozatra való felkészültségét…"""` — „3–5 mondat magyarul, tegező” | PRESET (nyelvi profil + „diák” feltételezés) |
| core/felkeszultseg/ertekeles.py:178 | „az „egy”, a „hét” (nap) és a „hat” nem számít számnak (főnév/névelő/ige)” — magyar szám-heurisztika | PRESET |
| core/felkeszultseg/eredmeny.py:39-67 | magyar szabad szöveg-regexek: `pont\w*`, `_FELTETELES (volna|lenne…)`, `_JOVO (lesz|várhatóan|remélem|tippelek…)`, `_SZANDEK (érek|kapok|szerzek…)`, `_KOZELITO (kb|kábé|körülbelül|nagyjából…)`, `_BIZONYTALAN (szerintem|gondolom…)`, `_OSSZESITETT (átlag|félév|tanév…)`, `_ERO (lett|kaptam|eredmény…)`, `_SZAZALEK_RAG (át|ét|kal|kel|ra|re|ig|ban|ben|nál|nél)` | PRESET (nyelvi profil; a dolgozat-eredmény-kinyerő magyar nyelvű szabad szövegre épül) |
| core/felkeszultseg/eredmeny.py:220-225 | `MEZO_KULCS = "Eredmény"`, `eredm[eé]ny::` | PRESET |
| core/asszisztens/szokas.py:25,27 | `NAPOK = ("hétfő", "kedd", …)`, `NAPON = ("hétfőn", "kedden", …)` (ragozott alak: „szerda este matek”) | PRESET |
| core/asszisztens/emlites.py:53-54,79-89 | `_NYELVTANI_NEVELO = frozenset({"a","az","egy"})`, `_KEZDO_NEVELO = r"^(?:(?:a|az|egy)\s+)+"` — magyar névelők a linkjavaslatban | PRESET |
| core/index/hibrid/normal.py:15-27 | `TO_HOSSZ = 6`, `MIN_HOSSZ = 3`, `TOLTELEK = frozenset("a az es egy hogy nem is mi mit … ban ben bol nak nek val vel tol rol hoz hez …")` — magyar töltelékszavak és ragok, 6-betűs „tő” | PRESET (nyelvi profil; ez a hibrid keresés lexikai ága) |
| core/index/kereses.py:3,52 · tar.py:6 · feloldas.py:17,165 | „ékezetfüggetlen” keresés: FTS5 `unicode61 remove_diacritics 2` | MARAD (általános Unicode-viselkedés; nyelvfüggetlenül működik) |
| modulok/kapuk/tokenek.py:3-28,36-44 | `TOVEK_HOSSZ = 5`; `FUGGVENYSZOK = {hogy nem egy vagy mint aki ami amely … sem soha senki semmi nelkul ket szerint kozul}`; `NEGATOROK = {"nem","sem","soha","senki","semmi","sehol","semmilyen","nelkul","ne","se"}`; `_SZAMRAG` („60-ban”) | PRESET (a közös forráshűség-kapu — kvíz/kártya/összefoglaló/vault-válasz elfogadása — a magyar toldalékolásra hangolt 5-betűs tőre és magyar tagadószavakra épül) |
| modulok/kapuk/forras.py:194-200 · huseg.py:124-139 · meres.py:115-145 | `nevtovek`, `tagado`, mondatkezdő nagybetű = nem tulajdonnév (magyar szabály) | PRESET |
| modulok/eval/kozos/tavolsag.py:17-28 | `tovek(s, n=5, min_hossz=3)` „a magyar toldalékolás miatt” | PRESET |
| modulok/eval/kozos/kijeloles.py:8,90 | „„magyar” próba: ékezetes magyar betű, kevés angol függvényszó” — a válasz nyelvének ellenőrzése | PRESET |
| modulok/cpp/ai.py:190-192,229-234 | `_AKCENT = [áéíóöőúüű]`, `_MAGYAR_SZAVAK = frozenset("az egy és nem hogy van …")`, `magyar_arany()` | PRESET |
| modulok/cpp/ai.py:72,89 | prompt: „Adj háromlépcsős tippet magyarul…”, „…írd le magyarul…” | PRESET |
| modulok/fuzet/kep.py:38-41,227-243 | `STOP = frozenset("a az és is vagy hogy nem de ha … feladat feladatok példa megoldás")`, `_SZO = [^\wáéíóöőúüű…]`, `tovek(s, n=5)` | PRESET |
| modulok/ytdlp/szovegreteg.py:20 | `K = 7  # szótő-előtag` (legacy `szoto_prefix_hossz`) | PRESET |
| modulok/ytdlp/egyezes.py:108 | „évszám-ELŐFORDULÁSAI: … ragozott háromjegyű, évszázad a közepével” — magyar évszám-heurisztika | PRESET |
| modulok/ytdlp/egyezes.py:347,369,384 | `nyelv != "hu"`, `auto = nyelv == "hu" and (harom or jel4)` — a lexikai téma-besorolás **csak magyarra** „mérhető” | PRESET |
| modulok/ytdlp/integralas.py:396,441 | `nyelv = itelet.norm_lang(r.get("nyelv")) or "hu"`; `if nyelv != "hu"` | PRESET |
| modulok/ytdlp/itelet.py:20-26,116-123 | `TEMA_PROMPT_TARTALOM = "Egy magyar oktatóvideó gépi átirata következik…"`, `TEMA_PROMPT_METAADAT`, `KOTES_PROMPT`; `_NEVELO = ^(?:A|Az)\s+`; „Válaszolj egyetlen szóval: igen,…” | PRESET |
| modulok/kviz/promptok.py:9 | `GENERALO_PROMPT = """Egy magyar középiskolás diák tankönyvi jegyzetének részlete következik…"""` | PRESET (nyelv + célközönség) |
| modulok/kviz/generalas.py:188,335 | „A magyar névelő („A helyes…”) nem betűválasz” — az A–D válasz-felismerés magyar névelő-kivétele; „`mellérendelő` ≠ `mellékmondat`”, „hang → hangot” tő-szabály | PRESET |
| modulok/osszefoglalas/promptok.py:12,30 | „Foglald össze az alábbi {mit} magyarul, {k} állításban…” | PRESET |
| modulok/kartya/generalas.py:41,48 | „Készíts {k} tanulókártyát az alábbi jegyzetrészletből, magyarul…”, „Válaszolj a kérdésre röviden (legfeljebb 12 szóval)…” | PRESET |
| modulok/eval/szoveg/feladat.py:51 · eval/ocr_kezi/feladat.py:28 | „…magyarul (8–14 kártya)…”, „Írd át pontosan, magyarul…” | PRESET |
| modulok/fuzet/modszer.py:33-49 | `FEJEZET_PROMPT`, `VALASZTO_PROMPT`, `FORGATAS_PROMPT = "Olvasd el … magyarul."` | PRESET |
| core/index/hibrid/kerdezz.py:66 | `PROMPT = """Válaszolj a kérdésre KIZÁRÓLAG az alábbi, számozott forrásokból…"""` | PRESET |
| core/kiegeszites_modell.py:30,46,50 | angol meta-prompt „… from a Hungarian Markdown note … in Hungarian” | PRESET |
| core/modell/bench.py:29-31,93 | prompt: „Egy oktatóvideó részletét és egy tankönyvi jegyzet részletét látod… Válaszolj egyetlen szóval: igen vagy nem”, „Foglald össze öt mondatban magyarul” | TÖRLÉS (mérési segéd) |
| core/atirat.py:26,43 · config/os.toml:383 | `ALAP_NYELVEK = ("hu", "en")`; `[media] nyelvek = ["hu","en"]` (felirat-elsőbbség) | CONFIG (már konfigurálható; alap legyen a rendszer nyelve) |
| core/modell/kliens.py:187 | `def atir(…, nyelv: str | None = "hu", …)` — a beszédfelismerés alap nyelve | CONFIG |
| core/modell/worker.py:200 | „a nyelv egy nyelvkód legyen (pl. hu)” | MARAD |
| modulok/ytdlp/config/config.yaml:42,61-65,81-82,97,194 | `language: "hu"`, `languages: ["hu","en"]`, „Hungarian suffixes work (“kozepkorban” contains “kozepkor”)” | CONFIG |
| config/os.toml:603-612 · config/letoltes.toml | `whisper_large_v3_hu` (`Trendency/whisper-large-v3-hu`, magyar finomhangolt) és `whisper_hu_turbo` a regiszterben | PRESET (nyelvi csomag) |
| core/server.py:65 | `<html lang=\"hu\">` a betöltő-lapon | CONFIG |
| shell/Info.plist:5 | `CFBundleDevelopmentRegion = hu` | CONFIG |

### 4.2 Felület (nem szöveg, hanem formázás/rendezés/nyelvkód)

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| app/src/ma/datum.ts:27-28 | `new Intl.DateTimeFormat('hu-HU', …)` (HONAPOK, ROVID) | CONFIG (egy `locale` a felületi beállításból) |
| app/src/bazis/ertek.ts:6-8 | `Intl.NumberFormat('hu-HU')`, `DateTimeFormat('hu-HU')` ×2 | CONFIG |
| app/src/hej/ErtesitesElozmeny.svelte:11 · hej/nezetek/Helyorzo.svelte:14-15 · hej/Allapotsor.svelte:21 · kod/KodEredmeny.svelte:47,51 · dolgozat/szoveg.ts:32,37 · szerkeszto/renderelok/plot/jellemzok.ts:128 · lib/tracker/megjelenites.ts:24,29 | `'hu-HU'` formátumok | CONFIG |
| app/src/lib/asszisztens/megjelenites.ts:41 · lib/vezerlo/megjelenites.ts:30,32,45 · lib/vault/elozmeny.ts:53 · media/pdf/magyarL10n.ts:28,122 | `'hu'` locale | CONFIG |
| app/src/lib/kereses/fuzzy.ts:207 · lib/vault/fa.ts:32 · atfedes/Paletta.svelte:21 | `new Intl.Collator('hu', …)` (rendezés — a magyar ábécé: cs, dz, dzs, gy… betűrend) | CONFIG |
| app/src/hej/Cimkek.svelte:58 · lib/vault/cimkek.svelte.ts:27 · lib/graf/kezdoallas.ts:24 | `localeCompare(…, 'hu', …)` | CONFIG |
| app/src/kartya/Pakli.svelte:46 · kviz/KvizBlokk.svelte:77 · osszefoglalas/Osszefoglalo.svelte:77 | `lang="hu"` | CONFIG |
| app/src/szerkeszto/beallitas.ts:141 · szerkeszto/notion/tablazat/szerkeszto.ts:368 | `lang: 'hu'` / `setAttribute('lang','hu')` (helyesírás-ellenőrzés nyelve) | CONFIG |
| app/src/media/pdf/magyarL10n.ts (egész fájl) | a PDF.js magyar lokalizációja | PRESET (nyelvi csomag) |

---

## 5. Gép-specifikus feltételezések

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| core/tartos.py:11-12,33-37,140-143 | `renamex_np`+`RENAME_EXCL`, `clonefile` (APFS-klón): „Más kötet vagy nem APFS: OSError (EXDEV/ENOTSUP) — tartalék másolás nincs” | MARAD (macOS/APFS követelmény; termék-döntés, a README-ben jelezni) |
| core/frame.py:5,278 | „A próba APFS-klónon fut”; `raise RuntimeError(f"APFS-klón nem sikerült: …")` | MARAD (de nem-APFS vault-kötetre tartalék/jelzés kell: pl. exFAT) |
| core/gepi_iras.py:17,44,891 | videó `tartos.klon_excl`, próbamód APFS-klónon | MARAD |
| core/doctor.py:22,254 | `TILTOTT_PYTHON = ("/Library/Frameworks/Python.framework", "/usr/bin/", "/opt/homebrew", "/usr/local")` | MARAD |
| core/doctor.py:360-363 | `.metadata_never_index` (Spotlight-kizárás a `var/`-ban) | MARAD (macOS) |
| core/doctor.py:680 | `sw_vers -productVersion` | MARAD |
| core/doctor.py:860 | „nincs működő git a PATH-on … (xcode-select --install)” | MARAD / CONFIG (a git-függőség telepítési lépés) |
| docs/ARCHITECTURE.md (3. fejezet „rendszer-git”) | a pillanatkép/visszavonás a rendszer `/usr/bin/git`-jére épül (Xcode CLT) | MARAD (vagy hordozható git: KIADAS.md 6.) |
| bin/mos:54 | `: > "$MOS_HOME/var/.metadata_never_index"` | MARAD |
| config/os.toml:49 | `sandbox_exec = "/usr/bin/sandbox-exec"` | MARAD (macOS-komponens; a CAS-homokozó/PDF-elemző/C++ futtató zárva hibázik nélküle) |
| core/index/pdfszoveg.py:154-159,261 · modulok/homokozo/__init__.py:188,207 · homokozo/program.py:100,107 · modulok/cpp/eszkoztar.py:209 | `shutil.which("sandbox-exec")`, „nincs sandbox-exec … elzáratlan futtatás nincs” | MARAD |
| core/index/pdf_profil.sb:12 · modulok/homokozo/profil*.sb | `(allow sysctl-read)` + `-D` paraméteres profilok | MARAD |
| core/index/figyelo.py:35-53,123,201-205 | `FSEvents` figyelő (`fajta = "fsevents"`, `dispatch_queue_create(b"hu.manifold.index.fsevents")`) + stat-alapú tartalék | MARAD (a `hu.manifold.index.fsevents` név TÖRLÉS/CONFIG: bundle-id-ből képezve) |
| core/modell/memoria.py:9-28 | `sysctl -n kern.memorystatus_level`, `hw.memsize` (fallback `16.0`), `vm.swapusage` | MARAD (macOS) / a `16.0` tartalék → CONFIG |
| core/modell/aktivitas.py:22,28 | `ioreg -c IOHIDSystem … HIDIdleTime` | MARAD |
| core/server.py:1016 | „a kapu jeleit (sysctl, ioreg) külön szál méri” | MARAD |
| core/modell/beallitas.py:20 · config/os.toml:414-416 | `ALAP_KERET = {"munka": 5.0, "tavol": 9.0}`; `[keret] munka = 5.0  # alap: a felhasználó dolgozik mellette`, `tavol = 9.0` — a fejlesztő 16 GB-os, ventilátor nélküli M4-ére hangolt keretek | PRESET (RAM-osztályonként: 8/16/24/32+ GB; automatikus `hw.memsize`-ből) |
| core/modell/betolto.py:3-4,126 | „14 GB a 16-ból”, „munka 5 GB, távol 9 GB; D5” | PRESET |
| config/os.toml:401-412 | `[modellgazda]` `cache_gb = 0.25`, `min_szabad_szazalek = 20`, `tartalek_szazalek = 5`, `chat_idokorlat_mp = 900` — a fejlesztő gépén mért | PRESET |
| config/os.toml:428-436 | `[ho]` hőfigyelés: „ventilátor nélküli M4”, `kuszob = 0.7`, `hutes_mp = 120` | PRESET |
| core/modell/ho.py:30-31 | `glm_ocr` alapszint 208 / 88 token/s (a fejlesztő gépén mért) | INSTALLATION DATA (`hoalap` tábla, `router.sqlite`) |
| config/os.toml:~504-860 `csucs_gb` | modellenkénti csúcs-memória („K80 (2026-10-07): mért mlx-csúcs 8,405”) | INSTALLATION DATA / PRESET |
| core/cpp_teszt.py:25,112 · config/os.toml:`[cpp] memoria_mb` | „1 MB–16 GB” memóriakorlát-tartomány | PRESET |
| config/os.toml:`[homokozo] memoria_mb = 768` | CAS-homokozó memóriakorlát | PRESET |
| shell/build.sh:28-30 | `xcrun --find swiftc`, `-target "arm64-apple-macos13.0"` | PRESET / MARAD (Apple Silicon + CLT feltétel) |
| shell/ikon/keszit.sh:22-24 | `xcrun --find swiftc`, `iconutil` | MARAD (build-lépés) |
| config/runtime-pins.env:3,6,9,17,19 | `uv-aarch64-apple-darwin`, `cpython-3.14.7+…-aarch64-apple-darwin`, `node-v24.21.0-darwin-arm64`, `imageio_ffmpeg-…macosx_11_0_arm64`, `ffmpeg-macos-aarch64-v7.1` | MARAD (Apple Silicon only; Intel Mac nem támogatott) |
| modulok/cpp/telepites.py:66,83,106-109,150,261,280 | `ISMERETLEN_CEL = "arm64e.x1"` (a macOS 27 SDK `.tbd`-je), `xcrun --show-sdk-path`, „nincs SDK a gépen (xcode-select --install)”, LLVM 23.1.2 ld64.lld | PRESET (SDK/LLVM-verzió kötés) |
| modulok/cpp/diagnosztika.py:9,33 · cpp/ellenorzes.py:241 | `arm64e?|x86_64h?`, `"arm64"` alap | MARAD |
| modulok/ytdlp/src/msp/transcription/mlx_whisper.py:3,36,46 | „Apple Silicon GPU through MLX… Apple Silicon only” | MARAD |
| core/fuzet_api.py:6,122 | `/usr/bin/osascript` + `«class PNGf»` (vágólap-kép) | MARAD (macOS) |
| core/modell/hatter.py · config/requirements.in | MLX / `mlx-vlm` / `mlx-whisper` / `mlx-audio` futtatók | MARAD (Apple Silicon only) |
| shell/Sources/Naptar.swift:2 · core/naptar_seged.py:1 · core/emlekezteto.py:18 | EventKit (Naptár/Emlékeztetők) | MARAD (macOS) |
| shell/Sources/AppController.swift:73-74 | `WKWebView`, `.nonPersistent()` adattár | MARAD |
| shell/Sources/AppController.swift:97-98,398 · CoreProcess.swift:125 · docs/ARCHITECTURE.md:40 | `NSWorkspace.willUnmountNotification` — a gyökér „kihúzható SSD”: lecsatoláskor mentés + rendezett leállás | CONFIG (SSD-s hordozható telepítés feltételezése; belső lemezes telepítésnél kikapcsolható) |
| config/os.toml:110-116 · core/teljes_mentes.py:263 | `[teljes_mentes]` külső kötetre, exFAT-hard-link megjegyzés, `cel` lemezfigyelő | CONFIG |
| config/os.toml:95-109 `[mentes] kodtar = "{os}"` + core/mentes.py | a kódtár `git bundle --all` a `{backup}`-ba: a telepített mappának **git-munkafának** kell lennie | INSTALLATION DATA (kiadott csomagban nincs `.git`) |
| docs/KIADAS.md:78 | „a `Manifold.app` a repóban követett bináris” | TÖRLÉS (kiadásnál build-artefaktum, nem forráskód) |
| core/mentes.py:49 | `ALLAPOT_STATE_MAPPAK = ("video-bejaras", "Manifold-media/itelet", "Manifold-media/kotes")` | TÖRLÉS (`Manifold-media` legacy mappanevek) |
| bin/mos:1-30 | `MOS_HOME`-ból számol; munkafa-mód (`.git` fájl), `MOS_MUNKAFA`, `MOS_BACKUP`, symlinkelt `var/` tiltása | TÖRLÉS (munkafa-mód: fejlesztői párhuzamos-chat munkafolyamat) / MARAD |
| modulok/ytdlp/scripts/crawl_all.sh:146,228-229 | `caffeinate -i -s -w $$` | MARAD (macOS) |

---

## 6. Legacy-kötés

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| modulok/ytdlp/__main__.py:114-116,348-349 | `os.environ["MOS_LEGACY"]` → `modulok/ytdlp/staging`; `staging-klon` parancs | TÖRLÉS |
| tools/mac/02_legacy_referencia.sh (17 találat) | a legacy fájlok olvasható másolata `origin/legacy-referencia` ágra | TÖRLÉS |
| modulok/ytdlp/utnorm.py:1-50 · bin/mos:275 (`video utnorm`) | legacy job-állapotfájlok út-normalizálása (264 db) | TÖRLÉS |
| modulok/ytdlp/klon.py:3,71 · staging.py:5-6 · integralas.py:98 | a legacy `staging` APFS-klónja; legacy `media_staging.py`/`media_auto.py` portja | TÖRLÉS |
| core/doctor.py:23,78,802-846 (≈26 találat) | `LEGACY_MINTA`: a doctor a legacy `var/`-ra, symlinkre, `core.worktree`-re mutatást keresi | TÖRLÉS |
| core/tasks.py:333,390 | `INSERT … 'legacy')`, `forras == "legacy"` — a legacy feladat-sorok (UI: app/src/hej/vezerlo/Valtozasok.svelte:82 „A legacy feladat változásai ebben a nézetben nem érhetők el.”) | TÖRLÉS (felhasználói szöveg is) |
| config/os.toml:29 | `video_jobs = "{state}/Manifold-media/jobs"` — „a legacy-ből átvett, a port csak olvassa” | TÖRLÉS |
| config/os.toml:35 | `fuzet = "{state}/Manifold-fuzet"` — „allapot.json (a legacy 522 kötése is)” | CONFIG (a mappa neve termék-név; a 522 kötés TÖRLÉS) |
| core/modell/bench.py:8,126 | `{state}/Manifold-media/itelet/n_kotes_minta.json` — legacy mérési minta | TÖRLÉS |
| modulok/ytdlp/integralas.py:97-98,466 | a legacy „olvasott kötés-címkék (Claude, 2026-09-20/23)” a `{state}/Manifold-media/itelet/` alól | TÖRLÉS |
| modulok/ytdlp/kotes_modell.json · kotes.py:4,30,33 · __init__.py:18 | a legacy `calibration.json → media.kotes.modell` változatlanul átvéve | INSTALLATION DATA (újratanítás) |
| modulok/ytdlp/itelet.py:4 · fuzet/modszer.py:4 · fuzet/kep.py:4 · kviz/generalas.py:48 · kviz/promptok.py:1 · kviz/mechanikus.py:14 | a legacy `calibration.json` promptjai/értékei „változatlan portja” | PRESET |
| config/os.toml:314,399 · config/letoltes.toml:14 · core/modell/beallitas.py:3 | `calibration.json → helyi_modell` / `kviz` blokk átmásolva | PRESET |
| core/szemelyes_db.py:1,26,115 · core/ma.py:3,15,33 · core/tracker.py:1,4 · core/felkeszultseg/adat.py:2,339 · core/server.py:184 | `pos.sqlite` (személyes adatbázis; a **séma** a legacy `db.py` elvéből) — a fájlnév és a `has_asszisztens`, `tr_*` táblák | MARAD (a névből „legacy” elhagyható; a fájl a felhasználó saját adata → USER DATA) |
| core/felkeszultseg/kotes.py:1 · core/ma.py:145 | `LEGACY-SZERZODESEK L59`, a legacy `szemelyes/dolgozat.py` `kotes`-e | MARAD (komment) |
| core/index/feloldas.py:3-16,116-122,251-277,330 | a feloldás a legacy `mfd`/`vaultlib` portja (az Obsidian-viselkedéshez igazítva) | MARAD (komment/algoritmus) |
| core/snapshot.py:1,648 · core/frame.py:1,137,243 · core/tulajdonsagok.py:80,209-212,269,325,420 | „a legacy `snapshot`/`kor`/`mfd.py`/`vaultlib` viselkedésre azonos portja” | MARAD (komment) |
| modulok/ytdlp/vaultoldal.py:1-11,25-37,63-117 | a vault-oldali melléklet formátuma a legacy `media.py`-val **bájtra** azonos; `SENTINEL = "<!-- manifold-media-source-note -->"`; „a vaultban 236 forrásjegyzet áll a sentinel-lel” | PRESET (a formátum maradhat; a „236 jegyzet” USER DATA-hivatkozás TÖRLÉS) |
| modulok/ytdlp/src/msp/ (a `msp` = multimedia-source-pipeline legacy másolata); modulok/ytdlp/lanc.py:6,33-47; kozvetlen.py:13,197-204; bejaras.py:5-20,121-153; modulok/ytdlp/PORT.md, docs/LEGACY-README.md | a letöltő a legacy `msp` csomag másolata (`import msp.archive/config/downloader/pipeline/crawl`) | PRESET (szállítandó, de saját névvel/csomagként; a legacy-hivatkozás TÖRLÉS) |
| modulok/ytdlp/vaultoldal.py:28 | `_INDOK = "A forras a multimedia-source-pipeline (msp) staging repojabol jott…"` — a vaultba írt szöveg | PRESET |
| modulok/ytdlp/tortenelem-hatralevo.txt | lásd 2.4 | TÖRLÉS |
| modulok/eval/tema/feladat.py:96 · keszit.py:55 · eval/kotes/feladat.py:58 · keszit.py · eval/fuzet_valaszto/feladat.py:3,148 · fuzet_forgatas/feladat.py · fuzet_fejezet/feladat.py · eval/parancslista.py:29-33 | `"legacy": LEGACY` összevetési sorok; „a legacy erős módszere (`fuzet_eros.py`)”, „a legacy két modellje (gemma-4-12B, Qwen3-VL-4B)” | TÖRLÉS (a legacy-viszonyítás mérési segéd) |
| config/vault-sema.json:2 | `_leiras`: „Az értékek a legacy kalibrációból átmásolva (2026-10-02)” | TÖRLÉS (komment) |
| tests/legacy_szabaly.py (hivatkozza: core/index/feloldas.py:15) | linkenkénti összevetés a legacy szabállyal | TÖRLÉS |
| tests/test_video_staging.py (19 `/Users|/Volumes` találat), tests/test_doctor.py (legacy-ág) | legacy út-/doctor-tesztek | TÖRLÉS |

---

## 7. Fejlesztői / Claude-artefaktumok

### 7.1 Termékbe kerülő kód

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| core/probafeladat.py:4,43-44 · core/vezerlo.py:205-209 | `MOS_PROBA_FELADAT=1` → `probafeladat.regisztral()` (a `proba` feladattípus csak tesztben/kézi próbán); docs/ARCHITECTURE.md:285 | TÖRLÉS (a production feladat-regiszterből; teszt-támogatás tests/ alatt) |
| core/gepi_kliens.py:15,129 | `MOS_PROBA=1` → minden írás APFS-klónra | MARAD (fejlesztői/diagnosztikai kapcsoló; env-vel védve) |
| shell/Sources/AppController.swift:18-19 | ablakcím: `"PRÓBA — Manifold (\(jel))"` a `MOS_PROBA_JELZES` env-ből | TÖRLÉS |
| shell/Sources/App.swift:15-24 · AppController.swift:21,56-71,99-136,257-288,386-432,458-474,507,576-606,674-770 | `--selftest[=forgatókönyv]` mód: forgatókönyvek (`core-ujraindul`, `kezfogas-ido`, `kilepes`, `lecsatolas`), `MOS_SELFTEST_JEL`, „SELFTEST OK/HIBA” kimenetek | TÖRLÉS (release-buildből; build-kapcsoló mögé) |
| shell/Sources/SelftestSzkript.swift (egész fájl) · Biztonsag.swift:35-44 · Eletciklus.swift:225 · HelyiMenu.swift:71 · Ertesites.swift:74 · CoreProcess.swift:125,156-160 | selftest-táblák beágyazva a production binárisba | TÖRLÉS (release-buildből) |
| core/naptar_seged.py:3,8 · core/csatolmany.py:289-291 · config/os.toml:47-48 | `MOS_NAPTAR_SEGED` / `MOS_HEJ_CLI` — ál-segéd tesztekhez (`tests/naptar_seged_alarm.py`) | MARAD (tesztelhetőségi kapocs) |
| core/osszeomlas.py:4,9 | `MOS_OSSZEOMLAS=<pont>` összeomlás-injektálás (`tests/osszeomlas.py` állvány) | TÖRLÉS (production útból; vagy no-op build-flag) |
| modulok/ytdlp/__main__.py:289,330,400-402 | `MOS_VIDEO_HELYI_ENGEDELY` („kizárólag a loopback-szerveres tesztek kapcsolója”), `selftest`, `test` alparancsok (`tests.test_video_selftest`) | TÖRLÉS |
| bin/mos:251-264,284 | `test`, `perf`, `video selftest|test`, `kezi` alparancsok (`tests/kezi/kapu.py`) | TÖRLÉS (kiadott CLI-ből) |
| core/doctor.py:449-466,528 | `PROBA_JELOLO = ".mos-proba.json"` (a `tests/kezi/_kornyezet.probamappa` klónjai), „tests/kezi” a doctor mappa-listájában | TÖRLÉS |
| core/modell/bench.py (egész fájl: 111,126) · core/modell/eval.py:277-322 · core/modell/__main__.py:48 · modulok/eval/ (parancslista.py, attekinto.py, osszesito.py, kijeloles_keszit.py) · modulok/kapuk/meres.py:380-439 · modulok/{kviz,kartya,osszefoglalas}/meres.py · modulok/grafikon/{meres,modell_meres}.py | mérő-/kalibrációs eszközök a fejlesztő aranyhalmazaira (`K27`, `K101`, `K135`, `C19`, `T050` hivatkozások a jelentésekben) | PRESET / INSTALLATION DATA (a mérőeszköz szállítható, az aranyhalmaz a felhasználóé; a jelentés-szövegek K/C hivatkozásai TÖRLÉS) |
| config/pillanat-kivetelek-vault.json | lásd 2.2 | TÖRLÉS |
| tests/kezi/ (38 fájl), app/tests/kezi/, app/vitest.kezi.config.ts | kézi mérőkapuk a valódi vaulton | TÖRLÉS |
| tools/mac/ (5 szkript + README) | Mac-oldali szkriptek a „cloud-chat” ↔ GitHub Desktop munkafolyamathoz | TÖRLÉS |

### 7.2 Felhasználó által látott szövegekben maradt K/C/T/D-hivatkozások

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| app/src/hej/vezerlo/Modellek.svelte:92 | `Nincs kalibrált modell: élesben nem fut (D9).` | TÖRLÉS (a „D9” kód-hivatkozás; a szöveg maradhat) |
| app/src/dolgozat/Dolgozat.svelte:330 | `title="A próbakvíz a kvíz (C22) elkészülte után indítható."` + elavult tartalom | TÖRLÉS |
| app/src/atfedes/KeresoAblak.svelte:270 | `title="… rerankerrel (C25b)"` | TÖRLÉS (kód-hivatkozás) |
| app/src/hej/vezerlo/Kerdezz.svelte:58 | „Próba: a modell erre a feladatra nem kalibrált.” | MARAD (érthető szöveg) |
| app/src/kod/KodAI.svelte:86 | „nincs kalibrált modell” | MARAD |
| core/matek_feladat.py:68 · kartya_feladat.py:60 · kviz_feladat.py:65 · osszefoglalas_feladat.py:69 · videolanc.py:309 · grafikon_feladat.py:62 | „Próbamód (D9): a … a vault APFS-klónjára kerül…” (feladat-figyelmeztetés a felületen) | TÖRLÉS (a „(D9)”) |
| core/gepi_iras.py:245,483,495,504,513,785,809,822 | `Invalid(… (D9))`, `(L12)`, `(L33)`, `(L36)` — HTTP-hibaüzenetek a felületen | TÖRLÉS (a hivatkozások; a szöveg maradhat) |
| core/modell/worker.py:119 · router.py:60-76 | „élesben csak kalibrált modell fut (D9)…mos eval … --kalibralt”, „a kalibrációt a C19 mérése adja” | TÖRLÉS (a hivatkozások) |
| core/modell/eval.py:277,280,322 · core/modell/kalibracio.py:124-125 · core/modell/__main__.py:48 | „(C19, T050)”, „előbb a jóváhagyás (K27)”, „✓ kalibrált (D9)” (CLI) | TÖRLÉS |
| core/frame.py:258 · core/doctor.py:73,177,363 | „(L13)”, „(C11b)”, „(T099)”, „(L50)” a doctor/üzenetekben | TÖRLÉS |
| core/modell/kapu.py:41 | „az app nemrég indult (D8)” (állapot-ok szövege) | TÖRLÉS |
| modulok/kviz/lanc.py:138 · kartya/lanc.py:150 · osszefoglalas/futtat.py:117 · matek/lanc.py:72 · grafikon/modell_hivo.py:56 · cpp/ai_futas.py:135 · fuzet/modell.py:51 · ytdlp/modell.py:51 · ytdlp/__main__.py:250 | „…nincs kalibrált modell (D9): élesen nem készül kvíz/kártya/összefoglaló…” + a **konkrét modellnév a súgóban**: `--olvaso qwen35_9b` (fuzet/modell.py:51) | TÖRLÉS (D9) / CONFIG (modellnév) |
| modulok/ytdlp/integralas.py:392 | „…nincs kalibrált modell (K29): a tétel a…” | TÖRLÉS |
| modulok/cpp/eszkoztar.py:72 | „linker a fordító-profil alatt nem futhat (K168)…” | TÖRLÉS |
| core/felkeszultseg/__main__.py:130 · modulok/*/__main__.py (kviz:124, kartya:130, osszefoglalas:151, kapuk:76, cpp:276, fuzet:79) | argparse `description="… (C22a, C22b)"`, `help` szövegek C-hivatkozással | TÖRLÉS |
| modulok/*/__main__.py `--proba` súgók (kviz:136, kartya:135, osszefoglalas:168, matek:219, grafikon:235-238, ytdlp:379, fuzet:10) | „az írás a vault APFS-klónjára (D9)” | TÖRLÉS (a hivatkozás) |
| config/os.toml (szinte minden szakasz) | `C23b`, `K160`, `K291`, `K135`, `CX-011`, `T142`, `L49`, `D8`, `NAPLO C18.1` hivatkozások a kommentekben és a `meres_kihagy` kulcsok értékeiben | TÖRLÉS (a kommentek; a `meres_kihagy` indoklások a fejlesztő mérési naplói) |
| app/src/**/*.svelte, *.ts | ~500 `(C12b)`, `(K176)`, `(T058)`, `(L42)` stb. hivatkozás **kommentekben** (nem látható a felhasználónak); felületi szövegekben csak a fenti 3 | TÖRLÉS (komment-tisztítás, nem sürgős) |
| core/*.py, modulok/*.py | ~570 fájlban K/C/T/D/L/CX hivatkozás docstringekben | TÖRLÉS (komment-tisztítás, nem sürgős) |
| core/doctor.py:528 | `"tests/kezi"` a mappa-listában | TÖRLÉS |
| core/ma.py:8 · core/felkeszultseg/kalibracio.py:3,223 | felhasználói üzenet: „… lezárt dolgozat kell, amelyhez van számszerű eredmény a „Dolgozat kiértékelő” jegyzetben…” | CONFIG |

---

## 8. Beégetett modellnevek a felületen / a core üzeneteiben

A felület (`app/src`) **nem** éget be modellnevet: a „Modellek” és „Rendszer” nézetek a core regiszteréből, dinamikusan jelenítik meg (app/src/hej/vezerlo/Modellek.svelte, Rendszer.svelte:71-83). A beégetett nevek a core/modulok oldalán vannak.

| fájl:sor | részlet | javasolt sors |
|---|---|---|
| modulok/fuzet/modell.py:51 | felhasználói hibaüzenet: `próbához adj meg modellt (pl. --olvaso qwen35_9b) és --proba-t (D9)` | CONFIG (a regiszterből választott példa) |
| modulok/eval/fuzet_forgatas/feladat.py:29 | `FORGATO = "qwen35_9b"` | PRESET / CONFIG (a router döntse) |
| modulok/eval/fuzet_valaszto/feladat.py:39,46,102,146 | `OLVASO = "qwen35_9b"`; `"modszer": "Qwen3.5-9B olvasó … + gemma-4-12B választó"`; hibaüzenet `({OLVASO} · fuzet_fejezet)` | PRESET |
| modulok/eval/parancslista.py:28-34,44 | `UTASITHATO_VLM = ("qwen35_9b","gemma4_12b","qwen3_vl_4b","qwen35_4b")`, `VALASZTO_JELOLT = ("gemma4_12b","qwen35_9b","qwen35_4b","gemma4_e4b")`, `TARSITAS_JELOLT = (...)`, `TPS = (80, 40, 20)` | PRESET (a jelölt-listák a regiszter `feladat` mezőjéből levezethetők) |
| modulok/osszefoglalas/formatum.py:12 · kviz/formatum.py:11 | docstring-példa `Modell: "qwen35_9b"` | MARAD (komment) |
| modulok/kviz/lanc.py:11,13 | komment: „a `qwen35_9b`”, „a Qwen3.5-család `max_tokens_szorzo`-ja” | MARAD |
| modulok/grafikon/modell_hivo.py:7 | komment: „`qwen35_4b`” | MARAD |
| modulok/kartya/meres.py:3 · osszefoglalas/meres.py:3 · kviz/meres.py:4 · grafikon/modell_meres.py:3 | CLI-használat `--modell qwen35_4b` | MARAD (komment) |
| core/modell/ervenyesseg.py:17-21 | komment: `glm_ocr`, `paddleocr_vl_16`, `ministral3_3b`, `qwen3_vl_4b`, `qwen35_2b`, `phi4_mini_reasoning` mért arányok | TÖRLÉS (komment: a fejlesztő mérései) |
| core/modell/ho.py:30-31 · betolto.py:3 · hatter.py:7 · fuzet_api.py:7 · letoltes.py:12 | komment/súgó: `glm_ocr`, `qwen3_vl_4b`, `gemma-4-12B`, `parakeet`; `mos letoltes glm_ocr parakeet_v3` (használati példa) | MARAD (komment) / CONFIG (a súgó példa) |
| core/index/hibrid/frissites.py:32 | komment: `"bge-m3:nincs"`, `"e5:query/passage"` | MARAD |
| config/os.toml:~499-860 `[modellek.*]` | modell-regiszter (qwen35_9b, gemma4_12b, qwen3_vl_4b, bge_m3, glm_ocr, chandra_ocr2, dots_mocr, nanonets_ocr2, parakeet_v3, whisper_*, ministral3_*, nemotron…, seed_coder…); `feladat = […]` a router-feladatkiosztás; `meres_kihagy` indoklások | PRESET (szállítható regiszter; a `meres_kihagy` TÖRLÉS) |
| config/os.toml:~446 `[router.feladat.ocr_kezi] tavolra_var = true  # a füzet ma a 9B+12B-vel 87/97` | modell-adat a kommentben, router-szabály | PRESET |
| config/os.toml:~480-500 `[meres.feladat.*]` | modellfüggő mérés-szabályok (repetition_penalty, gondolkodas) | PRESET |
| modulok/ytdlp/config/config.yaml:58,80-86 | `mlx_whisper`/`faster_whisper` modell-nevek | PRESET |
| app/src (összes) | (nincs beégetett modellnév) | — |

---

## 9. Tesztek (külön megjegyzés)

- `tests/` 264 fájl; ~72 említ `/Users|/Volumes|.obsidian|iCloud|Manifold-backup` mintát (túlnyomóan `.obsidian` álvault-jelzés — MARAD), ~132 vault-konvenciós nevet használ (`ATTCHMNTS`, `T01 - Történelem`, `X01`), ~108 `Tags/Source/Status/NN` frontmattert. Ez a szintetikus fixture-ek ára: a konvenciók kiemelésekor a fixture-generátort (`tests/bazis_segedek.py`, `index_segedek.py`, `helpers.py`) kell paraméterezni.
- `tests/kezi/` (38 fájl): a fejlesztő valódi vaultját/klónját igénylő kapuk → TÖRLÉS a kiadott csomagból.
- `tests/legacy_szabaly.py`, `tests/test_video_staging.py`, `tests/test_doctor.py` legacy-ága → TÖRLÉS a legacy-ágakkal.
- `app/tests/` 166 fájl: ~45 vault-konvenciót használ; `app/tests/kezi/*.kezi.ts` TÖRLÉS.
- `tests/test_config.py:14` `"/hazi/Manifold-backup"` — álhome (MARAD).
- `tests/test_eval_feladatok.py:53` `assertNotIn("/Volumes/", s, p)` — jó őr, MARAD.

---

## (a) A 15 legsúlyosabb kötés, rangsorolva

| # | Kötés | Hol | Miért súlyos | Sors |
|---|---|---|---|---|
| 1 | **Modell-kalibráció és aranyhalmazok a fejlesztő saját anyagán.** Élesben csak „kalibrált” modell futhat (D9); a `var/router.sqlite` üresen indul, a kalibrációt a fejlesztő füzetfotóin/vaultján mért aranyhalmazok adják. Új telepítésen minden AI-funkció (kvíz, kártya, összefoglaló, füzet, matek, OCR, átirat, kód-AI) „nincs kalibrált modell” hibát ad. | core/modell/router.py:53-76 · core/modell/kalibracio.py:1-8 · core/modell/worker.py:119 · modulok/{kviz,kartya,osszefoglalas,matek,grafikon,cpp,fuzet,ytdlp}/… „nincs kalibrált modell (D9)” · modulok/eval/*/ (aranyhalmazok) | A termék AI-fele új felhasználónál működésképtelen; a kalibrációs adat személyes (a fejlesztő magyar középiskolás jegyzetei, füzetfotói) | INSTALLATION DATA + PRESET (szállított alap-kalibráció / első indítási mérés a felhasználó saját mintáján) |
| 2 | **Egyetlen, személyes alapértékű konfigfájl a kódtárban, felhasználói réteg nélkül.** | config/os.toml (998 sor) · core/config.py:46-80 (csak `[utak]` MOS_* env + `MOS_CONFIG`) | Minden felhasználói beállítás (vault, naplóút, tantárgy-térkép, emlékeztető-lista, füzetmappák) a kód frissítésével ütközik | CONFIG (user-config overlay `~/Library/Application Support/…`) |
| 3 | **A vault-struktúra mappanevei beégetve** (`ATTCHMNTS - cards/quizes/summaries/Videos/photos`, `Média`, `_Template`, `X01 - Napló & To-Do`, `AI01/AI02/AI03`, `Prjct01`, `Elmélet`) — kb. 20 core/modul fájlban + 6 felületi tükör-konstans | core/automatika.py:47 · core/index/hibrid/hasonlo.py:23 · core/{osszefoglalas,kviz,kartya}_api.py · core/gepi_iras.py:818-821 · core/atirat.py:24 · core/asszisztens/beallitasok.py:7,18,44 · modulok/ytdlp/egyezes.py:38 · app/src/{kartya,kviz,osszefoglalas}/allando.ts:4 · app/src/szerkeszto/renderelok/plot/beiras.ts:16 | Más vaultban a gépi írás rossz helyre ír, az automatikák saját kimenetükre indulnak, a kapuk rosszul szűrnek | CONFIG (+ USER DATA az első indításkor; egy „kísérő-előtag” a configból, a felület a core-tól kapja) |
| 4 | **Magyar nyelvű forráshűség-kapu és hibrid keresés** (5/6-betűs „tő”, magyar függvényszavak és tagadószavak, ragok) — minden gépi írás elfogadási feltétele. | modulok/kapuk/tokenek.py:3-44 · core/index/hibrid/normal.py:15-27 · modulok/kapuk/{forras,huseg,meres}.py · modulok/eval/kozos/tavolsag.py:26 · modulok/fuzet/kep.py:38 | Más nyelvű jegyzeteknél a kapu hamisan elutasít/elfogad; a keresés tövezése értelmetlen | PRESET (nyelvi profil: stopszavak, tő-hossz, tagadószavak) |
| 5 | **Frontmatter-séma mint kód** (`Tags/Source/Status/NN/Canvas`) a váz-sablonokban, a felület kulcs-listáiban és a séma-kapuban; `status_gazdai` | core/pdfkiemeles.py:71-72 · core/naplo.py:74 · core/cpp_teszt.py:249-252 · modulok/ytdlp/vaultoldal.py:238-241 · core/gepi_iras.py:747,785,809 · app/src/szerkeszto/tulajdonsagok/ertek.ts:80-82 · config/vault-sema.json | Más tulajdonságnevű vaultban a gépi írók „sémasértést” okoznak vagy rossz vázat írnak | PRESET (séma-profil; a váz a profilból generálódik) |
| 6 | **Diák-/tantárgy-munkafolyamat beégetve:** tantárgy = a legfelső mappa első betűje (`[pdf.tags]`), `<Betű><két szám> - <cím>` témamappa, `Dolgozatok/ÉÉÉÉ-HH-NN - Tantárgy.md`, „Dolgozat kiértékelő”, magyar iskolai naptár-kulcsszavak (`ropi`, `tz`, `suli`), „magyar középiskolás diák” prompt | config/os.toml:387-395 · core/tracker.py:177 · core/videolanc.py:207 · modulok/ytdlp/egyezes.py:37 · core/naptar.py:33-78 · core/felkeszultseg/* · modulok/kviz/promptok.py:9 | A tracker, a felkészültség, a naptár-kategorizálás, a video-bevitel egy konkrét iskolai tanulási rendszert feltételez | PRESET (opcionális „Tanulás/iskola” modul-csomag; a magja tantárgy-független) |
| 7 | **Személyes adat a kódtárban:** `config/vault-sema.json` (tags-értékkészlet, `X03 - Books`, `Prjct01`, `emelt matematika témakörök.pdf`), `config/pillanat-kivetelek-vault.json` (a fejlesztő vault.git commit-hashei), `modulok/ytdlp/kotes_modell.json` (1140 pár, „mind T tárgy”), `tortenelem-hatralevo.txt` | lásd 2.2, 2.4 | Privát adat kerülne ki a kiadott csomagban; a modell az ő vaultjára tanított | TÖRLÉS / USER DATA / INSTALLATION DATA |
| 8 | **Legacy-híd:** `msp` másolat, `utnorm`, `MOS_LEGACY`, `staging-klon`, doctor `LEGACY_MINTA`, `tasks` `'legacy'` forrás, `Manifold-media`/`Manifold-fuzet` állapot-mappák | modulok/ytdlp/{utnorm,klon,__main__}.py · core/doctor.py:23,78,802-846 · core/tasks.py:333,390 · core/mentes.py:49 · config/os.toml:29,35 · tools/mac/02_legacy_referencia.sh | Új felhasználónak értelmetlen kód- és UI-szöveg („A legacy feladat változásai…”), hibaforrás | TÖRLÉS |
| 9 | **Hordozható-SSD telepítési modell:** `work = {os}/..`, `vault = {work}/Manifold`, kötet-lecsatolás figyelés, külső kötetre teljes mentés, `~/Manifold-backup`, `mentes.kodtar = {os}` (git-munkafa), `Manifold.app` a repóban követett bináris | config/os.toml:11-12,53,95-116 · shell/Sources/AppController.swift:97-98 · core/mentes.py · docs/KIADAS.md:78 | Normál telepítésnél (belső lemez, /Applications, nincs `.git`) a mentés, a doctor és a gyökér-keresés feltételei nem teljesülnek | CONFIG + INSTALLATION DATA (telepítési profil: portable / standard) |
| 10 | **Aláírás és azonosító:** `local.manifold-os.app`, `Manifold Helyi Alairas` önaláírt tanúsítvány, ad-hoc aláírás (minden újrafordítás új „app”) | shell/Info.plist:10 · shell/build.sh:6-43 · core/doctor.py:367-368,394-409 · docs/KIADAS.md:63-80 | Terjesztéshez Developer ID + notarizálás + valódi bundle id kell; a doctor a régi azonosítót ellenőrzi | CONFIG / INSTALLATION DATA |
| 11 | **Fejlesztői/teszt-hookok a production binárisban és CLI-ben:** `--selftest` forgatókönyvek (SelftestSzkript.swift), `MOS_PROBA_FELADAT`, `MOS_OSSZEOMLAS`, `MOS_VIDEO_HELYI_ENGEDELY`, `bin/mos test|perf|kezi|video selftest`, „PRÓBA — Manifold” ablakcím | shell/Sources/App.swift:15-24 · AppController.swift · core/vezerlo.py:208 · core/osszeomlas.py · bin/mos:251-284 | Támadási felület és zaj; a selftest-táblák a fejlesztő SSD-nevét tartalmazzák | TÖRLÉS (release build kizárja) |
| 12 | **Memóriakeretek a fejlesztő 16 GB-os M4-ére:** `[keret] munka 5.0 / tavol 9.0`, `ALAP_KERET`, `hw.memsize` tartalék 16.0, `[ho]` ventilátor nélküli M4, `csucs_gb` mért értékek | config/os.toml:414-436 · core/modell/beallitas.py:20 · core/modell/memoria.py:24 · core/modell/betolto.py:3-4,126 | 8 GB-os gépen egy modell sem fér be; 32+ GB-os gépen indokolatlanul szűk | PRESET (RAM-osztály szerinti keretek, automatikus felismerés) |
| 13 | **Felületi nyelvkódok és rendezés (`hu`, `hu-HU`, `Intl.Collator('hu')`, `lang="hu"`)** ~35 fájl a felületen; core: `<html lang="hu">`, `CFBundleDevelopmentRegion=hu`, `atir(nyelv="hu")`, `[sablon] nyelv`, `[media] nyelvek` | app/src/ma/datum.ts:27-28 · app/src/bazis/ertek.ts:6-8 · app/src/lib/kereses/fuzzy.ts:207 · app/src/lib/vault/fa.ts:32 · core/server.py:65 · core/modell/kliens.py:187 | Más nyelvű felhasználónak rossz dátum/szám/rendezés, rossz helyesírás-ellenőrzés | CONFIG (egy `locale` beállítás) |
| 14 | **Fejlesztői hivatkozások a felhasználónak látható szövegekben** (`D9`, `L12`, `L33`, `K29`, `K168`, `C22`, `C25b`, `„D13 - CS50”`, „AI01 Workflow 2.0 protokoll”, „A legacy feladat…”) — ~35 fájl; plusz ~570 fájl K/C/T-hivatkozás kommentben | core/gepi_iras.py:245,483,495,504,513,785,809 · core/modell/router.py:76 · modulok/*/lanc.py · app/src/szerkeszto/formazas.ts:101 · app/src/hej/vezerlo/Bevitel.svelte:374 · app/src/hej/vezerlo/Modellek.svelte:92 | A felhasználónak értelmezhetetlen; a fejlesztő saját mappanevét/protokollját árulja el | TÖRLÉS |
| 15 | **Obsidian-vault mint egyetlen támogatott forma** (`.obsidian` jelenléte = „valódi vault”; `app.json`, `types.json`, `graph.json` olvasása) | core/frame.py:129-132 · core/server.py:234-245 · core/doctor.py:165 · core/vaultio.py:184,403 · core/csatolmany.py:110 | Nem-Obsidian könyvtárat (sima mappa) a core nem kezeli „valódi” vaultként → nem ír bele, indulási helyreállítás kimarad | MARAD (termék-döntés) / CONFIG (kapcsolható feltétel) |

---

## (b) Becslés: érintett fájlok száma kategóriánként

(Egyedi fájlok, regex-alapú számolás; `src` = `core/ app/src/ shell/ bin/ config/ tools/ modulok/` (a `modulok/ytdlp/tests` és `src/msp` nélkül); `tests` = `tests/ app/tests/`. A számok felső becslések: a komment-szintű említések is beleszámítanak.)

| # | Kategória | forrás (src) | tesztek | Megjegyzés |
|---|---|---|---|---|
| 1 | Abszolút/személyes utak (`/Users`, `/Volumes`, `Manifold-backup`, `glodi`, iCloud, `.obsidian`) | ~26 | ~72 | ebből a **logikában** ~5 fájl: `modulok/ytdlp/utnorm.py`, `core/doctor.py`, a 16 `.obsidian`-olvasó (MARAD), `shell/Sources/CoreProcess.swift` (selftest) |
| 2 | Vault-struktúra konvenciók (mappanevek, blokkjelölők, szakaszcímek) | ~88 | ~132 | ebből ~20 core/modul + ~8 felületi fájl a tényleges kódkonstans |
| 2b | Frontmatter-séma (`Tags/Source/Status/NN/Canvas`) | ~33 | ~108 | + `config/vault-sema.json` |
| 2c | Tantárgy-térkép / `[pdf.tags]` / tantárgynevek | ~18 | ~73 | |
| 3 | Személyes identitás (bundle id, aláírás, lista-név, modell-repók, git identity) | ~12 | ~30 | e-mail/Apple ID: 0 |
| 4 | Nyelvi kötés (hu a logikában + felületi locale) | ~66 (core/modulok ~30, felület ~36) | ~26 | + ~15 `promptok`/prompt-szöveg modul |
| 5 | Gép-specifikus (APFS, sandbox-exec, sysctl/ioreg, arm64, EventKit, Spotlight, git) | ~96 | ~74 | többsége platform-követelmény (MARAD) |
| 6 | Legacy-kötés | ~118 (komment nélkül ~35) | ~65 (komment nélkül ~8) | TÖRLÉSre ítélt fájlok: `modulok/ytdlp/{utnorm,klon}.py`, `tools/mac/02_*`, doctor legacy-ága, `kotes_modell.json` |
| 7 | Fejlesztői/Claude-artefaktumok | felhasználói szövegben ~35; kommentben ~570 | ~280 | termékbe kerülő teszt-hook: ~15 fájl (`shell/Sources/*`, `core/probafeladat.py`, `core/osszeomlas.py`, `bin/mos`) |
| 8 | Beégetett modellnevek (felület/üzenet) | ~24 (felület: 0) | ~42 | a core üzeneteiben/súgóban: ~3 fájl; a többi komment és `modulok/eval` |

---

## (c) Ami már most konfigurálható — ezért NEM gond

**Környezeti változók és CLI**
- `MOS_ROOT` (gyökér), `MOS_CONFIG` (teljes konfigfájl-csere), `MOS_PYTHON`, **`MOS_<KULCS>` minden `[utak]` kulcsra** (pl. `MOS_VAULT`, `MOS_BACKUP`, `MOS_FFMPEG`, `MOS_LLVM`, `MOS_SDK`, `MOS_STATE`, `MOS_INDEX`, `MOS_RUN`, `MOS_VAULT_GIT`, `MOS_YTDLP_GIT`) — `core/config.py:46-80`.
- `MANIFOLD_MODELL_KERET_GB` (a modellkeret), `MANIFOLD_MODELL_ZAR` (modellzár útja) — `core/modell/beallitas.py:150`.
- `MOS_ALAIRAS_IDENTITAS` (aláírási tanúsítvány neve; üres = ad-hoc) — `shell/build.sh:18`.
- `MOS_CORE_PORT`, `MOS_KEZFOGAS_MP`, `MOS_NAPTAR_SEGED`, `MOS_HEJ_CLI`, `MOS_MODELL_MOD`, `MOS_TELJESITMENY` (futtatási/teszt-kapcsolók).
- A kód **abszolút utat nem éget be** (L49): a `doctor` őrzi (`core/doctor.py:23,78`), a `bin/mos` a saját helyéből számol (bin/mos:4-15).

**`config/os.toml` — a konvenciók nagy része már kulcs (csak az alapérték személyes)**
- Vault-mappák: `[sablon] mappa`, `[naplo] ut/sablon/canvas/dolgozat_mappa/kiertekelo_nevek`, `[kartya] mappa`, `[kviz] mappa`, `[osszefoglalas] mappa`, `[fuzet] cel_mappa/szakasz/mappak`, `[media] video_mappa/reteg_mappa/nyelvek`, `[video] vault_mappa`.
- Tantárgy-térkép: `[pdf.tags]`, `[asszisztens.tantargy_nevek]`, `[naptar.targyak]` (a `core/naptar.py:60` kommentje szerint bővíthető).
- Asszisztens-szűrők: `[asszisztens] higienia_arva_kizart`, `emlites_kizart`, `higienia_arva_tulajdonsag_kizart`, `higienia_arva_canvas` (a `kartya_kizart` csak a `core/asszisztens/beallitasok.py:44` kód-alapértékben szerepel, de ugyanazon szakaszból felülírható).
- Naptár/emlékeztető: `[naptar]` (`tanulas_naptar`, `szinkron_perc`, `mult_nap`, `jovo_nap`), `[emlekezteto]` (`lista`, `forras`, `ora`, `riasztas`), `[javaslat]` (sáv, perc).
- Memória/hőkezelés: `[keret] munka/tavol`, `[modellgazda]`, `[aktivitas]`, `[ho]`, `[homokozo]`, `[feladatsor]`.
- Mentés: `[mentes]`, `[teljes_mentes]` (`cel`, `figyelo_be`, `kihagy`), `[pillanat.vault/ytdlp]` (`kizar`, `kivetelek`).
- Modell-regiszter és router: `[modellek.*]` (`repo`, `revizio`, `futtato`, `feladat`, `csucs_gb`), `[router] feladatok`, `[router.feladat.*]`, `[meres.*]`.
- Séma: `[sema] vault` (a séma-fájl útja — a `vault-sema.json` cserélhető), a `vault-sema.json` `h1.sorszam_elotag`, `kivetel_osztalyok`, `tags_ertekkeszlet`.
- Nyelv: `[sablon] nyelv` (`hu|en`), `[media] nyelvek`.
- Futtatás: `[core] port` (0 = szabad), `[core] naplo_max_mb`, `[video] *`, `[grafikon]`, `[matek]`.
- `config/letoltes.toml` + `config/runtime-pins.env` + `config/requirements.lock`: letöltési lista, runtime-pinek (a hordozhatóság már megoldott: `bin/mos runtime fetch`).

**Amit a doctor már ellenőriz (jó tervezési minta)**
- `ENV_UTAS` (HF_/UV_/PIP_/MOS_ környezeti utak), `SAJAT_MINTA` (home-ba/`~/Applications`-be/`~/.cache`-be írás), Spotlight-kizárás, rendszer-git és `sandbox-exec` megléte, aláírás típusa.

**Összegzés a rangsorhoz:** a legtöbb konvenció **már kulcs az `os.toml`-ban**, de (1) az alapérték a fejlesztő saját vaultja, (2) a kód tartalék-alapértéket duplikálja, (3) a felület (`app/src/*/allando.ts`) saját tükör-konstanst tart, (4) a séma-fájl és a kivételek személyes adatot tartalmaznak. A termék-átalakítás tehát elsősorban **alapértékek cseréje + felhasználói konfig-réteg + nyelvi/séma-profil**, kisebb részben kódcsere.
