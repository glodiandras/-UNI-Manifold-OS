# 06 – Tesztkészlet-térkép és vault-konvenció térkép (READ-ONLY audit)

Forrás: `/Volumes/Work/Manifold-OS v2` (semmit nem módosítottam, tesztet nem futtattam; a `var/`, `runtime/`, `app/node_modules`, `modulok/ytdlp/staging`, `modulok/eval/*/` adatait nem olvastam). A számok statikus számlálások (`def test_`, grep), ezért ±5% pontatlanok lehetnek; ahol becslés, jelzem. Hivatkozás: `fájl:sor`.

---

# A) TESZTKÉSZLET-TÉRKÉP

## A1. Hogyan fut

| Réteg | Parancs | Mit futtat | Hely |
|---|---|---|---|
| Python | `bin/mos test` | `python -B -m unittest discover -s tests -t <repo>` (NEM pytest) | `bin/mos:251-263` |
| Python, kijelölt | `bin/mos test test_x tests.test_y tests/test_z.py [-v -k …]` | a név `tests.<n>` alakra normalizálva, `-m unittest <nevek>` | `bin/mos:253-261` |
| Python perf | `bin/mos perf` | `tests/perf_*.py` + vitest `app/tests/perf/*.perf.ts` (tétlen gép, `MOS_TELJESITMENY=1`) | `bin/mos:264-273`, `app/vite.config.ts:9,70` |
| Felület | `bin/mos app test` | `npx vitest run` (jsdom, `tests/**/*.test.ts`, setup `app/tests/beallitas.ts`) | `bin/mos:247`, `app/vite.config.ts:70-78` |
| Kézi/klónos | `bin/mos kapu [kezi] [próba…]` | `tests/kezi/kapu.py` – a valódi vault APFS-klónján futó próbák sorban | `bin/mos:284-285`, `tests/kezi/kapu.py:1-20` |
| Ytdlp-port | a `bin/mos test`-ből, alfolyamatban | `python -m pytest` a `modulok/ytdlp/tests`-en (16 fájl, hálózat nélkül) | `tests/test_ytdlp_port.py:24-35` |
| Lefedettség | `bin/mos exec … tests/kezi/lefedettseg.py` | `sys.monitoring`, `core/` soronkénti | `tests/kezi/lefedettseg.py:1-12` |

Mennyiség: `tests/` 227 bejegyzés = 210 `test_*/perf_*` fájl (kb. **3 985 `def test_`**) + 11 segéd (`helpers.py`, `*_segedek.py`, `legacy_szabaly.py`…) + `kezi/` (37 szkript) + `adat/`. `app/tests`: **152 `*.test.ts`**, 5 `*.kezi.ts`, 2 `*.perf.ts`; `app/src/**/*.test.ts`: **0**. `modulok/*/tests`: csak `modulok/ytdlp/tests` (16 fájl, pytest, `conftest.py`). (A `bin/mos:253` megjegyzés „~1000 tesztje” elavult.)

### Env-ek és keretek
| Env / eszköz | Szerep | Hely |
|---|---|---|
| `MOS_SZIGORU=1` | a kihagyott teszt bukás, kivéve `skipTest("[indokolt] …")`; a futás végén a kihagyások névsora kiíródik | `tests/__init__.py:1-62`, `tests/test_szigoru.py` |
| `MOS_PROBA_FELADAT=1` | csak ekkor regisztrálódik a „próbafeladat” típus (gépi commitot ír, `mp` másodpercig tart) – a leállás/életciklus tesztekhez | `core/probafeladat.py:43`, `core/vezerlo.py:208`, `tests/test_leallas.py:61`, `tests/test_vezerlo.py:89` |
| `MOS_ROOT` | a gyökér felülírása; minden `[utak]` kulcsot felülír a `MOS_<KULCS>` (pl. `MOS_VAULT`, `MOS_BACKUP`), `MOS_CONFIG` a konfig fájl | `core/config.py:22-26,55-58,70-76`; `bin/mos:13` |
| `MOS_API_TITOK` | rögzített API-titok (`tests/__init__.py:API_TITOK`), `setdefault`-tal a teljes folyamatra | `tests/__init__.py:~44` |
| `MOS_PYTHON`, `MOS_NAPTAR_SEGED`, `MOS_HEJ_CLI`, `MOS_LEGACY`, `MOS_CORE_PORT` | Python-választás, ál-EventKit-segéd, ál-héj-CLI, legacy referencia (paritás), core-port | `bin/mos:60`, `tests/test_felkeszultseg_api.py:34`, `tests/helpers.py:87` |
| `TZ=Europe/Budapest` | `budapest_idozona(self)` a `+02:00` fixture-ökhöz | `tests/__init__.py` |
| `tests/helpers.py` | `alg_gyoker`, `alg_core`, `env`, `ir`, `core_indito_szkript`, `tmpdir`, legacy-paritás segédek | `tests/helpers.py:14-114` |

### Az ál-környezet (álvault + ál-`var`) – ez a „keret”
`alg_gyoker(tmp)` (`tests/helpers.py:14-31`) létrehozza: `{tmp}/work/os/{bin,config,var/{state,tmp,cache},runtime}` és `{tmp}/work/Manifold` (az álvault); bemásolja a VALÓDI `config/os.toml`-t és `config/vault-sema.json`-t; stub `bin/mos`-t ír (opcionálisan `core_indito_szkript()` = `python -m core` a repo kódjával). `alg_core(tmp)` (`:73-80`) ehhez hozzáadja az `.obsidian/` mappát, és `config.load({MOS_ROOT, HOME=<tmp>/home})`-ot ad: `(cfg, root, vault)`. A pillanatkép-tároló az ál-`var/vault.git`. `env()` (`:48-70`) hermetikus gyermek-környezet: a `MOS_/UV_/PIP_/XDG_/MANIFOLD_` változókat kiszűri, ál-HOME-ot állít, a belső mentést (`MOS_BACKUP`) álgyökér-lokálissá teszi. Az AST-őr (`tests/test_kezi_kornyezet.py`, `tests/kezi/_kornyezet.py:VALODI_MARAD`) elvárja, hogy minden core/appot indító szkript minden `[utak]` kulcsot elkülönítsen.

Fontos: **a tesztek nem használnak külön, neutrális fixture-konfigot, hanem a fejlesztő valódi `config/os.toml`-ját és `vault-sema.json`-ját másolják** → a tesztek a fejlesztő konvencióit értékként is őrzik (pl. `tests/test_kviz_generalas.py:264` azt állítja, hogy `config.load()["kviz"]["mappa"] == "ATTCHMNTS - quizes"`).

