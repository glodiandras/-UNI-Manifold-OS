// A függvénygörbe mintavétele (C35a): egyenletes alaprács, adaptív finomítás (az elhajlás és a pólus környékén), az
// értelmezési tartomány szélének és a pólusnak a helyére szűkítés, szakaszokra bontás (`NaN`-nál) és a kilógó érték
// vágása. A pólus két oldalán nem húzunk vonalat (nincs „aszimptota-híd”), a tartomány szélén nincs rés.

import type { Ertek } from './kifejezes';

export interface Minta {
  x: number[];
  y: number[];
}

export interface MintaOpciok {
  /** a látható y-tartomány: a pólus-észlelés és a vágás mércéje */
  ymin: number;
  ymax: number;
  /** az alaprács pontjai (alap 600) */
  pontok?: number;
  /** az összes pont plafonja, a finomítással együtt (alap 6000) */
  maxPont?: number;
}

const MAX_MELYSEG = 12;
const ELHAJLAS = 0.002; // a magasság hányada: ennél nagyobb elhajlásnál finomít
const VAGAS_SZOROZO = 20; // a látható magasság többszöröse, ameddig a kilógó értéket megtartjuk

export function mintaz(f: Ertek, lo: number, hi: number, o: MintaOpciok): Minta[] {
  if (!(hi > lo) || !Number.isFinite(lo) || !Number.isFinite(hi)) return [];
  const alap = Math.min(8000, Math.max(50, Math.round(o.pontok ?? 600)));
  const plafon = o.maxPont ?? 6000;
  const H = Math.max(o.ymax - o.ymin, 1e-12);
  const als = o.ymin - VAGAS_SZOROZO * H;
  const fels = o.ymax + VAGAS_SZOROZO * H;
  const ki: [number, number][] = [];
  const hatar = (y: number) => Math.max(als, Math.min(fels, y));
  const tolj = (x: number, y: number) => ki.push([x, Number.isNaN(y) ? NaN : hatar(y)]);
  const szakit = () => {
    if (ki.length && !Number.isNaN(ki[ki.length - 1][1])) ki.push([NaN, NaN]);
  };

  /** A tartomány-szél keresése: `jo` oldalon véges, `rossz` oldalon `NaN`; a legszélső véges pontot adja. */
  const szel = (jo: number, rossz: number): number => {
    let a = jo;
    let b = rossz;
    for (let i = 0; i < 48; i++) {
      const m = (a + b) / 2;
      if (Number.isFinite(f(m))) a = m;
      else b = m;
    }
    return a;
  };

  const finomit = (a: number, fa: number, b: number, fb: number, d: number): void => {
    const faV = Number.isFinite(fa);
    const fbV = Number.isFinite(fb);
    if (faV && fbV) {
      const polus = fa * fb < 0 && Math.abs(fb - fa) > 3 * H;
      if (d < MAX_MELYSEG && ki.length < plafon) {
        const m = (a + b) / 2;
        const fm = f(m);
        if (polus || (Number.isFinite(fm) && Math.abs(fm - (fa + fb) / 2) > ELHAJLAS * H)) {
          finomit(a, fa, m, fm, d + 1);
          finomit(m, fm, b, fb, d + 1);
          return;
        }
      }
      if (polus) szakit();
      tolj(b, fb);
      return;
    }
    if (faV && !fbV) {
      const x = szel(a, b);
      if (x > a) tolj(x, f(x));
      szakit();
      return;
    }
    if (!faV && fbV) {
      const x = szel(b, a);
      szakit();
      tolj(x, f(x));
      if (b > x) tolj(b, fb);
      return;
    }
    if (d < MAX_MELYSEG && ki.length < plafon) {
      // mindkét végén értelmezetlen: lehet, hogy közepén van egy szűk értelmezett sáv — egy próba
      const m = (a + b) / 2;
      const fm = f(m);
      if (Number.isFinite(fm)) {
        finomit(a, fa, m, fm, d + 1);
        finomit(m, fm, b, fb, d + 1);
        return;
      }
    }
    szakit();
  };

  const xs = Array.from({ length: alap }, (_, i) => (i === alap - 1 ? hi : lo + ((hi - lo) * i) / (alap - 1)));
  const ys = xs.map(f);
  if (Number.isFinite(ys[0])) tolj(xs[0], ys[0]);
  for (let i = 0; i < alap - 1; i++) finomit(xs[i], ys[i], xs[i + 1], ys[i + 1], 0);
  const szakaszok: Minta[] = [];
  let akt: Minta = { x: [], y: [] };
  for (const [x, y] of ki) {
    if (Number.isNaN(y)) {
      if (akt.x.length > 1) szakaszok.push(akt);
      akt = { x: [], y: [] };
    } else {
      akt.x.push(x);
      akt.y.push(y);
    }
  }
  if (akt.x.length > 1) szakaszok.push(akt);
  return szakaszok;
}

/** A szakaszok egyetlen tömbpárban, `NaN`-nal elválasztva (a JSXGraph `curve` a `NaN`-nál szakít). */
export function egybe(szakaszok: Minta[]): Minta {
  const x: number[] = [];
  const y: number[] = [];
  szakaszok.forEach((s, i) => {
    if (i) {
      x.push(NaN);
      y.push(NaN);
    }
    x.push(...s.x);
    y.push(...s.y);
  });
  return { x, y };
}
