// A fájlfa adatmodellje (C11a): a core lapos fájl- és mappalistájából fa, magyar ábécérenddel, mappák elöl,
// számlálókkal. Tiszta függvények (nincs DOM, nincs állapot): az `Fa.svelte` ezt rajzolja, a teszt ezt védi.
// A felület nem old fel linket és nem olvas fájlrendszert (ARCHITECTURE 2.): csak a core listáját mutatja.

import { locale } from '../i18n';

import type { FajlInfo, FajlTipus } from './fajlok.svelte';
import { fajlNev } from './fajlok.svelte';
import { KOD_UT } from './kodFajl';

export const FA_RENDEZESEK = ['nev', 'nev-forditva', 'modositva', 'modositva-regi', 'letrehozva', 'letrehozva-regi'] as const;
export type FaRendezes = typeof FA_RENDEZESEK[number];
export function faRendezes(ertek: unknown): FaRendezes { return FA_RENDEZESEK.includes(ertek as FaRendezes) ? ertek as FaRendezes : 'nev'; }
export function faIdoMezo(rendezes: FaRendezes): 'mtime' | 'ctime' | null {
  if (rendezes === 'modositva' || rendezes === 'modositva-regi') return 'mtime';
  if (rendezes === 'letrehozva' || rendezes === 'letrehozva-regi') return 'ctime';
  return null;
}

export interface FaCsomopont {
  /** a vault-relatív NFC út; a gyökér üres */
  ut: string;
  /** a megjelenített név: jegyzetnél kiterjesztés nélkül */
  nev: string;
  mappa: boolean;
  tipus?: FajlTipus;
  /** Valódi fájl-módosítási idő másodpercben. Ismeretlen érték nem kap kitalált dátumot. */
  mtime?: number | null;
  /** Valódi születési idő másodpercben; nincs mtime- vagy POSIX ctime-helyettesítés. */
  ctime?: number | null;
  gyerekek: FaCsomopont[];
  /** mappánál: a teljes részfa fájljainak száma (a szám a sor végén) */
  fajlok: number;
  /** mappánál: ebből jegyzet (md és canvas) */
  jegyzetek: number;
}

export interface FaSor {
  cs: FaCsomopont;
  /** 0 a gyökér közvetlen gyerekeinél */
  melyseg: number;
  /** a testvérek között hányadik és hány (aria-posinset / aria-setsize) */
  hely: number;
  testverek: number;
}

/** Magyar ábécé (cs, dz, gy, ly… digráfokkal), a számok értékük szerint (02 < 10), kis-nagybetű-érzéketlen elsődlegesen. */
let gyujtoKod = '';
let gyujtoCache: Intl.Collator | null = null;
const GYUJTO = {
  compare: (a: string, b: string) => {
    if (!gyujtoCache || gyujtoKod !== locale()) {
      gyujtoKod = locale();
      gyujtoCache = new Intl.Collator(gyujtoKod, { numeric: true, sensitivity: 'variant' });
    }
    return gyujtoCache.compare(a, b);
  },
};

export function nevHasonlit(a: string, b: string): number {
  return GYUJTO.compare(a, b);
}

function mappaNev(ut: string): string {
  return ut.slice(ut.lastIndexOf('/') + 1);
}

/** A fa a core listáiból. A `mappak` az üres mappákat is hozza; a fájlok szülőmappái hiányuk esetén is létrejönnek. */
export function faEpit(lista: readonly FajlInfo[], mappak: readonly string[], rendezes: FaRendezes = 'nev'): FaCsomopont {
  const idomezo = faIdoMezo(rendezes);
  const gyoker: FaCsomopont = { ut: '', nev: '', mappa: true, gyerekek: [], fajlok: 0, jegyzetek: 0 };
  const mappaTerkep = new Map<string, FaCsomopont>([['', gyoker]]);

  const mappaCsomopont = (ut: string): FaCsomopont => {
    let cs = mappaTerkep.get(ut);
    if (cs) return cs;
    cs = { ut, nev: mappaNev(ut), mappa: true, gyerekek: [], fajlok: 0, jegyzetek: 0 };
    mappaTerkep.set(ut, cs);
    const szulo = ut.includes('/') ? ut.slice(0, ut.lastIndexOf('/')) : '';
    mappaCsomopont(szulo).gyerekek.push(cs);
    return cs;
  };

  for (const m of mappak) if (m) mappaCsomopont(m);
  for (const f of lista) {
    const szulo = f.ut.includes('/') ? f.ut.slice(0, f.ut.lastIndexOf('/')) : '';
    mappaCsomopont(szulo).gyerekek.push({
      ut: f.ut, nev: fajlNev(f.ut), mappa: false, tipus: f.tipus,
      mtime: typeof f.mtime === 'number' && Number.isFinite(f.mtime) ? f.mtime : null,
      ctime: typeof f.ctime === 'number' && Number.isFinite(f.ctime) ? f.ctime : null,
      gyerekek: [], fajlok: 0, jegyzetek: 0,
    });
  }

  const rendez = (cs: FaCsomopont): void => {
    let fajlok = 0;
    let jegyzetek = 0;
    for (const g of cs.gyerekek) {
      if (g.mappa) {
        rendez(g);
        fajlok += g.fajlok;
        jegyzetek += g.jegyzetek;
      } else {
        fajlok += 1;
        jegyzetek += g.tipus === 'md' || g.tipus === 'canvas' ? 1 : 0;
      }
    }
    cs.fajlok = fajlok;
    cs.jegyzetek = jegyzetek;
    cs.gyerekek.sort((a, b) => {
      if (a.mappa !== b.mappa) return a.mappa ? -1 : 1;
      const nev = nevHasonlit(a.nev, b.nev) || nevHasonlit(a.ut, b.ut) || (a.ut < b.ut ? -1 : a.ut > b.ut ? 1 : 0);
      // A dátum-módokban a mappák név szerint maradnak; nincs kitalált mappa-dátum.
      if (!a.mappa && idomezo) {
        const ai = a[idomezo] ?? null, bi = b[idomezo] ?? null;
        if (ai === null || bi === null) return ai === bi ? nev : ai === null ? 1 : -1;
        return (rendezes === 'modositva' || rendezes === 'letrehozva' ? bi - ai : ai - bi) || nev;
      }
      return rendezes === 'nev-forditva' ? -nev : nev;
    });
  };
  rendez(gyoker);
  return gyoker;
}