### `tests/adat` (fixture-ök) – személyes jegyzet nincs, de van két érzékeny elem
| Fájl | Tartalom | Személyes? |
|---|---|---|
| `tests/adat/idezet_escape.json` | PDF-idézet escape-vektorok (core ↔ felület) | nem |
| `tests/adat/cpp_diag/*.txt` + `README.md` | g++/clang/ld64 fordítói kimenetek (Ubuntu 24.04) | nem |
| `tests/adat/c18_1/glm_ocr-ocr_keplet.jsonl.gz` (164 sor) | modellválaszok: LaTeX-képletek `IMG_1331-nn` azonosítóval | enyhén (kézírásos füzet képletei, a telefonfotó azonosítója) |
| `tests/adat/c18_1/qwen3_vl_4b-ocr_kezi.jsonl.gz` (97 sor) | **kézírásos iskolai füzetoldalak OCR-je** (`IMG_1289.JPG`: „Gyakorló Anyag / Matematika / 8/B / Házi feladat…”) | **igen** (osztályjel, házi feladat, a fejlesztő füzetfotói) |
| `tests/adat/c18_1/phi4_mini_reasoning-matek_ellenorzo.jsonl.gz` (20 sor) | matek-levezetések, `<think>` blokkok | nem |
A `c18_1` a `var/runs/eval` másolata, használja: `tests/test_eval_ervenyesseg.py:3,14`, `tests/test_osszefoglalas_kontextus.py`. **Termékesítésnél a `qwen3_vl_4b-ocr_kezi` fixture cserélendő/anonimizálandó.** Mellékes találat: a `docs/Manifold OS v2/rendszernaplok/arhivum/audit-2026-10-03/*.json` fájlokban a fejlesztő rendszerfelhasználóneve szerepel (nem vizsgáltam részletesen).
Az inline fixture-ök (a tesztek szövegében) magyar iskolai tartalmat használnak: mappanevek `T01 - Történelem`, `M03 - Algebra`, `F01 - Fizika`, `I23 - A Nyugat`, `T05 - Ady Endre`, `D13 - CS50`, „Matek témazáró”, tantárgy-szavak, 2026-09/10-es dátumok; személynevek, e-mail, iskolanév nincs. A tantárgy-mappakódok (`T01`, `M01`…) 437 helyen szerepelnek a Python-tesztekben, `ATTCHMNTS` 183 helyen / 42 fájlban, `X01 - Napló` 54 / 20, „dolgozat” 199 / 18. Az `app/tests`-ben 19 fájl hivatkozik `ATTCHMNTS`/`X01`-re (45× `F02 - …`).

## A2. Csoportosítás modulonként (Python, `tests/test_*.py`, `perf_*.py`)

| Csoport (névminta) | Fájl | `def test_` | Jelleg |
|---|---|---|---|
| grafikon / homokozó / matek / C++ (`test_grafikon_*`, `test_homokozo*`, `test_matek_*`, `test_cpp_*`, `test_kod_arany`) | 32 | 677 | (e) sandbox-exec, LLVM; sok [indokolt] kihagyás |
| mentés / pillanatkép / vaultio / átnevezés / visszavonás / gépi írás / feladatsor / életciklus / összeomlás (`test_mentes`, `test_snapshot`, `test_vaultio`, `test_atnevezes`, `test_gepi_iras`, `test_eletciklus`, …) | 27 | 554 | (b) + git, APFS, FSEvents; alfolyamat |
| napló / ma / naptár / sablon / tracker / emlékeztető / tulajdonságok / higiénia / PDF-kiemelés / szemelyes_db | 18 | 417 | (b) – **konvenció-központú** |
| core/infra: `config`, `server`, `app`, `mos_es_shell`, `doctor`, `utvonalak`, `dokumentacio`, `indulas`, `forraskod`, `szigoru`, `szivargas`, `kapuk_*`, `fuzet`, `kezi_*`, `*_api` (nem kártya/kvíz…) | 24 | 363 | vegyes; `test_app`, `test_mos_es_shell`, `test_doctor` a `Manifold.app`-ot / `bin/mos`-t / gitet futtatja |
| videó / ytdlp / média / átirat (`test_video_*`, `test_videolanc`, `test_ytdlp_port`, `test_media*`, `test_atirat`, `test_kepek_bukas`) | 16 | 333 | (e) ffmpeg (pinelt), (b) |
| felkészültség (`test_felkeszultseg_*`) | 13 | 267 | (b)/(a) – **konvenció-központú** (dolgozat) |
| index / keresés / hibrid / elemző (`test_index_*`, `test_kereses_*`, `test_elemzo_*`, `perf_index/elemzo`) | 17 | 250 | (b)/(a) |
| modell / worker / eval (`test_modell_*`, `test_eval_*`, `test_core_api`, `test_gepi_api`) | 15 | 250 | (c) álmodellel (lásd lent) |
| asszisztens (`test_asszisztens_*`, `perf_asszisztens`) | 10 | 191 | (b) – **konvenció-központú** (tantárgy-nevek, kizárási listák) |
| kvíz (`test_kviz_*`) | 10 | 136 | (a)/(b) |
| kártya (`test_kartya_*`) | 7 | 126 | (a)/(b) |
| összefoglalás (`test_osszefoglalas_*`) | 9 | 112 | (a)/(b) |
| Bases (`test_bazis_*`, `perf_bazis`) | 12 | 309 | (a) tiszta + (b) |
| **Összesen** | **210** | **~3 985** | |
Felület (vitest): 152 fájl (38 `*.svelte.test.ts` komponens-teszt), jsdom; `app/tests/kezi` (5) és `perf` (2) nem része az alapfutásnak.

### Osztályozás (a)–(e) – heurisztikus, fájlszinten (grep-alapú)
| Osztály | Fájl | ~teszt | Megjegyzés |
|---|---|---|---|
| (a) tiszta unit (nincs tmpdir, alfolyamat, rendszereszköz) | **~55** | ~930 | pl. `test_bazis_{ertekek,fuggvenyek,kifejezes,kiertekelo,modell,hivatkozas,c12b}`, `test_kviz_{formatum,ertekeles,esemeny,mechanikus}`, `test_kartya_formatum`, `test_osszefoglalas_{formatum,kontextus,promptok,szakaszolas,lanc}`, `test_felkeszultseg_{eredmeny,forras,kotes,osszesit,rekonstrukcio,temak,terv,adat}`, `test_index_{elemzo,maszk}`, `test_grafikon_{formatum,jellemzok,vektorok}`, `test_gyakorlas`, `test_szoveg_tisztit`, `perf_elemzo`, `perf_index` |
| (b) álvaultot/ál-`var`-t igényel (`alg_core`/`alg_gyoker`/`tmpdir`) | **~149** | ~2 940 | a készlet gerince; a `FAJLOK`-dictek (`felkeszultseg_segedek.py`, `index_segedek.py:ALAP`, `bazis_segedek`, `grafikon_segedek`, `video_segedek`, `naptar_segedek`) építik a vaultot |
| (c) modell/worker – de **álmodellel** | ~20 fájl (363) | | `tests/modell_segedek.py:AlHatter` (ál-MLX háttér), `al_betolto`; `test_modell_worker` valódi worker-alfolyamatot indít **modell nélkül**; **nincs olyan automata teszt, amely valódi modellt töltene** → „kihagyás modell nélkül” osztály gyakorlatilag nincs; valódi modellhez csak `tests/kezi/{kviz_proba,fuzet_proba}`, `bin/mos eval/bench/kviz proba` |
| (d) valódi vault / `var/` / mentés (tests/kezi) | **37 szkript** (+ `app/tests/kezi` 5) | | ~27 a VALÓDI vault klónján/csak olvasva (`apfs_proba`, `atallas_riport`, `atnevezes_proba`, `bazis_meres`, `canvas_proba`, `graf*_paritas`, `index_meres`, `kor2_olvaso`, `link_*`, `mentes_proba`, `kiadas_mentes` [valódi `~/Manifold-backup`], `proba_app`, `sema_proba`, `szerkeszto_mentes`, `video_*proba`, `emlites_meres`, `hasonlosag_meres`, `kepletek`, `memoria_meres`…); 6 szintetikus (`atallas_probavault`, `bazis_proba`, `k42_proba`, `nagy_vault_meres`, `soak`, `notion_obsidian`); 2 futtató (`kapu`, `lefedettseg`). Osztályozásuk kötelező: `tests/test_kezi_kornyezet.py:34-59` (INDITO/INPROC/OLVASO/GENERATOR/KLIENS/FUTTATO). A Python-tesztek közül a **valódi repó-konfigot olvassák** (`config.load()`): `test_cpp_{ai,api,cli,ellenorzes}`, `test_kod_arany`, `test_kviz_generalas:262`, `test_osszefoglalas_automatika:89`, `test_gepi_iras:496`, `test_grafikon_api:341`, `test_grafikon_cli_c35b:85`, `test_kapuk_{huseg,meres}`, `test_matek_megoldas:390`, `test_modell_atirat:95`, `test_doctor:580`, `test_video_selftest:133` |
| (e) rendszerfüggő | **~37** | ~940 | `sandbox-exec` (~20 fájl: `test_homokozo*`, `test_grafikon_{api,burok,homokozo,meres}`, `test_cpp_*`, `test_matek_*`, `test_kereses_media`, `test_kod_arany`) – `skipUnless(MACOS…)`; **LLVM/clang** a `runtime/llvm`-ből (`VAN = MACOS and _E.kesz() …`, `test_cpp_*`); **ffmpeg** (~15 fájl: `test_video*`, `test_videolanc`, `test_javito3_videolanc`, `test_media`, `test_kepek_bukas`, `test_modell_atirat`, `test_runtime_fetch`, `test_ytdlp_port`); **git** (~17 fájl: `test_snapshot` 38 hivatkozás, `test_vaultio`, `test_mentes`, `test_doctor`, `test_eletciklus`, `test_vezerlo_valtozasok`…); `Manifold.app` (5: `test_app`, `test_mos_es_shell`, `test_cx_epites`, `test_doctor`, `test_kezi_kornyezet`); macOS-only (APFS-klón, FSEvents, `renamex_np`, NFD-nevek, F_FULLFSYNC, EventKit): 36 fájlban `csak_darwin`/`MACOS`/`sys.platform` |
Kihagyási okok (statikus): `skipUnless(VAN…)` 10×, `MACOS`+`sandbox-exec` 9–12×, `websockets` hiánya 7×, `ffmpeg` 3–4×, APFS-klón, `app/dist`, `node_modules`, PyMuPDF, Pillow, git (egyenként 1–2×). Szigorú módban csak az `[indokolt]` előtagúak engedettek.

