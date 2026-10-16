# 07 — Fájlfa és fájlműveletek: Obsidian-paritás audit

**Alrendszer:** a bal oldalsáv fájlfája és a rá épülő fájlműveletek (új, átnevezés, áthelyezés, Kuka, import, húzás).
**Viszonyítás:** Obsidian 1.8/1.9 asztali, csak a core és a core-pluginok (File explorer, a *Files & links* beállításai). Ahol az Obsidian-viselkedésben nem vagyok biztos, a sor `bizonyosság: alacsony` jelet kap; ilyen állításra nem épül „must”.
**Olvasott kód** (az utak a `/Volumes/Work/[UNI] Manifold-OS` gyökeréhez képest): `app/src/hej/Fa.svelte`, `app/src/lib/vault/fa.ts`, `app/src/lib/vault/fajlok.svelte.ts`, `app/src/lib/vault/ikonok.svelte.ts`, `app/src/atfedes/Atnevezes.svelte`, `app/src/szerkeszto/linkek/atnevezes.ts`, `app/src/szerkeszto/csatolmany.ts`, `app/src/lib/ui/JegyzetIkon.svelte`, `app/src/lib/ikon/fajlIkon.ts`, `app/src/lib/elrendezes/felulet.svelte.ts`, `app/src/alapParancsok.ts`, `app/src/hej/Oldalsav.svelte`, `app/src/hej/nezetek/Helyorzo.svelte`, `app/src/szerkeszto/FajlCim.svelte`, `app/src/lib/core/hej.ts`; core: `core/vaultio.py`, `core/atnevezes.py`, `core/csatolmany.py`, `core/index/api.py`, `core/index/olvaso.py`, `core/index/indexelo.py`, `core/index/feloldas.py`, `core/index/tar.py`, `core/mediatipus.py`; héj: `shell/Sources/Kuka.swift`, `shell/Sources/AppController.swift`, `shell/Sources/HelyiMenu.swift`. Referencia: `docs/dev/ARCHITECTURE.md:157,190,209,538-540`, `docs/dev/DESIGN.md:215-220`, `docs/plan/audit/03-felulet.md:54,234,269`.

**Jelmagyarázat.** Státusz: *megvan* / *részben* / *hiányzik* / *n.a.* (nem Obsidian-core). Súly: **must** = napi Obsidian-szokás, azonnal hiányzik; **should** = észrevehető; **nice** = csiszolás. Ráfordítás: S (<1 nap), M (1–3 nap), L (>3 nap). A hiány-azonosító `07-explorer-NN` a 2. fejezetre mutat.

**Összkép.** A fa szerkezete, a billentyűzet-modell, az új fájl, az átnevezés/áthelyezés (tervvel és visszavonással), a Kuka, a külső import és a szerkesztőbe húzás megvan, több ponton az Obsidiannál erősebb (3. fejezet). Ami hiányzik, az főként a fa *kényelmi* rétege: rendezési módok, „Expand all”, soron belüli átnevezés, többes kijelölés, Finder-megmutatás, másolat, valamint az Obsidian `app.json`-beállításainak (új fájl helye, nem támogatott fájlok, Kuka-mód) tisztelete. Egy „must” van (rendezés), kilenc „should”, a többi csiszolás.

---

## 1. Ellenőrzőlista

