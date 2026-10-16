// A ```plot blokk formátuma (C35a): elemzés és kanonikus szerializálás. A Python-oldal (`modulok/grafikon/formatum.py`,
// docs/PLOT-FORMATUM.md) tükre: a közös vektorok (`modulok/grafikon/vektorok/forras.json`) őrzik, hogy ugyanabból a
// szövegből ugyanaz az ábra, ugyanaz a hibalista és ugyanaz a kanonikus alak jön. A mezők neve a Python-oldal
// `abra_szotar` JSON-jáé (snake_case), hogy a két oldal alakja közvetlenül összevethető legyen.
//
// A formátum csak **adat**: a kifejezést nem értékeli (az `kifejezes.ts` dolga). Az ismeretlen vagy hibás sor hibát nem
// okoz: megmarad (`ismeretlen`), a renderelő kihagyja, a `hibak` a sor számát jelzi; így a kézi szerkesztés biztonságos.

import { t as tx } from '../../../lib/i18n';
export const MAX_ELEM = 64; // ennél több rajzelemet a renderelő nem kap (a többi `ismeretlen`)
export const MAX_SOR = 2000; // ennél hosszabb sor `ismeretlen`
export const MAX_BLOKK = 100_000; // ennél nagyobb blokkot nem elemzünk

export interface Fuggveny {
  fajta: 'fuggveny';
  kifejezes: string; // y = kifejezes (x-ben)
  cimke: string | null;
}
export interface Parameteres {
  fajta: 'parameteres';
  x: string;
  y: string;
  t: string; // a paraméter betűje
  tartomany: [string, string];
  cimke: string | null;
}
export interface Egyenlotlenseg {
  fajta: 'egyenlotlenseg';
  kifejezes: string; // y RELÁCIÓ kifejezes
  relacio: '<' | '<=' | '>' | '>=';
  cimke: string | null;
}
export interface Pont {
  fajta: 'pont';
  x: string;
  y: string;
  cimke: string | null;
}
export interface Megjegyzes {
  fajta: 'megjegyzes';
  szoveg: string;
}
export interface Ismeretlen {
  fajta: 'ismeretlen';
  sor: string;
}
export type Elem = Fuggveny | Parameteres | Egyenlotlenseg | Pont | Megjegyzes | Ismeretlen;

export interface Abra {
  x_tartomany: [string, string] | null;
  y_tartomany: [string, string] | null;
  elemek: Elem[];
  hibak: [number, string][]; // (sorszám 1-től, üzenet)
}

const KIF = String.raw`[0-9A-Za-z+\-*/^().,!_ ]+?`; // a kifejezés megengedett jelei (a `matek.elemez` fehérlistájának része)
const BIZ = /^[0-9A-Za-z+\-*/^().,!_ ]+$/;
const TART = new RegExp(String.raw`^([xy])\s+in\s*\[\s*(${KIF})\s*,\s*(${KIF})\s*\]$`);
const PTART = new RegExp(String.raw`^([a-wz])\s+in\s*\[\s*(${KIF})\s*,\s*(${KIF})\s*\]$`);
const EGYENL = new RegExp(String.raw`^y\s*(<=|>=|<|>)\s*(${KIF})$`);
const FGV = new RegExp(String.raw`^y\s*=\s*(${KIF})$`);
const PONT = new RegExp(String.raw`^pont\s*\(\s*(${KIF})\s*,\s*(${KIF})\s*\)$`);
const CIMKE = /\s+"((?:[^"\\]|\\.)*)"\s*$/;
const PARAM = new RegExp(String.raw`^x\s*=\s*(${KIF})$`);
const UNICODE: Record<string, string> = { '−': '-', '–': '-', '≤': '<=', '≥': '>=' };

/** Python `str.splitlines()`: `\n`, `\r\n`, `\r`, `\v`, `\f`, `\x1c`–`\x1e`, `\x85`, `\u2028`, `\u2029`. */
function sorok(szoveg: string): string[] {
  const r = szoveg.split(/\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/);
  if (r.length && r[r.length - 1] === '') r.pop();
  return r;
}

function tisztit(s: string): string {
  for (const [k, v] of Object.entries(UNICODE)) s = s.split(k).join(v);
  return s.replace(/\s+/g, ' ').trim();
}

function lev(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function kibont(s: string): string {
  return s.replace(/\\(.)/g, '$1');
}

function cimkevel(szoveg: string): [string, string | null] {
  const m = CIMKE.exec(szoveg);
  return m ? [szoveg.slice(0, m.index), kibont(m[1])] : [szoveg, null];
}

/** A sor végi ` # …` megjegyzés levágása (idézőjelen kívül). */
function megjegyzesNelkul(sor: string): string {
  let benn = false;
  for (let i = 0; i < sor.length; i++) {
    const c = sor[i];
    if (c === '\\' && benn) {
      i++;
      continue;
    }
    if (c === '"') benn = !benn;
    else if (c === '#' && !benn && (i === 0 || sor[i - 1] === ' ')) return sor.slice(0, i);
  }
  return sor;
}

/** Felső szintű vesszők mentén (zárójelen belül nem). */
function felbontVesszo(s: string): string[] {
  const reszek: string[] = [];
  let melyseg = 0;
  let ki = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === '(' || c === '[') melyseg++;
    else if (c === ')' || c === ']') melyseg--;
    else if (c === ',' && melyseg === 0) {
      reszek.push(s.slice(ki, i));
      ki = i + 1;
    }
  }
  reszek.push(s.slice(ki));
  return reszek.map((r) => r.trim());
}

