# Manifold-OS 2.0 — design-rendszer

**Minden, ami a felületen látszik, egy rendszerből jön: tokenek, egy ikonkészlet, egy mozgásskála, egy fókuszgyűrű.** A komponens nem ír nyers színt, méretet vagy időt; ha új érték kell, az előbb token lesz. Forrás: `app/src/styles/tokens.css` és `alap.css`; a felület szerkezete és API-ja: [ARCHITECTURE.md](ARCHITECTURE.md) 2. fejezet, „A felület (C07)”.

## 1. Elvek

- **Nulla AI-zaj a munkafelületen** (TERV 5.3). A Manifold-OS egyetlen gombbal (a szó, ikon nélkül) és ⇧⌘M-mel nyílik; a többi felület nyugodt, semleges.
- **Az olvasás az első.** A jegyzet törzse 16 px, 1,6-os sortávval, 44 rem (~704 px) szélességben (Notion-szerű); a felület krómja 13 px, hogy ne versenyezzen vele.
- **Billentyűzetről minden elérhető.** Minden funkció parancs a regiszterben (⌘P), a gombok is a parancsot futtatják.
- **Nincs elcsúszás.** A sávok mérete tokenben rögzített, és a felület a mentett állapottal együtt jelenik meg (a héj a `kesz` jelre mutatja az ablakot).
- **Egész pixel.** Minden méret a 4-es rácson; a sávok 1 px-es kerete a token-magasságon *kívül* van, így a 28 és 20 px-es elemek egész pixelre kerülnek középre (`--fulsor-teljes`, `--allapotsor-teljes`).

## 2. Szín

A téma a `color-scheme`-ből jön, minden színtoken egy `light-dark(világos, sötét)` pár — egy sor, nem két külön blokk, így a két téma nem csúszhat szét. Alapból a rendszert követi; a `<html data-tema="vilagos|sotet">` rögzíti (⌘P → „Téma: …”, vagy a Nézet menü). A héj a címsort is a témához igazítja. A `light-dark()` WebKit 17.5-től él; a lockolt futtatókörnyezet (macOS 26+) ezt adja.

A színek **szerep szerint** vannak elnevezve, nem árnyalat szerint: semleges, enyhén meleg szürkeskála és egyetlen akcentus: a **burgundi** (C37, CLAUDE.md 25. döntés; forrás: a Manifold-OS 2.0 design system). A felület szinte monokróm, a burgundi ritka, ezért jelent valamit. Három szerepe van, három tokenje: `--akcent` a vonal és a jel (húzás célvonala, elválasztó, a futó feladat pontja, a szövegkurzor, a haladássáv), `--akcent-kitoltes` (+ `--akcent-hover`, `--akcent-eloter`) a kitöltött gomb, `--akcent-szoveg` az akcentus-színű szöveg (link). Egy nézetben legfeljebb egy kitöltött gomb. Az akcent **soha nem jelöl állapotot**.

| Token | Világos | Sötét | Mire |
|---|---|---|---|
| `--hatter` | `#ffffff` | `#1c1c1c` | munkaterület, nézetek |
| `--hatter-oldalsav` | `#f7f7f5` | `#202020` | oldalsáv, jobb panel, állapotsor, listák lábléce |
| `--hatter-emelt` | `#ffffff` | `#262626` | átfedés, lap, értesítés (árnyékkal) |
| `--hatter-hover` | `#efeeec` | `#2c2c2c` | hover |
| `--hatter-aktiv` | `#e6e5e2` | `#353535` | lenyomva, kiválasztott fül |
| `--hatter-kijelolt` | `#f4e9eb` | `#3a1c24` | a lista aktív sora, szövegkijelölés (burgundi árnyalatú halvány háttér) |
| `--szoveg` | `#2f2e2b` | `#e8e7e4` | elsődleges szöveg |
| `--szoveg-masodlagos` | `#5c5b57` | `#b3b2ae` | másodlagos szöveg |
| `--szoveg-halvany` | `#64635e` | `#9f9e98` | címkék, utak, üres állapot, ikonok |
| `--keret` | `#e7e6e3` | `#303030` | elválasztó vonalak (díszítő) |
| `--keret-eros` | `#d3d2ce` | `#3d3d3d` | görgetősáv, erősebb vonal |
| `--keret-mezo` | `#82817b` | `#85847d` | beviteli mező kerete (UI-elem, ≥ 3:1) |
| `--akcent` | `#5a1828` | `#d0687b` | az akcentus mint vonal és jel: húzás célvonala, aktív elválasztó, a futó feladat pontja, szövegkurzor, haladássáv (sötétben rózsás borszín, hogy a sötét felületen is látsszon) |
| `--akcent-kitoltes` | `#5a1828` | `#5c1b2b` | a kitöltött gomb háttere (mindkét témában mély burgundi, krém betűvel) |
| `--akcent-hover` | `#3d1119` | `#6e2234` | a kitöltött gomb hovere |
| `--akcent-kitoltes-keret` | `#5a1828` | `#b85a6c` | a kitöltött gomb 1 px-es belső határa (C38, K226: ≥ 3:1 a felületen) |
| `--akcent-eloter` | `#f3ece3` | `#f3ece3` | krém szöveg és ikon a burgundi kitöltésen |
| `--akcent-szoveg` | `#7d2335` | `#e0909e` | akcentus-színű szöveg: link, wikilink, link-szerű gomb (a link mindig aláhúzott) |
| `--fokusz-gyuru` | `#5a1828` | `#d0687b` | a `:focus-visible` gyűrű |
| `--kiemeles` | `#5a1828` | `#eaa7b2` | keresési egyezés a listában |
| `--burgundi` | `#3d1119` | `#4a1520` | az app-ikon alapja és a kiállított márkafelület (a krómban nem szerepel) |
| `--krem` | `#f3ece3` | `#f3ece3` | az ikon gömbje; szöveg és vonal a `--burgundi`-n |
| `--burgundi-lap` | `#c23a52` | `#c23a52` | az ikon érintő lapja (csak az ikonban és a borítón) |
| `--siker` / `-hatter` | `#1d7a4c` / `#e8f5ee` | `#5cc28e` / `#1d2f25` | sikeres feladat |
| `--figyelmeztetes` / `-hatter` | `#8f5a00` / `#fbf1df` | `#e2a53f` / `#33291a` | figyelmeztetés, megszakadt kapcsolat |
| `--hiba` / `-hatter` | `#c03a2b` / `#fcebe9` | `#f2786a` / `#3a2220` | hiba |
| `--hatter-kod` | `#f6f5f2` | `#252524` | kódblokk (C08) |
| `--kod-kulcsszo` · `-szoveg` · `-szam` · `-megjegyzes` · `-fuggveny` · `-tipus` · `-meta` | `#8b2fa8` · `#2b7a3d` · `#a14d00` · `#6b6a64` · `#2459a8` · `#a3326f` · `#7a5a00` | `#d19af2` · `#8fd19e` · `#f0a86b` · `#9d9c96` · `#8cb8f7` · `#f08fbe` · `#d8b35c` | kódszínezés a `--hatter-kod`-on (a `tok-*` osztályokra) |
| `--jeloles-hatter` | `#fbeea0` | `#5a4a12` | `==kiemelés==` |
| `--graf-jegyzet` · `-canvas` · `-melleklet` | `var(--szoveg-masodlagos)` · `var(--callout-cian)` · `var(--callout-narancs)` | ugyanaz | a gráf csúcsai fájltípus szerint (C39, K228): a jegyzet semleges, a canvas és a melléklet adat-szín a callout-készletből; a színcsoport felülírja, az akcent csak a kijelölés |
| `--callout-<szín>` / `-hatter` | kék `#2e66c7`, cián `#0d7480`, zöld `#1d7a4c`, narancs `#9a5200`, piros `#c03a2b`, lila `#7044c2`, szürke `#5c5b57` | `#7fadf5`, `#5ec7d2`, `#5cc28e`, `#eba15a`, `#f2786a`, `#b59cf5`, `#b3b2ae` | callout címe és ikonja a saját halvány hátterén |

### Kontraszt (WCAG AA)

A `app/tests/kontraszt.test.ts` minden futáskor kiszámolja a tokenekből, mindkét témára: szöveg ≥ 4,5, UI-elem és fókuszgyűrű ≥ 3. A legszűkebb párok:

| Pár | Világos | Sötét |
|---|---|---|
| `--szoveg` / `--hatter` | 13,6 | 13,8 |
| `--szoveg-masodlagos` / `--hatter` | 6,8 | 8,0 |
| `--szoveg-halvany` / `--hatter` | 6,0 | 6,3 |
| `--szoveg-halvany` / `--hatter-aktiv` | 4,8 | 4,6 |
| `--akcent-szoveg` / `--hatter` | 9,7 | 7,0 |
| `--akcent-szoveg` / `--hatter-kijelolt` | 8,2 | 6,3 |
| `--kiemeles` / `--hatter-kijelolt` | 11,1 | 7,8 |
| `--akcent-eloter` / `--akcent-kitoltes` | 11,2 | 10,9 |
| `--akcent-eloter` / `--akcent-hover` | 13,9 | 9,2 |
| `--akcent` / `--hatter-aktiv` (jel, UI-elem) | 10,5 | 3,5 |
| `--fokusz-gyuru` / `--hatter-oldalsav` | 12,3 | 4,6 |
| `--fokusz-gyuru` / `--hatter-aktiv` | 10,5 | 3,5 |
| `--krem` / `--burgundi` | 13,9 | 12,6 |
| `--keret-mezo` / `--hatter-aktiv` | 3,1 | 3,3 |
| `--akcent-kitoltes-keret` / `--hatter-hover` | 11,4 | 3,1 |
| `--siker` / `--siker-hatter` | 4,8 | 6,4 |
| `--figyelmeztetes` / `--figyelmeztetes-hatter` | 5,2 | 6,6 |
| `--hiba` / `--hiba-hatter` | 4,7 | 5,4 |

**A hiba és az akcent** a vörös család két tagja: a `--hiba` és az `--akcent` közti kontraszt világosban 2,4, sötétben 1,3, vagyis csak színnel nem különíthető el. Ezért a burgundi soha nem jelöl állapotot, és **minden hibaüzenet ikonnal és szóval jön**: a `role="alert"` hibasorok (`.hiba`, `.kviz-hiba`, `.betoltes-hiba`, `.uj-hiba`, `.olvasasi-hiba`, `.hiba-sor`) egyetlen globális szabályból (`alap.css`, `--ikon-hiba`, a Lucide `CircleAlert` maszkja) kapják az ikont, a szöveg a magyar üzenet; az értesítés (`CircleAlert`) és a dobozok saját ikonjukat viselik.

