// A Notion-réteg blokkmodellje (C09): a szintaxisfából a „fogható” blokkok lapos listája. A modell tiszta
// adat (nincs DOM, nincs CodeMirror-nézet), a műveletek (`muveletek.ts`) erre és a sorokra épülnek.
//
// Fogható blokk: a Document közvetlen gyerekei (a frontmatter nem), és minden listaelem, bármely mélységben,
// a gyerekeivel együtt. A callout és az idézet egy blokk; az idézetben vagy lábjegyzetben álló listaelem nem
// külön blokk (v1-határ). A nem szöveges blokk (kód, táblázat, képlet, elválasztó …) utáni, üres sorral
// elválasztott önálló `^id` sor a blokk része, hogy mozgatáskor együtt maradjon vele. A PDF-kiemelés blokkja
// (`core/pdfkiemeles.py`: egysoros `%%manifold-kiemeles …%%` jelölősor + közvetlenül alatta az idézet) EGY blokk:
// a jelölősor a `jelolo` mezőben él, nem külön blokk és nem fogható, mert külön mozgatva az idézet árván maradna
// (a jelölő nélküli idézet nem kiemelés), duplikálva pedig kétszer állna ugyanaz a `k-…` azonosító.
//
// C31 (2. audit T160, T161): a blokkazonosító csak szöveges sorvégre kerül — ha a cél-sor kódkerítés, képlet, táblázat
// vagy HTML (egy idézet/callout végén vagy a listaelem saját sorában), a legfelső szintű blokk önálló `^id` sort kap, a
// listaelem pedig nem kap azonosítót (a menüpont tiltva). Egy blokk (egység) a több bekezdéses `%%…%%` megjegyzés és a
// nyitott HTML-konténer (`<details>` … `</details>` üres sorokkal) — a mozgatás nem vághatja ketté, és közé nem
// ejthető blokk; a lezáratlan kerítés és a lezáratlan `%%` (a szöveg végéig tart) nem mozgatható, és utána nem ejthető.

import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import type { EditorState } from '@codemirror/state';
import type { SyntaxNode } from '@lezer/common';
import { calloutAdat } from '../markdown/callout';

export type BlokkTipus =
  | 'bekezdes'
  | 'fejezet'
  | 'listaelem'
  | 'idezet'
  | 'callout'
  | 'kod'
  | 'matek'
  | 'tablazat'
  | 'elvalaszto'
  | 'html'
  | 'labjegyzet'
  | 'egyeb';

/** Hova írható a blokkazonosító: a szöveg sorvégére, önálló sorba a blokk után, vagy sehova. */
export type IdMod = 'sorveg' | 'onallo' | 'nincs';

export interface ListaAdat {
  rendezett: boolean;
  /** a jelölő szövege: `-`, `*`, `+`, `3.`, `3)` */
  jel: string;
  /** a sorszám (rendezett listánál) */
  szam: number | null;
  /** a jelölő előtti szóköz/tabulátor */
  behuzas: string;
  /** a jelölő utáni szóköz */
  szokoz: string;
  /** a feladatjelölő állapota (`' '`, `x` …), ha az elem feladat */
  feladat: string | null;
  /** a lista (BulletList/OrderedList csomópont) kezdőpozíciója: ez azonosítja a listát */
  listaFrom: number;
}

export interface Blokk {
  /** a lapos listabeli helye */
  index: number;
  tipus: BlokkTipus;
  /** fejezet szintje (1–6), egyébként 0 */
  szint: number;
  /** callout típusa a forrásban álló alakban */
  calloutTipus: string | null;
  /** kódblokk nyelve */
  nyelv: string | null;
  /** az első sor eleje és az utolsó sor vége (teljes sorok) */
  from: number;
  to: number;
  /** 1-alapú sorszámok, az önálló `^id` sorral együtt */
  elsoSor: number;
  utolsoSor: number;
  /** a blokk saját szövegének utolsó sora (listaelemnél a gyerek-lista előtt), 1-alapú */
  szovegVegSor: number;
  szulo: number | null;
  gyerekek: number[];
  lista: ListaAdat | null;
  id: string | null;
  idMod: IdMod;
  /** PDF-kiemelés: a blokkhoz tartozó jelölősor 1-alapú sora (közvetlenül az `elsoSor` előtt); egyébként null */
  jelolo: number | null;
  /** C31 (T161): hamis a lezáratlan kerítésnél és a lezáratlan `%%` megjegyzésnél (a szöveg végéig tartanak) */
  mozgathato: boolean;
}

const ID_SORVEG = /(?:^|[ \t])\^([A-Za-z0-9-]+)[ \t]*$/;
const ID_ONALLO = /^[ \t]*\^([A-Za-z0-9-]+)[ \t]*$/;
const LISTA_SOR = /^([ \t]*)([-*+]|\d{1,9}[.)])([ \t]*)(?:\[(.)\]([ \t]|$))?/u;