| # | Obsidian-viselkedés | Manifold ma (path:line) | Státusz | Súly | Ráf. | Bizonyosság | Hiány |
|---|---|---|---|---|---|---|---|
| 1 | Mappa kinyit/becsuk kattintásra, ←/→ billentyűvel; állapot tartós | `Fa.svelte:44-50` (`valt`), `:92-96` (`aktival`), `:114-122` (←/→); tartós: `felulet.svelte.ts:56,115,223` (legfeljebb 2000 nyitott mappa, `:14`) | megvan | – | – | magas | – |
| 2 | **Collapse all** gomb a fejlécben | `Fa.svelte:342-344` (`osszecsuk`), gomb `:366`; ⌘P `fa.osszecsuk` `alapParancsok.ts:125` | megvan | – | – | magas | – |
| 3 | Ugyanaz a gomb **Expand all**-ra vált, ha minden zárva | nincs: csak összecsukás; a nyitott halmaz a `felulet.oldalsav.nyitott` | hiányzik | should | S | magas | 02 |
| 4 | Rendezés: *File name (A to Z)* alapértelmezés | fix magyar `Intl.Collator('hu', {numeric})`, mappák elöl: `fa.ts:32-36,79` | megvan (fix) | – | – | magas | – |
| 5 | **Change sort order** menü: név Z→A, módosítás új→régi / régi→új, létrehozás új→régi / régi→új; tartós | nincs rendezésváltó. Az `mtime` megvan a listában (`fajlok.svelte.ts:10-15`, `olvaso.py:177-182`), létrehozási idő nincs az indexben (`tar.py:21-36`: csak `mtime_ns`) | hiányzik | **must** | M | magas | 01 |
| 6 | **New note** a fejlécben: „Untitled” az alapértelmezett helyen (*Default location for new notes*), megnyílik, a cím azonnal átnevezhető | gomb `Fa.svelte:364` → soron belüli névmező `:155-160,434-479` → `POST /api/vault/uj` (`vaultio.py:421-495`; H1 automatikusan `:463`, kurzor a fülön `Fa.svelte:192`). A hely a fókuszált sor mappája vagy a gyökér (`:150-153`); a `newFileLocation`-t a core csak a feloldatlan link jegyzetéhez olvassa (`vaultio.py:369-380,382-410`) | részben | should | S | magas | 10 |
| 7 | **⌘N** „Create new note” globális gyorsbillentyű | nincs `Mod+N` kötés; a `fa.uj-jegyzet` parancsnak nincs billentyűje (`alapParancsok.ts:114-124`) | hiányzik | should | S | magas | 10 |
| 8 | **New folder** (fejléc + mappa menü), soron belüli név | gomb `Fa.svelte:365`, menü `:230`; `POST /api/vault/mappa` (`csatolmany.py:275-285`, névellenőrzés `:103-106`) | megvan | – | – | magas | – |
| 9 | **New canvas** (mappa menü, parancs, szalag) | mappa menü `Fa.svelte:234`; core `vaultio.py:41` (`UJ_CANVAS`); ⌘P `canvas.uj` `canvas/index.ts:66` | megvan | – | – | magas | – |
| 10 | **New base** (1.9: mappa menü, parancs) | mappa menü `Fa.svelte:233`; core `vaultio.py:40` (`UJ_BASE`); ⌘P-parancs nincs | megvan (parancs: nice) | nice | S | magas | 23 |
| 11 | **Rename (F2)**: a név a fa sorában, helyben szerkeszthető; ↩ átnevez, a linkek a beállítás szerint frissülnek (párbeszéd nélkül) | F2 a parancsregiszteren át a fókuszált sorra (`linkek/atnevezes.ts:172-190`); **modális** átfedést nyit tervvel (`Fa.svelte:217-220`, `Atnevezes.svelte:138-151,184-239`). A szerkesztő fejlécének címmezője is átnevez (`FajlCim.svelte:11-29`) | részben | should | M | magas | 03 |
| 12 | **Áthelyezés húzással** mappára vagy a gyökérre; a zárt mappa kinyílik; azonnal végrehajt | `Fa.svelte:271-314` (`huzasKezd`, `huzasFolott`, `ejtes`), szabályok `fa.ts:105-117`, kinyitás 700 ms `:290`; az ejtés a **terv-átfedést** nyitja, megerősítés kell (`:313`, `Atnevezes.svelte:37`) | részben (plusz kattintás) | should | S | magas | 15 |
| 13 | **„Move file to…”** parancs mappaválasztóval | `vault.athelyezes` (`linkek/atnevezes.ts:191`); fuzzy mappalista ↑↓↩ (`Atnevezes.svelte:47-53,152-183`) | megvan | – | – | magas | – |
| 14 | Mappa áthelyezése/átnevezése (húzás, „Move folder to…”, „Rename”) | ugyanaz az út, `mappaMod` (`Atnevezes.svelte:22`); core `_ellenoriz_mappa` (`atnevezes.py:286-335`), atomi `os.rename` (`:73-80`); rejtett fájl vagy symlink a mappában blokkol (`:309-324`) | megvan (szegély: 21) | nice | S | magas | 21 |
| 15 | **Delete** → megerősítő párbeszéd (*Confirm file deletion* kikapcsolható); a cél a `trashOption` szerint: rendszer-Kuka / `.trash` / végleges | menü `Fa.svelte:246`, párbeszéd `:350-360`, `kukaba` `:327-338` → `POST /api/vault/kuka` (`csatolmany.py:296-343`) → `Manifold --kuka` (`Kuka.swift:22`, `trashItem`). Mindig megerősít, mindig a macOS Kuka | megvan (opciók: részben) | nice | M | magas | 20 |
| 16 | Delete/⌫ billentyű a fában a kijelölt elemre → a párbeszéd | a `billentyu` (`Fa.svelte:102-129`) nem kezeli | hiányzik | nice | S | alacsony | 05 |
| 17 | **Show in system explorer** (Reveal in Finder) fájlra és mappára | nincs; a héj-híd csak `megnyit` (http/https/mailto) üzenetet ismer (`hej.ts:5-18`, `AppController.swift:269-273`) | hiányzik | should | S | magas | 07 |
| 18 | **Open in default app** | nincs; a nem támogatott fájl helyőrzője sem kínálja (`Helyorzo.svelte:43`) | hiányzik | nice | S | magas | 08 |
| 19 | **Copy Obsidian URL** (core). Sima „Copy path” nem core-elem (alacsony) | nincs; vágólap-segéd van (`szerkeszto/vagolap.ts`) | hiányzik | nice | S | közepes | 09 |
| 20 | **Make a copy** → „Név 1.md” ugyanabban a mappában | nincs; az ütközés-számozás mintája az importban megvan (`csatolmany.py:223-233`) | hiányzik | should | M | magas | 06 |
| 21 | **Mappa helyi menü**: New note / New folder / New canvas / New base / Rename / Move folder to… / Delete / Search in folder / Bookmark / Show in system explorer | `Fa.svelte:229-247`: Új mappa, Új jegyzet, Új jegyzet sablonból…, Új adatbázis-nézet, Új canvas, Összefoglalás a mappából, Keresés ebben a mappában, Mappa átnevezése…, Áthelyezés a Kukába…, Mappa áthelyezése… | részben (Finder, Bookmark hiányzik) | – | – | magas | 07, nyitott kérdés 8 |
| 22 | **Fájl helyi menü**: Open in new tab / Open to the right / Open in new window / Make a copy / Move file to… / Bookmark / Rename / Delete / Copy Obsidian URL / Show in system explorer / Open in default app | `Fa.svelte:240-247`: Megnyitás, Megnyitás új fülben, Megnyitás osztásban, Összefoglalás, Átnevezés… (F2), Áthelyezés a Kukába…, Áthelyezés… | részben | – | – | magas | 06, 07, 08, 09 |
| 23 | **Reveal current file in navigation** parancs (biztos); automatikus követés kapcsoló (alacsony) | parancs `fa.megmutat` (`alapParancsok.ts:86-95`) → `Felulet.megmutatFaban` (`felulet.svelte.ts:198-207`) → fókusz a sorra (`Fa.svelte:65-68`). Automatikus követés nincs; a fa csak jelöli az aktív fájlt (`:394,406`) | részben | should | S | alacsony | 11 |
| 24 | „Show attachments” kapcsoló — **nem Obsidian-core** (a legközelebbi: *Detect all file extensions*, lásd 27.) | nincs szűrő: az index minden fájlja látszik (`fa.ts:58-61`) | n.a. | – | – | alacsony | – |
| 25 | **Excluded files** (`userIgnoreFilters`): keresés, gráf, gyorsváltó, unlinked mentions elől rejt; a fában (szerintem) látszanak | nincs felhasználói kizárás; fix `SKIP_DIRS` (`feloldas.py:38`), pontos fájlok (`:127`, `indexelo.py:63-67`). Az `app.json`-ból csak `attachmentFolderPath` (`csatolmany.py:109-119`) és `newFileLocation` (`vaultio.py:369-380`) olvasódik | hiányzik (index-szint) | nice | M | alacsony | 13 |
| 26 | **Fájl-ikon**: nincs; a nem-md fájl neve kiterjesztés nélkül + kis nagybetűs címke (`PDF`, `PNG`, `CANVAS`) | típus-ikon (`fajlIkon.ts:5-21`), frontmatter `icon` emoji/kép (`JegyzetIkon.svelte:14-34`, `ikonok.svelte.ts:22-29`, `olvaso.py:326-345`); a nem-md név teljes `név.kit` (`fajlok.svelte.ts:28-31`) | megvan+ (címke: részben) | nice | S | közepes | 14 |
| 27 | **Nem támogatott típus**: rejtve, amíg a *Detect all file extensions* (`showUnsupportedFiles`) nincs bekapcsolva; megnyitás a rendszer appjával | minden látszik `egyeb` típussal (`indexelo.py:44-60`); megnyitás → `Helyorzo.svelte` (típus, méret, módosítva) | részben | should | S | magas | 12 |
| 28 | **Fájl húzása a jegyzetbe** → `[[jegyzet]]`, képre/PDF-re/médiára `![[…]]` a kurzorhoz | `Fa.svelte:274` (`VAULT_HUZAS`), ejtés `csatolmany.ts:93-101`, a legrövidebb egyértelmű link a core feloldásával `:62`; `!` kiterjesztés-regex alapján `:67` | megvan (csiszolás) | nice | S | magas | 16, 17 |
| 29 | **Többes kijelölés**: ⇧/⌘-kattintás, együtt húzható, „Move N files…”, „Delete N files” | nincs: egy `fokuszUt` (`Fa.svelte:36`), egy `huzott` (`:259`); a core végpontok egy utat fogadnak (`atnevezes.py:848-850`, `csatolmany.py:296-299`) | hiányzik | should | L | magas | 04 |
| 30 | Külső fájl ejtése a fába (Finder → mappa): bemásol | `Fa.svelte:304-309,316-323` → `fajlImport` (`csatolmany.ts:34-45`, 4 MiB-os darabok, foglalt zárra újrapróbál `:19-32`) → `POST /api/vault/import` (`csatolmany.py:158-239`, „név 1” ütközésnév `:223-233`) | megvan | – | – | magas | – |
| 31 | Középső kattintás → új fül | csak `onclick` (`Fa.svelte:410`); ⌘ új fül, ⌘⌥ osztás (`navigacio.ts:31-35`) | hiányzik | nice | S | közepes | 18 |
| 32 | Jobb klikk a fa üres területén → a gyökér (mappa-)menüje | `oncontextmenu` csak a sorokon (`Fa.svelte:412`) | hiányzik | nice | S | alacsony | 19 |
| 33 | Átnevezés után a nyitott fülek, legutóbbiak, nyitott mappák követik | `Felulet.utatNevez` (`felulet.svelte.ts:190-195`), WS `vault_atnevezes` (`linkek/atnevezes.ts:147-163`) | megvan | – | – | magas | – |
| 34 | Billentyűs navigáció a fában (↑↓, ↩) | teljes ARIA-fa: ↑↓ Home End → ← ↩ szóköz ⇧F10 (`Fa.svelte:102-129,397-406`) | megvan+ | – | – | közepes | – |
| 35 | **Search in folder** | `Fa.svelte:236-238` (`path:"…/"` előtaggal nyitja a keresőablakot) | megvan | – | – | magas | – |
| 36 | Mappa-számláló a sor végén | nincs az Obsidianban | `fa.ts:63-77`, `Fa.svelte:423` | megvan+ (erősség) | – | – | magas | – |
| 37 | Fájlnév-tiltás: `* " \ / < > : \| ? # ^ [ ]` | azonos készlet `vaultio.py:52` (`_TILTOTT_NEV`), `atnevezes.py:220-222`, `csatolmany.py:103-106` | megvan | – | – | magas | – |

