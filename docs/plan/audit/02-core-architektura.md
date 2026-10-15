# 02 — A core architektúra-térképe (Manifold-OS 2.0) a termékesítés tervezéséhez

Forrás: `/Volumes/Work/Manifold-OS v2` (csak olvasva). Minden hivatkozás `fájl:sor` a gyökérhez képest. A `var/`, `runtime/`, `archive/`, `app/`, `.git`, a staging és az eval-adatok nem lettek megnyitva; ahol az adatukról szól a térkép, az a kódból és a `docs/ARCHITECTURE.md` 3–5. fejezetéből (`docs/ARCHITECTURE.md:405-479`) következik.

Jelölések: **CORE** = minden felhasználónál azonos logika · **USER** = felhasználói adatot kezel · **KONFIG** = a viselkedése konfig-függő · **SZEMÉLYES** = a fejlesztő vault-konvencióihoz kötött (beégetett mappanév, frontmatter-kulcs, magyar tantárgy-/naptár-szótár).

---

## 0. A legfontosabb megállapítások (a terv szempontjából)

1. **Egy core = egy `{os}` = egy `var/` = egy vault.** Minden út egyetlen TOML-ból jön (`core/config.py:45-54`), de az alapértékek `{os}`-relatívak (`config/os.toml:11-53`), és a kód több helyen közvetlenül a `cfg.root`-ot használja (7. fejezet).
2. **A vault léte = `.obsidian` mappa.** `Vault.root` `.obsidian` nélkül `NemElerheto` (503) minden vault-végponton (`core/vaultio.py:178-184`), az indulási helyreállítás kimarad (`core/frame.py:128-132`, `core/server.py:243-246`). Egy friss, üres mappa tehát nem vault.
3. **Nincs tároló-létrehozó parancs.** A `snapshot.Repo.init()` létezik (`core/snapshot.py:202-233`), de egyetlen hívója a `visszaallitas.py:136` (bundle-ből visszaállítás). Hiányzó `var/vault.git`-nél a szerkesztő pillanatkép nélkül ment, a gépi írás és az átnevezés megtagadja a munkát (1.5 fejezet).
4. **A `var/` és a vault azonos APFS-kötetet feltételez** (`rename_excl`, `clonefile`, `cp -c`). A doctor kifejezetten HIBA-t ad, ha nem így van (`core/doctor.py:740-742`). Ez a (a) célnak („var az Application Supportban, a vault külső SSD-n”) közvetlenül ellentmond.
5. **A kód ír a saját fájába:** `bin/mos` létrehozza a `var/tmp`, `var/cache`, `var/.metadata_never_index` fájlokat (`bin/mos:49-52`); a `felkeszultseg kalibral --rogzit` az `os.toml`-t írja (`core/felkeszultseg/kalibracio.py:300-314`); a ytdlp-lánc pillanatkép-munkafája és stagingje a `modulok/ytdlp` alatt él (`config/os.toml:24,27,85`). Egy csak-olvasható `.app` bundle ezeket nem viseli el.
6. **„Gépszintű” zárak valójában `var/`-szintűek:** a modellzár `{state}/modell.lock` (`config/os.toml:408`, `core/modell/zar.py:1-4`), a worker-zár `{run}/worker.lock` (`core/modell/worker.py:361`). Két workspace = két `var/` = két worker és két betöltött modell (épp az L23 által tiltott 14 GB-os eset).
7. **A belső mentés (`{backup}`) nincs workspace-hez kötve:** a bundle- és állapotnevek (`vault-*.bundle`, `mos-allapot-*`) workspace-azonosító nélküliek, a rotáció a `<név>-*.bundle` mintára számol (`core/snapshot.py:771-791`, `core/mentes.py:415-476`). Két workspace egy `{backup}`-ban egymás mentéseit forgatná ki.
8. **D9 (csak kalibrált modell ír élesben) a `router.sqlite`-on és a `modulok/eval/*/feladat.py` VERZIO-ján múlik** (`core/modell/halmaz.py`, `core/gepi_iras.py:497-514`). Új telepítésen kalibrációs sor nincs → minden modelles funkció 503/400. A kalibráció termékszinten **telepítési** (nem felhasználói) adat kell legyen, de ma a fejlesztő aranyhalmazaira épül.
9. **Erős biztonsági mag**, amelyet meg kell őrizni: API-titok + Host + Origin (`core/server.py:681-742, 848-864`), lépés-token default-deny (`core/lepes_kapu.py:82-97`), gépi írás csak pillanatképpel (`core/gepi_iras.py:544-548`), atomi tartós írás (`core/tartos.py:101-146`), kör-zár (`core/frame.py:65-97`), szándéknaplók és indulási helyreállítás (`core/server.py:308-335`).
10. **SZEMÉLYES konvenciók a kódban is** (nem csak a TOML-ban): `ATTCHMNTS - …` előtag (`core/automatika.py:47`, `core/index/hibrid/hasonlo.py:23`), napi jegyzet útja és váza (`core/naplo.py:25,74`), naptár-kategóriák és magyar tantárgy-szótár (`core/naptar.py:33-62`), `Tags/Source/Status/NN/Canvas` séma (`config/vault-sema.json`, `core/tulajdonsagok.py:349-359`).

---

## 1. Indulási sorrend

### 1.1 A gyökér (`{os}`) feloldása — három réteg

| Réteg | Hol | Mit csinál |
|---|---|---|
| Héj (Swift) | `shell/Sources/RootLocator.swift:5-17` | Jelölt gyökér: `MOS_ROOT` env, különben **az `.app` szülőmappája**. Érvényes, ha van futtatható `bin/mos` és `config/os.toml` (`:7-10`). Hibánál üzenet: „A Manifold.app-nak a Manifold-OS mappájában kell lennie” (`shell/Sources/AppController.swift:92`). |
| Héj → core | `shell/Sources/CoreProcess.swift:55-61` | `root/bin/mos core start`, env: `MOS_ROOT`, opcionálisan `MOS_CORE_PORT` (újraindításnál a régi port), `MOS_API_TITOK` (újraindításnál a régi titok); stdin = `Pipe` (életciklus). |
| `bin/mos` (bash) | `bin/mos:6-13` | A saját helyéből (symlinket feloldva) `MOS_HOME`, és **felülírja** `MOS_ROOT=$MOS_HOME`-ot. Munkafa-mód: `.git` fájl esetén saját `var/` kötelező, `MOS_BACKUP=var/backup` (`bin/mos:19-31`). Beégetett `var/` utak env-ként: `HF_HOME`, `XDG_CACHE_HOME`, `UV_CACHE_DIR`, `PIP_CACHE_DIR`, `TMPDIR=$MOS_HOME/var/tmp` (`bin/mos:35-47`); `mkdir var/tmp var/cache`, `var/.metadata_never_index` (`bin/mos:49-52`). Interpreter: `MOS_PYTHON` → `var/venv` → fő checkout venv → `runtime/python` (`bin/mos:56-62`). `core start` → `python -B -m core start` (`bin/mos:199`). |
| Python | `core/config.py:22-25, 71-82` | `os_root()`: `MOS_ROOT`, különben `core/` szülője. Konfig: `MOS_CONFIG`, különben `{root}/config/os.toml` (`:74`). |

### 1.2 Az `os.toml` és a `MOS_*` felülírások

- Helyőrzők: `{os}`, `{home}` és minden `[utak]` kulcs, rekurzív feloldással, körfigyeléssel (`core/config.py:28-42`).
- Minden `[utak]` kulcsot a `MOS_<KULCS>` env felülír (`core/config.py:52-54`), pl. `MOS_VAULT`, `MOS_VAR`, `MOS_STATE`, `MOS_BACKUP`, `MOS_VAULT_GIT`. **Ez már ma lehetővé teszi** a vault és a var áthelyezését kódváltozás nélkül — a 7. fejezet sorolja, hol nem elég.
- Csak a `[utak]` kulcsai írhatók felül env-vel; a többi szakasz (pl. `[pillanat.vault] kivetelek`, `[sema] vault`, `[mentes] kodtar`) a TOML-ban `{os}`-relatív (`config/os.toml:74,93,98`) — ezek csak a TOML cseréjével (`MOS_CONFIG`) mozgathatók.
- Egyéb env-kapcsolók: `MOS_CORE_PORT` (`core/server.py:1002`), `MOS_API_TITOK` (`core/__main__.py:23`, `core/server.py:117-127`), `MOS_OSSZEOMLAS` (teszthorog, `core/osszeomlas.py:15`), `MOS_PROBA_FELADAT` (`core/probafeladat.py`), `MANIFOLD_MODELL_ZAR` / `MANIFOLD_MODELL_KERET_GB` (`core/modell/beallitas.py:149`), `MOS_NAPTAR_SEGED`, `MOS_HEJ_CLI`, `MOS_LETOLTES` (`core/letoltes.py:130`).

### 1.3 Indulás lépésről lépésre (`python -m core start`)

| # | Lépés | Hol | Megjegyzés (D8: a megnyitás nem indít nehéz munkát) |
|---|---|---|---|
| 1 | Az API-titok kivétele a környezetből (a gyermekek ne örököljék) | `core/__main__.py:18-23` | |
| 2 | `config.load()` | `core/server.py:983` | `ConfigError`, ha nincs `os.toml` (`core/config.py:78-79`). |
| 3 | Egypéldányos zár: `{run}/core.lock` (`flock`); foglaltnál első stdout-sor `{"foglalt":true,pid,vault}`, kilépés 75 | `core/server.py:944-966, 985-991` | A zár a `{run}`-hoz kötött → „egy core / var”, nem „egy core / vault”. |
| 4 | Forgatott `{runs}/core.log` + faulthandler | `core/server.py:993`, `core/corenaplo.py:117-140` | |
| 5 | `App.__init__`: titok sorsolása, esemény-busz, modell-beállítás, jelek, aktivitás, kapu, worker-kliens (nem indul), mentés-ütemező, **feladatsor** (`feladatok.sqlite` megnyitása/migrációja, naplótakarítás, legacy-import, indulási szünet-időzítő), teljes-mentés-figyelő, **index** (példány), `Vault`, átnevezés, tulajdonságok (+ `vault-sema.json`), Bases, előzmények, tracker (`pos.sqlite`), C++-szolgálat, **gépi írás**, naptár-szolgálat, asszisztens, füzet-figyelő (no-op), kártya-szinkron, automatika (fogyasztók), média-token, útvonal-regiszter | `core/server.py:133-228`; `core/tasks.py:199-237` | A feladatsor `indulasi_szunet_mp` (180 s) után indít (`core/tasks.py:216,237`). |
| 6 | HTTP-szerver `127.0.0.1:<port>` (`[core] port` vagy `MOS_CORE_PORT`, 0 = szabad) | `core/server.py:1002-1003` | |
| 7 | **Gyors indulási helyreállítás a kör-zár alatt** (csak ha `.obsidian` van): elakadt `index.lock`, zárt git-környezet (`info/attributes`, hooks off), megszakadt visszavonás, átnevezés, gépi írás szándéknaplója; foglalt zárnál háttér-újrapróba ≤600 s; az előző mentés hibája üzenetként | `core/server.py:233-262, 308-353`; `core/frame.py:117-146` | A kézfogás előtt — a felület első mentése előtt le kell zárulnia. |
| 8 | Index-szál indítása (bejárás, `vault.sqlite`, FSEvents) | `core/server.py:1008`; `core/index/indexelo.py:114,194-234` | Háttérben, modell nélkül. |
| 9 | Időzítős szolgálatok: naptár (60 s késleltetés), asszisztens/higiénia, füzet-figyelő (kikapcsolva), mentés-ütemező (30 perc), teljes-mentés-figyelő (alapból ki), kártya-szinkron (≤20 s), automatika (180 s), rendszerjelek (memória, HID), képgyorsítótár-takarítás (180 s) | `core/server.py:1009-1022` | |
| 10 | SIGTERM-kezelő (második ⌘Q) | `core/server.py:1118-1123` | |
| 11 | **Kézfogás**: első stdout-sor `{"port","pid","titok"}` | `core/server.py:1124-1125` | A héj ebből tölti be a lapot és injektálja a titkot. |
| 12 | Kézfogás utáni háttérmunka: saját `.manifold-tmp` maradékok törlése (bejárás zár nélkül, törlés zár alatt, csak a core indulása előtti mtime), futó mag ujjlenyomata (CX-001); a feladatsor árva lépéseinek leállítása saját szálon | `core/server.py:264-306, 1126`; `core/tasks.py:262-297` | |
| 13 | stdin-figyelő szál (a héj kilépése = rendezett leállás) és `serve_forever` | `core/server.py:1107-1129` | |
| — | Leállás: feladatsor (tétel végén; 20 s után azonnal), WS zárás, kvíz késleltetett írása, C++ megszakítás, szolgálatok, worker, kilépési **belső mentés** | `core/server.py:1060-1105, 1130-1142` | SIGTERM: 10 s után `os._exit`, előtte ≤15 s a kör-zárra és 1 s bundle-próba (`:1042-1058`). |

