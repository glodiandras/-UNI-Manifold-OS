# S0 — integrációs javítások és ellenőrzés

Dátum: 2026-10-18. Állapot: **lezárt integrációs checkpoint**. Ez a [stabilizálási terv](2026-10-18-STABILIZALASI-TERV.md) első végrehajtási szakasza; nem az egész termék vagy az F11 lezárása.

## Cél és megőrzött munka

Az auditkor jelen levő, jelentős commitolatlan F11-fejlesztést integráljuk. A Canvas, Bases, Graph/Outline, hotkeys/history/recovery, font/exclusion és daily/template/composer meglévő kódja megmarad. A szakasz a jelenlegi build-/regressziós akadályokat és a review-ban igazolt adatmegőrzési réseket javítja; a későbbi UI-/RAM-tervet nem helyettesíti.

A munkát három agent és a koordinátor végezte, fájlonként elkülönített feladatokkal. A v2, a közösen használt runtime és a valódi vault csak olvasható forrás maradt; a tesztek szintetikus adatokat használnak. A munkafának külön ága van: `codex/stabilization-s0`.

## Elkészült javítások

| Terület | Változás | Bizonyíték |
|---|---|---|
| Canvas task | A hiányzó callback átadásra kerül; a kártya feladatjelölője a meglévő biztonságos mentési úton ír. | `canvas-feladat.svelte.test.ts`: tartós mentés, újrarajzolás, undo/redo, stale kártya, 409 és readonly. A korábbi 6 kezeletlen kivétel megszűnt a célzott körben. |
| Canvas zoom | A geometriai helper explicit nagyítási plafont fogad: teljes vászon legfeljebb 1×, kijelölés legfeljebb 2×, globális korlátokkal. | `canvas-muveletek.test.ts`, új `canvas-zoom.svelte.test.ts`: node/edge-végpontok, üres kijelölés, kamera megjegyzése, nincs tartalmi fájlírás. |
| Outline | A tesztelvárások a teljes ősláncot, ékezetfüggetlen részszóegyezést és helyes no-op határpozíciókat kérik számon. | `f11-graf-vazlat.test.ts`: az eredeti 4 hibás elvárás helyett a szerződés ellenőrzése; CRLF-es részfa-mozgatás egyetlen undo/redo lépéssel. Az implementációt nem kellett emiatt átírni. |
| Bases List | A már megírt List komponens a közös nézetkeretben ténylegesen renderelődik; a létrehozási/típusmenü mind a négy típust ismeri. | Új `s0-bazis-integracio.svelte.test.ts`: file-like, Live Preview és Reading forrásszerződések; a többi layout regressziója. |
| Bases vezérlés | A meglévő rendezés-, csoport- és új-jegyzet panelek elérhetők. CSV/TSV/Markdown másolás működik, hibával és újrapróbával. List-csoportok nézetenként összecsukhatók. | 19 új integrációs teszt, a teljes célzott Bases-kör 170 tesztje. A CSV-másolás nem állítja magáról, hogy natív fájlexport. |
| Bases async mentés | Új nézet csak sikeres mentés után válik aktívvá. A számolás alap-szövege és readonly/konfliktus kapuja az aszinkron válasz után újra ellenőrződik. | Új `s0-bazis-verseny.svelte.test.ts`: 8 deferred-response eset; a javítás előtt 7 bukott. Külső szerkesztés, no-op, readonly, konfliktus és sikeres újrapróba. |
| Törölt jegyzet előnézete | Billentyűzetről olvasható readonly szövegmező; literal tartalom. A későn érkező korábbi előnézet nem írja felül az új kiválasztást. | Új `s0-torolt-visszahozas.svelte.test.ts`: nyers HTML nem fut, előnézetből nincs mentés, stale válasz eldobása. |
| Recovery életciklus | Ütközés nem ír felül fájlt; új néven újrapróbálható. Bezárt/leváltott párbeszéd késői eredménye nem zár be más overlayt és nem navigál; siker/hiba továbbra is visszajelzést ad. | Ugyanott: pontos kérésparaméterek, tiltott eredeti hely, retry, Undo, késői siker és tartós hibajelzés. |
| Fordítás | A hiányzó 194 kulcs és az új integrációs feliratok angol szótárbejegyzést kaptak; a régi Markdown-only history-kulcs kikerült. | `i18n-szotar`, `i18n-ratchet`; paraméterek és többes számú párok változatlanul szigorú ellenőrzése. |
| API/engedélyleltár | Három history út státusztáblája, hat új POST explicit gépi tiltása és kilenc endpoint dokumentációja elkészült. | `test_utvonalak`, `test_lepes_kapu`, `test_dokumentacio`, `biztonsag.test_gepi_kapu`. Production gépi engedély nem bővült. |
| Workspace/import fixture | A vault-relatív napi sablonút a tesztben is érvényesül. A terv determinisztikája és a változó szabad lemezhely külön ellenőrzött. | Rögzített kapacitás mellett teljes dict-egyezés; eltérő kapacitás mellett az összes szemantikus mező, a tervhash és a forrás bájtazonossága megmarad. |
| C31/F2 kompatibilitási fixture | A C31 próbavault a megőrzött pure `v2_vaz` helpert hívja. A F2-konfig golden továbbra is minden régi értéket ellenőriz; kilenc új F11 levél külön név-, típus- és alapérték-ellenőrzést kap. | A generált v2 napi váz bájtazonos. A history-lapozás, automatikus párok, két betűcsalád és kizárási lista pontos értékekkel szerepel; nincs új wildcard kivétel vagy production config-változás. |
| Build-változat | A natív jegyzék és a Swift JS-rekord explicit `hej_valtozat` értéket kap. A release selftest még NSApplication létrehozása előtt érthető hibával leáll. | `test_cx_epites`, új `test_s0_build_valtozat`: mindkét compile flag, helper-prioritás és normál belépési ág szintetikus Swift app/helper stubokkal; JSON/Swift egyezés és változatlan hash-szemantika. A valódi kiadási bináris külön smoke-kaput kap. |
| Csomagoló | Csak explicit kiadási héj csomagolható; developer, hiányzó és hibás változat nem kerül át stagingbe. A változat a befagyasztott jegyzékben megmarad. | A stale-build tesztkivétel sem kerülheti meg; szintetikus csomagolótesztek és frissített bundle-fixture. |

