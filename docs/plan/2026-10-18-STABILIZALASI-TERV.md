# Manifold — PDF-audit és befejezési terv

Dátum: 2026-10-18. Állapot: **az audit és a terv elkészült; a termék javítása és a kiadási kapuk lezárása még hátravan**.

Ez a [Master Plan](../PLAN.md) kiegészítése. Az F1–F11 eredeti céljai megmaradnak; az alábbi S0–S6 munkaszakaszok azok integrációját, a felhasználói PDF megállapításait, a RAM-optimalizációt és a macOS 27 felé közelítő megjelenést rendezik végrehajtható sorrendbe. Az audit három párhuzamos agent vizsgálatát és a koordinátor teljes, 13 oldalas vizuális PDF-ellenőrzését egyesíti.

Megfigyelési forrás: a felhasználó `Manifold-OS_UI&infrastructural problems.pdf` című, 13 képes oldalból álló dokumentuma; nincs benne kinyerhető szövegréteg. A személyes képek a helyi forrásban maradnak, az alábbi leltár csak a termékre vonatkozó észrevételeket rögzíti.

## 1. Mi bizonyított most?

1. **A vizsgálatkor a v2 app futott.** A folyamatlista a `v2:Manifold.app/Contents/MacOS/Manifold` binárist és a v2 Python-hátterét mutatta. Ez igazolja a másik változat használatát; önmagában nem bizonyítja, hogy a v2 saját buildje elavult. A PDF v2-n tapasztalt hibáit külön ellenőrizni kell az UNI-n.
2. **Az UNI lemezen álló felülete és héja az audit kezdetén elavult volt.** A forrásujjlenyomat eltért a buildek jegyzékétől. A héj újrafordítása és ad-hoc aláírás-ellenőrzése sikerült; a frontend új buildjét jelenleg fordítási hibák állítják meg.
3. **A friss UI-regresszió nem zöld:** 3 132 tesztből 3 119 sikeres, 13 bukó; 228 fájlból 4 bukó; további 6 kezeletlen `ReferenceError`. A buildellenőrzés 5 hibát és 1 figyelmeztetést ad; a Vite-fordítás ezért el sem indul.
4. **Jelentős fejlesztés már jelen van.** Az audit kezdeti git-pillanatképe 176 módosított/nem követett tételt rögzített. Ezeket meg kell őrizni és integrálni. Nem indokolt a szerkesztő, a property-rendszer, a Model Manager vagy a csomagoló újraépítése.
5. **Nincs igazolt teljes UNI RAM-benchmark.** A meglévő cache-/élettartam-korlátok valósak, de nem bizonyítanak megfelelő teljes alkalmazásos memóriahasználatot vagy nagy-canvas válaszidőt.
6. **A korábbi F11-zárás szűkebb scope-ot igazolt.** A 01–08 checklist 94 történeti Verified sora mellett a 09–14 további 59 Open sort tartalmaz. A nyers összeg 153 sor (28 must, 125 should); ez nem deduplikált követelményszám és nem aktuális teljesítési százalék.
7. **A célzott core-kör sem zöld:** 13 modul 290 tesztjéből 284 sikeres, 6 bukó, 0 kihagyás. Négy bukás endpoint-/engedély-/dokumentációs leltárhiányt jelez (részben ugyanazt a hiányt két őr vizsgálja), kettő a sablonút és a volatilis lemezhely tesztelvárásának eltérése. Ezeket nem szabad hat önálló adatbiztonsági hibaként összegezni.

### Friss ellenőrzések és helyi bizonyíték

| Ellenőrzés | Eredmény | Helyi napló az audit könyvtárában |
|---|---|---|
| `bin/mos app test` | FAIL: 3 119 pass, 13 fail; 6 unhandled error | `ui-test.log` |
| `bin/mos app build` | FAIL: 5 error, 1 warning; nincs új `app/dist` | `ui-build.log` |
| `MOS_SETTINGS='' bash shell/build.sh` | PASS: release héj, ad-hoc aláírás és verify; a developer próba után a release változat visszaállítva | `shell-build.log`, `shell-release-final.log` |
| Developer héj + natív diagnosztika | A developer héj fordult; a `tests.test_app.HejFelulettelTeszt` 4 selftestje átment a régi UI-val. A teljes kör szándékosan megszakítva, nem teljes regressziós eredmény | `shell-developer-build.log`, `python-developer-full.log` |
| Célzott aktuális core-integráció (13 modul) | FAIL: 284 pass / 6 fail / 290 teszt; 0 skip; 81,34 s. A pontos modulok az auditösszesítőben | `core-integration.log`, `audit-summary.json` |
| Első natív Python-próba | MEGSZAKÍTOTT: a koordinátor release héjat fordított a developer selftest elé; az időtúllépések nem termékhibák | `python-full.log` |
| Korábbi sandboxos Python-próba | MEGSZAKÍTOTT: a környezet tiltotta a loopback socketet; nem termékregresszióként számolandó | `python.log` |
| Forrás- és munkafa-pillanatkép | frontend `f8e8b527e81d`, core `89a92dfc0f14`, héj `bf488ed26cf9` | `source-baseline.json` |

