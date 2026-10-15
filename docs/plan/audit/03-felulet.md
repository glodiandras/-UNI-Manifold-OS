# 03 – Felület (frontend) termékesítési audit

Forrás: `/Volumes/Work/Manifold-OS v2/app` (Svelte 5 runes + TypeScript + Vite 8, CodeMirror 6). READ-ONLY audit; a `core/` és `shell/` csak a kapcsolódási pontok ellenőrzéséhez volt olvasva. Mérés időpontja: dist build `91aa03a9…` (2026-10-14).

Méretek: `src/` = 114 `.svelte` (24 798 sor) + 260 `.ts` (33 200 sor, ebből 44 `*.svelte.ts` runes-modul) + 10 `.css`; `tests/` = 152 `*.test.ts`. Hivatkozások `fájl:sor` alakban, az `app/src` alól (kivéve ahol más gyökér szerepel).

---

## 0. Vezetői összkép (a termék-célhoz mérve)

| Termék-cél | Mai állapot | Súly |
|---|---|---|
| Választható felületi nyelv | NINCS szövegtár. ~2 355 magyar string-literál/töredék, 211 fájlban, mindenhol beégetve; `hu-HU` 31 helyen; `<html lang="hu">`; core-üzenetek magyarul, kód nélkül | nagy, de mechanikus |
| Több felhasználó | NINCS felhasználó/profil fogalom. 1 vault (`os.toml: vault = "{work}/Manifold"`), 1 `felulet.json`, 1 core/vault (egypéldányos zár) | architekturális (nem csak UI) |
| First-run onboarding | NINCS. Az egyetlen „első indulás” logika a csend módé (`lib/elrendezes/felulet.svelte.ts:134`). Munkaterület-választás nincs: a vault útja csak konfig/env | nagy |
| Model Manager | Csak olvasó „Modellek” szakasz (router-tábla, HF-modellnevek, keretek). Letöltés/telepítés/teszt UI nincs (CLI: `bin/mos models pull`) | nagy |
| Settings-rendszer | Nincs egységes. Szétszórt: ⌘P-parancsok (téma, csend, rendszerértesítés), 2 kapcsoló (Asszisztens/Tracker), `felulet.json` | közepes |
| Privacy Center | Nincs. Alapanyag: Tracker kapcsoló + `Adatkezeles.svelte` (törlés/export), Használat nézet | közepes |
| Health oldal | Nincs külön oldal. Alapanyag: Rendszer szakasz, build-állapot, Állapotsor, core `/health`, `/api/vezerlo/rendszer`, `doctor.py` | közepes |
| Developer Mode | Nincs kapcsoló. Csak 2 „Fejlesztő: …” parancs (`szerkeszto/index.ts:212,222`) + a normál nézetben látható technikai részletek | közepes |
| Empty state-ek / user-readable hibák | Részben: sok helyen van egysoros üres szöveg; hiba = cím (felületi) + NYERS core-üzenet | közepes |
| Design-rendszer | Erős: token-őr teszt, kontraszt-teszt, `m-gomb`/`m-jelolo` minták; de nincs kapcsoló/mező/kártya/szegmens/üres-állapot minta | jó alap |

---

## 1. Komponens-térkép

### 1.1 Belépés, port, API-titok, héj-kapcsolat

| Lépés | Hol | Mi történik |
|---|---|---|
| Indítás (Swift héj) | `shell/Sources/AppController.swift:107-170` | A héj indítja a Python core-t, vár a kézfogásra (port + API-titok; időkorlát 25 s, `:420`). Közben a natív `ToltesJelzo` mutatja az „A Manifold indul…” feliratot (`:780`) – ez NEM a `app/src/hej/`, hanem Swift NSView. |
| Port | `AppController.swift:136` | A lapot `http://127.0.0.1:<port>/` címről tölti (`webView.load`, `:170`). A felület **soha nem kapja meg a portot külön**: minden hívás relatív URL (`kerdez('/api/…')`, `lib/core/api.ts:105`), a WS a `location.host`-ból (`lib/core/ws.svelte.ts:23`). Egy origin, a core szolgálja ki a `dist/`-et (`os.toml: app_dist`). |
| API-titok | `AppController.swift:161-165` → `lib/core/titok.ts` | A héj `WKUserScript`-tel (`atDocumentStart`, csak főkeret) injektálja `window.__MOS_TITOK__`-t. `main.ts:15` `titokBetolt()` beolvassa, törli a globálisból, érvényesíti (`/^[A-Za-z0-9_.-]{16,128}$/`, `titok.ts:7`). Dev-tartalék: `#titok=<t>` a címben, olvasás után `history.replaceState` törli. Node-ban: `MOS_API_TITOK`. Titok nélkül minden API 403. |
| Titok használata | `lib/core/api.ts:112`, `ws.svelte.ts:63` | HTTP: `X-Manifold: <titok>` fejléc. WS: alprotokoll `mos.<titok>` (a böngésző WS nem küldhet fejlécet). Média (`<img>/<video>`): tokenes útvonal `/media/<token>/…` (`lib/vault/linkek.svelte.ts:93`, a token az `/api/allapot`-ból). |
| `window.manifold` | `lib/core/hid.ts:66-99` (telepít: `App.svelte:124`) | NEM a port/titok hordozója, hanem a **héj → lap** híd: `parancs(id)`, `fokusz()`, `naptarEngedely(v)`, `mentes()` (kilépéskor: leáll-réteg → felület-állapot + minden jegyzet mentése → tracker puffer, ≤2 s → jelentés), `mentetlen()`, `leallAllapot(sz)`, `ertesitesKattintas(azon)`, `hejUzenet({szint,cim,szoveg})`. |
| Lap → héj | `lib/core/hej.ts:21-27` | `webkit.messageHandlers.manifold.postMessage(...)`: `kesz`, `tema`, `megnyit` (külső URL), `naptar-engedely`, `naptar-allapot`, `kenyszeritett-kilepes`, `ertesites` (macOS Értesítési központ), `helyi-menu`. Böngészőben csendben no-op (`hejbenFut()`). Képesség-bejelentés: `window.__MOS_HEJ__` (`hej.ts:39`). A héj origin-ellenőrzést végez (`AppController.swift:251-254`). |
| Belépési pont | `main.ts` → `App.svelte` | `main.ts`: titok → `betolt()` (`GET /api/felulet/allapot`, ≤2,5 s, `felulet.svelte.ts:248`) → `new Felulet(allapot)` → `megnyitNezet('manifold')` (indító áttekintő fül, `main.ts:19`) → téma → `mount(App)` → `data-kesz=1` + `hejnek({tipus:'kesz'})` (a héj ekkor mutatja az ablakot). Ha a core nem válaszolt: alapállapot, a mentő zárolt (`Mento.zarol`), a WS `hello` pótolja (`betoltesPotol`, `App.svelte:111`). |
| `App.svelte` | `App.svelte:44-144` | Gyökér: `CoreKapcsolat` (WS) + `VaultFajlok` + `kornyezetBeallit` (Svelte context: `felulet`, `fajlok`, `kapcsolat`, `lib/kornyezet.ts`); 16 modul-telepítő (`szerkesztoTelepit`, `bazisTelepit`, `kvizTelepit`, `grafTelepit`, `maTelepit`, `dolgozatTelepit`, `canvasTelepit`, `mediaTelepit`, `kodTelepit`, `trackerTelepit`, `matekTelepit`, `kartyaTelepit`, `osszefoglalasTelepit`, `vezerloTelepit`, `naptarTelepit`, `alapParancsok`); nézet-regisztráció (`nezetek.regisztral`); tartós állapot mentő (500 ms). Renderel: `<Hej />`. |
| `hej/` terminológia | – | Figyelem: a `app/src/hej/` a **Svelte „héj” (chrome)**: oldalsáv, fülsor, jobb panel, állapotsor. A Swift `Manifold.app` is „héj”. Az onboarding szempontjából a Swift-oldali „A Manifold indul…” és a Svelte-oldali `hej/Hej.svelte` két külön réteg. |

Core-hívás-minta: minden modul a közös `kerdez<T>()`-t (`lib/core/api.ts:105`; időkorlát, `ApiHiba`, `X-Manifold`) vagy `kerdezEtag` (feltételes GET, gráf) használja; push: `CoreKapcsolat.figyel(tipus, fn)` WS-események (`hello`, `vault_valtozas`, `index`, `kapcsolok`, `vault_elerheto`, `indulasi_uzenet`, `kimaradt`, …).

### 1.2 Almappák (1 sor/mappa)