---

## 2. Hiányok és javaslatok

Minden javaslat a meglévő rétegezésben marad: a felület nem olvas fájlrendszert és nem old fel linket (ARCHITECTURE 2.), minden írás a core végpontjain megy, a héj (Swift) csak a rendszer-integrációt adja.

### 07-explorer-01 — Rendezési módok (must, M, magas)
**Obsidian.** A fejléc „Change sort order” gombja hat módot kínál: *File name (A to Z / Z to A)*, *Modified time (new to old / old to new)*, *Created time (new to old / old to new)*; a választás tartós, a mappák mindig a fájlok előtt.
**Manifold.** Egyetlen fix rend (`fa.ts:32,79`): magyar ábécé, számok értékük szerint, mappák elöl. Az `mtime` már a listában van (`fajlok.svelte.ts:14`, `olvaso.py:179-180`), a létrehozási idő nincs (`tar.py:21-36`).
**Javaslat.**
1. `felulet.oldalsav.rendezes: 'nev' | 'nev-forditva' | 'modositva' | 'modositva-regi' | 'letrejott' | 'letrejott-regi'` a `Felulet`-ben (`felulet.svelte.ts:56`, `beallit`/`sorosit` `:108-116,223`), alap `'nev'`.
2. `faEpit(lista, mappak, rendezes)` (`fa.ts:43-83`): a `FaCsomopont` kap `mtime`/`btime` mezőt (fájl: a sajátja; mappa: a részfa legfrissebbje — nyitott kérdés 1), a `rendez` komparátora a mód szerint, a mappák továbbra is elöl és név szerint. A `nevHasonlit` marad a név-módok alapja (a magyar rend megőrzendő erősség). Teszt: `app/tests/fa.test.ts` bővítése.
3. UI: a fejléc (`Fa.svelte:362-367`) egy `ArrowDownAZ`-ikongombja `lebegoMenu`-vel (a `szerkeszto/notion/menu` már a helyi menüt is adja), ⌘P-parancsok `fa.rendezes.<mód>` az `alapParancsok.ts`-ben.
4. Létrehozási idő: az index `fajl` táblája kap `btime_ns` oszlopot (`tar.py:21-36`, sémaverzió-léptetés), az indexelő az `mtime_ns` mellé írja az `st_birthtime`-ot (`indexelo.py:690,744`), az `olvaso.fa()` (`olvaso.py:177-182`) és a `FajlInfo` (`fajlok.svelte.ts:10-15`) adja tovább. A `tartos.atomi_ir` megőrzi a születési időt (`vaultio.py:7,152-155`), így a mentés nem rontja el a rendet. Létrehozási idő nélkül S, vele M.