## A3. A fejlesztő VAULT-KONVENCIÓIHOZ kötött tesztek (jövőbeli „preset-tesztek”)

Jelölők a Python-tesztekben (fájl / előfordulás): `ATTCHMNTS` 42 / 183; tantárgy-mappa (`[A-Z]{1,3}\d{2} - `) 64 / 526; `X01 - Napló & To-Do` 20 / 54; dolgozat 18 / 199; `[pdf.tags]`-érték (History, Mathematics…) vagy `pdf` szekció 36 / 129; séma (`vault-sema`, `mezosorrend`, `status_gazdai`, `ertekkeszlet`) 7 / 63; `AI0x`/`Prjct`/`X03 - Books` 9 / 44; `NN:`/`Canvas:` 33 / 67; `/Média` 10 / 49; `_Template` 8 / 37; magyar hónapnevek 12 / 28.
Legalább egy jelölő: **101 / 210 fájl** (~2 100 teszt); ≥5 jelölő: 62 fájl (~1 480 teszt); jelölő nélkül: 113 fájl.

| Kategória | Fájlok | ~teszt | Mi kell velük a termékesítéskor |
|---|---|---|---|
| **A. Konvenciót DEFINIÁLÓ modul tesztjei** → valódi preset-tesztek | `test_naplo`, `test_ma`, `test_ma_api`, `test_sablon`, `test_naptar*` (3), `test_emlekezteto`, `test_pdfkiemeles`, `test_tulajdonsagok`, `test_higienia*`, `test_tracker*`, `test_gyakorlas`, `test_tanulas_db`, `test_szemelyes_db`, `test_felkeszultseg_*` (13), `test_asszisztens_*` (9) – **40 fájl** | **~875 (~22%)** | a „Diák / AI01 Workflow” preset tesztcsomagja; mellé generikus (default-séma) párt kell írni |
| **B. Konvenciót HASZNÁLÓ (fixture/útvonal-függő)** | `test_automatika`, `test_*_automatika`, `test_kartya_{generalas,formatum,api,apkg*,fsrs}`, `test_kviz_{formatum,api,tar,lanc,cli,generalas,adatbazis}`, `test_osszefoglalas_{formatum,api,lanc,cli,kontextus}`, `test_atirat`, `test_kereses_media`, `test_media*`, `test_binaris_naplo`, `test_fuzet`, `test_video_*` (7), `test_videolanc`, `test_javito3_videolanc`, `test_gepi_iras`, `test_index_graf_meta`, `test_vezerlo_valtozasok`, `test_cx_csatolmany`, `test_atallas_probavault`, `test_config`, `test_dokumentacio` – **42 fájl** | **~795** | főleg a fixture-útvonalak (`ATTCHMNTS - cards/`, `M06 - …`) paraméterezése `COMPANION_ROOT`/`TOPIC` segédre; a logika generikus |
| C. Jelölő nélküli, vault-konvenció-független | ~113 fájl | ~1 900 | változatlanul maradnak (Bases, index-mag, modell, homokozó, mentés-mag, C++ …) |
Becslés: **~40 fájl/~875 teszt átnevezendő „preset-teszt”**, további **~40–60 fájl** csak fixture-paraméterezést kér; ~110 fájl érintetlen. Felület: ~19 `*.test.ts` hivatkozik `ATTCHMNTS`/`X01`-re, ~44 valamilyen konvenció-jelölőre (Matek/Történelem/Dolgozat/…) a 152-ből; a felület-állandók (`app/src/{kartya,kviz,osszefoglalas}/allando.ts:4`) a mappanév tükrei, és vannak őrző tesztek (`[kviz] mappa` komment: „a felület `kviz/allando.ts` előtagja ennek tükre (teszt őrzi)”, `config/os.toml:316`).

## A4. `tests/test_dokumentacio.py` – mit őriz (README/doku ↔ kód)

| Teszt (sor) | Őrzi |
|---|---|
| `:60` `…szerepel_a_keresek_tablaban` | minden regisztrált végpont (`server.regiszter_epit()`) szerepel a `tests/test_utvonalak.py` `KERESEK` táblában (576 soros tábla) |
| `:64,74,78` | minden végpont szerepel a `docs/ARCHITECTURE.md`-ben `` `METÓDUS /út` `` alakban; kivételek (`KIVETEL`) valódiak |
| `:90` | a `CLAUDE.md` „## 1. Rögzített döntések” `\| N \|` sorai 1-től folytonosak, ≥ 43 |
| `:98` | „## 2. A legacy döntései” D1–D12 teljes |
| `:133` | minden regisztrált billentyű (`billentyu: '…'` az `app/src`-ben, ≥25) szerepel a README-ben ⌃⌥⇧⌘ glifként |
| `:139` | a README `` `[szakasz] kulcs` `` hivatkozásai léteznek az `os.toml`-ban (≥4) |
| `:150` | a README „## 7. Parancsok” táblájának `bin/mos` parancsai (≥18) léteznek a `bin/mos` case-ágaiban |
| `:160` | a README relatív linkjei létező fájlra mutatnak (≥8) |
| `:167` | a README tartalmazza: „Asszisztens”, „Tracker”, `local.manifold-os.app.plist`, `~/Manifold-backup`, `docs/KIADAS.md` |
| `:182-205` | `tools/**` alatt nincs merge-jelölő, a `.sh` szkriptek `bash -n`-nel épek, nincs beégetett „Manifold-OS legacy” út |
**Termék-doku hatás:** a README-teszt a szakaszszámokra (`## 7.`/`## 8.`), a fejlesztői szavakra (`~/Manifold-backup`, `plist`, `docs/KIADAS.md`) és a `CLAUDE.md` döntésszámozására támaszkodik – mind törékeny a felhasználói dokumentáció átírásakor. Javaslat: két külön teszt: (1) *fejlesztői doku-konzisztencia* (endpoint-tábla, döntésszámok, `tools/`) változatlan; (2) *felhasználói doku-konzisztencia* (parancsok, beállítási kulcsok, billentyűk, linkek), amely a regiszterekből generált szakaszokat vet össze (nem szakaszszám-alapú parsolás), és a „termék-szavak” listáját konfigurálható.