| Mappa | Felelősség · fő komponensek | Core API (előtag) |
|---|---|---|
| `src/` (gyökér) | `main.ts` belépés; `App.svelte` gyökér; `alapParancsok.ts` (≈31 alapparancs: paletta, váltó, nézet, fül, panel, fókusz, téma, értesítés); `node-fs.d.ts` | `/api/felulet` (main) |
| `atfedes/` | Modális átfedések: `Paletta` (⌘P), `Valto` (⌘O), `KeresoAblak`, `Atnevezes`, `Kiemelt` | `/api/vault` (kereső, átnevezés) |
| `bazis/` | Bases/adatbázis-nézetek (`.base`): `Tabla`, `Kanban`, `Kartyak`, `Cella*`, `SzuroPanel`, `BeallitasPanel`; `modell.svelte.ts` | `/api/vault/bazis`, `/api/pillanat` |
| `canvas/` | JSON Canvas (`.canvas`) szerkesztő: `Vaszon`, `Kartya`, `Eszkoztar`, `CanvasFul` | `/api/vault/fajl`, `/uj` |
| `dolgozat/` | Dolgozat-felkészültség oldal: témánkénti becslés, napi terv, önkalibráció | `/api/felkeszultseg` |
| `graf/` | Gráfnézet: `Graf`, `GrafVezerlo` (szűrők, erők) | `/api/vault/graf`, `graf-meta` |
| `hej/` (+`kapcsolatok/`, `nezetek/`, `vezerlo/`) | A héj-chrome: `Hej` rács, `Oldalsav`, `Fa` (fájlfa, 628 sor), `Cimkek`, `Fulsor`, `JobbPanel`, `Allapotsor`, `Ertesitesek`, `ErtesitesElozmeny`, `LeallVedelem`, `ManifoldLap`. `kapcsolatok/`: Visszahivatkozások, Említések, Higiénia, Hasonlók, Előzmények (+diff). `nezetek/`: `UjFul`, `Helyorzo`. `vezerlo/`: a „Manifold” oldal szakaszai (Most, Bevitel, Kérdezz, Tanulás, Statisztika, Használat, Naptár, Asszisztens-kapcsolók/-tanult/-statisztika, Modellek, Rendszer, TeljesMentes) | `/api/vault/fa,kuka,mappa,uj,cimkek,kereses`, `/api/higienia`, `/api/feladatok`, `/api/mentes`, `/api/sablon` |
| `kartya/` | Kártya-pakli (FSRS), „Mai ismétlés” | `/api/kartya`, `/api/feladatok` |
| `kod/` | C++ munkafelület: `KodFul`, `KodEredmeny`, `KodAI`, `UjFeladat` | `/api/cpp/*`, `/api/vault/fajl` |
| `kviz/` | Kvíz-blokk (kitölthető beágyazás) | `/api/kviz`, `/api/feladatok` |
| `lib/` (gyökér) | `kornyezet.ts` (Svelte context) | – |
| `lib/asszisztens/` | Javaslat-kártya (`JavaslatKartya`), adat-tár, megjelenítés | `/api/asszisztens/*`, `/api/higienia`, `/api/ma` |
| `lib/core/` | `api.ts` (HTTP + `ApiHiba` + magyar státuszüzenetek), `ws.svelte.ts` (WS), `titok.ts`, `hej.ts` (lap→héj), `hid.ts` (`window.manifold`), `epites.ts`, `frissitoSor.ts`, `keresSor.ts`, `leall.svelte.ts`, `aktivitas.ts` | `/api/aktivitas`, `/api/rendszer/epites` |
| `lib/design/` | `kontraszt.ts`: WCAG-kontraszt + token-elemző (tesztek használják) | – |
| `lib/elrendezes/` | `felulet.svelte.ts` (tartós állapot + `Mento`), `munkaterulet.svelte.ts` (fülek/panelek), `nezetek.svelte.ts` (nézet-regiszter), `csend.svelte.ts` (csend mód), `tema.ts` | `/api/felulet/allapot` |
| `lib/ertesites/` | Értesítés-szolgáltatás (`ertesitesek.ertesit`), macOS rendszerértesítés-híd (`rendszer.ts`) | – (héj-üzenet) |
| `lib/fokusz/` | Fókuszcsapda, régiók (F6), billentyű-hatókör | – |
| `lib/fuzet/` | Füzet (kézírás-fotó) parancsok és feladat | `/api/fuzet`, `/api/feladatok` |
| `lib/graf/` | Gráf-fizika (Worker), rajzoló, modell, beállítások | `/api/vault/graf*` |
| `lib/ikon/` | Lucide-ikonok tree-shake-elve (`ikonok.ts`, 140 sor), `Ikon.svelte`, fájl-ikonok | – |
| `lib/kereses/` | Fuzzy, vault-keresés, hasonló, „Kérdezz a vaulttól” | `/api/kereses`, `/api/vault/kereses` |
| `lib/naptar/` | Naptár/emlékeztető állapot, magyar mondat-formázás (`megjelenites.ts`), `hid` | `/api/naptar`, `/api/emlekezteto` |
| `lib/parancsok/` | `regiszter.ts` (parancsregiszter), `billentyuk.ts` (akkordok, ⌘⇧ megjelenítés), `kezelo.ts` (globális billentyűkezelő) | – |
| `lib/tracker/` | Tracker kliens, adatkezelés (`Adatkezeles.svelte`), gépelés-mérés, grafikon | `/api/tracker/*` |
| `lib/ui/` | Közös UI: `Atfedes`, `Billentyu`, `IkonGomb`, `JegyzetIkon`, `ListaValaszto` | – |
| `lib/vault/` | `VaultFajlok` (index), címkék, gráfadat, ikonok, linkek, előzmény, média-token | `/api/vault/*`, `/api/allapot` |
| `lib/vezerlo/` | Vezérlő API (`api.ts`), feladatsor, kapcsolók, rendszer-állapot, build-állapot, videó-bevitel | `/api/feladatok`, `/api/vezerlo/*`, `/api/video/*`, `/api/pillanat` |
| `ma/` | „Ma”/„Manifold” kezdőoldal (nézet-típus `manifold`): dolgozat, naptár, napi jegyzet, feladatok, kártyák, asszisztens-javaslatok; sablon-választó | `/api/ma`, `/api/felkeszultseg/keret`, `/api/naplo/ma`, `/api/sablon` |
| `matek/` | Levezetés-ellenőrzés (margójel), „Megoldás” | `/api/matek`, `/api/feladatok` |
| `media/` (+`pdf/`) | PDF-olvasó (pdf.js, `PdfFul`, kiemelés, `magyarL10n.ts`), lejátszó (`Lejatszo`), átirat | `/api/media/atirat`, `/api/pdf/*` |
| `naptar/` | Naptár-értesítések telepítése | `/api/naptar` |
| `osszefoglalas/` | Összefoglaló, külső AI kontextus-csomag (`KulsoAi`) | `/api/osszefoglalas/*` |
| `styles/` | `tokens.css` (243 sor), `alap.css` (260), `minta.css` (91) | – |
| `szerkeszto/` (+10 alsó) | CodeMirror 6 szerkesztő: `Szerkeszto`, `Olvaso`, dokumentum-állapot, Live Preview (`elo/`), Notion-szerű blokkok + `/` menü (`notion/`), linkek/átnevezés (`linkek/`), tulajdonság-panel (`tulajdonsagok/`), renderelők (KaTeX, Mermaid, JSXGraph plot), asszisztens-folytatás, beágyazás | `/api/vault/jegyzet,fajl,import,sema,tulajdonsagok`, `/api/pillanat`, `/api/keplet-ocr`, `/api/grafikon` |
| `tracker/` | Statisztika- és Használat-nézet fülek | `/api/tracker/*` (lib/tracker) |
| `vezerlo/` | `index.ts`: a vezérlő telepítése (feladatsor-figyelés, feladat vége értesítés, 4+2 parancs), `helyorzok.ts` (üres lista) | `/api/feladatok`, `/api/vezerlo` |

---

## 2. i18n-helyzet

### 2.1 Van-e szövegtár?
**Nincs.** Semmilyen `i18n`/`t()`/`locale`/gettext réteg. Az egyetlen „nyelvi” elemek:

| Elem | Hol | Megjegyzés |
|---|---|---|
| `<html lang="hu">`, `<meta … >` | `index.html:2` | fix |
| `Intl.*('hu-HU')` / `localeCompare(…,'hu')` | 9 fájl, 31 hely: `ma/datum.ts:27`, `hej/Allapotsor.svelte:21`, `hej/ErtesitesElozmeny.svelte:11`, `hej/nezetek/Helyorzo.svelte:14`, `hej/Cimkek.svelte:58`, `kod/KodEredmeny.svelte`, `dolgozat/szoveg.ts`, `lib/tracker/megjelenites.ts`, `bazis/ertek.ts` … | locale-paraméterezhető |
| Kézzel írt hónapnevek | `lib/naptar/megjelenites.ts:80` (`'jan.','febr.',…`) | nem Intl |
| pdf.js saját magyar l10n | `media/pdf/magyarL10n.ts` (55 string) | külön szótár, teszt őrzi a lefedettséget (`magyar-l10n.test.ts`) |
| Core `[sablon] nyelv` (`hu`/`en`) | `core/ma.py:225`, `core/sablon.py:16,75` | **a Ma-oldal dátum-feliratát a core a vault-beállítás nyelvén formázza** (`felirat`), vagyis a core már ismer nyelvet, de ez vault-konfig, nem felhasználói beállítás |
| Swift héj | `shell/Sources/*.swift`: ~308 magyar string (AppController 94, Eletciklus 72, Naptar 71, Ertesites 24, HelyiMenu 19, Kuka 18…); `Info.plist` `CFBundleDevelopmentRegion=hu`, 5 `NS…UsageDescription` | natív menü, párbeszédek, engedély-szövegek: `.lproj` kell |

