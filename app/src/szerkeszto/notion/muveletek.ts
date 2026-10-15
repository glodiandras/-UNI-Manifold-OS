// A blokkok szerkesztő-műveletei (C09): mozgatás, átalakítás, duplikálás, törlés, blokkazonosító. Tiszta
// függvények: az `EditorState`-ből és a blokkmodellből egy `Szerkesztes`-t (csere + kurzor) adnak, a nézet
// ezt egyetlen tranzakcióban alkalmazza (egy ⌘Z visszavonja).
//
// A műveletek a sorok tömbjén dolgoznak (`state.doc.toJSON()`), a végén a régi és az új tömb legkisebb
// sor-cseréje lesz a változás. Így a kimenet a blokk szövegét bájtra őrzi, a sorvég (`\n` vagy `\r\n`) pedig
// a dokumentumé marad. Legfelső szinten a blokkok között egy üres sor áll (a művelet ezt tartja): a beszúrt
// blokk köré, és a kivett blokk helyére is, ha a két szomszédja üres sor nélkül állt (különben a szomszédok
// összeolvadnának: két bekezdés eggyé, a táblázat elnyelné a bekezdést, az idézet lusta folytatása). A
// listaelemek szorosak vagy lazák maradnak a céllistájuk szerint.

import type { ChangeSpec, EditorState } from '@codemirror/state';
import { type Blokk, blokkEleje, fejezetSzoveg, lazaLista, leszarmazott, testverek } from './blokkmodell';

export interface Szerkesztes {
  changes: ChangeSpec;
  selection: { anchor: number; head?: number };
}

/** Egy mozgatás célja: egy blokk elé / mögé, vagy (listaelemnél) az elem gyerekeként. */
export interface Cel {
  blokk: Blokk;
  hely: 'elott' | 'utan' | 'gyerek';
}

const URES = /^[ \t]*$/;
export const ures = (s: string | undefined): boolean => s === undefined || URES.test(s);

/** A szóköz/tabulátor oszlopszélessége (a tabulátor 4 széles). */
function oszlop(ws: string): number {
  let o = 0;
  for (const c of ws) o = c === '\t' ? o + (4 - (o % 4)) : o + 1;
  return o;
}

function behuzasOszloppal(cols: number, tabos: boolean): string {
  return tabos ? '\t'.repeat(Math.floor(cols / 4)) + ' '.repeat(cols % 4) : ' '.repeat(cols);
}

// ---------------------------------------------------------------------- a sorok tömbje → változás

/** A kurzor az új sorokban: a sor száma (0-alapú) és az oszlopa; oszlop nélkül a sor végén; `veg` esetén
 *  az `oszlop`–`veg` szakasz ki van jelölve. */
export type Kurzor = number | { sor: number; oszlop?: number; veg?: number };

/** A régi (a dokumentum) és az új sorok legkisebb sor-cseréje, a kurzorral az új sorok között. */
export function szerkesztes(state: EditorState, uj: string[], kurzor: Kurzor = 0): Szerkesztes | null {
  if (uj.length === 0) uj = [''];
  const doc = state.doc;
  const regi = doc.toJSON();
  const br = state.lineBreak;
  const max = Math.min(regi.length, uj.length);
  let p = 0;
  while (p < max && regi[p] === uj[p]) p++;
  if (p === regi.length && p === uj.length) return null;
  let s = 0;
  while (s < max - p && regi[regi.length - 1 - s] === uj[uj.length - 1 - s]) s++;
  const regiVeg = regi.length - s;
  const ujVeg = uj.length - s;
  let changes: ChangeSpec;
  if (regiVeg > p && ujVeg > p) {
    changes = { from: doc.line(p + 1).from, to: doc.line(regiVeg).to, insert: uj.slice(p, ujVeg).join(br) };
  } else if (regiVeg === p) {
    if (p < regi.length) {
      const hely = doc.line(p + 1).from;
      changes = { from: hely, to: hely, insert: uj.slice(p, ujVeg).join(br) + br };
    } else changes = { from: doc.length, to: doc.length, insert: br + uj.slice(p, ujVeg).join(br) };
  } else if (regiVeg < regi.length) {
    changes = { from: doc.line(p + 1).from, to: doc.line(regiVeg + 1).from, insert: '' };
  } else {
    changes = { from: doc.line(p).to, to: doc.length, insert: '' };
  }
  const k = typeof kurzor === 'number' ? { sor: kurzor } : kurzor;
  const sor = Math.max(0, Math.min(k.sor, uj.length - 1));
  let eltolas = 0;
  for (let i = 0; i < sor; i++) eltolas += uj[i].length + 1; // a CodeMirror a sortörést mindig egy jelnek számolja
  const hossz = uj[sor].length;
  const oszlop = Math.min(k.oszlop ?? hossz, hossz);
  return {
    changes,
    selection: k.veg === undefined ? { anchor: eltolas + oszlop } : { anchor: eltolas + oszlop, head: eltolas + Math.min(k.veg, hossz) },
  };
}