A **worker** csak igény szerint indul: modelligényes feladat env-jénél (`core/server.py:454-466`), a képlet-OCR-nél (`core/fuzet_api.py:143`), a kiegészítésnél (`core/kiegeszites_modell.py:117`), a C++ AI-nál (`core/cpp_ai.py:159`), a hibrid keresés lusta kötésénél (`core/kereses_api.py:81-102`). Indítás: `core/modell/kliens.py:256-285` (`cwd={os}`, `PYTHONPATH` = a futó kód helye, napló `{runs}/worker.log`).

### 1.4 Héj ↔ core kézfogás és API-titok

- A titok: rögzített (`MOS_API_TITOK`, a héj újraindításkor visszaadja) vagy `secrets.token_urlsafe(32)`; formátum `[A-Za-z0-9_.-]{16,128}` (`core/server.py:114-127`).
- A felület minden `/api/*` és `/health` kérésben `X-Manifold: <titok>`; a WS az alprotokollban (`mos.<titok>`) (`core/server.py:732-742, 860-864`).
- A média-URL saját tokent kap (`media_token`, `core/server.py:219`), mert `<img>/<video>` nem küld fejlécet (`core/media.py`).

### 1.5 Mi feltételezi, hogy a vault és a `var/vault.git` MÁR LÉTEZIK?

| Feltétel | Hol | Hiányában mi történik |
|---|---|---|
| A vault mappa `.obsidian`-nel | `core/vaultio.py:178-184` (`Vault.root`) | Minden vault-olvasó és -író végpont 503 `NemElerheto` („a kötet le van választva…”) + `vault_elerheto:false` WS. **Egy új, üres mappa ugyanígy viselkedik, mint egy kihúzott SSD.** |
| Ugyanez az indulásnál | `core/frame.py:128-132`; `core/server.py:243-246, 268` | Az indulási helyreállítás és a tmp-takarítás kimarad (stderr-üzenet). Szándékos: a munkafa-módot védi (T002). |
| A vault mappa léte (`is_dir`) | `core/index/indexelo.py:336,371,472` | Az index üres, `elerheto:false`; a figyelő a mappa visszatérésére vár. Index-végpontok 503-at adnak, amíg nem kész. |
| `.obsidian/app.json`, `types.json`, `graph.json` | `core/csatolmany.py` (csatolmány-mappa), `core/index/elemzo.py` (`tipusok_olvas`), `core/index/graf_meta.py` | Hiányzó fájl → alapérték; nem hiba, de az Obsidian-modell a termék előfeltétele. |
| `var/vault.git` élő (HEAD + munkafa) | `core/snapshot.py:195-200`; `core/frame.py:235-237` | **Szerkesztő mentése**: pillanatkép nélkül ír, figyelmeztet + `pillanat_hiba` WS (`core/vaultio.py:328-329, 383-395, 484-486`). **Gépi írás**: 503 „pillanatkép nélkül gép nem ír” (`core/gepi_iras.py:544-548`). **Próbaklón** (D9): 503 (`core/gepi_iras.py:523-524`). **Átnevezés**: 409 (`core/atnevezes.py:568-570`). **Visszavonás**: 404 (`core/server.py:540-544`). **Előzmények**: 404 (`core/elozmeny.py:54-58`). **Belső mentés**: nincs vault-bundle (`core/mentes.py:415-476` csak élő tárolót ment). Doctor: HIBA (`core/doctor.py:183-197`). |
| A vault sémafájl | `config/os.toml:93` → `config/vault-sema.json`; `core/tulajdonsagok.py:84-86` | Hiányzó `[sema] vault` → `FileNotFoundError`; a tulajdonság-ellenőrzés és a gépi írás sémavizsgálata erre épül. |
| A vault helye `{os}/../Manifold` | `config/os.toml:11-12` | Más elrendezésnél `MOS_VAULT` kell. |

**Ismert hézag — tároló-létrehozás.** A `Repo.init()` (`core/snapshot.py:202-233`: `git init --bare`, `core.worktree`, `core.ignorecase` mérése, `precomposeunicode`, `info/exclude` a configból, `biztosit_kornyezet`) **kész és idempotens**, de csak a `core/visszaallitas.py:136` hívja. Nincs `bin/mos` parancs (`bin/mos:191-289` listája), nincs API-végpont és nincs indulási ág, amely üres vaulton tárolót hozna létre. Előfeltétele a meglévő munkafa (`core/snapshot.py:204-205`). Az első commit nélküli tárolót a `commit()` kezeli (`core/snapshot.py:316-318`), tehát egy `init` + az első keret „kézi” commitja elegendő lenne. A first-run onboardingnak ezt a lépést kell pótolnia, a `.obsidian` létrehozásával együtt.

---

## 2. Modul-térkép

Oszlopok: **Vault** = ír-e a vaultba (közvetlenül vagy a gépi íráson át) · **var** = ír-e a `var/` alá · **Modell** = igényel-e modellt (workert) · **Osztály** = CORE / USER / KONFIG / SZEMÉLYES.

### 2.1 Infrastruktúra, életciklus, biztonság

| Modul | Felelősség | Fő függőségek | Vault | var | Modell | Osztály |
|---|---|---|---|---|---|---|
| `__main__.py` | `start` / `doctor` / `backup` belépő | server, doctor, mentes | – | – | – | CORE |
| `config.py` | Út-feloldás, helyőrzők, `MOS_*` | tomllib | – | – | – | CORE, KONFIG |
| `server.py` | HTTP+WS, `App`, indulás/leállás, hitelesítés, undo | szinte minden | igen (undo) | igen (`run/core.lock`) | – | CORE |
| `utvonalak.py` | Útvonal-regiszter, `HttpError`, biztonsági fejlécek | – | – | – | – | CORE |
| `websocket.py` | Saját RFC 6455 | – | – | – | – | CORE |
| `events.py` | Esemény-busz, korlátos sor, `kimaradt` | – | – | – | – | CORE |
| `corenaplo.py` | `{runs}/core.log` forgatás, faulthandler | config | – | igen | – | CORE |
| `osszeomlas.py` | Összeomlás-injektáló teszthorog | – | – | – | – | CORE |
| `lepes_kapu.py` | Lépés-token jogkészlet, env-fehérlista, default-deny | – | – | – | – | CORE |
| `utkapu.py` | Symlink-őr (a vaulton belül marad-e) | – | – | – | – | CORE |
| `vaultkivul.py` | „Nem a vaultba” őr (inode-azonosság, zárva hibázik) | – | – | – | – | CORE |
| `tartos.py` | `F_FULLFSYNC`, atomi írás, `rename_excl`, `clonefile`, kizáró írás | osszeomlas | (eszköz) | – | – | CORE |
| `frame.py` | Kör-zár, pillanatkép-keret, APFS-próbaklón, tmp-/naplótakarítás | snapshot | igen (keret) | igen (`run/kor.lock`, `tmp/proba`) | – | CORE |
| `snapshot.py` | Külső `GIT_DIR`-es pillanatkép, undo, bundle | mediatipus, tartos | igen (revert) | igen (`vault.git`, `run/visszavonas`) | – | CORE |
| `mediatipus.py` | Média-kiterjesztések egyetlen listája | – | – | – | – | CORE |
| `epites.py` | Forrás-ujjlenyomat, build-frissesség (`/api/rendszer/epites`) | git | – | – | – | CORE (a `{os}` git-fájára és a `Manifold.app/Contents/Resources/epites.json`-ra épít) |
| `doctor.py` | Rendszer-diagnózis | config, snapshot, … | – | – | – | CORE, de **fejlesztői környezetre szabott** (7. fejezet) |
| `tasks.py` | Tartós feladatsor, erőforrás-szabály, lépés-alfolyamatok, lépés-token | frame, lepes_kapu | közvetve | igen (`feladatok.sqlite`, `runs/feladatok`) | lépésenként | CORE |
| `vezerlo.py` | Rendszerállapot, kapcsolók, feladat-változások | frame, mentes, snapshot, modell | – | igen (`state/kapcsolok.json`) | – | CORE, USER (beállítás) |
| `mentes.py` | Belső lemezes mentés (bundle, állapotmásolat, migráció előtti másolat), ütemező | frame, snapshot, tartos | – (kézi commit kilépéskor) | igen (`state/mentes-hiba.json`) + `{backup}` | – | CORE, USER |
| `teljes_mentes.py` | Verziózott külső mentés, ellenőrzés, visszaállítás üres célba | config, frame, snapshot, vaultkivul | – | igen (`state/teljes-mentes.json`) | – | CORE, USER |
| `visszaallitas.py` | Tároló visszaállítása bundle-ből (CLI) | snapshot, tartos | igen (hiányzó fájlok) | igen (`vault.git`) | – | CORE |
| `letoltes.py` | Modell-letöltő (CLI, D3) | config | – | igen (`models/`) | – | CORE (telepítés) |
| `probafeladat.py` | Teszt-feladattípus (csak `MOS_PROBA_FELADAT=1`) | gepi_kliens, tasks | igen (klón) | – | – | CORE (teszt) |

### 2.2 Vault-réteg (fájlok, index, szerkesztés)