## Tesztek és a tesztkör megbízhatósága

- Az i18n őr már nem keresi végig a Python-forrást azokról a kulcsokról, amelyek UI-használata eleve igazolt. A ténylegesen nem használt/core-only kulcsok kapuja megmaradt; timeout nem lett megemelve.
- A Reader célzott-frissítési tesztje ellenőrzött időzítőkkel befejezi az inicializálást, mielőtt kérésalapot mér. Két külön embed célt vizsgál: más fájl változása nem kér újra, a megváltozott cél pontosan egyszer frissül; az érintetlen DOM, scroll és hostszöveg megmarad. Nincs tetszőleges alvás vagy termékkód-változás.
- A kis-DMG teszt sandboxban `Device not configured` hibát kapott; ugyanaz a szintetikus teszt emelt körben 1/1 sikeres. Nem került új skip a kapuba.
- Az első teljes Python-kör 5286 tesztnél egy setuphibát és egy paritási bukást talált (`python-full.log`, 1666,406 s). Ezek a fenti C31/F2 tesztintegrációs eltérések; a termékforrás nem változott a javításukkor. A 73 kihagyásból 0 indokolatlan. A két javítás után 146/146 kapcsolódó teszt, majd a megismételt teljes kör is sikeres; az első futás nem szerepel zöld kapuként.
- A teljes suite-ok a befagyasztott termékforrást és friss UI-buildet ellenőrzik; a Python/natív kör developer héjjal futott. Ezután külön release rebuild, aláírás-ellenőrzés és normál indulási/kilépési próba is sikeres.