### 2.2 Számlálás (grep/tokenizáló; kommentek és `*.test.ts` nélkül)
Módszer: saját JS/Svelte tokenizáló (`/private/tmp/.../audit/tmp/szamol.py`): minden `'…'`, `"…"`, `` `…` `` literál, a Svelte-sablon szövegcsomópontjai, a statikus attribútumok (`aria-label`, `title`, `placeholder`, `cimke`…) és a `{…}` kifejezések stringjei, amelyek **ékezetes magyar betűt** (áéíóöőúüű) tartalmaznak. Egy sablon-literál 1 egység; a sablon-szövegcsomópont a `{…}` kifejezések között külön töredék.

| Mutató | Érték |
|---|---|
| Fájl, amelyben van ékezetes UI-string | **211** (114 `.svelte` + 260 `.ts` közül) |
| Literál/töredék összesen | **2 355** (ebből string-literál 1 291, sablon-szövegcsomópont 570, statikus attribútum 248, sablon-literál 246) |
| Egyedi szöveg | 1 951 |
| Szavak (ékezetes töredékekben) | ≈ 8 500 |
| Ékezet nélküli magyar UI-szöveg (pl. „Nincs találat", „Mind", „Parancsok", „Kanban") | becslés +250–350 (a heurisztika 137-et talált biztosan; a valós szám a „csak szó” címkékkel együtt ~300) |
| **Becsült teljes fordítandó mennyiség** | **≈ 2 600–2 700 kulcs/töredék, ≈ 11 000 szó** (a paraméteres 246 sablon-literál ~200 ICU-szerű kulcsra olvad; az egy szavas 637 töredék jelentős része gyakori, ismétlődő címke: Mégse, Mentés, …) |
| Kulcsos/paraméteres (`${…}`) | 246 (többes szám és szórend problémák: „N jegyzet · M fájl", „Kész: {név}") |
| Egy szavas címke | 637 |
| Swift (külön) | ≈ 308 |
| Core (Python, külön) | 2 545 ékezetes string-literál a `core/`-ban; ebből ~190 `raise`/hiba-hívás (a felhasználónak megjelenő rész) |

Nem-UI jellegű magyar string (nem fordítandó, de a számlálás tartalmazza; az egyedi tétel ~5–8 %-a): vault-tulajdonságnevek és mappanevek (`Média`, `Source`, `NN`…), parancs-kategória *azonosítók*, a „Callout" típusnevek, a `/` menü által *a jegyzetbe beírt* sablonszövegek (`szerkeszto/notion/sablonok.ts`: a menü-címke UI, a beszúrt Markdown felhasználói adat).

### 2.3 Top 20 fájl (ékezetes literál/töredék)

| # | Fájl | Db | Egyedi | Szó |
|---|---|---|---|---|
| 1 | `dolgozat/Dolgozat.svelte` | 82 | 81 | 439 |
| 2 | `alapParancsok.ts` | 65 | 49 | 146 |
| 3 | `kviz/KvizBlokk.svelte` | 55 | 52 | 209 |
| 4 | `media/pdf/magyarL10n.ts` | 55 | 48 | 115 |
| 5 | `szerkeszto/index.ts` | 51 | 39 | 159 |
| 6 | `hej/vezerlo/Bevitel.svelte` | 47 | 46 | 318 |
| 7 | `lib/naptar/megjelenites.ts` | 46 | 46 | 179 |
| 8 | `atfedes/KeresoAblak.svelte` | 42 | 41 | 134 |
| 9 | `szerkeszto/notion/sablonok.ts` | 41 | 37 | 128 |
| 10 | `media/pdf/PdfFul.svelte` | 40 | 35 | 130 |
| 11 | `kod/KodAI.svelte` | 38 | 34 | 127 |
| 12 | `hej/Fa.svelte` | 37 | 35 | 100 |
| 13 | `szerkeszto/tulajdonsagok/Tulajdonsagok.svelte` | 37 | 29 | 74 |
| 14 | `media/Lejatszo.svelte` | 31 | 28 | 90 |
| 15 | `hej/vezerlo/NaptarSzakasz.svelte` | 30 | 30 | 77 |
| 16 | `kod/KodEredmeny.svelte` | 30 | 28 | 65 |
| 17 | `canvas/Eszkoztar.svelte` | 29 | 26 | 58 |
| 18 | `osszefoglalas/parancsok.ts` | 29 | 29 | 205 |
| 19 | `tracker/HasznalatNezet.svelte` | 28 | 27 | 145 |
| 20 | `graf/GrafVezerlo.svelte` | 27 | 27 | 104 |

A top 20 összesen ≈ 840 töredék = a teljes ~36 %-a. Mappánként: `hej/vezerlo` 271, `media` 167, `kod` 158, `bazis` 144, `canvas` 124, `dolgozat` 111, `szerkeszto/notion` 99, `ma` 89, `atfedes` 84, `osszefoglalas` 78, `kviz` 66, `alapParancsok.ts` 65, `szerkeszto/renderelok` 60, `tracker` 56, `szerkeszto/index.ts` 51, `lib/naptar` 50, `szerkeszto/tulajdonsagok` 50, `graf` 50, `hej/kapcsolatok` 50.

### 2.4 Külön kategóriák

| Kategória | Mennyiség | Hol |
|---|---|---|
| **Parancsregiszter címkék** | 84 azonosított `id`+`nev` pár (83 ékezetes) + ~100 `kategoria:` előfordulás (25 egyedi kategória: Szerkesztő, Jegyzet, Manifold, C++, Fül, Nézet, Fájl, Panel, Napló, Füzet, Keresés, Értesítések, Navigáció, Fókusz, Canvas, Tanulás, Gráf, **Fejlesztő**, Asszisztens, Téma, Általános, Gyorsváltó, Grafikon, Média, hiba). 19 fájlban: `alapParancsok.ts` 31, `szerkeszto/index.ts` 12, `kod/index.ts` 6, `ma`/`vezerlo`/`lib/fuzet`/`osszefoglalas` 4–4 … Dinamikus: `${i+1}. fül` (`alapParancsok.ts:135`), `${cim} bekapcsolása` (`vezerlo/index.ts:99`). | `lib/parancsok/regiszter.ts:27-31` (`Parancs.nev/kategoria`); a paletta szűrése a nevekre épül (`atfedes/Paletta.svelte`), a héj helyi menüje a regiszterből olvas (`vezerlo/helyorzok.ts:19`) |
| **Hibaüzenetek** | ~225 hiba-jellegű töredék (198 egyedi) a statikus szövegekben; kód-oldalról: 58 `szint: 'hiba'` értesítés, 187 `ertesitesek.ertesit(` hívás, 88 `role="alert"`, 53 `throw new`, 5 `new ApiHiba`, ~81 `{hiba}` sablon-kötés | `lib/core/api.ts:32-66` (kapcsolat-hiba, 11 státuszüzenet, nyers hálózati hibák regexei), `ma/naplo.ts` (7), `szerkeszto/dokumentum/dokumentum.svelte.ts` (7), `kod/futas.svelte.ts`, `matek/index.ts` |
| **Billentyű-súgó** | **Önálló billentyű-súgó nincs.** A gyorsbillentyű a parancs-regiszterben él (`billentyu: 'Mod+P'`), megjelenítése: `lib/ui/Billentyu.svelte` (macOS-glifek ⌘⇧⌥, nyelvfüggetlen) a Palettában, `IkonGomb` tooltip + `aria-keyshortcuts`-ban, és az `hej/nezetek/UjFul.svelte:8-14` 5 soros „Nincs megnyitott jegyzet" listájában. Nyelvfüggő rész csak a parancsnév és az `ariaAlak` | `lib/parancsok/billentyuk.ts:60-125` |
| **Naptár/dátum** | 46 + 10 töredék + 9 `Intl('hu-HU')` | `lib/naptar/megjelenites.ts`, `ma/datum.ts`, `lib/tracker/megjelenites.ts` |
| **Beágyazott könyvtár-szöveg** | pdf.js nézet: 55 | `media/pdf/magyarL10n.ts` |

### 2.5 Honnan jön a szöveg: felület vs. core