### 07-explorer-02 — Expand all (should, S, magas)
**Obsidian.** A „Collapse all” gomb „Expand all”-ra vált, ha minden mappa zárva.
**Manifold.** Csak összecsukás (`Fa.svelte:342-344,366`).
**Javaslat.** `osszesKinyit()`: a `gyoker` bejárásával minden mappaút a `felulet.oldalsav.nyitott`-ba (a 2000-es plafonra figyelve, `felulet.svelte.ts:14`: fölötte mélységi korlát és értesítés); a gomb ikonja `ChevronsDownUp` ↔ `ChevronsUpDown` a `nyitott.size === 0` szerint; ⌘P `fa.kinyit`.

### 07-explorer-03 — Soron belüli átnevezés (should, M, magas)
**Obsidian.** F2 / „Rename…” a fa sorában teszi szerkeszthetővé a nevet; ↩ átnevez, Esc elvet; a linkek a beállítás szerint, párbeszéd nélkül frissülnek.
**Manifold.** F2 a regiszteren át (`linkek/atnevezes.ts:172-190`) modális átfedést nyit: név → terv → megerősítés (`Atnevezes.svelte:138-151,184-239`). A terv és a visszavonás megőrzendő erősség, de a gyakori eset (nincs érintett link) három lépés.
**Javaslat.** Az `ujSor` mintájára (`Fa.svelte:434-463`) egy `atnevezesSor = { ut, nev }` állapot: a sor `.nev` eleme (`:422`) helyén `<input>`; ↩ → `atnevezesTerv(regi, uj)`; ha `terv.ok && terv.fajlok.length === 0 && !terv.figyelmeztetesek?.length` → azonnal `atnevezesVegrehajt` + `atnevezesErtesites` (a „Visszavonás” gombos értesítés már megvan, `linkek/atnevezes.ts:134-144`); különben a mai átfedés nyílik a tervvel előtöltve (a `felulet.atnevezes` típusa `uj?: string`-gel bővül, `felulet.svelte.ts:72`; az `Atnevezes.svelte:35-40` a húzás mintájára rögtön `terveznel`-t hív). Az F2 a `billentyu`-ban (`Fa.svelte:102-129`) helyben indul; a regiszter-parancs a szerkesztő aktív fájljára marad. Mappára ugyanez.

### 07-explorer-04 — Többes kijelölés (should, L, magas)
**Obsidian.** ⇧-kattintás tartomány, ⌘-kattintás hozzáad; a kijelölés együtt húzható, a helyi menü „Move N files to…”, „Delete N files”; a szerkesztőbe ejtve N link.
**Manifold.** Egyetlen fókuszált/húzott elem (`Fa.svelte:36,259`); a core végpontok egy utat fogadnak.
**Javaslat.** Felület: `kijelolt: Set<string>` állapot, ⇧/⌘ a `aktival`-ban (`:92-96`), `aria-multiselectable="true"` a fán, `aria-selected` a sorokon (`:406`); a húzás a `VAULT_HUZAS`-ba JSON-listát tesz, a `csatolmany.ts:96` listát olvas és N linket szúr; a helyi menü N elemre „Áthelyezés (N)…”, „Áthelyezés a Kukába (N)…”. Core: a `/api/vault/atnevezes/terv` és `/api/vault/atnevezes` fogadjon `{tetelek: [{ut, uj}]}` alakot — a `_Terv.lek` leképezés már többutas (`atnevezes.py:195`, `_terv_kozos` `:364-393`), tehát a többfájlos terv a leképezések uniója egy commitban; a `/api/vault/kuka` fogadjon `utak` listát (egy `_kor_zar`, egy kézi commit, `csatolmany.py:300-343`). Visszavonás: egy pillanatkép az egész kötegre.

