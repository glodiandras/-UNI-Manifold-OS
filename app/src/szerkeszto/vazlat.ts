// A Vázlat (Outline) tiszta logikája (11-graph-06/07/08): a fejezetek fája, az összecsukás és a szűrő láthatósága, a szakaszok
// és — az adatbiztonság szempontjából a lényeg — a szakasz-áthelyezés terve. A modul DOM és Svelte nélkül tesztelhető.
//
// A szakasz-áthelyezés a jegyzetet CSAK a szerkesztő meglévő útján írja: a terv egyetlen CodeMirror-tranzakció (törlés +
// beszúrás), amelyet a szerkesztő komponens a nézetén át küld el, így a `Dokumentum` változáskövetése, az automatikus mentés,
// az alap-hash alapú ütközés-felismerés (409) és a visszavonás (egy lépés) mind változatlanul érvényes. Ez a modul semmit
// nem ír; csak kiszámolja, mit kellene, és megmondja, mikor TILOS (csak olvasható, ütközés, Olvasó mód, elavult nézet).

import { ChangeSet, type ChangeSpec, type EditorState } from '@codemirror/state';
import type { VazlatElem } from './szerkesztok.svelte';

// ------------------------------------------------------------------ a fa és a láthatóság

/** Egy sor a Vázlatban: a fejezet, a szülője és a stabil kulcsa (az összecsukás állapotának). */
export interface VazlatSor {
  /** az `elemek` tömbbeli indexe */
  i: number;
  elem: VazlatElem;
  /** Az azonos szint + szöveg + előfordulás sorszáma: a szerkesztés közben is stabil (a sorszám nem), szintváltáskor új kulcs. */
  kulcs: string;
  /** a szülő sor indexe (az `elemek`-ben), vagy -1 */
  szulo: number;
  /** van-e alatta mélyebb szintű fejezet */
  gyerek: boolean;
  /** a behúzás: a szint a legkisebb szinthez képest */
  mely: number;
}

export function vazlatSorok(elemek: readonly VazlatElem[]): VazlatSor[] {
  const legkisebb = elemek.reduce((m, e) => Math.min(m, e.szint), 6);
  const latott = new Map<string, number>();
  const verem: number[] = [];
  const ki: VazlatSor[] = [];
  elemek.forEach((e, i) => {
    const alap = `${e.szint}\u0001${e.szoveg}`;
    const n = latott.get(alap) ?? 0;
    latott.set(alap, n + 1);
    while (verem.length && elemek[verem[verem.length - 1]].szint >= e.szint) verem.pop();
    ki.push({ i, elem: e, kulcs: `${alap}\u0001${n}`, szulo: verem.length ? verem[verem.length - 1] : -1, gyerek: false, mely: Math.max(0, e.szint - legkisebb) });
    verem.push(i);
  });
  for (const s of ki) if (s.szulo >= 0) ki[s.szulo].gyerek = true;
  return ki;
}

