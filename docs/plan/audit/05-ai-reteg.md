# 05 — Az AI-réteg („measured AI”) termékesítésének alapozása

Forrás: `/Volumes/Work/Manifold-OS v2` (csak olvasva, 2026-10-15). Semmi nem futott (`bin/mos` sem), modell nem töltődött.
A `var/models` csak listázva; a `var/router.sqlite` egyszer `immutable=1` módban olvasva (a WAL nélkül, ezért a legutóbbi
írások hiányozhatnak belőle). Aranyhalmaz-adat (`arany.json`, `katalogus.json`, `parok.json`, `forrasok/`, `feladatok/`) nem volt
megnyitva: a feladatokról a `feladat.py` kód és a docstringje alapján írok.

Hivatkozások: `fájl:sor`. Rövidítések: **MM** = Model Manager, **SU** = Setup (modelltesztelő) felület.

---

## 0. Vezetői összefoglaló

1. A réteg tiszta és mérésközpontú. **Egy worker-folyamat** fut, benne **egy modell** (plusz legfeljebb egy beágyazó mellette).
   A router a `router.sqlite` kalibrált sorai közül választ, a gépi írás kapuja pedig másodszor is ellenőriz (D9). Ez a két réteg
   a termékben is megtartható.
2. **A „kalibrált” jelet ma ember adja** (`--kalibralt` kapcsoló). A kódban **nincs pontszám-küszöb**, a használati küszöbök
   csak a `docs/MERES-2026-10-07.md` 3. fejezetében állnak. Ha az SU „Modell tesztelése” gombja automatikusan jelet adna, egy
   gyenge, de érvényes (nem levágott, nem hurkolt) modell is kalibrált lenne. → **A küszöb kódba kell** (új `[kalibracio.<f>]`
   szakasz; a feladat szövege ilyet említ, de az `os.toml`-ban jelenleg nincs).
3. **Az aranyhalmazok többsége a fejlesztő vaultjából épül** (fotók, jegyzetek, kijelölések, videók). Szállítható alapot ma
   csak a `kod`, a `kiegeszites`, a `matek`/`matek_cas`/`matek_ellenorzo` és részben a `grafikon` adhat. A többihez anonim,
   licenctiszta halmaz kell, vagy helyben, a felhasználó saját vaultjából épített halmaz (a `kijeloles_keszit.py` jó minta).
4. **A modell-regiszter két forrásból áll**: a `config/letoltes.toml` és az `os.toml [modellek.*]` szakasza, amelyek feladatlistái
   eltérnek. Hiányzik a telepítettség valódi ellenőrzése, a lemezen mért méret, a törlés, a strukturált haladásjelzés, a
   konvertáló, a nyelv mező, és a „funkció → feladat → modell” adatleképezés.
5. **A degradáció funkciónként eltérő.** A keresés, az asszisztens és a videólánc szépen lép vissza, a füzetlánc viszont
   fotónként `KliensHiba`-szöveggel bukik. A felhasználó ma sok helyen CLI-zsargont lát (`mos eval --rogzit --kalibralt`, „D9”).
6. **A több fiókos vagy több workspace-es futás nincs megoldva.** A „gépszintű” modellzár valójában a telepítés `{state}`-je alatt
   van. Két telepítés így két modellt tölthet be egyszerre, két 9 GB-os kerettel; közös telepítésnél pedig a 0644-es zárfájlok
   miatt a második fiók hibával áll meg.
7. **Minden promptot, minden kimeneti jelölőt és minden lexikai kaput magyarra szabtak.** A router kalibrációs kulcsában
   (feladat × modell) nincs nyelv, így a magyar whisper-finomhangolás angol videóra is futna.

---

## 1. A router és a kalibráció modellje

### 1.1 A `[router] feladatok` lista (`config/os.toml:442-444`) — mire való, mi függ tőle

| Router-feladat | Mire való | Felhasználói funkció (hívó) | Kalibrált ma (`router.sqlite`, fő fájl) | Aranyhalmaz-mappa |
|---|---|---|---|---|
| `ocr_kezi` | kézírásos füzetlap átirata | Füzetfotó-bekötés, 2. lépés, átirat (`modulok/fuzet/lanc.py:161`); az átirat az indexbe kerül (`core/fuzet.py:6`); „beszúrás az aktív jegyzetbe” módban a forgatás-próba is ez (`lanc.py:138`) | qwen35_9b 0,722; qwen35_4b 0,639 | `modulok/eval/ocr_kezi/` |
| `ocr_keplet` | képlet-kivágás → LaTeX | Képlet-OCR a vágólapról (`core/fuzet_api.py:145`, `app/src/szerkeszto/kepletOcr.ts`) | glm_ocr 0,949 | `ocr_keplet/` |
| `atirat` | hang → szöveg | Videólánc, szövegréteg, ha nincs felirat (`modulok/ytdlp/modell.py:66-68`) | nincs | `atirat/` |
| `szoveg` | összefoglaló, kártya, válasz | Kártyák ebből (`modulok/kartya/lanc.py:23`); Összefoglalás (`modulok/osszefoglalas/futtat.py:44`); „Kérdezz a vaulttól” (`core/kereses_modell.py:12`); Dolgozat szöveges értékelése (`core/felkeszultseg/api.py:60-81`) | gemma4_12b 0,632; qwen35_4b 0,433 | `szoveg/` |
| `kviz` | 5 kérdéses feleletválasztós darab | Kvíz ebből (`modulok/kviz/lanc.py:32`) | qwen35_9b 0,505 (csak távol-keretben) | `kviz/` |
| `matek` | levezetés + `VÉGEREDMÉNY:` | **éles hívót nem találtam** (a „Megoldás” a `matek_cas`-t használja) | qwen35_9b 0,925; qwen35_4b 0,775 | `matek/` |
| `matek_cas` | SymPy-kódot író megoldás | „Megoldás” parancs (`modulok/matek/lanc.py:15`), második vélemény `kizart_csalad`-dal | nincs | `matek_cas/` |
| `matek_ellenorzo` | levezetés-ítélet `ÍTÉLET:` | **éles modell-hívót nem találtam**: a levezetés-ellenőrzés (`core/matek_api.py`) CAS-alapú, modell nélkül fut | ministral3_8b_reasoning 0,900 | `matek_ellenorzo/` |
| `beagyazas` | vektor | Vektorindex (`core/vektorindex_feladat.py:39`, `core/index/hibrid/frissites.py`), hibrid keresés, hasonló jegyzetek | bge_m3 0,86 | `beagyazas/` (+ `kereses/`) |
| `rerank` | újrarangsorolás | Hibrid keresés, „Jelentés szerint” (`core/kereses_api.py:88-91`) | bge_reranker_v2_m3 0,923 | `rerank/` |
| `osztalyozas` | szabad szöveges kérés osztályozása | **nincs hívó és nincs aranyhalmaz** (a router zárva hibázik) | nincs | — |
| `fuzet_fejezet` | fotó → tantárgy/fejezet (zárt lista) | Füzetlánc, 1. lépés (`modulok/fuzet/lanc.py:150-151`) | nincs (a lánc a legacy-mérce alatt) | `fuzet_fejezet/` (+ `fuzet_forgatas/`, ami nem router-feladat) |
| `fuzet_valaszto` | jegyzetválasztás a jelöltek közül | Füzetlánc, 3. lépés (`lanc.py:185`) | nincs | `fuzet_valaszto/` |
| `kod` | C++ hibamagyarázat, tipp, teszt | C++ „Mi a hiba?” (`core/cpp_ai.py:37`, `modulok/cpp/ai_futas.py:32`) | qwen35_9b 0,709 | `kod/` |
| `grafikon` | képlet → függvényjellemzők JSON-ban | A grafikon-beírás modell-ága a bizonytalan képletekre (`modulok/grafikon/modell_hivo.py:19`); élesen csak `modell_ag = true` mellett ír (`os.toml:909`, ma `false`) | ministral3_8b 0,987; qwen35_4b 0,787 | `grafikon/` |
| `tema` | videó → tankönyvi téma | Videólánc, médiatársítás (`modulok/ytdlp/itelet.py:20-23`) | nincs | `tema/` |
| `kotes` | magyarázza-e a videó a jegyzetet | Videólánc, kötési javaslat (`itelet.py:26`) | nincs | `kotes/` |
| `kiegeszites` | szövegfolytatás | Asszisztens folytatás (`core/kiegeszites_modell.py:22`) | nincs (0,50, jel nélkül) | `kiegeszites/` |
| `kifejtes` | kijelölés kifejtése | Asszisztens ⌘J | qwen35_4b 0,917 | `kifejtes/` |
| `osszefoglal_kijeloles` | kijelölés 1–2 mondatban | Asszisztens ⇧⌘J | qwen3_vl_4b 0,894 | `osszefoglal_kijeloles/` |