## A5. Mi kell az új „fresh-install” és „multi-user izoláció” tesztszinthez

Ami MÁR megvan:
| Képesség | Hely |
|---|---|
| Ál-gyökér + álvault + ál-`var` generátor | `tests/helpers.py:14-31,73-80` (`alg_gyoker`, `alg_core`) |
| Egy példányban futó, hermetikus környezet (ál-HOME, ál-backup, nincs `MOS_*` szivárgás) | `tests/helpers.py:48-70`; `tests/kezi/_kornyezet.py` (`elkulonit`, `cfg_elkulonitve`, AST-őr: `tests/test_kezi_kornyezet.py`) |
| Core **in-process**, szálon: `server.start(cfg, stdin=<cső>, out=<gyűjtő>, start_delay=0)`; az első stdout-sor a kézfogás `{port,pid,titok}` | `tests/test_core_api.py:60-82`, `core/server.py:978-998` |
| Core **alfolyamatként**: `core_indito_szkript()` + `python -m core start`, `MOS_ROOT`, stdin-zárás = leállás | `tests/helpers.py:34-37`, `tests/test_eletciklus.py`, `tests/test_leallas.py:61`, `tests/test_mos_es_shell.py` |
| Port-ütközés ellen: `[core] port = 0` (szabad port); a worker `[modellgazda] port = 0`, a tesztek `("127.0.0.1", 0)`-t kötnek; beégetett port nincs (egyetlen `:8080` egy URL-parser tesztmintában) | `config/os.toml:56,402`; `core/server.py:1002` |
| Példányonkénti zár: `{run}/core.lock` (flock) – két core azonos `var/`-on: „foglalt” kézfogás, kilépési kód 75 | `core/server.py:945-995` |
| Konfig példány-szintű (nincs globális config): minden `[utak]` kulcs felülírható `MOS_<KULCS>`-vel | `core/config.py:51-76` |
| Vault-generátorok | `tests/index_segedek.py:ALAP`, `tests/felkeszultseg_segedek.py:FAJLOK`, `tests/kezi/{bazis_proba,k42_proba,atallas_probavault}.py` (determinisztikus), `tests/kezi/nagy_vault_meres.py` (10 000 jegyzet, 50 tantárgymappa), `tests/kezi/soak.py` (~200 jegyzet, saját core) |

Ami HIÁNYZIK / kockázat:
| # | Hiány | Javaslat |
|---|---|---|
| 1 | Nincs **semleges, paraméterezhető vault-generátor** (preset, méret, seed); mindegyik a fejlesztő konvencióit (`X01`, `ATTCHMNTS`, `M06 - …`) építi | egy `tests/vaultgyar.py` (`general(preset="default"|"ai01", n, seed)`), az `ALAP`/`FAJLOK`/`nagy_vault_meres` generátorait ebbe olvasztva |
| 2 | **Fresh-install**: `alg_gyoker` mindig létrehozza a `var/` mappákat, `alg_core` az `.obsidian/`-t; nincs „csak `{os}` kód + konfig, `var/` és vault NINCS” kezdőállapot, sem `.obsidian` nélküli vault, sem üres `.obsidian` | `alg_gyoker(var=False)`, `alg_core(obsidian=False/ures)`; a core indulásának (`server.py:234-246`, `vaultio.py:183-186` – `.obsidian` nélkül „nem érhető el”) fresh-install elvárásait külön tesztelni; a `runtime fetch/install` (hálózat, pinek) csak mockkal (`test_runtime_fetch`, `test_doctor` a minta) |
| 3 | **Multi-user izoláció**: két példány egymás mellett nincs tesztelve. Alfolyamatként biztonságos (külön `MOS_ROOT`/`var`, port 0, külön `core.lock`, külön API-titok); **in-process két core ugyanabban a Python-folyamatban kockázatos**: közös modulszintű állapot (`core/tasks.py:115 REGISTRY`, a tesztek takarítják: `test_core_api.py:~73`; `os.environ["MOS_API_TITOK"]` – a második `server.start`-nak `api_titok=` kell; `corenaplo.indit` csak főszálon) | alfolyamat-keret: `core_pelda(root) -> {port, titok, proc}` a kézfogás-sor olvasásával; két példány, majd: (i) `var/`+vault fák diszjunktak (hash-bejárás), (ii) cross-API (a másik titka 403), (iii) a másik vaultjára mutató `ut` visszautasítása (`vaultkivul`, `vaultio`) |
| 4 | **Globális/OS-szintű erőforrások**, amelyek példányok között megoszlanak és az álvault-keret nem fedi: Apple Emlékeztetők „Manifold” lista (`[emlekezteto] lista`), `~/Library/Preferences/local.manifold-os.app.plist` (`core/doctor.py:374-386`), launchd, `{home}/Manifold-backup` (`[utak] backup`), közös `runtime/` és `models/` (HF_HOME), a modell-zár (`MANIFOLD_MODELL_ZAR`, egy GPU) | ál-EventKit-segéd (`MOS_NAPTAR_SEGED`, megvan), per-user `home`, per-user `MOS_BACKUP`; modell-zár-verseny teszt |
| 5 | A felhasználó-fogalom a kódban nincs: egy példány = egy gyökér = egy vault (`[utak] vault = "{work}/Manifold"`, `config/os.toml:12`) | a „multi-user” = több független példány/profil; a teszt a `MOS_*` útkészlet teljes elkülönítését bizonyítja (a `VALODI_MARAD` engedélylista mintájára, de profilonként) |
| 6 | A tesztkészlet macOS-függő (APFS-klón, FSEvents, `sandbox-exec`, EventKit, `Manifold.app`): a fresh-install/multi-user szint CI-ben csak macOS-runneren futtatható, a `[index] figyelo = "lekerdezes"` tartalék (`os.toml:135`) más OS-hez egy rés | a szint két rétege: platformfüggetlen (config/vault-séma/workspace-init) és macOS-függő (héj, FSEvents) |

---

# B) VAULT-KONVENCIÓ TÉRKÉP

## B1. Konvenció-táblázat

Jelmagyarázat – javaslat: **D** = DEFAULT (általános) séma/viselkedés; **P** = PRESET „AI01 Workflow”; **O** = opcionális modul.