| Modul | Felelősség | Fő függőségek | Vault | var | Modell | Osztály |
|---|---|---|---|---|---|---|
| `vaultio.py` | Szerkesztői olvasás/írás/létrehozás, ütközés, `.obsidian`-kapu | frame, snapshot, tartos, utkapu | **igen** | – | – | CORE, USER |
| `gepi_iras.py` | A gép egyetlen írási útja (tétel, szándéknapló, D9, próbaklón, `mozgat`/`behoz`) | vaultio, frame, snapshot, binaris_naplo, kalibracio, halmaz | **igen** | igen (`run/gepi-iras`, `tmp/proba`, `tmp/apkg-media`) | (D9-vizsgálat) | CORE, USER; a `mozgat` célmappák alapértéke SZEMÉLYES (`core/gepi_iras.py:818-821`) |
| `gepi_kliens.py` | A lépések kliense a gépi íráshoz (`MOS_CORE_URL` + token) | lepes_kapu | (a core-on át) | – | – | CORE |
| `atnevezes.py` | Átnevezés teljes link-átírással, szándéknapló | frame, snapshot, index, bazis | **igen** | igen (`run/atnevezes`) | – | CORE, USER |
| `elozmeny.py` | Jegyzet-előzmények, visszaállítás revert-commitként | frame, snapshot | **igen** | – | – | CORE, USER |
| `csatolmany.py` | Kézi darabolt import, új mappa, Kuka (héj `--kuka`) | frame, snapshot, vaultio | **igen** | igen (`tmp/csatolmany`) | – | CORE, USER (Obsidian `attachmentFolderPath`) |
| `binaris_naplo.py` | Bináris mozgásnapló (L19), média-visszavonás | mediatipus, tartos | igen (visszaköltöztetés) | igen (`state/binaris-naplo.jsonl`) | – | CORE, USER |
| `tulajdonsagok.py` | Frontmatter bájthű módosítása, séma-ellenőrzés | index.elemzo | – (tiszta) | – | – | KONFIG, SZEMÉLYES (`Tags/Status/Source`, `core/tulajdonsagok.py:349-359,472,614`) |
| `sablon.py` | Sablonmotor, új jegyzet sablonból | vaultio | igen (`/api/sablon/uj`) | – | – | KONFIG (`_Template`, `core/sablon.py:36`) |
| `naplo.py` | Napi jegyzet megnyitása/létrehozása | sablon, vaultio | igen | – | – | SZEMÉLYES (`X01 - Napló & To-Do/…`, váz `Tags: Napló`, `core/naplo.py:25,74`) |
| `pdfkiemeles.py` | PDF-kiemelés jegyzet formátuma, írás | vaultio, tulajdonsagok | igen | – | – | KONFIG, SZEMÉLYES (`Source`, `[pdf.tags]`) |
| `media.py`, `kepek.py` | Média-kiszolgálás tokennel, Range; kicsinyített képek, videó-poszter | vaultio, `modulok.ytdlp.eszkoz` (ffmpeg) | – | igen (`cache/vault-kepek`) | – | CORE |
| `atirat.py` | Média-átirat (VTT) a lejátszónak | mediatipus | – | – | – | SZEMÉLYES (`ATTCHMNTS - Videos`, `Média`, `core/atirat.py:24-25`) |
| `felulet.py` | A felület tartós állapota | config | – | igen (`state/felulet.json`) | – | CORE, USER |
| `szoveg_tisztit.py`, `gyakorlas.py`, `cpp_teszt.py` | Formátum-segédek (egyetlen hely) | index.maszk | – | – | – | CORE; `gyakorlas` SZEMÉLYES (`## Gyakorlás`, `core/gyakorlas.py:20`) |
| `index/` (csomag) | `indexelo` (író, figyelő), `olvaso`, `tar` (`vault.sqlite`), `elemzo`, `feloldas` (link-feloldás egy helyen), `maszk`, `kereses`, `linkek`, `graf_meta`, `feladatok`, `pdfszoveg` + `pdf_gyerek` (homokozott PDF-kinyerés), `figyelo` (FSEvents) | tartos, utkapu | – | igen (`index/vault.sqlite`, `index/pdf-szoveg.sqlite`) | – | CORE (Obsidian-szabály szerinti feloldás) |
| `index/hibrid/` | Hibrid keresés (FTS+vektor RRF), vektortár, darabolás, „Kérdezz” váz, hasonlóság | `modulok.kapuk` | – | igen (`index/vektor.sqlite`) | beágyazó/reranker (opcionális) | CORE; `hasonlo.py:23` SZEMÉLYES (`ATTCHMNTS - `) |
| `bazis/` (csomag) | Obsidian Bases: elemző, kiértékelő, függvények, lekérdezés, `.base` hivatkozás-átírás | index | – (tiszta) | – | – | CORE |
| `higienia.py` | Jegyzethigiénia-riport | index, tulajdonsagok, asszisztens.beallitasok | – | – | – | KONFIG, SZEMÉLYES (`Source`, `Média`) |

### 2.3 Funkció-modulok (láncok core-oldala)

| Modul | Felelősség | Fő függőségek | Vault | var | Modell | Osztály |
|---|---|---|---|---|---|---|
| `automatika.py` | Közös automatika-ütemező (80(a) óta csak `vektorindex`) | index, tasks, `modulok.kapuk` | – | igen (`automatika.sqlite`) | – (feladatot küld) | CORE; `KISERO_ELOTAG` SZEMÉLYES (`core/automatika.py:47`) |
| `vektorindex_feladat.py` | `vektorindex` (automatikus) | tasks | – | igen (vektortár) | beágyazó | CORE |
| `kartya_api.py`, `kartya_feladat.py` | Kártyák (FSRS), szinkron, `.apkg` import/export; „Kártyák ebből” | `modulok.kartya`, tanulas_db, gepi | igen (import, generálás) | igen (`tanulas.sqlite`, `szemelyes/export`) | generálás: igen (D9) | USER, KONFIG (`ATTCHMNTS - cards`) |
| `kviz_api.py`, `kviz_feladat.py` | Kvíz kitöltése, értékelés, `## Kitöltések`; „Kvíz ebből” | `modulok.kviz`, `modulok.kapuk`, gepi | igen (`## Kitöltések`, generálás) | igen (`tanulas.sqlite`) | generálás: igen | USER, SZEMÉLYES (`ATTCHMNTS - quizes`, `core/kviz_api.py:36`) |
| `tanulas_db.py` | `tanulas.sqlite` sémája | mentes (migráció előtt) | – | igen | – | USER |
| `osszefoglalas_api.py`, `osszefoglalas_feladat.py` | Kontextus-csomag, visszamásolt válasz kapuja, összefoglaló | `modulok.osszefoglalas` | igen (feladat) | – | feladat: igen | USER, SZEMÉLYES (`ATTCHMNTS - summaries`, `core/osszefoglalas_api.py:43,147`) |
| `grafikon_api.py`, `grafikon_feladat.py`, `plot_allapot.py` | `plot` blokk CAS-jellemzői (homokozó), beírás, tiltólista | `modulok/grafikon` alfolyamat | igen (feladat) | igen (`state/plot-*.json`) | modell-ág: opcionális | CORE, USER |
| `matek_api.py`, `matek_feladat.py` | Levezetés-ellenőrzés (homokozó), „Megoldás” | `modulok/matek` alfolyamat | igen (feladat) | – | megoldás: igen | CORE |
| `fuzet.py`, `fuzet_api.py`, `fuzet_feladat.py`, `fuzet_figyelo.py` | Füzetfotó-lánc, képlet-OCR, bejövő mappa (figyelő kikapcsolva) | `modulok/fuzet` | igen (`mozgat`) | igen (`state/Manifold-fuzet`, `fuzet/bejovo`, `tmp/keplet-ocr`) | igen | USER, SZEMÉLYES (`{work}/Notebooks - digitalized`, `## Füzet`, `ATTCHMNTS - photos`) |
| `videolanc.py`, `video_api.py` | Videó letöltés/bejárás/bevitel feladatai, bejövő videó | `modulok.ytdlp` alfolyamat | igen (bevitel) | igen (`video/bejovo`, `state/video-bejaras`) + **`{os}/modulok/ytdlp/staging`** | bevitel: igen | USER, SZEMÉLYES (`ATTCHMNTS - Videos`, `core/videolanc.py:310-315`) |
| `cpp_utvonal.py`, `cpp_ai.py` | C++ munkafelület (⌘R, homokozó), AI-tippek | `modulok.cpp` alfolyamat | igen (új feladat-jegyzet) | – | AI: igen (D9, `kod`) | CORE; `[cpp] sablon` KONFIG |
| `kereses_api.py`, `kereses_modell.py` | Hibrid keresés, „Kérdezz a vaulttól”, worker-kötés | index.hibrid, kliens | – | – | Kérdezz: igen (D9); vektor: opcionális | CORE |
| `kiegeszites_modell.py` | Szövegkiegészítés modellútja | router, kliens | – | – | igen (ha `modell=true`) | CORE |
| `asszisztens/` (csomag) | Higiénia-szolgálat, említések, szokásminta, statisztika, mintatár, kiegészítés, hangoló | tracker, index, kereses | – | igen (`state/asszisztens.json`, `pos.sqlite`) | kiegészítés: opcionális | USER, SZEMÉLYES (`beallitasok.py:7,18,44` kizárt előtagok; `emlites.py:13,51` `NN - Cím — Feladattár` névkonvenció) |
| `ma.py` | „Ma” oldal összesítő (csak olvas) | naplo, sablon, index | – | – | – | SZEMÉLYES (`Dolgozatok` kötés) |
| `tracker.py`, `szemelyes_db.py` | Tevékenységnapló, használat (`pos.sqlite` egyetlen írója), séma | vezerlo, ma | – | igen (`szemelyes/pos.sqlite`, `szemelyes/export`) | – | USER |
| `naptar.py`, `naptar_seged.py`, `naptar_szolgalat.py`, `naptar_javaslat.py`, `naptar_api.py`, `emlekezteto.py` | EventKit-segéd (a héj CLI-je), naptár-szinkron, emlékeztető-tükör, tanulásiblokk-javaslat | szemelyes_db, gepi | igen (`✅` kipipálás gépi írással, `core/emlekezteto.py:336`) | igen (`pos.sqlite`) | – | USER, SZEMÉLYES (kategóriák és tantárgy-szótár: `core/naptar.py:33-62`); külső írás: Naptár, Emlékeztetők |
| `felkeszultseg/` (csomag) | Dolgozat-felkészültség, terv, eredmény, önkalibráció, szöveges értékelés | pos/tanulas ro, index, `modulok.kartya` | – | igen (`state/tanulasi-keret.json`); a CLI az **`os.toml`-t** írja | értékelés: igen (D9) | USER, SZEMÉLYES (L59 `Dolgozatok/ÉÉÉÉ-HH-NN - Tantárgy.md`, „Dolgozat kiértékelő”) |

### 2.4 Modellréteg (`core/modell/`)

| Modul | Felelősség | Vault | var | Modell | Osztály |
|---|---|---|---|---|---|
| `worker.py`, `betolto.py`, `hatter.py`, `utemezo.py` | A worker-folyamat; az egyetlen hely, ahol modell töltődik (MLX); kérés-ütemező | – (nem olvas, nem ír) | igen (`run/worker.lock`, `run/worker.pid` 0600, `state/modell.lock`) | **igen** | CORE |
| `kliens.py` | Worker-kliens, worker indítása | – | igen (`runs/worker.log`) | – | CORE |
| `router.py`, `kalibracio.py`, `halmaz.py`, `revizio.py`, `attekintes.py` | Router (kalibrált + keretbe férő), `router.sqlite`, aranyhalmaz-verziók (`{modulok}/eval`), pinelt HF-revízió | – | igen (`router.sqlite`) | – | CORE (a kalibráció **telepítési** adat) |
| `kapu.py`, `jelek.py`, `aktivitas.py`, `memoria.py`, `ho.py`, `zar.py` | Feladatsor-kapu, memória/HID-jelek, aktivitásjel, hőfigyelés, gépszintű modellzár | – | igen (`run/aktivitas`) | – | CORE |
| `beallitas.py` | `[modellgazda]`, `[keret]`, `[router]`, `[modellek.*]` | – | – | – | KONFIG (SYSTEM) |
| `bench.py`, `eval.py`, `ervenyesseg.py`, `__main__.py` | Mérés és kalibráció (CLI) | – | igen (`runs/eval`) | igen | CORE (fejlesztői eszköz); `bench.py:126` a legacy médiaállapotot olvassa |
| `api.py` | `/api/modell`, `/api/vezerlo/modellek`, `/api/aktivitas` | – | igen (`run/aktivitas`) | – | CORE |

Megjegyzés a csatolásról: a docstringek szerint „a core nem importál `modulok`-ot”, valójában több modul **in-process importálja**: `core/kviz_api.py:51-52`, `core/kartya_api.py:46,345,359`, `core/osszefoglalas_api.py:37`, `core/automatika.py:57`, `core/index/hibrid/kerdezz.py:62,127,141`, `core/index/hibrid/darabolas.py:67`, `core/felkeszultseg/rekonstrukcio.py:21`, `core/felkeszultseg/adat.py:384`, `core/kepek.py:266`. A `core` és a `modulok` tehát egy csomagként szállítandó.

---

## 3. API-felület

### 3.1 Hitelesítés és határok

| Szabály | Hol |
|---|---|
| Csak `127.0.0.1`; `Host` csak `127.0.0.1`/`localhost`/`[::1]` (különben 403) | `core/server.py:68, 681-682, 1002` |
| `/api/*` és `/health`: `X-Manifold` = API-titok (teljes jog) **vagy** érvényes lépés-token (olvasók + `ENGEDELYEZETT`) | `core/server.py:732-753`; `core/lepes_kapu.py:82-97` |
| `/ws`: `Origin` csak saját origin; titok az alprotokollban | `core/server.py:848-864` |
| `/media/<token>/…`: URL-token (a böngészőelemek nem küldenek fejlécet) | `core/media.py:19`, `core/server.py:219` |
| `/…` statikus: `{app_dist}` hitelesítés nélkül (csak a csomag, rejtett szegmens nélkül) | `core/server.py:813-825` |
| Törzs ≤ 16 MiB; socket-művelet ≤ 30 s; nincs keep-alive | `core/server.py:69-71, 686-709` |
| Lépés-token: lépésenként `token_urlsafe(24)`, a lépés végén törlődik; a `"nincs"` jogkészlet (videóletöltés, vektorindex) se tokent, se core-címet nem kap | `core/tasks.py:737-740, 632-652`; `core/lepes_kapu.py:18-25, 65-67` |