Megjegyzések:
- A `kifejtes`, `osszefoglal_kijeloles` és `kiegeszites` csak `[asszisztens.kiegeszites] modell = true` mellett fut
  (`os.toml:955`, ma `false`): a kalibráció egyedül nem kapcsolja be.
- A `docs/MERES-2026-10-07.md` összefoglalója szerint az `atirat`-nak „nincs hang-háttere”. Ez **elavult**: a
  `core/modell/hatter.py:307` ma már ismeri az `mlx-whisper` hátteret.
- A gépi írás a `[router] feladatok` listán kívüli feladatnevet elutasítja (`core/gepi_iras.py:487-495`). Új funkció tehát
  csak új router-feladattal jöhet.

### 1.2 Hogyan lesz egy modell „kalibrált”

**Séma** (`core/modell/kalibracio.py:20-56`, `user_version = 3`):
- `kalibracio(feladat, modell, pontszam, datum, aranyhalmaz_verzio, kalibralt, megjegyzes, ervenyes, snapshot)`,
  ahol a PK a `(feladat, modell)` pár: a legutóbbi **érvényes** állás.
- `kalibracio_naplo`: hozzáfűzős napló, az érvénytelen mérés is ide kerül.
- `hoalap(modell, tps_alap, mintak, frissitve)`: a hőfigyelés alapszintje.
- WAL módban fut; a migráció előtt állapotmásolat készül (`kalibracio.py:69-76`).

**A jel feltételei** (minden feltételnek egyszerre teljesülnie kell):

| # | Feltétel | Hol érvényesül |
|---|---|---|
| 1 | **teljes halmaz**: `--limit`, `--tetel` és `--beallit` nélkül | `eval.py:239-240`, `eval.py:276-278`, CLI `eval.py:336-338` |
| 2 | **érvényes mérés**: (levágott ∪ hurok ∪ üres ∪ hiba)/n ≤ `[meres] ervenyes_kuszob` (0,10), és nincs hiányzó tétel | `ervenyesseg.py:79-115`, `eval.py:226-228`, `kalibracio.py:121-122` |
| 3 | **jóváhagyott aranyverzió**: a `VERZIO` nem végződik `-vazlat`-ra (`modulok/eval/kozos/arany.py:18-20`) | `kalibracio.py:123-125`, `eval.py:279-280` |
| 4 | **aktuális aranyverzió**: a sor `aranyhalmaz_verzio`-ja egyezik a `feladat.py` mai `VERZIO`-jával | `halmaz.py:26-64`, `kalibracio.py:158-172`, `router.py:59-62` |
| 5 | **kifejezett döntés**: `--rogzit --kalibralt`. A jelet ember adja; `None` esetén a meglévő jel megmarad, `--kalibralt-le` leveszi | `kalibracio.py:111-149`, `eval.py:322-325` |
| 6 | **használati küszöb** (`ocr_keplet` 0,90; `ocr_kezi` 0,60; `szoveg`/`kviz` 0,40; `matek`/`grafikon` 0,75; `matek_ellenorzo` 0,80; `beagyazas`/`rerank` 0,80; füzet: a legacy 87/97) | **csak dokumentum**: `docs/MERES-2026-10-07.md:143-160`. A kódban nincs ilyen ellenőrzés. |

A `snapshot` mező a mért HF-commit (`revizio.mert_pillanatkep`, `eval.py:254`). **A router ezt nem szűri**: csak a doctor
jelzi, ha egy kalibrált sor pillanatképe eltér a rögzített revíziótól (`revizio.py:63-72`). Egy MM-beli „modellfrissítés”
ezért nem vonja vissza magától a kalibrációt.

**Két jel feladatonként** (a koordinátor döntése, `MERES:160-163`): egy a legjobb érvényes sornak, egy a legjobb
munka-keretes (≤ 5 GB) sornak.

### 1.3 A keret és az aktivitás szerinti választás

| Fogalom | Érték / szabály | Hol |
|---|---|---|
| `[keret] munka` | 5,0 GB, az alapértelmezés (a felhasználó dolgozik a gépen) | `os.toml:414-416`, `beallitas.py:20` |
| `[keret] tavol` | 9,0 GB, csak `tavol` aktivitásnál (≥ 15 perc tétlenség) vagy a CLI saját workerén (`MANIFOLD_MODELL_KERET_GB`) | `os.toml:416`, `utemezo.py:161-168` |
| Aktivitás | `aktiv` < 120 s, `tetlen`, `tavol` ≥ 15 perc. Forrásai: a felület jele (`{run}/aktivitas` mtime) és a macOS `HIDIdleTime`; a frissebb számít | `aktivitas.py:25-33, 82-91`, `os.toml:420-424` |
| A kérés keretje | csak **szűkíthet**, nem tágíthat (M3) | `utemezo.py:161-168` |
| Router | a legjobb kalibráltat választja, ha belefér. Ha csak a távol-keretbe fér: a `[router.feladat.<f>].tavolra_var` dönt (vár, vagy a gyengébb fut). Ha semmi sem fér: `RoutingHiba` | `router.py:53-87`; `tavolra_var = true` csak az `ocr_kezi`-nél (`os.toml:446-447`) |
| Interaktív kérés távolra váró döntéssel | `RoutingHiba`: „most csak tartós tétlenségben …” | `utemezo.py:181-183` |
| Automatikus (`auto`) kérés | aktív használat alatt nem indul; vár a távol-keretre | `utemezo.py:194-195`, `kapu.py:37-50` |
| Visszatérés a géphez | a távol-keretes modell a folyó tétel után kiürül | `utemezo.py:212-227` |

---

## 2. A mérés folyamata

### 2.1 A lépések (`core/modell/eval.py`, a `modulok/eval/parancslista.py` szerint)

