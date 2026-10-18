// A nézet-beállítások tiszta függvényei (C12b, 8. lépés): a felület gesztusából (fejléc-kattintás, húzás, menü)
// a core `modosit` műveletei. DOM nincs benne, így külön tesztelhető; a core a `.base` nyers YAML-ján dolgozik,
// ezért a nézet `beallitas`-a (a nyers kulcsok) az igazság, nem a válasz oszlopai.

import type { Muvelet, Valasz } from './tipusok';
import { tk } from '../lib/i18n';
import { elerhetoNev, oszlopNev } from './nevek';

export type Irany = 'ASC' | 'DESC';
export interface Rendezes {
  property: string;
  direction: Irany;
}

export const MIN_SZELESSEG = 60;
export const MAX_SZELESSEG = 900;

/** A beépített összesítők (Obsidian) magyar névvel; a kulcs a `.base`-ben álló név. */
export const OSSZESITOK: ReadonlyArray<{ nev: string; felirat: string }> = [
  { nev: 'Average', felirat: tk('Átlag') },
  { nev: 'Min', felirat: tk('Minimum') },
  { nev: 'Max', felirat: tk('Maximum') },
  { nev: 'Sum', felirat: tk('Összeg') },
  { nev: 'Range', felirat: tk('Terjedelem') },
  { nev: 'Median', felirat: tk('Medián') },
  { nev: 'Stddev', felirat: tk('Szórás') },
  { nev: 'Earliest', felirat: tk('Legkorábbi') },
  { nev: 'Latest', felirat: tk('Legkésőbbi') },
  { nev: 'Checked', felirat: tk('Bejelölt') },
  { nev: 'Unchecked', felirat: tk('Üres jelölő') },
  { nev: 'Empty', felirat: tk('Üres') },
  { nev: 'Filled', felirat: tk('Kitöltött') },
  { nev: 'Unique', felirat: tk('Egyedi') },
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

// ------------------------------------------------------------------ rendezés-szerkesztő (10-bases-04)

/** Új rendezési kulcs a lista végére (a már szereplő tulajdonság nem kerül be kétszer). */
export function rendezesHozzaad(lista: Rendezes[], azon: string, irany: Irany = 'ASC'): Rendezes[] {
  return lista.some((r) => r.property === azon) ? lista : [...lista, { property: azon, direction: irany }];
}

export function rendezesTorol(lista: Rendezes[], i: number): Rendezes[] {
  return lista.filter((_, n) => n !== i);
}

/** A kulcs egy hellyel feljebb (`d = -1`, nagyobb prioritás) vagy lejjebb (`d = 1`). */
export function rendezesMozgat(lista: Rendezes[], i: number, d: -1 | 1): Rendezes[] {
  const j = i + d;
  if (i < 0 || j < 0 || i >= lista.length || j >= lista.length) return lista;
  const ki = [...lista];
  [ki[i], ki[j]] = [ki[j], ki[i]];
  return ki;
}

export function rendezesIranyFordit(lista: Rendezes[], i: number): Rendezes[] {
  return lista.map((r, n) => (n === i ? { ...r, direction: r.direction === 'ASC' ? 'DESC' : 'ASC' } : r));
}

/** Az i. kulcs tulajdonságának cseréje (ha a másik kulcs már szerepel, a csere nem történik meg). */
export function rendezesTulajdonsag(lista: Rendezes[], i: number, azon: string): Rendezes[] {
  if (lista.some((r, n) => n !== i && r.property === azon)) return lista;
  return lista.map((r, n) => (n === i ? { ...r, property: azon } : r));
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

/** A tulajdonság-azonosító olvasható neve a választóban (`note.x` → `x`, `file.name` → `File name`…; a `file.*` alapnév fordítva). */
export function azonosNev(v: Valasz, azon: string): string {
  const o = v.oszlopok.find((x) => x.id === azon);
  if (o) return oszlopNev(o);
  const e = v.fajl?.elerheto.find((x) => x.id === azon);
  return e ? elerhetoNev(e) : azon.replace(/^(note|formula)\./, '');
}
