// A tracker megjelenítési segédei (C27): idő, szám és dátum magyar szövege.

/** A helyi nap ÉÉÉÉ-HH-NN alakban (a core is helyi napban aggregál). */
import { t, tk, locale } from '../i18n';
export function maiNap(d = new Date()): string {
  const k = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${k(d.getMonth() + 1)}-${k(d.getDate())}`;
}

/** A nap eltolása `n` nappal (helyi nap; a DST nem számít, mert déli időponttal számol). */
export function napEltol(nap: string, n: number): string {
  const [y, h, d] = nap.split('-').map(Number);
  return maiNap(new Date(y, h - 1, d + n, 12));
}

export function idoSzoveg(mp: number): string {
  if (!Number.isFinite(mp) || mp <= 0) return t('0 p');
  if (mp < 60) return t('{n} mp', { n: Math.round(mp) });
  const perc = Math.round(mp / 60);
  const ora = Math.floor(perc / 60);
  return ora ? t('{ora} ó {perc} p', { ora, perc: String(perc % 60).padStart(2, '0') }) : t('{perc} p', { perc });
}

export function szamSzoveg(n: number): string {
  return new Intl.NumberFormat(locale()).format(n);
}

export function msSzoveg(ms: number | null): string {
  if (ms === null || ms === undefined) return '–';
  if (ms >= 1000) return `${(ms / 1000).toLocaleString(locale(), { maximumFractionDigits: 1 })} s`;
  return `${Number.isInteger(ms) ? ms : ms.toFixed(1)} ms`;
}

export function szazalekSzoveg(r: number | null): string {
  return r === null || r === undefined ? '–' : `${Math.round(r * 100)} %`;
}

const NAP_ROVID = [tk('V|nap'), tk('H|nap'), tk('K|nap'), tk('Sze|nap'), tk('Cs|nap'), tk('P|nap'), tk('Szo|nap')];
const honapRovid = (m: number) => new Intl.DateTimeFormat(locale(), { month: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(2000, m, 1)));

function reszek(nap: string): Date {
  const [y, h, d] = nap.split('-').map(Number);
  return new Date(y, h - 1, d, 12);
}

/** Tengelycímke: napi bontásnál a nap rövid neve, heti bontásnál a hét hétfőjének napja. */
export function napCimke(nap: string, bontas: 'nap' | 'het'): string {
  const d = reszek(nap);
  return bontas === 'nap' ? t(NAP_ROVID[d.getDay()]) : `${d.getDate()}.`;
}

export function napSzoveg(nap: string, bontas: 'nap' | 'het' = 'nap'): string {
  const d = reszek(nap);
  const alap = locale() === 'hu-HU' ? `${honapRovid(d.getMonth())} ${d.getDate()}.` : `${d.getDate()} ${honapRovid(d.getMonth())}`;
  return bontas === 'het' ? t('{alap}-tól', { alap }) : `${alap} (${t(NAP_ROVID[d.getDay()])})`;
}

const FORRAS_NEV: Record<string, string> = {
  billentyu: tk('billentyű|forras'),
  paletta: tk('paletta|forras'),
  menu: tk('helyi menü|forras'),
  gomb: tk('gomb|forras'),
  hej: tk('menüsor|forras'),
  egyeb: tk('egyéb|forras'),
};
export const forrasNev = (f: string) => (FORRAS_NEV[f] ? t(FORRAS_NEV[f]) : f);