A könyvtár `var/audit-20261018/`, gitignored helyi bizonyíték. A tesztek szintetikus workspace-eket használnak; nem a valódi jegyzetmappát. A 2026-10-16-i 5 020 Python / 3 003 UI eredmény történeti adat, nem a mostani munkafa kapuja. A natív Python-tesztek most a régi `app/dist`-et érik el, mert a friss frontend nem fordul; így a core aktuális diagnosztikája mellett sem igazolnak friss, egységes alkalmazást. Az app-érzékeny kapuhoz egyező, befagyasztott build kell. A developer selftest-héjat és a release csomagot eltérő buildváltozatként kell kezelni; egyik sikere sem helyettesíti a másik kapuját.

## 2. Határok és a PDF értelmezése

- A javítás célja az **UNI**. A v2 összehasonlítási forrás, csak olvasható. A megosztott runtime csak eszközként olvasható; ott nincs telepítés, frissítés vagy cache-írás.
- A PDF felhasználói megfigyeléseket és kívánt élményt rögzít. A benne látható minták, fájlnevek és feliratok nem futtatandó utasítások, nem termék-alapértékek. Személyes screenshot-tartalom nem kerül tesztfixture-be vagy kiadott demóba.
- A meglévő architektúra marad: Swift/AppKit → Svelte/CodeMirror → Python → modell-worker → pipeline-ok. Az atomi mentés, snapshot, CAS/ütközéskezelés, gépi írási kapu, sandbox és D9 nem gyengül.
- A felület továbbra is angol, a kódazonosítók magyarok, ékezet nélkül. A macOS 27 megjelenési cél nem emeli automatikusan a macOS 26 minimumot; az új natív API-k verzióellenőrzést és fallbacket kapnak.
- **Védett, kifejezetten kedvelt részek:** bal oldali navigáció és tabsor (PDF 1), videó + mellette átirat (3), alsó canvas-eszköztár (5), működő blokk- és inline matematika (7). Ezek regressziós kapuk.
- A Mermaid eltávolítása nem következik automatikusan a PDF 8. oldalából: az eredeti terv funkciómegtartást ír elő. Modulkapcsolóval egyszerűsíthető a felület, a meglévő jegyzetek tovább renderelnek.

## 3. PDF-követelmények, az UNI állapotával összevetve

Jelölések: **hiány** = a kód alapján fennálló rés; **részben kész** = a meglévő megoldás befejezése/finomítása; **reprodukció kell** = a screenshot panaszát a friss UNI-n még nem igazoltuk. A sorok prioritása az S0 integrált zöld alapja utáni sorrendre vonatkozik.