### 07-explorer-05 — Delete/⌫ billentyű a fában (nice, S, alacsony)
**Obsidian.** A kijelölt elemen a Delete (macOS: ⌘⌫) a törlés-párbeszédet nyitja — ebben nem vagyok biztos.
**Manifold.** A `billentyu` nem kezeli.
**Javaslat.** `Delete` és `Meta+Backspace` → `torlendo = cs.ut; torlesHiba = ''` (`Fa.svelte:102-129,246`).

### 07-explorer-06 — Make a copy (should, M, magas)
**Obsidian.** Fájl menü „Make a copy” → „Név 1.md” ugyanabban a mappában, a tartalom szó szerint (frontmatter is).
**Manifold.** Nincs.
**Javaslat.** Core `Vault.masol(d)` a `vaultio.py`-ban: cél `<törzs> 1<kit>`, számozás az import mintájával (`csatolmany.py:223-233`), kis-nagybetű- és NFC-független ütközés-vizsgálat (`vaultio.py:452`); szöveges fájl: `tartos.kizaro_ir` + `commit_machine("másolat a pultban: …")` (`:473-486` mintája); bináris: `shutil.copy2`, commit nélkül (a `kovetett` szűrő `csatolmany.py:147-155`). Útvonal `POST /api/vault/masolat {ut}` az `utvonalak`-ban (`vaultio.py:510-514`), ARCHITECTURE-táblázat (`:538-540`). UI: menüelem `masolat` (`Fa.svelte:240-247`) → `kerdez` → `fajlok.frissit()` → a másolat megnyitása és megmutatása (`felulet.megmutatFaban`).

### 07-explorer-07 — Show in system explorer / Reveal in Finder (should, S, magas)
**Obsidian.** Fájl és mappa menüben.
**Manifold.** Nincs; a héj-híd `megnyit` üzenete csak http/https/mailto (`hej.ts:7`, `AppController.swift:269-273`, `Biztonsag.megnyithatoKulsoCim`).
**Javaslat.** Új híd-üzenet `{ tipus: 'finder', ut }` (`hej.ts:5-18` unió + `hid.ts`); `AppController.swift` `case "finder"`: a vault gyökeréhez illeszti (a héj ismeri a vault útját), a `Kuka.ellenoriz` mintájával ellenőrzi (`Kuka.swift:80-105`: gyökér alatt, nincs `..`, nem kötet-gyökér), majd `NSWorkspace.shared.activateFileViewerSelecting([url])`. Menüelem fájlra és mappára (`Fa.svelte:245` mellé), ⌘P `fa.finder` az aktív fájlra; a `window.webkit` nélküli (böngészős) futásban az elem rejtve.

### 07-explorer-08 — Open in default app (nice, S, magas)
**Javaslat.** Ugyanaz a híd: `{ tipus: 'megnyit-fajl', ut }` → ugyanazzal az útellenőrzéssel `NSWorkspace.shared.open(url)`; menüelem a fájl menüben és egy gomb a `Helyorzo.svelte:43` helyőrzőjén („Megnyitás a rendszer alkalmazásával”).

### 07-explorer-09 — Copy Obsidian URL / vault-út másolása (nice, S, közepes)
**Obsidian.** „Copy Obsidian URL” a fájl menüben (core). Sima „Copy path” nem core-elem (alacsony bizonyosság).
**Manifold.** Nincs; a `vagolapra` segéd megvan (`szerkeszto/vagolap.ts`).
**Javaslat.** Két menüelem: „Vault-út másolása” (`vagolapra(cs.ut)`) és „Obsidian URL másolása” (`obsidian://open?vault=<név>&file=<út .md nélkül>`, `encodeURIComponent`); a vault neve a `GET /api/vault/index` válaszába vagy a `hello` eseménybe kerüljön (a felület nem ismeri az abszolút utat). Mivel a vault egyben Obsidian-vault, az URL az Obsidianban is nyit.

### 07-explorer-10 — ⌘N és az új jegyzet helye a beállítás szerint (should, S, magas)
**Obsidian.** ⌘N új jegyzet; a fejléc „New note” gombja és a ⌘N a *Default location for new notes* (`newFileLocation`: root / current / folder + `newFileFolderPath`) szerint rak.
**Manifold.** Nincs ⌘N; a fejléc gombja a fókuszált sor mappáját vagy a gyökeret használja (`Fa.svelte:150-153,364`); a core a beállítást csak a feloldatlan linkhez olvassa (`uj_fajl_beallitas` `vaultio.py:369-380`, `link_jegyzet_helye` `:382-410`).
**Javaslat.** `billentyu: 'Mod+N'` a `fa.uj-jegyzet` parancson (`alapParancsok.ts:114`; a CodeMirror nem használja). A fókuszált sor nélküli indításnál a `POST /api/vault/uj` kap `{ hely: 'alap', forras: <aktív fül útja> }` alakot, amelyet a `create` (`vaultio.py:421-430`) a `link_jegyzet_helye` útján old fel (`root|current|folder`), és a névmező abban a mappában nyílik (`ujJegyzetNyit(mappa)`, a mappa `valt`-tal kinyitva). A mappa helyi menüjének „Új jegyzet itt” változatlan.

