// A felület szövegtára (F4, PLAN P2). A KULCS A MAI MAGYAR SZÖVEG: `t('Mentés')`. A `hu` nyelv identitás (a kulcs jön vissza), így
// a felület viselkedése és a szöveg-assertek változatlanok; az angol a `lib/i18n/en/*.json` szótárakból jön. Hiányzó angol kulcs:
// a magyar szöveg (sosincs üres felület, a fordítás fokozatosan haladhat).
//
//   t('Mentés')                                  → "Save"            (en)   / "Mentés"            (hu)
//   t('Törölve: {nev}', { nev })                 → "Deleted: x"      (en)   / "Törölve: x"        (hu)
//   t('Törlés|gomb')                             → "Delete"          (en)   / "Törlés"            (hu)   ← környezet: `kulcs|ctx`
//   tp('{n} jegyzet', 3)                         → "3 notes"         (en)   / "3 jegyzet"         (hu)
//   tk('Fájl')                                   → "Fájl"  (jelölő: táblázatban, konstansban álló szöveg; megjelenítéskor `t()`)
//
// A szótárak (`en/*.json`) lapos `{ "<magyar kulcs>": "<angol>" }` objektumok, partíciónként egy fájl; az `import.meta.glob` egyesíti
// őket. Azonos kulcs több fájlban csak azonos értékkel állhat (teszt őrzi).
//
// Szótár-konvenció (a fordítónak):
//   - kulcs = a forrásban álló magyar szöveg betűre pontosan; `{nev}` a helyettesítés (a kulcsban és az értékben ugyanazok);
//   - környezet: `Törlés|gomb` (kisbetűs azonosító a `|` után) — csak kétértelmű magyar szónál; a hiányzó fordítás is a `|` nélküli szöveg;
//   - többes szám: `<kulcs>|one` és `<kulcs>|other` (az angolban; kötelező pár), opcionálisan `<kulcs>|zero` ("No notes");
//   - core-hibakód: `hiba.<kod>` (pl. `hiba.vault.nem_elerheto`) → angol mondat a core `param` mezőivel; a core magyar `hiba` szövege a tartalék;
//   - egy fájl egy partíciót fed: `en/{szerkeszto,hej,nezetek,modulok,oldalak,lib,core,parancsok}.json`.
// Hangnem: rövid, nyugodt, mondatkezdő nagybetű, felkiáltójel nélkül; a szószedet a CLAUDE.md-ben és a PLAN P2 döntésben.

import { nyelv, type Nyelv } from './nyelv.svelte';

export { nyelv, nyelvBetolt, nyelvKod, NYELVEK, ALAP_NYELV, type Nyelv } from './nyelv.svelte';

/** A `{nev}` helyettesítések értékei. */
export type Param = Record<string, string | number | boolean>;

// --- szótárak ---------------------------------------------------------------------------------------------------------------

type Szotar = Record<string, string>;

const FAJLOK = import.meta.glob<Szotar>('./*/*.json', { eager: true, import: 'default' });

/** A betöltött szótárfájlok: `{ "./en/lib.json": {…}, … }` (a tesztek ellenőrzik: azonos kulcs azonos értékkel, `{param}`-egyezés). */
export function szotarFajlok(): Record<string, Szotar> {
  return FAJLOK;
}

function egyesit(): Partial<Record<Nyelv, Szotar>> {
  const ki: Record<string, Szotar> = {};
  for (const [ut, tartalom] of Object.entries(FAJLOK)) {
    const kod = ut.split('/')[1]; // './en/lib.json' → 'en'
    Object.assign((ki[kod] ??= {}), tartalom);
  }
  return ki;
}

const SZOTAR = egyesit();

// --- kulcs-alak -------------------------------------------------------------------------------------------------------------

/** A kulcs végi környezet-utótag: `Törlés|gomb` (kisbetűs ASCII azonosító a `|` után). A magyar szöveg és a hiányzó fordítás a
 *  nélküle vett kulcs. (A többes szám kategóriája a `tp()`-ben a kulcs UTÁN jön: `{n} fájl|lista|one`.) */
const KONTEXTUS = /\|[a-z][a-z0-9_.-]*$/;

/** A kulcs a környezet-utótag nélkül: a megjelenő magyar szöveg. */
export function alapSzoveg(kulcs: string): string {
  return String(kulcs ?? '').replace(KONTEXTUS, '');
}

const HELYETTESITES = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

/** `{nev}` → érték, egyetlen menetben (a behelyettesített érték nem értelmeződik újra); ismeretlen név marad. ICU-mentes. */
export function helyettesit(szoveg: string, param?: Param): string {
  if (!param) return szoveg;
  return szoveg.replace(HELYETTESITES, (egesz, nev: string) => (Object.hasOwn(param, nev) ? String(param[nev]) : egesz));
}