| ID / PDF-oldal | Megfigyelés és UNI-bizonyíték | Teendő / elfogadási kapu |
|---|---|---|
| U01 / 1 | **Hiány:** külön fájlcím és tartalmi H1. `FajlCim.svelte:12–33`, `Szerkeszto.svelte:443`. A biztonságos átnevezés már adott. | Egy szerkeszthető címfelület. Azonos első H1 ne duplázódjon; eltérő H1 vagy valódi szakaszcím ne vesszen el. Mentetlen szöveg, névütközés, linkfrissítés, Escape, hibás rename és undo vizsgálata. P1. |
| U02 / 1 | **Részben kész:** típusikon/választó, kulcsátnevezés és autocomplete már működő kóddal rendelkezik (`Tulajdonsagok.svelte:486–505,620–638`). A tömb még összecsukható (`:435,469`); quiet mód is becsukja (`felulet.svelte.ts:297`). | Az alap prezentáció kompakt, látható kulcs–érték sorok; nincs tartalom nélküli diagnosztikai blokk. A helyes YAML LP-ben már rejtett (`elo.svelte.ts:73–81`). Ezt és a meglévő típus-/javaslatkezelést megtartani. Quiet mód nem rejti el a hibát vagy a mentetlen állapotot. P1. |
| U03 / 1–2, 4 | **Hiány:** a PDF ikonmentes fájl/mappasort és külön, jobb oldali CANVAS/MP4 jelzést mutat. Ma ikon és teljes, ellipsissel csonkolódó név van (`Fa.svelte:797–821`); `fajlNev()` csak `.md`-t vág (`fajlok.svelte.ts:31–34`). | Chevron + tiszta név + zsugorodásmentes típusjel. A `.canvas` ne a levágott cím végén legyen. Mappa, Markdown, PDF, média, canvas, base, hosszú név, szűk sáv, multi-select, rename/drag/billentyűzet kapu. A valódi út nem változik. P1. |
| U04 / 3 | **Megtartandó:** videó és oldalsó átirat. | Seek, átiratszűrés, időkód-beillesztés és lapbezárási erőforrás-felszabadítás regresszióteszt. |
| U05 / 5 | **Részben kész:** canvas-kijelölés és lebegő card-toolbar minősége (`canvas.css:66–71,431–444`). | Finom handles, skálától független érthető kijelölés, fókusz/drag elkülönítés. Az alsó toolbar elrendezése marad. P1. |
| U06 / 6 | **Hiány:** URL-szerkesztő egy lebegő input, blur-re ment (`Vaszon.svelte:1671–1695`). | Rendezett URL-popover címkével, validálással, Save/Cancel művelettel; Enter/Escape és fókuszvisszaadás, nincs véletlen blur-mentés. P1. |
| U07 / 6 | **Reprodukció/mérés kell:** nagy canvas lag. Már van 48 részletes node-os LRU és node-/él-culling (`Vaszon.svelte:150–153,236–277`). | S2 benchmark alapján optimalizálni. Nem új cullingot építeni. Lineáris szűrés, render/mount és geometria költsége külön mérendő; térbeli index csak indokolt profil alapján. P1. |
| U08 / 7 | **Igazolt ok:** root jegyzethez az üres mappanév is szerkezeti kohorsz (`core/asszisztens/mintatar.py:140–165,240–244`). | Root ne jelentsen automatikusan témaközösséget. Strukturális javaslat csak alkalmas, releváns összehasonlító mintából; root/vegyes mappa/sablon/kizárás fixture-ek. A létező asszisztens célzott javítása. P1. |
| U09 / 8 | **Igazolt eltérés:** X = `figyelmen_kivul` (`JavaslatKartya.svelte:36`), ami nem tartós elutasítás (`mintatar.py:124–135`); a döntésküldési hiba elnyelődik (`kartya.svelte.ts:104–106`). | X, No, timeout és automatikus leváltás külön szerződése; explicit bezárás cooldownnal, No tartós tiltással, sikertelen mentés visszajelzéssel/retryjal. Újranyitás/újraindítás/API-hiba teszt. P1. |
| U10 / 7 | **Reprodukció kell:** gyors scroll után a plot véletlen kijelölése. A plot saját selectionje tiltott (`plot/rajzolo.ts:239`), a sima wheel átengedett (`:439–449`). | Valódi WKWebView + trackpad reprodukció; CodeMirror/widget pointer/fókusz események követése. Scroll nem kapcsolhat szerkesztést/kijelölést; szándékos plot-pan/zoom és editor-kurzor tovább működik. P1. |
| U11 / 7 | **Új, kért felület:** plot builder. Már van parser, formátum és képlet→plot beillesztés (`plot/beiras.ts:20–47`), kézi wizard nincs. | Egyszerű függvény/tartomány/tengely űrlap, élő előnézet, érthető hiba, ugyanaz a plot kód, egy undo-lépés. Nincs új chart motor vagy AI-függőség. P2. |
| U12 / 8 | **Termékdöntés megőrzése:** Mermaid/canvas részben átfed. Mermaid lazy/strict render megvan. | Funkció marad; az alapfelület egyszerűsítését modulkapcsoló és dokumentáció oldja meg. |
| U13 / 9 | **Valószínű CSS-ok, natív ellenőrzés kell:** fehér link-completion sötét témában. `.nt-linkmenu` nincs a CodeMirror tooltip-specifikusságot kezelő csoportban (`notion.css:118–124`; `linkek/kiegeszites.ts:552–565`). | Minden CM popup computed-style vizsgálata Light/Dark/System módban. Közös tokenes surface/text/border/selected/focus; téma-váltás nyitott popup mellett, kontraszt- és billentyűzetkapu. P1. |
| U14 / 9 | **Hiány:** a canvas embed statikus SVG és open művelet (`canvas/beagyazas.ts:38–108`). | Könnyű read-only pan/zoom preview, Open gomb és jól kezelt scroll/fókusz. Nem teljes canvas-editor minden embedben; képernyőn kívül felfüggesztés és erőforráskorlát. P2, S2 RAM-kerettel. |
| U15 / 10 | **Igazolt jelenlegi változateltérés:** v2 app fut; UNI lemezes UI-buildje is elavult. | S0: ismert UNI-forrás → zöld build → egyező fingerprint → kizárólag szintetikus UNI smoke. A v2 munkamenetét nem állítjuk le automatikusan. P0. |
| U16 / 11 | **Hiány:** a trash-confirmation még egyszerű szöveg/kétgombos blokk (`Fa.svelte:674–693`). | Közös alert-dialog hierarchia, rendezett action-sor, alapértelmezett Cancel/fókusz, hosszú utak és error/retry. A macOS Trash és visszaállítási viselkedés marad. P1/P2. |
| U17 / 12 | **Polish:** összesítés, periódusválasztás, accessible diagram és szöveges tábla megvan (`StatisztikaNezet.svelte:41–118`). | Jobb chart- és tipográfiai hierarchia, skála/legend/térköz, üres állapot. Nem az aggregáció újraírása. P2. |
| U18 / 13 | **Részben javított:** külön Settings, Developer gate és rejtett process-adatok már léteznek. A Ma még a teljes ManifoldLapot ágyazza be (`ma/Ma.svelte:224–226`), a Most technikai feladattörténetet mutat (`vezerlo/Most.svelte:16,31–34`). | A napi kezdőlap közérthető állapotot és kevés fő műveletet adjon; részletek fokozatosan, technikai előzmények Developer alatt. A Settings-rendszert továbbfejleszteni. P1. |
| U19 / 13 + kérés | **Teljes felületre vonatkozó elvárás:** a PDF csak mintavétel. | S4-ben útvonal-/képernyőleltár és normál/üres/töltő/hiba/offline/nincs-modell/disabled állapotok ellenőrzése. Nem elegendő a screenshotokon szereplő nézeteket szépíteni. |
| U20 / kérés | **RAM-optimalizáció és a korábbi termékcélok teljes lezárása.** | S2 mérési program és S5–S6 integráció/kiadás. Készültség kizárólag friss teszt + natív felhasználói folyamat + szükséges mérés alapján. |