| Lépés | Parancs (ma) | Mit csinál | Ír | Igényli a fejlesztő vaultját? |
|---|---|---|---|---|
| 0. Aranyhalmaz-készítés | `modulok/eval/<f>/keszit.py`, `kijeloles_keszit.py`, `ocr_kezi/epit_katalogus.py` | a vaultból fagyaszt (szöveg, sha256, katalógus) | `modulok/eval/<f>/*.json` | **igen** (a `kod`, `kiegeszites` és a `matek*` kivételével) |
| 1. Előpróba (K32) | `mos eval <m> <f> --limit 3 --kimenet {tmp}/eval-proba`, majd `osszesito.py` | 3 tétel, érvényesség, levágás; zöld kapu után jöhet az éles kör | `{tmp}/eval-proba/…` | **igen**: a `tetelek(cfg)` olvassa a vaultot (pl. `ocr_kezi/feladat.py:80-84`, `ocr_keplet:33`, `atirat:65-68`) vagy a fagyasztott másolatot |
| 2. Éles mérés (K28) | `mos eval <m> <f>` (alapból `auto` mód) | minden tétel; folytatható a tétel-id és a kérés-ujjlenyomat alapján (`eval.py:185-214`) | `{runs}/eval/<m>/<f>.jsonl` | igen (mint fent) |
| 3. Jóváhagyás (K27) | **kézi lépés**: az `arany.json` `allapot`-ja `vazlat` → `jovahagyott` (az `attekinto.py` HTML-áttekintőjével) | a `VERZIO`-ról lekerül a `-vazlat` | `arany.json` | **igen**: a fejlesztő maga nézi át a saját jegyzeteit |
| 4. Újrapontozás | `mos eval <m> <f> --csak-ertekel --rogzit` | worker és generálás nélkül pontoz, a tétel **aktuális** `vart`-jával (`eval.py:217-257`) | `router.sqlite` (a sor, jel nélkül) | csak a `pontoz`-hoz kell (a `vart` és a fagyasztott forrás) |
| 5. Kalibrált jel | `… --csak-ertekel --rogzit --kalibralt` | a jel (az 1.2 feltételeivel) | `router.sqlite` | nem |

**Ami a termékbe nem szállítható:** a 0. és a 3. lépés minden olyan feladatnál, amelynek aranya a fejlesztő vaultjára épül,
illetve a 1–2. lépés is, amikor a `tetelek(cfg)` futásidőben a `{vault}`-ból olvas. A docstringek szerint:

| Feladat | Az arany forrása | Szállítható? |
|---|---|---|
| `ocr_kezi`, `ocr_keplet`, `fuzet_fejezet`, `fuzet_forgatas`, `fuzet_valaszto` | 97, illetve 20 füzetfotó a vaultból (`cfg.path("vault") / ARANY["fotomappa"]`), a vault jegyzetkatalógusa | **nem** (személyes kézírás és jegyzetek) |
| `szoveg`, `kviz` | 20 jegyzet fagyasztott másolata (`szoveg/forrasok/jNN.md`) | **nem** (a fejlesztő jegyzetei; a forrásmappa a repóban van, de tartalmilag személyes) |
| `kifejtes`, `osszefoglal_kijeloles` | 12 kijelölés a fejlesztő jegyzeteiből (`kijeloles_keszit.py`) | **nem** |
| `beagyazas`, `rerank` | 50 kérdés–jegyzet pár, ~300 vault-jegyzetből álló korpusz | **nem** |
| `atirat` | a vault `— Átirat.md` jegyzete (a kiadó szövege) és a videó | **nem** (személyes és szerzői jogi kérdés) |
| `tema`, `kotes` | 118 staging-videó átirata, 141 felirat–jegyzet pár | **nem** |
| `grafikon` | 15 képlet jegyzetrészletből | részben (ha a részlet saját írás) |
| `matek`, `matek_cas`, `matek_ellenorzo` | 40 emelt szintű feladat; 10+10 levezetés beültetett hibával | **valószínűleg igen** (a feladatszövegek licencét ellenőrizni kell) |
| `kod` | 12 saját C++ feladat, homokozóban igazolva | **igen** |
| `kiegeszites` | 12 saját készítésű iskolai mondatkörnyezet | **igen** |
| `osztalyozas` | nincs | — |

### 2.2 Mi kell egy szállítható, anonim aranyhalmazhoz

**Fájlszerkezet** (a mai szerződés megtartásával, `eval.py:6-11`):

```
modulok/eval/<feladat>/
  feladat.py        VERZIO, ROUTER_FELADAT, tetelek(cfg), pontoz(rekordok), formatum_ok(valasz, vart)
  arany.json        {"verzio", "allapot": "jovahagyott", "nyelv": "hu", "licenc", "szallithato": true, "tetelek": [...]}
  forrasok/         licenctiszta szövegek (pl. saját írású vagy CC-BY tananyag), .md
  kepek/            szintetikus vagy önkéntesen adott, anonimizált kézírás-fotók (EXIF nélkül)
  hang/             licenctiszta hangminták (rövid, 16 kHz)
```

Kötelező elvek: a `tetelek(cfg)` **ne olvasson `{vault}`-ot** (csak a mappa saját fájljait); a `vart` a tételben álljon; a
`VERZIO` tartalmazza a nyelvet és a forrás típusát (pl. `szoveg-hu-szall-v1`). Utóbbira azért van szükség, mert ma
router-feladatonként **csak egy** aktuális verzió lehet (`halmaz.py:56-59`). Ha két mappának ugyanaz a `ROUTER_FELADAT`-ja, a
rendezésben későbbi felülírja a korábbit.

| Feladat | Javasolt méret | A tétel formája (`keres` / `vart`) | Pontozó (meglévő újrahasznosítható) |
|---|---|---|---|
| `ocr_kezi` | 40–60 kép | képek + az átirat promptja / kézi teljes átirat (vagy kulcsszavak) | ma kötési BM25-bíró a vault-katalógusra (`ocr_kezi/feladat.py:113`). Szállítható változatban **CER/WER kézi átiraton** (`kozos/tavolsag.py`), a BM25 egy szállított mini-katalógusra |
| `ocr_keplet` | 30 kivágás | kép / LaTeX | `ocr_keplet/feladat.py:73` (normalizáló, `kozos/latex.py`), változatlanul |
| `szoveg` | 15–20 forrás × (összefoglaló + kártya) | forrás.md / kulcsrészek, kártyázható tények | `szoveg/feladat.py:111-183` + `modulok/kapuk`, változatlanul |
| `kviz` | 15–20 darab | forrásdarab / arany tények | `kviz/feladat.py:140-170` |
| `kifejtes`, `osszefoglal_kijeloles` | 12–20 kijelölés | kijelölés + előtte / kulcstények, témaszavak, tiltott állítás | `kozos/kijeloles.py` |
| `beagyazas`, `rerank` | 50 kérdés, 200–300 dokumentumos szállított korpusz | kérdés / céldokumentum | `beagyazas/feladat.py:45`, `rerank/feladat.py:65` (recall@5, MRR) |
| `atirat` | 10–15 perc licenctiszta hang | hang / referencia-átirat | `atirat/feladat.py` (WER, CER) |
| `tema`, `kotes` | 40–60, illetve 60–100 pár | szállított átirat-részlet + témalista / címke | `tema/feladat.py:67`, `kotes/feladat.py:42` |
| `fuzet_fejezet`, `fuzet_valaszto` | a szállított mini-katalógusra 40 fotó | fotó + zárt lista / fejezet, jegyzet | meglévő bírók, a katalógus a mappában |
| `matek*`, `kod`, `kiegeszites`, `grafikon` | a mai halmazok | változatlan | változatlan |

A **minimális tételszámot** a kódnak kell kikényszerítenie (pl. `[kalibracio] min_tetel = 20`), különben egy felhasználói
mini-halmaz bármit átenged.

### 2.3 Aranyhalmaz a felhasználó saját vaultjából (helyben, opcionálisan)

A **`modulok/eval/kijeloles_keszit.py`** jó minta: kézzel választott `{ut, kezd, veg}` tételekből fagyaszt (`kivag`,
`fagyaszt_tetel`), sha256-tal, `--ellenoriz` móddal, és tartalmi változásnál `vazlat`-ra áll vissza. A vaultot csak olvassa.
Termékesítve:

