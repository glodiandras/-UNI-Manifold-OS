// A vezérlő megjelenítési segédei (C17): magyar feliratok és rövid idő-/méretformák. Tiszta függvények.

import { t, tHaVan, tk, locale } from '../i18n';
import { kodUzenet } from '../core/api';

import type { Feladat, FeladatAllapot } from './tipusok';

/** A core régi, állandó feladatszövegei a szótárból jönnek. A dinamikus szöveg és a benne lévő felhasználói adat érintetlen. */
export const feladatSzoveg = (szoveg: string): string => tHaVan(szoveg) ?? szoveg;

/** Új core: hibakód + paraméterek; régebbi core: a kész hibaüzenet. */
export const feladatHiba = (feladat: Feladat): string => kodUzenet(feladat);

const CIMKE: Record<FeladatAllapot, string> = {
  sorban: tk('Várakozik'),
  fut: tk('Fut'),
  kesz: tk('Kész|allapot'),
  hiba: tk('Hiba|allapot'),
  megallitva: tk('Megállítva'),
  torolve: tk('Törölve'),
  megszakadt: tk('Megszakadt'),
};

export const allapotCimke = (a: FeladatAllapot): string => (CIMKE[a] ? t(CIMKE[a]) : a);

/** A haladás szövege: `2/5. lépés · 40 %`; sorban álló feladatnál üres. */
export function haladasSzoveg(f: Feladat): string {
  if (f.allapot === 'sorban') return '';
  const n = f.lepesek.length;
  const lepes = n > 1 ? t('{i}/{n}. lépés · ', { i: Math.min(f.lepes_i + 1, n), n }) : '';
  return `${lepes}${Math.round(f.szazalek)} %`;
}

/** `14:03` ma, különben `okt. 2. 14:03`. */
export function idoRovid(iso: string | null, most: Date = new Date()): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const ora = new Intl.DateTimeFormat(locale(), { hour: '2-digit', minute: '2-digit' }).format(d);
  if (d.toDateString() === most.toDateString()) return ora;
  return `${new Intl.DateTimeFormat(locale(), { month: 'short', day: 'numeric' }).format(d)} ${ora}`;
}

/** A feladat időtartama a befejezett feladatnál: `3 mp`, `2 p 14 mp`, `1 ó 05 p`. */
export function idotartam(f: Feladat): string {
  if (!f.indult || !f.vegzett) return '';
  const mp = Math.round((new Date(f.vegzett).getTime() - new Date(f.indult).getTime()) / 1000);
  if (!Number.isFinite(mp) || mp < 0) return '';
  if (mp < 60) return t('{n} mp', { n: mp });
  if (mp < 3600) return t('{p} p {mp} mp', { p: Math.floor(mp / 60), mp: String(mp % 60).padStart(2, '0') });
  return t('{ora} ó {perc} p', { ora: Math.floor(mp / 3600), perc: String(Math.floor((mp % 3600) / 60)).padStart(2, '0') });
}

const szam = { format: (x: number) => new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(x) };
export const gb = (x: number): string => `${szam.format(x)} GB`;
export const mb = (x: number): string => (x >= 1024 ? gb(x / 1024) : `${szam.format(x)} MB`);

/** Egy fájl-út neve és mappája a változáslistához. */
export function utReszei(ut: string): { nev: string; mappa: string } {
  const i = ut.lastIndexOf('/');
  return i < 0 ? { nev: ut, mappa: '' } : { nev: ut.slice(i + 1), mappa: ut.slice(0, i) };
}