| Forrás | Példák | Felületi kezelés | i18n-hatás |
|---|---|---|---|
| **Felület** (a fenti ~2 355) | címkék, gombok, üres állapotok, `ertesit({cim})`, `aria-label` | beégetve | `t()`-vel kiváltható |
| **Core: HTTP-hiba törzs** `{"hiba": "<magyar mondat>", …adat}` | `core/server.py:755,759` (`HttpError`, `atnevezes.Hiba`, `vaultio.NemElerheto`); az `ApiHiba.message` a nyers core-szöveg (`api.ts:85-90`) | **nyersen jelenik meg**: ~119 `e.message`, ~103 `String(e)`, 42 `hibaSzoveg(`; mintázat: `ertesit({cim: <felületi magyar>, szoveg: <nyers core-üzenet>})` (pl. `hej/Fa.svelte:321`, `kod/muveletek.ts:122`, `matek/index.ts:75`) | core-kód + paraméter kell |
| **Core: szakasz-hibák a `/api/ma` válaszban** | `{hiba: "kisbetűs mondat"}` szakaszonként; a Ma-oldal nagybetűsít (`ma/Ma.svelte:53`) | nyers + stílus-javítás | kód kell |
| **Core: feladatsor** | `Feladat.cim/osszegzes/figyelmeztetes[]/lepesek[].cim/hiba` (`lib/vezerlo/tipusok.ts:7-27`), napló-sorok (`FeladatReszlet`), `Kész: ${nev}` (`vezerlo/index.ts:30-34`) | a `cim`-et a core adja | feladat-típus-kulcs + paraméter |
| **Core: higiénia/tulajdonság-észrevételek** | `uzenet` + `reszlet.kod` (`core/higienia.py:328,365`, `core/tulajdonsagok.py:310`) – **már van `kod`** | `.uzenet` 22 sablon-kötés / 11 fájl | `kod`-ra áttérhető |
| **Core: WS-események** | `indulasi_uzenet.uzenetek[]` (nyers mondatok, `szerkeszto/index.ts:246-250`), `vault_elerheto` (felületi szöveg) | részben nyers | kód kell |
| **Core: egyéb mezők** | `felirat` (dátum, a core formázza), `indok` (router-döntés, 4 hely), `megjegyzes` (2), `reszlet` | nyers | kód/paraméter |
| **Swift héj** | natív menü, `NSAlert`, `uzenetJs` → `window.manifold.hejUzenet({cim,szoveg})` | héj-oldali | `.lproj` + nyelv-üzenet a laptól |
| **Python core szövegei** | `lepes_kapu`, `video_api`, `cpp_*`… (kb. 190 raise) | – | érintett, de külön audit (core) |

### 2.6 Javasolt i18n-megközelítés (legkevesebb regresszió)

1. **Kulcs = a mai magyar szöveg, `t('…')` burkoló.** `app/src/lib/i18n/index.ts`: `t(kulcs: string, param?: Record<string, string|number>)`. A `hu` nyelv *identitás* (a kulcs maga a szöveg) → a felület viselkedése és az 1 706 szöveg-asszert **változatlan** marad. Új nyelv = `lib/i18n/en.json` (`{"Mentés": "Save", "{n} jegyzet": "{n} notes"}`); hiányzó kulcs → a magyar szöveg (nincs üres felület, fokozatos fordítás).
2. **Reaktív nyelv:** `nyelv = $state('hu')` egy `i18n.svelte.ts`-ben; a `t()` ezt olvassa → a Svelte magától újrarajzol. Nyelv tárolása: `felulet.json` `nyelv` kulcs (a `FeluletMentes` bővítése, mint a `tema`: `felulet.svelte.ts:27,221`; `beallit()` validál), első indulásnál `navigator.language` → `hu|en`.
3. **Paraméteres és többes szám:** a 246 sablon-literál `` `${n} jegyzet · ${m} fájl` `` → `t('{n} jegyzet · {m} fájl', {n, m})`; többes: `t.plural('{n} jegyzet', n)` (CLDR-szabályok az `Intl.PluralRules`-ból; a magyar nem ragoz számnév után, az angol igen → külön `_one/_other` kulcsok csak az `en.json`-ban).
4. **Szám/dátum:** a 31 `'hu-HU'` → `i18n.locale`; a kézi hónaptömb (`naptar/megjelenites.ts:80`) → `Intl.DateTimeFormat`. `<html lang>` állítása futásidőben (képernyőolvasó, orvosi/helyesírás: a szerkesztő spellcheck is nyelvfüggő).
5. **Parancsregiszter:** `nev` a regisztráció helyén `t('…')`-vel (fordítás a *paletta-renderkor*, nem a regisztráláskor, hogy nyelvváltáskor frissüljön: `nev` lehet `() => string`, vagy a Paletta hív `t(p.nev)`-et). A parancs-`id` marad a stabil kulcs (tracker, legutóbbiak is ezt tárolják – `felulet.legutobbiParancsok`). A `kategoria` szöveg ugyanígy.
6. **Core-üzenetek: hibakód + paraméterek.** A core hibatörzs bővítése visszafelé kompatibilisen: `{"hiba": "<magyar fallback>", "kod": "vault.nem_elerheto", "param": {"vault": "…"}}`. Az `ApiHiba` már hordoz `adat`-ot (`api.ts:6-14`): `ApiHiba.kod`, `.param`; új `hibaUzenet(e)` = `t('hiba.' + kod, param)` ha van fordítás, különben `e.message` (a mai magyar nyers szöveg). Prioritás: a 11 státusz-üzenet (`api.ts:46`), vault-elérhetőség, mentés, feladat-`hiba`/`cim`, `/api/ma` szakasz-hibák, higiénia-`kod` (már van). A core felé a kérés-nyelv: `X-Manifold-Nyelv` fejléc vagy a `kerdez()` automatikusan; a core csak a *fallback* szöveget kell hogy adja.
7. **Swift:** `Localizable.strings` + `Info.plist` `CFBundleLocalizations`; a lap egy új `{tipus:'nyelv', ertek}` üzenetet küld (a `tema` mintájára, `hej.ts:12`), a héj újraépíti a menüt.
8. **Regresszió-őrök:** (a) `tests/i18n.test.ts`, „token-őr” mintára (`tokenek.test.ts`): új ékezetes literál `.svelte`/`.ts`-ben, `t(` nélkül → bukik (a mai állomány ratchet-lista, csak csökkenhet); (b) `en.json` kulcsai ⊆ a forrásban talált `t('…')` kulcsoknak (elavult kulcs-ellenőrzés); (c) param-egyezés (`{n}` mindkét nyelven); (d) a tesztek `setupFiles`-ban `nyelv = 'hu'` fixen (ne `navigator.language`-ből!).
9. **Bevezetési sorrend** (kockázat szerint): ① infrastruktúra + nyelvválasztó + `felulet.json`; ② új felületek (onboarding, settings, Model Manager, Health, Privacy) eleve `t()`-vel; ③ közös szolgáltatás-szövegek (`lib/core/api.ts`, `ertesitesek` hívások címei, parancs-nevek: ~400 töredék, a leglátványosabb); ④ a nagy fájlok (top 20); ⑤ mechanikus codemod a maradékra (a tokenizáló már megvan a kinyeréshez); ⑥ core-kódok.

Miért nem „kulcs = azonosító” (`settings.theme.dark`): ~2 600 kulcs kézi kitalálása + minden teszt-asszert átírása (1 706 sor), nagyobb regresszió-kockázat; a magyar-kulcs módszer ütközése csak azonos magyar szó eltérő angol jelentésénél van (pl. „Fájl" menü vs. „Fájl" típus) → ott környezeti kulcs: `t('Törlés', {ctx:'gomb'})` / `'Törlés|gomb'`.

---

## 3. Meglévő „beállítás-szerű” felületek

### 3.1 A „Manifold” oldal (`ma/Ma.svelte`, nézet-típus `manifold`)

A „Manifold” oldal = a **Ma** nézet (`ma/Ma.svelte`, induló fül: `main.ts:19`). Szakaszai: Tanulás a héten (`StatisztikaSzakasz` + `TanulasiKeret`), Következő dolgozat, A nap, Napi jegyzet, Feladatok ma, Kártyák, Asszisztens-javaslatok, és legalul egy `<details>`: **„Rendszer és beállítások”** (`ma/Ma.svelte:222-225`; állapot: `felulet.manifoldRendszer`, `felulet.svelte.ts:74`), benne a `hej/ManifoldLap.svelte` accordion-szakaszai:

| Szakasz (ManifoldLap.svelte sor) | Tartalom | Beállítás-szerű? | Technikai részlet, ami a normál felhasználónak látszik |
|---|---|---|---|
| Most (`:36`) | futó/lezárt feladatok (feladatsor), leállítás, napló, változások, visszavonás | nem | feladat-típus-azonosítók, „kör", commit-SHA-k, `legacy` forrás |
| Bevitel (`:39`) | videólink-letöltés, bejárás, bevitel, fotó/füzet behúzás | részben | `staging`, `mp4/m4v/mov/mkv/webm/avi`, „célmappa (téma)", yt-dlp |
| Kérdezz a vaulttól (`:42`) | vault-kérdés | nem | „Próba: a modell erre a feladatra nem kalibrált" (`Kerdezz.svelte:58`) |
| Tanulás (`:45`) | „Mai ismétlés" | nem | – |
| Statisztika (`:48`), Használat (`:51`) | tracker-adatok; parancshasználat | adat | „a V2.1 rangsorához", parancs-azonosítók (`id`-k), p95 ms (`tracker/HasznalatNezet.svelte:39`) |
| Naptár és emlékeztetők (`:54`) | engedély-állapot, kategória-választás, szinkron, ütközések | **igen** (engedély, kategória) | `Rendszerbeállítások › Adatvédelem…`, állapotkódok |
| Asszisztens (`:57`) | **2 kapcsoló** (Asszisztens, Tracker: `hej/vezerlo/Kapcsolok.svelte`) + Tanult + Statisztika | **igen** (ez az egyetlen valódi kapcsoló-UI) | tanult szokás-minták, elutasítási arányok |
| Modellek (`:61`) | **router-tábla** feladatonként | nem (csak olvas) | lásd lent |
| Rendszer (`:64`) | memória, modellzár, betöltött modell, SSD, utolsó mentés, build-állapot; „Mentés most"; **TeljesMentes** (külső lemez) | részben (mentés) | lásd lent |