// ---------------------------------------------------------------------- kivétel és beszúrás

/** Egy kivétel: a [r0, r1) sorok (félig nyílt) helyére `tolt` üres sor (0 vagy 1) kerül. */
type Kivetel = [r0: number, r1: number, tolt: number];

/** Legfelső szintű blokk sorainak kivétele: a körülötte álló üres sorból egy marad; ha a két szomszéd sor
 *  üres sor nélkül állt, a varratba üres sor kerül (`tolt`), hogy a szomszédok ne olvadjanak össze. */
function docKivesz(sorok: string[], a: number, b: number): Kivetel {
  let r0 = a;
  let r1 = b + 1;
  const elozoUres = a === 0 || ures(sorok[a - 1]);
  const kovetkezoUres = r1 >= sorok.length || ures(sorok[r1]);
  if (elozoUres && kovetkezoUres && r1 < sorok.length) r1++;
  else if (a > 0 && ures(sorok[a - 1]) && r1 >= sorok.length) r0--;
  return [r0, r1, !elozoUres && !kovetkezoUres ? 1 : 0];
}

function listaKivesz(sorok: string[], bl: readonly Blokk[], src: Blokk): Kivetel {
  const a = src.elsoSor - 1;
  const b = src.utolsoSor - 1;
  const tv = testverek(bl, src);
  if (src.szulo === null && tv.length === 1) return docKivesz(sorok, a, b);
  if (lazaLista(tv)) {
    const vanKovetkezo = tv.findIndex((x) => x.index === src.index) < tv.length - 1;
    if (vanKovetkezo && ures(sorok[b + 1])) return [a, b + 2, 0];
    if (!vanKovetkezo && a > 0 && ures(sorok[a - 1])) return [a - 1, b + 1, 0];
  }
  return [a, b + 1, 0];
}

/** A sorok a kivétel után: a [r0, r1) helyén a `tolt` üres sor. */
function kivetelEredmeny(sorok: string[], [r0, r1, tolt]: Kivetel): string[] {
  return [...sorok.slice(0, r0), ...Array<string>(tolt).fill(''), ...sorok.slice(r1)];
}

/** A `p` régi sorindex helye a [r0, r1) kivétel után (a `tolt` sor a kivétel helyén marad). */
function kivetelUtan(p: number, [r0, r1, tolt]: Kivetel): number {
  if (p >= r1) return p - (r1 - r0) + tolt;
  return p > r0 ? r0 : p;
}

export function docBeszur(arr: string[], p: number, m: string[]): { arr: string[]; kezd: number } {
  const elott = p > 0 && !ures(arr[p - 1]);
  const utan = p < arr.length && !ures(arr[p]);
  const be = [...(elott ? [''] : []), ...m, ...(utan ? [''] : [])];
  return { arr: [...arr.slice(0, p), ...be, ...arr.slice(p)], kezd: p + (elott ? 1 : 0) };
}

// ---------------------------------------------------------------------- listaelem átépítése és számozás

const SORSZAM = /^([ \t]*)(\d+)([.)])/;