/** A kifejezés-szövegek nem üresek, a megengedett jelekből állnak, a zárójelek párosak. */
function jo(...kifejezesek: string[]): boolean {
  for (const k of kifejezesek) {
    if (!k.trim() || !BIZ.test(k)) return false;
    let m = 0;
    for (const c of k) {
      m += (c === '(' ? 1 : 0) - (c === ')' ? 1 : 0);
      if (m < 0) return false;
    }
    if (m) return false;
  }
  return true;
}

type Tartomany = { tartomany: 'x' | 'y'; ertek: [string, string] };

function elem(sor: string): Elem | Tartomany | null {
  const [torzs0, cimke] = cimkevel(sor);
  const torzs = torzs0.trim();
  let m = TART.exec(torzs);
  if (m && cimke === null) {
    if (jo(m[2], m[3])) return { tartomany: m[1] as 'x' | 'y', ertek: [m[2].trim(), m[3].trim()] };
    return null;
  }
  m = PONT.exec(torzs);
  if (m && jo(m[1], m[2])) return { fajta: 'pont', x: m[1].trim(), y: m[2].trim(), cimke };
  m = EGYENL.exec(torzs);
  if (m && jo(m[2])) return { fajta: 'egyenlotlenseg', kifejezes: m[2].trim(), relacio: m[1] as Egyenlotlenseg['relacio'], cimke };
  m = FGV.exec(torzs);
  if (m && jo(m[1])) return { fajta: 'fuggveny', kifejezes: m[1].trim(), cimke };
  const reszek = felbontVesszo(torzs);
  if (reszek.length === 3) {
    const mx = PARAM.exec(reszek[0]);
    const my = FGV.exec(reszek[1]);
    const mt = PTART.exec(reszek[2]);
    if (mx && my && mt && jo(mx[1], my[1], mt[2], mt[3])) {
      return {
        fajta: 'parameteres',
        x: mx[1].trim(),
        y: my[1].trim(),
        t: mt[1],
        tartomany: [mt[2].trim(), mt[3].trim()],
        cimke,
      };
    }
  }
  return null;
}

/** A blokk tartalma (kerítés nélkül) → `Abra`; soronkénti hiba a `hibak`-ban, az ismeretlen sor megmarad. */
export function elemez(szoveg: string): Abra {
  if ((szoveg ?? '').length > MAX_BLOKK) {
    return { x_tartomany: null, y_tartomany: null, elemek: [], hibak: [[0, tx('túl nagy blokk')]] };
  }
  let xt: [string, string] | null = null;
  let yt: [string, string] | null = null;
  const elemek: Elem[] = [];
  const hibak: [number, string][] = [];
  sorok(szoveg ?? '').forEach((nyers, i) => {
    const n = i + 1;
    const sor = tisztit(nyers);
    if (!sor) return;
    if (sor.startsWith('#')) {
      elemek.push({ fajta: 'megjegyzes', szoveg: sor.slice(1).trim() });
      return;
    }
    if (sor.length > MAX_SOR) {
      elemek.push({ fajta: 'ismeretlen', sor });
      hibak.push([n, tx('a sor hosszabb {n} jelnél', { n: MAX_SOR })]);
      return;
    }
    const e = elem(tisztit(megjegyzesNelkul(sor)));
    if (e === null) {
      elemek.push({ fajta: 'ismeretlen', sor });
      hibak.push([n, tx('ismeretlen vagy hibás sor')]);
    } else if ('tartomany' in e && !('fajta' in e)) {
      if (e.tartomany === 'x' && xt === null) xt = e.ertek;
      else if (e.tartomany === 'y' && yt === null) yt = e.ertek;
      else {
        elemek.push({ fajta: 'ismeretlen', sor });
        hibak.push([n, tx('a tartomány már meg van adva')]);
      }
    } else if (elemek.filter((k) => k.fajta !== 'megjegyzes' && k.fajta !== 'ismeretlen').length >= MAX_ELEM) {
      elemek.push({ fajta: 'ismeretlen', sor });
      hibak.push([n, tx('legfeljebb {n} rajzelem', { n: MAX_ELEM })]);
    } else {
      elemek.push(e as Elem);
    }
  });
  return { x_tartomany: xt, y_tartomany: yt, elemek, hibak };
}

function cimkeSzoveg(cimke: string | null): string {
  return cimke !== null ? ` "${lev(cimke)}"` : '';
}

function sor(e: Elem): string {
  switch (e.fajta) {
    case 'fuggveny':
      return `y = ${e.kifejezes}${cimkeSzoveg(e.cimke)}`;
    case 'parameteres':
      return `x = ${e.x}, y = ${e.y}, ${e.t} in [${e.tartomany[0]}, ${e.tartomany[1]}]${cimkeSzoveg(e.cimke)}`;
    case 'egyenlotlenseg':
      return `y ${e.relacio} ${e.kifejezes}${cimkeSzoveg(e.cimke)}`;
    case 'pont':
      return `pont (${e.x}, ${e.y})${cimkeSzoveg(e.cimke)}`;
    case 'megjegyzes':
      return `# ${e.szoveg}`.trimEnd();
    case 'ismeretlen':
      return e.sor;
  }
}

/** Kanonikus szöveg (kerítés nélkül, záró újsor nélkül): előbb az `x`, `y` tartomány, aztán az elemek. */
export function szerializal(abra: Abra): string {
  const ki: string[] = [];
  if (abra.x_tartomany) ki.push(`x in [${abra.x_tartomany[0]}, ${abra.x_tartomany[1]}]`);
  if (abra.y_tartomany) ki.push(`y in [${abra.y_tartomany[0]}, ${abra.y_tartomany[1]}]`);
  for (const e of abra.elemek) ki.push(sor(e));
  return ki.join('\n');
}