/** A látható sorok lapos listája a nyitott mappák szerint (a gyökér maga nem sor). */
export function lapit(gyoker: FaCsomopont, nyitott: ReadonlySet<string>): FaSor[] {
  const ki: FaSor[] = [];
  const bejar = (cs: FaCsomopont, melyseg: number): void => {
    cs.gyerekek.forEach((g, i) => {
      ki.push({ cs: g, melyseg, hely: i + 1, testverek: cs.gyerekek.length });
      if (g.mappa && nyitott.has(g.ut)) bejar(g, melyseg + 1);
    });
  };
  bejar(gyoker, 0);
  return ki;
}

/** Az út összes ősmappája, a gyökértől lefelé (`a/b/c.md` → `a`, `a/b`). */
export function osMappak(ut: string): string[] {
  const reszek = ut.split('/');
  reszek.pop();
  return reszek.map((_, i) => reszek.slice(0, i + 1).join('/'));
}

/** Egy fájl vagy mappa új útja, ha a `celMappa` mappába húzzuk (a név megmarad). */
export function athelyezettUt(ut: string, celMappa: string): string {
  const nev = mappaNev(ut);
  return celMappa ? `${celMappa}/${nev}` : nev;
}

/** Áthelyezhető-e a `forras` (fájl vagy mappa) a `celMappa` mappába: nem önmagába vagy a saját részfájába, és nem oda,
 *  ahol már van (a szülő nem változna). */
export function athelyezheto(forras: string, forrasMappa: boolean, celMappa: string): boolean {
  if (forrasMappa && (celMappa === forras || celMappa.startsWith(forras + '/'))) return false;
  const szulo = forras.includes('/') ? forras.slice(0, forras.lastIndexOf('/')) : '';
  return szulo !== celMappa;
}

/** Kinyitás szélességi sorrendben: a szülők előbb látszanak, a már megjegyzett nyitások megmaradnak.
 *  A korlát csak új nyitásra vonatkozik; a meglevő állapotot egy kényelmi művelet nem csonkítja. */
export function mappakatKinyit(gyoker: FaCsomopont, meglevo: readonly string[], korlat: number): { utak: string[]; kimaradt: number } {
  const nyitott = new Set(meglevo), varo = [gyoker];
  let kimaradt = 0;
  for (let i = 0; i < varo.length; i++) {
    for (const g of varo[i].gyerekek) {
      if (!g.mappa) continue;
      varo.push(g);
      if (!nyitott.has(g.ut)) {
        if (nyitott.size < korlat) nyitott.add(g.ut);
        else kimaradt++;
      }
    }
  }
  return { utak: [...nyitott], kimaradt };
}

/** Nem támogatott fájltípus (07-explorer-12): az `egyeb` típus, kivéve a kód-munkafelület saját nézettel bíró forrásfájljait (F10). */
export function nemTamogatott(f: Pick<FajlInfo, 'ut' | 'tipus'>): boolean {
  return f.tipus === 'egyeb' && !KOD_UT.test(f.ut);
}

/** A fán látszó fájlok: a nem támogatottak rejtve, ha `mindenFajl` hamis (az Obsidian `showUnsupportedFiles`-ának megfelelője). */
export function lathatoFajlok(lista: readonly FajlInfo[], mindenFajl: boolean): readonly FajlInfo[] {
  return mindenFajl ? lista : lista.filter((f) => !nemTamogatott(f));
}

/** A kijelölés legfelső elemei (07-explorer-04): ha egy mappa és a részfájának eleme is ki van jelölve, csak a mappa marad,
 *  hogy a tömeges művelet ne dolgozzon kétszer ugyanazon. A sorrend az eredeti. */
export function legfelsoUtak(utak: readonly string[]): string[] {
  const halmaz = new Set(utak);
  return [...halmaz].filter((u) => {
    for (let szulo = u.includes('/') ? u.slice(0, u.lastIndexOf('/')) : ''; szulo; szulo = szulo.includes('/') ? szulo.slice(0, szulo.lastIndexOf('/')) : '')
      if (halmaz.has(szulo)) return false;
    return true;
  });
}

/** Shift-kijelölés: a látható sorok `honnan`–`meddig` tartománya (mindkét vég benne); ismeretlen horgonynál csak a `meddig`. */
export function kijelolesTartomany(sorok: readonly FaSor[], honnan: string | null, meddig: string): string[] {
  const j = sorok.findIndex((s) => s.cs.ut === meddig);
  if (j < 0) return [];
  const i = honnan === null ? j : sorok.findIndex((s) => s.cs.ut === honnan);
  if (i < 0) return [meddig];
  const [a, b] = i <= j ? [i, j] : [j, i];
  return sorok.slice(a, b + 1).map((s) => s.cs.ut);
}