1. **SU-varázsló, „Saját mérőhalmaz”**: a felhasználó a szerkesztőben kijelöl (a `kifejtes`/`osszefoglal_kijeloles`-hez), vagy
   jegyzeteket jelöl meg (`szoveg`/`kviz`-forrás); a `vart` mezőket (kulcstények, kártyázható tények) a felület kéri be.
2. **A fagyasztás helye** `{var}/eval-sajat/<feladat>/`, **nem a `modulok/`**. A `halmaz.Verziok` ma csak a `modulok/eval`-t
   nézi (`halmaz.py:29-30`), ezért második forrásra és egy választásra van szükség („szállított” vagy „saját”).
3. **A jóváhagyás felületi lépés**: tételenként „rendben / kiveszem”, ez állítja `jovahagyott`-ra.
4. **Saját halmaznál a kalibrált jel csak helyben él**, és a router-sor `aranyhalmaz_verzio`-ja ezt jelzi.
5. A fotós feladatokhoz a felhasználó a saját bekötött füzetfotóit adhatja; a meglévő `{fuzet}/allapot.json` kötései adják a
   `helyes` címkét. (Ez a lehetőség a `fuzet_valaszto` bírójából látszik; nem ellenőriztem, hogy minden mező megvan-e.)

---

## 3. A modell-regiszter

### 3.1 `config/letoltes.toml` (31 modell; fejléc: `letoltes.toml:7-22`)

| Mező | Jelentés | Megjegyzés MM-szempontból |
|---|---|---|
| `repo` | HF-repó | ✓ |
| `revizio` | 40 jegyű commit-sha (C19, T141) | ✓ rögzített |
| `feladat` | feladatlista | **eltér** az `os.toml`-tól (pl. qwen35_9b: `letoltes.toml:28` 3 feladat, `os.toml:508` 6 feladat). A tesztek csak a nevet, a repót, a `minta`-t és a `csucs_gb`-t vetik össze (`os.toml:494`) |
| `minta` | `allow_patterns` | ✓ |
| `meret_gb` | a HF API szerinti méret (2026-09-30), statikus | a lemezen mért méret hiányzik |
| `csucs_gb`, `csucs_mert` | csúcs-RAM (mért vagy becsült) | ✓ |
| `keret` | munka vagy távol | származtatható adat, duplikált |
| `futtato` | háttér | ✓ |
| `konvertalas` | nem MLX-formátum | nincs konvertáló (lásd lent) |
| `licenc` | a modellkártya szerint | ✓ jó az MM-nek |
| `kor` | `elso` vagy `opcionalis` | csoport-letöltéshez |
| `megvan` | **kézzel írt** „már letöltve” jelző | **nem lemezellenőrzés** (`letoltes.py:65`) |

### 3.2 `core/letoltes.py`

- A forrás a HF `snapshot_download(repo_id, allow_patterns, cache_dir={models}/hub, max_workers=16, token, revision=revizio)`
  (`letoltes.py:79-108`).
- A letöltés után ellenőrzi, hogy a pillanatkép mappaneve egyezik-e a rögzített revízióval (`letoltes.py:93-94`), és jelzi, ha a
  `refs/main` eltér (`:95-98`). **Fájlszintű sha-ellenőrzés nincs** a HF saját etag/blob-nevein túl.
- Szabad lemezhelyet ellenőriz (×1,05) (`:146-151`), majd interaktív „Letöltöd? [i/N]” kérdést tesz fel (`:153-157`). A HF-token
  csak a memóriában él (`:159-164`).
- Megszakítás: csak `KeyboardInterrupt`; újraindítás után folytat (`:100-103`, `:171-173`). Haladásjelzés: csak `[i/n]`
  nyomtatás és a HF tqdm-je. **Nincs `[manifold-progress]`**, pedig az eval kiírja (`eval.py:213`).
- A napló helye `{runs}/letoltes-<idő>.json` (`:111-117`).
- `bin/mos models pull` és `letoltes`: csak itt `HF_HUB_OFFLINE=0` (`bin/mos:206-211`); a worker offline
  (`worker.py:358`, `hatter.py:323-331`, `local_files_only`).

**`var/models` (ls szinten):** `hub/` (31 `models--…` mappa, a regiszterrel egyezik), `modules/`, `xet/`; összesen kb. 87 GB.
A HF_HOME-szerkezet: `{models}/hub/models--<org>--<név>/{refs/main, snapshots/<sha>/}` (`revizio.py:16-17`).

**`mos models list`** (`core/modell/__main__.py:26-50`): név, futtató, csúcs, keret, „helyben”, kalibrációs jelek. A „helyben”
értéke annyi, hogy van-e **bármilyen** `snapshots/*` (`__main__.py:11-12`): nem a rögzített revíziót nézi, és nem azt, hogy
teljes-e a letöltés.

**Konvertálás:** `konvertalas = true` esetén a betöltő `BetoltesHiba`-t dob (`hatter.py:312-315`), konvertáló kód viszont
**nincs** a modellrétegben (az egyetlen `konvertalas.py` a videóé). Érintett: `whisper_large_v3_hu`, `whisper_hu_turbo`.

### 3.3 `[modellek.*]` az `os.toml`-ban (`:497-850`; betöltés: `beallitas.py:135-156`)

Mezők: `repo`, `revizio`, `futtato`, `kepessegek` (szoveg | kep | hang | beagyazas | rerank), `csalad` (szöveges modellnél
kötelező; a második vélemény ebből zár ki, `router.py:69-73`), `feladat`, `csucs_gb`/`csucs_mert`, `gondolkodas` (a sablon
gondolkodását kapcsolja ki), `gondolkodo` (mindig gondolkodik), `gondolkodas_token`, `minta`, `konvertalas`,
`meres.<feladat>` (a mérés kérés-beállítása, `MERES_KULCSOK`, `beallitas.py:26-27`), `meres_kihagy` (szöveg vagy feladat →
indok tábla). A mérés-beállításokat a mérés és az éles hívás is használja (`eval.keres_beallitas`, `eval.py:83-103`), ez a
„mért = éles” elv kulcsa.

### 3.4 Mi hiányzik egy Model Managerhez