/** A listaelem sorai új behúzással és jelölővel; a gyerekei az új szülőhöz igazodnak. */
function atepit(sorok: string[], src: Blokk, behuzas: string, jel: string): string[] {
  const l = src.lista!;
  const elso = sorok[src.elsoSor - 1];
  const marad = elso.slice(l.behuzas.length + l.jel.length + l.szokoz.length);
  const ki = [behuzas + jel + l.szokoz + marad];
  const regiTartalom = oszlop(l.behuzas) + oszlop(l.jel + l.szokoz);
  const ujTartalom = oszlop(behuzas) + oszlop(jel + l.szokoz);
  const tabos = behuzas.includes('\t');
  for (let i = src.elsoSor; i < src.utolsoSor; i++) {
    const s = sorok[i];
    if (ures(s)) {
      ki.push(s);
      continue;
    }
    const w = /^[ \t]*/.exec(s)![0];
    if (w.includes('\t') || oszlop(w) < regiTartalom) {
      ki.push(s.startsWith(l.behuzas) ? behuzas + s.slice(l.behuzas.length) : s);
      continue;
    }
    ki.push(behuzasOszloppal(ujTartalom + oszlop(w) - regiTartalom, tabos) + s.slice(w.length));
  }
  return ki;
}

/** Az ordered lista elemeinek újraszámozása (a `sorok` helyben módosul), ha az eredeti számozás folyamatos volt. */
function ujraszamoz(arr: string[], elemek: number[], kezdo: number): void {
  elemek.forEach((sor, k) => {
    arr[sor] = arr[sor].replace(SORSZAM, (_m, ws: string, _n: string, d: string) => `${ws}${kezdo + k}${d}`);
  });
}

function folyamatos(tv: readonly Blokk[]): boolean {
  if (!tv[0]?.lista?.rendezett) return false;
  const kezd = tv[0].lista.szam ?? 0;
  return tv.every((b, k) => b.lista!.szam === kezd + k);
}

// ---------------------------------------------------------------------- mozgatás

function celJel(src: Blokk, z: Blokk, hely: Cel['hely']): { behuzas: string; jel: string } {
  const l = z.lista!;
  if (hely === 'gyerek') {
    const egyseg = l.behuzas.includes(' ') ? ' '.repeat(oszlop(l.jel + l.szokoz)) : '\t';
    return { behuzas: l.behuzas + egyseg, jel: src.lista!.rendezett ? '1.' : src.lista!.jel };
  }
  if (l.rendezett) return { behuzas: l.behuzas, jel: `${l.szam}${l.jel.slice(-1)}` };
  return { behuzas: l.behuzas, jel: l.jel };
}

function docCelPozicio(bl: readonly Blokk[], cel: Cel): number | null {
  const b = cel.blokk;
  if (cel.hely === 'gyerek') return null;
  if (b.lista) {
    if (b.szulo !== null) return null;
    const tv = testverek(bl, b);
    return cel.hely === 'elott' ? tv[0].elsoSor - 1 : tv[tv.length - 1].utolsoSor;
  }
  return cel.hely === 'elott' ? blokkEleje(b) - 1 : b.utolsoSor;
}

export function mozgat(state: EditorState, bl: readonly Blokk[], src: Blokk, cel: Cel): Szerkesztes | null {
  if (cel.blokk.index === src.index || leszarmazott(bl, cel.blokk, src)) return null;
  // C31 (T161): a lezáratlan kerítés/`%%` nem mozog, és utána (a belsejébe) nem kerül blokk
  if (!src.mozgathato || (!cel.blokk.mozgathato && cel.hely !== 'elott')) return null;
  const sorok = state.doc.toJSON();
  const ujSorok = src.lista ? listaMozgat(sorok, bl, src, cel) : docMozgat(sorok, bl, src, cel);
  if (!ujSorok) return null;
  return szerkesztes(state, ujSorok.sorok, ujSorok.kurzor);
}

function docMozgat(sorok: string[], bl: readonly Blokk[], src: Blokk, cel: Cel): { sorok: string[]; kurzor: number } | null {
  if (cel.blokk.lista && cel.blokk.lista.listaFrom === src.lista?.listaFrom) return null;
  const p = docCelPozicio(bl, cel);
  if (p === null) return null;
  const a = blokkEleje(src) - 1;
  const b = src.utolsoSor - 1;
  const kivetel = docKivesz(sorok, a, b);
  const be = docBeszur(kivetelEredmeny(sorok, kivetel), kivetelUtan(p, kivetel), sorok.slice(a, b + 1));
  // a kurzor a blokk első fogható során áll (a PDF-kiemelésnél az idézeten, nem a jelölősoron: onnan nincs blokk)
  return { sorok: be.arr, kurzor: be.kezd + (src.elsoSor - blokkEleje(src)) };
}

