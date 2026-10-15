// A Markdown-táblázat modellje a vizuális szerkesztőhöz (C09): a szintaxisfából beolvasott cellák, az
// igazítás, a sorok előtagja (behúzás, idézet-`> `, listajelölő), a tiszta műveletek (cella, sor, oszlop), és a
// kimenet: az oszlopszélességre igazított Markdown. Csak szerkesztéskor ír: a nem szerkesztett táblázat
// bájtra változatlan marad.
//
// A cella tartalma a nyers forrás (képlet, link, kiemelés jelölőstül). A `|` csak a képleten kívül lesz
// `\|` (a képlet felismerése az elemzőé: `matek.ts` `kepletVege`), így a `$|x|$` érintetlen marad. A
// fejléc nélküli táblázat nincs. Az első sor előtagja (`elotag`) és a többi soré (`folytatas`) külön áll:
// listajelölős táblázatnál (`- | a |`) csak az első sor viszi a jelölőt, a többi a jelölő szélességű
// behúzást; idézetnél a kettő azonos. A fejlécnél rövidebb sort a modell kipárnázza, a fejlécnél hosszabb
// sor extra cellái (a Markdown ezeket nem jeleníti meg) megmaradnak: a sor végére, nyersen íródnak vissza,
// hogy egy másik cella szerkesztése ne törölje őket.

import { type EditorState, Text } from '@codemirror/state';
import type { SyntaxNode } from '@lezer/common';
import { obsidianElemzo } from '../../markdown/elemzo';
import { kepletVege } from '../../markdown/matek';
import { sorCellai } from '../../markdown/tablazat';

export type Igazitas = '' | 'bal' | 'kozep' | 'jobb';

export interface Tabla {
  /** az első (fejléc) sor eleje a `|` előtt: behúzás, idézetjel vagy listajelölő */
  elotag: string;
  /** az elválasztó és a törzssorok eleje: idézetnél az `elotag`, listajelölőnél a jelölő szélességű behúzás */
  folytatas: string;
  /** a sorok cellái; a 0. sor a fejléc. A fejlécnél hosszabb sorban az `oszlopSzam` utáni cellák az extrák. */
  sorok: string[][];
  igazitas: Igazitas[];
}

export function oszlopSzam(t: Tabla): number {
  return t.igazitas.length;
}

// ---------------------------------------------------------------------- beolvasás

function igazitasok(delim: string): Igazitas[] {
  return delim
    .replace(/^[\s>]*\|?|\|?\s*$/g, '')
    .split('|')
    .map((x) => {
      const s = x.trim();
      return s.startsWith(':') && s.endsWith(':') ? 'kozep' : s.endsWith(':') ? 'jobb' : s.startsWith(':') ? 'bal' : '';
    });
}

/** A rövid sor `db` hosszúra párnázva; a hosszabb érintetlen (az extra cellák megmaradnak). */
function illeszt<T>(sor: T[], db: number, ures: T): T[] {
  return sor.length >= db ? sor : [...sor, ...Array.from({ length: db - sor.length }, () => ures)];
}

/** A `Table` csomópont modellje és a sorainak tartománya (teljes sorok). */
export function tablaNodebol(state: EditorState, n: SyntaxNode): { tabla: Tabla; from: number; to: number } | null {
  return tablaNodebolDoc(state.doc, n);
}

export function tablaNodebolDoc(doc: Text, n: SyntaxNode): { tabla: Tabla; from: number; to: number } | null {
  const olvas = (a: number, b: number) => doc.sliceString(a, b);
  const elso = doc.lineAt(n.from);
  const sorok: string[][] = [];
  let igaz: Igazitas[] = [];
  let folytatas: string | null = null;
  for (let c = n.firstChild; c; c = c.nextSibling) {
    if (c.name === 'TableDelimiter') {
      igaz = igazitasok(olvas(c.from, c.to));
      const sor = doc.lineAt(c.from);
      folytatas = sor.text.slice(0, c.from - sor.from);
    } else if (c.name === 'TableHeader' || c.name === 'TableRow') {
      const cellak = sorCellai(c).map((r) => olvas(r.from, r.to));
      sorok.push(cellak);
    }
  }
  if (!sorok.length) return null;
  const db = sorok[0].length || igaz.length || 1;
  const elotag = elso.text.slice(0, n.from - elso.from);
  return {
    tabla: {
      elotag,
      folytatas: folytatas ?? elotag,
      sorok: sorok.map((s) => illeszt(s, db, '')),
      igazitas: illeszt(igaz, db, '' as Igazitas).slice(0, db),
    },
    from: elso.from,
    to: doc.lineAt(n.to).to,
  };
}