/** Ékezet- és kisbetű-független összehasonlító alak (a szűrőhöz). */
export function egyszerusit(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

/**
 * A látható sorok. Szűrő nélkül: az összecsukott fejezet alatti sorok rejtve. Szűrővel: a találatok és az őseik (az összecsukás
 * ilyenkor nem rejt: a találatnak látszania kell), a nem illeszkedő ős halványan, csak a szerkezetért marad.
 */
export function latszoSorok(sorok: readonly VazlatSor[], osszecsukott: ReadonlySet<string>, szuro: string): { sor: VazlatSor; talalat: boolean }[] {
  const q = egyszerusit(szuro.trim());
  if (q) {
    const talalat = new Set<number>();
    const lathato = new Set<number>();
    for (const s of sorok)
      if (egyszerusit(s.elem.szoveg).includes(q)) {
        talalat.add(s.i);
        for (let k = s.i; k >= 0; k = sorok[k].szulo) lathato.add(k);
      }
    return sorok.filter((s) => lathato.has(s.i)).map((sor) => ({ sor, talalat: talalat.has(sor.i) }));
  }
  const rejtett = new Set<number>();
  const ki: { sor: VazlatSor; talalat: boolean }[] = [];
  for (const s of sorok) {
    if (s.szulo >= 0 && (rejtett.has(s.szulo) || osszecsukott.has(sorok[s.szulo].kulcs))) {
      rejtett.add(s.i);
      continue;
    }
    ki.push({ sor: s, talalat: false });
  }
  return ki;
}

/** Az összecsukható (van gyereke) sorok kulcsai: az „összes összecsukása”. */
export function osszecsukhatok(sorok: readonly VazlatSor[]): string[] {
  return sorok.filter((s) => s.gyerek).map((s) => s.kulcs);
}

// ------------------------------------------------------------------ szakaszok

export interface Szakasz {
  /** a fejezet sora (1-től) */
  s0: number;
  /** a szakasz utolsó sora: a következő azonos vagy magasabb szintű fejezet előtti sor (a fájl végi sortörés nem része) */
  s1: number;
}

/** A fejezet szakasza: a fejezet sorától a következő azonos vagy magasabb szintű fejezet előtti sorig (a mélyebb fejezetek
 *  a szakaszhoz tartoznak). */
export function szakaszTartomany(doc: EditorState['doc'], elemek: readonly VazlatElem[], i: number): Szakasz {
  const s0 = elemek[i].sor;
  let veg = doc.lines;
  for (let j = i + 1; j < elemek.length; j++)
    if (elemek[j].szint <= elemek[i].szint) {
      veg = elemek[j].sor - 1;
      break;
    }
  // a záró üres „sor” csak a fájl végi sortörés: nem a szakaszé
  if (veg === doc.lines && doc.lines > s0 && doc.line(doc.lines).length === 0) veg = doc.lines - 1;
  return { s0, s1: Math.max(s0, veg) };
}

/** Az azonos szintű előző / következő testvér indexe (azonos szülő alatt), vagy -1. */
export function testverIndex(sorok: readonly VazlatSor[], i: number, irany: -1 | 1): number {
  const s = sorok[i];
  if (!s) return -1;
  for (let j = i + irany; j >= 0 && j < sorok.length; j += irany) {
    const t = sorok[j];
    if (t.elem.szint < s.elem.szint) return -1; // a szülő szakaszából kiléptünk
    if (t.elem.szint === s.elem.szint) return t.szulo === s.szulo ? j : -1;
  }
  return -1;
}

// ------------------------------------------------------------------ szakasz-áthelyezés terve

export type Hova = 'elott' | 'utan';

/** Az áthelyezés tervének kimenete: a tranzakció változtatásai az ELŐTTI dokumentum koordinátáiban. */
export interface AthelyezTerv {
  changes: ChangeSpec[];
  /** Az áthelyezett fejezet kezdete az ÚJ dokumentumban (a kurzornak és a görgetésnek). */
  fejezetPoz: number;
  /** A kiindulási szakasz sorai (1-től, az eredeti dokumentumban). */
  szakasz: Szakasz;
}

export type TervHiba = 'ervenytelen' | 'sajatReszben' | 'nincsValtozas';

/**
 * A `forras` fejezet szakaszának áthelyezése a `cel` fejezet ELÉ (`elott`) vagy a cél szakasza (és minden alatta álló fejezet)
 * UTÁN (`utan`). A szint nem változik (csak a blokk mozog; 11. audit 5. nyitott kérdés), a szakasz bájtra azonos marad
 * (a sortörést a dokumentum `lineBreak`-je adja, így CRLF-es jegyzetben is CRLF marad).
 */
export function athelyezTerv(state: EditorState, elemek: readonly VazlatElem[], forras: number, cel: number, hova: Hova): { terv: AthelyezTerv } | { hiba: TervHiba } {
  const doc = state.doc;
  if (!Number.isInteger(forras) || !Number.isInteger(cel) || !elemek[forras] || !elemek[cel]) return { hiba: 'ervenytelen' };
  for (const e of [elemek[forras], elemek[cel]]) if (e.sor < 1 || e.sor > doc.lines) return { hiba: 'ervenytelen' };
  const sz = szakaszTartomany(doc, elemek, forras);
  // a beszúrás sora: a cél fejezet sora (elé), vagy a cél szakaszát követő sor (után); doc.lines + 1 = a fájl vége (sortörés nélkül)
  const p = hova === 'elott' ? elemek[cel].sor : szakaszTartomany(doc, elemek, cel).s1 + 1;
  if (p > sz.s0 && p <= sz.s1) return { hiba: 'sajatReszben' };
  if (p === sz.s0 || p === sz.s1 + 1) return { hiba: 'nincsValtozas' };
  if (cel === forras) return { hiba: 'sajatReszben' };

  const lb = state.lineBreak;
  const blokk = state.sliceDoc(doc.line(sz.s0).from, doc.line(sz.s1).to);
  const utolso = sz.s1 >= doc.lines; // a szakasz a fájl legvégén áll (záró sortörés nélkül)
  let torles: { from: number; to: number };
  if (utolso) {
    if (sz.s0 <= 1) return { hiba: 'nincsValtozas' }; // az egész jegyzet egyetlen szakasz
    torles = { from: doc.line(sz.s0 - 1).to, to: doc.line(sz.s1).to }; // a megelőző sortöréssel együtt
  } else torles = { from: doc.line(sz.s0).from, to: doc.line(sz.s1 + 1).from };

  let beszur: { from: number; insert: string };
  if (p > doc.lines) beszur = { from: doc.length, insert: lb + blokk }; // a fájl végére (az utolsó sor után)
  else beszur = { from: doc.line(p).from, insert: blokk + lb };

  const changes: ChangeSpec[] = [torles, beszur];
  const fejezetPoz = ChangeSet.of(changes, doc.length).mapPos(beszur.from, -1) + (p > doc.lines ? lb.length : 0);
  return { terv: { changes, fejezetPoz, szakasz: sz } };
}

// ------------------------------------------------------------------ mikor tilos

/** Miért nem lehet áthelyezni (a felületnek ezt kell kimondania; angol szöveg a `t()`-vel a komponensben). */
export type AthelyezTilt =
  | 'olvaso' //          Olvasó mód: nincs szerkesztés
  | 'nincsNezet' //      a szerkesztő még nem épült fel
  | 'csakOlvashato' //   bájthűség: hibás UTF-8 vagy vegyes sorvég, a mentés felülírná
  | 'utkozes' //         a lemezen közben más változat keletkezett: a felhasználó dönt
  | 'eltunt' //          a fájl eltűnt a lemezről
  | 'betoltes' //        a dokumentum még töltődik
  | 'elavult'; //        a jegyzet a húzás megkezdése óta megváltozott

export interface AthelyezAllapot {
  mod: 'elo' | 'forras' | 'olvaso';
  nezetVan: boolean;
  csakOlvashato: string | null | undefined;
  /** a Dokumentum mentési állapota */
  allapot: 'betoltes' | 'tiszta' | 'piszkos' | 'mentes' | 'hiba' | 'utkozes' | 'eltunt' | undefined;
}

/** A tiltás oka, vagy `null`: szabad. A hiba (`hiba`: sikertelen mentés) és a futó mentés nem tilt: a gépelés is megy ilyenkor,
 *  és az újrapróba ugyanazt a CAS-utat használja. */
export function athelyezTilt(a: AthelyezAllapot): AthelyezTilt | null {
  if (a.mod === 'olvaso') return 'olvaso';
  if (!a.nezetVan) return 'nincsNezet';
  if (a.csakOlvashato) return 'csakOlvashato';
  if (a.allapot === 'utkozes') return 'utkozes';
  if (a.allapot === 'eltunt') return 'eltunt';
  if (a.allapot === 'betoltes' || a.allapot === undefined) return 'betoltes';
  return null;
}

/** Az áthelyezés kérése: a fejezetek AZONOSÍTÁSA sor + szint + szöveg szerint (nem index szerint), a kérés idejének változatával. */
export interface AthelyezKeres {
  forras: VazlatElem;
  cel: VazlatElem;
  hova: Hova;
  /** A `SzerkesztoPeldany.valtozat()` értéke a húzás megkezdésekor: ha azóta változott a szöveg, a kérés elavult. */
  valtozat: number;
}

export type AthelyezEredmeny = { kesz: true } | { kesz: false; ok: AthelyezTilt | TervHiba };

/** A kérésben megnevezett fejezet indexe a friss fejezetlistában (sor + szint + szöveg egyezik), vagy -1. */
export function elemIndex(elemek: readonly VazlatElem[], e: VazlatElem): number {
  return elemek.findIndex((x) => x.sor === e.sor && x.szint === e.szint && x.szoveg === e.szoveg);
}