function listaMozgat(sorok: string[], bl: readonly Blokk[], src: Blokk, cel: Cel): { sorok: string[]; kurzor: number } | null {
  let z = cel.blokk;
  let hely = cel.hely;
  if (!z.lista) return null;
  if (hely === 'gyerek' && z.gyerekek.length) {
    z = bl[z.gyerekek[0]];
    hely = 'elott';
  }
  const S = testverek(bl, src);
  const ujLista = hely === 'gyerek';
  const T = ujLista ? [] : testverek(bl, z);
  const { behuzas, jel } = celJel(src, z, hely);
  const m = atepit(sorok, src, behuzas, jel);
  const p = hely === 'elott' ? z.elsoSor - 1 : z.utolsoSor;

  const kivetel = listaKivesz(sorok, bl, src);
  const [r0, r1, tolt] = kivetel;
  const arr2 = kivetelEredmeny(sorok, kivetel);
  const p2 = kivetelUtan(p, kivetel);
  const laza = !ujLista && lazaLista(T);
  const be = laza ? (hely === 'elott' ? [...m, ''] : ['', ...m]) : m;
  const kezd = p2 + (laza && hely !== 'elott' ? 1 : 0);
  const arr3 = [...arr2.slice(0, p2), ...be, ...arr2.slice(p2)];

  // a számozott listák újraszámozása (csak ha eredetileg folyamatosak voltak)
  const uj = (i: number): number => {
    const j = i >= r1 ? i - (r1 - r0) + tolt : i;
    return j >= p2 ? j + be.length : j;
  };
  const maradok = (lista: readonly Blokk[]) => lista.filter((x) => x.index !== src.index).map((x) => uj(x.elsoSor - 1));
  const lista = (tv: readonly Blokk[], extra: number[]) => {
    if (!folyamatos(tv)) return;
    const sorokUj = [...maradok(tv), ...extra].sort((x, y) => x - y);
    ujraszamoz(arr3, sorokUj, tv[0].lista!.szam ?? 1);
  };
  if (T.length && T[0].lista!.listaFrom === S[0].lista!.listaFrom) lista(S, [kezd]);
  else {
    if (S.length > 1) lista(S, []);
    if (T.length) lista(T, [kezd]);
  }
  return { sorok: arr3, kurzor: kezd };
}

// ---------------------------------------------------------------------- duplikálás, törlés

/** A blokk sorai az önálló `^id` sor nélkül, és a sorvégi `^id` nélkül (az azonosító egyedi marad). A PDF-kiemelés
 *  jelölősora (`jelolo`) nem másolódik: a másolat sima idézet, nem második, azonos azonosítójú kiemelés. */
function masolatSorok(sorok: string[], src: Blokk): string[] {
  let m = sorok.slice(src.elsoSor - 1, src.utolsoSor);
  if (src.id && src.idMod === 'onallo') {
    m = m.slice(0, -1);
    while (m.length && ures(m[m.length - 1])) m = m.slice(0, -1);
  } else if (src.id) {
    const k = src.szovegVegSor - src.elsoSor;
    m[k] = m[k].replace(/[ \t]*\^[A-Za-z0-9-]+[ \t]*$/, '');
  }
  return m;
}

export function duplikal(state: EditorState, bl: readonly Blokk[], src: Blokk): Szerkesztes | null {
  const sorok = state.doc.toJSON();
  const m = masolatSorok(sorok, src);
  if (!src.lista) {
    const be = docBeszur(sorok, src.utolsoSor, m);
    return szerkesztes(state, be.arr, be.kezd);
  }
  const T = testverek(bl, src);
  const l = src.lista;
  const jel = l.rendezett ? `${l.szam}${l.jel.slice(-1)}` : l.jel;
  const kopi = atepit(m, { ...src, elsoSor: 1, utolsoSor: m.length }, l.behuzas, jel);
  const p = src.utolsoSor;
  const laza = lazaLista(T);
  const be = laza ? ['', ...kopi] : kopi;
  const arr = [...sorok.slice(0, p), ...be, ...sorok.slice(p)];
  const kezd = p + (laza ? 1 : 0);
  if (folyamatos(T)) {
    const elemek = [...T.map((x) => (x.elsoSor - 1 >= p ? x.elsoSor - 1 + be.length : x.elsoSor - 1)), kezd].sort((x, y) => x - y);
    ujraszamoz(arr, elemek, T[0].lista!.szam ?? 1);
  }
  return szerkesztes(state, arr, kezd);
}