| Kapu | Állapot | Helyi bizonyíték (`var/s0-20261018/`) |
|---|---|---|
| Teljes UI, 4 worker, kihagyás nélkül | PASS: 232 fájl, 3169/3169 teszt | `ui-verified.log` |
| Svelte/TypeScript + production build | PASS; 0 Svelte error / warning, Vite build sikeres | `ui-build.log` |
| Teljes szigorú Python + natív kör | PASS: 5292 eset; 5219 sikeres, 73 indokolt kihagyás, 0 hiba/bukás; 1575,356 s | `python-verified.log`; első futás: `python-full.log` |
| Lezáró dokumentációs kapuk | PASS: 46/46, 0 kihagyás | `docs-closure.log` |
| Developer héj build + aláírás | PASS | `shell-developer.log` |
| Release héj + fail-fast + aláírás | PASS: friss `kiadasi`, ad-hoc aláírás; mindkét selftest-argumentum korai 2-es kilépés | `shell-release.log`, `release-smoke.json` |
| Normál release indulás/kilépés | PASS: saját shell/core PID-kapcsolat, hitelesített API/GUI WebSocket, bájtra egyező HTML/JS, rendes kilépés és takarítás | `release-smoke.log`, `release-smoke.json` |
| Csomagoló build-/változat-preflight | PASS: friss kiadási héj/UI, stale-build kivétel nélkül; hordozható Git ellenőrzése kihagyva, új termékbundle nem készült | `release-package-preflight.json` |
| Hash/whitespace, source preservation | PASS: a termékhash-ek egyeznek, teszt-/buildforrás megőrizve; csak a lezáró dokumentumok külön rögzített változásai | `source-frozen.json`, `verification.json` |

A Vite a már meglévő JSXGraph JessieCode közvetlen `eval` használatára és nagy dependency-chunkokra figyelmeztet. Ezek nem Svelte-diagnosztikák, és nincsenek elhallgattatva. A runtime CSP/offline kapu külön fut; a dependency/renderköltség vizsgálata az S2 része. A sikeres build nem jelenti, hogy ezek a későbbi feladatok lezárultak.

A normál release-próba külső, szintetikus launcher-megfigyelővel a valódi bináris normál indulási útját ellenőrzi. A GUI saját hitelesített WebSocket-hello üzenetét figyeli meg; nincs release ready-hook vagy teljes vizuális audit állítva. A kilépés pontos PID/executable alapján történt, a próba jegyzetének bájtjai megmaradtak, a saját core leállt és a fixture törlődött. A csomagoló preflight hordozható Git nélküli tesztmódja a hiányzó hordozható Git kapuját nem zárja le.

A lezárt termékforrás SHA-256 ujjlenyomatai:

| Rész | SHA-256 |
|---|---|
| UI (`felulet`) | `b72994f5afa3d2c3d94e399d08644f9c7bb1c89520909cc74cd7a68d347293f1` |
| Python/modulok (`mag`) | `8612a7f33c06b19e3b4e7c809f519a6432e704fddb3d22fe5f4d73309b485971` |
| Natív héj (`hej`) | `f3d474594c9336335a3ada1d753b7a7a38eda318d52da407b6ab16a010f568ca` |

## Még nyitott munka

- S1: a PDF napi editor- és navigációs kérései, a többi F11 must-integráció, komment/index szemantika, egyszerűbb kezdőlap és dialógusok.
- S2: teljes natív RAM/soak baseline és hardverhez igazított modellkeret; a friss UI-build még nem RAM-mérés.
- Bases: natív CSV-fájlexport, Kanban oszlopműveletek, a nem-List layoutok csoportösszecsukása és a vizuális filterfa nem lett késznek jelölve.
- A canvas trackpad/pointer és az összes nézet részletes natív vizuális auditja későbbi kapu; a teljes natív editor-selftest nem helyettesíti az egész UX-auditot.
- Valódi modellkalibráció, független hordozható Git/runtime, clean-account install, teljes média-restore és a nyilvános kiadás aláírása/notarizációja a korábbi terv szerint megmarad.
- A konfigurált hosted CI még nem igazolt futás. A CONTRIBUTING build-/tesztsorrendje és CI-leírása pontosítva; a SECURITY privát kapcsolati címe kiadás előtt kitöltendő.

## Git átadás

A szakasz a korábbi commitolatlan fejlesztésekkel együtt kap ellenőrzött helyi integrációs commitot. A kezdeti HTTPS-hozzáférés és a módosítás nélküli próbapush 403-at adott. A felhasználó ezt követően kifejezetten magára vállalta a push-t; további távoli írási próbát nem végzünk. Az átadás a helyi ágat és commitazonosítót tartalmazza, nem állít távoli publikálást.