Jelmagyarázat a táblákban: **V** = a vaultba ír (közvetlenül vagy gépi íráson át) · **M** = modellt hív; **D9** = élesben csak kalibrált modell, különben 503/400 · **L** = a lépés-token mellett is hívható (különben default-deny, 403). Minden `GET`/`HEAD` **L**.

### 3.2 Infrastruktúra, rendszer, feladatsor

| Út | Metódus | Leírás | V | M | L |
|---|---|---|---|---|---|
| `/health` | GET | Életjel (`{ok}`) | | | L |
| `/api/allapot` | GET | Verzió, pid, RSS, média-token, feladatsor, élő tárolók | | | L |
| `/api/rendszer/epites` | GET | A futó és a lemezen álló build ujjlenyomata (CX-001) | | | L |
| `/api/feladatok` | GET / POST | Utolsó 40 feladat / új feladat (`tipus`, `parameterek`, `prioritas`) | POST: V a típustól | típusfüggő (D9 a lépésben) | GET |
| `/api/feladatok/{id}` | GET | Feladat naplósorokkal | | | L |
| `/api/feladatok/{id}/leallitas` | POST | Leállítás (tétel végén / azonnal) | | | |
| `/api/feladatok/{id}/valtozasok` | GET | A feladat gépi commitjai (vezérlő) | | | L |
| `/api/vezerlo/rendszer` | GET | Memória, modellzár birtokosa, SSD, utolsó mentés | | | L |
| `/api/vezerlo/kapcsolok` | GET / PUT | Asszisztens- és Tracker-kapcsoló (`state/kapcsolok.json`) | | | GET |
| `/api/vezerlo/modellek` | GET | Router-tábla, kalibrált jel feladatonként | | | L |
| `/api/modell` | GET | Aktivitás, kapu oka, worker-egészség, router-tábla | | | L |
| `/api/aktivitas` | POST | Felületi aktivitásjel (`run/aktivitas`) | | | |
| `/api/felulet/allapot` | GET / PUT | A felület tartós állapota (`state/felulet.json`) | | | GET |
| `/api/mentes/teljes` | GET | A teljes külső mentés állapota | | | L |
| `/api/pillanat/{tar}/naplo` | GET | Commitok trailerekkel | | | L |
| `/api/pillanat/{tar}/visszavonas` | POST | Commit vagy kör visszavonása (kör-zár, média visszaköltöztetése) | **V** | | |
| `/ws` | GET | WebSocket (3.9) | | | (alprotokoll-titok kell) |

Feladattípusok (`POST /api/feladatok`): `mentes`, `teljes_mentes` (V-erőforrás), `vektorindex` (M, auto), `kartya_general`/`kartya_automatikus`, `kviz_general`, `osszefoglalas`/`osszefoglalas_automatikus`, `matek_megoldas`, `grafikon_beiras`/`grafikon_automatikus`, `fuzet_lanc`/`fuzet_automatikus`/füzet-ellenőrzés, `video_letoltes`, `video_bejaras`, `video_integralas` (M+V) — `core/tasks.py:130,147`; `core/*_feladat.py`; `core/videolanc.py:367-370`. Az `automatikus=True` típusok a `vektorindex` kivételével beküldéskor tiltottak (80(a), `core/server.py:93-102`).

### 3.3 Vault — fájlok, szerkesztés, struktúra

| Út | Metódus | Leírás | V | M | L |
|---|---|---|---|---|---|
| `/api/vault/fajl` | GET | Szöveges fájl + sha1 | | | L |
| `/api/vault/fajl` | PUT | Atomi mentés (`.md/.base/.canvas/.cpp`), `alap`-hash ütközésvizsgálat, opcionális pillanatkép | **V** | | |
| `/api/vault/uj` | POST | Új fájl (vagy feloldatlan link jegyzete) | **V** | | |
| `/api/vault/import` | POST | Kézi, darabolt fájlimport (felülírás nélkül) | **V** | | |
| `/api/vault/mappa` | POST | Új mappa | **V** | | |
| `/api/vault/kuka` | POST | Fájl/mappa a macOS Kukába (héj `--kuka`, megerősítéssel) | **V** | | |
| `/api/vault/atnevezes/terv` | POST | Átnevezés terve (tiszta) | | | **L** |
| `/api/vault/atnevezes` | POST | Átnevezés teljes link-átírással | **V** | | |
| `/api/vault/elozmeny` | GET | Jegyzet-előzmények | | | L |
| `/api/vault/elozmeny/valtozat` | GET | Egy változat szövege | | | L |
| `/api/vault/elozmeny/visszaallit` | POST | Visszaállítás revert-commitként | **V** | | |
| `/api/vault/sema` | GET | A vault-séma | | | L |
| `/api/vault/tulajdonsagok/kulcsok`, `/ertekek` | GET | Tulajdonság-javaslatok | | | L |
| `/api/vault/tulajdonsagok/elemez`, `/modosit`, `/osszefesul` | POST | Frontmatter-számolók (nem írnak) | | | **L** |
| `/api/vault/ikonok`, `/api/vault/cimkek` | GET | Ikonok, címkék az indexből | | | L |
| `/api/vault/bazis/lekerdez`, `/bazis/modosit` | POST | Bases-lekérdezés / tiszta módosítás-számoló | | | **L** |
| `/api/sablon/lista` | GET | Sablonok | | | L |
| `/api/sablon/kiertekel` | POST | Sablon kiértékelése (tiszta) | | | **L** |
| `/api/sablon/uj` | POST | Új jegyzet sablonból | **V** | | |
| `/api/naplo/ma` | POST | Napi jegyzet megnyitása/létrehozása | **V** | | |
| `/api/pdf/kiemelesek` | GET | Egy PDF kiemelései | | | L |
| `/api/pdf/kiemeles`, `/api/pdf/kiemeles/torol` | POST | Kiemelés hozzáadása/törlése (kiemelés-jegyzet + `Source`) | **V** | | |
| `/api/gepi-iras` | POST | **A gép egyetlen írási útja** (tétel; D9-vizsgálat a `modell` mezőre) | **V** | (D9 a kimenetre) | **L** |
| `/media/<token>/<út>` | GET/HEAD | Vault-média (Range, ETag, `?w=`, `?poster=`) | | | (URL-token) |
| `/api/media/atirat` | GET | Média VTT-átirata | | | L |

### 3.4 Vault — index, keresés, gráf

| Út | Metódus | Leírás | V | M | L |
|---|---|---|---|---|---|
| `/api/vault/index` | GET | Index-állapot | | | L |
| `/api/vault/fa` | GET | Fájlfa | | | L |
| `/api/vault/jegyzet` | GET | Jegyzet elemzése (tulajdonságok, linkek, fejezetek…) | | | L |
| `/api/vault/visszahivatkozasok`, `/emlitesek` | GET | Backlinkek, linkeletlen említések | | | L |
| `/api/vault/kereses` | GET | Obsidian-szerű lexikai keresés | | | L |
| `/api/vault/graf`, `/graf-meta`, `/graf-beallitasok` | GET | Gráf (ETag), szűrő-meta, `.obsidian/graph.json` | | | L |
| `/api/vault/linkcel`, `/beagyazas`, `/aliasok` | GET | Link-cél, beágyazás feloldása, aliasok | | | L |
| `/api/vault/feloldas` | POST | Linkek kötegelt feloldása | | | **L** |
| `/api/kereses/hibrid` | GET | Hibrid keresés (lexikai + vektor; modell nélkül lexikai tartalék) | | beágyazó/reranker (opcionális) | L |
| `/api/kereses/vektor-allapot`, `/hasonlo` | GET | Vektortár állapota, hasonló jegyzetek (modell nélkül) | | | L |
| `/api/kereses/hasonlosag` | POST | Jegyzet-hasonlóság (vektortárból) | | | |
| `/api/kereses/kerdezz` | POST | „Kérdezz a vaulttól” (NDJSON is) | | **M, D9** (`szoveg`; 503: `core/kereses_api.py:263`) | |
| `/api/higienia` | GET | Higiénia-riport | | | L |
| `/api/ma` | GET | „Ma” oldal | | | L |

### 3.5 Tanulás: kártya, kvíz, összefoglaló, felkészültség

| Út | Metódus | Leírás | V | M | L |
|---|---|---|---|---|---|
| `/api/kartya/allapot`, `/esedekes`, `/jegyzet` | GET | Összesítő, esedékes kártyák, egy pakli | | | L |
| `/api/kartya/valasz`, `/visszavon` | POST | FSRS-értékelés / visszavonás (`tanulas.sqlite`) | | | |
| `/api/kartya/export` | POST | `.apkg` export a `{szemelyes}/export` alá (vaultba 400) | | | |
| `/api/kartya/import` | POST | `.apkg` import (próba / éles gépi írással, médiával) | **V** | | |
| `/api/kviz/kviz` | GET | Kvíz kitöltésre (kulcs nélkül, tokennel) | | | L |
| `/api/kviz/megoldas`, `/kitoltes`, `/jelol` | POST | Válasz rögzítése, értékelés, „hibás” jelölés (`tanulas.sqlite`; késleltetett `## Kitöltések` gépi írás) | **V** (késleltetve, `core/kviz_api.py:121`) | | |
| `/api/osszefoglalas/kontextus`, `/valasz` | POST | Kontextus-csomag külső AI-nak / visszamásolt válasz a kapun át (nem ír) | | | |
| `/api/osszefoglalas/jegyzet`, `/mappa-terv` | GET | Összefoglaló elemzése, mappa-terv | | | L |
| `/api/felkeszultseg`, `/dolgozat`, `/kalibracio`, `/keret` | GET | Felkészültség, dolgozat-részlet, kalibrációs jelentés, napi keret | | | L |
| `/api/felkeszultseg/keret` | PUT | Napi tanulási keret (`state/tanulasi-keret.json`) | | | |
| `/api/felkeszultseg/ertekeles` | POST | Szöveges értékelés | | **M, D9** (`core/felkeszultseg/api.py:80`) | |

### 3.6 Matek, grafikon, C++, füzet, videó

| Út | Metódus | Leírás | V | M | L |
|---|---|---|---|---|---|
| `/api/matek/levezetes` | POST | Levezetés-ellenőrzés (CAS-homokozó, alfolyamat) | | | |
| `/api/grafikon/elemzes` | POST | `plot` CAS-jellemzők (homokozó) | | | |
| `/api/grafikon/tiltolista` | GET | Tiltólista | | | L |
| `/api/grafikon/tiltolista/levesz` | POST | Levétel (`state/plot-tiltolista.json`) | | | |
| `/api/cpp/allapot`, `/api/cpp/feladat`, `/api/cpp/futas/{id}` | GET | Eszközlánc, feladat-jegyzet, futás | | | L |
| `/api/cpp/feladat` | POST | Új C++ feladat-jegyzet + `.cpp` | **V** | | |
| `/api/cpp/ellenoriz`, `/megszakit`, `/formaz` | POST | ⌘R homokozóban, megszakítás, clang-format (nem ír) | | | |
| `/api/cpp/ai/allapot`, `/api/cpp/ai/{ai-id}` | GET | Van-e kalibrált `kod` modell; futás | | | L |
| `/api/cpp/ai`, `/ai/megszakit`, `/ai/tipp` | POST | AI-mód indítása / megszakítás / tipp-esemény | | **M, D9** (`core/cpp_ai.py:130`) | |
| `/api/fuzet/allapot` | GET | Füzetlánc összesítő | | | L |
| `/api/fuzet/bejovo` | POST | Fotó a `{fuzet_bejovo}` alá (vaulton kívül) | | | |
| `/api/keplet-ocr` | POST | Vágólap-kép → LaTeX | | **M, D9** (`ocr_keplet`, worker-router) | |
| `/api/video/allapot`, `/bejaras` | GET | Staging-állapot, bejárás eredménye | | | L |
| `/api/video/bejovo` | POST | Videó darabja a `{video_bejovo}` alá | | | |