export function torol(state: EditorState, bl: readonly Blokk[], src: Blokk): Szerkesztes | null {
  const sorok = state.doc.toJSON();
  const kivetel = src.lista ? listaKivesz(sorok, bl, src) : docKivesz(sorok, blokkEleje(src) - 1, src.utolsoSor - 1);
  const [r0, r1, tolt] = kivetel;
  const arr = kivetelEredmeny(sorok, kivetel);
  if (src.lista) {
    const tv = testverek(bl, src);
    if (folyamatos(tv) && tv.length > 1) {
      const elemek = tv.filter((x) => x.index !== src.index).map((x) => (x.elsoSor - 1 >= r1 ? x.elsoSor - 1 - (r1 - r0) + tolt : x.elsoSor - 1));
      ujraszamoz(arr, elemek, tv[0].lista!.szam ?? 1);
    }
  }
  // a kurzor a kivett blokk utáni első sorra áll (a varratba tett üres sor mögé)
  return szerkesztes(state, arr, Math.min(r0 + tolt, Math.max(0, arr.length - 1)));
}

// ---------------------------------------------------------------------- átalakítás

export type AtalakitCel =
  | { tipus: 'szoveg' }
  | { tipus: 'fejezet'; szint: number }
  | { tipus: 'lista' }
  | { tipus: 'szamozott' }
  | { tipus: 'feladat' }
  | { tipus: 'idezet' }
  | { tipus: 'callout'; callout: string }
  | { tipus: 'kod'; nyelv?: string };

const LISTA_CELOK = new Set<AtalakitCel['tipus']>(['lista', 'szamozott', 'feladat']);

function levag(s: string, cols: number): string {
  let o = 0;
  let i = 0;
  while (i < s.length && o < cols && (s[i] === ' ' || s[i] === '\t')) {
    o = s[i] === '\t' ? o + (4 - (o % 4)) : o + 1;
    i++;
  }
  return s.slice(i);
}

/** A blokk tartalma az előtagja (jelölő, `>`, kerítés) nélkül; null, ha a típus nem alakítható. */
function tartalom(sorok: string[], src: Blokk): string[] | null {
  const mind = sorok.slice(src.elsoSor - 1, src.utolsoSor);
  switch (src.tipus) {
    case 'bekezdes':
      return mind;
    case 'fejezet':
      return /^[ \t]{0,3}#/.test(mind[0]) ? [fejezetSzoveg(mind[0])] : mind.slice(0, -1);
    case 'listaelem': {
      const l = src.lista!;
      const jelHossz = l.behuzas.length + l.jel.length + l.szokoz.length;
      let elso = mind[0].slice(jelHossz);
      if (l.feladat !== null) elso = elso.replace(/^\[.\][ \t]?/u, '');
      const tart = oszlop(l.behuzas) + oszlop(l.jel + l.szokoz);
      return [elso, ...mind.slice(1).map((s) => (ures(s) ? s : levag(s, tart)))];
    }
    case 'idezet':
      return mind.map((s) => s.replace(/^[ \t]{0,3}>[ ]?/, ''));
    case 'callout': {
      const fej = /^[ \t]{0,3}>[ ]?\[![^\]\s]+\][+-]?[ \t]*(.*)$/.exec(mind[0]);
      const cim = fej?.[1].trim() ?? '';
      return [...(cim ? [cim] : []), ...mind.slice(1).map((s) => s.replace(/^[ \t]{0,3}>[ ]?/, ''))];
    }
    case 'kod': {
      if (!/^[ \t]*(`{3,}|~{3,})/.test(mind[0])) return mind.map((s) => levag(s, 4));
      const veg = mind.length > 1 && /^[ \t]*(`{3,}|~{3,})[ \t]*$/.test(mind[mind.length - 1]) ? mind.length - 1 : mind.length;
      return mind.slice(1, veg);
    }
    default:
      return null;
  }
}