### 07-explorer-11 — Az aktív fájl automatikus követése (should, S, alacsony)
**Obsidian.** „Files: Reveal current file in navigation” parancs (biztos). Automatikus követés kapcsolóként — nem vagyok biztos, hogy core.
**Manifold.** A parancs megvan (`alapParancsok.ts:86-95`), automatikus követés nincs; a `megmutatFaban` fókuszt is ad a sornak (`Fa.svelte:56-62,65-68`), ami automatikus módban elvenné a szerkesztő fókuszát.
**Javaslat.** `felulet.oldalsav.autoMegmutat: boolean` (tartós); `$effect` a `Fa.svelte`-ben az `aktivUt`-ra: az ősmappák nyitása (`osMappak` `fa.ts:99-103`) és `scrollIntoView({ block: 'nearest' })` **fókusz nélkül**; kapcsoló a fejléc menüjében és ⌘P `fa.auto-megmutat`.

### 07-explorer-12 — Nem támogatott fájltípusok elrejtése a beállítás szerint (should, S, magas)
**Obsidian.** Az ismeretlen kiterjesztésű fájl (pl. `.txt`, `.docx`, `.zip`) rejtve marad, amíg a *Detect all file extensions* (`showUnsupportedFiles`) nincs bekapcsolva; bekapcsolva a rendszer appjával nyílik.
**Manifold.** Minden fájl látszik `egyeb` típussal (`indexelo.py:44-60`), kattintásra a `Helyorzo.svelte`.
**Javaslat.** Core: az `olvaso.fa()` válasza (`olvaso.py:177-182`) kap `beallitasok: { minden_kiterjesztes }` mezőt az `.obsidian/app.json` `showUnsupportedFiles` kulcsából (olvasó az `uj_fajl_beallitas` mellé, `vaultio.py:369-380`). Felület: a `faEpit` kihagyja az `egyeb` típust, ha a beállítás hamis és nincs `felulet.oldalsav.mindenFajl` felülírás; kivétel a `.cpp` (Manifold saját nézete, `kod/index.ts:24`). A számlálók (`fa.ts:63-77`) a látható fájlokat számolják. Nyitott kérdés 5: rejtés vagy halványítás.

### 07-explorer-13 — Excluded files (`userIgnoreFilters`) (nice, M, alacsony)
**Obsidian.** A *Excluded files* lista a keresésből, gráfból, gyorsváltóból, unlinked mentionsből rejt; a fában — szerintem — a fájlok látszanak.
**Manifold.** Nincs felhasználói kizárás, csak a fix `SKIP_DIRS` (`feloldas.py:38`) és a pontos fájlok (`:127`).
**Javaslat.** A core olvassa a `userIgnoreFilters`-t (előtag vagy `/regex/`), a `fa()` fájlonként `kizart: true`-t ad; a fa halványítja (`--atlatszosag-felig`), a keresés/gráf/gyorsváltó alrendszere tiszteli (ott a paritás-hiány; itt csak a jelzés). Előbb ellenőrizni az Obsidian fa-viselkedését.

### 07-explorer-14 — Kiterjesztés-címke a teljes fájlnév helyett (nice, S, közepes)
**Obsidian.** A nem-md fájl neve kiterjesztés nélkül, mellette kis nagybetűs címke (`PDF`, `CANVAS`, `BASE`, `PNG`).
**Manifold.** `fajlNev` csak az `.md`-t vágja (`fajlok.svelte.ts:28-31`), a sor a teljes nevet mutatja (`Fa.svelte:422`), az ikon mondja a típust.
**Javaslat.** A sorban `<span class="kit">` a kiterjesztéssel (`--betu-kicsi`, `--szoveg-halvany`, mint a `.db` `:577-582`); a `fajlNev`-et a gyorsváltó és a fülek is használják, ezért külön `megjelenoNev(ut)` vagy paraméter, hogy a többi hely viselkedése ne változzon (nyitott kérdés 10).

### 07-explorer-15 — Húzásos áthelyezés megerősítés nélkül, ha nincs link-változás (should, S, magas)
**Obsidian.** Az ejtés azonnal áthelyez.
**Manifold.** Az ejtés mindig a terv-átfedést nyitja (`Fa.svelte:313`, `Atnevezes.svelte:37`).
**Javaslat.** Az `ejtes`-ben (`Fa.svelte:301-314`) előbb `atnevezesTerv`; ha `ok && fajlok.length === 0 && !figyelmeztetesek?.length` → `atnevezesVegrehajt` + `atnevezesErtesites` (a „Visszavonás” gomb megmarad); különben a mai átfedés. Opcionális `felulet.athelyezes.megerosit: 'mindig' | 'csak-linkeknel'` kapcsoló azoknak, akik a tervet mindig látni akarják. Mappára ugyanez (`mozgo_fajlok > 0` önmagában nem ok a párbeszédre).

### 07-explorer-16 — Mappa húzása a szerkesztőbe nyers útvonalat szúr be (nice, S, közepes)
**Obsidian.** Mappa ejtése a szerkesztőbe nem csinál semmit (közepes bizonyosság).
**Manifold.** A `huzasKezd` mappára is `text/plain`-t ad (`Fa.svelte:273`), a `VAULT_HUZAS`-t csak fájlra (`:274`); a `csatolmany.ts:93-101` ejtés-kezelője `false`-szal tér vissza, így a CodeMirror alapértelmezése a mappa útját szövegként beszúrja.
**Javaslat.** Mappára ne legyen `text/plain` (vagy `VAULT_HUZAS` `mappa:` előtaggal, amelyet a `drop` `preventDefault`-tal nyel el).