### 3.7 Naptár, emlékeztető, tracker, asszisztens

| Út | Metódus | Leírás | V | M | L |
|---|---|---|---|---|---|
| `/api/naptar/allapot`, `/javaslatok` | GET | Naptár-állapot, tanulásiblokk-javaslatok | | | L |
| `/api/naptar/szinkron` | POST | Kézi kör (naptár → emlékeztetők → javaslatok; kipipálás gépi írással) | **V** | | |
| `/api/naptar/kategoria` | POST | Naptár-kategória (`pos.sqlite`) | | | |
| `/api/naptar/javaslat/{id}/jovahagy`, `/elvet` | POST | Javaslat jóváhagyása (**macOS Naptárba ír**) / elvetése | | | |
| `/api/emlekezteto/allapot` | GET | Emlékeztető-tükör | | | L |
| `/api/emlekezteto/utkozes/latva` | POST | Ütközés láttamozása | | | |
| `/api/tracker/esemenyek` | POST | Felületi események (`pos.sqlite`) | | | |
| `/api/tracker/statisztika`, `/hasznalat` | GET | Statisztika, használat | | | L |
| `/api/tracker/export`, `/torles` | POST | Export a `{szemelyes}/export` alá; adattörlés | | | |
| `/api/asszisztens/higienia`, `/mintak`, `/tanult`, `/szokas`, `/statisztika` | GET | Asszisztens-adatok | | | L |
| `/api/asszisztens/kiegeszites` | POST | Szövegkiegészítés (helyi minta; modell csak `[asszisztens.kiegeszites] modell=true`) | | M opcionális, D9 | |
| `/api/asszisztens/kiegeszites/elvet`, `/elfogad`, `/mintak/tanit`, `/mintak/torles`, `/higienia/latva`, `/tanult/torles`, `/tanul`, `/kartya`, `/kartya/dontes`, `/emlitesek`, `/szokas/dontes`, `/dontes`, `/statisztika/torles` | POST | Asszisztens-döntések, minták, statisztika (`state/asszisztens.json`, `pos.sqlite`) | | | |

A regiszter teljes forrása: `core/server.py:108-111` (`UTVONAL_MODULOK`) + `core/server.py:647-666`; a végpontok a modulok `utvonalak(r)` függvényeiben (a fenti táblák a `r.get/post/put` hívásokból készültek). A `/api/vault/.*` ismeretlen alútja 404 (`core/index/api.py:35-38`).

### 3.8 Lépés-folyamatnak engedélyezett nem-olvasó végpontok (a teljes fehérlista)

`POST /api/gepi-iras`, `/api/vault/tulajdonsagok/{elemez,modosit,osszefesul}`, `/api/vault/bazis/{lekerdez,modosit}`, `/api/vault/atnevezes/terv`, `/api/vault/feloldas`, `/api/sablon/kiertekel` — `core/lepes_kapu.py:82-92`. Minden más POST/PUT (a szerkesztői írás, a feladat-indítás, a visszavonás, a „Kérdezz”, a felületi állapot) a lépésnek 403 (`core/server.py:741-742`). A döntéstáblát a `tests/test_lepes_kapu.py` kényszeríti.

### 3.9 WebSocket-üzenetek

**core → felület** (`tipus` szerint):

| Esemény | Forrás | Tartalom |
|---|---|---|
| `hello` | `core/server.py:878` | verzió, média-token, indulási figyelmeztetések |
| `indulasi_uzenet` | `core/server.py:290` | késői indulási üzenetek |
| `kimaradt` | `core/events.py:19-31` | túlcsordult sor (újraszinkron kell) |
| `feladat` | `core/tasks.py:377` | feladatállapot és haladás |
| `vault_iras` | `core/vaultio.py:377,505`; `core/gepi_iras.py:639` | saját írás (út, hash, pillanat) |
| `gepi_iras` | `core/gepi_iras.py:640` | gépi tétel (kör, tétel, utak, sha, forrás) |
| `vault_valtozas` | `core/index/indexelo.py:535-542` | külső/belső változás kötege |
| `vault_atnevezes` | `core/atnevezes.py:732,792,806` | átnevezés |
| `visszavonas` | `core/server.py:585` | visszavonás |
| `pillanat_hiba` | `core/vaultio.py:386,395` | pillanatkép nélküli mentés |
| `vault_elerheto` | `core/vaultio.py:197` | a vault eltűnt / visszajött |
| `index`, `pdf_szoveg` | `core/index/indexelo.py:234,318,329,361,834` | index-állapot, PDF-szöveg |
| `modell` | `core/server.py:516` | worker-állapot (5 s-onként változáskor) |
| `kapcsolok` | `core/vezerlo.py:227` | kapcsolóváltás |
| `naptar_valtozas`, `naptar_javaslat`, `emlekezteto_valtozas`, `emlekezteto_utkozes` | `core/naptar_szolgalat.py:131,170`; `core/naptar_api.py:34`; `core/naptar_javaslat.py:271,302,363,369`; `core/emlekezteto.py:298,300` | naptár/emlékeztető |
| `asszisztens_valtozas` | `core/asszisztens/szolgalat.py:141,193` | higiénia frissült |
| `cpp_futas`, `cpp_ai` | `core/cpp_utvonal.py:334`; `core/cpp_ai.py:214` | C++ futás/AI eseményei |

**felület → core**: egyetlen üzenet, `{tipus:"mentetlen", utak:[…]}` — a nyitott, mentetlen dokumentumok halmaza; ezekbe a gép nem ír (türelmi idővel a bontás után) (`core/server.py:400-418, 393-398`).

---

## 4. Adatbázisok és állapot

### 4.1 SQLite-ok

| Fájl (alap út) | Író | Séma (`user_version`) | Újraépíthető? | Adat-osztály | Belső mentésben? |
|---|---|---|---|---|---|
| `{index}/vault.sqlite` (`var/index/`) | `core/index/indexelo.py:80` (egy író), olvasó: `olvaso.py`, `higienia.py:393` | 4 (`core/index/tar.py:16,184-219`): `fajl, mappa, tulajdonsag, cimke, fejezet, blokk, link, feladat, keplet, kodblokk, meta, fts*, szakasz, media_szoveg` | **igen** (a vaultból; sérültnél félretesz és újraépít) | WORKSPACE-cache | nem |
| `{index}/vektor.sqlite` | `core/index/hibrid/vektortar.py` (a `vektorindex` lépés) | 1 (`vektortar.py:27`): `meta, jegyzet, darab` (+ `vec_darab`) | **igen** (modell-kulcs váltásra ürül) | WORKSPACE-cache (modell-függő) | nem |
| `{index}/pdf-szoveg.sqlite` | `core/index/pdfszoveg.py` (gyermekfolyamat eredménye) | 1 (`pdfszoveg.py:31-72`): `pdf` | **igen** | WORKSPACE-cache | nem |
| `{router_db}` = `var/router.sqlite` | `core/modell/kalibracio.py` (`mos eval --rogzit`, hő-alapszint) | 3 (`kalibracio.py:89-101`): `kalibracio`, `kalibracio_naplo`, `hoalap` | **nem** (mérés eredménye) | **INSTALLATION** (gép × modell × aranyverzió) | igen |
| `{feladatok_db}` = `var/feladatok.sqlite` | `core/tasks.py:57-79, 247-254` | 2: `feladat`, `meta` | részben (előzmény) | WORKSPACE (a feladatok vault-útra hivatkoznak) | igen |
| `{tanulas_db}` = `var/tanulas.sqlite` | `core/tanulas_db.py` (kártya, kvíz) | 2 (`tanulas_db.py:74`): `kartya, valasz, sirko, apkg_kulcs, kviz_kitoltes, kviz_valasz, kviz_jeloles` | **nem** (FSRS-történet) | **USER WORKSPACE** | igen |
| `{automatika_db}` = `var/automatika.sqlite` | `core/automatika.py:179-238` (a lépés is: `Tar.kesz`) | 2: `allapot` (+ `adat`) | részben | WORKSPACE | igen |
| `{szemelyes}/pos.sqlite` | `core/tracker.py` (egyetlen író), `core/szemelyes_db.py` (séma), naptár-szolgálat | **5** (`core/szemelyes_db.py:100-101`; az ARCHITECTURE 4. még 3-at ír): 1: `forras_rekord, import_futas, naptar, naptar_valtozas` (legacy); 2: `tr_*`, `has_*`; 3: `emlekezteto*`, `naptar_javaslat`; 4: `has_asszisztens`; 5: `tr_aktiv_ora` | **nem** | **USER** (személyes; a naptár része gép-/fiókfüggő) | igen |

Közös szabály: séma csak új migrációval, WAL; a használt DB migrációja előtt `mentes.migracio_elott` (`core/mentes.py:384-412`) a `{backup}` alá.

### 4.2 `state/` és egyéb `var/` fájlok

| Út | Író | Mi | Osztály |
|---|---|---|---|
| `state/felulet.json` | `core/felulet.py` | téma, elrendezés, fülek, legutóbbiak | USER (UI-preferencia; részben workspace-függő utak) |
| `state/kapcsolok.json` | `core/vezerlo.py:36` | Asszisztens/Tracker kapcsoló | USER (preferencia) |
| `state/asszisztens.json` | `core/asszisztens/allapot.py:24` | asszisztens állapot, minták | USER WORKSPACE |
| `state/tanulasi-keret.json` | `core/felkeszultseg/keret.py:9-19` | napi tanulási keret | USER |
| `state/plot-tiltolista.json`, `plot-beirasok.json`, `plot-automatika.json` | `core/plot_allapot.py:29-49` | grafikon tiltólista, beírás-napló | USER WORKSPACE |
| `state/binaris-naplo.jsonl` | `core/binaris_naplo.py:66` | média-mozgásnapló (a visszavonás erre épül) | USER WORKSPACE (a `vault.git` párja) |
| `state/Manifold-fuzet/` (`allapot.json`, `naplo.jsonl`, `valaszok/`, `ocr.json`, `.zar`) | `core/fuzet.py`, `modulok/fuzet` | füzetlánc kötései | USER WORKSPACE |
| `state/Manifold-media/` (`jobs`, `itelet`, `kotes`) | `modulok/ytdlp`, `core/binaris_naplo.py:490` | videólánc állapota (legacy) | USER WORKSPACE |
| `state/video-bejaras/<sha1>.json` | `core/videolanc.py:184` | bejárás eredménye | USER WORKSPACE |
| `state/mentes-hiba.json` | `core/mentes.py:479-504` | utolsó mentés hibája | WORKSPACE (rendszer) |
| `state/teljes-mentes.json` | `core/teljes_mentes.py:438,580` | teljes mentés állapota | WORKSPACE |
| `state/felkeszultseg-kalibracio.jsonl` | `core/felkeszultseg/kalibracio.py:317` | önkalibráció naplója | USER |
| `state/modell.lock` | `core/modell/zar.py` | „gépszintű” modellzár | **INSTALLATION/gép** (ma tévesen var-szintű) |
| `run/` (`core.lock`, `kor.lock`, `worker.lock`, `worker.pid`, `aktivitas`, `atnevezes/`, `gepi-iras/`, `visszavonas/<tár>/`) | server, frame, worker, atnevezes, gepi_iras, snapshot | zárak, szándéknaplók | WORKSPACE-futás (a `worker.*` gép-szintű kellene legyen) |
| `runs/` (`core.log*`, `worker.log`, `feladatok/*.log`, `eval/`, `video/VIDEOBE-*.json`, `kapu-*.json`, `pult/feladatok.jsonl`) | corenaplo, kliens, tasks, eval | naplók, riportok | WORKSPACE-napló |
| `index/` | lásd 4.1 | | cache |
| `vault.git`, `ytdlp.git` | snapshot, frame | pillanatképek | **USER WORKSPACE** (a vault történetének egyetlen helye; nem újraépíthető) |
| `allapot.git` | — (legacy, nem használt) | | archív |
| `tmp/` (`proba/`, `apkg-media/`, `csatolmany/`, `keplet-ocr/`, `video-proba/`) | gepi_iras, csatolmany, fuzet_api, frame | ideiglenes, próbaklónok | WORKSPACE (a vault kötetén kell!) |
| `cache/` (`vault-kepek/`, `uv`, `pip`, `npm`) | kepek, bin/mos | gyorsítótárak | cache (vault-képek: WORKSPACE; uv/pip/npm: INSTALLATION) |
| `models/` (`HF_HOME`) | letoltes | modellek | **INSTALLATION** (nagy, megosztandó) |
| `venv/` | `bin/mos runtime install` | Python-környezet | **INSTALLATION** |
| `fuzet/bejovo/`, `video/bejovo/` | fuzet_api, video_api | beérkező fájlok | USER WORKSPACE (átmeneti) |
| `szemelyes/` (`pos.sqlite`, `export/`) | tracker, kartya_api | személyes adat, exportok | USER |
| `archive/` (`eval-C18.1/`, `audit-*`) | kézi | | fejlesztői |
| `var/.metadata_never_index` | `bin/mos:52` | Spotlight-kizárás | INSTALLATION/WORKSPACE |