A forráshivatkozások az audit kezdeti UNI-állapotának sorai; relatív helyük az ismert alrendszeren belül értendő. Javítás után az új teszt és a változásazonosító kerül melléjük, nem az eredeti sorok vak megőrzése.

## 4. S0 — először a mostani integrációt kell működőre hozni

Ez az első végrehajtandó szakasz. Nagyobb vizuális módosítás előtt a meglévő fejlesztéseket kell stabilizálni.

| Feladat | Mai konkrét bizonyíték | Elvárt eredmény |
|---|---|---|
| Canvas task callback | `Kartya.svelte:119` hívja az `onfeladat`-ot, amely a prop típusában szerepel, de a destructuringból hiányzik. 6 teszt és 6 kezeletlen kivétel kapcsolódik hozzá. | Meglévő `feladat.ts` biztonságos mentésének bekötése; kattintás, tartós újrarender, undo/redo, stale DOM, 409 és read-only kapu. |
| Bases `list` integráció | `Eszkoztar.svelte:45` típustábla és a választók csak 3 típust ismernek; `BazisNezet.svelte:115–129` nem rendereli a létező `Lista.svelte`-t. | Valódi List nézet, típusválasztás és a meglévő panelek elérhetősége; fájl/LP/Reading/canvas út egyezzen. Nem csak a típushiba elnémítása. |
| Canvas zoom szerződés | `Vaszon.svelte:221` 4 paramétert ad a 2–3 paraméteres `mindentMutat`-nak. | Kijelölésre és teljes canvasra helyes zoom; geometria és natív kézi kapu. |
| Build-higiénia/a11y | Két unused paraméter a `graf-vaszon-segedek.ts:27,37`-ben; `ToroltVisszahozas.svelte:177` nem interaktív `<pre tabindex=0>`. | 0 error / 0 warning; a preview billentyűzetes olvashatósága/görgetése maradjon. |
| Szótár | 194 hiányzó és 1 elavult kulcs a friss `i18n-szotar` futásban. | Minden új kulcs helyes angol fordítása; 0 missing/unused, ratchet változatlanul szigorú. |
| Outline/előzmény tesztszerződés | 4 Outline elvárás/fixture-eltérés; 1 régi md-only history-szövegelvárás. | Követelményből ellenőrzött elvárás, valós adatmegőrző tesztek; ne lazuljon a teszt pusztán a zöld kedvéért. Nem igazolt adatvesztési hibaként jelentendő. |
| API/jogosultsági leltár | A törölt-előzmény 3 endpointja hiányzik a státusztáblából; 6 új endpoint a gépi-műveleti döntéstáblából (`test_utvonalak.py:614`, `test_lepes_kapu.py:86`). A friss dokuőr további 9 nem dokumentált endpointot jelez a `docs/dev/ARCHITECTURE.md`-hez. | Minden út explicit státusz-/írási döntést és pontos API-dokumentációt kapjon. Az alapból tiltó kaput nem szabad permisszív fallbackre cserélni. |
| Workspace/import tesztszerződés | Célzott reprodukció: `fresh_install/test_workspace_letrehozas.py:158` még `Napi` nevet vár a már helyesen vault-relatív `Sablonok/Napi.md` helyett. `migracio/test_obsidian_import.py:115` a teljes előnézet-dictet hasonlítja, benne az időközben változó `szabad_bajt`-tal; a `terv_hash` közben azonos. | A sablonút új szerződését a régi fixture-rel is egyeztetni; a determinisztikus tervet külön ellenőrizni a volatilis kapacitásadatoktól. A forrás bájtazonosságára vonatkozó kapu nem lazul. A célzott futás itt nem adatvesztést, hanem elváráseltérést igazolt. |
| Régi FAIL-ek egyeztetése | A korábbi `naplo.irany` hibakód már megvan (`hibauzenetek.py:498`). | Csak frissen reprodukált hibára készül javítás; régi log önmagában nem aktuális hibalista. |
| Egységes forrás/build azonosítás | `core/epites.py`, `/api/rendszer/epites` és a csomagjegyzék már létezik. A natív selftest developer héjat igényel. | Sikeres UI- és release shell-build után egyező ujjlenyomat; normál Aboutban érthető verzió/build, részletes útvonal csak Developerben. Buildváltozat jelölése és selftest-preflight, hogy release héjjal ne hosszú timeout legyen a teszt eredménye. |