| # | Konvenció | Hol él a kódban | Konfigurálható ma? (os.toml kulcs) | „Sima” Obsidian-vaultban nincs ilyen → mi történik | Javaslat |
|---|---|---|---|---|---|
| 1 | **`.obsidian/` mappa = „valódi vault”** | `core/vaultio.py:181-186` (`Vault.root` → `NemElerheto`), `core/frame.py:129-132`, `core/server.py:234-246`, `core/doctor.py:165`, `core/binaris_naplo.py:55` | nem | `.obsidian` nélküli mappa: minden vault-API „a vault nem érhető el”, az indulási helyreállítás kimarad, doctor FIGYELEM | **D**: a workspace-létrehozás hozza létre (üres `app.json`); a feltételt `workspace.toml`-ra cserélni, az `.obsidian`-t kompat-adapterré tenni |
| 2 | Napi jegyzet útja `[X01 - Napló & To-Do]/YYYY-MM/[Napló]/YYYY-MM-DD` | `core/naplo.py:25` (`ALAP_UT`), `:31-56`; `core/ma.py:71` | **igen** `[naplo] ut`, `sablon`, `canvas` (`os.toml:179-183`) | a kulcs nélkül is létrehozza a (nem létező) `X01 …/YYYY-MM/Napló/` mappafát (`mappa_keszit`); működik, de a vault-szerkezetbe idegen mappát épít | **D**: `Daily/YYYY-MM-DD` (vagy `daily-notes.json` olvasása); **P**: a mai érték |
| 3 | Napi váz: `Tags: [Napló]`, `Source/Status/NN/Canvas` üres kulcsok, `# Napló` | `core/naplo.py:71-76` (`alapvaz`), `:79-90` (`_vaz`: a sablonmappa „Napi jegyzet” felülírja) | részben (`[naplo] sablon`) | séma-sértés (ld. 9. sor) vagy idegen kulcsok kerülnek a jegyzetbe | **D**: üres váz/felhasználó sablonja; **P**: a 5-kulcsos váz |
| 4 | Sablonmappa `_Template` | `core/sablon.py:36,198-204,215-228`; `config/os.toml:173-177` | **igen** `[sablon] mappa`, `datum`, `ido`, `nyelv` | hiányzó mappa → üres lista (nem hiba, `sablon.py:215-218`); a komment szerint „az Obsidian templates.json-jával azonos”, de **a kód NEM olvassa** a `.obsidian/templates.json`-t | **D**: `templates.json` `folder` olvasása + `[sablon] mappa` felülírás |
| 5 | Sablon dátumnevek: magyar hónap/nap (`jan.`, `márc.`…) | `core/sablon.py:41-63` (`_NEVEK` hu/en) | **igen** `[sablon] nyelv` = `hu`\|`en` | hu alap: egy angol vaultban a `{{date:MMMM}}` magyarul ír | **D**: `en` vagy a rendszer-locale; **P**: `hu` |
| 6 | **`ATTCHMNTS - ` előtag = gépi kísérőjegyzet/melléklet** (cards, quizes, summaries, photos, Videos) | `core/automatika.py:47,117-119` (`tartalmi_ut`); `core/index/hibrid/hasonlo.py:23`; `core/osszefoglalas_api.py:147`; `core/kviz_api.py:36`; `core/kartya_api.py:52`; `modulok/grafikon/automatika.py:99`; `modulok/ytdlp/egyezes.py:38`; `core/atirat.py:24`; `core/gepi_iras.py:818-821`; felület: `app/src/{kartya,kviz,osszefoglalas}/allando.ts:4`, `osszefoglalas/parancsok.ts:18`, `kviz/index.ts:13`, `szerkeszto/renderelok/plot/beiras.ts:16`; `config/vault-sema.json:12-32` (`utvonal_elotag`); `core/asszisztens/beallitasok.py:7,18,44` | **részben és ELLENTMONDÁSOSAN**: a mappanév konfigurálható (`[kartya] mappa`, `[kviz] mappa`, `[osszefoglalas] mappa`, `[fuzet] cel_mappa`, `[video] vault_mappa`, `[media] video_mappa`), de a „kísérő = `ATTCHMNTS - `-előtagú” felismerés **beégetett** 6+ kódhelyen, a sémaosztályok pedig a `vault-sema.json`-ban külön, szintén fixen | átnevezett mappa esetén: a kísérőjegyzetekre kártyát/összefoglalót/említést generálna (nem „tartalmi”-ként szűrné ki), a gépi írás `uj` műveletnél 400 (a sémaosztály az útja szerint nem egyezik: `gepi_iras.py:775-780`) | **D**: EGY forrású `[workspace] companion_root` + alkönyvtárak; a kód és a séma ebből származtatott. **P**: `ATTCHMNTS - …` |
| 7 | Frontmatter-séma: `Tags, Source, Status, NN, Canvas` (+`version`) sorrenddel | `config/vault-sema.json:3-4`; `core/tulajdonsagok.py:69-101,302-360` | **igen**: `[sema] vault` a JSON útja (`os.toml:92-93`) – de a motor nem tud „szabad” módot | minden jegyzet: `mezosorrend` SÉRTÉS (higiénia `sema_sertes` FIGYELEM minden fájlra; szerkesztésnél megerősítés kell); ismeretlen kulcs: sértés (`tulajdonsagok.py:316-323`); gépi **új** `.md` ír: 400-zal elutasítja a sértőt (`gepi_iras.py:780-783`) | **D**: tanácsadó/kikapcsolható séma (ld. B2); **P**: a mai |
| 8 | `Tags` értékkészlet = tantárgyak (History, Literature, Mathematics, Physics, Informatics, Grammar, English, Íráskészség, AI, Workflow, Projekt-1, Napló) | `config/vault-sema.json:6`; `core/tulajdonsagok.py:347-351` (`ertekkeszlet` sértés; ≥2 jegyzet használata legitimál, CX-002) | igen (JSON) | az értékkészlet nélkül minden első használat sértés („nincs az értékkészletben”) | **D**: nincs értékkészlet-ellenőrzés (`null`); **P**: a lista |
| 9 | `Status` értékkészlet (Completed/In progress/Review) + **„gazdai” Status: gép nem ír** | `config/vault-sema.json:7-8`; `core/tulajdonsagok.py:77,507-510`; `core/gepi_iras.py:788,805` | igen (JSON, `status_gazdai`) | ha nincs Status, nincs hatás; ha van más értékkészletű Status: sértés | **D**: opcionális, `status_gazdai` kikapcsolható; **P**: igen |
| 10 | **H1 = fájlnév** (a `NN[F] - ` előtag nélkül) – `hiba` szintű, megerősítéssel sem írható | `config/vault-sema.json:41-50`; `core/tulajdonsagok.py:435-485`; `core/gepi_iras.py:780,803,964` | igen: a `"h1"` kulcs elhagyása kikapcsolja (`tulajdonsagok.py:442` `if not h: return []`) | a gép által létrehozott/módosított jegyzetnél 400, ha az új H1 nem a fájlnév (csak az ÚJ sértés akadály a `csere`-nél) | **D**: `h1` kulcs nélkül (kikapcsolva); **P**: bekapcsolva |
| 11 | Sémaosztályok útelőtag szerint: `kviz`, `kartya`, `osszefoglalo`, `konyv-jegyzet` (`X03 - Books/`) | `config/vault-sema.json:11-39`; `core/tulajdonsagok.py:89-101` | igen (JSON) | a `konyv-jegyzet` csak a fejlesztő `X03 - Books/` mappájára hat; a három kísérő-osztály **kell** a gépi íráshoz | **D**: a 3 kísérő-osztály (származtatva a companion_root-ból); `konyv-jegyzet`→**P** |
| 12 | Beégetett, fejlesztő-specifikus kivételek: `AI01 - Workflow System/2.0/`, `AI02 - Log/`, `AI03 - Memória/`, `Prjct01 - Obsidian/`, `X01 …`, `_Template/`; `sema_nelkuli_utak` (`AI01 …/CLAUDE.md`, `MEMORY.md`) | `config/vault-sema.json:45,52`; `core/asszisztens/beallitasok.py:7,18,44`; `modulok/ytdlp/egyezes.py:38` | részben (`[asszisztens] higienia_arva_kizart`, `emlites_kizart`, `kartya_kizart`) | sima vaultban egyszerűen nem illeszkednek (ártalmatlan) | **P** |
| 13 | `## Gyakorlás` szakasz + `![[kísérő]]` beágyazás | `core/gyakorlas.py:20-21,29-41` (egyetlen hely); `core/gepi_iras.py:113` (`szakasz_beszur`) | nem | a hiányzó szakaszt a jegyzet végén létrehozza (nem törik); a magyar szakasznév fix | **D**: konfigurálható nevű szakasz (`## Practice`); **P**: `Gyakorlás` |
| 14 | Kísérőjegyzet-nevek és -formátum: ` — kártyák`, ` — Kvíz ÉÉÉÉ-HH-NN ÓÓPP`, ` — összefoglaló`; kulcsok `Source/Modell/Keszult` (+`Kviz`, `Osszefoglalas`, `Szint`) | `modulok/kartya/formatum.py:32,101-108,212-218`; `modulok/kviz/formatum.py:63,132-139,164-166,228-235,258`; `modulok/osszefoglalas/formatum.py:43-44,186-188,233-236`; a kvíz H1-regex a séma JSON-ban (`vault-sema.json:16`) | részben (`[kartya] utotag`, `[osszefoglalas] utotag`); a kvíz utótagja és a kulcsnevek fixek | **működik** sima vaultban, ha a 3 sémaosztály megvan; a magyar ASCII-kulcsnevek (`Keszult`, `Osszefoglalas`) idegenül hatnak | **D**: marad, de a nevek `[kartya]/[kviz]/[osszefoglalas]` alatt egységesen konfigurálhatók |
| 15 | **PDF-kiemelés**: ` – kiemelések.md`, váz `Tags/Source/Status/NN/Canvas`, `Source` = `"[[X.pdf#page=N]]"` lista | `core/pdfkiemeles.py:31-32,54-62,65-69,309-316,331` | részben (`[pdf.tags]`) | működik; a váz mindig beír 4 üres, séma-kulcsot (zaj egy sima vaultban); a `Source`-írás `modosit(…, megerosit=True)` megkerüli a séma-megerősítést | **D**: váz csak `Source` (+`Tags`, ha van címke); **P**: teljes váz |
| 16 | **`[pdf.tags]` betű → tantárgy-címke** a legfelső mappa első betűjéből; **a beégetett `ALAP_TAGS` mindig beleolvad** (`M,F,T,I,D,N,E`) | `config/os.toml:387-395`; `core/pdfkiemeles.py:32,54-62` | igen, de **nem törölhető az alap** (`dict(ALAP_TAGS).update(config)`) | **hamis találat**: bármely `M…`, `F…`, `T…`, `I…`, `D…`, `N…`, `E…` kezdőbetűs mappa („Notes/”, „Termékek/”) tantárgyat kap (Grammar, History…) – a tracker és a PDF-váz is | **D**: nincs betű-térkép; tantárgy = explicit leképezés vagy mappanév (ld. B3); **P**: a mai betű-térkép |
| 17 | **Téma-mappa minta `<Betű><két szám> - <cím>`**; a `…00 - ` = vizuális mappa | `core/videolanc.py:207,219-237,262`; `modulok/ytdlp/egyezes.py:7,37,68,158`; `modulok/ytdlp/integralas.py:164-167,288-290` | nem | videó-bevitelnél a „Célmappa (téma)” ellenőrzés elutasít minden más nevet (`TemamappaHiba`); a téma-modell/horgonyzás nem talál témát | **D**: tetszőleges mappa témának jelölhető; **P**: a mai minta |
| 18 | `[A-Z]\d\d` stb. a `NN` tulajdonság = „témalinkek” | `core/felkeszultseg/temak.py:15,59-85` (`KULCSOK = ("source","nn")`) | nem | `NN` nélkül a felkészülési jegyzet maga az egyetlen téma (`onmaga`) – nem törik | **O** (diák-modul) |
| 19 | **Dolgozat-felkészülés**: `<hónap>/Dolgozatok/ÉÉÉÉ-HH-NN - Tantárgy.md` + „Dolgozat kiértékelő”/„Dolgozat Napló” jegyzetek, `Eredmény:: 16/23` mező, magyar szabadszöveg-kinyerő | `core/naplo.py:34`; `core/felkeszultseg/kotes.py:25,54-71`; `core/felkeszultseg/adat.py:36-64`; `core/felkeszultseg/eredmeny.py:1-60`; `core/ma.py:142-191` | igen (`[naplo] dolgozat_mappa`, `kiertekelo_nevek`; `[felkeszultseg]` 30+ kulcs) | nincs dolgozat → „nincs ilyen dolgozat / nincs felkészülési jegyzet” üzenetek, üres Ma-kártya (nem törik, `osszesit.py:228-232`); a kinyerő magyar nyelvű (lett, kaptam, értem el…) | **O**: „Diák / felkészülés” modul, **P**-be |
| 20 | **Naptár-kategóriák** (Me-time, Tanulás, Órarend, Edzés, Határidők és dolgozatok, Egyéb, Ünnep) + magyar kulcsszavak + **TARGYAK** szótár (Matematika, Fizika, Történelem, Irodalom, Nyelvtan, Német, Angol, Digitális kultúra, Biológia, Kémia, Földrajz, Programozás) | `core/naptar.py:33-59,63-78,95-130,157-162`; `core/ma.py:121-125,173` | részben: a tantárgyszótárat `[naptar.targyak]` **bővíti** (nem csökkenti; a szakasz az `os.toml`-ban nincs is felvéve), `[naptar] tanulas_naptar` | nincs EventKit/naptár: üres; kategória nélkül „egyeb” (kézzel állítható: `naptar.py:304`); az EventKit macOS-függő | **O** (naptár-modul), a szótárak **P** |
| 21 | Média-réteg `<Téma>/Média/` (felirat, `info.json`, forrásleíró jegyzet), `ATTCHMNTS - Videos` | `core/atirat.py:5-9,24-25,44`; `core/higienia.py:122-123,303`; `core/videolanc.py:310` | **igen** `[media] reteg_mappa`, `video_mappa`, `nyelvek`, `[video] vault_mappa` | hiányzó réteg → üres átirat („nincs találat: hiány és nem tévedés”) | **D**: `Média`→`Attachments/Media`; a videólánc **O** |
| 22 | Higiénia: `Canvas` és `Source` frontmatter-linkek „szerkezeti” (nem kapcsolat); a canvas-ból érkező link számít | `core/higienia.py:269-293`; `core/asszisztens/beallitasok.py:6-8` | **igen** `[asszisztens] higienia_arva_*` | sima vaultban a `Source`/`Canvas` kulcs nem jelentkezik → semmi hatás | **D** marad (konfig) |
| 23 | Tag-kezelés: `tags`/`tag` kulcs, `#címke` | `core/index/elemzo.py:42-43,174-177,354-358` | – | Obsidian-standard, kompatibilis | **D** marad |
| 24 | Tulajdonság-típusok a `.obsidian/types.json`-ból | `core/index/elemzo.py:444-452`; `core/index/indexelo.py:394,492`; `core/bazis/adat.py:115,135` | – | hiányzó fájl → `{}` → a típus az értékből/leggyakoribbból | **D** marad |
| 25 | Füzetlánc: `ATTCHMNTS - photos`, szakasz `## Füzet`, tantárgybetű-térkép (M=Matematika, F=Fizika, T, I, N=Magyar nyelvtan, D=Digitális kultúra, E=Angol nyelv), külső mappák | `modulok/fuzet/modszer.py:30-31,105-110,116,178`; `config/os.toml:369-379`; `core/gepi_iras.py:821` | igen (`[fuzet]`), de a betű→név térkép beégetett, a `[pdf.tags]` másolata | diák-specifikus, sima vaultban értelmetlen | **O/P** |
| 26 | Asszisztens tantárgy-nevek (EN címke → HU név) | `config/os.toml:962-970`; `core/asszisztens/beallitasok.py:45` | igen (`[asszisztens.tantargy_nevek]`) | címke nélkül a javaslatban a címke-azonosító jelenik meg | **P** |
| 27 | Napi/dolgozat „Canvas” havi canvas (`YYYY-MM.canvas`) | `core/naplo.py:26,59-68,71-76` | igen `[naplo] canvas` | nincs canvas → `Canvas:` üres (nem törik) | **P** |