A Tracker és a Mentés **nem önálló szakasz**: a Tracker kapcsoló az Asszisztens szakaszban, a Mentés a Rendszerben. A szakaszok nyitott/zárt állapota tartós (`felulet.vezerlo.nyitott`, `ManifoldLap.svelte:22-23`).

### 3.2 Technikai részletek a normál nézetben (Developer Mode jelöltek)

| Részlet | Hol | Mit mutat |
|---|---|---|
| **Modellnevek** | `hej/vezerlo/Modellek.svelte:80` `{s.modell}`; `Rendszer.svelte:78` `r.worker.modell`, `zarSzoveg` (`repo`, `pid`, `:44-49`) | HF-repo azonosítók, worker/pid |
| **Router-tábla** | `Modellek.svelte:67-95` | pontszám (3 tizedes), „munka/távol keret", „aranyhalmaz-verzió", ✓ kalibrált, „(elavult)"; a belső feladat-kulcsok (`ocr_kezi`, `fuzet_fejezet`, `matek_cas`, `rerank`… 14 db) emberi címre fordítva (`:12-27`, ez jó példa) |
| **K/D/C/T-tételek** | „(D9)" `Modellek.svelte:92`; „C20–C26-ban érkeznek" `tracker/HasznalatNezet.svelte:94`; „a C22 után", „C23b-vel érkezik" `dolgozat/Dolgozat.svelte:331,344`; „a … chatben készül el" `vezerlo/index.ts:114` | fejlesztési ciklus-azonosítók a felhasználói szövegben |
| **Env/CLI-nevek** | `bin/mos runtime fetch / install / models pull` (`TeljesMentes.svelte:44`), `bin/mos felkeszultseg kalibral --rogzit`, `os.toml` (`dolgozat/Dolgozat.svelte:424`), `var/venv`, `runtime/` | parancssor-utasítás a felhasználónak |
| **Útvonalak** | `placeholder="/Volumes/Mentés/Manifold"` (`TeljesMentes.svelte:48`), `Rendszer.svelte:88` SSD-kötetnév, vault-relatív utak mindenhol | – |
| **Build-állapot** | `Rendszer.svelte:58-66` „Mag: <hash>, felulet: …, (elavult)" | forrás-ujjlenyomat |
| **Memória/worker** | `Rendszer.svelte:70-72` „core: … worker: …", „memóriaőr-szünet" | RSS, szünetek |
| **Mentés-hibák** | `Rendszer.svelte:94-98` `tároló/elem: üzenet` nyers | – |
| **Gombok/állapotok** | `hej/Allapotsor.svelte:74` „Nincs kapcsolat a core-ral" (a „core" szó), `ms`/`p95` a Használatban | „core", „worker", „staging", „index" |

### 3.3 A `felulet.json` (`var/state/felulet.json`)

Szerkezete: `FeluletMentes` (`lib/elrendezes/felulet.svelte.ts:22-46`), `verzio:1`, `kenyelmiVerzio:1`. Írás: `PUT /api/felulet/allapot` (`Mento`, 500 ms késleltetés, visszalépő újrapróba 2→30 s, zár ha a betöltés elbukott); a core csak „JSON-objektum, ≤ 256 KiB" ellenőrzést végez (`core/felulet.py`), **a tartalom a felületé** → bővíthető (új kulcs: `nyelv`, `beallitasok`, `onboarding`, `fejlesztoMod`, `modellKezelo`) a core módosítása nélkül.

| Mentett beállítás | Kulcs | UI-vezérlő ma |
|---|---|---|
| Téma (rendszer/világos/sötét) | `tema` | **csak ⌘P**: „A rendszer szerint / Világos / Sötét" (`alapParancsok.ts:147-149`) |
| Csend mód | `csend.{be,bemutatva}` | **csak ⌘P** „Csend mód be/ki" (`alapParancsok.ts:111`) |
| Rendszerértesítések | `rendszerErtesites` | **csak ⌘P** „Rendszerértesítések be/ki" (`:152-159`) |
| Szerkesztő mód (élő/forrás) | `szerkesztoMod` | szerkesztő-gomb |
| Oldalsáv/jobb panel szélesség, nyitottság, nézet, panel-szakaszok | `oldalsav`, `jobbPanel` | húzás, gombok |
| Tulajdonság-panel, kereső-kivágások | `tulajdonsagok`, `kereso` | gombok / ⌘G |
| Gráf-felülírások | `graf` (`lib/graf/beallitasok.ts`) | GrafVezerlo |
| Vezérlő-szakaszok | `vezerlo.nyitott` | accordion |
| Munkaterület (fülek, osztások), legutóbbi fájlok (≤50), parancsok (≤20), fa nyitott mappái (≤2000) | `munkaterulet`, `legutobbiFajlok`, … | automatikus |

Core-oldali kapcsolók és konfig (nem `felulet.json`): `kapcsolok.json` (Asszisztens, Tracker; `GET/PUT /api/vezerlo/kapcsolok`, `lib/vezerlo/kapcsolok.svelte.ts` – optimista váltás + WS `kapcsolok` esemény + `hello`-ra újratöltés: **jó minta**), `os.toml` (utak, port, memória-keretek), vault-szintű `graph.json`, `[sablon] nyelv`, `[media] nyelvek`.

### 3.4 Ami Settings-rendszer alapja lehet

* **Tárolás:** `felulet.json` (felhasználói/UI) + `kapcsolok.json`-minta (core-ot érintő): a kettős út már működik és tesztelt (`felulet-betoltes.test.ts`, `kapcsolok` tesztek). A `Felulet` osztály `beallit()`/`sorosit()` párja a séma-validálás helye.
* **Kapcsoló-vezérlő:** `hej/vezerlo/Kapcsolok.svelte` (`role="switch"` checkbox + leírás + hiba-sor) – kiemelhető közös `Kapcsolo.svelte`-vé.
* **Accordion:** `hej/Szakasz.svelte` (+ tartós nyitottság).
* **Kereshetőség/parancsok:** a ⌘P-parancsok (`tema.*`, `hej.csend`, `ertesites.rendszer`) a Settings-oldal sorainak 1:1 megfelelői – a regiszter-azonosítók maradhatnak (a Settings sor `regiszter.futtat(id)`-t hív, a parancs marad).
* **Hiányzik:** önálló Settings nézet (nézet-regisztráció: `nezetek.regisztral({id, illeszkedik, komponens})`, `App.svelte:54-55` mintájára, fül-típus mint a `manifold`/`dolgozat`), kategória-navigáció, kereső, „visszaállítás alapra", érték-séma-verzió/migráció (`verzio`/`kenyelmiVerzio` csak 1), per-felhasználó profil.
* **Több felhasználó:** a mai felépítés nem támogatja: 1 vault (`config/os.toml`), 1 state-mappa (`var/state`), a core egypéldányos zára vaulton (`CoreProcess.swift:6`), a héj `WKWebsiteDataStore.nonPersistent()` (nincs böngészőtár). Per-user = külön `state`/`var` + külön vault-út, a core-nak indulási paraméterként (`MOS_VAULT`, `MOS_STATE`); a felület csak profil-választót és `felulet.json` per profilt kapna.

---

## 4. Empty state és hiba-UX

### 4.1 Hibák megjelenése

| Réteg | Hol | Formátum |
|---|---|---|
| **Értesítés-szolgáltatás** (egyetlen központi hely) | `lib/ertesites/ertesites.svelte.ts` (141 sor), kirajzol: `hej/Ertesitesek.svelte` (jobb alsó; max. 3 látszik, `MAX_LATHATO`; hiba `role="alert"`, többi `role="status"`, `:23`), előzmény: `hej/ErtesitesElozmeny.svelte` (max. 50) | `{szint: info/siker/figyelmeztetes/hiba, cim, szoveg?, muvelet?, idotartam, kulcs?, rendszer?}`; hiba/művelet: 10 s, `0` = tartós (vault eltűnése, `szerkeszto/index.ts:284-294`); azonos kulcs frissül, azonos tartalom `darab++`; hiba → macOS Értesítési központ, ha háttérben (`rendszer.ts:36`) |
| **Inline hibasor** | 88 `role="alert"` (`.hiba`, `.uj-hiba`, `.betoltes-hiba`…); `alap.css:55-70`: minden `[role=alert]` hibasor ikonnal (`--ikon-hiba`) + szóval, sosem csak színnel | szöveg: `A <dolog> nem érhető el: {nyers hiba}` (pl. `Rendszer.svelte:48`, `Modellek.svelte:57`) |
| **Állapotsor** | `hej/Allapotsor.svelte:74` „Nincs kapcsolat a core-ral, újrapróbálás…", `Index: hiba` (`title` = nyers `index.hiba`); csendben is megjelenik (`csend.svelte.ts` `allapotsorMondanivalo`) | – |
| **„Leáll" réteg** | `hej/LeallVedelem.svelte`, `lib/core/leall.svelte.ts` (`window.manifold.leallAllapot`) | modális védelem kilépéskor |
| **Natív (Swift)** | `NSAlert` „A Manifold nem indul", „A core nem válaszol" (`AppController.swift:404-448`) | magyar, részben nyers stderr-farok |