/** A PDF-kiemelés jelölősora. Szándékosan lazább, mint a core `pdfkiemeles.JELOLO`: nem validál (az azonosító és a
 *  téglalapok a core dolga), csak azt ismeri fel, hogy a sor a kiemelés jelölője, hogy egy blokkba kerüljön az idézettel. */
const KIEMELES_JELOLO = /^%%manifold-kiemeles\b.*%%[ \t]*$/;

const NEM_SZOVEGES = new Set<BlokkTipus>(['kod', 'matek', 'tablazat', 'elvalaszto', 'html', 'labjegyzet', 'egyeb']);

/** A szintaxisfa nem szöveges csomópontjai: ha a blokk cél-sora ilyenbe esik, oda nem kerülhet sorvégi `^id` (T160). */
const NEM_SZOVEGES_CSOMOPONT = new Set([
  'FencedCode', 'CodeBlock', 'MathBlock', 'Table', 'HTMLBlock', 'HorizontalRule', 'CommentBlock', 'ProcessingInstructionBlock',
]);
const VOID_TAG = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const HTML_NYITO = /^[ \t]{0,3}<([A-Za-z][A-Za-z0-9-]*)(?:\s[^>]*)?>/;

/** A `%%` jelek száma a szövegben, a soron belüli kód (`…`) nélkül. */
function megjegyzesJelek(szoveg: string): number {
  return (szoveg.replace(/`+[^`\n]*`+/g, '').match(/%%/g) ?? []).length;
}

export function listaSorAdat(sor: string): { behuzas: string; jel: string; szokoz: string; feladat: string | null; hossz: number } | null {
  const m = LISTA_SOR.exec(sor);
  if (!m) return null;
  return { behuzas: m[1], jel: m[2], szokoz: m[3], feladat: m[4] ?? null, hossz: m[1].length + m[2].length + m[3].length };
}

function tipusIdMod(t: BlokkTipus): IdMod {
  if (t === 'fejezet') return 'nincs';
  if (t === 'bekezdes' || t === 'listaelem' || t === 'idezet' || t === 'callout') return 'sorveg';
  return NEM_SZOVEGES.has(t) ? 'onallo' : 'nincs';
}

export function blokkok(state: EditorState): Blokk[] {
  const fa = ensureSyntaxTree(state, state.doc.length, 200) ?? syntaxTree(state);
  const doc = state.doc;
  const olvas = (a: number, b: number) => doc.sliceString(a, b);
  const ki: Blokk[] = [];

  const letrehoz = (n: SyntaxNode, tipus: BlokkTipus, rest: Partial<Blokk> = {}): Blokk => {
    const a = doc.lineAt(n.from);
    const z = doc.lineAt(Math.min(n.to, doc.length));
    return {
      index: ki.length,
      tipus,
      szint: 0,
      calloutTipus: null,
      nyelv: null,
      from: a.from,
      to: z.to,
      elsoSor: a.number,
      utolsoSor: z.number,
      szovegVegSor: z.number,
      szulo: null,
      gyerekek: [],
      lista: null,
      id: null,
      idMod: tipusIdMod(tipus),
      jelolo: null,
      mozgathato: true,
      ...rest,
    };
  };

  // T160: a sorvégi `^id` cél-sora nem szöveges (kódkerítés, képlet, táblázat, HTML a blokk végén)
  const nemSzovegesSor = (sorSzam: number, kezd: number, veg: number): boolean => {
    const sor = doc.line(sorSzam);
    let talalt = false;
    fa.iterate({
      from: Math.max(sor.from, kezd),
      to: Math.min(sor.to, veg),
      enter: (n) => {
        if (talalt) return false;
        if (NEM_SZOVEGES_CSOMOPONT.has(n.name) && n.from <= sor.to && n.to >= sor.from) talalt = true;
        return undefined;
      },
    });
    return talalt;
  };
  const idModIgazit = (b: Blokk, legfelso: boolean): void => {
    if (b.idMod !== 'sorveg' || b.id) return;
    if (nemSzovegesSor(b.szovegVegSor, b.from, b.to)) b.idMod = legfelso && (b.tipus === 'idezet' || b.tipus === 'callout') ? 'onallo' : 'nincs';
  };

  const elsoSorok = new Set<number>();
  const listaBejar = (lista: SyntaxNode, szulo: number | null) => {
    const rendezett = lista.name === 'OrderedList';
    for (let it = lista.firstChild; it; it = it.nextSibling) {
      if (it.name !== 'ListItem') continue;
      const elsoSor = doc.lineAt(it.from);
      if (elsoSorok.has(elsoSor.number)) continue; // `- - a`: ugyanazon a soron több elem
      elsoSorok.add(elsoSor.number);
      const adat = listaSorAdat(elsoSor.text);
      if (!adat) continue;
      const b = letrehoz(it, 'listaelem', {
        szulo,
        lista: {
          rendezett,
          jel: adat.jel,
          szam: rendezett ? parseInt(adat.jel, 10) : null,
          behuzas: adat.behuzas,
          szokoz: adat.szokoz,
          feladat: adat.feladat,
          listaFrom: lista.from,
        },
      });
      // a saját szöveg vége: az első bekezdés (vagy feladat) utolsó sora
      let szovegVeg = b.elsoSor;
      for (let c = it.firstChild; c; c = c.nextSibling)
        if (c.name === 'Paragraph' || c.name === 'Task') {
          szovegVeg = doc.lineAt(Math.min(c.to, doc.length)).number;
          break;
        }
      b.szovegVegSor = szovegVeg;
      b.id = ID_SORVEG.exec(doc.line(szovegVeg).text)?.[1] ?? null;
      idModIgazit(b, false);
      ki.push(b);
      if (szulo !== null) ki[szulo].gyerekek.push(b.index);
      for (let c = it.firstChild; c; c = c.nextSibling) if (c.name === 'BulletList' || c.name === 'OrderedList') listaBejar(c, b.index);
    }
  };

  const nemLista = (c: SyntaxNode): Blokk | null => {
    const fej = /^(?:ATX|Setext)Heading(\d)$/.exec(c.name);
    if (fej) return letrehoz(c, 'fejezet', { szint: Number(fej[1]) });
    switch (c.name) {
      case 'Paragraph': {
        const b = letrehoz(c, 'bekezdes');
        b.id = ID_SORVEG.exec(doc.line(b.utolsoSor).text)?.[1] ?? null;
        return b;
      }
      case 'Blockquote': {
        const a = calloutAdat(c, olvas);
        const b = letrehoz(c, a ? 'callout' : 'idezet', { calloutTipus: a?.tipus ?? null });
        b.id = ID_SORVEG.exec(doc.line(b.utolsoSor).text)?.[1] ?? null;
        idModIgazit(b, true);
        return b;
      }
      case 'FencedCode':
      case 'CodeBlock': {
        let nyelv: string | null = null;
        let jelek = 0;
        for (let g = c.firstChild; g; g = g.nextSibling) {
          if (g.name === 'CodeInfo') nyelv = olvas(g.from, g.to).trim().split(/\s+/)[0] || null;
          if (g.name === 'CodeMark') jelek++;
        }
        // T161: a lezáratlan kerítés (egyetlen `CodeMark`) a szöveg végéig tart — nem mozgatható
        return letrehoz(c, 'kod', { nyelv, mozgathato: c.name === 'CodeBlock' || jelek >= 2 });
      }
      case 'MathBlock':
        return letrehoz(c, 'matek');
      case 'Table':
        return letrehoz(c, 'tablazat');
      case 'HorizontalRule':
        return letrehoz(c, 'elvalaszto');
      case 'HTMLBlock':
        return letrehoz(c, 'html');
      case 'FootnoteDefinition':
        return letrehoz(c, 'labjegyzet');
      case 'LinkReference':
      case 'CommentBlock':
      case 'ProcessingInstructionBlock':
        return letrehoz(c, 'egyeb');
      default:
        return null;
    }
  };

  // T161: a csomóponttól induló egység vége — a több bekezdéses `%%` megjegyzés és a nyitott HTML-konténer egy blokk.
  // → [az utolsó csomópont, lezárt-e], vagy null, ha a csomópont nem nyit ilyen egységet.
  const egysegVege = (c: SyntaxNode): [SyntaxNode, boolean] | null => {
    if (c.name === 'FencedCode' || c.name === 'CodeBlock') return null;
    const szoveg = olvas(c.from, c.to);
    if (megjegyzesJelek(szoveg) % 2 === 1) {
      let utolso = c;
      for (let n = c.nextSibling; n; n = n.nextSibling) {
        utolso = n;
        if (n.name !== 'FencedCode' && n.name !== 'CodeBlock' && megjegyzesJelek(olvas(n.from, n.to)) % 2 === 1) return [n, true];
      }
      return [utolso, false];
    }
    const m = c.name === 'HTMLBlock' ? HTML_NYITO.exec(szoveg) : null;
    if (m && !VOID_TAG.has(m[1].toLowerCase())) {
      const zaro = new RegExp(`</${m[1]}\\s*>`, 'i');
      if (zaro.test(szoveg)) return null;
      for (let n = c.nextSibling; n; n = n.nextSibling) if (zaro.test(olvas(n.from, n.to))) return [n, true];
    }
    return null;
  };

  let elozo: Blokk | null = null;
  for (let c = fa.topNode.firstChild; c; c = c.nextSibling) {
    const egyseg = c.name === 'Frontmatter' ? null : egysegVege(c);
    if (egyseg && egyseg[0] !== c) {
      const [vege, lezart] = egyseg;
      const b = letrehoz(c, c.name === 'HTMLBlock' ? 'html' : 'egyeb', { mozgathato: lezart });
      const z = doc.lineAt(Math.min(vege.to, doc.length));
      b.to = z.to;
      b.utolsoSor = z.number;
      b.szovegVegSor = z.number;
      ki.push(b);
      elozo = b;
      c = vege;
      continue;
    }
    if (egyseg && !egyseg[1]) {
      // egyetlen csomópontban kezdődő, le nem zárt `%%`: a szöveg végéig tart
      const b = nemLista(c) ?? letrehoz(c, 'egyeb');
      b.mozgathato = false;
      ki.push(b);
      elozo = b;
      continue;
    }
    if (c.name === 'Frontmatter') {
      elozo = null;
      continue;
    }
    if (c.name === 'BulletList' || c.name === 'OrderedList') {
      listaBejar(c, null);
      elozo = null;
      continue;
    }
    // önálló `^id` sor a nem szöveges blokk (vagy idézet) után
    if (c.name === 'Paragraph' && elozo && elozo.id === null && (elozo.idMod === 'onallo' || elozo.tipus === 'idezet' || elozo.tipus === 'callout')) {
      const sor = doc.lineAt(c.from);
      const m = ID_ONALLO.exec(olvas(c.from, c.to));
      if (m && sor.number >= elozo.utolsoSor + 2 && doc.lineAt(c.to).number === sor.number) {
        elozo.id = m[1];
        elozo.to = sor.to;
        elozo.utolsoSor = sor.number;
        elozo.szovegVegSor = sor.number;
        continue;
      }
    }
    // PDF-kiemelés: az egysoros jelölősor és a közvetlenül a következő sorban kezdődő idézet egy blokk
    const kov = c.name === 'Paragraph' ? c.nextSibling : null;
    if (kov?.name === 'Blockquote') {
      const sor = doc.lineAt(c.from);
      if (doc.lineAt(c.to).number === sor.number && doc.lineAt(kov.from).number === sor.number + 1 && KIEMELES_JELOLO.test(sor.text)) {
        const b = nemLista(kov)!;
        b.jelolo = sor.number;
        ki.push(b);
        elozo = b;
        c = kov;
        continue;
      }
    }
    const b = nemLista(c);
    if (b) ki.push(b);
    elozo = b;
  }
  return ki;
}

/** A blokk első sora a hozzá tartozó jelölősorral együtt (1-alapú): a kivétel és a beszúrás ettől számol. */
export function blokkEleje(b: Blokk): number {
  return b.jelolo ?? b.elsoSor;
}

/** A blokk testvérei (a saját magát is beleértve): ugyanazon lista elemei; a legfelső szintű nem listaelem
 *  blokkoknak nincs testvérük ebben az értelemben. */
export function testverek(bl: readonly Blokk[], b: Blokk): Blokk[] {
  const l = b.lista;
  return l ? bl.filter((x) => x.lista && x.lista.listaFrom === l.listaFrom) : [];
}

export function leszarmazott(bl: readonly Blokk[], b: Blokk, os: Blokk): boolean {
  for (let p: number | null = b.index; p !== null; p = bl[p].szulo) if (p === os.index) return true;
  return false;
}

/** Az adott sort tartalmazó legbelső blokk (üres sorra null). */
export function blokkSorban(bl: readonly Blokk[], sor: number): Blokk | null {
  let legjobb: Blokk | null = null;
  for (const b of bl) {
    if (sor < b.elsoSor || sor > b.utolsoSor) continue;
    if (!legjobb || b.elsoSor >= legjobb.elsoSor) legjobb = b;
  }
  return legjobb;
}

/** A blokk gyökér-blokkja (a legfelső szintű listaelem); nem listaelemnél önmaga. */
export function gyoker(bl: readonly Blokk[], b: Blokk): Blokk {
  let x = b;
  while (x.szulo !== null) x = bl[x.szulo];
  return x;
}

/** Az üres sorokkal elválasztott (laza) lista-e: valamely két szomszédos elem között van üres sor. */
export function lazaLista(tv: readonly Blokk[]): boolean {
  for (let i = 1; i < tv.length; i++) if (tv[i].elsoSor > tv[i - 1].utolsoSor + 1) return true;
  return false;
}

/** A fejezet szövege (a `#`-ek és a záró `#`-ek nélkül); Setext-fejezetnél az első sor. */
export function fejezetSzoveg(sor: string): string {
  return sor
    .replace(/^[ \t]{0,3}#{1,6}[ \t]*/, '')
    .replace(/[ \t]+#+[ \t]*$/, '')
    .trim();
}