| Képesség | Ma | Kell |
|---|---|---|
| Egy forrás | két fájl, eltérő `feladat`-listával | egyetlen regiszter-manifeszt (aláírva, a termékkel szállítva), plusz felhasználói felülírás-réteg (`{var}/modellek.toml`) |
| Telepítettség | `snapshots/*` glob, kézi `megvan` | a rögzített revízió megléte + teljes fájllista (`allow_patterns` ∩ repó-fa) + **blob-sha256** (az LFS-blob neve maga a sha256) ellenőrzése; az állapot: `nincs` / `részleges` / `kész` / `eltérő revízió` / `konvertálásra vár` |
| Méret | `meret_gb` (HF API, statikus) | a lemezen mért méret (`du` a blobokon, a repók közt megosztott blobokat egyszer számolva) és a „felszabadítható” méret |
| Törlés | nincs | `models rm <név>`: a `snapshots/<sha>` és a csak ehhez tartozó blobok törlése, `refs` takarítás; **kalibráció visszavonása** a `(*, modell)` sorokon (napló-bejegyzéssel); megerősítés |
| Haladásjelzés, megszakítás | tqdm, Ctrl-C | strukturált (bájt/s, fájl, ETA) esemény a core-nak (WS), megszakítható feladatsor-feladat; a `letolt` ma `snapshot_download`-ot hív, ehhez `hf_hub_download` fájlonkénti hurok vagy tqdm-hook kell |
| Ellenőrzés | `doctor` + `revizio.ellenoriz` (`revizio.py:40-60`) | „Ellenőrzés” gomb: revízió, blob-sha, futtató a lockban, betölthetőség (próbabetöltés a betöltőn át, a kereten belül) |
| Konvertálás | nincs | egyszeri helyi lépés (pl. `mlx_whisper` konverzió) a betöltő zárja alatt, vagy a szállított regiszterben csak MLX-formátumú repó szerepeljen |
| Feladat-leírás | a feladatnevek magyar azonosítók (`ocr_kezi`, …) | `[feladat.<f>] cim.hu/en, leiras.hu/en, ikon` |
| „Ehhez a funkcióhoz kell” | kódbeli konstansok (`FELADAT = "szoveg"` négy helyen) | **funkció → router-feladat → modell** tábla adatként (`[funkcio.fuzetfoto] feladatok = ["ocr_kezi", "fuzet_fejezet", "fuzet_valaszto"]`); az MM ebből mondja ki: „A kézírás-OCR-hez kell (Füzetfotó-bekötés). Ajánlott: Qwen3.5-4B (4,1 GB RAM, 3,0 GB lemez)” |
| Nyelv | nincs | `nyelvek = ["hu"]` a whisper-hu finomhangolásokon; a router kulcsában is (7. fejezet) |
| Ajánlás | `kor = elso/opcionalis` | gépi RAM szerinti profil (8/16/24 GB → munka/távol keret), feladatonként egy ajánlott és egy alternatív modell |
| Frissítés | új `revizio` a TOML-ban | „frissítés elérhető” → új revízió letöltése → **újramérés szükséges** (a router ma nem szűri a snapshot-eltérést) |

---

## 4. A betöltő és a worker

### 4.1 Működés

| Elem | Lényeg | Hol |
|---|---|---|
| Worker | külön folyamat (`python -m core.modell.worker`), csak `127.0.0.1`; az első stdout-sor a `{port, pid}`; a stdin bezárásakor kilép | `worker.py:1-26, 355-407` |
| Egy worker telepítésenként | `{run}/worker.lock` (flock); a cím a `{run}/worker.pid`-ben (`"<pid> <port> <titok>"`, 0600) | `worker.py:361-366`, `343-352` |
| Worker-titok | munkamenetenként sorsolt, `X-Manifold` fejlécben jön, a `Host` is ellenőrzött | `worker.py:244-251`, `kliens.py:42-52, 271-274` |
| Végpontok | `/v1/chat/completions`, `/v1/chat/stream` (NDJSON, 1 s-os életjel, a kliens bontása elveti a kérést), `/v1/embeddings`, `/v1/rerank`, `/v1/audio/transcriptions`, `/v1/megszakit` (`F-…` azonosító), `/v1/automatikus`, `/unload`, `/router`, `/router/valaszt`, `/health` | `worker.py:298-328` |
| D9 a workerben | kifejezett modell csak `proba: true`-val, és a válasz is hordozza a `proba` jelet; különben a router dönt | `worker.py:116-123` |
| Hibakódok | `RoutingHiba` → **409** `nincs_kalibralt` (+ `nincs_masik_csalad`); keret/leállás/időtúllépés → 503; megszakítás → 409 `megszakitva` | `worker.py:253-268`, `165-174` |
| Ütemező | egy végrehajtó szál; az interaktív kérés előbb jön, a betöltött modell kérései előbb jönnek; az auto kérés aktív használat vagy hűtés alatt nem indul | `utemezo.py:189-210` |
| Betöltő, 4 szabály | (1) közös zár, egy modell; (2) keret: ha a `csucs_gb` nagyobb a keretnél, el sem indul; (3) `cache_gb = 0,25`, darabolt prefill; (4) memóriaőr: `kern.memorystatus_level` < 20% esetén kiürít, és 30 s-ig vár az „elég” állapotra; GPU-memóriahibánál 3 próba | `betolto.py:8-16, 80-118, 231-255` |
| `egyutt_maradhat` | pontosan az egyik modell beágyazó, mindkét csúcs ismert, és az összegük belefér a keretbe | `betolto.py:122-132` |
| Zár | `{state}/modell.lock` (`MANIFOLD_MODELL_ZAR` felülírja), `fcntl.flock`, 0644; a második igénylő vár | `zar.py:1-72`, `os.toml:408` |
| Memória | `sysctl kern.memorystatus_level`, `hw.memsize` | `memoria.py:16-24` |
| Tétlenségi ürítés | 10 perc után | `utemezo.py:216-219` |

### 4.2 Mi törne el több felhasználónál vagy több workspace-nél ugyanazon a gépen

| Eset | Mi történik | Hivatkozás |
|---|---|---|
| **Két külön telepítés** (két fiók, vagy egy fiók két workspace-másolattal) | Mindkettőnek saját `{state}/modell.lock`-ja van. A „gépszintű” zár (a docstring szerint, `zar.py:1`) **valójában telepítésenkénti**: két worker két modellt tölthet be egyszerre, mindegyik a saját 5/9 GB-os keretével (16 GB-on 2 × 9 GB). Csak a rendszerszintű memóriaőr (`memorystatus_level`) fékez, utólag. | `os.toml:408`, `beallitas.py:149`, `betolto.py:93-105` |
| **Közös telepítés két fiókkal** | A `worker.lock` és a `modell.lock` 0644 joggal, az első fiók tulajdonában jön létre; a második fiók `os.open(O_RDWR)` hívása `PermissionError`-t kap: **hibával áll meg**, nem vár. A 0600-as pidfájlt a második fiók nem olvashatja, ezért a `fut_url` `None`-t ad, és új workert próbál indítani. | `zar.py:41`, `worker.py:361`, `kliens.py:55-65` |
| Közös `router.sqlite`, `feladatok.sqlite` | WAL esetén mindkét fióknak írási jog kell a fájlra, a `-wal` és a `-shm` fájlra is. Fiókok között ez nincs megoldva. | `kalibracio.py:85-88` |
| Aktivitás | A `HIDIdleTime` a gépé, nem a fiókhoz kötött: a másik fiók (gyors felhasználóváltás) gépelése is „aktív” jelnek számít. A felületi jel telepítésenkénti fájl. | `aktivitas.py:25-33` |
| Két workspace egy fiókban, közös `{os}`, különböző vault (`MOS_VAULT`) | Egy `{run}` van, így egy worker fut; a második core átveszi az elsőét (`Folyamat.biztosit`). A worker viszont **az első core `MOS_ROOT`/config-környezetéből** indult (router.sqlite, `modulok/eval`, keret), és vele áll le (D4): ha az első core kilép, a második core worker-hívásai megszakadnak. | `kliens.py:256-297` |
| Keret | Minden worker abból indul ki, hogy az 5/9 GB csak az övé. Nincs gépszintű „költségvetés”. | `utemezo.py:161-168` |

### 4.3 A modell-tárhely megosztása

- **Ma is lehetséges** az `[utak] models` kulcs (`os.toml:17`) felülírásával: `MOS_MODELS=…`, illetve a `bin/mos:35`
  `HF_HOME=${HF_HOME:-…}`. A futás offline és csak olvas (`local_files_only`, `hatter.py:323-331`), ezért ugyanazt a HF-cache-t
  több workspace is olvashatja.
- **Egy fiók, több workspace:** `~/Library/Application Support/Manifold/models` (HF_HOME) megfelelő. Letöltést egyszerre csak egy
  folyamat végezzen (a HF `.locks` mappája ezt kezeli), és a törlés legyen tudatában, hogy több workspace hivatkozik a modellre
  (referenciaszámlálás vagy „használja: X, Y”).