/** Az átalakítás érvényes-e a blokkra (a menü a nem érvényeset kihagyja vagy halványítja). */
export function atalakithato(sorok: string[], src: Blokk, cel: AtalakitCel): boolean {
  if (src.jelolo !== null) return false; // a PDF-kiemelés blokkja: a jelölő nélküli idézet már nem kiemelés
  if (src.id && src.idMod !== 'sorveg') return false;
  const c = tartalom(sorok, src);
  if (!c) return false;
  if (src.tipus === 'listaelem') {
    if (!LISTA_CELOK.has(cel.tipus) && (src.gyerekek.length > 0 || src.szulo !== null)) return false;
    if (src.lista!.feladat !== null && cel.tipus === 'feladat') return false;
    if (cel.tipus === 'lista' && !src.lista!.rendezett && src.lista!.feladat === null) return false;
    if (cel.tipus === 'szamozott' && src.lista!.rendezett && src.lista!.feladat === null) return false;
  }
  if (cel.tipus === 'fejezet') {
    if (c.length !== 1 || src.id) return false;
    if (src.tipus === 'fejezet' && src.szint === cel.szint) return false;
  }
  if (cel.tipus === 'kod' && (src.id || src.tipus === 'kod')) return false;
  if (cel.tipus === 'szoveg' && src.tipus === 'bekezdes') return false;
  if (cel.tipus === 'idezet' && src.tipus === 'idezet') return false;
  if (cel.tipus === 'callout' && src.tipus === 'callout' && src.calloutTipus?.toLowerCase() === cel.callout.toLowerCase()) return false;
  return true;
}

