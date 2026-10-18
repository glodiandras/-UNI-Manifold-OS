// A Bases-nézet másolása és CSV-exportja (10-bases-09): tiszta függvények a `lekerdez` válaszán (nincs core-hívás). A csoportosított
// nézet egy „Csoport” oszlopot kap. A CSV RFC 4180 szerinti (idézőjel, CRLF); a táblázatkezelők képletként futtatnák az `=`, `+`, `-`,
// `@` (és tab / CR) jellel kezdődő szöveg-cellát, ezért az ilyen cella elé `'` kerül (CSV-injekció elleni védelem). A tényleges
// számérték (a core számként adta) nem szöveg, ezért előtag nélkül marad; a vágólapra másolás ugyanezt a védelmet használja.

import { t, tk } from '../lib/i18n';
import { ertekSzoveg } from './ertek';
import { oszlopNev } from './nevek';
import type { Ertek, Valasz } from './tipusok';

export interface Tablazat {
  fejlec: string[];
  /** a cellák szövege; `szam`: igaz, ha a cella a core tényleges számértéke (nem kell injekció-védelem) */
  sorok: Array<Array<{ szoveg: string; szam: boolean }>>;
}

const VESZELYES_KEZDET = /^[=+\-@\t\r]/;
export const CSOPORT_FEJLEC = tk('Csoport');

/** A táblázatkezelő számára képletnek látszó szöveg-cella elé `'` (nem szám). */
export function cellaBiztos(szoveg: string, szam = false): string {
  return !szam && VESZELYES_KEZDET.test(szoveg) ? `'${szoveg}` : szoveg;
}

/** Az érték gépi-barát szövege az exporthoz: ISO dátum, `true`/`false`, a lista vesszővel, a szám nyersen. */
export function exportSzoveg(e: Ertek): string {
  if (e === null || e === undefined) return '';
  if (typeof e === 'boolean') return e ? 'true' : 'false';
  if (typeof e === 'number') return String(e);
  if (typeof e === 'string') return e;
  switch (e.t) {
    case 'datum':
      return e.ido ? e.iso.replace('T', ' ') : e.iso;
    case 'lista':
      return e.e.map(exportSzoveg).join(', ');
    case 'html':
      return e.v;
    default:
      return ertekSzoveg(e);
  }
}

export function tablazat(v: Valasz): Tablazat {
  const csoportos = !!v.csoportok;
  const fejlec = [...(csoportos ? [t(CSOPORT_FEJLEC)] : []), ...v.oszlopok.map((o) => oszlopNev(o))];
  const csoportCimke = (i: number): string => {
    const cs = v.csoportok?.find((c) => i >= c.tol && i < c.tol + c.db);
    return cs ? cs.cimke : '';
  };
  const sorok = v.sorok.map((s, i) => {
    const cellak = s.cellak.map((e) => ({ szoveg: exportSzoveg(e), szam: typeof e === 'number' && Number.isFinite(e) }));
    return csoportos ? [{ szoveg: csoportCimke(i), szam: false }, ...cellak] : cellak;
  });
  return { fejlec, sorok };
}

function csvMezo(szoveg: string): string {
  return /[",\r\n]|^\s|\s$/.test(szoveg) ? `"${szoveg.replace(/"/g, '""')}"` : szoveg;
}

/** RFC 4180 CSV (CRLF sorvég, záró sorvéggel); az injekció-védett cellák után kerül az idézés. */
export function csv(tab: Tablazat): string {
  const sorok = [tab.fejlec.map((f) => csvMezo(cellaBiztos(f))), ...tab.sorok.map((s) => s.map((c) => csvMezo(cellaBiztos(c.szoveg, c.szam))))];
  return sorok.map((s) => s.join(',')).join('\r\n') + '\r\n';
}

/** Tabulátoros szöveg a vágólapra (táblázatkezelőbe illeszthető); a cellán belüli tab / sortörés szóközzé válik. */
export function tsv(tab: Tablazat): string {
  const tiszta = (s: string) => s.replace(/[\t\r\n]+/g, ' ');
  return [tab.fejlec.map((f) => tiszta(cellaBiztos(f))), ...tab.sorok.map((s) => s.map((c) => tiszta(cellaBiztos(c.szoveg, c.szam))))]
    .map((s) => s.join('\t'))
    .join('\n');
}

/** Markdown-táblázat a jegyzetbe illesztéshez (a `|` és a sortörés escape-elve). */
export function markdownTabla(tab: Tablazat): string {
  const tiszta = (s: string) => s.replace(/\|/g, '\\|').replace(/[\r\n]+/g, ' ');
  const sor = (cellak: string[]) => `| ${cellak.map(tiszta).join(' | ')} |`;
  return [sor(tab.fejlec), sor(tab.fejlec.map(() => '---')), ...tab.sorok.map((s) => sor(s.map((c) => c.szoveg)))].join('\n');
}

export type Kimenet = 'tsv' | 'markdown' | 'csv';

export function kimenetSzoveg(v: Valasz, fajta: Kimenet): string {
  const tab = tablazat(v);
  return fajta === 'csv' ? csv(tab) : fajta === 'markdown' ? markdownTabla(tab) : tsv(tab);
}