### 4.3 A `var/`-on kívüli állapot

| Hely | Mi | Osztály |
|---|---|---|
| `{os}/modulok/ytdlp/` (munkafa a `ytdlp.git`-hez), `staging/`, `archive/` (`config/os.toml:24,27-28,85`) | a videólánc kódja ÉS adata egy fában | **kód+USER keverve** |
| `{os}/archive/` (`video-eredeti`, `video-visszavont`, `apkg-visszavont`, `config/os.toml:29-31,52`) | a visszavont/eredeti média | USER WORKSPACE |
| `{os}/config/os.toml` (a CLI írja: `core/felkeszultseg/kalibracio.py:300-314`), `vault-sema.json`, `pillanat-kivetelek-vault.json` | konfiguráció + vault-séma + vault-történeti kivételek | keverék (5. fejezet) |
| `{os}/modulok/eval/*/` (aranyhalmazok; a router `VERZIO`-t olvas: `core/modell/halmaz.py`) | mérési adat a fejlesztő vaultjából | fejlesztői/INSTALLATION (kalibráció alapja) |
| `{backup}` = `~/Manifold-backup` (`config/os.toml:53`) | bundle-ök, `mos-allapot-*`, `mos-migracio-*`, `mos-kodtar-*` | USER (mentés) — workspace-azonosító nélkül |
| `~/Library/Preferences/local.manifold-os.app.plist` | AppKit-ablakkeretek | INSTALLATION (megengedett kivétel, `core/doctor.py:366-367`) |

### 4.4 A szétválasztás alapja: USER WORKSPACE vs CORE vs INSTALLATION

| Réteg | Tartalom | Hol él ma | Hol kellene |
|---|---|---|---|
| **CORE (kód, csak olvasható)** | `core/`, `modulok/` (a `ytdlp/staging`, `ytdlp/archive` nélkül), `app/dist`, `bin/mos`, `shell` build, `modulok/homokozo/*.sb`, `core/index/pdf_profil.sb`, alap-`os.toml` (SYSTEM szakaszok) | `{os}` | `Manifold.app/Contents/Resources/…` |
| **INSTALLATION (gépenként egy)** | `runtime/` (python, uv, ffmpeg, llvm, sdk), `var/venv`, `var/models`, `var/cache/{uv,pip,npm}`, `router.sqlite` (kalibráció + hő-alap), modellzár + worker-zár/pid, `config/letoltes.toml`, `runtime-pins.env`, `cpp-pins.env` | `{os}/runtime`, `{os}/var` | `~/Library/Application Support/Manifold/` (+ `Caches`) |
| **USER WORKSPACE (vaultonként egy)** | a vault, `vault.git`, `binaris-naplo.jsonl`, `tanulas.sqlite`, `automatika.sqlite`, `feladatok.sqlite`, `state/*.json` (plot, asszisztens, füzet, média), `index/*` (cache), `tmp/` (a vault kötetén!), `run/` (kör-zár, szándéknaplók, `core.lock`), `runs/`, a workspace-konfig (mappanevek, séma, napló-út, `[pdf.tags]`) | `{os}/var`, `{os}/config`, `{os}/modulok/ytdlp`, `{os}/archive` | workspace-gyökér (pl. `<vault>/.manifold/` vagy a vault kötetén egy testvérmappa — a kötet-feltétel miatt) |
| **USER (személyes, workspace-független?)** | `pos.sqlite` (naptár, tracker, emlékeztetők), `felulet.json`, `kapcsolok.json`, `tanulasi-keret.json`, `{backup}` | `var/szemelyes`, `var/state`, `~/Manifold-backup` | döntés kell: fiók-szintű (Application Support) vagy workspace-szintű; az emlékeztető-tükör és a tracker jegyzetútra hivatkozik → inkább workspace |

---

## 5. Konfiguráció (`config/os.toml`)

Osztályok: **P** = PRODUCT CONFIG (a felhasználó állítja a beállításokban) · **W** = WORKSPACE CONFIG (vault-függő) · **S** = SYSTEM (kalibráció, pin, belső) · **T** = történeti, a core nem olvassa.

| Szakasz (sor) | Egy mondat | Osztály |
|---|---|---|
| `[utak]` (10) | Minden út helyőrzővel; a vault, a var, a mentés és az eszközök helye | S (+ W: `vault`, `work`, `backup`) |
| `[core]` (55) | Port, időkorlátok, mentetlen-türelem, naplóméret | S |
| `[vault]` (63) | Kör-zár-várakozás, próbaklónok élettartama | S |
| `[pillanat.vault]` (71) | A vault pillanatkép-tárolója, kizárások, történeti kivételek | W (+S: `git_dir`) |
| `[pillanat.ytdlp]` (84) | A videólánc tárolója | S |
| `[sema]` (92) | A vault frontmatter-sémájának fájlja | W |
| `[mentes]` (95) | Belső mentés: megtartás, ütem, kódtár | P (megtartás, ütem) / S (`kodtar`) |
| `[teljes_mentes]` (110) | Külső mentés: megtartás, kihagyás, célmappa, figyelő | P |
| `[feladatsor]` (118), `[feladatsor.max_futas_tipus_mp]` (125) | Indulási szünet, párhuzamosság, naplók, időkorlátok | S |
| `[index]` (134) | Figyelő típusa, keresési korlátok, regex/Bases/PDF időkeret | S |
| `[kereses.hibrid]` (146), `[kereses.kerdezz]` (163) | RRF-súlyok, vektor/rerank kapcsoló, „Kérdezz” paraméterei | S (a `vektor` kapcsoló P lehet) |
| `[sablon]` (173) | Sablonmappa, dátum/idő formátum, nyelv | W (mappa) + P (formátum, nyelv) |
| `[naplo]` (179) | Napi jegyzet útja, sablonja, havi canvas, dolgozat-mappa, kiértékelő-nevek | W (SZEMÉLYES alapértékek) |
| `[naptar]` (192) | Automatikus szinkron, ritmus, ablak, tanulási naptár | P |
| `[emlekezteto]` (200) | Emlékeztető-tükör: lista, óra, riasztás, korlátok | P |
| `[javaslat]` (212) | Tanulásiblokk-javaslat: hossz, sáv, darab | P |
| `[felkeszultseg]` (223) | Felkészültség-súlyok, küszöbök, terv; `kalibralt` + kalibrációs paraméterek (a CLI írja) | P (terv, cél) / S (súlyok, `kalibralt`, `kalibracio_*`) |
| `[kartya]` (255) | Kísérőjegyzet-mappa, FSRS-paraméterek, napi limit | W (mappa, utótag) + P (FSRS, napi limit) |
| `[kartya.generalas]` (268) | Generálási mennyiség, duplikátum-küszöb | S |
| `[kartya.automatika]` (277) | Automatikus mód paraméterei (`be` nem olvasott) | T/S |
| `[kapuk]` (289) + `.osszefoglalo/.kartya/.kviz/.valasz` | A forráshűség-kapu küszöbei | S |
| `[kviz]` (315) | Kvízmappa, kérdésszám, generálási paraméterek | W (mappa) + P (kérdésszám) + S |
| `[osszefoglalas]` (334), `[osszefoglalas.automatika]` (356) | Összefoglaló-mappa, állítás-paraméterek, kontextus-méret | W (mappa) + S; automatika: T/S |
| `[fuzet]` (369) | Figyelt fotómappák, cél-mappa, szakasz, korlátok (figyelő kulcsai T) | W (SZEMÉLYES: `{work}/Notebooks - digitalized`) |
| `[media]` (380) | Videómappa, melléklet-réteg, felirat-nyelvek, képgyorsítótár | W + P (nyelvek) |
| `[pdf.tags]` (387) | Mappa-előtag → tantárgy-címke szótár | W (SZEMÉLYES) |
| `[modellgazda]` (401) | Worker-port, MLX cache, memóriaőr küszöb, modellzár útja, tétlen kiürítés, időkorlátok | S |
| `[keret]` (414) | Memóriakeret munka / távol módban (GB) | S (esetleg P „teljesítmény-profil”) |
| `[aktivitas]` (420) | Aktív/távol küszöb, HID-tétlenség | S |
| `[ho]` (428) | Hőfigyelés | S |
| `[router]` (439), `[router.feladat.*]` (446) | Router-feladatok listája, távol-keretre várás | S |
| `[meres]` (454), `[meres.feladat.*]` | Mérés érvényességi küszöbei, generálási paraméterek | S |
| `[modellek.*]` (503–836) | Modell-regiszter: repó, **pinelt revízió**, csúcsmemória, képességek | S |
| `[homokozo]` (852) | CAS-homokozó idő-/memória-/kimenet-korlátai | S |
| `[video]` (863), `[video.kozvetlen]` (880) | Letöltés/bevitel korlátai, kodekek, célmappa, közvetlen fájl-felismerés | P (korlátok, eredeti megtartása) + W (`vault_mappa`) + S |
| `[grafikon]` (889), `[matek]` (894) | Homokozós végpontok időkorlátai, gyorsítótár | S |
| `[grafikon.automatika]` (900) | Grafikon-beírás paraméterei; `modell_ag` | S (+P: `modell_ag`); `be` T |
| `[asszisztens]` (917) | Higiénia/említés/szokás/küszöb/hangolás paraméterei, kizárt előtagok | S + W (kizárt előtagok, SZEMÉLYES) |
| `[asszisztens.kiegeszites]` (954) | Modell-kapcsoló, próba-modell | P (`modell`) / S (`proba_modell`) |
| `[asszisztens.tantargy_nevek]` (962) | Tantárgy-címke → megjelenített név | W (SZEMÉLYES) |
| `[cpp]` (975) | C++ szabvány, fordító- és sanitizer-flagek, korlátok, formázás, sablon | S (+W: `sablon`) |

**Amit a felhasználónak soha nem szabad látnia (vagy szerkesztenie):**
- titkok (nem a TOML-ban, env-ben): `MOS_API_TITOK`, `MOS_LEPES_TOKEN`, `MOS_WORKER_TITOK`, a `worker.pid` titka, a média-token (`core/server.py:117-142, 219`; `core/modell/kliens.py:272-274`);
- teszt/hibakereső kapcsolók: `MOS_OSSZEOMLAS` (a doctor HIBA-t ad rá, `core/osszeomlas.py:7`), `MOS_PROBA_FELADAT`, `MOS_PROBA_JELZES`, `MOS_NAPTAR_SEGED`/`MOS_HEJ_CLI` (ál-segéd);
- a biztonsági és integritási paraméterek: `[pillanat.*]` (git-dir, kizárás, kivételek), `[utak] sandbox_exec`, `naptar_seged`, `hej_cli`, `runtime`, `venv`, `llvm`, `sdk`, `ffmpeg`, `node`, `run`, `tmp`;
- a D9 és a mérés: `[router]`, `[meres*]`, `[modellek.*]` (revízió-pinek), `[felkeszultseg] kalibralt` + súlyok (a CLI írja), `[kapuk*]` küszöbök, `[homokozo]`, `[cpp]` sanitizer-flagek, `[modellgazda] zar/cache_gb/min_szabad_szazalek` (a memóriaőr), `[core]` időkorlátok;
- a „történeti, nem olvasott” kulcsok (`[kartya.automatika] be`, `[osszefoglalas.automatika] be`, `[grafikon.automatika] be`, `[fuzet] figyelo_*`), mert hatástalanok és félrevezetők.