### 4.2 Formátum: nyers core-üzenet?

**Igen, kétrétegű:** a *cím* felületi magyar mondat („A mentés nem indult el"), a *szöveg* a **nyers core-hiba** (`e instanceof Error ? e.message : String(e)`: 119+103 előfordulás). Az `api.ts` egyetlen szűrője: a böngészőmotor nyers hálózati hibáit (`Load failed`, `Failed to fetch`…) cseréli `KAPCSOLAT_HIBA`-ra (`api.ts:32,69-72`) és 11 státuszkódhoz ad magyar szöveget (`:46-58`); minden egyéb a core mondata marad (`valaszHiba`, `:85`). Következmény: a core-mondatok sorsa = a felület nyelve; technikai tartalom (útvonal, pid, Python-kivétel) kiszivároghat (`Rendszer.svelte:94-98`: `tároló: üzenet`; `kod/muveletek.ts:97` `r.uzenet`). Nincs: hibakód, „mit tehetek" lépés, „Részletek/Másolás" (kivéve a feladat-értesítés „Részletek" gombja, `vezerlo/index.ts:22`), hibajelentés/diagnosztika-export, Developer Mode-ban nyers, másképp magyarázó réteg.

### 4.3 Empty state-ek

| Képernyő / eset | Van-e | Szöveg / hely |
|---|---|---|
| Üres vault (fájlfa) | minimális | „A vault üres." (`hej/Fa.svelte:429`) – nincs teendő-gomb („Új jegyzet", „Importálás") |
| Üres gráf | minimális | „A vaultban még nincs fájl." (`graf/Graf.svelte:462`) |
| Nincs megnyitott jegyzet (fül) | **jó** | `UjFul.svelte`: 5 teendő gyorsbillentyűvel |
| Üres keresés | van | „Nincs találat: „…”." (`atfedes/KeresoAblak.svelte:264`), paletta „Nincs ilyen parancs" |
| Üres címkék | van | „A vaultban nincs címke." (`hej/Cimkek.svelte:176`) |
| Jobb panel: nincs fájl / említés / hasonló / higiénia | van | `Nincs megnyitott fájl`, `Nincs linkeletlen említés`, `Nincs hasonló jegyzet`, `Nincs észrevétel…` |
| Ma-oldal szakaszok | van, de adatot feltételez | „Nincs közelgő határidő a naptárban", „Nincs esemény", „Még nincs [napi jegyzet]", „Nincs mára esedékes feladat" (`ma/Ma.svelte:114,137,156,184`); a *Kártyák* szakasz üres állapota hiányzik (csak `—`, ha nincs adat, `:196`) |
| Modell nélküli funkció | részben | `kod/KodAI.svelte:86` „nincs kalibrált modell"; `Modellek.svelte:92` „Nincs kalibrált modell: élesben nem fut (D9)"; Kérdezz: „Próba: a modell erre a feladatra nem kalibrált" – technikai, nincs „Modell letöltése" CTA |
| Statisztika / Használat | van | „Még nincs adat", „Még nincs rögzített parancshasználat", „Még nem írt gép a vaultba (a funkciók a C20–C26-ban érkeznek)" |
| Naptár | van | „Még nincs beolvasott naptár" |
| Bevitel | van | „Nincs várakozó videó a stagingben" |
| Dolgozat / felkészültség | részben | `Dolgozat.svelte:140,162,210,251,327`: „Nincs közelgő dolgozat…", „Nincs téma: a felkészülési jegyzet `Source` és `NN` mezője nem hivatkozik jegyzetre" (szakmai) |
| Vault nem elérhető | tartós értesítés | `szerkeszto/index.ts:284` (WS `vault_elerheto`) – mentés szünetel, nincs külön „Válassz másik munkaterületet" |
| Nincs `dist` / core hiba | natív | Swift `NSAlert` |

Mintázat: az üres állapotok **egysoros, passzív szövegek** (CSS `.ures`), nincs közös `UresAllapot` komponens (ikon + cím + magyarázat + elsődleges művelet).

### 4.4 Melyik képernyő feltételezi az adatokat

| Képernyő | Feltételezés | Üres vault/új felhasználó esetén |
|---|---|---|
| **Ma** (`ma/Ma.svelte`) | naptár-integráció (EventKit), `Source`/`NN`-t használó „felkészülési jegyzet", napi jegyzet sablon, feladatok `📅`-határidővel, kártya-pakli | szekciónként „Nincs…" szövegek – összetett, nem vezet be |
| **Dolgozat / felkészültség** (`dolgozat/`) | naptári *dolgozat* események + jegyzet `Source`/`NN` frontmatter + mért kártya/kvíz eredmény | „Nincs közelgő dolgozat", „Mért tudás nélkül nincs szám" |
| **Statisztika / Használat** (`tracker/`, `hej/vezerlo/StatisztikaSzakasz`) | napokig gyűlt tracker-adat | „Még nincs adat" |
| **Gráf** (`graf/`) | kapcsolt jegyzetek | „A vaultban még nincs fájl" |
| **Kártyák/Kvíz/Összefoglaló/Matek** | kísérőjegyzet, modell | akcióhoz kötött; modell nélkül hibaértesítés |
| **Tanulás a héten** (`TanulasiKeret`, `StatisztikaSzakasz`) | tracker be van kapcsolva | a Ma-oldal tetején mindig megjelenik |

---

## 5. Onboarding-hiány

**Mi történik ma, ha a core nem talál vaultot?** A vault útja *csak konfig/env* (`config/os.toml: vault = "{work}/Manifold"`, `MOS_VAULT`) – a felületnek nincs vault-választója. A core a vaultot induláskor feloldja; ha a kötet/mappa nincs meg, a kérések `503 {vault_elerheto:false, lemez_hiba:true}`-t adnak (`core/vaultio.py:97,186`, `server.py:759`), a felület: `VaultFajlok.hiba` (`lib/vault/fajlok.svelte.ts:79`), a fa „A vault üres." / „A fájllista töltődik…", tartós „A vault nem érhető el" értesítés (`szerkeszto/index.ts:284`, a szöveg egy *kidobott SSD-re* szól: „Az SSD vagy a kötet eltűnt…"). Hiányzik a Manifold-gyökér: Swift `fail("A Manifold-OS gyökere nem található… Az SSD nincs csatlakoztatva?")` (`AppController.swift:92`). Másik példány: „Ugyanezen a vaulton már fut egy Manifold" (`:384`). **Nincs** „hozz létre / nyiss meg munkaterületet" lépés.

**Van-e „első indítás" állapot?** Csak töredékek:
* `felulet.svelte.ts:132-138`: ha a `csend` kulcs hiányzik → „az első C38-as indulás": csend-alapállapot egyszer; `csend.bemutatva` jelzi, hogy a bemutató értesítés már megjelent. **Ez a meglévő first-run-minta** (hiányzó kulcs = első indulás; a séma-migráció a `kenyelmiVerzio`-val).
* `BETOLTES_IDOKORLAT`/`betoltve=false`: a core-hibás induláskor a mentő zárol (adatvesztés-védelem, **onboarding közben is ugyanígy kell**).
* Induló fül: a „Manifold" (Ma) áttekintő (`main.ts:19`).
* `HELYORZOK` üres (`vezerlo/helyorzok.ts:18`).
* Nincs: Welcome, nyelv-/téma-választás, preset, modell-letöltés, adatvédelmi tájékoztató, jogosultság-lépések (naptár: csak a Naptár szakaszban, kérésre).

**A természetes hely(ek):**

| Réteg | Hely | Miért |
|---|---|---|
| **A) Swift, core előtt** (Welcome → workspace létrehozás/megnyitás) | `AppController.applicationDidFinishLaunching` (`:61`) és a `ToltesJelzo` helyén (`:780`, jelenleg „A Manifold indul…") – a `RootLocator`/`CoreProcess.start` előtt | a vault-út a core *indításakor* dől el (`config.py`/`MOS_VAULT`; az egypéldányos zár is vault-alapú) → a munkaterület-választás natív `NSOpenPanel`/új mappa létrehozás, utána `MOS_VAULT`-tal indul a core. Itt a felület még nem létezik, nincs core-hívás. (Alternatíva: a core „vault nélküli mód” + `POST /api/munkaterulet/…` + futásidejű vault-váltás – nagyobb core-beavatkozás.) |
| **B) Svelte, core után** (nyelv, preset, modellek, adatvédelem, jogosultságok) | `main.ts:19` helyett/előtt: ha `felulet.onboarding?.kesz !== true` → teljes képernyős `Onboarding` réteg a `<Hej/>` helyett (`App.svelte:144`) vagy induló nézet-fül (`nezetek.regisztral`, mint `UjFul`); a `kesz` jelet (`main.ts:25`) továbbra is a mount után kell küldeni (különben a héj töltésjelzője marad) | a nyelv, a téma, a `kapcsolok` (Tracker/Asszisztens – Privacy), a preset és a modell-letöltés mind a felületen/core-API-n át megy; az állapot a `felulet.json`-ban (új kulcs `onboarding`) |
| **C) Utólagos belépés** | ⌘P parancs „Üdvözlő / Beállítási varázsló", Ma-oldal „Rendszer és beállítások" | újrafuttatás |

