// Az ábrából rajzterv (C35a): a kifejezések lefordítása, az ablak kiválasztása (a megadott tartomány, különben a
// mintákból „szép” határokkal), a hibás elem halk kihagyása. Tiszta logika: a JSXGraph-ot a `rajzolo.ts` hívja.

import { t as tx } from '../../../lib/i18n';
import type { Abra } from './forras';
import { KifejezesHiba, fordit, konstans, type Ertek } from './kifejezes';

/** A sorozatok színei: csak meglévő design-tokenek (25. döntés; a kontraszt-teszt fedi), az `--akcent` az első. */
export const SOROZAT_SZIN = ['--akcent', '--canvas-szin-1', '--canvas-szin-2', '--canvas-szin-3', '--canvas-szin-4', '--canvas-szin-5', '--canvas-szin-6'];

export interface Gorbe {
  fajta: 'fuggveny' | 'parameteres';
  cimke: string | null;
  /** az eredeti kifejezés-szöveg (a CAS-jellemzők kérése) */
  kifejezes: string;
  /** y = f(x) (paraméteres görbénél `NaN`) */
  ertek: Ertek;
  param?: { x: Ertek; y: Ertek; lo: number; hi: number };
  szin: string;
}

export interface TartomanyElem {
  relacio: '<' | '<=' | '>' | '>=';
  cimke: string | null;
  kifejezes: string;
  ertek: Ertek;
  szin: string;
}

export interface PontElem {
  x: number;
  y: number;
  cimke: string | null;
}

export interface Rajzterv {
  tengelyFelirat?: { x: string; y: string };
  ablak: { x: [number, number]; y: [number, number] };
  gorbek: Gorbe[];
  tartomanyok: TartomanyElem[];
  pontok: PontElem[];
  /** halk figyelmeztetések: a kihagyott sorok és a hibás kifejezések (a blokk többi eleme él) */
  figyelmeztetesek: string[];
  /** van-e bármi, ami kirajzolható */
  hasznalhato: boolean;
}