### 07-explorer-17 — A beágyazás/link döntés ad hoc regexszel (nice, S, magas)
**Manifold.** `csatolmany.ts:67` saját kiterjesztés-listája (png jpg jpeg gif webp heic pdf mp4 mov mp3 wav svg) szűkebb, mint a `mediatipus.MEDIA_TIPUS` (`mediatipus.py:19-28`: avif, bmp, tiff, m4a, flac, ogg, webm, mkv…) — egy `.m4a` húzása `[[…]]`-t ad `![[…]]` helyett.
**Javaslat.** `fajlok.info(ut)?.tipus ∈ {kep, pdf, video, hang}` döntsön (`fajlok.svelte.ts:59-62`); külső fájlnál az import válaszának útja után ugyanez.

### 07-explorer-18 — Középső kattintás új fülben nyit (nice, S, közepes)
**Javaslat.** `onauxclick` (`button === 1`) → `felulet.munkaterulet.megnyit(cs.ut, 'ujful')` a sor eseményei közé (`Fa.svelte:410-413`).

### 07-explorer-19 — Jobb klikk az üres területen → a gyökér menüje (nice, S, alacsony)
**Javaslat.** `oncontextmenu` a `.fa` tárolón (`Fa.svelte:370-384`), ha a cél nem sor: a mappa-menü a gyökérre (`ujJegyzetNyit('')`, `'mappa'`, `'base'`, `'canvas'`, keresés előtag nélkül), átnevezés/áthelyezés/Kuka nélkül.

### 07-explorer-20 — `trashOption` és a megerősítés kikapcsolása (nice, M, magas)
**Obsidian.** *Deleted files*: system trash / Obsidian `.trash` / permanent; *Confirm file deletion* kikapcsolható.
**Manifold.** Mindig a macOS Kuka a héj-segéddel (`csatolmany.py:322-340`, `Kuka.swift:22`), mindig megerősítés (`Fa.svelte:350-360`).
**Javaslat.** A `kuka()` olvassa a `trashOption`-t: `system` → mai út; `local` → `<vault>/.trash/<név>` `tartos.rename_excl`-lel és ütközés-számozással (a `.trash` a `SKIP_DIRS`-ben van, `feloldas.py:38`, tehát az indexből eltűnik); `none` → nyitott kérdés 4 (javaslat: rendszer-Kuka és értesítés, végleges törlés nincs). Felület: „Ne kérdezze többet” jelölő a párbeszédben → `felulet.kuka.megerosit` (tartós), a helyi menü ilyenkor közvetlenül `kukaba()`.

### 07-explorer-21 — Mappa-áthelyezés rejtett fájl miatt blokkol (nice, S, magas)
**Obsidian.** Bármilyen tartalmú mappát áthelyez.
**Manifold.** `_ellenoriz_mappa` (`atnevezes.py:309-324`) minden pontos fájlt/mappát és symlinket blokkolónak vesz (kivéve `.DS_Store`): egy `.gitkeep` vagy `.obsidian`-szerű almappa megakasztja.
**Javaslat.** A pontos elemek „mozognak, de nincsenek a tervben” (nem indexeltek, az `os.rename` a teljes mappát egyben viszi, `_mozgat` `:73-80`); blokkoló csak a vaulton kívülre mutató symlink maradjon (`utkapu.belul`). A docstring (`:287-289`) frissítendő: a média már mozoghat (CX-003).

### 07-explorer-22 — Dokumentáció és a parancs hatóköre eltér a kódtól (nice, S, magas)
**Manifold.** `ARCHITECTURE.md:209` szerint csak `.md`/`.canvas` nevezhető át; a kód (CX-003, `atnevezes.py:4,213-238`) bármely fájlt enged azonos kiterjesztéssel, mappát médiával is (`:286-335`). A ⌘P „Jegyzet átnevezése…” az aktív fülre csak md/canvas/base esetén él (`linkek/atnevezes.ts:65,168-171`), miközben a fában egy PDF is átnevezhető.
**Javaslat.** ARCHITECTURE-bekezdés igazítása; a `SZOVEGES` szűrő elhagyása az `aktivUt`-ban (a média átnevezése visszavonás nélkül megy, `atnevezes.py:741-745`, az értesítés ezt már jelzi).

### 07-explorer-23 — „Új adatbázis-nézet” ⌘P-parancs (nice, S, magas)
**Obsidian.** „Bases: Create new base” parancs (1.9).
**Manifold.** Csak a mappa helyi menüjéből (`Fa.svelte:233`); a canvasnak van parancsa (`canvas/index.ts:66`).
**Javaslat.** `bazis.uj` parancs a `bazis/index.ts`-ben a `canvas.uj` mintájára (`ujJegyzetNyit(celMappa(), 'base')` a `felulet.faUjJegyzet` mintájú jelzéssel).

---

## 3. Manifold-erősségek az Obsidianon túl (megőrzendők)