Telepítési konfig a `config/` alatt: `runtime-pins.env`, `cpp-pins.env`, `requirements.in/.lock`, `letoltes.toml` (modell-jelöltek, revíziók) — S, a bundle része.

---

## 6. Kritikus biztonsági mechanizmusok (amit a termékesítés NEM törhet meg)

| Mechanizmus | Hol él | Bemeneti feltétel | Mi törne el, ha a gyökér / vault / var máshová kerül |
|---|---|---|---|
| **Atomi, tartós írás** | `core/tartos.py:40-162` (`tmp_ut`, `atomi_ir` 101, `rename_excl` 125, `klon_excl` 138, `kizaro_ir` 148); `core/vaultio.py:134-138, 293-380, 446-506` | A tmp-fájl a célfájl **mappájában** (`.<név>.<hex>.manifold-tmp`); `F_FULLFSYNC`; APFS a `renamex_np`/`clonefile`-hoz | A szerkesztő írása kötet-független (a tmp a vaultban van) — **marad**. A `rename_excl`/`klon_excl` **`{tmp}` → vault** útjai (`gepi_iras` `mozgat`/`behoz`: `core/gepi_iras.py:878-923`, `892`; csatolmány: `core/csatolmany.py:173`; videó-klón a stagingből) **EXDEV/ENOTSUP-pal elbuknak**, ha a `{tmp}`/staging/bejövő nem a vault kötetén van; tartalék másolás szándékosan nincs (`core/tartos.py:138-146`). Nem-APFS (exFAT, hálózati) vault: a klón és az `F_FULLFSYNC` gyengül. |
| **Kör-zár** | `core/frame.py:50-126` (`{run}/kor.lock`, `flock`); hívók: `snapshot_frame` 240-270, undo `core/server.py:562`, gépi írás `core/gepi_iras.py:578-580`, átnevezés, előzmény, csatolmány, mentés (`core/__main__.py:11`) | Minden író folyamat **ugyanazt** a `{run}`-t lássa | Ha két folyamat (core, `bin/mos backup`, `visszaallit`, a lépések klónja) más `MOS_RUN`/var-t kap, **két kör-zár** lesz → párhuzamos git-írás, kevert commitok (L13). A var áthelyezésekor minden belépési pont (héj, `bin/mos`, lépés-env `core/tasks.py:632-652`, worker) ugyanazt a feloldást kell kapja. A `flock` hálózati köteten nem megbízható. |
| **Gépi írás szolgáltatás** | `core/gepi_iras.py` (útvonal: `1054-1063`; D9: `497-514`; pillanatkép-kötelezettség: `544-548`; szándéknapló + helyreállítás: `296-431, 562-576`; próbaklón: `516-542`) | Élő `vault.git`; kalibrált modell (élesben); `[router] feladatok`; `{run}/gepi-iras`; a próbához APFS-klón a `{tmp}/proba` alá | A próbaklón a vault teljes **APFS-klónja** a `{tmp}` alá (`core/frame.py:273-291`) → `{tmp}` a vault kötetén kell legyen. A D9 a `router.sqlite`-ot és a `{modulok}/eval` verzióit olvassa (`core/gepi_iras.py:508`) → ha a kalibráció telepítés-szintű lesz, ezt a két forrást együtt kell mozgatni. A klón env-je a `MOS_*` útfelülírásokat a `cfg.table`-ből építi (`core/gepi_iras.py:532-537`) — egy új, nem `[utak]`-beli helyhez (pl. workspace-gyökér) ezt bővíteni kell. |
| **Lépés-token (default-deny)** | `core/lepes_kapu.py:1-97`; kiadás `core/tasks.py:632-652, 737-740`; ellenőrzés `core/server.py:732-742` | A lépés env-je fehérlistás; a token csak a futó lépésig él | Kötet-független. A fehérlista a `MOS_*`-előtagot átengedi (`core/lepes_kapu.py:56-61`) — új titok-jellegű változó csak `TITOK/TOKEN/SECRET…` névvel kerül ki automatikusan. Új író végpont csak a `tests/test_lepes_kapu.py` döntésével kerülhet be. |
| **API-titok + Host + Origin** | `core/server.py:114-127, 420-422, 681-753, 848-864`; `core/__main__.py:21-23`; héj: `shell/Sources/CoreProcess.swift:59-61` | A titok csak a héj és a core között (stdout-kézfogás) | Kötet-független. Több workspace = több core = több port és titok: a héjnak core-onként kell tartania. A lap origin-je a portból jön — a WS `Origin` és a `MOS_CORE_PORT`-os újraindítás erre épít. |
| **`vaultkivul.py`** | `core/vaultkivul.py:15-36`; hívók: `core/teljes_mentes.py:264,334`, CLI-kiírások | A vault útja feloldható; zárva hibázik | Ha a vault eltűnik (kihúzott SSD), minden „nem a vaultba” írás tiltott (szándékos). Egy workspace-gyökér a vault **belsejében** (pl. `<vault>/.manifold`) ezzel az őrrel ütközne: az exportok, a mentések célja „vaultban van”-nak számítana. |
| **`utkapu.py` (symlink-őr)** | `core/utkapu.py:13-30`; `core/vaultio.py:186-192` | — | Kötet-független; a vault bárhol lehet. |
| **CAS- és program-homokozó** | `modulok/homokozo/__init__.py:180-202`, `profil.sb:1-33`, `program.py:99-118`; PDF: `core/index/pdfszoveg.py:29-30,151-153`, `core/index/pdf_profil.sb`; alfolyamatok: `core/matek_api.py:58,81-85`, `core/grafikon_api.py:61,146-150` | `[utak] sandbox_exec = /usr/bin/sandbox-exec`; minden út `-D` paraméter | A profil olvasást enged a Python-prefixre, a venvre és a `modulok/{homokozo,matek,grafikon,…}` kódra (`profil.sb:11-28`) — ezek a `-D` paraméterekből jönnek, így egy `.app`-beli kódra is működik. A venv/runtime áthelyezésekor a `PY_PREFIX`/`PY_BASE` paramétereknek a valódi helyre kell mutatniuk. App Store-sandbox alatt a `sandbox-exec` beágyazása nem engedélyezett (kiadási kockázat). |
| **Memóriaőr** | `core/modell/kapu.py:20-59` (feladatsor-kapu), `core/modell/jelek.py`, `core/modell/betolto.py:96-108` (betöltési küszöb), `core/modell/memoria.py:17-18` (`kern.memorystatus_level`); zárak: `core/modell/zar.py`, `core/modell/worker.py:361-372` | `[modellgazda] min_szabad_szazalek`; egy worker és egy modellzár **gépenként** | A modellzár `{state}/modell.lock`, a worker-zár `{run}/worker.lock` — **var-szintűek**. Több workspace vagy több var esetén több worker tölthet modellt egyszerre (az L23 által tiltott eset). Ezeket installation-szintre (pl. `~/Library/Application Support/Manifold/run/`) kell vinni. |
| **Belső mentés** | `core/mentes.py` (`ment` 415, `kilepeskor` 518, `Utemezo` 563, `allapot_forrasok` 202-234, `migracio_elott` 384); bundle-mag `core/snapshot.py:761-791` | `{backup}` a belső lemezen; élő tárolók; a próbaklón (`mos.klon`) kihagyva (`core/frame.py:23,288-290`) | A nevek (`vault-*.bundle`, `ytdlp-*`, `mos-allapot-*`, `mos-migracio-*`) **nem tartalmaznak workspace-azonosítót**, a rotáció glob-alapú → két workspace közös `{backup}`-ban egymás bundle-jeit törli. A `mos-kodtar` bundle a `{os}` git-fáját menti (`config/os.toml:98`, `core/mentes.py:132-183`) — `.app`-ban nincs `.git`, a lépés csendben kimarad (rendben, de a doctor/vezérlő „friss?” jelzése változik). |
| **Teljes külső mentés** | `core/teljes_mentes.py` (gyökerek `83-91`, kizárások `93-121`, cél-ellenőrzés `329-336`, kódtár-bundle `398-411`, visszaállítás `490-566`) | A cél **más kötet**, mint a `cfg.root` (`core/teljes_mentes.py:336, 614`; `core/tasks.py:139`) | A „külső kötet” ellenőrzés a **kód gyökeréhez** mér, nem a vaulthoz: `/Applications`-beli kódnál egy belső lemezes cél „külső”-nek számít, a vault SSD-je pedig elfogadott cél lehet. A mentés az `os` gyökeret mint forrást is viszi (`:85`) és egy `aktiv-os.toml`-t (`:409-411`) — `.app`-nál ez a bundle tartalma, nem a felhasználói adat. A visszaállítás `MOS_ROOT`-tal új `{os}`-t épít (`:540-557`). |
| **Visszaállítás bundle-ből** | `core/visszaallitas.py:42-56` (core-zár próbája), `87-168`; `Repo.init` `:136` | A core nem fut (`{run}/core.lock`); a `{vault_git}` hiányzik vagy üres; a vault szülője létezik | A core-zár a `{run}`-ban: ha a CLI más var-t lát, mint a futó core, a „core nem fut” vizsgálat hamis. Ez az egyetlen hely, amely tárolót hoz létre — az onboarding ugyanerre az `init`-re építhet. |
| **Indulási helyreállítás / szándéknaplók** | `core/server.py:233-353`; `core/frame.py:135-188`; `core/atnevezes.py:49,102-126`; `core/gepi_iras.py:339-431`; `core/snapshot.py:579-650` | `.obsidian` a vaultban; a kör-zár | A naplók a `{run}`-ban, abszolút/relatív vault-utakkal: ha a var két vaulthoz is tartozhat, egy napló rossz vaultra állhat vissza — ezért kapuz a `vault_letezik` (T002). Workspace-onként külön `{run}` kötelező. |
| **Egypéldányos core** | `core/server.py:944-991` | `{run}/core.lock` | „Egy core / var” — ha két var ugyanarra a vaultra mutat (rossz konfiguráció), két core írhatja ugyanazt a vaultot. A zár kulcsa termékben a **vault** (pl. a vault-kötet + inode) kellene legyen, nem a var. |

---

## 7. Több-workspace alkalmasság

### 7.1 A mai modell

Egy `{os}` = egy `config/os.toml` = egy `var/` = egy vault (`[utak] vault = {work}/Manifold`, `config/os.toml:11-12`). A héj a gyökeret az `.app` helyéből veszi (`shell/Sources/RootLocator.swift:16-17`), a `bin/mos` a sajátjából (`bin/mos:6-13`), a Python a `core/` szülőjéből (`core/config.py:22-25`). Workspace-fogalom nincs; a „munkafa-mód” (saját `var/` git worktree-ben, `bin/mos:19-31`) a legközelebbi rokon.

### 7.2 (a) `var/` a felhasználó Application Support mappájában

Konfigból már ma: `MOS_VAR=~/Library/Application Support/Manifold/var` → a `state, models, venv, cache, tmp, runs, run, szemelyes, vault_git, *_db, index, fuzet_bejovo, video_bejovo` mind követi (`config/os.toml:15-46`). **Akadályok a kódban:**