## B2. A frontmatter-séma (`config/vault-sema.json`) – mennyire magyar/személyes, és egy minimális alapséma

**Felépítés (54 sor):** `mezosorrend` (`:3`), `extra_kulcsok` (`version`, `:4`), `tags_ertekkeszlet` (`:6`), `status_ertekkeszlet` + `status_gazdai` (`:7-8`), `kivetel_osztalyok` (`:10-40`: `kviz`, `kartya`, `osszefoglalo`, `konyv-jegyzet`), `h1` szabály (`:41-50`: `szabaly: "fajlnev"`, `sorszam_elotag` `^\d+[A-Z]? - `, `kivetel_utvonalak`, `kivetel_osztalyok`: megoldás-sorszámos, érettségi témakör, sablon-váz), `sema_nelkuli_utak` (`:52`). Betöltés: `core/tulajdonsagok.py:69-101` (`Sema.betolt` ← `[sema] vault`, `os.toml:92-93`).

| Elem | Kötelező? | Értékkészlet | Magyar/személyes mértéke |
|---|---|---|---|
| `Tags, Source, Status, NN, Canvas` (sorrendben) | „tanácsadó” (SERTES, megerősítéssel írható), a gépi új jegyzetnél HIBA | – | angol kulcsnevek, de az `NN` (kapcsolt témák) és a `Canvas` (havi napló-canvas) a fejlesztő saját workflow-ja (AI01) |
| `Tags` | ellenőrzött | 12 érték: 6 tantárgy-címke (History, Literature, Mathematics, Physics, Informatics, Grammar), English, **Íráskészség**, AI, Workflow, **Projekt-1**, **Napló** | **erősen személyes**: tantárgyak + saját projektek |
| `Status` | ellenőrzött, gazdai | Completed / In progress / Review | általános, de „gép nem ír” szabály |
| `kviz` / `kartya` / `osszefoglalo` osztályok | a gépi íráshoz kötelező | mezősorrend `Source,Kviz,Modell,Keszult` stb. | gép-formátum, nem személyes (csak az előtag `ATTCHMNTS - …`) |
| `konyv-jegyzet` (`X03 - Books/`: `Szerző, Műfaj, Rate, Status`) | – | – | személyes |
| `h1` | HIBA szint | fájlnév = H1 | fejlesztői szokás |
| `kivetel_utvonalak`, `sema_nelkuli_utak` | – | – | teljesen a fejlesztő vaultjának mappái |