Megjegyzés a „core nélkül" állapotra: `main.ts:16` blokkol a `betolt()`-ra (≤2,5 s), mielőtt mountolna, vagyis a felület *mindig* core-ral indul; a Swift héj sosem tölti be a lapot core nélkül (`AppController.swift:170` a kézfogás után). Tehát a „core nélküli Welcome" kizárólag natív lehet.

---

## 6. Design-rendszer: mit kell kötelezően tokenből használni

Források: `styles/tokens.css` (243 sor: 1 forrás minden nyers értékhez), `styles/alap.css` (reset, tipográfia, fókusz, hibasor-ikon, MANIFOLD betűjel, csend-blokk `:234-260`), `styles/minta.css` (`m-gomb` kitöltött/`.semleges`/`.link`/`.suru`, `m-jelolo`), `lib/design/kontraszt.ts`, dokumentáció `docs/DESIGN.md` (359 sor), `docs/C39-DESIGN-SYSTEM-FRISSITES.md`. Tesztek: `tests/tokenek.test.ts` („token-őr", C39), `tests/kontraszt.test.ts`, `tests/csend.test.ts`. (Megjegyzés: a fájl neve `tokens.css`, nem `tokenek.css`.)

**Kötelező szabályok (a token-őr automatikusan bukik rajtuk; az új .svelte `<style>` és `.css` mind vizsgálva van, kivétel csak az explicit listán):**

| # | Szabály | Token / minta |
|---|---|---|
| 1 | Minden `var(--x)` létező tokenre mutasson | `tokens.css` |
| 2 | **Szín-literál tilos** (hex/rgb/hsl/nevesített) a `tokens.css-en` kívül | `--hatter*`, `--szoveg*`, `--keret*`, `--siker/figyelmeztetes/hiba(+‑hatter)`, `--callout-*` |
| 3 | Szín-token **önmagában** nem lehet `box-shadow`/`outline`/`border` értéke | `inset 0 0 0 var(--keret-vastag) var(--keret-mezo)` |
| 4 | `font-size`/`line-height`/`font-weight`/`border-radius` tokenből | `--betu-ui/-kicsi/-torzs/-h1…`, `--sor-ui`, `--suly-*`, `--kerekites*` |
| 5 | Átmenet-idő, árnyék, átlátszóság, fókusz-vonal tokenből | `--mozgas-*` (csökkentett mozgásnál 0), `--arnyek-*`, `--tiltott-atlatszosag`, `--fokusz-vastag/-tav` |
| 6 | Vezérlő-magasság/szélesség tokenből (20/22/24/28/32/36/44 px nyers érték tilos) | `--magassag-gomb(-kicsi)`, `--magassag-suru`, `--magassag-mezo`, `--magassag-lista-sor` |
| 7 | `z-index ≥ 10` csak rétegtokenből | `--reteg-lap/atfedes/ertesites/lebego` |
| 8 | **Kitöltött (akcent) gomb csak `.m-gomb`** (a `background: var(--akcent-kitoltes)` egyetlen helye `minta.css`) | `m-gomb`, `.semleges`, `.link`, `.suru` |
| 9 | Távolság a 4/8-as skálán | `--t-1…--t-8` |
| 10 | Téma: `light-dark()` párok egy sorban; a `<html data-tema>` / rendszer követése | – |
| 11 | Hiba: `role="alert"` + ikon + szó (az alap.css automatikusan, a listán lévő osztályokra: `.hiba, .hiba-sor, .kviz-hiba, .betoltes-hiba, .uj-hiba, .olvasasi-hiba`) – új hiba-osztályhoz az alap.css szelektorát bővíteni kell | `--ikon-hiba`, `--hiba`, `--hiba-hatter` |
| 12 | Fókusz: egy gyűrű mindenhol | `outline: var(--fokusz-vastag) solid var(--fokusz-gyuru)`, `--fokusz-tav(-befele)` |
| 13 | Kontraszt (WCAG ≥ 4,5 szöveg, ≥ 3 vezérlő-határ): új színpár a `tokens.css`-be kerüljön, és a `kontraszt.test.ts` listájába | `--keret-mezo` (≥3:1) |
| 14 | Állapotot az akcent **soha** nem jelöl (hiba/siker saját token) | `--siker`, `--figyelmeztetes`, `--hiba` |

**Márka:** egyetlen akcent a **burgundi** (`--akcent` `#5a1828` / sötét `#d0687b`, `tokens.css:36`; három szerep: vonal/jel `--akcent`, kitöltés `--akcent-kitoltes`+`-hover`+`-eloter`, szöveg `--akcent-szoveg`); márka-színek az app-ikonból (`--burgundi`, `--krem`, `--burgundi-lap`, `:60-62`), a munkafelület krómjában nem szerepelnek. **MANIFOLD betűjel:** `.manifold-jel` (+`.nagy`), forrásszöveg „Manifold", a nagybetűt/ritkítást a CSS adja (`alap.css:73-86`, `--betu-jel`, `--ritkitas-jel`); csak a Manifold-gomb és a vezérlő lapcíme használhatja („máshol a felület nem ír ritkított nagybetűt") – a Welcome-képernyő `.manifold-jel.nagy`-t használhatja (28 px, 0,24em) ha a DESIGN.md engedi. **Csend mód** (C38): `<html data-csend>` / `data-csend-gepeles`; `[data-csend-rejt]`, `[data-csend-terulet]`, `[data-csend-halvanyul]` attribútumok (`alap.css:234-260`), `--mozgas-csend`, `--csend-halvany`; szabály: hiba, megszakadt kapcsolat, mentetlen állapot jele soha nem rejtett/halvány (teszt őrzi). Alapból BE van (`felulet.csend.be = true`) → az új felületek (onboarding/settings) ne rejtsenek el kritikus vezérlőt `data-csend-rejt`-tel.

**Hiányzó minták az új felületekhez** (jelenleg komponens-szintű lokális stílus; érdemes `minta.css`-be emelni, `m-` előtaggal): kapcsoló (`Kapcsolok.svelte` saját stílus), szegmens/rádió (téma-választó), szöveg-/legördülő mező (`--magassag-mezo` 44 px a palettához; a normál űrlap-mezőé nincs), kártya/lista-sor (`--magassag-lista-sor`), `UresAllapot`, haladássáv (`--kerekites-jel`, `--akcent` töltősáv van, komponens nincs), tab/lépés-jelző (onboarding), párbeszéd (`lib/ui/Atfedes.svelte` modális alap). Új token csak a `tokens.css`-be (+ DESIGN.md, kontraszt-lista).

---

## 7. Tesztek

| Mutató | Érték |
|---|---|
| Futtató | **vitest 5**, környezet **jsdom 30**, `@testing-library/svelte 5.4`; `resolve.conditions: ['browser']` (a runes-os modulokhoz); `setupFiles: tests/beallitas.ts` (matchMedia, `Element.animate`, `scrollIntoView`, Range-geometria pótlás) (`vite.config.ts:62-79`) |
| Tesztfájl | **152** `tests/*.test.ts` (38 `*.svelte.test.ts` komponens/runes-teszt, 114 egység) + 11 segéd (`beallitas.ts`, `*-segedek.ts`, `dolgozat-fixture.ts`, `plot-hamis.ts`…) |
| **`app/src/**/*.test.ts`** | **0** – a tesztek nem a forrás mellett élnek; az `include` is csak `tests/**/*.test.ts` |
| Teszteset / csoport / `expect` | 1 765 `it/test` · 474 `describe` · 5 905 `expect(` · 28 942 sor (statikus számlálás, `it.each` nélkül kibontva) |
| Egyéb készletek | `tests/kezi/*.kezi.ts` (5, valódi vaulton, Node-környezet, `vitest.kezi.config.ts`); `tests/perf/*.perf.ts` (2, falióra-alapú, `MOS_TELJESITMENY=1`/`bin/mos perf`); `app/` scriptek: `check` (svelte-check, `--fail-on-warnings`), `build`, `test` |
| Fixture-ek | core-hívások `kerdez` mockolva / hamis `CoreKapcsolat.szetoszt`; nincs valódi core a fő készletben |

**Mi törik el i18n-nél (becslés):**