**S0 zárókapu:** teljes UI-suite és warningmentes check/build; utána developer héj (`MOS_DEVELOPER_BUILD=1`) és teljes szigorú Python-/natív selftest-suite. Ezután külön release héj és release smoke/csomagellenőrzés; a release binárison nem futtatunk developer-only `--selftest`-et. `git diff --check`, friss fingerprint és egyező, szintetikus UNI WKWebView kör szükséges. A forrás és a tesztlog ugyanahhoz a checkpoint-hoz tartozzon. A meglévő felhasználói módosításokat külön nem commitoljuk áttekintés nélkül; minden saját változás körülhatárolt marad.

## 5. A végrehajtás további sorrendje

| Szakasz | Tartalom | Függőség és lezárás |
|---|---|---|
| **S0 — integráció** | A fenti build-, teszt-, fordítás- és endpoint-rések; 14 audit közös állapotmodellje. | Belépési kapu a további UX-munkához. A helyi hibás baseline nem írható felül történelmi zölddel. |
| **S1 — napi munkafelület és F11 must** | U01–03 cím/properties/fa, U13 popup, U16 dialog, U18 kezdőlap; a már megírt komponensek használatával. Az új 09–14 leltár napi használati must sorai, különösen local/unresolved graph és daily/import/nyelvi integráció, ebben a körben záródnak. | S0 után; a meglévő backend/UI bekötése diszjunkt fájlokon párhuzamosítható. Light/Dark/System, keyboard/focus, zoom, keskeny ablak; safe rename/save/undo. Új P2 felület nem előzi meg a nyitott napi must tételeket. |
| **S2 — RAM és nagy canvas** | Az alábbi mérési program; U05–07 canvas-interakció; erőforrás-élettartam. | S0 után indulhat, S1-gyel csak diszjunkt fájlokon párhuzamos. Mérés előtte/utána, azonos fixture és host; nincs bemondott százalékos javulás. |
| **S3 — asszisztens és vizuális tartalom** | U08–11 kontextus/cooldown/plot scroll + builder; U14 korlátos interaktív embed. | Működő napi szerkesztés és az S1 must-kapu után; az új P2 builder/embed az S2 költségkeretéhez igazodik. A kontextus-/ismétlődési hibajavítás külön, korábban is futhat. D9/írási kapuk sértetlenek. |
| **S4 — egységes macOS megjelenés** | Az alábbi design-szerződés; minden fő modul és állapot; U17 statistics. | A tokentervezés már S1 előtt közös, az app-szintű vizuális elfogadás S1–S3 után. Jó minőségű alapélmény csökkentett effektussal is. |
| **S5 — F11 és F6–F10 összesített igazolása** | A korábban bekötött 14 audit deduplikált sorainak végellenőrzése, megmaradó should tételek és release-rések, AI-telepítés/mérés útjai. | Nem halasztja idáig az editor must-integrációt. Minden sor saját bizonyítékkal; must 100%, should legalább 80% a hitelesített, egyesített scope-on. Tudatos halasztásnak indoka és vissza nem regresszáló viselkedése van. |
| **S6 — kiadhatóság** | Befagyasztott build, önálló runtime/Git, csomag/DMG, tiszta-fiókos telepítés, teljes restore, natív vizuális és teljesítménykör. | A Master Plan 15 pontos DoD-je végigjátszható; sem ad-hoc csomag, sem unit-teszt önmagában nem kiadásigazolás. |

Nincs előre becsült óraszám: S0 és a teljesítmény-alapmérés után adható hiteles becslés. Fázisváltáskor NAPLO-bejegyzés rögzíti a változást, teszteket, tényleges maradékot és kockázatot. A régi F1–F11 számok/célok nem íródnak át.

### Az F11 újabb részének befejezése, dupla munka nélkül