function kerites(c: string[]): string {
  let hossz = 3;
  for (const s of c) for (const m of s.matchAll(/`+/g)) if (m[0].length >= hossz) hossz = m[0].length + 1;
  return '`'.repeat(hossz);
}

function epit(cel: AtalakitCel, c: string[]): string[] {
  const prefix = (elso: string, kov: string) => c.map((s, i) => (i === 0 ? elso + s : ures(s) ? s : kov + s));
  switch (cel.tipus) {
    case 'szoveg':
      return c;
    case 'fejezet':
      return [`${'#'.repeat(cel.szint)} ${c[0]}`.trimEnd()];
    case 'lista':
      return prefix('- ', '  ');
    case 'szamozott':
      return prefix('1. ', '   ');
    case 'feladat':
      return prefix('- [ ] ', '  ');
    case 'idezet':
      return c.map((s) => (s === '' ? '>' : `> ${s}`));
    case 'callout':
      return [`> [!${cel.callout}]`, ...c.map((s) => (s === '' ? '>' : `> ${s}`))];
    case 'kod': {
      const k = kerites(c);
      return [k + (cel.nyelv ?? ''), ...c, k];
    }
  }
}

export function atalakit(state: EditorState, src: Blokk, cel: AtalakitCel): Szerkesztes | null {
  const sorok = state.doc.toJSON();
  if (!atalakithato(sorok, src, cel)) return null;
  const a = src.elsoSor - 1;
  const b = src.utolsoSor - 1;

  // listaelem → listaelem: csak a jelölő cserélődik, a gyerekek érintetlenek
  if (src.tipus === 'listaelem' && LISTA_CELOK.has(cel.tipus)) {
    const l = src.lista!;
    const jel = cel.tipus === 'szamozott' ? '1.' : l.rendezett ? '-' : l.jel;
    const feladat = cel.tipus === 'feladat' ? '[ ] ' : '';
    const elso = sorok[a];
    let marad = elso.slice(l.behuzas.length + l.jel.length + l.szokoz.length);
    if (l.feladat !== null) marad = marad.replace(/^\[.\][ \t]?/u, '');
    const ujElso = `${l.behuzas}${cel.tipus === 'feladat' && l.rendezett ? l.jel : jel} ${feladat}${marad}`;
    const arr = [...sorok.slice(0, a), ujElso, ...sorok.slice(a + 1)];
    return szerkesztes(state, arr, a);
  }

  // callout → másik típus: csak a típusnév cserélődik
  if (src.tipus === 'callout' && cel.tipus === 'callout') {
    const arr = [...sorok];
    arr[a] = arr[a].replace(/(\[!)[^\]\s]+(\])/, `$1${cel.callout}$2`);
    return szerkesztes(state, arr, a);
  }

  const c = tartalom(sorok, src)!;
  let ki = epit(cel, c);
  // a lista belsejéből kilépő blokk körül üres sor kell (a lista kettéválik)
  if (src.tipus === 'listaelem' && !LISTA_CELOK.has(cel.tipus)) {
    const elott = a > 0 && !ures(sorok[a - 1]);
    const utan = b + 1 < sorok.length && !ures(sorok[b + 1]);
    ki = [...(elott ? [''] : []), ...ki, ...(utan ? [''] : [])];
    const arr = [...sorok.slice(0, a), ...ki, ...sorok.slice(b + 1)];
    return szerkesztes(state, arr, a + (elott ? 1 : 0));
  }
  // C29.7b (a T035 rokona): az eredmény „folytatható” blokk (bekezdés, idézet, callout, listaelem), a szomszéd pedig üres sor nélkül
  // állt mellette — az utána álló sort az idézet/listaelem lustán folytatná, a bekezdés mindkét irányba összeolvadna. A varratba
  // üres sor kerül. (Az előző bekezdést az idézet és a lista megszakítja, ezért ott csak a bekezdésnél kell.)
  const folytathato = cel.tipus === 'szoveg' || cel.tipus === 'idezet' || cel.tipus === 'callout' || LISTA_CELOK.has(cel.tipus);
  const elott = cel.tipus === 'szoveg' && a > 0 && !ures(sorok[a - 1]);
  const utan = folytathato && b + 1 < sorok.length && !ures(sorok[b + 1]);
  ki = [...(elott ? [''] : []), ...ki, ...(utan ? [''] : [])];
  const arr = [...sorok.slice(0, a), ...ki, ...sorok.slice(b + 1)];
  return szerkesztes(state, arr, a + (elott ? 1 : 0));
}

// ---------------------------------------------------------------------- blokkazonosító és link

const ID_BETUK = 'abcdefghijklmnopqrstuvwxyz0123456789';

export function ujBlokkId(state: EditorState, veletlen: () => number = Math.random): string {
  const szoveg = state.doc.toString();
  const van = new Set<string>();
  for (const m of szoveg.matchAll(/\^([A-Za-z0-9-]+)/g)) van.add(m[1]);
  for (;;) {
    let id = '';
    for (let i = 0; i < 6; i++) id += ID_BETUK[Math.floor(veletlen() * ID_BETUK.length)];
    if (!van.has(id)) return id;
  }
}

/** A blokk azonosítójának beírása. Szöveges blokknál a szöveg sorvégére, nem szövegesnél (kód, táblázat …)
 *  üres sor után önálló sorba. A fejezetnek nincs azonosítója (az Obsidian a `#Cím` alakkal linkeli). Ha a
 *  blokknak már van azonosítója, az marad, és nincs változás. */
export function idBeir(
  state: EditorState,
  src: Blokk,
  id: string,
): { id: string; szerkesztes: Szerkesztes | null } | null {
  if (src.idMod === 'nincs') return null;
  if (src.id) return { id: src.id, szerkesztes: null };
  const sorok = state.doc.toJSON();
  if (src.idMod === 'sorveg') {
    const k = src.szovegVegSor - 1;
    const arr = [...sorok];
    arr[k] = `${arr[k].replace(/[ \t]+$/, '')} ^${id}`;
    return { id, szerkesztes: szerkesztes(state, arr, k) };
  }
  const p = src.utolsoSor;
  const be = ['', `^${id}`, ...(p < sorok.length && !ures(sorok[p]) ? [''] : [])];
  const arr = [...sorok.slice(0, p), ...be, ...sorok.slice(p)];
  return { id, szerkesztes: szerkesztes(state, arr, p + 1) };
}

/** A fejezetlink szövege: a `#`, `|`, `^`, `[`, `]` jelek az Obsidianban nem állhatnak a fejezet nevében. */
export function fejezetLinkSzoveg(sor: string): string {
  return fejezetSzoveg(sor).replace(/[#|^[\]]/g, ' ').replace(/\s+/g, ' ').trim();
}

/** A blokk linkje: `[[Név#^id]]`, fejezetnél `[[Név#Cím]]`. */
export function blokkLink(nev: string, src: Blokk, id: string | null, sorSzoveg: string): string | null {
  if (src.tipus === 'fejezet') return `[[${nev}#${fejezetLinkSzoveg(sorSzoveg)}]]`;
  return id ? `[[${nev}#^${id}]]` : null;
}