const TRIG = /\b(?:sin|cos|tan|tg|cot|ctg)\s*\(/;
const MINTA = 401;
const MARGO = 0.08;

/** Az [lo, hi] „szép” (1/2/5·10ᵏ lépcsős) határokra kerekítve. */
export function szepHatarok(lo: number, hi: number): [number, number] {
  const tav = hi - lo;
  const nyers = tav / 4;
  const k = 10 ** Math.floor(Math.log10(nyers));
  const m = nyers / k;
  const lepes = (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * k;
  const tiszta = (v: number) => Number(v.toPrecision(12));
  return [tiszta(Math.floor(lo / lepes) * lepes), tiszta(Math.ceil(hi / lepes) * lepes)];
}

function szazalek(rendezett: number[], p: number): number {
  return rendezett[Math.min(rendezett.length - 1, Math.max(0, Math.floor(p * (rendezett.length - 1))))];
}

/** A mintázott y-értékek ablaka: margóval, szép határokkal; ha pár szélsőséges érték (pólus) a tartományt az 1.–99.
 *  percentilis háromszorosánál is jobban nyújtaná, az 1.–99. percentilis. */
function yAblak(ertekek: number[]): [number, number] {
  const v = ertekek.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return [-5, 5];
  let lo = v[0];
  let hi = v[v.length - 1];
  const p1 = szazalek(v, 0.01);
  const p99 = szazalek(v, 0.99);
  if (hi - lo > 3 * Math.max(p99 - p1, 1e-9)) {
    lo = p1;
    hi = p99;
  }
  if (hi - lo < 1e-9) {
    lo -= 1;
    hi += 1;
  }
  const m = (hi - lo) * MARGO;
  return szepHatarok(lo - m, hi + m);
}

function tartomanyKonstans(par: [string, string], nev: string, fig: string[]): [number, number] | null {
  try {
    const lo = konstans(par[0]);
    const hi = konstans(par[1]);
    if (!(lo < hi)) throw new KifejezesHiba(tx('az alsó határ kisebb legyen a felsőnél'));
    return [lo, hi];
  } catch (e) {
    fig.push(tx('{nev} tartomány: {hiba}', { nev, hiba: e instanceof Error ? e.message : String(e) }));
    return null;
  }
}

export function terv(abra: Abra): Rajzterv {
  const fig: string[] = abra.hibak.map(([n, uzenet]) => tx('{n}. sor: {uzenet}', { n, uzenet }));
  const gorbek: Gorbe[] = [];
  const tartomanyok: TartomanyElem[] = [];
  const pontok: PontElem[] = [];
  let db = 0;
  const szinek = new Map<number, string>();
  const tengelyFelirat = { x: 'x', y: 'y' };
  // A formátum megjegyzéseiben tárolt beállítások a korábbi olvasókkal is körútállók.
  for (const e of abra.elemek) if (e.fajta === 'megjegyzes') {
    const sz = /^szin ([1-9][0-9]?) (#[a-fA-F0-9]{6}|#[a-fA-F0-9]{3})$/.exec(e.szoveg);
    const tengely = /^([xy])-felirat "([^"<>]{1,80})"$/.exec(e.szoveg);
    if (sz) szinek.set(Number(sz[1]), sz[2]);
    else if (tengely) tengelyFelirat[tengely[1] as 'x' | 'y'] = tengely[2];
    else if (/^(szin |[xy]-felirat )/.test(e.szoveg)) fig.push(tx('Hibás szín vagy tengelyfelirat-beállítás.'));
  }
  const szin = () => { const i = db++; return szinek.get(i + 1) ?? SOROZAT_SZIN[i % SOROZAT_SZIN.length]; };
  const hibas = (leiras: string, e: unknown) => fig.push(`${leiras}: ${e instanceof Error ? e.message : String(e)}`);

  for (const e of abra.elemek) {
    try {
      if (e.fajta === 'fuggveny') {
        gorbek.push({ fajta: 'fuggveny', cimke: e.cimke, kifejezes: e.kifejezes, ertek: fordit(e.kifejezes, 'x'), szin: szin() });
      } else if (e.fajta === 'egyenlotlenseg') {
        tartomanyok.push({ relacio: e.relacio, cimke: e.cimke, kifejezes: e.kifejezes, ertek: fordit(e.kifejezes, 'x'), szin: szin() });
      } else if (e.fajta === 'parameteres') {
        if (e.t === 'e') throw new KifejezesHiba(tx('a paraméter neve nem lehet `e` (az Euler-szám)'));
        const lo = konstans(e.tartomany[0]);
        const hi = konstans(e.tartomany[1]);
        if (!(lo < hi)) throw new KifejezesHiba(tx('a paraméter alsó határa kisebb legyen a felsőnél'));
        gorbek.push({
          fajta: 'parameteres',
          cimke: e.cimke,
          kifejezes: `${e.x}; ${e.y}`,
          ertek: () => NaN,
          param: { x: fordit(e.x, e.t), y: fordit(e.y, e.t), lo, hi },
          szin: szin(),
        });
      } else if (e.fajta === 'pont') {
        pontok.push({ x: konstans(e.x), y: konstans(e.y), cimke: e.cimke });
      }
    } catch (err) {
      hibas(e.fajta === 'fuggveny' || e.fajta === 'egyenlotlenseg' ? `y ${e.fajta === 'fuggveny' ? '=' : e.relacio} ${e.kifejezes}` : e.fajta, err);
    }
  }

  // x-ablak
  const xMegadott = abra.x_tartomany ? tartomanyKonstans(abra.x_tartomany, 'x', fig) : null;
  const vanFuggveny = gorbek.some((g) => g.fajta === 'fuggveny') || tartomanyok.length > 0;
  const trig = [...gorbek.filter((g) => g.fajta === 'fuggveny'), ...tartomanyok].some((g) => TRIG.test(g.kifejezes));
  let x: [number, number] = xMegadott ?? (trig ? [-2 * Math.PI, 2 * Math.PI] : [-5, 5]);

  // minták a hiányzó ablakokhoz
  const xs = Array.from({ length: MINTA }, (_, i) => x[0] + ((x[1] - x[0]) * i) / (MINTA - 1));
  const paramXY: [number, number][] = [];
  for (const g of gorbek) {
    if (g.param) {
      for (let i = 0; i < MINTA; i++) {
        const t = g.param.lo + ((g.param.hi - g.param.lo) * i) / (MINTA - 1);
        const px = g.param.x(t);
        const py = g.param.y(t);
        if (Number.isFinite(px) && Number.isFinite(py)) paramXY.push([px, py]);
      }
    }
  }
  if (!xMegadott && !vanFuggveny && (paramXY.length || pontok.length)) {
    const px = [...paramXY.map((p) => p[0]), ...pontok.map((p) => p.x)];
    const lo = Math.min(...px);
    const hi = Math.max(...px);
    const m = Math.max((hi - lo) * 0.15, 0.5);
    x = szepHatarok(lo - m, hi + m);
  }

  let y: [number, number];
  const yMegadott = abra.y_tartomany ? tartomanyKonstans(abra.y_tartomany, 'y', fig) : null;
  if (yMegadott) y = yMegadott;
  else {
    const ertekek: number[] = [];
    for (const g of [...gorbek.filter((k) => k.fajta === 'fuggveny'), ...tartomanyok]) {
      const f = g.ertek;
      for (const v of xs) ertekek.push(f(v));
    }
    for (const p of paramXY) ertekek.push(p[1]);
    for (const p of pontok) ertekek.push(p.y);
    y = yAblak(ertekek);
    if (!ertekek.some(Number.isFinite)) y = [-5, 5];
    if (!xMegadott && !vanFuggveny && pontok.length && !paramXY.length) {
      const m = Math.max((Math.max(...pontok.map((p) => p.y)) - Math.min(...pontok.map((p) => p.y))) * 0.15, 0.5);
      y = szepHatarok(Math.min(...pontok.map((p) => p.y)) - m, Math.max(...pontok.map((p) => p.y)) + m);
    }
  }
  if (!(y[0] < y[1])) y = [y[0] - 1, y[0] + 1];
  if (!(x[0] < x[1])) x = [x[0] - 1, x[0] + 1];

  return {
    ablak: { x, y },
    tengelyFelirat,
    gorbek,
    tartomanyok,
    pontok,
    figyelmeztetesek: fig,
    hasznalhato: gorbek.length + tartomanyok.length + pontok.length > 0,
  };
}