| Leltár | Ami már jelen van | Amit még végig kell kötni/igazolni |
|---|---|---|
| 09 Canvas — 15 sor | Drop/clipboard/menu/task/note-editor/target-selection kód és új tesztek; LRU/culling. | Callback és zoom javítása, minden új művelet valódi UI-ból elérhető, safe-save/undo; PDF/Bases kártya és nagy canvas natív kapui. |
| 10 Bases — 14 sor | List, sort/group/new-note/CSV/rich-cell segédek, backend-bővítések. | List és panelek renderelése/vezérlése, minden layout, beágyazott megjelenések, CSV és hibák; visual-filter igény külön specifikált, nem feltételezett készültség. |
| 11 Graph/Outline — 8 sor | Local graph/settings/context-menu és outline/filter/rearrange kód; teljesítménytesztek. | Valódi oldalpanel és követés, unresolved/tag/visibility, Outline szerződéses hibák rendezése, drag safe-write/undo. |
| 12 Templates/daily/composer — 11 sor | Dátum/idő és szomszéd napi jegyzet API, extract/merge backend, importjavítások. | A `/sablon/most`, `/naplo/szomszed`, `/komponalo` frontend használata hiányzik; Settings típusok/mezők, startup és palettaparancsok. Merge-nél linkek és byte/CAS kapu. |
| 13 Palette/hotkeys/history — 6 sor | Hotkey-import, közös billentyűforrás, mélyebb history és deleted recovery. | Route-/permission-leltár, natív menüegyezés, tényleges recovery belépési pont és több fájltípusos komponenskapu. |
| 14 Appearance — 5 sor | Fontok, auto-pair, exclusions UI/core kód és tesztek. | Test/build-integráció, kizárások minden kereső/gráf/váltó/mention útján, table-spellcheck és natív font/zoom. |

A régi 94 Verified sort sem kell újraimplementálni. Friss regresszióval és konkrét, név szerint megadott tesztekkel kell újraigazolni őket; általános „agent report” hivatkozás nem elég a végső checklisthez. A 153 nyers sor és U01–U20 átfedéseit is össze kell vonni, a forrásazonosítókat megtartva.

**Külön szemantikai rés:** a `%% … %%` kommentet az editor elrejti, de a core index maszkja még nem kezeli ugyanúgy (`core/index/maszk.py`; NAPLO komment-checkpoint és F11-zárás). Rejtett kommentből link/címke/feladat/fejezet kerülhet az indexbe. Az editor–index egyezésről explicit szerződés és közös szintetikus fixture-kapu kell; ezt a régi Verified rendering-státusz nem zárja le. A napi keresést/navigációt érintő rendezése S1, teljes újraigazolása S5 feladat.

## 6. RAM- és teljesítményprogram

### Meglévő alap, amelyet megtartunk

- Editor-state LRU: maximum 10 (`szerkesztok.svelte.ts:50,128–131`).
- Canvas: maximum 48 részletes node, viewport node-/él-culling.
- PDF: közös refcount, 30 s elengedés (`media/pdf/dokumentum.ts:10,38–74`), offscreen canvas lenullázása (`beagyazas.ts:187–205`), maximum 40 thumbnail.
- PDF.js/Mermaid/JSXGraph lazy import; worker-cache és idle ürítés (`core/modell/utemezo.py:212–227`).
- `tests/kezi/soak.py` már szintetikus, AI nélküli core-terhelést készít. A meglévő 600 MB core-RSS plafon és trend/FD/thread kapu kiinduló szerződés, nem ma elért eredmény és nem a teljes app költségkerete.

### Még megoldandó

1. **Biztonságos benchmark:** a `tests/kezi/memoria_meres.py:79–81` a konfigurált vaultot klónozza, ezért változatlanul nem futtatható. Közös szintetikus fixture-generátor és izolált install/workspace kell a core-soak és az új natív UI-mérés alá.
2. **Valódi folyamat-hozzárendelés:** shell, core, a hozzá tartozó WebContent/GPU és külön model worker. A teljes gép WebKit-folyamatainak RSS-összege nem a Manifold fogyasztása; az RSS sem egyenlő a macOS fizikai memóriaterhével.
3. **Mérési mátrix:** hideg/meleg indulás; 0/10 nyitott jegyzet; 1k/5k szintetikus fájlfa; 100/1k/5k node-os canvas külön sűrűséggel; képes/PDF-es canvas; hosszú PDF/thumb-scroll; nagy gráf; videó+átirat; lapok bezárása; 30–60 perc ismételt megnyitás/bezárás. AI nélkül és valódi modellel külön, utóbbi csak megfelelő mérőkörben.
4. **Mutatók:** phys_footprint/megfelelő macOS-memóriamérés, RSS és peak, pressure/swap, CPU/GPU, FD/szál/subscription/DOM-canvas darabszám, keystroke/pan/zoom frame time p50/p95, long task, idle visszaállás. OS-, hardver-, build- és fixture-azonosító, valamint nyers időbélyeges minták együtt kerüljenek a riportba.
5. **Hardverprofil:** a modell aktív/távol kerete ma fix 5/9 GB (`core/modell/beallitas.py:24,139–160`; `config/os.toml`). Ez nem a teljes app RAM-korlátja. 8/16/24/32+ GB-os automatikus profil és a Settings › Performance tényleges bekötése szükséges; a végleges számokat mérés és OS-tartalék alapján kell kijelölni. Az ismeretlen memórianyomás nem kezelhető bizonyítottan biztonságos állapotként: ma `betolto.py:95–98` továbbenged, a hardverlekérdezés hibája pedig 16 GB-ra esik vissza (`memoria.py:22–24`). Konzervatív, látható és tesztelt fallback kell.
6. **Csak a mért hot path javuljon:** szükség esetén geometriai cache/spatial index, mount/canvas/text-preview munka korlátozása, szüneteltetés rejtett nézeteknél, célzott invalidálás. A már működő LRU-k, lazy importok és refcountok ne kapjanak párhuzamos második rendszert.

