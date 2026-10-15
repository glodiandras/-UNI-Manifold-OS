// A grafikon jelenete (C35a), a rajzoló-könyvtártól függetlenül: a görbék és a kitöltés adata az aktuális ablakra
// (a nagyításkor és a mozgatáskor újra számolódik), a CAS-jellemzők jelölői, a jelmagyarázat és a képernyőolvasónak
// szóló leírás. A színek **design-token nevek** (25. döntés): a rajzoló oldja fel őket az aktuális témában.

import type { Meret, Nezet } from './interakcio';
import { szam, szepSzoveg, type Jellemzok } from './jellemzok';
import { egybe, mintaz, type Minta } from './mintavetel';
import type { Gorbe, Rajzterv, TartomanyElem } from './terv';

/** A nem sorozat-színű elemek tokenjei (az aszimptota halvány, a kiemelt pont a szöveg színe). */
export const JELOLO_SZIN = { aszimptota: '--szoveg-halvany', pont: '--szoveg' } as const;

export interface PontJelolo {
  tipus: 'pont';
  szin: string;
  x: number;
  y: number;
  /** `ures`: zérushely; `teli`: szélsőérték és a felhasználó pontja */
  stilus: 'ures' | 'teli';
  felirat: string;
}
export interface EgyenesJelolo {
  tipus: 'egyenes';
  szin: string;
  /** két pont az egyenesen (a rajzoló a végtelenig húzza) */
  p1: [number, number];
  p2: [number, number];
  felirat: string;
}
export type Jelolo = PontJelolo | EgyenesJelolo;

const MIN_PONT = 200;
const MAX_PONT = 1600;

function pontszam(meret: Meret): number {
  return Math.min(MAX_PONT, Math.max(MIN_PONT, Math.round(meret.szelesseg)));
}

/** Egy görbe vonala az ablakra: egyetlen tömbpár, `NaN`-nal szakítva (a JSXGraph `curve` a `NaN`-nál szakít). */
export function vonalAdat(g: Gorbe, nezet: Nezet, meret: Meret): Minta {
  if (g.fajta === 'fuggveny') return egybe(mintaz(g.ertek, nezet.x[0], nezet.x[1], opciok(nezet, meret)));
  return paramAdat(g, nezet, meret);
}

function opciok(nezet: Nezet, meret: Meret) {
  return { ymin: nezet.y[0], ymax: nezet.y[1], pontok: pontszam(meret) };
}

function paramAdat(g: Gorbe, nezet: Nezet, meret: Meret): Minta {
  const p = g.param!;
  const n = Math.min(3000, Math.max(400, 2 * pontszam(meret)));
  const hx = nezet.x[1] - nezet.x[0];
  const hy = nezet.y[1] - nezet.y[0];
  const vag = (v: number, lo: number, h: number) => Math.max(lo - 20 * h, Math.min(lo + 21 * h, v));
  const x: number[] = [];
  const y: number[] = [];
  let szakadt = false;
  for (let i = 0; i < n; i++) {
    const t = p.lo + ((p.hi - p.lo) * i) / (n - 1);
    const px = p.x(t);
    const py = p.y(t);
    if (!Number.isFinite(px) || !Number.isFinite(py)) {
      if (x.length && !szakadt) {
        x.push(NaN);
        y.push(NaN);
        szakadt = true;
      }
      continue;
    }
    x.push(vag(px, nezet.x[0], hx));
    y.push(vag(py, nezet.y[0], hy));
    szakadt = false;
  }
  if (szakadt) {
    x.pop();
    y.pop();
  }
  return { x, y };
}

/** Az egyenlőtlenség kitöltése: a határgörbe és az ablak széle közti sokszögek (`NaN`-nal elválasztva). */
export function kitoltesAdat(t: TartomanyElem, nezet: Nezet, meret: Meret): Minta {
  const felul = t.relacio === '>' || t.relacio === '>=';
  const el = felul ? nezet.y[1] : nezet.y[0];
  const x: number[] = [];
  const y: number[] = [];
  mintaz(t.ertek, nezet.x[0], nezet.x[1], opciok(nezet, meret)).forEach((s, i) => {
    if (i) {
      x.push(NaN);
      y.push(NaN);
    }
    x.push(...s.x, s.x[s.x.length - 1], s.x[0]);
    y.push(...s.y, el, el);
  });
  return { x, y };
}

/** A határgörbe vonala az egyenlőtlenséghez (a szaggatás a relációtól függ: a `<` és a `>` szaggatott). */
export function hatarAdat(t: TartomanyElem, nezet: Nezet, meret: Meret): Minta {
  return egybe(mintaz(t.ertek, nezet.x[0], nezet.x[1], opciok(nezet, meret)));
}