**A motor korlátai az általános séma szempontjából** (`core/tulajdonsagok.py:316-323,347-360`): üres `mezosorrend` esetén minden kulcs „ismeretlen_kulcs” sértés; üres `tags_ertekkeszlet`/`status_ertekkeszlet` esetén minden első érték „nincs az értékkészletben” sértés. Azaz **a mai motorral „szabad séma” NEM fejezhető ki** konfigból; kell: (1) `ismeretlen_kulcs: engedett|jelez`, (2) `tags_ertekkeszlet: null` = nincs ellenőrzés (ugyanígy `status`), (3) `mod: "ki"|"tanacsado"|"szigoru"` globális kapcsoló, (4) a `h1` kulcs elhagyása már ma kikapcsolja.

**Minimális általános alapséma**, amely mellett a kártya/kvíz/összefoglaló kísérőjegyzet és a PDF-kiemelés működik (mivel a három formátum-elemző csak `Source`, `Modell`, `Keszult`, `Kviz`/`Osszefoglalas`/`Szint` kulcsokat olvas – `modulok/kartya/formatum.py:101-108`, `kviz/formatum.py:258-271`, `osszefoglalas/formatum.py:233-236`; a `Tags/Status/NN/Canvas` egyiknek sem kell; a PDF-kiemelés csak a `Source` listát írja a tulajdonság-szerkesztőn át):
```json
{
  "mod": "tanacsado",
  "mezosorrend": [],
  "extra_kulcsok": [],
  "tags_ertekkeszlet": null,
  "status_ertekkeszlet": null,
  "status_gazdai": false,
  "kivetel_osztalyok": [
    {"nev": "kartya",       "utvonal_elotag": ["<companion_root>/cards/"],     "mezosorrend": ["Source","Modell","Keszult"], "tartalmi": false, "h1": false},
    {"nev": "kviz",         "utvonal_elotag": ["<companion_root>/quizzes/"],   "mezosorrend": ["Source","Kviz","Modell","Keszult"], "tartalmi": false},
    {"nev": "osszefoglalo", "utvonal_elotag": ["<companion_root>/summaries/"], "mezosorrend": ["Source","Osszefoglalas","Szint","Modell","Keszult"], "tartalmi": false, "h1": false}
  ]
}
```
(csak a `mod`, a `null`-értékkészlet és az `<companion_root>` helyettesítés új; a `h1` kulcs elhagyva = kikapcsolva). A kísérő-osztályok útelőtagját a kódnak a `companion_root`-ból kell származtatnia (B1/6. sor), nem külön JSON-ból.

## B3. A tantárgy-fogalom – hány modul függ tőle

A „tantárgy” ma **három, egymástól független forrásból** él: (i) `[pdf.tags]` betű → címke (angol címke), (ii) `modulok/fuzet` saját betű → magyar név (`modszer.py:30-31`, a `[pdf.tags]` másolata), (iii) a `naptar.TARGYAK` névszótár (magyar kanonikus név + rokon szavak, `core/naptar.py:63-78`). A `[asszisztens.tantargy_nevek]` az (i) címkéit fordítja le (`os.toml:962-970`).

