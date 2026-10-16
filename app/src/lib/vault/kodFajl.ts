// A kód-munkafelület nyelvei a fájlfa, az ikonok és a kód-fül számára (F10): a `kod-nyelvek.json` a `core/kod_nyelvek.py` profiljainak
// tükre (a `tests/test_kod_ui_nyelvek.py` őrzi az egyezést), a szerkeszthető kiterjesztések a core `vaultio.IRHATO`-jával azonosak.
// Tiszta adat és függvények: nincs hálózat, nincs állapot — a `lib` többi része is innen kérdez, nem kézzel vezetett listából.

import adat from './kod-nyelvek.json';

export interface KodNyelv {
  /** a core profil-azonosítója (`cpp`, `python`, …) */
  azonosito: string;
  /** a nyelv megjelenő neve (tulajdonnév, nem fordítandó) */
  nev: string;
  /** a szerkeszthető kiterjesztések kisbetűvel, ponttal; az első a kanonikus */
  kiterjesztesek: readonly string[];
  /** a jegyzet kódblokkjának elfogadott nyelvjelölői (` ```python `) */
  kerites: readonly string[];
  /** a router feladata ehhez a nyelvhez (D9: nyelvenként külön kalibrálva) */
  kalibracios_kulcs: string;
  /** `cpp`: a C36a motor (C és C++), `nyelv`: az általános motor */
  motor: 'cpp' | 'nyelv';
  /** van-e hibakereső (sanitizer) mód */
  hibakereso: boolean;
  /** az „ellenőrzés” lépés csak szintaxis-vizsgálat (értelmezett nyelv), nem fordítás */
  elemzes: boolean;
}

/** A kiterjesztések, amelyeket a core nem enged szerkeszteni (a pillanatkép bináris-ként zárja ki, pl. `.mts`). */
const NEM_SZERKESZTHETO = new Set((adat.nem_szerkesztheto as string[]).map((k) => k.toLowerCase()));

export const KOD_NYELVEK: readonly KodNyelv[] = (adat.nyelvek as unknown as KodNyelv[]).map((n) => ({
  ...n,
  kiterjesztesek: n.kiterjesztesek.filter((k) => !NEM_SZERKESZTHETO.has(k.toLowerCase())),
}));

const KIT_NYELV = new Map<string, KodNyelv>(KOD_NYELVEK.flatMap((n) => n.kiterjesztesek.map((k) => [k.toLowerCase(), n] as const)));

const kiterjesztes = (ut: string): string => {
  const i = ut.lastIndexOf('.');
  return i < 0 || ut.indexOf('/', i) >= 0 ? '' : ut.slice(i).toLowerCase();
};

const esc = (k: string) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Minden szerkeszthető forrás-kiterjesztés (az `ut` vége): ez dönti el, hogy egy fájl kód-fület kap-e. */
export const KOD_KITERJESZTESEK: readonly string[] = [...KIT_NYELV.keys()];

/** Igaz, ha az út egy ismert nyelv szerkeszthető forrásfájlja (kis-nagybetűtől függetlenül). */
export const KOD_UT = new RegExp(`(?:${[...KOD_KITERJESZTESEK].sort((a, b) => b.length - a.length).map(esc).join('|')})$`, 'i');

/** A beágyazott forrás a jegyzetben (`![[x.py]]`, opcionális `#alcím` / `|méret`): csak felismerés, a feloldás a core-é. */
export const BEAGYAZOTT_KOD = new RegExp(`!\\[\\[[^\\]|#\\n]+?(?:${[...KOD_KITERJESZTESEK].sort((a, b) => b.length - a.length).map(esc).join('|')})(?:#[^\\]|\\n]*)?(?:\\|[^\\]\\n]*)?\\]\\]`, 'i');

/** Az első beágyazott forrás a jegyzet szövegéből (a core is az elsőt választja): az útja, vagy `null`. */
export function elsoBeagyazottKod(szoveg: string): string | null {
  const m = new RegExp(BEAGYAZOTT_KOD.source, 'i').exec(szoveg);
  return m ? m[0].slice(3).replace(/(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]$/, '') : null;
}

/** Az út nyelve a kiterjesztés alapján; nem forrásfájl: `null`. */
export function nyelvUt(ut: string | null | undefined): KodNyelv | null {
  return ut ? (KIT_NYELV.get(kiterjesztes(ut)) ?? null) : null;
}

/** A nyelv azonosító szerint. */
export function nyelvAzonosito(azonosito: string | null | undefined): KodNyelv | null {
  return KOD_NYELVEK.find((n) => n.azonosito === azonosito) ?? null;
}

/** A jegyzet kódblokkjának nyelvjelölőjéből (` ```py `) a nyelv; ismeretlen jelölő: `null`. */
export function nyelvKeritesbol(jelolo: string | null | undefined): KodNyelv | null {
  const j = (jelolo ?? '').trim().split(/\s+/)[0]?.toLowerCase();
  return j ? (KOD_NYELVEK.find((n) => n.kerites.includes(j)) ?? null) : null;
}