// --- keresés ----------------------------------------------------------------------------------------------------------------

function keres(kulcs: string): string | undefined {
  const sz = SZOTAR[nyelv.kod]; // a `nyelv.kod` olvasása köt a reaktív követéshez
  return sz && Object.hasOwn(sz, kulcs) ? sz[kulcs] : undefined;
}

/**
 * CSAK TESZTHEZ: ideiglenes szótár-kiegészítés egy nyelvhez (a futásidejű szótár a `en/*.json` fájlokból jön). A visszaadott függvény
 * visszaállítja az előző állapotot. Nem reaktív: a már számolt `$derived`/`$effect` a nyelvváltáskor frissül, nem a kiegészítéskor.
 */
export function szotarKiegeszit(kod: Nyelv, szotar: Szotar): () => void {
  const sz = (SZOTAR[kod] ??= {});
  const elozo = new Map<string, string | undefined>(Object.keys(szotar).map((k) => [k, Object.hasOwn(sz, k) ? sz[k] : undefined]));
  Object.assign(sz, szotar);
  return () => {
    for (const [k, v] of elozo) {
      if (v === undefined) delete sz[k];
      else sz[k] = v;
    }
  };
}

/** Az aktív nyelv fordítása, ha van; különben `undefined` (a `hu` nyelvnek nincs szótára). A core-hibakódoknál (`hiba.<kod>`) kell:
 *  ott a tartalék a core magyar mondata, nem a kulcs. */
export function tHaVan(kulcs: string, param?: Param): string | undefined {
  const sz = keres(kulcs);
  return sz === undefined ? undefined : helyettesit(sz, param);
}

// --- t() / tp() / tk() ------------------------------------------------------------------------------------------------------

/**
 * A felület szövege az aktív nyelven. `kulcs` a magyar szöveg (opcionálisan `|környezet` utótaggal a kétértelmű szavakhoz);
 * `param` a `{nev}` helyettesítések. Nem kulcs-alakú (dinamikus) szöveget ne adj át: a kulcsnak egy fordítható, állandó szövegnek
 * kell lennie. Reaktív: a Svelte-sablonban és a `$derived`-ben nyelvváltáskor újraszámolódik.
 */
export function t(kulcs: string, param?: Param): string {
  return helyettesit(keres(kulcs) ?? alapSzoveg(kulcs), param);
}

const SOROK = new Map<string, Intl.PluralRules>();

function kategoria(n: number): Intl.LDMLPluralRule {
  let sor = SOROK.get(nyelv.kod);
  if (!sor) SOROK.set(nyelv.kod, (sor = new Intl.PluralRules(nyelv.locale)));
  return sor.select(n);
}

/**
 * Többes szám: `tp('{n} jegyzet', n)`. A szótár kulcsai `<kulcs>|<kategória>`, a kategória a CLDR szerinti (`one`, `other`, …;
 * az angolban `one`/`other`), plusz a nyelvtől független `zero` (n = 0). Keresési sorrend: `<kulcs>|zero` (ha n = 0), `<kulcs>|<kat>`,
 * `<kulcs>|other`, `<kulcs>` (egyalakú bejegyzés), végül a magyar kulcs (a magyar nem ragoz számnév után). `{n}` mindig
 * helyettesítődik; a `param` további helyettesítésekhez. Környezettel: `tp('{n} fájl|lista', n)` → `{n} fájl|lista|one`.
 */
export function tp(kulcs: string, n: number, param?: Param): string {
  const sz = (k: string) => keres(`${kulcs}|${k}`);
  const talalat = (n === 0 ? sz('zero') : undefined) ?? sz(kategoria(n)) ?? sz('other') ?? keres(kulcs) ?? alapSzoveg(kulcs);
  return helyettesit(talalat, { ...param, n });
}

/**
 * Fordítási jelölő (mint a gettext `N_()`): a kulcsot változatlanul adja vissza, de a forráskód-vizsgálat (ratchet és lefedettség)
 * fordítandó szövegnek tekinti. Táblázatban, állandóban, regisztrációban álló szövegre (`nev: tk('Kártyák ebből')`); a megjelenítés
 * helyén `t(...)` fordít (a regiszter és a paletta ezt teszi a parancsnevekkel), így nyelvváltáskor frissül.
 */
export function tk<T extends string>(kulcs: T): T {
  return kulcs;
}

/** Az `Intl` nyelvi címkéje az aktív nyelvhez (dátum, szám, rendezés): `new Intl.Collator(locale())`. Reaktív. */
export function locale(): string {
  return nyelv.locale;
}