- **Több fiók:** a `~/Library` fiókonkénti, ezért erre a `/Users/Shared/Manifold/models` (csoport-írás, `umask 002`) vagy egy
  `/Library/Application Support/Manifold` alatti, rendszergazdai telepítésű tár alkalmas.
- **Ezzel együtt áthelyezendő:** a modellzár egy gépszintű helyre (pl. `/Users/Shared/Manifold/run/modell.lock`, 0666, vagy
  `flock` egy közös csoport-írható fájlon). Így valóban egy modell lesz a gépen. A worker maradhat telepítésenkénti.
  Alternatíva egy gépszintű „modellgazda”-démon, ez azonban kérésenként hordozná a hívó router-tábláját és arany-verzióit
  (multi-tenant), ami nagyobb átalakítás.
- **A kalibráció megosztható** ugyanazon a gépen, ha szállított aranyhalmazon készült: a `(feladat, modell, arany-verzió,
  snapshot)` gépfüggetlen, csak a sebesség- és a `hoalap`-adat gépfüggő. Saját aranyhalmazon mért sort viszont ne osszunk meg.

---

## 5. Graceful degradation ma

Alapállapot: a core **worker nélkül indul** (`core/server.py:144-152`, lusta `Folyamat`), az ML-könyvtárak lustán töltődnek
(`hatter.py:1-7`). A `config/requirements.lock` viszont ma kötelezően tartalmazza a `torch`, `mlx*`, `sentence-transformers`
és `huggingface-hub` csomagot (`requirements.lock:370, 586-660, 1433, 1619`). Egy AI nélküli termékcsomaghoz ezeket külön,
opcionális komponensbe kell tenni.

| Funkció | Router-feladat(ok) | Kalibrált modell nélkül ma | A felhasználónak ma eljutó üzenet | Javasolt termék-üzenet |
|---|---|---|---|---|
| Hibrid keresés, „Jelentés szerint” | `beagyazas`, `rerank` | **lexikai visszalépés**; betöltés alatt `ok: "modell_betoltes_alatt"`, utána ismétel (`kereses_api.py:17-21, 79-91`) | nincs hiba, lexikai találatok | „Jelentés szerinti keresés: helyi AI-modell kell. [Telepítés] — most szó szerinti találatokat látsz.” |
| ⌘⇧F keresés | — | lexikai, modell nélkül | — | — |
| „Kérdezz a vaulttól” | `szoveg` (+ `beagyazas`) | 503; a források megjelennek (`kereses_api.py:261-263`) | „A válaszhoz nincs kalibrált nyelvi modell (a források alább).” (`app/src/lib/kereses/kerdezz.svelte.ts:58`) | „A válaszhoz helyi AI-modell kell. [Telepítés] [Tesztelés] — a források alább.” |
| Kártyák ebből | `szoveg` | a feladat megáll (`Megall`) | „A `szoveg` feladatra nincs kalibrált modell (D9): élesen nem készül kártya. Próbához adj meg …” (`modulok/kartya/lanc.py:149-150`) | „Ez a funkció helyi AI-modellt igényel (Szövegértés). [Telepítés] [Folytatás AI nélkül: kártya kézzel]” |
| Összefoglalás | `szoveg` | `Megall` (`modulok/osszefoglalas/futtat.py:116-117`) | ugyanilyen technikai szöveg; a külső AI-blokk kézi beillesztése megmarad (`core/osszefoglalas_api.py:11`) | „… [Telepítés] [Másolás külső AI-hoz]” |
| Kvíz ebből | `kviz` | `Megall` (`modulok/kviz/lanc.py:137-138`); munka-keretben ma **csak távol-keretes** kalibrált modell van, így a kvíz tétlenségre vár | „A `kviz` feladatra nincs kalibrált modell (D9) …” | „A kvízkészítő modell csak akkor fut, ha nem használod a gépet (≥ 15 perc). [Ütemezés] [Kisebb modell tesztelése]” |
| Füzetfotó-bekötés | `fuzet_fejezet`, `ocr_kezi`, `fuzet_valaszto` | **hibás visszalépés**: a `/router/valaszt` 409-e `KliensHiba` lesz, amit a `Modellek.modell_nev` nem alakít `NincsModell`-lé (`modulok/fuzet/modell.py:46-51`). A lánc így **fotónként** „hiba” állapotot ad (`lanc.py:312-319, 377-381`), nem áll meg tisztán. Ma a `fuzet_fejezet`/`fuzet_valaszto` kalibrálatlan, így ez az **alapeset** (kivéve „beszúrás az aktív jegyzetbe”) | „olvas: KliensHiba: a(z) fuzet_fejezet feladatra nincs kalibrált modell — … (mos eval --rogzit --kalibralt)” fotónként | „A füzetfotók automatikus besorolásához helyi AI-modell kell. [Telepítés] [Folytatás AI nélkül: fotó csatolása kézzel a jegyzethez]”. **Javítás: a 409-et `NincsModell`-ként kezelni.** |
| Képlet-OCR (vágólap) | `ocr_keplet` | 400 (a 409 `<500`, ezért 400 lesz, `core/fuzet_api.py:147-149`) | „a képlet-olvasó modell nem válaszolt: a(z) ocr_keplet feladatra nincs kalibrált modell — … (mos eval --rogzit --kalibralt)” | „Képletfelismerés: helyi AI-modell kell (1,6–2,2 GB). [Telepítés]” |
| C++ „Mi a hiba?” | `kod` | 503 `kod = nincs_kalibralt` (`core/cpp_ai.py:91-101, 130`) | „A C++ AI-hoz még nincs kalibrált modell (a `kod` mérése után kapcsol be).” (`app/src/kod/aiElfogad.ts:18`) | „C++ magyarázat: helyi AI-modell kell. [Telepítés] [Tesztelés]” |
| Asszisztens ⌘J / ⇧⌘J / folytatás | `kifejtes`, `osszefoglal_kijeloles`, `kiegeszites` | ki van kapcsolva (`modell = false`); kalibrálatlan kijelölés-módnál a `kiegeszites` modellje próbaként fut; ha semmi sincs: csak helyi minták (`core/kiegeszites_modell.py:80-130`) | „Csak elfogadott helyi minták. A modell ki van kapcsolva.” / „Még nincs méréssel ellenőrzött kiegészítő modell. A helyi minták elérhetők.” | jó példa, csak a [Telepítés] gomb hiányzik |
| „Megoldás” (matek) | `matek_cas` | `Megall` (élesen nincs kalibrált modell); a második vélemény hiányát a callout kimondja (`modulok/matek/lanc.py:5-8`) | technikai „nincs kalibrált modell” | „Megoldáskereséshez helyi AI-modell kell. [Telepítés] — a levezetés-ellenőrzés (CAS) AI nélkül is működik.” |
| Levezetés-ellenőrzés | — | **modell nélkül**, CAS-homokozóban (`core/matek_api.py`) | — | — |
| Grafikon-beírás | `grafikon` (csak a modell-ág) | a determinisztikus CAS-ág fut, a modell-ág próba vagy kimarad (`modulok/grafikon/modell_hivo.py:6-12, 42-50`) | — | „A bizonytalan képletekhez AI-javaslat is kérhető. [Telepítés]” |
| Videólánc: téma, kötés | `tema`, `kotes` | **lexikai út**, nem vár (`modulok/ytdlp/modell.py:3-5, 36-51`) | — (jó) | „Pontosabb témaválasztás helyi AI-val. [Telepítés]” |
| Videólánc: átirat | `atirat` | felirat nélkül: `NincsModell`, a tétel kimarad (`modulok/ytdlp/integralas.py:392`) | „nincs kész staging-átirat, és az `atirat` feladatra nincs kalibrált modell (K29) …” | „Felirat nélküli videóhoz beszédfelismerő modell kell. [Telepítés] [Kihagyás]” |
| Dolgozat szöveges értékelése | `szoveg` | 503 (`core/felkeszultseg/api.py:80`) | „A szöveges értékelés modellje nincs kötve (a router-táblában nincs kalibrált `szoveg` modell).” | „Szöveges értékelés: helyi AI-modell kell. [Telepítés] — a pontszám AI nélkül is látszik.” |
| Vektorindex (háttér) | `beagyazas` | nem épül; a hibrid kereső lexikai marad | — | MM-ben: „A jelentés szerinti kereséshez index épül, ha telepíted a beágyazót.” |
| Bármelyik, ha a worker nem indul (nincs ML-runtime) | — | 503 „a modell-worker nem indult el: … (napló: …)” (`kliens.py:288-295`) | technikai | „A helyi AI-komponens nincs telepítve. [AI-komponens telepítése]” |

