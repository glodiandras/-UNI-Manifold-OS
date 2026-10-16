// Dátum- és időszövegek a „Ma” oldalhoz (C15). A hónap- és napneveket a core adja (`felirat`), itt csak a relatív
// napok, az időtartományok és az éjfél-számítás él; a szöveg magyar.

import { locale, t, tp } from '../lib/i18n';
import type { NaptarEsemeny } from './tipusok';

/** A helyi nap kulcsa: `ÉÉÉÉ-HH-NN`. */
export function napKulcs(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** A következő helyi éjfélig hátralévő ezredmásodperc (legalább 1 s, hogy az időzítő ne pörögjön). */
export function ejfelig(most: Date): number {
  const ejfel = new Date(most.getFullYear(), most.getMonth(), most.getDate() + 1, 0, 0, 0, 0);
  return Math.max(1000, ejfel.getTime() - most.getTime());
}

/** „ma”, „holnap”, „3 nap múlva”, „tegnap”, „2 napja”. */
export function napokSzoveg(napok: number): string {
  if (napok === 0) return t('ma');
  if (napok === 1) return t('holnap');
  if (napok === 2) return t('holnapután');
  if (napok === -1) return t('tegnap');
  return napok > 0 ? tp('{n} nap múlva', napok) : tp('{n} napja', -napok);
}

const HONAPOK = () => new Intl.DateTimeFormat(locale(), { year: 'numeric', month: 'long', day: 'numeric' });
const ROVID = () => new Intl.DateTimeFormat(locale(), { month: 'short', day: 'numeric' });

/** „2026. október 5.” az `ÉÉÉÉ-HH-NN` kulcsból (a hely időzónájától függetlenül). */
export function napSzoveg(kulcs: string): string {
  const [y, m, d] = kulcs.split('-').map(Number);
  return HONAPOK().format(new Date(y, m - 1, d));
}

/** „okt. 5.” */
export function napRovid(kulcs: string): string {
  const [y, m, d] = kulcs.split('-').map(Number);
  return ROVID().format(new Date(y, m - 1, d));
}

/** Az esemény ideje a listában: „08:55–09:40”, „08:55” vagy „egész nap”. */
export function idoSzoveg(e: Pick<NaptarEsemeny, 'egesznap' | 'kezd_ora' | 'veg_ora'>): string {
  if (e.egesznap || !e.kezd_ora) return t('egész nap');
  return e.veg_ora && e.veg_ora !== e.kezd_ora ? `${e.kezd_ora}–${e.veg_ora}` : e.kezd_ora;
}

/** A naptáradat korának szövege: „Az itt látott naptár a 2026. szeptember 27-i állapot.” (a szinkron ISO időpontjából). */
export function szinkronSzoveg(iso: string | null): string {
  if (!iso) return t('A naptáradat kora ismeretlen.');
  return t('Az itt látott naptár a {nap}-i állapot.', { nap: napSzoveg(iso.slice(0, 10)).replace(/\.$/, '') });
}

/** Az esemény éppen tart-e (a naptár saját órája szerint, helyi `HH:mm` összevetéssel; csak a mai napon hívjuk). */
export function folyamatban(e: Pick<NaptarEsemeny, 'egesznap' | 'kezd_ora' | 'veg_ora'>, most: Date): boolean {
  if (e.egesznap || !e.kezd_ora || !e.veg_ora) return false;
  const p = (n: number) => String(n).padStart(2, '0');
  const ora = `${p(most.getHours())}:${p(most.getMinutes())}`;
  return e.kezd_ora <= ora && ora < e.veg_ora;
}

/** Két `ÉÉÉÉ-HH-NN` nap különbsége napokban (`nap` − `ma`); a helyi időzónától független. */
export function napKulonbseg(nap: string, ma: string): number {
  const [y1, m1, d1] = nap.split('-').map(Number);
  const [y2, m2, d2] = ma.split('-').map(Number);
  return Math.round((Date.UTC(y1, m1 - 1, d1) - Date.UTC(y2, m2 - 1, d2)) / 86_400_000);
}

/** A javaslat ideje a kártyán: „holnap · okt. 7. · 16:00–17:00 · 60 perc” (az idők a core ISO-jának saját órái). */
export function javaslatIdo(j: { nap: string; kezd: string; veg: string; perc: number | null }, maKulcs: string): string {
  const reszek = [napokSzoveg(napKulonbseg(j.nap, maKulcs)), napRovid(j.nap), `${j.kezd.slice(11, 16)}–${j.veg.slice(11, 16)}`];
  if (j.perc) reszek.push(t('{p} perc', { p: j.perc }));
  return reszek.join(' · ');
}