| Mutató | Darab |
|---|---|
| `expect/getBy/findBy…` sor ékezetes literállal | ~1 706 sor, mind a 152 fájlban |
| ebből DOM-szöveg-lekérdezés (`getByText/ByRole name/Label/Title`, `textContent`, `aria-label`) | ~730 sor; `getByText…` 276 hívás, `getByRole(…name)` 207, attribútum-szelektor 16 |
| legszövegesebb tesztek | `tracker-nezet.svelte` 68, `bevitel.svelte` 61, `atnevezes` 60, `vezerlo-lap.svelte` 53, `notion-muveletek` 52, `dolgozat-ertekeles.svelte` 50, `kereso-ablak` 45, `tulajdonsagok-panel` 41, `tulajdonsag-javaslatok` 39 |
| `lib/core/api.ts` hibaszöveg-tesztek | `tests/api-hiba.test.ts` (21 magyar assert: `KAPCSOLAT_HIBA`, státusz-üzenetek) |
| Parancs-nevek/palettában | `paletta*`, `parancs*`, `billentyu-utkozes`, `csend` (37) |

* **Kulcs = magyar szöveg + fix `hu` a tesztekben ⇒ ~0 törés** (a `t()` identitás). Munka: a `setupFiles`-ban a nyelvet `hu`-ra rögzíteni; a `*.svelte.test.ts` komponens-tesztek a context-et (`kornyezet`) saját maguk adják → i18n-nek is ugyanígy kell (modul-szintű állapot, nincs context-igény; `nyelv` `$state` modul).
* **Kulcs = azonosító ⇒ ~1 700 assert átírása** (vagy a teszt `hu.json`-ból kérdezi a szöveget).
* **Core-hiba kódosítása:** az `ApiHiba.message` marad → a mai 119+ hibaszövegre épülő tesztek zöldek maradnak, ha a `hiba` fallback-ként megmarad.
* **Új tesztek kellenek:** nyelvváltás (reaktivitás), hiányzó kulcs → hu fallback, param-egyezés, többes szám, `Intl` locale, parancs-nevek nyelvváltás után a paletta-szűrésben, „nincs nyers magyar literál” ratchet.
* Teszt-hatás kicsi, de fontos: a tokenek-őr minden új `.svelte`-t/`.css`-t magától vizsgál; az új onboarding/settings stílusai ezen mennek át.

---

## 8. Vendorált könyvtárak és CSP

Nincs `vendor/` mappa: mind **npm-függőség, pontosan rögzítve** (`package.json`, nincs `^`), a Vite csomagolja a `dist/`-be; külső URL nincs (`vite.config.ts:55-56` „Külső URL nincs benne (D3)").

| Könyvtár | Verzió | Hogyan van bekötve | Betöltés | Megjegyzés |
|---|---|---|---|---|
| **pdf.js** (`pdfjs-dist`) | 6.3.289 | `media/pdf/pdfjs.ts:39-45`: lusta `import('pdfjs-dist')`, worker `…/pdf.worker.min.mjs?url`, `pdf_viewer.mjs` + `.css`; futásidejű adatok `dist/pdfjs/{cmaps,standard_fonts,wasm}` fix úton (`vite.config.ts` `pdfjsAdatok`: a worker név szerint kéri) | lusta (PDF-fül) | `useWasm:false` (a CSP-ben nincs `wasm-unsafe-eval`; a JPX/JBIG2 `*_nowasm_fallback.js` JS-tartalék), `enableXfa:false`, `useWorkerFetch`, `disableAutoFetch/Stream`; saját `MagyarL10n` (`media/pdf/magyarL10n.ts`), hogy ne kérjen hálózati `viewer.ftl`-t |
| **KaTeX** | 0.18.10 | `szerkeszto/renderelok/katex.ts` (+ `olvaso/html.ts`, `elo/widgetek.ts`, `kviz`, `JobbPanel`) | lusta `katex-*.js` (259 KB) | fontok: 20 × (woff2+woff+ttf) = ~1,17 MB a `dist/assets`-ben; WebKit-nek elég a woff2 (296 KB) → ~0,9 MB megtakarítás a `ttf/woff` elhagyásával |
| **Mermaid** | 12.0.0 | `szerkeszto/renderelok/mermaid.ts:20` lusta `import('mermaid')`, `securityLevel:'strict'`, feliratok DOMPurify-jal tisztítva | lusta: ~34 diagram-/segéd-chunk | **a legnagyobb**: `elk-…js` 1,46 MB, `cytoscape.esm` 435 KB, `chunk-FOHPRMQF` 662 KB, diagramonkénti chunkok (usecase, architecture, sequence, gantt, c4, swimlanes…); becslés ≈ 4,3–4,8 MB a 10,7 MB JS-ből |
| **JSXGraph** | 1.13.3 | `szerkeszto/renderelok/plot/index.ts:14` lusta `import('jsxgraph')`, `rajzolo.ts` (a könyvtárat a hívó adja, tesztben hamis) | lusta `src-*.js` 1,0 MB | – |
| **Lucide** | 1.49.0 | `lib/ikon/ikonok.ts` (140 sor): *csak* az itt felsorolt ikonok (tree-shake), `Ikon.svelte`; `IconNode` típus a parancs-regiszterben | beágyazott a fő csomagba | új ikon csak az `ikonok.ts`-be |
| **CodeMirror 6** | 6.x (12 csomag) + `@lezer/*` | `szerkeszto/beallitas.ts` | fő csomag + `naplo-*.js` 544 KB + `dist-*.js` modulpreload-ok | – |

**CSP** (kizárólag `<meta>` az `index.html:6-9`; a core `server.py:691` csak `X-Content-Type-Options: nosniff`-et ad, HTTP CSP-fejléc nincs): `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; object-src 'none'; base-uri 'none'; form-action 'none'`. Következmények az új felületekre: nincs inline script/eval/wasm, nincs `worker-src` (→ `default-src 'self'` ⇒ saját-origin Worker/pdf.worker rendben, `blob:` Worker nem), a `style-src 'unsafe-inline'` kell a Svelte `style:`-hoz/Mermaidhoz, **külső fordítás-/telemetria-letöltés nem megy** (modell-letöltés a core-on át, nem a böngészőből → a Model Manager csak core-API-n keresztül dolgozhat; a `connect-src` ne bővüljön), `connect-src` a WS miatt `ws://127.0.0.1:*`. A `form-action 'none'` miatt natív `<form>`-submit nem használható (esemény-kezelő kell).

**Build-méret** (`du -sh app/dist` = **16 MB**): `assets/` 13 MB (251 `.js` = 10,7 MB, 3 `.css` = 0,4 MB, betűk+SVG+GIF = 1,05 MB), `pdfjs/` 3,1 MB (cmaps 1,6 MB, standard_fonts 0,8 MB, wasm-tartalék 0,6 MB). **A kezdeti betöltés** (`index.html` + modulpreload + CSS) ≈ **2,2 MB** (index 769 KB, naplo 544 KB, CodeMirror-`dist-*` + szerkesztok 79 KB, CSS 234 KB+naplo.css); minden más lusta. `assetsInlineLimit: 0`, `sourcemap: false`. Hatása: a nyelvi fájlok (JSON, ~2 600 kulcs ≈ 150–250 KB/nyelv) elhanyagolhatók; az i18n bundle-mérete a `import('./en.json')` lusta betöltésével elkerülhető, `hu`-nál nincs szótár.

---

## 9. Kiemelt kockázatok / döntési pontok az implementációhoz

1. **A vault-választás nem a felületen dől el** (core indításkori konfig + a Swift héj). A Welcome/workspace lépés ezért natív vagy új core-mód; a Svelte onboarding csak a core-ral élő lépéseket (nyelv, preset, modell, adatvédelem) tudja.
2. **Nincs felhasználó/profil**: per-user állapot = külön `state`/`var` + vault; a felület-oldali munka ehhez kicsi (profilválasztó), a lényeg core/héj.
3. **Settings-oldal**: az egyetlen valódi kapcsoló-minta (`Kapcsolok.svelte` + `kapcsolok.svelte.ts`) jó, de téma/csend/értesítés csak ⌘P-ből érhető → a Settings-oldal első értéke ezek felszínre hozása.
4. **Model Manager**: a core-nak ma csak *olvasó* `/api/vezerlo/modellek` (router-tábla) és `/api/vezerlo/rendszer` van; letöltés/telepítés/teszt CLI (`bin/mos models pull`) → új core-végpontok + feladat-típusok (a `feladatsor` WS-eseményes haladás-mintája kész: `lib/vezerlo/feladatsor.svelte.ts`). Felhasználói név ↔ technikai modellnév leképezés mintája: `Modellek.svelte:12-27` (`NEV`).
5. **Developer Mode**: egy `fejlesztoMod` kapcsoló (`felulet.json`) + a 3.2 táblázat elemeinek feltételes megjelenítése; a ⌘P „Fejlesztő:” kategória már létezik (`szerkeszto/index.ts:212,222`) – ugyanezzel a flaggel szűrhető (`Parancs.elerheto`).
6. **Hibák**: a `hibaSzoveg()` (`api.ts:69`) a természetes egységesítési pont; `kod` hiányában a nyers `hiba`-szöveg kiszivárog – Developer Módon kívül csak a felhasználói rövid szöveg + „Részletek” (másolható) kell.
7. **i18n sorrend**: a ratchet-teszt és a `t()` infrastruktúra az onboarding *előtt*, hogy az új felületek eleve kétnyelvűek legyenek, és ne növelje a ~2 600 elemes állományt.