export function szaggatott(t: TartomanyElem): boolean {
  return t.relacio === '<' || t.relacio === '>';
}

/** A CAS-jellemzők és a felhasználó pontjai jelölőként. `eredmenyek`: a `terv.gorbek` sorszáma → jellemzők; csak a
 *  kész (`ok`, `reszleges`) állapot számít. */
export function jelolok(terv: Rajzterv, eredmenyek: ReadonlyMap<number, Jellemzok>): Jelolo[] {
  const ki: Jelolo[] = [];
  terv.gorbek.forEach((g, i) => {
    const j = eredmenyek.get(i);
    if (!j || (j.allapot !== 'ok' && j.allapot !== 'reszleges')) return;
    for (const z of j.zerushelyek) ki.push({ tipus: 'pont', szin: g.szin, x: z.ertek, y: 0, stilus: 'ures', felirat: szepSzoveg(z.x) });
    for (const s of j.szelsoertekek) {
      ki.push({
        tipus: 'pont',
        szin: g.szin,
        x: s.x_ertek,
        y: s.y_ertek,
        stilus: 'teli',
        felirat: `${s.tipus === 'maximum' ? 'max' : 'min'} (${szepSzoveg(s.x)}; ${szepSzoveg(s.y)})`,
      });
    }
    for (const a of j.aszimptotak) {
      ki.push({
        tipus: 'egyenes',
        szin: JELOLO_SZIN.aszimptota,
        p1: a.tipus === 'fuggoleges' ? [a.ertek, 0] : [0, a.ertek],
        p2: a.tipus === 'fuggoleges' ? [a.ertek, 1] : [1, a.ertek],
        felirat: szepSzoveg(a.egyenlet),
      });
    }
    for (const f of j.ferde_aszimptotak) {
      ki.push({
        tipus: 'egyenes',
        szin: JELOLO_SZIN.aszimptota,
        p1: [0, f.eltolas],
        p2: [1, f.meredekseg + f.eltolas],
        felirat: szepSzoveg(f.egyenlet),
      });
    }
  });
  for (const p of terv.pontok) {
    ki.push({ tipus: 'pont', szin: JELOLO_SZIN.pont, x: p.x, y: p.y, stilus: 'teli', felirat: p.cimke ?? '' });
  }
  return ki;
}

/** A jelmagyarázat: a címkézett görbék és egyenlőtlenségek, a színükkel (sorrend: görbék, utána a tartományok). */
export function jelmagyarazat(terv: Rajzterv): { szin: string; cimke: string }[] {
  return [...terv.gorbek, ...terv.tartomanyok].filter((e) => e.cimke !== null).map((e) => ({ szin: e.szin, cimke: e.cimke! }));
}

/** A képernyőolvasónak: a függvények és a nevezetes pontok szövegben (a rajz maga `role="img"`). */
export function leiras(terv: Rajzterv, eredmenyek: ReadonlyMap<number, Jellemzok>): string {
  const reszek = [
    ...terv.gorbek.map((g) => (g.fajta === 'fuggveny' ? `y = ${g.kifejezes}${g.cimke ? ` (${g.cimke})` : ''}` : `paraméteres görbe${g.cimke ? ` (${g.cimke})` : ''}`)),
    ...terv.tartomanyok.map((t) => `y ${t.relacio} ${t.kifejezes} tartomány`),
  ];
  const pontok: string[] = [];
  terv.gorbek.forEach((_g, i) => {
    const j = eredmenyek.get(i);
    if (!j || (j.allapot !== 'ok' && j.allapot !== 'reszleges')) return;
    for (const z of j.zerushelyek) pontok.push(`zérushely x = ${szepSzoveg(z.x)}`);
    for (const s of j.szelsoertekek) pontok.push(`${s.tipus} (${szepSzoveg(s.x)}; ${szepSzoveg(s.y)})`);
    for (const a of [...j.aszimptotak, ...j.ferde_aszimptotak]) pontok.push(`aszimptota ${szepSzoveg(a.egyenlet)}`);
  });
  for (const p of terv.pontok) pontok.push(`pont (${szam(p.x)}; ${szam(p.y)})${p.cimke ? ` ${p.cimke}` : ''}`);
  return `Grafikon: ${reszek.join('; ') || 'nincs rajzolt elem'}.${pontok.length ? ` Nevezetes pontok: ${pontok.join('; ')}.` : ''}`;
}