**Elfogadás:** azonos hoston/fixture-rel ismételhető előtte/utána riport; nincs tartósan növekvő retained objektum-/listener-/FD-szám; lapbezárás és idle után stabil memória-plató; a regressziós működés/undo nem sérül. Az általános desktop interakcióhoz tervezési cél a 60 Hz körüli folyamatosság, de a konkrét fixture-nkénti p95/memóriakeretet az alapmérés után rögzítjük. Nem ígérünk mérés nélküli RAM-csökkenési százalékot.

## 7. macOS 27 irány — konkrét design-szerződés

Hivatalos alap: [Apple Materials HIG](https://developer.apple.com/design/human-interface-guidelines/materials), [Adopting Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass), [Modernize your AppKit app, WWDC26](https://developer.apple.com/videos/play/wwdc2026/289/), [macOS 27 design kits](https://developer.apple.com/news/?id=e2lxw9l1).

Az Apple a Liquid Glasst elsősorban a navigáció és a vezérlők külön rétegéhez javasolja, takarékos használattal. A tartalmi felület maradjon nyugodt és olvasható. A macOS 27 AppKit-útmutató a sidebar, toolbar, kijelölés, billentyűzetes használat és a konténerhez igazodó sarkok finomításait is tárgyalja. A következők ennek Manifoldra alkalmazott **tervezési döntései**, nem szó szerinti Apple-követelmények:

- **Tartalom az első:** editor/property/lista/table/chart stabil, olvasható felület; finom anyaghatás a navigáción/lebegő vezérlőkön. Nincs blur a jegyzet törzse vagy minden canvas-kártya mögött.
- **Egy tokenszerződés:** szemantikus surface/content/overlay/material/selection, tipó, méret, sugár, árnyék és mozgás a meglévő `tokens.css`-ben. A burgundi marad az egyetlen márkaakcentus; nem hibajelzés. Ugyanaz a dialog, popover, menu, field és action-sor minden modulban.
- **Natív héj, meglévő webes munkafelület:** AppKit standard window/toolbar/material ahol ésszerű, Svelte-ben a közös komponensek finomítása. Nem költöztetjük át az egész editort SwiftUI-ba. A CSS üveghatás nem állítható a natív Liquid Glass teljes megfelelőjének.
- **Geometria/hierarchia:** összetartozó vezérlők egy csoportban, egymásba illő sarkok, kevesebb egymásba rakott panel/keret, SF rendszerbetű, jobb cím/secondary/caption arány. A kedvelt tabsor, navigáció és canvas toolbar felismerhető marad.
- **Akadálymentesség és takarékosság:** Reduce Motion/Transparency és Increase Contrast figyelembevétele, ha szükséges a natív–webes bridge bővítésével; korrekt opaque fallback, fókusz és klaviatúra, nyitott menu közbeni témaváltás. Az effektek nélküli változat is teljes értékű.

**Vizuális kapu:** valós UNI WKWebView-képek Light/Dark/System, normál/reduced effektus, szűk/tág ablak és több zoom mellett; olvasható címkék és állapotok, nincs kilógás/átfedés/fehér popup; minden új színpár a token-/kontraszt-tesztben. Az S2 mérést az effektusok után újra kell ellenőrizni az érintett forgatókönyveken.

### App-szintű ellenőrző kör

Indító, Setup, Ma/kezdőlap, fájlfa/tabs/osztás, editor/Reading/Source, properties/links/search, Canvas, Bases, Graph/Outline, PDF, média/átirat, Cards/Quiz/Summaries, Math/plots, Code workbench, Notebook/Video import, Calendar/Reminders, Readiness/Tracker, Models/Calibration, Backup/Restore, Privacy/Health, Settings/About, Developer. Mindenhol normál, üres, betöltő, hiba/retry, offline/nincs modell és read-only/disabled állapot, ahol értelmezett. Ez tervezett leltár, nem ma végigvizsgált vizuális megfelelőség.

## 8. A korábbi termékcélok lezárása

| Terület | Meglévő munka | Nyitott, igazolandó kapu |
|---|---|---|
| F6 — AI/modellek | Manifeszt, Model Manager, hash-ellenőrzött megszakítható letöltés, threshold enforcement, saját halmaz és Trial jelzés. | Tényleges modelltelepítés/mérés megfelelő gépen és halmazon; hiányzó nyelvi halmazok, licenc és mérési küszöbök rendezése. Küszöb nélküli feladatot nem címkézünk kalibráltnak. Nem-C++ AI addig Trial, ahol nincs saját igazolt mérés. |
| F7 — Health/Privacy/Developer | Már meglevő oldalak és biztonságos javítások. | U18–19 normál módú egyszerű használat, valódi állapot, nincs technikai zaj vagy elrejtett fontos hiba. |
| F8 — import/demo/doku | Dry-run/resume/undo import, v2-import, 100 fájlos demo és 16 oldalas doku. | Jelenlegi integrációval import bájtazonosság/visszaút; 7 demo-folyam, dokumentáció egyezik az új UI-val. |
| F9 — csomagolás | Bundle/DMG-builder, relokáció, Git-builder, aláírási/notarizációs út és jegyzékellenőrzés. | Új, egyező buildből csomag, hordozható Git és igazolt pin, tiszta forrásazonosító; clean-account install/restore. A régi csomag nem jelölt RC. |
| F10 — többnyelvű kód | Adapterek és sandbox, Python/JS/TS/C/C++/Swift korábban ténylegesen gyakorolva; Java/Go/Rust mockolt. | Jelenlegi regresszió; támogatottnak ígért toolchain tényleges ellenőrzése; AI-nyelvi kalibráció, tracker-rés követése. |

A meglévő `var/build` próba-csomag jegyzéke régi `86d2d78` commitot, piszkos munkafát, hiányzó hordozható Gitet és aláírást, valamint elavult UI/héj figyelmeztetést tartalmaz. A builder már alapból tiltja az elavult buildet (`packaging/build_app.py:99–107`); a korábbi tesztkivétel nem release-megoldás. A Git-pinek még hiányoznak; a meglévő `packaging/hordozhato_git.py:30–36` szerződése szerint kell rögzíteni/verifikálni őket.

### S6 végső kiadási kapu

1. Friss core/UI/regressziós tesztek azonos checkpointból; 0 nem indokolt skip, 0 kezeletlen UI-kivétel; engedély-/adatbiztonsági kapuk zöldek.
2. Egyező production UI + release héj + core/csomagjegyzék; build csak az ismert forrást tartalmazza. `--elavult-ok` és `--git-nelkul` nélkül készült önálló csomag.
3. macOS 26 támogatási alap és macOS 27 célkör ellenőrzése; tiszta fiókban, fejlesztői runtime/CLT nélkül telepítés és újraindítás.
4. A Master Plan 15 DoD-pontja végigjátszva, köztük safe-save, import, helyi AI próbával/méréssel, PDF, sandbox, backup és teljes restore médiával együtt. Külső tesztelői kör.
5. Függőségek online auditja a megfelelő körben, licenc- és szállíthatósági ellenőrzés; a helyi offline teszt nem helyettesíti ezt.
6. Natív vizuális/trackpad/keyboard/zoom kör és S2 RAM/soak riport; nincs screenshot alapján bemondott teljesítményjavulás.
7. Ad-hoc helyi jelölt és Developer ID/notarizált nyilvános kiadás külön státusz. A szükséges identitás és tanúsítvány valódi külső feltétel; nincs „kész” jelölés a hiányában. RC tag csak a releváns kapuk után.

## 9. Hatékony agent-munka és átadás

- A koordinátor kezeli az integrációt, a közös tokeneket/típusokat, a checklistet és a végső kaput. A jelenlegi audit már három diszjunkt agent-vizsgálatot használt: UI/PDF, runtime/RAM, készültség/integráció.
- Következő végrehajtáskor legfeljebb három, fájltulajdon szerint elkülönített munkasáv: **canvas**, **Bases + daily/composer**, **közös UI/i18n + assistant**. A pontos kiosztás mindig az adott szakaszhoz igazodik; közös `App.svelte`, tokenek, nyelvi index és API-szerződések módosítása koordinált.
- Egy fájlt egyszerre egy agent szerkeszt. A tesztet/javítást a saját érintett körén futtatja; a teljes UI/core-suite a befagyasztott integráción egyszer fut, újra csak új változás vagy feloldatlan hiba indokolja.
- Újraírás előtt keresés a jelenlegi munkafában és meglévő tesztekben. Minden követelmény státusza: **kész és frissen igazolt / megvan, nincs bekötve / hibás / hiányzik / natív reprodukcióra vár / külső feltétel**. Régi log és általános Verified címke nem helyettesíti ezt.
- Minden lezárt munkaszakasz: pontos diff, friss log és fingerprint, NAPLO, követelményhez rendelt bizonyíték és megmaradó kockázat. A valódi vaulton vagy a futó v2-n nem végzünk automatikus QA-t.

**Következő konkrét munka:** S0 — a jelenlegi integrációs hibák javítása, a Bases/list bekötésével és a safe-write kapuk megtartásával; utána egyező UNI-buildből natív szintetikus ellenőrzés. A teljes alkalmazás elkészültét ez a tervezési dokumentum nem állítja.