| Modul / funkció | Mi a tantárgy-forrás | Hely |
|---|---|---|
| **Tracker** (tanult idő tantárgyanként, `tr_aktiv` – a címke **íráskor tárolódik**) | `pdfkiemeles.cimke` (legfelső mappa első betűje) → „Egyéb” | `core/tracker.py:177-181,284,298,391,604` |
| **PDF-kiemelés váz** (`Tags`) | első betű (+ beégetett `ALAP_TAGS`) | `core/pdfkiemeles.py:32,54-62,331` |
| **C++ feladat váz** (`Tags`) | ugyanaz | `core/cpp_utvonal.py:216` |
| **Kártya-automatika szűrő** (auto-fogyasztó; most `be=false`, de a kód él) | `felso[0][:1] in [pdf.tags]` | `core/kartya_feladat.py:102-112` |
| **Összefoglaló-automatika szűrő** | ugyanaz (delegál) | `core/osszefoglalas_feladat.py:122-129` |
| **Videó-bevitel** (célmappa-ellenőrzés, téma-modell, horgonyzás) | `<Betű><két szám> - <cím>` + betű ∈ `[pdf.tags]` | `core/videolanc.py:207-237,262,302`; `modulok/ytdlp/egyezes.py:37,68,158`; `modulok/ytdlp/integralas.py:164-167,288` |
| **Füzetlánc** | saját betű→név térkép | `modulok/fuzet/modszer.py:30-31,105-116,178` |
| **Asszisztens – szokás/napszak-minta** (a tracker tantárgyából) | tracker + `tantargy_nevek` | `core/asszisztens/szokas.py:41-91`, `beallitasok.py:45` |
| **Asszisztens – említés-javaslat** | a legfelső mappa **neve** (nem betű) | `core/asszisztens/emlites.py:178-203` |
| **Naptár / tanulási blokk / felkészültség / dolgozat-kötés** | NÉV-alapú szótár (`naptar.targy()`), a felkészülési jegyzet fájlnevéből | `core/naptar.py:63-78,108-130,233-238`; `core/felkeszultseg/kotes.py:54-71`; `core/felkeszultseg/forras.py:56-60`; `core/ma.py:142-160` |
| Felület | `app/src/tracker/StatisztikaNezet.svelte`, `app/src/dolgozat/*`, `app/src/lib/tracker/*`, `lib/naptar/tipusok.ts`, `lib/asszisztens/tipusok.ts` | – |
**Összesítés: 9 modul/funkció függ a betű-térképtől (tracker, PDF-váz, C++-váz, kártya-auto, összefoglaló-auto, videó-bevitel, füzet, szokás-minta + UI-statisztika), 3 függ a névalapú szótártól (naptár, felkészültség, dolgozat-kötés), 1 a mappanévtől (említés).**

**Generikus megfelelő (javaslat):**
1. `workspace.toml` → `[subjects]` tábla: `id → {label, match: "<glob|regex|prefix>", tag?}` (a mai `[pdf.tags]` + `ALAP_TAGS` + `fuzet.TANTARGYAK` + `naptar.TARGYAK` EGY forrásba), és egy `subject_of(path, note_props) -> id|None` függvény, amelyet minden fenti hely hív.
2. Feloldási sorrend: (a) jegyzet-szintű opcionális `Subject` tulajdonság (frontmatter), (b) a `[subjects]` mintája az útra, (c) alap: a legfelső mappa **neve** mint címke (nincs betű-konvenció, nincs hamis találat), (d) „Egyéb”.
3. „Topic folder” = tetszőleges nevű mappa; a `<Betű><két szám> - <cím>` minta a **P** presetben `topic_pattern` regex, a DEFAULT-ban nincs (a videó-bevitel „célmappa” bármely meglévő mappa lehet).
4. A tracker tárolt `tantargy` oszlopa (íráskor rögzített címke) miatt migráció/újraszámolás kell, ha a térkép változik (`core/tracker.py:284,298`).
5. A felkészültség/dolgozat-fogalom (`ÉÉÉÉ-HH-NN - Tantárgy.md`, `NN` témalinkek, `Eredmény::`) opcionális **diák-modul** (preset), nem alapfunkció.

## B4. Obsidian-kompatibilitás: milyen `.obsidian/*.json` fájlokat olvas a kód

| Fájl | Olvasó | Mit olvas | Hiányában |
|---|---|---|---|
| `app.json` | `core/csatolmany.py:109-136` (`beallitas`, `mappa`; „a beállítás EGYETLEN olvasója”, 80(c)) | `attachmentFolderPath` (`""`/`/`→gyökér, `./x`→a jegyzet mappája, egyéb→a gyökértől) | `''` = vault-gyökér (az Obsidian alapja); nem szöveges érték → 400 |
| `app.json` | `core/vaultio.py:402-413` (`uj_fajl_beallitas`) és a link-célú új jegyzet `:415-…`; felület: `app/src/szerkeszto/linkek/navigacio.ts:47` | `newFileLocation` (`root`/`current`/`folder`), `newFileFolderPath` | `root`, `/` |
| `graph.json` | `core/index/graf_meta.py:74-100`; felület `app/src/lib/graf/beallitasok.ts`, `graf/GrafVezerlo.svelte` | `colorGroups` (lekérdezés, szín), `centerStrength`, `repelStrength`, `linkStrength`, `linkDistance`, szűrők | `{"van": False}`; a felület a fájltípus-színeket és alapértékeket használja; **csak olvas, soha nem ír** |
| `types.json` | `core/index/elemzo.py:328,444-452`; `core/index/indexelo.py:394,492` (változáskor újraszámol); `core/bazis/adat.py:115,135` | `types` (tulajdonság → típus) | `{}`; a típus az értékből / a leggyakoribbból |
| `templates.json` | **nincs olvasó** (a `[sablon] mappa` kézzel szinkronban tartott; `os.toml:173` komment) | – | – |
| `daily-notes.json`, `appearance.json`, `bookmarks.json`, `core-plugins.json`, `hotkeys.json`, `workspace.json`, `community-plugins.json` | nincs | – | – |
| maga a `.obsidian/` mappa | `vaultio.py:183`, `frame.py:132`, `server.py:234-246`, `doctor.py:165` | létezése | lásd B1/1: nélküle a vault „nem érhető el” |
A `.obsidian/`-ba a 2.0 nem ír (24(b); `core/index/graf_meta.py:75`, `csatolmany.py:112`). **Új, üres workspace viselkedése** (`.obsidian/` létezik, de üres): az indexelés, a keresés, a gráf, a szerkesztő és a csatolmány-feltöltés kulcs nélkül is működik (alapértékek); a sablonlista üres; a „Ma” oldal napi jegyzete a `[naplo] ut` szerinti (X01…) mappafát hozza létre; a séma minden jegyzetre sértést jelez; a videó/füzet/dolgozat/naptár funkciók üres állapotban maradnak (nem törnek). Javaslat: a workspace-init (1) létrehozza az `.obsidian/`-t, (2) a hiányzó `templates.json`/`daily-notes.json` értékeit olvassa fel (Obsidian-kompat), (3) saját beállításait `.manifold/workspace.toml`-ban tartja.

---

# ÖSSZEGZŐ JAVASLATOK (a workspace-absztrakcióhoz)

1. **Egy forrású workspace-konfig** (`companion_root`, `daily`, `templates`, `subjects`, `schema mód`) – a mai szétszórt beégetett értékek (6+ kódhely az `ATTCHMNTS - `-re, 3 különálló tantárgy-térkép) megszüntetése; a `vault-sema.json` kísérő-osztályai ebből származzanak.
2. **Séma-motor „tanácsadó/ki” mód + `null` értékkészlet** (`core/tulajdonsagok.py:316-360`), így a DEFAULT séma szabad lehet; a H1-szabály már ma kikapcsolható.
3. **`ALAP_TAGS` beolvadás megszüntetése** (`core/pdfkiemeles.py:56`): jelenleg hamis tantárgy-címkét ad bármely M/F/T/I/D/N/E betűs mappának.
4. **Preset-modulok**: Diák/AI01 (dolgozat-felkészülés, naptár-szótárak, füzetlánc, tantárgybetűk, X01 napló, `X03 - Books`), a hozzájuk tartozó ~40 fájl/~875 teszt átcsoportosítása (`tests/preset_ai01/`), a többi ~40–60 fájl fixture-paraméterezése.
5. **Tesztkeret**: semleges, paraméterezhető vault-generátor; `alg_gyoker(var=False)`/`.obsidian`-nélküli kezdőállapot a fresh-install szinthez; alfolyamat-alapú `core_pelda()` két párhuzamos példányhoz (az in-process kettő a `tasks.REGISTRY` és a `MOS_API_TITOK` miatt kockázatos); `qwen3_vl_4b-ocr_kezi.jsonl.gz` fixture lecserélése.