/** A táblázat sorainak szövegéből (a widget ezt tárolja): a csomópont, a modell és az olvasó függvény. */
export function tablaForrasbol(forras: string): { tabla: Tabla; node: SyntaxNode; olvas: (a: number, b: number) => string } | null {
  let node: SyntaxNode | null = null;
  obsidianElemzo.parse(forras).iterate({
    enter(x) {
      if (x.name === 'Table' && !node) {
        node = x.node;
        return false;
      }
    },
  });
  if (!node) return null;
  const r = tablaNodebolDoc(Text.of(forras.split('\n')), node);
  return r ? { tabla: r.tabla, node, olvas: (a, b) => forras.slice(a, b) } : null;
}

// ---------------------------------------------------------------------- kimenet

function karakterSzelesseg(cp: number): number {
  if (cp === 0x200d || (cp >= 0xfe00 && cp <= 0xfe0f)) return 0;
  if (
    (cp >= 0x1100 && cp <= 0x115f) ||
    (cp >= 0x2e80 && cp <= 0xa4cf) ||
    (cp >= 0xac00 && cp <= 0xd7a3) ||
    (cp >= 0xf900 && cp <= 0xfaff) ||
    (cp >= 0xfe30 && cp <= 0xfe4f) ||
    (cp >= 0xff00 && cp <= 0xff60) ||
    (cp >= 0xffe0 && cp <= 0xffe6) ||
    (cp >= 0x1f300 && cp <= 0x1f64f) ||
    (cp >= 0x1f900 && cp <= 0x1f9ff) ||
    (cp >= 0x20000 && cp <= 0x3fffd)
  )
    return 2;
  return 1;
}

/** A szöveg megjelenítési szélessége a kipárnázáshoz (kombináló jel 0, szélesek 2). */
export function szelesseg(s: string): number {
  let w = 0;
  for (const c of s) w += /\p{M}/u.test(c) ? 0 : karakterSzelesseg(c.codePointAt(0)!);
  return w;
}

function parna(s: string, w: number, ig: Igazitas): string {
  const hiany = Math.max(0, w - szelesseg(s));
  if (ig === 'jobb') return ' '.repeat(hiany) + s;
  if (ig === 'kozep') {
    const bal = Math.floor(hiany / 2);
    return ' '.repeat(bal) + s + ' '.repeat(hiany - bal);
  }
  return s + ' '.repeat(hiany);
}

function elvalasztoCella(w: number, ig: Igazitas): string {
  switch (ig) {
    case 'bal':
      return ':' + '-'.repeat(w - 1);
    case 'jobb':
      return '-'.repeat(w - 1) + ':';
    case 'kozep':
      return ':' + '-'.repeat(w - 2) + ':';
    default:
      return '-'.repeat(w);
  }
}

/** A táblázat sorai az oszlopszélességre igazítva (fejléc, elválasztó, törzs). Az első sor az `elotag`-gal, a többi a
 *  `folytatas`-sal kezdődik; a fejlécen túli extra cellák igazítás nélkül, nyersen a sor végére kerülnek. */
export function szerializal(t: Tabla): string[] {
  const db = oszlopSzam(t);
  const szel = Array.from({ length: db }, (_, c) => Math.max(3, ...t.sorok.map((s) => szelesseg(s[c] ?? ''))));
  const sor = (elotag: string, cellak: string[]) =>
    `${elotag}| ${[...cellak.slice(0, db).map((x, c) => parna(x, szel[c], t.igazitas[c])), ...cellak.slice(db)].join(' | ')} |`;
  const elvalaszto = `${t.folytatas}| ${szel.map((w, c) => elvalasztoCella(w, t.igazitas[c])).join(' | ')} |`;
  return [sor(t.elotag, t.sorok[0]), elvalaszto, ...t.sorok.slice(1).map((s) => sor(t.folytatas, s))];
}

// ---------------------------------------------------------------------- cella

/** A cella nyers forrásának védése: a képleten kívüli `|` → `\|`, a sortörés → `<br>`. */
export function cellaForras(szoveg: string): string {
  const s = szoveg.replace(/\r?\n/g, '<br>').trim();
  let ki = '';
  let esc = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === '$' && !esc) {
      const k = kepletVege(s, i);
      if (k) {
        ki += s.slice(i, k.veg);
        i = k.veg - 1;
        continue;
      }
    }
    if (c === '|' && !esc) ki += '\\|';
    else ki += c;
    esc = !esc && c === '\\';
  }
  return ki;
}

// ---------------------------------------------------------------------- műveletek (tiszta)