| Hely | Probléma |
|---|---|
| `bin/mos:35-52` | `HF_HOME`, `XDG_CACHE_HOME`, `UV_CACHE_DIR`, `PIP_CACHE_DIR`, `TMPDIR` és a `mkdir`/`.metadata_never_index` **beégetetten** `$MOS_HOME/var/…` — az `os.toml`-t nem olvassa. |
| `bin/mos:57` | Interpreter: `$MOS_HOME/var/venv/bin/python` beégetve. |
| `core/doctor.py:740-742` | HIBA, ha a `var/` és a vault külön köteten van. |
| `core/doctor.py:748-758` | A `root/var` symlinkjét vizsgálja (a gyökér alatti `var/`-t feltételezi). |
| `core/doctor.py:366-391` | A `~/Library/Application Support`, `Caches`, `Logs` alatti, az app azonosítójával kezdődő fájlt FIGYELEM-mel jelzi (`HOME_NEM_ENGEDETT`). |
| `core/frame.py:273-291`; `core/gepi_iras.py:516-542` | A D9-próbaklón `cp -c` a vaultról a `{tmp}/proba` alá — **csak azonos APFS-köteten**. |
| `core/tartos.py:125-146`; `core/gepi_iras.py:87-89, 878-923`; `core/csatolmany.py:173`; `core/fuzet.py:50-51` | `rename_excl`/`clonefile` a `{tmp}`, `{fuzet_bejovo}`, `{video_bejovo}`, `{staging}` és a vault között → EXDEV, ha nem azonos kötet. |
| `config/os.toml:408`; `core/modell/zar.py:3`; `core/modell/worker.py:361,372` | A modellzár és a worker-zár var-szintű; az Application Support-beli var-nál workspace-onként egy var → több worker. |
| `docs/ARCHITECTURE.md:436` | „A `var/` … ugyanazon az APFS-köteten van, mint a vault” — építészeti szabály. |

**Következmény a tervhez:** a `var/` két részre kell bomoljon: **INSTALLATION-var** (Application Support: `models`, `venv`, `cache/{uv,pip,npm}`, `router.sqlite`, modell-/worker-zár, `runs/worker.log`) és **WORKSPACE-var** a vault kötetén (`vault.git`, `tmp`, `run`, `index`, `state`, `*_db`, bejövő mappák). Ehhez új `[utak]` kulcs kell (pl. `{workspace}`), és a fenti beégetések megszüntetése.

### 7.3 (b) a vault bárhol

Konfigból: `MOS_VAULT` (vagy `[utak] vault`). **Akadályok:**

| Hely | Probléma |
|---|---|
| `config/os.toml:11-12` | Alapérték `{os}/../Manifold` — a kódfa szomszédja. |
| `core/vaultio.py:178-184`; `core/frame.py:128-132` | `.obsidian` kötelező — egy új, Obsidian nélküli mappa „nem érhető el”. |
| `core/snapshot.py:202-233` + nincs hívó (csak `core/visszaallitas.py:136`) | Tároló-létrehozás hiányzik (1.5). |
| `config/os.toml:370` (`[fuzet] mappak = {work}/…`) | Személyes, `{work}`-relatív figyelt mappák. |
| `core/teljes_mentes.py:336, 614`; `core/tasks.py:139` | A „külső kötet” vizsgálat a kód gyökerét (`cfg.root`) veti össze a céllal, nem a vaultot. |
| `core/server.py:964`; `core/visszaallitas.py:42-56` | A core-zár a var-ban, tartalma a vault útja — két var ugyanarra a vaultra = két író core. |
| `core/vaultkivul.py:15-36` | Ha a workspace-állapot a vault **alá** kerül (`<vault>/.manifold`), minden „nem a vaultba” kiírás (export, mentés) ütközik; a pillanatkép kizárásába (`[pillanat.vault] kizar`, `config/os.toml:75-80`) és a `norm_path` rejtett-szegmens tilalmába (`core/vaultio.py:153-163`) is bele kell férnie. |
| `config/vault-sema.json`, `config/os.toml:74` (`pillanat-kivetelek-vault.json`), `[naplo]`, `[kartya] mappa`, `[kviz] mappa`, `[osszefoglalas] mappa`, `[media]`, `[pdf.tags]`, `[asszisztens.tantargy_nevek]` | Vault-függő konfig a kódfa `config/` mappájában — workspace-onként külön kell. |
| `core/naplo.py:25,74`; `core/sablon.py:36`; `core/atirat.py:24-25`; `core/automatika.py:47`; `core/index/hibrid/hasonlo.py:23`; `core/kviz_api.py:36`; `core/osszefoglalas_api.py:147`; `core/gepi_iras.py:818-821`; `core/naptar.py:33-62`; `core/asszisztens/beallitasok.py:7,18,44`; `core/asszisztens/emlites.py:51`; `core/gyakorlas.py:20` | **SZEMÉLYES** konvenciók kódban (alapérték vagy fix érték) — új felhasználónál vagy konfigurálhatóvá, vagy semleges alapértékűvé kell tenni (`ATTCHMNTS - ` előtag két helyen fix). |

### 7.4 (c) a kód egy csak-olvasható `.app` bundle-ben

| Hely | `{os}`-relatív feltételezés / írás a kódfába |
|---|---|
| `shell/Sources/RootLocator.swift:7-17` | A gyökér = az `.app` **szülője**, benne `bin/mos` + `config/os.toml`. Bundle-ben a gyökér az `.app/Contents/Resources` kellene. |
| `shell/Sources/CoreProcess.swift:55` | `root/bin/mos` indítása (bash, `set -euo pipefail`). |
| `bin/mos:12-13, 35-52` | `MOS_HOME` = a szkript szülője; `var/` létrehozása a kódfában. |
| `core/config.py:25, 74` | `{os}` = `core/` szülője; az `os.toml` alapból `{os}/config/os.toml` (felülírható `MOS_CONFIG`-gal). |
| `config/os.toml:13-14, 15, 24, 27-31, 44, 47-48, 50-52, 74, 93, 98` | `modulok`, `runtime`, `var`, `ytdlp` (+ `staging`, `ytdlp_archivum`), `video_eredeti/visszavont`, `apkg_visszavont`, `app_dist`, `naptar_seged`/`hej_cli` (`{os}/Manifold.app/Contents/MacOS/Manifold` — bundle-ben a viszony megfordul), `llvm`, `sdk`, `archive`, a vault-kivételek, a séma, a kódtár. |
| `core/felkeszultseg/kalibracio.py:300-314` (+ `core/felkeszultseg/__main__.py:134-137`) | **Az `os.toml`-t írja** (atomi cserével) — read-only bundle-ben hiba; a kalibrált súlyok workspace-állapotba kellenek. |
| `config/os.toml:24,85`; `core/snapshot.py:807-815` | A `ytdlp` pillanatkép-tároló munkafája a `{os}/modulok/ytdlp` (kód + `source.md`/`metadata.json` adatok egy fában); a `staging` és az `archive` is ott. |
| `core/tasks.py:127, 144`; `core/*_feladat.py` (pl. `core/kartya_feladat.py:78,90`, `core/kviz_feladat.py:66`, `core/osszefoglalas_feladat.py:106,116`, `core/fuzet_feladat.py:65,71`, `core/grafikon_feladat.py:63`, `core/matek_feladat.py:69`, `core/vektorindex_feladat.py:33`, `core/videolanc.py:171,195,317`) | Minden lépés `cwd = cfg.root`, `python -m modulok.<x>` vagy `{modulok}/<x>/__main__.py` — csak olvas, bundle-ben működik, ha `PYTHONPATH` és `MOS_ROOT` a bundle-re mutat. |
| `core/tasks.py:640, 650, 654-676` | A lépés env-je `MOS_ROOT={os}`, `PYTHONPATH={os}`; a DB-ben `{os}`-relatív lépések (rendben). |
| `core/matek_api.py:81-85`; `core/grafikon_api.py:146-150`; `core/cpp_utvonal.py:39,61-63`; `core/cpp_ai.py:35`; `core/modell/kliens.py:272-281`; `core/modell/bench.py:176` | Alfolyamatok `cwd={os}`, `MOS_ROOT`, `PYTHONPATH` — olvasó, de a `cwd`-nek írhatónak nem kell lennie; ellenőrizendő, hogy egyik sem ír relatív útra. |
| `core/modell/halmaz.py` (`Verziok({modulok})`), `core/gepi_iras.py:508`, `core/kereses_api.py:102`, `core/cpp_ai.py:91`, `core/modell/worker.py:340`, `core/fuzet_api.py:51`, `core/modell/eval.py:65` | A D9 aranyhalmaz-verziója a `{modulok}/eval/*/feladat.py`-ból — bundle-ben csak-olvasható, rendben, de **a fejlesztő vaultjából készült aranyadatokat** szállítaná (adatvédelmi kérdés). |
| `core/epites.py:106-107, 141, 146`; `core/server.py:305` | Build-ujjlenyomat a `{os}` git-fájából és a `Manifold.app/Contents/Resources/epites.json`-ból (a gyökérhez képest). |
| `core/mentes.py:132-183`; `config/os.toml:98` | A kódtár-bundle a `{os}/.git`-et feltételezi (bundle-ben nincs → kimarad). |
| `core/teljes_mentes.py:85, 111, 398-411, 540-557` | A teljes mentés forrásgyökere a `{os}`, és `git bundle`-t készít belőle; a visszaállítás egy `{os}`-t épít újra. |
| `core/letoltes.py:130`; `core/doctor.py:261, 312, 338-339, 618, 737, 877` | `{os}/config/{letoltes.toml, runtime-pins.env, requirements.*}`, `{os}/bin/mos` — olvasás (bundle-ben rendben). |
| `core/doctor.py:23-24, 804-825` | `SAJAT_MINTA` HIBA-t ad `/Applications/Manifold` útra és `~/Applications`-re mutató `.app`-ra — egy telepített `/Applications/Manifold.app` a doctor szerint hibás. |
| `core/index/pdfszoveg.py:29-30`; `modulok/homokozo/__init__.py:46-47, 200`; `modulok/homokozo/gyerek.py:21-22`; `modulok/homokozo/program.py:39` | `__file__`-relatív profil- és kódutak — bundle-ben jók (olvasás). |
| `bin/mos:39`, `-B` kapcsolók | `PYTHONDONTWRITEBYTECODE=1` — a bundle nem kap `__pycache__`-t (rendben). |
| `app_dist` (`config/os.toml:44`, `core/server.py:813-825`) | Olvasás — bundle-ben rendben. |

### 7.5 Összegzés: mi kellene a több-workspace-hez (a terv bemenete)

1. **Új gyökér-hármas** a `config.py`-ban: `{os}` (kód, read-only), `{install}` (Application Support), `{workspace}` (a vault kötetén) — az `[utak]` alapértékei ezekre épüljenek, a `bin/mos` beégetett `var/` útjai helyett az `os.toml`-ból (vagy a héj env-jéből) jöjjenek.
2. **Workspace-regiszter a héjban** (melyik vault, melyik workspace-var, utoljára nyitott), és core-onként külön port/titok/`core.lock`; az egypéldányos zár kulcsa a vault legyen.
3. **Installation-szintű zárak**: `modell.lock`, `worker.lock`/`worker.pid` az `{install}` alá — egy worker szolgáljon ki minden core-t (ma a worker-pidfájl `{run}`-ban, `core/modell/kliens.py:35`).
4. **Onboarding-lépések**: vault-mappa kiválasztása/létrehozása, `.obsidian` létrehozása (vagy a kapu lazítása), `Repo.init()` + első commit, workspace-konfig (mappanevek, séma) sablonból, a SZEMÉLYES alapértékek semlegesítése.
5. **Mentés**: a `{backup}` alá workspace-azonosítós almappa (a bundle-rotáció glob-ja ma ütközne).
6. **Kalibráció mint szállított adat**: `router.sqlite` (vagy egy olvasható kalibrációs jegyzék) a bundle-ben; az aranyhalmazok helyett csak a `VERZIO`-k szállítása.
7. **A kódba írók megszüntetése**: `felkeszultseg kalibral --rogzit` → workspace-állapot; a `ytdlp` munkafa/staging/archive → workspace; a doctor kötet-, `/Applications`- és Application Support-szabályainak átírása.
