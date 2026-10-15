// A Bases-értékek magyar megjelenítése (C12): szám, dátum, lista, link, címke. A core a típusos JSON-alakot adja
// (`Ertek`); itt készül belőle a cella szövege. A formázás nem módosít értéket (a cellaszerkesztés a nyers értékhez nyúl).

import type { Ertek } from './tipusok';

const szamFormatum = new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 6 });
const datumFormatum = new Intl.DateTimeFormat('hu-HU', { year: 'numeric', month: '2-digit', day: '2-digit' });
const datumIdoFormatum = new Intl.DateTimeFormat('hu-HU', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

export function szamSzoveg(n: number): string {
  return Number.isInteger(n) && Math.abs(n) >= 10_000 ? String(n) : szamFormatum.format(n);
}

/** A `YYYY-MM-DD[THH:mm:ss]` ISO-szöveg helyi időként (a core naiv, helyi időt ad). */
export function datumSzoveg(iso: string, ido: boolean): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(iso);
  if (!m) return iso;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4] ?? 0), Number(m[5] ?? 0), Number(m[6] ?? 0));
  return (ido ? datumIdoFormatum : datumFormatum).format(d);
}

export type ErtekFajta =
  | 'ures'
  | 'logikai'
  | 'szam'
  | 'szoveg'
  | 'lista'
  | 'datum'
  | 'link'
  | 'cimke'
  | 'hiba'
  | 'kep'
  | 'egyeb';

export function fajta(e: Ertek): ErtekFajta {
  if (e === null || e === undefined) return 'ures';
  if (typeof e === 'boolean') return 'logikai';
  if (typeof e === 'number') return 'szam';
  if (typeof e === 'string') return 'szoveg';
  switch (e.t) {
    case 'lista':
      return 'lista';
    case 'datum':
      return 'datum';
    case 'link':
      return 'link';
    case 'cimke':
      return 'cimke';
    case 'hiba':
      return 'hiba';
    case 'kep':
      return 'kep';
    default:
      return 'egyeb';
  }
}

/** Az érték egyszerű szövege (a cella `title`-je, a szűréshez és a kimásoláshoz). */
export function ertekSzoveg(e: Ertek): string {
  if (e === null || e === undefined) return '';
  if (typeof e === 'boolean') return e ? 'igen' : 'nem';
  if (typeof e === 'number') return szamSzoveg(e);
  if (typeof e === 'string') return e;
  switch (e.t) {
    case 'szam':
      return e.v === 'NaN' ? 'NaN' : e.v === 'Infinity' ? '∞' : '−∞';
    case 'lista':
      return e.e.map(ertekSzoveg).join(', ');
    case 'objektum':
      return Object.entries(e.e)
        .map(([k, v]) => `${k}: ${ertekSzoveg(v)}`)
        .join(', ');
    case 'datum':
      return datumSzoveg(e.iso, e.ido);
    case 'idotartam':
      return e.szoveg;
    case 'link':
      return e.nev;
    case 'cimke':
      return e.v;
    case 'regex':
      return e.v;
    case 'kep':
      return e.ut ?? e.url ?? e.szin ?? '';
    case 'ikon':
      return e.nev;
    case 'html':
      return e.v;
    case 'hiba':
      return `Hiba: ${e.u}`;
  }
}

/** A csoportfejléc és az összesítő rövid szövege. */
export function osszesitoSzoveg(e: Ertek): string {
  return ertekSzoveg(e);
}
