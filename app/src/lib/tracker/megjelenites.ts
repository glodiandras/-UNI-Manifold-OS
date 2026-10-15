// A tracker megjelenítési segédei (C27): idő, szám és dátum magyar szövege.

/** A helyi nap ÉÉÉÉ-HH-NN alakban (a core is helyi napban aggregál). */
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
  if (!Number.isFinite(mp) || mp <= 0) return '0 p';
  if (mp < 60) return `${Math.round(mp)} mp`;
  const perc = Math.round(mp / 60);
  const ora = Math.floor(perc / 60);
  return ora ? `${ora} ó ${String(perc % 60).padStart(2, '0')} p` : `${perc} p`;
}

export function szamSzoveg(n: number): string {
  return new Intl.NumberFormat('hu-HU').format(n);
}

export function msSzoveg(ms: number | null): string {
  if (ms === null || ms === undefined) return '–';
  if (ms >= 1000) return `${(ms / 1000).toLocaleString('hu-HU', { maximumFractionDigits: 1 })} s`;
  return `${Number.isInteger(ms) ? ms : ms.toFixed(1)} ms`;
}

export function szazalekSzoveg(r: number | null): string {
  return r === null || r === undefined ? '–' : `${Math.round(r * 100)} %`;
}

const NAP_ROVID = ['V', 'H', 'K', 'Sze', 'Cs', 'P', 'Szo'];
const HONAP_ROVID = ['jan.', 'febr.', 'márc.', 'ápr.', 'máj.', 'jún.', 'júl.', 'aug.', 'szept.', 'okt.', 'nov.', 'dec.'];

function reszek(nap: string): Date {
  const [y, h, d] = nap.split('-').map(Number);
  return new Date(y, h - 1, d, 12);
}

/** Tengelycímke: napi bontásnál a nap rövid neve, heti bontásnál a hét hétfőjének napja. */
export function napCimke(nap: string, bontas: 'nap' | 'het'): string {
  const d = reszek(nap);
  return bontas === 'nap' ? NAP_ROVID[d.getDay()] : `${d.getDate()}.`;
}

export function napSzoveg(nap: string, bontas: 'nap' | 'het' = 'nap'): string {
  const d = reszek(nap);
  const alap = `${HONAP_ROVID[d.getMonth()]} ${d.getDate()}.`;
  return bontas === 'het' ? `${alap}-tól` : `${alap} (${NAP_ROVID[d.getDay()]})`;
}

const FORRAS_NEV: Record<string, string> = {
  billentyu: 'billentyű',
  paletta: 'paletta',
  menu: 'helyi menü',
  gomb: 'gomb',
  hej: 'menüsor',
  egyeb: 'egyéb',
};
export const forrasNev = (f: string) => FORRAS_NEV[f] ?? f;