A közös minta: kell egy `kod`-alapú hibaszerződés (`nincs_kalibralt`, `nincs_telepitve`, `csak_tavol`, `nincs_ai_runtime`)
plusz a `feladat`. A felület ebből a §3.4 „funkció → feladat” táblája szerint generálja a szöveget és a gombokat. Ma a `kod` csak
a C++ útnál van meg (`modulok/cpp/ai_futas.py:9`).

---

## 6. A kalibráció mint felhasználói művelet

### 6.1 Minimális lépéssor egy „Modell tesztelése” gomb mögött

| # | Lépés | A mai építőelem | Megszakítható? |
|---|---|---|---|
| 0 | **Előfeltétel**: a modell telepítve (rögzített revízió), a futtató a `HATTEREK`-ben van, `konvertalas = false`, `csucs_gb` ≤ a gép távol-kerete | `hatter.py:307-320`, `revizio.van_pillanatkep` | — |
| 1 | **Előpróba**: 3 tétel, `--kimenet {tmp}/eval-proba`; érvénytelen esetén megáll („a modell levágja vagy hurkolja a választ”) | `eval.futtat(limit=3, kimenet=…)` + `eval.ertekel` | igen |
| 2 | **Éles mérés**: a teljes halmaz, `auto` mód (aktív használat alatt szünetel), feladatsor-feladatként (`resources={"modell"}`), `feladat_id`-vel | `eval.futtat`, `kliens.Folyamat` | **igen, veszteség nélkül**: a sorkulcs a tétel-id és a kérés-ujjlenyomat, a kész sorok megmaradnak (`eval.py:193`); a futó tétel `/v1/megszakit`-tal áll le |
| 3 | **Értékelés** | `eval.ertekel` → `<f>-ertekeles.json` (`pontszam`, `ervenyesseg`, `futas.csucs_gb_max`, `mp_atlag`, `snapshot`) | — |
| 4 | **Rögzítés és jel**: `rogzit(..., kalibralt=True)` **csak** ha teljes, érvényes, jóváhagyott arany, **és pontszám ≥ a feladat küszöbe (új kód)** | `eval.rogzit` (`eval.py:271-296`) | — |
| 5 | **Kimenet a felületen**: pontszám a küszöbhöz és a többi helyi modellhez képest, érvényesség (levágott/hurok/üres/hiba), átlagos idő/tétel, mért csúcs-RAM (eltérés esetén figyelmeztetés: `csucs_figyelmeztetes`, `eval.py:260-268`), és a router új döntése (munka/távol, `attekintes.attekintes`) | `/api/vezerlo/modellek` (`attekintes.py:30-64`) | — |

**Akadályok a mai kódban:**
- A kifejezett keretű mérés saját workert követel, és ha fut az app workere, elutasít (`kliens.py:261-263`, `eval.py:347-351`). Az
  appon belüli gomb ezért csak az app workerét használhatja. A > 5 GB-os modell interaktív módban `KeretHiba`-t kap
  (`utemezo.py:173-176`), `auto` módban pedig vár a ≥ 15 perces tétlenségre. **UX**: „Ez a modell 7,3 GB: a teszt akkor fut,
  amikor nem használod a gépet.”
- A regiszterbeli `csucs_gb` a keret-döntés alapja; ha a mért érték nagyobb, ma csak figyelmeztetés jön. A terméknek egy
  **helyi felülírás-tárba** kellene írnia (a `config/os.toml` szállított, nem a felhasználó fájlja).

### 6.2 Idő és memória (becslés a `parancslista.py` `TETELIDO` táblájából; ≤ 2,3 / ≤ 5 / > 5 GB modell, mp/tétel)

| Feladat | Tételszám (docstring) | Munka-keretes modell (≤ 5 GB) | Távol-keretes modell (> 5 GB) |
|---|---|---|---|
| `ocr_keplet` | 20 | ~1,5 perc | ~3 perc |
| `ocr_kezi` | 97 | ~40 perc | ~97 perc |
| `szoveg` | 40 (20 × 2) | ~20 perc | ~45 perc |
| `kviz` | 20 | ~8 perc | ~18 perc |
| `matek` / `matek_cas` | 40 | ~13–16 perc | ~30–33 perc |
| `matek_ellenorzo` | 20 | ~5 perc | ~9 perc (a gondolkodó modell lényegesen több) |
| `kod` | 60 | ~35 perc | ~70 perc (+ gondolkodás) |
| `kifejtes`, `osszefoglal_kijeloles`, `kiegeszites` | 12 | 2–5 perc | — |
| `beagyazas`, `rerank` | 50 (+ korpusz) | néhány perc | — |
| `tema` / `kotes` | 236 / 141 | ~30 / ~7 perc | ~60 / ~14 perc |

Memória: a modell `csucs_gb`-je (1,2–8,5 GB) plusz a memóriaőr tartaléka (≥ 20% szabad + 5% + a modell része,
`betolto.py:107-118`). A teszt alatt a többi AI-funkció vár (egy modell, egy zár).

### 6.3 A gyenge modell „kalibrálásának” kockázata

- **Ma a küszöb nem véd, mert a kódban nincs.** Az érvényességi kapu (`ervenyesseg.py`) csak a kimenet *alakját* nézi (levágás,
  hurok, üresség, hiba), a minőségét nem. A minőségi küszöb csak a dokumentációban él, és a jelet a fejlesztő adja kézzel. Ha az
  SU gombja `--kalibralt`-ot adna, egy 0,10-es kvízmodell is élesen futna.
- **Ami ma mégis véd:** (1) a teljes halmaz kötelező; (2) a jóváhagyott arany kötelező; (3) a router **a legjobb** kalibráltat
  választja, így egy gyengébb kalibrált sor csak akkor fut, ha a jobbik nem fér a keretbe; (4) a lexikai forráshűség-kapuk a
  `szoveg`/`kviz` kimenetén (a rossz állítás kiesik, `modulok/kapuk/huseg.py`), a CAS a `matek`/`grafikon` kimenetén; (5) a D9
  írás-kapu (`gepi_iras.py:497-516`).
- **Javaslat:**
  - `[kalibracio.<feladat>] kuszob, min_tetel, mero = "szallitott"|"sajat"` kódban kikényszerítve (`eval.rogzit`, `Tabla.rogzit`).
  - Saját aranyhalmazon a jel **jelölt** legyen („saját mérés”), a felület ezt mutassa.
  - A „második szint” (a munka-keretes jel) maradjon a küszöbhöz kötve.
  - A felület a pontszámot mindig a szállított referencia-sorok mellé tegye (pl. „qwen35_4b: 0,43 — küszöb 0,40”).