**A kitöltött gomb határa** (C38, K226): a mély burgundi kitöltés (`--akcent-kitoltes` #5c1b2b) sötétben a felülettől csak 1,2–1,3:1-re válik el; a krém felirat marad (11,2 / 10,9), és a gomb 1 px-es belső vonalat kap az `--akcent-kitoltes-keret` tokenből (világosban maga a kitöltés, #5a1828; sötétben finom borszín, #b85a6c), így a határ minden síkon, ahol kitöltött gomb állhat, ≥ 3:1 (WCAG 1.4.11; sötétben a `--hatter`-en 3,8, az `--hatter-hover`-en 3,1). A vonal `box-shadow: inset 0 0 0 var(--keret-vastag) …` (a gomb mérete nem változik), vagy a kerettel bíró gombon a `border-color`.

A szerkesztő párjai (C08): `--szoveg` és `--szoveg-halvany` a `--hatter-kod`-on, a hét `--kod-*` a `--hatter-kod`-on, `--szoveg` a `--jeloles-hatter`-en, és callout-színenként a cím, a szöveg és a halvány szöveg a saját hátterén — mind ≥ 4,5 (a legszűkebb: piros cím világosban 4,75).

Az `app/tests/kontraszt.test.ts` a `--név: var(--másik)` álneveket is feloldja (a canvas preset színei), és az akcentus minden új párját méri mindkét témában (a kitöltött gomb, az akcent mint jel minden síkon, a fókuszgyűrű a kijelölt és a kód háttéren, a krém a burgundin, az app-ikon lapja a mélybordón). Új színpárt (előtér a háttéren) a tesztbe is fel kell venni.

## 3. Tipográfia

- Betű: a rendszerbetű (`-apple-system`, SF Pro); kód: `ui-monospace` (SF Mono). Betöltendő betűfájl nincs.
- **Olvasótörzs** (`.tipo`): 16 px / 1,6, max. `--olvasasi-szelesseg` (44 rem), középre.
- **Címek**: H1 30 px / 700, H2 24 px / 700, H3 20 px / 600, H4 17 px / 600, H5 16 px / 600, H6 16 px / 600 másodlagos színnel. A H1–H2 felett 32 px, a H3–H4 felett 24 px térköz, alatta 4–12 px: a cím a következő bekezdéshez tartozik.
- **Króm**: 13 px / 20 px (UI), 12 px / 16 px (állapotsor, címkék, láblécek). Számlálók `tabular-nums`-szal.

## 4. Térköz és méretek

4/8-as skála: `--t-1` 4 · `--t-2` 8 · `--t-3` 12 · `--t-4` 16 · `--t-5` 24 · `--t-6` 32 · `--t-7` 48 · `--t-8` 64.

| Elem | Méret |
|---|---|
| fülsor, oldalsáv-fejléc | 36 px (+1 px keret) |
| állapotsor | 24 px (+1 px keret) |
| gomb, ikongomb, fül, listasor (sávban) | 28 px |
| listasor (paletta, gyorsváltó) | 32 px |
| keresőmező | 44 px |
| kicsi ikongomb (állapotsor, fül bezárása, értesítés) | 20 px (`--magassag-gomb-kicsi`) |
| sűrű sor, chip, sorbeli kis vezérlő (Bases, tulajdonságok, diff-sor) | 24 px (`--magassag-suru`; a korábbi 22 px-es elemek a 4-es rácsra, C39) |
| Manifold-lap | 420 px |
| átfedés (paletta, váltó) | 600 px, a tetejétől 12 vh |
| oldalsáv | 200–480 px (alap 264) |
| jobb panel | 220–480 px (alap 288) |

Lekerekítés: 4 (kicsi), 6 (alap), 8 (átfedés, értesítés, a canvas csoportja is); a jelölő (haladássáv, keresési jel, kiemelés-téglalap) `--kerekites-jel` 2, a pont `--kerekites-kor` 50% (C39). Árnyék: `--arnyek-atfedes` (lebegő réteg), `--arnyek-lap` (oldalról becsúszó lap).

## 5. Ikonok

[Lucide](https://lucide.dev) (ISC-licenc), a `lucide` npm-csomagból a buildbe csak a használt ikonok kerülnek (tree-shake); hálózat futásidőben nincs. Minden ikon az `app/src/lib/ikon/ikonok.ts`-ből jön, és az `Ikon.svelte` rajzolja: 16 px (alap), 14 px (sűrű sor) vagy 20 px; vonal 1,75 (20 px-nél 1,6). Az ikon mindig díszítő (`aria-hidden`), a jelentést a gomb címkéje hordozza. Ikon csak ott áll, ahol felismerést gyorsít; a Manifold-gomb szándékosan ikon nélküli.

## 6. Mozgás

`--mozgas-gyors` 120 ms (hover, szín), `--mozgas-alap` 160 ms (átfedés, oldalsáv), `--mozgas-lassu` 200 ms (a Manifold-lap becsúszása), `--mozgas-csend` 400 ms (a gépeléskor halványuló króm, C38, a `--csend-halvany` 0,12 átlátszóságig); egy görbe: `cubic-bezier(0.2, 0, 0, 1)`. `prefers-reduced-motion: reduce` esetén minden 0 ms — CSS-ben a tokenek, JS-ben a `lib/elrendezes/mozgas.ts` `ido()`-ja. Húzás közben nincs átmenet.

## 7. Állapotok

Minden interaktív elemnek négy állapota van, mind tokenből:

| Állapot | Megjelenés |
|---|---|
| hover | `--hatter-hover`, a szöveg/ikon `--szoveg`-re erősödik |
| aktív (lenyomva) | `--hatter-aktiv` |
| fókusz (billentyűzetről) | `--fokusz-vastag` (2 px) `--fokusz-gyuru`; sávokban és listákban befelé (`outline-offset: var(--fokusz-tav-befele)`), máshol `--fokusz-tav` (2 px) távolságra; ahol az `outline` nem látszik (vászon, cella), `box-shadow: inset 0 0 0 var(--fokusz-vastag) var(--fokusz-gyuru)`. Egérre nem jelenik meg (`:focus-visible`). Az elválasztók fókuszát az akcentus-vonal jelzi. |
| kiválasztott / kapcsolt | `--hatter-aktiv` vagy `--hatter-kijelolt` (a szegmens-kapcsoló kiválasztott eleme is; az akcent nem); ARIA: `aria-selected`, `aria-pressed`, `aria-expanded` |
| tiltott | `opacity: var(--tiltott-atlatszosag)` (0,4); az okát a tooltip mondja |

## 8. Billentyűzet

Macen a `Mod` = ⌘. Betűknél a felirat számít (a magyar QWERTZ-en is), számoknál a fizikai gomb. Nem használunk olyan jelet, amely a magyar kiosztáson csak Option/AltGr-rel érhető el (`\ [ ] { }`).

| Billentyű | Parancs |
|---|---|
| ⌘P | parancspaletta |
| ⌘O | gyorsváltó (fájl megnyitása); a listában ↩ az aktív fülben, ⌘↩ új fülben, ⌥⌘↩ osztásban |
| ⇧⌘M | Manifold-OS vezérlő |
| ⌘T / ⌘W | új fül / fül bezárása |
| ⌃⇥ / ⌃⇧⇥ | következő / előző fül |
| ⌘1–⌘8, ⌘9 | n-edik fül, utolsó fül |
| ⇧⌘2 / ⌥⌘↓ | osztás jobbra / lefelé |
| ⌥⌘1 / ⌥⌘2 | oldalsáv / jobb panel megjelenítése vagy elrejtése (C38; a héj Nézet menüjében is) |
| F6 / ⇧F6 | régióváltás: oldalsáv → munkaterület → jobb panel → állapotsor; a rejtett régió is sorra kerül, és átfedésként megjelenik (C38) |
| ←→ (fülsorban) | fülváltás; Delete a fül bezárása |
| ←→ / ↑↓ (elválasztón) | méretezés |
| esc | a legfelső réteg bezárása, a fókusz visszatér a megnyitóra |
| ⌘E / ⇧⌘E | Olvasó ↔ szerkesztés / Live Preview ↔ Forrás (C08) |
| ⌘S | mentés most (a szerkesztő magától is ment) |
| ⌘B / ⌘I / ⌘⇧H | félkövér / dőlt / kiemelés (`==`); a ⌘H a macOS „Manifold elrejtése” (CLAUDE.md 20. döntés); áthúzás és kód a ⌘P-ből |
| ⌘K | link a kijelölésre (URL-mező), kijelölés nélkül `[]()` (C09) |
| ⌥↑ / ⌥↓ | a blokk mozgatása a testvérei között (Live Preview, C09) |
| ⌘F | keresés és csere a jegyzetben |
| ⇧⌘F | keresés a vaultban (a nagy keresőablak, E3) |
| ⇧⌘D | a mai napi jegyzet megnyitása; ha még nincs, létrejön (C15) |
| ⇧⌘I | beszúrás a jegyzetbe: a PDF-kijelölés kiemelése idézetként, a lejátszóból az időkód (C16) |
| F2 | átnevezés: a fájlfában fókuszált sorra (fájl vagy mappa), különben az aktív jegyzetre |
| ⌘Z / ⇧⌘Z | visszavonás / újra (a CodeMirror előzménye; a héj menüjében szándékosan nincs Visszavonás) |
| ⌘R / ⇧⌘R | C++-ellenőrzés (fordítás + tesztek) / ugyanez hibakereső móddal (ASan, UBSan) — csak `.cpp` fülön vagy `.cpp`-t beágyazó jegyzeten él; futás közben Esc a megszakítás (C36a-UI) |
| ⇧⌥F | C++-formázás clang-formattal (egy lépésben visszavonható; csak `.cpp` fülön) |

Nyitott modális átfedés alatt csak az átfedésben is érvényes parancsok (⌘P, ⌘O, ⇧⌘M) futnak.

## 9. Akadálymentesség

- Landmarkok: `nav` (oldalsáv), `main` (munkaterület), `aside` (jobb panel), `footer` (állapotsor); a fülsor `tablist`/`tab`/`tabpanel`; a paletta és a váltó `combobox` + `listbox` (`aria-activedescendant`); a Manifold-lap nem modális `dialog`, az átfedés modális.
- Minden ikongombnak magyar `aria-label`-je és tooltipje van; a gyorsbillentyű `aria-keyshortcuts`-ban is.
- Élő régiók: az értesítés `role="status"`, a hiba `role="alert"`; a „nincs találat” és az index állapota `status`.
- Fókusz: modális rétegben csapda, bezáráskor vissza a megnyitóra; az eltűnt elem helyett a munkaterület kapja.

## 10. A szerkesztő (C08)

- **Tipográfia**: a jegyzet az olvasótörzsé (16 px / 1,6, 44 rem középen); a fejezetek a 3. pont méretei, a fölöttük álló térköz a sor `padding-top`-ja. Kód, képletforrás és frontmatter: `--betu-mono`, 0,875 em.
- **Live Preview**: a jelölés csak az aktív egységben (a kijelölés által érintett levélblokkban) látszik; a többi helyén a kirajzolt elem. A callout fejléce külön egység. Fókuszvesztéskor nem változik semmi (nincs ugrás).
- **Olvasó**: ugyanaz a tipográfia (`.tipo .md`); a sima sortörés `<br>` (az Obsidian alapja), a lábjegyzetek a lap alján.
- **Callout**: halvány háttér a típus színéből, cím és ikon a típus színével; az összecsukó (chevron) a cím után áll, nyitva 90°-kal elforgatva. Ismeretlen típus: a „note” megjelenése, a címe a típus neve.
- **Kódblokk**: `--hatter-kod`, a nyelv címkéje és a másolás gomb a fejlécben (a gomb 1,5 s-ig pipát mutat).
- **Ütközés**: modális párbeszéd (`Atfedes`, az összefésüléshez a széles változat: `--szelesseg-atfedes-szeles`).

## 11. A Notion-réteg (C09)

Csak Live Preview-ban; minden műveletnek közönséges Markdown az eredménye (a kapu: a 10 esetes teszt, `app/tests/notion-obsidian.test.ts`), minden művelet egy tranzakció, a ⌘Z egy lépésben visszavon. Új token nincs: a menük a `--hatter-emelt` + `--arnyek-atfedes`, az aktív sor a `--hatter-kijelolt`, a célvonal az `--akcent`.

- **`/` menü**: a sor elején vagy szóköz után gépelt `/` nyit (kódban, képletben, linkben, szó közepén nem); a szűrő a gépelt szöveg (ékezetfüggetlen). ↑↓ / ⌃N ⌃P / PageUp-Down léptet, ↩ vagy ⇥ választ, esc zár. Elemek: Fejezet 1–3, Idézet, Felsorolás, Számozott, Feladat, callout típusonként (a regiszterből) és összecsukható, Kódblokk, Matek, Mermaid, Táblázat, Elválasztó, Beágyazás, Bases-nézet, Dátum (ma/holnap/tegnap). Üres sorra a sablon a sort cseréli; szöveg után új blokként a bekezdés alá kerül (a `/szűrő` helyén csak a beírt szakasz tűnik el); idézetben minden sora megkapja az előtagot, és ha a szomszéd idézett sor nem üres, előtagos üres sor választja el tőle (különben setext-fejezet vagy elnyelt sor lenne); üres listaelemben azonos típusnál a jelölő, a sorszám és a szóköz marad, a feladat csak a `[ ] `-t fűzi hozzá; listaelemben vagy idézett szöveg mellett csak a soron belüli elemek (beágyazás, dátum) választhatók.
- **Blokkfogó** (⋮⋮ a bal margón, az egér alatti blokk első sorának magasságában): húzás (saját pointer-események, akcentus-színű célvonal, szélen automatikus görgetés, esc megszakít) vagy kattintás → menü: Átalakítás ▸, Duplikálás, Mozgatás fel/le, Link másolása a blokkra, Törlés. A listaelem a gyerekeivel mozog, a behúzás és a jelölő a céllistához igazodik; a céltól 24 px-nél jobbra eső egér gyerekként ejti. Az idézetben/calloutban álló listaelem nem külön blokk (v1).
- **Lebegő eszköztár**: nem üres, egy blokkon belüli kijelölés fölött (egérrel húzva az elengedés után): félkövér, dőlt, kód, kiemelés, link; a gomb `aria-pressed` állapota a körbefogásból jön (a `**` és a `*` külön: `***x***` mindkettő).
- **Táblázat**: Live Preview-ban mindig a vizuális szerkesztő; a cella kattintásra a nyers Markdownnal szerkeszthető (Enter lefelé és az utolsó sor alatt új sort ad, Tab/⇧Tab lép, Esc elvet), az oszlop/sor fogója húz vagy menüt nyit (beszúrás, duplikálás, törlés, mozgatás, oszlopnál igazítás), a „+” a jobb és az alsó szélen. Szerkesztéskor a táblázat oszlopszélességre igazítva íródik vissza (a listajelölős táblázat folytatósorai a jelölő szélességű behúzást kapják, a fejlécnél hosszabb sorok extra cellái megmaradnak); a nem szerkesztett táblázat bájtra változatlan. A nyers Markdown a Forrás módban érhető el.
- **Blokklink**: szöveges blokkon a sorvégi ` ^id`, nem szövegesen önálló `^id` sor; a vágólapra `[[Név#^id]]` kerül (a név a fájlnév, nem egyedi névnél az út). Fejezetnél `[[Név#Cím]]`.
- **Billentyűzet**: a fogó és a táblázat menüje is teljesen billentyűzetről járható (↑↓, → almenü, ← vissza, ↩, esc); a blokkparancsok a ⌘P-ben (`szerkeszto.blokk-*`), a táblázat a nyilakkal és a Backspace-szel nem fogadja be a szomszéd sor szövegét.

## 12. Linkek, beágyazás és a jobb panel (C10)

Új token nincs: a popover a `--hatter-emelt` + `--arnyek-atfedes`, a beágyazott jegyzet `--hatter-oldalsav` háttérrel és `--keret-eros` bal sávval, a hibajelzés `--hiba`/`--hiba-hatter`.

- **Link a Live Preview-ban**: az aktív soron kívül csak az alias (vagy a cél, a horgony előtt ` › `) látszik, a `[[ ]]` rejtve; az aktív sorban a forrás. Kattintásra megnyílik (⌘ új fül, ⌘⌥ osztás); a forrásmódban csak ⌘-kattintásra.
- **Beágyazás**: egyedül álló sor blokk, sor közepén inline (ott a jegyzet link-chip). Jegyzet: halvány fejléc (`név › horgony`, kattintásra megnyit), a törzs az Olvasó tipográfiájával. Kép/videó a sor szélességére korlátozva, a méret-alias (`|300`, `|300x200`) szerint; PDF 520 px magas (a `|N` a magasságot adja). Hiányzó cél: halvány sor „Létrehozás” gombbal; hiba (körkörös, túl mély): `--hiba` színnel, az útvonallal.
- **Lebegő előnézet**: ⌘ (vagy ⌃) nyomva tartva a link fölött, ~300 ms után; 440 px széles, legfeljebb 22 rem magas, görgethető, fejléc nélkül; a popoverre lépve nyitva marad, Esc zárja. Billentyűzeten: „Link előnézete a kurzornál” (⌘P).
- **`[[` menü**: a C09 menüje, szélesebb (320–560 px); a név mellett jobbra a mappa (alias-találatnál `→ cél`), a találat kiemelve; a jegyzetek a mellékletek előtt. ↑↓ léptet, ↩ vagy ⇥ választ, esc zár; találat nélkül az ↩ a gépelt szöveget fogadja el.
- **Jobb panel**: négy összecsukható szakasz (visszahivatkozások, linkeletlen említések, kimenő linkek, vázlat); a link kiemelve a sorában (`--jeloles-hatter`), a canvas- és tulajdonság-forrás jelölve; a „Linkelés” gomb az említés sorában.
- **Átnevezés/áthelyezés** (F2, ⌘P): modális `Atfedes`; lépések: név vagy mappa → terv (összegzés, fájlonként kinyitható előtte→utána sorok pirossal/zölddel, blokkolók `--hiba-hatter`-rel) → megerősítés; sikernél értesítés „Visszavonás” gombbal.

## 13. Hogyan bővít egy modul

- **Parancs**: `regiszter.regisztral({ id: '<modul>.<művelet>', nev, kategoria, billentyu?, elerheto?, futtat })` → leiratkozó függvény (`app/src/lib/parancsok/regiszter.ts`). Ütköző azonosító vagy billentyű hibát dob.
- **Nézet**: `nezetek.regisztral({ id, illeszkedik: (ful, info) => …, komponens, prioritas })` (`app/src/lib/elrendezes/nezetek.svelte.ts`); a nagyobb prioritás nyer, a C07 helyőrzői negatívak.
- **Értesítés**: `ertesitesek.ertesit({ szint, cim, szoveg?, muvelet?, idotartam? })` — egyetlen hely, más modul nem rajzol saját toastot.
- **Kódblokk-renderelő** (C08): `kodRenderelok.regisztral({ nyelv: 'plot', render(forras, cel, k), becsultMagassag? })` (`app/src/szerkeszto/renderelok/regiszter.ts`) — a Live Preview és az Olvasó is ezzel rajzolja a ```` ```nyelv ```` blokkot; a hibát a regiszter a blokkban mutatja.
- **Beágyazás-típus** (C10): `beagyazasRenderelok.regisztral({ tipus: 'canvas', render(adat, link, kont, o) })` (`app/src/szerkeszto/beagyazas/regiszter.ts`) — a canvas (C14), a base (C12) és a PDF-nézet (C16) ide kapcsolódik; addig link-chip jelenik meg.
- **Callout-típus** (C08): `calloutTipusok.regisztral({ nevek, cimek, ikon, szin })` (`app/src/szerkeszto/renderelok/callout.ts`).
- **Szín, méret, idő**: csak token; új token ide és a kontraszttesztbe.

## 14. A fájlfa, a keresőablak és a nagyító (C11a, E3)

Új token nincs: a sorok a `--hatter-hover`, az aktív fájl a `--hatter-kijelolt`, a húzás célja a `--hatter-kijelolt` + 2 px `--akcent` keret (a gyökérre húzásnál a fa kerete), a számlálók `--szoveg-halvany`, a hiba `--hiba`/`--hiba-hatter`, a találat-kiemelés `--jeloles-hatter`, a nagyító háttere `color-mix(in srgb, var(--hatter) 92%, transparent)` (mindkét témában a téma háttere, a kép fölött).

- **Oldalsáv**: a fejlécben két fül (Fájlok | Címkék; `tablist`, ←→ körbe vált; a Címkék a C11b-ből; a Keresés fül az E3-tól a nagy keresőablak), jobbra az oldalsáv gombja; a nézet tartós. A fájlfa fejléc-sora (28 px): a fájlok száma, „Új jegyzet”, „Összes mappa összecsukása” (kicsi ikongombok).
- **Fájlfa**: 28 px-es sorok, 16 px behúzás szintenként (a 4-es rácson), a nyíl (14 px), az ikon (16 px: `Folder`/`FolderOpen`, a fájloké a típus szerinti), a név (egy sorban, `…`-tal vágva, a teljes út a tooltipben), a mappa végén a fájlok száma. A mappák elöl, magyar ábécé (cs, gy, ly, sz, zs digráfokkal), a számok értékük szerint (02 előbb, mint 10). ARIA `tree`/`treeitem`, gördülő tabindex (egy tabbolható sor; F6 ide érkezik); ↑↓ lép, → kinyit, majd belép, ← becsuk, majd a szülőre lép, Home/End, ↩ vagy szóköz megnyit/kapcsol, ⌘↩ új fülben, F2 átnevez, ⇧F10 vagy jobb klikk a helyi menü (Új jegyzet itt, Megnyitás új fülben/osztásban, Átnevezés, Áthelyezés, Keresés ebben a mappában). **Új jegyzet**: a fókuszált mappában (fájlnál a szülőjében, különben a gyökérben) soron belüli névmező; ↩ létrehozza és megnyitja, Esc elvet, a core hibája a mező alatt. **Húzás**: fájl vagy mappa egy mappa sorára (vagy a fa üres helyére: gyökér); a zárt mappa 700 ms után kinyílik; nem ejthető önmagába, a saját részfájába és oda, ahol már van; az ejtés a terv-átfedést nyitja a célmappával (megerősítés nélkül semmi nem ír). A húzás mellett mindig van billentyűs út (F2 → „Áthelyezés…”).
- **Átnevezés-párbeszéd mappára**: ugyanaz a lépéssor (név vagy mappa → terv → megerősítés), a terv összegzése a mozgó jegyzetek számát is mondja; a blokkolók (média a mappában, ütközés, önmagába mozgatás) indokkal, `--hiba-hatter`-rel. A terv megjelenésekor a fókusz a párbeszédben marad, az Esc a fókuszvesztés után is zár (a fájlfa húzása után nincs mező, amelyben a fókusz állna).
- **Keresőablak** (⇧⌘F, E3; `atfedes/KeresoAblak.svelte`): a `szeles` átfedés (középre, 80vh), felül a mező (`combobox`, 17 px), jobbra az állapot („N találó fájl”, „Az index még épül…”, „Nincs találat”) és a „Jelentés szerint” kapcsoló; hiba esetén a core magyar üzenete `--hiba-hatter` dobozban (`role="alert"`). Üresen a keresőnyelv súgója (szó, "kifejezés", OR, -tagadás, zárójel, path:, file:, tag:, line:, /regex/). A találat egy kártya (`group`): a név félkövéren (a kiemelés `<mark>`, `--jeloles-hatter`) + „N egyezés”, a mappa-út halványan, legfeljebb négy kivágás (sorszám / PDF-lap / időkód, a kiemelt egyezéssel; a többit „+N további sor”). Az aktív elem (kártyafejléc vagy kivágás, `--hatter-kijelolt`) az `aria-activedescendant`. ↑↓ léptet (körbe), PageUp/PageDown 8-at, ↵ megnyit és a találat sorára ugrik, ⌘↵ új fülben, ⌥⌘↵ osztásban, ⌥↵ linket szúr az aktív szerkesztőbe, Tab a jegyzeten belüli keresést nyitja, ⌘G a kivágásokat ki-be kapcsolja (tartós: `felulet.kereso.kivagasok`), Esc bezár. A kártyák 30-asával rajzolódnak (`content-visibility: auto`).
- **Külső link**: a megnyitható link (Olvasó: `a.link[data-url]`; Live Preview: `cm-link` a kirajzolt soron) kurzora `pointer`; a belső és a tiltott sémájú (javascript:, file:, relatív) link csak szöveg.
- **Nagyító**: a beágyazott kép kurzora `zoom-in`, `role="button"`, fókuszálható (↩/szóköz nyit). A nézegető modális `dialog`: az eredeti kép `object-fit: contain`-nel a nézetablakban, jobb felül a bezáró gomb (28 px, `--hatter-emelt`); Esc, a háttér és a gomb zár, a fókusz a képre tér vissza.

## 15. Tulajdonságok, címkék, előzmények (C11b)

Új token nincs: a panel a `--hatter` + 1 px `--keret` alsó vonal, a chip a `--hatter-aktiv` (link-chip `--akcent-szoveg`), a mezők hover `--hatter-hover`, fókuszban `--keret-mezo` keret; a séma-jelzés a `--figyelmeztetes`/`--figyelmeztetes-hatter`, a hiba a `--hiba`/`--hiba-hatter`; a címkefa és az előzmények a fájlfa és a jobb panel sorstílusát használják. Új szín-párok a kontraszttesztben: `szoveg-masodlagos`/`figyelmeztetes-hatter`, `hiba` és `figyelmeztetes` a `--hatter`-en, `akcent-szoveg` és `szoveg-halvany` a `--hatter-kijelolt`-en. Új ikon (Lucide): `Tag`, `Tags`, `Hash`, `Image`, `RotateCcw`, `FileClock`, `SlidersHorizontal`. Új gyorsbillentyű nincs; a parancsok csak a ⌘P-ben: „Címkék (címkefa)”, „Tulajdonságok megjelenítése / összecsukása”, „Jegyzet előzményei”.

- **Tulajdonság-panel**: a szerkesztő fejléce és a szöveg között, mindhárom módban azonos; a fejlécsor 28 px (összecsukó nyíl, „Tulajdonságok”, a darabszám, a séma-eltérések jelzése, jobbra „Új tulajdonság”), a törzs legfeljebb a szerkesztő 40%-a, saját görgetéssel; az összecsukás tartós. A sor: 104 px-es kulcs-oszlop (halvány), az érték, 24 px-es törlés (hover/fókusz alatt látszik). Mezők: szöveg és szám (átlátszó, hoverre/fókuszra keretes; ↩ vagy fókuszvesztés ír, Esc eldob), dátum és dátum+idő (a rendszer natív választója), jelölő, **lista** (chipek × gombbal; ↩ vagy vessző hozzáad, üres mezőben a Backspace az utolsót törli; a wikilink elemek link-chipek: kattintásra megnyílnak, ⌘ új fül, ⌘⌥ osztás), **Status** (választólista a három értékből, az üres „—”), link (egy értékű `[[…]]`: chip, ceruza a szerkesztéshez), nem szerkeszthető érték (objektum: mono, tooltippel). A séma szerinti link-mezőkbe (`Source`, `NN`, `Canvas`) a beírt név automatikusan `[[…]]` lesz.
- **Séma-jelzés**: a sértés a mező alatt, 12 px-es `--figyelmeztetes-hatter` dobozban (ikon, az üzenet, „A vault sémája szerint ez eltérés; a legacy séma-próba találatot ad rá.”, „Mégis beírom” / „Mégse”); a hiba szintű (érvénytelen érték, gépi Status, formai hiba) csak piros sor, megerősítés nincs. A fejlécben az „N eltérés” chip (kattintásra kinyílik a lista; piros, ha hiba szintű is van). Új tulajdonság: a nevet a séma hiányzó kulcsaiból javasolja (`datalist`), a típus választható (szöveg, szám, dátum, dátum és idő, jelölő, lista, címkék).
- **Oldalikon és borító**: az `icon` (emoji vagy a core által feloldott kép) a fül, a fájlfa sora, a keresőpanel találata és a morzsa ikonhelyén (14/16 px, a fájltípus-ikon helyett); a `cover` a panel fölött 160 px magas sáv (`object-fit: cover`, a kicsinyített `?w=1600` változat); külső URL a CSP miatt nem tölthető be, ilyenkor egy halvány sor jelzi. Az írásuk séma-sértés (megerősítés).
- **Címkék fül**: a fa 28 px-es sorokkal (a Fájlok fáéval azonos), `role="tree"`, gördülő tabindex; ↑↓ lép, → kinyit / belép, ← becsuk / a szülőre lép, Home/End, ↩ vagy szóköz kijelöl (újra: megszüntet); a sorban a címke neve és a számláló (a gyerekekkel együtt; a tooltip a pontos számot is mondja). A kijelölt címke alatt a jegyzetek listája (a címke gyerekeivel együtt; név szerint, mappával), kattintásra megnyílnak (⌘ új fül); a lista fejlécében ✕ a szűrés megszüntetésére.
- **Előzmények**: a jobb panel új szakasza (Vázlat alatt, alapból zárt): soronként a felirat (szerkesztés a Manifoldban, átnevezés, gépi lánc, kézi változás, visszaállítás, visszavonás), az idő és a kör azonosítója; a legújabb „jelenlegi”. Kattintásra a szélesebb `Atfedes`: kétoldalas, csak olvasható diff (`az előzővel` / `a jelenlegivel` váltó), az összecsukott változatlan sorok a tokenekből színezve (`.cm-mergeView`, mindkét téma). A „Visszaállítás erre a verzióra” az átfedés alján, megerősítéssel; a legújabb, a törölt és a korábbi néven álló változatnál tiltva, tooltipben az okkal. Siker után értesítés „Visszavonás” gombbal.

## 16. A „Ma” oldal, a napi jegyzet és a sablonok (C15)

Új token nincs: a szakaszfejek a `--szoveg-halvany` + `--keret` alsó vonal, a kártyák és a sorok a felület szokásos hover/aktív állapotai, a lekerekítés `--kerekites`, a jegyzet-gomb a `--keret-eros` keretes gomb. A naptár színpontja a naptár saját színe (adat, nem token); az üres vagy hiányzó szín `--keret-eros`. Új Lucide-ikon: `CalendarDays` (a Ma-fül és parancs), `CalendarCheck` (a napi jegyzet). Új gyorsbillentyű: **⇧⌘D**. A parancsok a ⌘P-ben: „Napi jegyzet megnyitása”, „Ma”, „Sablon beszúrása…” (szerkesztő nyitva); az „Új fül” nézete a „Ma” és „Napi jegyzet” sorral indul.

- **Elrendezés** (jóváhagyott vázlat, 2026-10-02): **egy oszlop, szakaszokkal**, az olvasótörzs szélességében (`--olvasasi-szelesseg`, középen), 13 px-es krómmal; a dátumfej a H1 mérete (30 px / 700), alatta halvány sor csak akkor, ha a naptáradat régi („Az itt látott naptár a 2026. szeptember 27-i állapot.”). A szakaszcím 12 px, nagybetűs, ritkított, a jobb szélén a darabszám (`tabular-nums`).
- **Szakaszok sorrendben**: Következő dolgozat / határidő (a nagy kártya: színpont, 20 px-es cím, relatív nap · dátum · idő · hely, „Felkészülési jegyzet” gomb a kötött jegyzethez; alatta a következő két határidő kis sorként) → A nap (idő-oszlop 88 px, színpont, cím, hely halványan; egész napos elöl) → Napi jegyzet (van: a név, a kivonat legfeljebb 3 sorban, „Megnyitás ⇧⌘D”; nincs: „Még nincs.” és „Létrehozás ⇧⌘D”) → Feladatok ma (+ „Lejárt”, csak ha van) → Kártyák.
- **Üres és hibás állapot**: az üres szakasz egy halvány sorra zsugorodik; az elérhetetlen forrás (hiányzó `pos.sqlite`, még épülő index) csak a saját szakaszában ad magyar mondatot, az oldal többi része él. A „Feladatok ma” üres sorának tooltipje a határidő írásmódját súgja (`📅 ÉÉÉÉ-HH-NN`). A **Kártyák** szakasz a C23-ig csak a fejet mutatja „—” számlálóval; a tooltipje megmondja, mikor jelennek meg.
- **Mozgás és nyugalom**: az oldal frissül, ha a vault vagy az index változik (összevonva, csak látszó fülön), láthatóvá váláskor és éjfélkor; nyugalomban és rejtett lapon semmi nem ütemez.
- **Billentyűzet**: minden gomb sor-szerű és fókuszálható (`:focus-visible` gyűrű, a sorokban befelé), a feladatsor ↩-re vagy kattintásra megnyitja a jegyzetet a feladat sorára (⌘: új fülben, ⌘⌥: osztásban); a gombok a parancsot futtatják.
- **Sablon-választó**: a gyorsváltó mintája (`Atfedes` + `ListaValaszto`, combobox + listbox): sablonnév ékezetfüggetlen szűréssel, ↩ beszúr a kurzornál, esc zár; üres sablonmappánál a mappa nevét mondja.
- **Fülsor**: a Ma-fül címe „Ma”, ikonja `CalendarDays`; a napi jegyzet a Ma-fül mellett új fülben nyílik (a Ma-fül nem íródik felül).

## 17. A canvas (C14)

Új tokenek: a JSON Canvas hat preset színe, `--canvas-szin-1` … `-6` és a halvány párjuk (`-hatter`): 1 piros, 2 narancs, 4 zöld, 5 cián, 6 lila — a callout-tokenek álnevei (`--canvas-szin-1: var(--callout-piros)`, C37, T163), az Obsidian megszokott árnyalataival —, 3 sárga saját (`#7a6200` / `#dcbc4c`). A kontraszttesztben: a szín a halvány párján ≥ 4,5 (a kártya fejléce), a vászon hátterén ≥ 3 (keret, él), a `--szoveg` és a `--szoveg-halvany` a halvány párokon ≥ 4,5. A hex szín (a felhasználó adata) nyersen jelenik meg. Minden más meglévő token: a vászon a `--hatter` a `--keret-eros` pontrácsával, a kártya `--hatter` + 1 px `--keret-eros` (színnel 2 px a szín, a kitöltés a szín 6%-a), a csoport a szín 7%-os kitöltése, 12 px-es lekerekítéssel, a kijelölés 2 px `--akcent`, a kijelölő téglalap az `--akcent` 10%-a, az él alapszíne a `--szoveg-halvany`, az eszköztárak `--hatter-emelt` + `--arnyek-atfedes`. Új ikonok (Lucide): `SquareDashed`, `Grid3x3`, `ZoomIn`, `ZoomOut`, `Undo2`, `Redo2`, `Palette`, `ArrowLeftRight`, `MoveRight`, `MoveLeft`, `ExternalLink`.

- **Méretek a képernyőn állandók**: a fogók (10 px), az él-fogók (12 px), a kijelölés vonala, a fájl- és csoportcímke a nagyítással osztva (`--z`); 25% alatt a kártyák vázlatot mutatnak (a név), a fájlcímkék és az élcímkék elrejtve.
- **Mutató**: görgetés = mozgatás, ⌘/⌃ + görgetés és csípés = nagyítás a kurzor körül (3–300%), szóköz + húzás vagy középső gomb = mozgatás, üres helyen húzás = kijelölő téglalap (⇧ bővít), kártyára kattintás = kijelölés (⇧ kapcsol), húzás 4 px küszöb után (a kijelölt csoport a teljesen benne álló kártyákkal), 8 átméretező fogó (min. 40 × 40), az oldal-fogóból húzás egy másik kártyára = új él (a célnál a legközelebbi oldal). A rács (20 px) húzáskor és méretezéskor igazít, ⌥ ideiglenesen kikapcsolja. A kijelölt kártya görgethető tartalma (jegyzet, hosszú szöveg) görgetéskor a saját tartalmát görgeti.
- **Dupla kattintás**: üres helyen új szövegkártya (azonnal szerkesztve), szövegkártyán szerkesztés (a jegyzet szerkesztője, Live Preview; Esc vagy kattintás kívül lezár), fájlkártyán megnyitás (⌘ új fül, ⌘⌥ osztás), link-kártyán a böngésző, a csoport címkéjén a címke, élen a címke szerkesztése.
- **Eszköztárak**: alul a vászoné (új szöveg-, fájl-, link-kártya, csoport; visszavonás, újra; rács; kicsinyítés, nagyítás %, nagyítás, mindent mutat); a kijelölés fölött lebegve: szín (a paletta a hat presettel és a „nincs”-csel), megnyitás, szerkesztés, csoport a kijelölés köré, törlés; élnél az irány (→ ← ↔ —) és a címke. Csak-olvasható canvasnál az alsó sáv „Csak olvasható”, szerkesztő gomb nincs.
- **Billentyűzet** (a fókusz a vásznon; a vászon `role="application"`): Tab / ⇧Tab a kártyák között (a fókuszba kerülő kártya kijelölődik), nyilak = mozgatás egy rácslépéssel (⇧: öt), ↩ szerkeszt / megnyit / címkét szerkeszt, Delete / Backspace törlés (a node az éleivel), ⌘Z / ⇧⌘Z / ⌘Y visszavonás és újra (a szövegszerkesztés közben a CodeMirror-é), ⌘A mind, ⌘D duplikálás, Esc a kijelölés törlése, `+` / `-` nagyítás, ⇧1 mindent mutat, ⌘S mentés most. A canvas-parancsok a ⌘P-ben is (`Canvas: …`, és az „Új canvas”).
- **Beágyazás** (`![[x.canvas]]`): a canvas kicsinyített képe 360 px magasan (a kártyák kerete és első sora, a csoportok, az élek), a fejléc a canvas neve; kattintásra megnyílik.
- **A fejléc**: a morzsa (a canvas ikonja), jobbra a jelek: „Csak olvasható” (`--figyelmeztetes`), „N eltérés a spectől” (tooltipben a lista), a mentés állapota, ütközésnél a „Ütközés — döntés kell” gomb; a hibás JSON helyett a hiba helye és szövege `--hiba-hatter` dobozban.

## 18. A Manifold-OS vezérlő (C17)

Új token nincs (a lap a `--hatter-emelt` + `--arnyek-lap`, a haladássáv a `--akcent` a `--hatter-aktiv` sávon, az állapotok a `--siker` / `--hiba` / `--figyelmeztetes`, a napló a `--hatter-kod` + `--betu-mono`). Új kontrasztpárok a tesztben: `szoveg-halvany` a `hatter-emelt`-en és a `hatter-hover`-en, `szoveg-masodlagos` a `hatter-kod`-on, `akcent` a `hatter-aktiv`-on (≥ 3). Új Lucide-ikonok: `Activity`, `Boxes`, `ChartNoAxesColumn`, `Cpu`, `GraduationCap`, `HardDrive`, `Inbox`, `ListChecks`, `Save`, `Server`, `Sparkles`, `Square`. Új parancsok a ⌘P-ben: „Manifold: futó feladatok”, „Manifold: mentés a belső lemezre”, „Asszisztens / Tracker be- és kikapcsolása”; a gyorsbillentyű változatlanul a ⇧⌘M.

- **A lap**: jobbról becsúszó, nem modális, Esc zárja (a feladat-kiválasztást is elengedi), a fókusz visszatér a megnyitóra. Szakaszai a jobb panel `Szakasz` elemével, sorrendben: **Most**, Bevitel, Tanulás, Statisztika, **Asszisztens**, Modellek, **Rendszer**; alapból csak a Most nyitott, a szakaszok állapota tartós (`felulet.json` `vezerlo.nyitott`). A Bevitel, Tanulás, Statisztika és Modellek egy mondatos üres állapotot mutat (melyik chat tölti meg).
- **Most**: a futó és várakozó feladatok (cím, állapot, haladássáv, „2/5. lépés · 40 %”, indulás ideje), alattuk a legutóbbi nyolc (kész, hiba, megállítva, megszakadt; a törölt nem látszik). Sorra kattintva a lapon belül **feladatrészlet** (← Feladatok): állapot és haladás, **Leállítás** (a kulturált típusnál a tétel végén áll meg; különben megerősítés után azonnali), kulturált típusnál külön „Azonnal…”; sorban álló feladatnál „Törlés a sorból”; a hiba és a figyelmeztetések a fejlécben; **Mit változtatott**: körönként (a kör azonosítója monospace) a fájlok állapotjellel (A/M/D), névvel, mappával és +/−-szel, fájlra kattintva a feladat előtti és utáni szöveg kétoldalas összevetése (az előzmények diffjével közös `mergeNezet`); a kör **Visszavonás** gombja megerősítéssel (az új commit visszavonható; ütközésnél vagy foglalt kör-zárnál a core üzenete és a fájlok láthatók); a már visszavont kör „visszavonva”; **Napló** monospace, a vég követésével (csak futó feladatnál és látszó ablakban frissül, 2 s).
- **Jelenlét**: egy `--akcent` pont (6 px, a MANIFOLD jel után fél em-nyire, nincs animáció és szám) a Manifold gomb mellett, amíg feladat **fut** (a várakozó nem számít); rejtett oldalsávnál ugyanez az állapotsorban. A képernyőolvasó „, feladat fut” szöveget kap. A feladat végén egyetlen értesítés (kész, hiba, megállítva, megszakadt) „Részletek” művelettel, amely a lapot a feladatra nyitja.
- **Asszisztens**: az Asszisztens és a Tracker `role="switch"` kapcsoló (natív jelölőnégyzet), alapból be; a váltás azonnali, hibánál visszaáll. Az Asszisztens kikapcsolása az automatikus munkákat tiltja (ARCHITECTURE 2., C17).
- **Rendszer**: memória (szabad %, összes, a core és a worker RSS-e), modellzár birtokosa (modell, pid, idő; elavult bejegyzés szabadnak számít), betöltött modell és keret (ha a worker fut), SSD (kötet, szabad / összes), utolsó mentés (figyelmeztetés, ha régebbi a legutóbbi változásnál) és a **Mentés most** gomb (a `mentes` feladattípus). Az adat csak nyitott lap és látszó ablak mellett frissül (5 s).
- **A modulok parancsai**: a „Kártyák ebből” (C23), „Kvíz ebből” (C22), „Megoldás” és „Levezetés ellenőrzése” (C24), „Összefoglalás” (C26) **helyőrző** parancsok (`kartya.ebbol`, `kviz.ebbol`, `matek.megoldas`, `matek.levezetes`, `osszefoglalas.keszit`; csak megnyitott `.md` jegyzetnél érhetők el): futtatáskor értesítés, hogy melyik chat készíti el. A tulajdonos chat **ugyanazon az azonosítón** regisztrálja a valódi parancsot (előbb a helyőrző leiratkozik; `app/src/vezerlo/helyorzok.ts`), a helyi menü a regiszterből olvas, így nem kell hozzányúlni.
- **A jegyzet helyi menüje** (jobb klikk vagy ⇧F10 / a Menü billentyű a Markdown-jegyzet szerkesztőjében): a natív menü helyett saját (a fájlfa menüjének primitívje): Kivágás / Másolás / Beillesztés, alatta a Manifold-parancsok (az elérhetetlen tiltott). A canvas-kártya és más szerkesztők natív menüt kapnak. A natív „Szó keresése” és a helyesírás-javaslat így nem érhető el (felhasználói döntés).


## 19. A PDF-olvasó és a lejátszó (C16)

Új tokenek: `--pdf-hatter` (a lapok körüli sík, `#e9e8e4` / `#141414`), `--pdf-lap` (a lap mindkét témában papírfehér: tartalom, nem króm), `--pdf-kiemeles` / `--pdf-kiemeles-aktiv` (sárga, áttetsző, `mix-blend-mode: multiply` a lapon), `--arnyek-pdf-lap`, `--lejatszo-hatter` (a videó letterboxa, fekete), `--lejatszo-felirat` / `--lejatszo-felirat-hatter` (a képre írt felirat). A kontraszttesztben: `lejatszo-felirat` a `lejatszo-hatter`-en. Új Lucide-ikonok: `Play`, `Pause`, `RotateCw`, `Volume2`, `VolumeX`, `Captions`, `CaptionsOff`, `PictureInPicture2`, `ChevronUp`. Új gyorsbillentyű: **⇧⌘I** („Beszúrás a jegyzetbe”); a PDF-fülben a ⌘F, ⌘+ / ⌘− / ⌘0 a fül sajátja (a szerkesztő ⌘F-je csak akkor fut, ha szerkesztő az aktív).

- **PDF-fül**: egy 36 px-es eszköztár (bélyegsáv-kapcsoló, morzsa, ‹ `N / M` ›, kicsinyítés · Oldalszélesség / Egész oldal / % · nagyítás, keresés, kiemelés), alatta a pdf.js virtualizált lapjai a `--pdf-hatter`-en, 16 px köz. A bélyegsáv 160 px, a bélyeg 112 px széles, a látszó bélyegek rajzolódnak (legfeljebb 40 vászon él), az aktuális 2 px `--akcent` kerettel, ↑↓ / Home / End léptet. A keresősáv (⌘F) az eszköztár alatt: a mező, „N / M” vagy „Nincs találat”, ↩ / ⇧↩, Esc zár; ékezet- és kisbetű-független. A nagyítás trackpad-csípéssel (WKWebView `gesture*`) és ⌘/⌃-görgővel is; az „Oldalszélesség” átméretezéskor újraszámolódik.
- **Kiemelés**: a kijelölés alatt lebegő „Kiemelés” gomb (`--akcent-kitoltes`, krém betű); vagy ⇧⌘I. A kiemelés a PDF melletti `<PDF> – kiemelések.md`-be kerül (a core írja, pillanatképpel), és idézetként a célzott jegyzetbe; a lapon sárga téglalap. A téglalapra kattintva menü: „Idézet beszúrása a jegyzetbe”, „Megnyitás a kiemelés-jegyzetben” (osztásban, ⌘ új fülben), „Kiemelés törlése” (`--hiba` szín). Több lapra nyúló kijelölés: figyelmeztetés. Kijelölés nélkül a ⇧⌘I a látott lapra mutató linket szúr be.
- **Lejátszó**: a kép a fül szélességében (`object-fit: contain`, letterbox), alatta egy sor vezérlő: −10 s, lejátszás/szünet, +10 s, `m:ss / m:ss` (`tabular-nums`), idősáv a pufferelt résszel (`--keret-eros`), sebesség-választó (0,75–2,5×), némítás és hangerő, felirat a képen, kép a képben, teljes képernyő (a két utóbbi csak ha a WebKit engedi), jobb szélén „Időkód a jegyzetbe”. Hangfájlnál a kép helyén 160 px-es kártya a névvel. Jobb oldalt 320 px-es **átirat** (keskeny fülben, < 760 px, alul): fejléc „ÁTIRAT” + „gépi · hu” / „kiadói”, szűrőmező, a mondatok `m:ss` időkóddal (`--akcent-szoveg`), az aktív `--hatter-kijelolt`, követő görgetéssel (a saját görgetés után 4 s szünet). A fejlécben „Forrásleíró jegyzet” (osztásban nyílik).
- **Billentyűzet a lejátszóban**: szóköz / K lejátszás, J / L ±10 s, ← / → ±5 s, ⇧< / ⇧> sebesség, M némítás, C felirat. A ⌘P-ben: „Lejátszó: …” és „PDF: …” parancsok (csak nyitott nézetnél látszanak).
- **Beszúrás a jegyzetbe (⇧⌘I)**: a cél az aktív szerkesztő, különben az utoljára aktív, még nyitott jegyzet (tipikusan osztásban a PDF vagy a videó mellett); Olvasó módban vagy nyitott jegyzet nélkül a szöveg a vágólapra kerül, és értesítés szól. Az idézet új bekezdés a kurzor sora után (`> szöveg` / `> — [[X.pdf#page=N]]`), és a `Source` listába is bekerül; az időkód `[[v.mp4#t=760|12:40]]` a kurzornál. Frontmatterben álló kurzornál a beszúrás a frontmatter után történik. Egy tranzakció: a ⌘Z egy lépés.
- **Beágyazott PDF** (`![[x.pdf#page=N]]`): egy lap a tartalom szélességében, 520 px (vagy `|N`) magas görgethető sávban, `--pdf-hatter`-en; fejléc: „név › N. oldal”, ‹ ›, „Megnyitás” (a lapon, új fülben). Csak láthatóvá váláskor tölt. A beágyazott videó és hang a natív vezérlővel marad.

## 20. A dolgozat-oldal (C28a)

Új token nincs: a szakaszfejek, a sorok, a gombok és a hiba-/figyelmeztető sávok a „Ma” oldaléi (16. fejezet), a téma-sáv a `--akcent` a `--keret` sávon (6 px, `role="meter"`), a táblázat `--keret` alsó vonalakkal. Új Lucide-ikon nincs: `GraduationCap` (a fül és a parancs), `FileText` (a jegyzet-gomb). A **burgundi átállás** (C37) ezért egy helyen megy végig: a sáv és a gombok csak tokent használnak. Parancs a ⌘P-ben: „Dolgozat-felkészültség” (`dolgozat.megnyit`, kategória Tanulás); a Ma oldal dolgozat-kártyáján „Felkészültség” gomb.

- **Elrendezés**: egy oszlop, az olvasótörzs szélességében (`--olvasasi-szelesseg`), 13 px-es krómmal; a fej a dolgozat címe (H1), alatta halvány sor: relatív nap · dátum · idő · tantárgy; több közelgő dolgozatnál egy `<select>` váltó („okt. 7. · Matek témazáró”, a lezárt „(lezárt)”).
- **A szám**: 48 px-es, `tabular-nums`, alatta a szint szavai (jó / közepes / gyenge / nincs adat); mellette „Ha ma nem tanulsz többet: X% a dolgozat napjára.”, „N / M témára van mért adat.” és a kalibrálatlanság jelzése. **Mért tudás nélkül nincs szám**: „—”, „Még nincs elég mért adat a számhoz (kártya vagy kvíz kell).”, és egy halvány sor, hogy melyik forrás mit hiányol. A kötött felkészülési jegyzet gombja és a kötés fokozata („biztos kötés”, „valószínű kötés”, „áthelyezve?”) a számmal egy sorban.
- **Témák**: soronként a név (gomb: megnyitja a jegyzetet), a százalék (szövegben is), a sáv és egy halvány összegző sor (kártyák · kvíz · utolsó tanulás · idő); a „Hogyan?” gomb (`aria-expanded`) táblázatot nyit: összetevő · érték · bizalom · súly · nyers adat, plusz a kilátás és az átnevezés előtti útvonalak említése. A források (PDF-oldalak) a lista alatt.
- **Gyenge pontok**, **Esedékes kártyák**, **Napi terv** (napok, szeletek perccel és okkal, a naptárban már levő blokk, a kártyák becsült napi száma, a nyitott javaslat jelzése a jóváhagyás helyével), **Hogyan számolódik** (`<details>`: a képlet szövege és a súlyok). A **Próbakvíz** és a **Mai ismétlés** tiltott gomb; a magyarázat (a kvíz a C22, a kártyaismétlés a C23b után) a szövegben áll, nem csak tooltipben.
- **Szín**: a szín csak kiegészít — a szint, a számok és az állapotok mindig szavakkal is látszanak; az egyetlen akcentus a sáv.
- **Üres és hibás állapot**: töltés közben `role="status"`, a lista vagy a részlet hibája `role="alert"` (`--hiba-hatter`), a figyelmeztetések `--figyelmeztetes-hatter` sávban; nincs közelgő dolgozat vagy nincs naptáradat: egy halvány magyar mondat a core üzenetével.
- **Mozgás és nyugalom**: mint a „Ma” oldal — csak látszó fülön tölt, a vault, az index, a naptár és a javaslat eseményére összevonva, láthatóvá váláskor és éjfélkor; nyugalomban semmi nem ütemez.
- **Fülsor**: a fül címe „Dolgozat”, ikonja `GraduationCap`; a kiválasztott dolgozat a fül állapotában (`nezet.azon`) tartós.
- **C28b — eredmény, szöveges értékelés, önkalibráció** (új token és új ikon nincs). *Eredmény*: a lezárt dolgozat fejében „A dolgozat eredménye: 69,6% (16 / 23 pont)” és halványan a forrás („a kiértékelő jegyzet szerint: „16/23””); ellentmondó eredménynél halvány `role="status"` sor a két értékkel és a javítási kéréssel (eredmény ilyenkor nincs). *C28c*: a forrás-sor megmondja az eredetet („az „Eredmény::” mezőből: `Eredmény:: 16/23`” kódbetűvel, ill. „a kiértékelő jegyzet szövegéből: „…””); a szövegből jött, az ellentmondó (a hibás mezőnél a mező hibájának okával) és az eredmény nélküli lezárt dolgozat alatt egy halvány tipp-sor mutatja a mező alakját (`<code>`, új token nincs); a mezőből jött eredmény mellett tipp nincs. *Szöveges értékelés* szakasz a Témák előtt: „Értékelés kérése” (`m-gomb semleges`; futás közben tiltott, „A helyi modell dolgozik…”) — a modell **csak kattintásra fut** (D8); a szöveg olvasható bekezdés, alatta halvány sor a modellről: „Kalibrált helyi modell (…)”, vagy „Próba — a modell (…) erre a feladatra nincs kalibrálva” (D9); a szám-kapu bukása és a modell hibája szövegben (`--figyelmeztetes-hatter` sáv / `role="alert"`); ha a tények ujjlenyomata eltér, a szöveg marad, de „A számok azóta változtak: kérj új értékelést.” látszik. Szám nélkül nincs gomb, hanem magyarázat. *Önkalibráció* (második `<details>` a képlet alatt, **megnyitáskor tölt**, nem magától): az állapot szava („nem teljesíthető” / „nincs javulás” / „javítás javasolt”) és a „0 / 8 kalibrációs pont”, az ok teljes mondata, a mért hiba százalékpontban (kis mintára kimondva, hogy tájékoztató), pontonkénti táblázat (eredmény · becslés · hiba) és a kihagyott dolgozatok okkal; a súlyok írása a `bin/mos felkeszultseg kalibral --rogzit`-é, a felületen nincs gomb.

## 21. A C++ munkafelület (C36a-UI)

Új token nincs: minden érték a meglévőkből (25. döntés). A részletek: [C36A-UI-TERV.md](C36A-UI-TERV.md).

- **`.cpp` fül**: a fejléc a többi fülé (morzsa, mentés- és ütközés-jelek), jobbra két ikongomb: `Bug` (⇧⌘R, hibakereső mód) és `Play` (⌘R). A szerkesztő `--betu-mono` / `--betu-ui` / `--sor-ui`, sorszám-margó `--szoveg-halvany`-nyal és `--keret` elválasztóval, az aktív sor `--hatter-hover`, a zárójel-pár `--jeloles-hatter` + `--keret-eros` keret; a színezés a kódblokkok `tok-*` → `--kod-*` szabályai (`.cm-kodszerkeszto` hatókör). A fordító hibája hullámos aláhúzás (`--hiba`, figyelmeztetés `--figyelmeztetes`) és egy 8 px-es pont a margón; a buborék és a kódrészlet-lista `--hatter-emelt` + `--arnyek-atfedes`.
- **Eredménypanel** a fül alján (`--hatter-emelt`, felül `--keret`), legfeljebb a fül 45%-a, saját görgetéssel, összecsukható. Fejléc: jelvények — fordítás (`Check`/`X`, `--siker`/`--hiba` a halvány párján), `n/m teszt átment`, figyelmeztetések száma, mód, idő; futás közben a fázis szövege („Fordítás…”, „Teszt 2/5…”) és a „Megszakítás” gomb. A fordító üzenetei soronként (hely mono, szint színnel *és* szóval), a saját forrás sora kattintható (ugrás a sorra és oszlopra). Tesztenként egy 32 px-es sor (ikon, cím, állapot szóval, idő, memória); az első nem átment teszt magától nyitva: üzenet, az első eltérés helye és oka, bemenet, és a diff (várt sor `--hiba-hatter`, kapott sor `--siker-hatter`, az egyező szakasz „… n egyező sor …”). A szín mindig kiegészít: minden állapot szóval is látszik.
- **Beágyazás** `![[x.cpp]]`: fejléc (a fájlnév link, a jelvény — „4/5 átment”, „fordítási hiba”, „lefordul” —, jobbra „Megnyitás”), alatta csak olvasható, színezett kód `--hatter-kod` alapon, legfeljebb 24 sor magasan, saját görgetéssel.
- **Új C++ feladat** párbeszéd: az átnevezés párbeszédének mintája (név, mappa a mappák listájával, magyarázó sor, Mégse / Létrehozás akcentussal).

## 22. A betűjel és az app-ikon (C37)

Forrás: a Manifold-OS 2.0 design system (CLAUDE.md 25. döntés); az átvétel a C37-ben, a csend és elérés a C38-ban (23. fejezet), a felületek egységesítése a C39-ben (24. fejezet).

- **A MANIFOLD betűjel**: logó és embléma helyett a név ritkított nagybetűvel. A forrásszöveg „Manifold”, a nagybetűt a `text-transform: uppercase` adja, így a képernyőolvasó szót olvas. A króm méretében `--betu-jel` 12 px / `--sor-jel` 16 px, súly `--suly-felkover` (600), ritkítás `--ritkitas-jel` 0,2 em; kiállításban (a C39 kezdőlapja, vezérlő nyitó állapota; egy nézetben legfeljebb egyszer) `--betu-jel-nagy` 28 px / `--sor-jel-nagy` 32 px / `--ritkitas-jel-nagy` 0,24 em. A stílus egyetlen helye a globális `.manifold-jel` (`.nagy` a kiállítási méret) osztály (`alap.css`).
- **Hol áll**: a Manifold-gomb az oldalsáv alján (nyugalomban `--szoveg-masodlagos`, hoverre `--szoveg`, ikon nélkül) és a vezérlő lapjának címe (`--szoveg`). Máshol a felület nem ír ritkított nagybetűs szöveget: a jel attól egyedi, hogy egyedül áll. Színe sosem akcentus, háttere sosem színes.
- **A pont**: a jel mellett csak egy dolog állhat: a futó feladat `--akcent` pontja (6 px, a jel után fél em-nyire; rejtett oldalsávnál az állapotsorban). Csak futó feladatot jelez, nem díszít.
- **Szövegkurzor**: a szerkesztő (CodeMirror) és minden beviteli mező kurzora `--akcent` (`caret-color`).
- **Az app-ikon — Érintő lap**: egy gömb körvonala és egy lap, amely a gömböt kívülről, egyetlen helyen érinti (a manifold definíciója egy képben: kicsiben sík, egészében görbe). Három szín, színátmenet, árnyék és fény nélkül: `--burgundi` alap (#3d1119), `--krem` gömb (#f3ece3), `--burgundi-lap` lap (#c23a52). Az ikon témától független (sötét módban is ugyanaz).
- **Fájlok** (`shell/ikon/`): `manifold-ikon.svg` (a macOS-rács: 1024-es vászon, 824 px-es test, 185 px-es lekerekítés), `manifold-ikon-kicsi.svg` (16–32 px-re, vastagabb gömbvonal), `manifold-ikon-teli.svg` (széltől szélig, ha a rendszer maszkol), `manifold-sablon.svg` (egyszínű sablonjel a menüsorhoz; a héj ma nem használ menüsor-elemet, ezért nincs bekötve). A forrás a design systemből változatlanul átvett négy SVG.
- **A .icns előállítása**: `bash shell/ikon/keszit.sh` (a `rasztero.swift` AppKit/CoreSVG-vel átlátszó hátterű PNG-ket készít az iconset tíz méretéhez — 16–32 px a kicsi SVG-ből, 64 px-től a nagyból —, az `iconutil` összeállítja). A `qlmanage` nem használható: az SVG-t fehér háttérre rendereli, így a lekerekített sarkok fehérek lennének. A kimenet, a `shell/ikon/AppIcon.icns`, **verziókövetett**: a héj build-je (`shell/build.sh`) csak másolja a `Contents/Resources/`-ba (`CFBundleIconFile` = `AppIcon`), így a build nem függ a raszterezéstől. A `bash shell/ikon/keszit.sh --ellenoriz` összeveti a forrásból készülő sha256-ot a verziókövetett fájléval.
- **Ne**: ne írj betűt vagy szót az ikonba, ne tedd a lapot a gömb belsejébe, ne színezd át a gömböt, ne használd a felületen gombikonként.

## 23. Csend és elérés (C38)

Forrás: a design system „Csend és elérés” fejezete (CLAUDE.md 25. döntés). **Amit nem használsz éppen, az nem látszik; amit keresel, egy billentyű vagy egy egérmozdulat.** Egy kapcsoló a ⌘P-ben: „Csend mód be/ki” (alapból be, tartós; kikapcsolva a mindent mutató felület). A terv: `docs/C38-TERV.md`.

- **Egy állapot, egy CSS-hely.** A mód a `<html data-csend>`, a gépelés a `<html data-csend-gepeles>` (a `lib/elrendezes/csend.svelte.ts` állítja; a láthatósági szabályok tiszta függvények ugyanott, egységteszttel). A rejtett elem `data-csend-rejt`, a tartálya `data-csend-terulet`: csendben átlátszó, a tartály hoverjére vagy fókuszára előjön (`--mozgas-gyors`). A helye megmarad (nincs elcsúszás), fókuszálható és kattintható marad: **semmi nem érhető el csak hoverrel**. A szabály az `alap.css` „Csend és elérés” blokkja; komponens saját csend-szabályt nem ír (kivétel a fülsor aktív fülének bezáró gombja, amely eddig mindig látszott).
- **Alapból látszik**: a jegyzet, a fülsor (csak a fülek), az oldalsáv a fával és a MANIFOLD jellel.
- **Alapból rejtett**:

| Elem | Csendben | Elérés |
|---|---|---|
| jobb panel | zárva | ⌥⌘2, ⌘P „Jobb panel…”, F6 (átfedésként a jobb szélről, a fókusz elhagyásáig; Esc zárja) |
| oldalsáv | látszik; elrejthető | ⌥⌘1; rejtve az ablak bal szélére (8 px) vitt egér vagy az F6 átfedésként hozza elő (`--arnyek-lap-balrol`, `--mozgas-alap`); a gomb ekkor „Oldalsáv rögzítése” |
| állapotsor | átfedés az ablak alján, az oldalsáv mellett (a MANIFOLD jelet nem takarja); csak ha mondanivalója van: megszakadt kapcsolat, index-hiba vagy épülő index, olvasatlan figyelmeztetés vagy hiba, nyitott értesítés-előzmény, futó feladat rejtett oldalsávnál | az egér az alsó szélen (8 px; a sáv fölött marad), fókusz benne (F6, ⌘P „Állapotsor megjelenítése”) |
| tulajdonság-panel | összecsukva, egy halvány „N tulajdonság” sor; az „Új tulajdonság” hoverre; **a séma-eltérés chipje mindig látszik** | kattintás, ⌘P „Tulajdonságok…” |
| fülsor „+” és az aktív fül ✕ | a fülsor / a fül hoverjére és fókuszára | ⌘T, ⌘W |
| a fa eszköztára (fájlszám, új jegyzet, összecsukás) | az oldalsáv hoverjére és fókuszára | ⌘P „Új jegyzet a fájlfában”, „Összes mappa összecsukása” |
| a jegyzet fejléce (morzsa, mód-kapcsoló, „Mentés…”) | a fejléc hoverjére és fókuszára | ⌘E, ⌘P „Megmutatás a fájlfában” |

- **Soha nem rejtett és nem halványul**: a hiba, a megszakadt kapcsolat és a mentetlen állapot jele (a szerkesztő fejlécében a „Csak olvasható”, az „Ütközés — döntés kell”, a „Nincs mentve”, „A fájl eltűnt”; az állapotsorban a kapcsolat és az index hibája; a séma-chip). A `tests/csend.test.ts` őrzi: `data-csend-rejt` nem kerülhet hiba-, figyelmeztetés- vagy riasztás-jelre, és halványulni csak az oldalsáv és a fülsor halványul.
- **Gépelés közben csend**: a szerkesztőben (`.cm-content`) leütött nyomtatható billentyű, Backspace, Delete, Enter (⌘ és ⌃ nélkül) után az oldalsáv és a fülsor (`data-csend-halvanyul`) `--csend-halvany`-ra halványul `--mozgas-csend` alatt; valódi egérmozdulatra, ⌘ lenyomására vagy F6-ra azonnal (`--mozgas-gyors`) visszajön. Csökkentett mozgásnál a két idő 0: azonnali váltás. Az attribútum csak állapotváltáskor íródik (leütésenként egy logikai vizsgálat); a gépelési késleltetés a C08 mérőjével csend be/ki mellett azonos (NAPLO C38).
- **A rejtés nem csonkít**: a sávok DOM-ja rejtve is megmarad (`inert` + 0 szélesség), a jobb panel rejtve nem tölt, de nem is üríti a listáit (ugyanott, ugyanazzal a görgetéssel nyílik ki), a szakaszok nyitottsága tartós.
- **Első indulás**: a C38 utáni első indításkor (a `felulet.json`-ban nincs `csend` kulcs) a jobb panel bezárul és a tulajdonságok összecsukódnak, egyszer; utána egy halk értesítés mondja meg, hol érhetők el a panelek („Csend mód: a panelek ⌥⌘1/⌥⌘2-vel és a ⌘P-ből érhetők el.”), szintén egyszer, tartósan. A kapcsoló bekapcsolva ugyanezt az alapállapotot állítja, kikapcsolva mindkettőt kinyitja; az oldalsáv a felhasználóé.
- **Az olvasatlan értesítés**: az állapotsort csak a figyelmeztetés és a hiba hozza elő (`olvasatlanFontos`); az info és a siker már látszott értesítésként.

## 24. Egységes minták (C39)

Forrás: a design system (CLAUDE.md 25. döntés); a terv: `docs/C39-TERV.md`, a döntések: `docs/logs/2026-10-07-c39.md`. **A C12–C36 felületei (vezérlő, Ma oldal, dolgozat-oldal, Bases, canvas, gráf, PDF és lejátszó, kvíz, C++ fül, tulajdonságok, értesítések, párbeszédek) ugyanazokból a tokenekből és ugyanazokból a komponens-mintákból rajzolnak**; egyszeri szín, méret, árnyék, átlátszóság vagy réteg nincs.

- **A gomb egy minta, a design system nevével** (`app/src/styles/minta.css`, globális): `m-gomb` a kitöltött (`--akcent-kitoltes`, krém felirat, 1 px `--akcent-kitoltes-keret` belső határ, hover `--akcent-hover`, lenyomva 0,5 px süllyedés), `m-gomb semleges` a mellékművelet (átlátszó, 1 px `--keret-mezo` belső határ — a halvány kitöltés a `--hatter`-en ~1,1:1 lenne, a határ ≥ 3:1, WCAG 1.4.11 —, hover `--hatter-hover`), `m-gomb link` a soron belüli művelet (`--akcent-szoveg`, aláhúzva), `suru` a 24 px-es sorbeli változat. Mind 28 px, `--suly-kozepes`, tiltva `--tiltott-atlatszosag`. A komponens a gombot csak elrendezi (margó, hely); színt, keretet, hovert, fókuszt nem ír rá. A régi osztálynév (`elso`, `gomb`, `kviz-gomb`, `muvelet` …) a jelölésben megmaradhat az elrendezéshez és a tesztekhez. Kivétel, külön minta: az eszköztár szellem-gombja (`IkonGomb`, a Bases-eszköztár `Popover`-gombja) és a szerkesztő fejlécének jel-gombja (`jel gomb`: „Ütközés — döntés kell”, „A lemezen lévő betöltése”).
- **Jelölő**: `m-jelolo` (`.be` kitöltve) a kirajzolt jelölőnégyzet (Bases-cella).
- **Szegmens-kapcsoló**: a kiválasztott elem `--hatter-kijelolt` + `--szoveg` (gráf, Bases-beállítás); az akcent nem jelöl kiválasztást.
- **Fókusz**: egy gyűrű (`--fokusz-vastag`, `--fokusz-tav`, `--fokusz-tav-befele`; 7. fejezet). A C37 lelete (a C++ felület öt helyén `box-shadow: var(--fokusz-gyuru)`: puszta szín árnyékként, érvénytelen CSS, nem volt gyűrű) javítva.
- **Jelölővonal**: az akcent mint jel (célvonal, kijelölés kerete, az aktív bélyeg, a canvas kijelölése) `--jel-vastag` (2 px).
- **Új tokenek**: `--fokusz-vastag`, `--fokusz-tav`, `--fokusz-tav-befele`, `--jel-vastag`, `--tiltott-atlatszosag` (0,4), `--atlatszosag-felig` (0,5: a húzott elem, az átméretező fogó, a grafikon akcent-oszlopa), `--magassag-gomb-kicsi` (20), `--magassag-suru` (24), `--kerekites-jel` (2), `--kerekites-kor` (50%), `--betu-mezo` / `--sor-mezo` (15/20, a paletta mezője: a design system `krom-mezo`-ja), `--betu-kijelzo` (48, a dolgozat-oldal száma), `--reteg-lebego` (60, a lebegő link-előnézet). A 11 és a 12 px-es nyers betű a `--betu-kicsi`-re került, a Bases rendezési sorszáma (`sup`) 0,75 em.
- **A gráf színei** (K228): a jegyzet-csúcs semleges, a canvas és a melléklet a callout cián és narancs álneve; az akcent a gráfban csak a kijelölt csúcs és a kiemelt él. A színcsoportok (a `graph.json`-ból és a felület saját csoportjai, 24. döntés) elsőbbsége változatlan. Kontraszt: mindhárom ≥ 3 a `--hatter`-en (a kontraszt-teszt az álneveket feloldja).
- **Hibás token-hivatkozás javítva**: a canvas élének alapszíne (`var(--canvas-el)`, nem létező token) `--szoveg-halvany`; a vezérlő Bevitel-mezője (`var(--hatter-mezo, …)`) átlátszó.
- **Az őr**: `app/tests/tokenek.test.ts` — minden `var(--x)` létező tokenre vagy helyi egyedi tulajdonságra mutat; szín-literál csak a `tokens.css`-ben; puszta színtoken nem lehet `box-shadow` / `outline` / `border` egyetlen értéke; betűméret, sortáv, súly, lekerekítés, átmenet-idő, árnyék, átlátszóság, fókusz-vonal és vezérlő-magasság (20/22/24/28/32/36/44 px) csak tokenből; `z-index` ≥ 10 csak rétegtokenből (1–9 a komponensen belüli halmozás); a kitöltött gomb háttere csak a `minta.css`-ben. A kivételek explicit listán, indokkal (`KIVETELEK`, `ERTEK_KIVETELEK`; ma: a `tokens.css`, a token-elemző és a beágyazott canvas SVG-felirata), és a lista elavult eleme is hiba. A stíluslapokat a lemezről olvassa (a `.css` `?raw` importja a vitestben üres lehet).
- **A gépelési út nem változott**: csak CSS és osztálynév; a szerkesztő leütés-kezelése érintetlen.
- **Fejezetszámok**: új fejezet mindig a végére kerül, a meglévők számát nem tolja el; a kódban és a tervekben álló hivatkozások a mai számozásra javítva (`alap.css`: 22., `notion.css`: 11., `C14-TERV.md`: 17.).

