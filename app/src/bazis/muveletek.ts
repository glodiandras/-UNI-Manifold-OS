// A nézet-beállítások tiszta függvényei (C12b, 8. lépés): a felület gesztusából (fejléc-kattintás, húzás, menü)
// a core `modosit` műveletei. DOM nincs benne, így külön tesztelhető; a core a `.base` nyers YAML-ján dolgozik,
// ezért a nézet `beallitas`-a (a nyers kulcsok) az igazság, nem a válasz oszlopai.

import type { Muvelet, Valasz } from './tipusok';

export type Irany = 'ASC' | 'DESC';
export interface Rendezes {
  property: string;
  direction: Irany;
}

export const MIN_SZELESSEG = 60;
export const MAX_SZELESSEG = 900;

/** A beépített összesítők (Obsidian) magyar névvel; a kulcs a `.base`-ben álló név. */
export const OSSZESITOK: ReadonlyArray<{ nev: string; felirat: string }> = [
  { nev: 'Average', felirat: 'Átlag' },
  { nev: 'Min', felirat: 'Minimum' },
  { nev: 'Max', felirat: 'Maximum' },
  { nev: 'Sum', felirat: 'Összeg' },
  { nev: 'Range', felirat: 'Terjedelem' },
  { nev: 'Median', felirat: 'Medián' },
  { nev: 'Stddev', felirat: 'Szórás' },
  { nev: 'Earliest', felirat: 'Legkorábbi' },
  { nev: 'Latest', felirat: 'Legkésőbbi' },
  { nev: 'Checked', felirat: 'Bejelölt' },
  { nev: 'Unchecked', felirat: 'Üres jelölő' },
  { nev: 'Empty', felirat: 'Üres' },
  { nev: 'Filled', felirat: 'Kitöltött' },
  { nev: 'Unique', felirat: 'Egyedi' },
];

function nyers(v: Valasz): Record<string, unknown> {
  return v.nezet?.beallitas ?? {};
}

export function rendezesek(v: Valasz): Rendezes[] {
  const s = nyers(v).sort;
  if (!Array.isArray(s)) return [];
  const ki: Rendezes[] = [];
  for (const e of s) {
    if (e && typeof e === 'object' && typeof (e as Rendezes).property === 'string')
      ki.push({
        property: (e as Rendezes).property,
        direction: String((e as Rendezes).direction ?? 'ASC').toUpperCase() === 'DESC' ? 'DESC' : 'ASC',
      });
  }
  return ki;
}

/** A fejléc-kattintás: nincs → növekvő → csökkenő → nincs. `hozzaad` (⇧): a többi rendezés megmarad, ez a
 *  sor végére kerül (vagy a helyén vált). Alapból a kattintott oszlop az egyetlen rendezés. */
export function rendezesValt(jelenlegi: Rendezes[], azon: string, hozzaad: boolean): Rendezes[] {
  const i = jelenlegi.findIndex((r) => r.property === azon);
  const kovetkezo: Irany | null = i < 0 ? 'ASC' : jelenlegi[i].direction === 'ASC' ? 'DESC' : null;
  if (hozzaad) {
    const lista = jelenlegi.filter((r) => r.property !== azon);
    if (kovetkezo === null) return lista;
    if (i >= 0) {
      const ki = [...jelenlegi];
      ki[i] = { property: azon, direction: kovetkezo };
      return ki;
    }
    return [...lista, { property: azon, direction: kovetkezo }];
  }
  return kovetkezo === null ? [] : [{ property: azon, direction: kovetkezo }];
}

export function rendezesBeallit(nezet: number, lista: Rendezes[]): Muvelet {
  return { fajta: 'nezet_beallit', nezet, kulcs: 'sort', ertek: lista.length ? lista : null };
}

/** Egy oszlop rendezése kifejezetten az adott irányba (a fejléc-menüből), a többi rendezést eldobva. */
export function rendezesIrany(nezet: number, azon: string, irany: Irany): Muvelet {
  return rendezesBeallit(nezet, [{ property: azon, direction: irany }]);
}

export function oszlopAzonok(v: Valasz): string[] {
  return v.oszlopok.map((o) => o.id);
}

export function sorrendBeallit(nezet: number, azonok: string[]): Muvelet {
  return { fajta: 'nezet_beallit', nezet, kulcs: 'order', ertek: azonok };
}

/** Az oszlop új helye (`cel`: a végleges index a többi elem eltávolítása után). */
export function oszlopMozgat(azonok: string[], azon: string, cel: number): string[] {
  const i = azonok.indexOf(azon);
  if (i < 0) return azonok;
  const ki = azonok.filter((a) => a !== azon);
  ki.splice(Math.max(0, Math.min(ki.length, cel)), 0, azon);
  return ki;
}

/** Egy oszlop kijelölése / elrejtése a `order`-ben (a megjelenített oszlopok sorrendje megmarad). */
export function oszlopKapcsol(azonok: string[], azon: string, lathato: boolean): string[] {
  const van = azonok.includes(azon);
  if (lathato) return van ? azonok : [...azonok, azon];
  return azonok.filter((a) => a !== azon);
}

export function szelessegKorlat(px: number): number {
  return Math.round(Math.min(MAX_SZELESSEG, Math.max(MIN_SZELESSEG, px)));
}

export function szelessegBeallit(nezet: number, azon: string, px: number): Muvelet {
  return { fajta: 'nezet_beallit', nezet, kulcs: 'columnSize', alkulcs: azon, ertek: szelessegKorlat(px) };
}

export function osszesitoBeallit(nezet: number, azon: string, nev: string | null): Muvelet {
  return { fajta: 'nezet_beallit', nezet, kulcs: 'summaries', alkulcs: azon, ertek: nev };
}

export function csoport(v: Valasz): Rendezes | null {
  const g = nyers(v).groupBy;
  if (g && typeof g === 'object' && typeof (g as Rendezes).property === 'string')
    return {
      property: (g as Rendezes).property,
      direction: String((g as Rendezes).direction ?? 'ASC').toUpperCase() === 'DESC' ? 'DESC' : 'ASC',
    };
  return null;
}

export function csoportBeallit(nezet: number, azon: string | null, irany: Irany = 'ASC'): Muvelet {
  return {
    fajta: 'nezet_beallit',
    nezet,
    kulcs: 'groupBy',
    ertek: azon ? { property: azon, direction: irany } : null,
  };
}

export function nezetKulcs(nezet: number, kulcs: string, ertek: unknown): Muvelet {
  return { fajta: 'nezet_beallit', nezet, kulcs, ertek: ertek === '' ? null : ertek };
}

/** A pozitív egész beírt szövege (limit, cardSize); az üres: nincs beállítás (`null`); a hibás: `undefined`. */
export function egeszBevitel(szoveg: string): number | null | undefined {
  const s = szoveg.trim();
  if (s === '') return null;
  if (!/^\d+$/.test(s)) return undefined;
  const n = Number(s);
  return n > 0 && Number.isSafeInteger(n) ? n : undefined;
}

/** A tulajdonság-azonosító olvasható neve a választóban (`note.x` → `x`, `file.name` → `Fájlnév`…). */
export function azonosNev(v: Valasz, azon: string): string {
  const o = v.oszlopok.find((x) => x.id === azon);
  if (o) return o.nev;
  const e = v.fajl?.elerheto.find((x) => x.id === azon);
  return e?.nev ?? azon.replace(/^(note|formula)\./, '');
}