---

## 7. Nyelvfüggés

### 7.1 Magyar-specifikus elemek

| Réteg | Elem | Hol |
|---|---|---|
| Promptok | a kvíz, az összefoglaló, a kártya, a füzet (TANTÁRGY/CÍMEK/TARTALOM/FEJEZET), a videó téma/kötés („Egy magyar oktatóvideó …”), a matek, a C++ AI, a grafikon modell-ága, a Kérdezz, a dolgozat-értékelés, a bench | `modulok/kviz/promptok.py` (`PROMPT_VERZIO` `:6`), `modulok/osszefoglalas/promptok.py` (`:9`), `modulok/kartya/generalas.py:49`, `modulok/fuzet/modszer.py:37-45`, `modulok/ytdlp/itelet.py:20-27`, `modulok/matek/megoldas.py:25`, `modulok/cpp/ai.py`, `modulok/grafikon/modell_ag.py`, `core/index/hibrid/kerdezz.py`, `core/felkeszultseg/ertekeles.py`, `core/modell/bench.py:28-35` |
| Angol utasítás magyar kimenettel | „Fill a blank in a Hungarian Markdown note … in Hungarian” | `core/kiegeszites_modell.py:28-29` |
| Kimeneti jelölők (a pontozó és a lánc parszolja) | `VÉGEREDMÉNY:`, `ÍTÉLET: HELYES/HIBA`, `TANTÁRGY:`, `Magyarázat:`, `NEM TUDOM` | `eval/matek/feladat.py:24`, `eval/matek_ellenorzo/feladat.py:27`, `fuzet/modszer.py:85`, `kviz/formatum.py:70`, `kartya/generalas.py:49` |
| Nyelvkapuk | C++: magyar szólista és ékezetarány, `MAGYAR_KUSZOB = 0,30`; kijelölés: `_HU_BETU` + angol függvényszó-lista | `modulok/cpp/ai.py:192, 234`, `eval/kod/feladat.py:45, 128-144`, `eval/kozos/kijeloles.py:54-55, 95` |
| Forráshűség-kapu (`modulok/kapuk`) | magyar függvényszó-stoplista (`FUGGVENYSZOK`), magyar tagadószavak (`NEGATOROK`), 5 karakteres „tő” a toldalékoláshoz, magyar nagybetűs tulajdonnév-szabály, ékezethajtás (csak a magyar ékezetekre), kihagyott szakaszok („Füzet”, „Gyakorlás”, „Kitöltések”); a küszöbök a magyar `szoveg` halmazon mérve | `kapuk/tokenek.py:14-28, 36-48, 72-84`, `eval/kozos/tavolsag.py:7`, `kapuk/forras.py:26`, `os.toml:286-292` |
| Mondatra bontás | `.!?` + szóköz vagy sortörés, képlet-védelemmel; nyelvfüggetlen, de rövidítéseket nem kezel | `kapuk/forras.py:221-235`, `eval/kozos/kijeloles.py` `_MONDATHATAR` |
| Hang | `kliens.atir(nyelv="hu")` alapértelmezés; az eval `"nyelv": "hu"`; két magyar whisper-finomhangolás; `ALAP_NYELVEK = ("hu","en")` | `core/modell/kliens.py:187`, `eval/atirat/feladat.py:72`, `os.toml:603, 734`, `core/atirat.py:26` |
| Tárgytérkép | magyar tantárgynevek (`TARGY_TERKEP`) | `modulok/ytdlp/integralas.py:59` |
| Modellválasztás | a jelöltek magyar teljesítményre lettek mérve („kézírás-OCR magyarul”, „Átirat magyar hangból”, „… magyarul”) | `docs/MODELL-JELOLTEK.md` 1–3. fejezet |
| Router | a kulcs `(feladat, modell)`, **nyelv nélkül**: egy `atirat`-ra kalibrált magyar finomhangolás angol hangra is futna | `kalibracio.py:21-30`, `router.py:53` |

### 7.2 Mi kell egy angol (és általános) nyelvi profilhoz

1. **Nyelvi profil a configban** (`[nyelv] alap = "hu"`), plusz jegyzetenként vagy videónként felismert nyelv (a ytdlp lánc
   ezt már tudja: `itelet.norm_lang`).
2. **A router kulcsa kapjon nyelvet**: `szoveg@en`, vagy egy `nyelv` oszlop a `kalibracio`-ban (új migráció, `VERZIO = 4`).
   Az aranyhalmaz `ROUTER_FELADAT`-ja ehhez igazodik. A regiszterben legyen `nyelvek = [...]` mező; a router zárja ki azt a
   modellt, amelyik a kért nyelvet nem tudja (pl. `whisper_*_hu` csak `hu`).
3. **Promptkészletek nyelvenként**, `PROMPT_VERZIO`-val nyelvenként (a „mért = éles” elv miatt minden nyelvi prompt külön mérést
   igényel).
4. **Nyelvsemleges kimeneti formátum**: a parszolt jelölők (`VÉGEREDMÉNY`, `ÍTÉLET`, `TANTÁRGY`) helyett JSON-kulcsok vagy
   kétnyelvű jelölők.
5. **A kapuk nyelvi csomagja**: stoplista, tagadószavak, tövesítés (angolra Snowball vagy Porter; az 5 karakteres előtag-tő
   angolra gyenge), tulajdonnév-heurisztika (az angol nagybetűs „I” és a címek), ékezethajtás a célnyelv betűire,
   szakaszkihagyó lista. **A küszöbök újramérése** a `bin/mos kapu meres`-sel az angol halmazon.
6. **A „magyar-kapuk” általánosítása „célnyelv-kapuvá”** (`cpp/ai.py`, `eval/kod`, `kozos/kijeloles`).
7. **Angol szállított aranyhalmazok** (§2.2), külön `VERZIO`-val.
8. **Whisper**: a `nyelv` a forrásból jöjjön, ne `"hu"` legyen beégetve; ismeretlen nyelvnél `None` (automatikus felismerés).

---

## 8. Javasolt sorrend (a termékesítés alapozásához)

1. **A küszöb kódba**: `[kalibracio.<f>]` (kuszob, min_tetel), kikényszerítés a `rogzit`-ben; a D9 kapuk változatlanok.
2. **Egységes regiszter-manifeszt** és **funkció → feladat** tábla (feladatleírás hu/en, nyelvek), a `letoltes.toml` beolvasztása.
3. **MM-backend**: telepítettség (revízió + blob-sha), lemezen mért méret, törlés (a kalibráció visszavonásával), strukturált
   haladásjelzés és megszakítás feladatsor-feladatként; `/api/modellek/*`.
4. **Hibaszerződés** (`kod`: `nincs_telepitve`, `nincs_kalibralt`, `csak_tavol`, `nincs_ai_runtime`), és a füzetlánc
   409-kezelésének javítása (`modulok/fuzet/modell.py:46-51`).
5. **SU**: a „Modell tesztelése” az előpróbával, az éles méréssel és a feltételes jellel; szállított aranyhalmazok a `kod`, a
   `kiegeszites` és a `matek*` feladatra, a többihez az anonim halmazok elkészítése, plusz a „saját halmaz” varázsló
   (`kijeloles_keszit.py` mintára, `{var}/eval-sajat/`).
6. **Közös modelltár és gépszintű zár** (`MOS_MODELS`, a zár áthelyezése); az ML-runtime leválasztása opcionális komponensbe.
7. **Nyelvi profil** (a router kulcsa, promptok, kapuk), az angol kör.