const masol = (t: Tabla, sorok = t.sorok, igazitas = t.igazitas): Tabla => ({ elotag: t.elotag, folytatas: t.folytatas, sorok, igazitas });

export function cellaIr(t: Tabla, sor: number, oszlop: number, szoveg: string): Tabla {
  return masol(t, t.sorok.map((s, i) => (i === sor ? s.map((x, c) => (c === oszlop ? cellaForras(szoveg) : x)) : s)));
}

/** Új üres törzssor az `index` helyére (legalább 1: a fejléc előtt nincs sor). */
export function sorBeszur(t: Tabla, index: number): Tabla {
  const i = Math.max(1, Math.min(index, t.sorok.length));
  const uj = Array.from({ length: oszlopSzam(t) }, () => '');
  return masol(t, [...t.sorok.slice(0, i), uj, ...t.sorok.slice(i)]);
}

export function sorTorol(t: Tabla, index: number): Tabla {
  if (index < 1 || index >= t.sorok.length) return t;
  return masol(t, t.sorok.filter((_, i) => i !== index));
}

export function sorDuplikal(t: Tabla, index: number): Tabla {
  if (index < 1 || index >= t.sorok.length) return t;
  return masol(t, [...t.sorok.slice(0, index + 1), [...t.sorok[index]], ...t.sorok.slice(index + 1)]);
}

/** A törzssor áthelyezése: az `innen` sor a `ide` index elé kerül (az eltávolítás előtti számozással). */
export function sorMozgat(t: Tabla, innen: number, ide: number): Tabla {
  if (innen < 1 || innen >= t.sorok.length) return t;
  const cel = Math.max(1, Math.min(ide, t.sorok.length));
  if (cel === innen || cel === innen + 1) return t;
  const sor = t.sorok[innen];
  const maradt = t.sorok.filter((_, i) => i !== innen);
  maradt.splice(cel > innen ? cel - 1 : cel, 0, sor);
  return masol(t, maradt);
}

export function oszlopBeszur(t: Tabla, index: number): Tabla {
  const i = Math.max(0, Math.min(index, oszlopSzam(t)));
  const be = <T>(s: T[], x: T) => [...s.slice(0, i), x, ...s.slice(i)];
  return masol(
    t,
    t.sorok.map((s, r) => be(s, r === 0 ? `Oszlop ${oszlopSzam(t) + 1}` : '')),
    be(t.igazitas, '' as Igazitas),
  );
}

export function oszlopTorol(t: Tabla, index: number): Tabla {
  if (oszlopSzam(t) <= 1 || index < 0 || index >= oszlopSzam(t)) return t;
  const ki = <T>(s: T[]) => s.filter((_, c) => c !== index);
  return masol(t, t.sorok.map(ki), ki(t.igazitas));
}

export function oszlopDuplikal(t: Tabla, index: number): Tabla {
  if (index < 0 || index >= oszlopSzam(t)) return t;
  const dup = <T>(s: T[]) => [...s.slice(0, index + 1), s[index], ...s.slice(index + 1)];
  return masol(t, t.sorok.map(dup), dup(t.igazitas));
}

/** Az oszlop áthelyezése az `ide` index elé (az eltávolítás előtti számozással). */
export function oszlopMozgat(t: Tabla, innen: number, ide: number): Tabla {
  const db = oszlopSzam(t);
  if (innen < 0 || innen >= db) return t;
  const cel = Math.max(0, Math.min(ide, db));
  if (cel === innen || cel === innen + 1) return t;
  const mozgat = <T>(s: T[]) => {
    const x = s[innen];
    const maradt = s.filter((_, c) => c !== innen);
    maradt.splice(cel > innen ? cel - 1 : cel, 0, x);
    return maradt;
  };
  return masol(t, t.sorok.map(mozgat), mozgat(t.igazitas));
}

export function oszlopIgazit(t: Tabla, index: number, ig: Igazitas): Tabla {
  if (index < 0 || index >= oszlopSzam(t)) return t;
  return masol(t, t.sorok, t.igazitas.map((x, c) => (c === index ? ig : x)));
}

/** Új táblázat a `/` menühöz: `oszlop` oszlop, `sor` üres törzssor, „Oszlop N” fejléccel. */
export function ujTabla(oszlop = 3, sor = 2): Tabla {
  return {
    elotag: '',
    folytatas: '',
    sorok: [Array.from({ length: oszlop }, (_, c) => `Oszlop ${c + 1}`), ...Array.from({ length: sor }, () => Array.from({ length: oszlop }, () => ''))],
    igazitas: Array.from({ length: oszlop }, () => '' as Igazitas),
  };
}