1. **Átnevezés és áthelyezés tervvel, referencia-próbával és visszavonással.** A terv soronként mutatja az előtte→utána linkeket, a blokkolókat és a Bases-kifejezések figyelmeztetéseit (`Atnevezes.svelte:184-239`; core `atnevezes.py:364-393` terv, `:596-640` próba), egy pillanatkép, „Visszavonás” gomb az értesítésen (`linkek/atnevezes.ts:110-144`), szándéknapló a megszakadt művelet helyreállítására (`atnevezes.py:85-150`), a mentetlen dokumentum védelme (`:685-694`). Az Obsidian csendben ír át, visszavonás nélkül.
2. **Mappa-számlálók** a sor végén és a fejlécben (`fa.ts:63-77`, `Fa.svelte:363,423`), tooltipben jegyzet/fájl bontás (`:346,407`).
3. **Magyar ábécérend** digráfokkal, a számok értékük szerint (`fa.ts:32-36`; teszt `app/tests/fa.test.ts:10-24`). A rendezési módok (01) ezt alapként tartsák meg.
4. **Ikonok**: típus-ikon és a frontmatter `icon` (emoji vagy a core által feloldott kép) a fában, a fülön, a keresőben (`JegyzetIkon.svelte`, `ikonok.svelte.ts`, `olvaso.py:326-345`). Az Obsidian core-ban nincs fájl-ikon.
5. **Teljes billentyűzet-modell** ARIA-fával: ↑↓ Home End → ← ↩ szóköz, ⇧F10/ContextMenu, gördülő tabindex, F6-régió (`Fa.svelte:102-129,397-406`).
6. **Új fájl név előtt, „Untitled”-szemét nélkül**: soron belüli névmező, automatikus H1 a sorszám-előtag nélkül, kurzor a H1 után (`Fa.svelte:434-479,192`, `vaultio.py:66,463`); kizáró írás (`tartos.kizaro_ir`, `:473-476`), kis-nagybetű- és NFC-független ütközés (`:452`), az Obsidianéval azonos névtiltás (`:52`).
7. **Új jegyzet sablonból** a mappa menüjéből, séma-ellenőrzéssel és „Mégis létrehozom” megerősítéssel (`Fa.svelte:232,175-184,464-477`).
8. **Mappa- és fájlszintű AI-műveletek** a helyi menüben: „Összefoglalás a mappából”, „Összefoglalás az átiratból” (`Fa.svelte:235,243`).
9. **A húzás sosem ír**: az ejtés terv (`Fa.svelte:6,313`); a külső fájl darabolt, fsync-elt, ütközésmentes importtal kerül be, foglalt zárra újrapróbálással (`csatolmany.ts:19-45`, `csatolmany.py:158-239`).
10. **Kuka biztonsággal**: a héj-segéd csak a vault alatti elemet mozgatja (`Kuka.swift:80-105`), a core útvonal-zárakkal, mentetlen-dokumentum őrrel és előzetes kézi commitral (`csatolmany.py:308-321`); a visszahozás a macOS Kukából.
11. **Élő fa** WS-eseményre, 300 ms-os összevonással és a gyanús zsugorodás (lecsatolt kötet, részleges index) elleni őrrel (`fajlok.svelte.ts:38-41,83-96,98-123`); a vault elérhetetlensége külön eseményként (`vaultio.py:184-205`).
12. **Megnyitás új fülben / osztásban** ⌘ és ⌘⌥ kattintással és a menüből (`navigacio.ts:31-35`, `Fa.svelte:240-242`).
13. **Tartós állapot**: nyitott mappák (2000-es plafon), oldalsáv-nézet; átnevezés után a fülek, a legutóbbiak és a nyitott mappák átcímződnek (`felulet.svelte.ts:56,115,190-207`).
14. **Az Obsidian beállításainak tisztelete ott, ahol már olvassuk**: `attachmentFolderPath` (`csatolmany.py:109-137`), `newFileLocation`/`newFileFolderPath` a feloldatlan link jegyzetéhez (`vaultio.py:369-410`) — a 10., 12., 20. hiány ezt a mintát terjeszti ki.
15. **Keresés ebben a mappában** a keresőablak `path:` előtagjával (`Fa.svelte:236-238`), a Címkék fül ugyanabban az oldalsávban (`Oldalsav.svelte:37-40`).

---

## 4. Nyitott kérdések

1. **Rendezés mappákra**: a választott mód a mappákra is vonatkozzon (módosítási idő = a részfa legfrissebbje), vagy a mappák mindig név szerint álljanak? Az Obsidian viselkedésében nem vagyok biztos.
2. **Soron belüli átnevezés küszöbe**: link-változás nélkül azonnali végrehajtás (visszavonással), link-változásnál a terv — vagy beállítás, amely mindig a tervet kéri?
3. **Többes kijelölés**: kell-e köteg-végpont (egy commit, egy visszavonás), vagy elég a felület sorban hívó megoldása (N commit)?
4. **`trashOption: none`**: az Obsidian véglegesen töröl; a Manifold elve a visszahozhatóság. Javaslat: rendszer-Kuka + értesítés, végleges törlés soha.
5. **Nem támogatott fájlok**: rejtés vagy halványítás? A `.txt`/`.json`/`.csv` olvasható a core-nak (`vaultio.py:38`, `OLVASHATO`), de nincs nézetük — kapjanak csak olvasható szövegnézetet, mielőtt elrejtjük őket?
6. **Excluded files a fában**: az Obsidianban látszanak-e (halványan?) — ellenőrzendő, mielőtt a 13. hiány célja rögzül.
7. **Létrehozási idő** nem APFS-köteten (exFAT, hálózati): `st_birthtime` hiányában `mtime`-ra esik vissza?
8. **Bookmarks** és **Open in new window** a helyi menüben: core-plugin, illetve munkaterület-funkció — melyik paritás-jelentés gazdája?
9. **Héj-híd fájlrendszer-műveletekre** (07, 08): az útellenőrzés a héjban (a `Kuka.ellenoriz` mintája) vagy a core-ban (`utkapu`)? Javaslat: mindkettő, mint a Kukánál.
10. **`fajlNev` és a kiterjesztés**: a 14. hiány a fára szól; a gyorsváltó és a fülek is az Obsidian mintájára (név + címke) váltsanak?
