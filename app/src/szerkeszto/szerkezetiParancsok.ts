// Soronkénti Markdown-parancsok mindkét szerkesztőmódhoz. A kijelölések ugyanazt a sort csak egyszer
// módosítják; a kód, képlet, YAML, HTML és táblázat szövege nem változik. Egy művelet egy undo-lépés.

import { isolateHistory } from '@codemirror/commands';
import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import type { ChangeSpec, EditorState, Line } from '@codemirror/state';
import type { EditorView } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';

export type ListaTipus = 'lista' | 'szamozott' | 'feladat';

const VEDETT = new Set(['FencedCode', 'CodeBlock', 'MathBlock', 'Frontmatter', 'Table', 'HTMLBlock', 'CommentBlock', 'ObsidianCommentBlock', 'ObsidianComment', 'ProcessingInstructionBlock', 'LinkReference', 'HorizontalRule']);

interface SorAdat {
  sor: Line;
  /** behúzás és idézet-tárolók; a lista jelölője nélkül */
  elotag: string;
  lista: string;
  szokoz: string;
  feladat: string | null;
  torzs: string;
}

/** A sor eleji tárolók. A feladatállapot egy Unicode-karakter is lehet. */
function sorAdat(sor: Line): SorAdat {
  const m = /^([ \t]*(?:>[ \t]*)*)(?:([-*+]|\d{1,9}[.)])([ \t]+)(?:\[([^\n])\](?:[ \t]+|$))?)?(.*)$/u.exec(sor.text)!;
  return { sor, elotag: m[1], lista: m[2] ?? '', szokoz: m[3] ?? '', feladat: m[4] ?? null, torzs: m[5] };
}

function kijeloltSorok(state: EditorState): SorAdat[] {
  const szamok = new Set<number>();
  const uresKurzorSorok = new Set<number>();
  let utolsoSor = 1;
  for (const r of state.selection.ranges) {
    const elso = state.doc.lineAt(r.from).number;
    if (r.empty) uresKurzorSorok.add(elso);
    // A következő sor elejéig tartó kijelölés nem jelöli ki annak a tartalmát.
    const utolso = state.doc.lineAt(r.empty ? r.to : Math.max(r.from, r.to - 1)).number;
    utolsoSor = Math.max(utolsoSor, utolso);
    for (let n = elso; n <= utolso; n++) szamok.add(n);
  }
  const fa = ensureSyntaxTree(state, state.doc.line(utolsoSor).to, 100);
  if (!fa) return [];
  return [...szamok].sort((a, b) => a - b).map((n) => sorAdat(state.doc.line(n))).filter((a) => {
    // Többsoros kijelölésnél a bekezdéseket elválasztó üres sor megmarad. Üres soron álló kurzorral
    // viszont természetesen lehet új feladatot/fejezetet/listát kezdeni.
    if (!a.sor.text.trim() && !uresKurzorSorok.has(a.sor.number)) return false;
    // A teljes sor vizsgálata a kerítések és a `---` YAML-határok sorát is védi. Egy soron belüli
    // kód vagy képlet viszont közönséges bekezdésben is lehet: az nem akadálya a sor átalakításának.
    let vedett = false;
    fa.iterate({ from: a.sor.from, to: a.sor.to, enter(n) {
      if (VEDETT.has(n.name) && n.from <= a.sor.to && n.to >= a.sor.from) vedett = true;
      return !vedett;
    } });
    // Callout fejléce és önálló blokkazonosító adat, nem sima bekezdés.
    return !vedett && !/^(?:\[![^\]]+\]|\^[A-Za-z0-9-]+(?:[ \t]*$))/.test(a.torzs);
  });
}

function alkalmaz(view: EditorView, sorok: SorAdat[], atalakit: (a: SorAdat, i: number) => string, esemeny: string): boolean {
  if (view.state.readOnly || !sorok.length) return false;
  const valtozas: ChangeSpec[] = [];
  sorok.forEach((a, i) => {
    const uj = atalakit(a, i);
    if (uj === a.sor.text) return;
    // Csak a közös elő-/utótag közötti rész változik. A bekezdésben álló kurzor így ugyanahhoz a
    // betűhöz tartozik továbbra is; a visszafelé kijelölés és az összes másodlagos kurzor is megmarad.
    let elol = 0;
    while (elol < uj.length && elol < a.sor.length && uj[elol] === a.sor.text[elol]) elol++;
    let hatul = 0;
    while (hatul < uj.length - elol && hatul < a.sor.length - elol && uj[uj.length - 1 - hatul] === a.sor.text[a.sor.length - 1 - hatul]) hatul++;
    valtozas.push({ from: a.sor.from + elol, to: a.sor.to - hatul, insert: uj.slice(elol, uj.length - hatul) });
  });
  if (!valtozas.length) return false;
  view.dispatch({ changes: valtozas, userEvent: esemeny, annotations: isolateHistory.of('full'), scrollIntoView: true });
  return true;
}

/** ⌘↩: jelöletlen feladat → kész, minden más feladatállapot → jelöletlen; szöveg/lista → feladat. */
export function feladatValthato(state: EditorState): boolean {
  return !state.readOnly && kijeloltSorok(state).length > 0;
}

export function feladatValt(view: EditorView): boolean {
  return alkalmaz(view, kijeloltSorok(view.state), (a) => {
    const jel = a.lista || '-';
    const allapot = a.feladat === null ? ' ' : a.feladat === ' ' ? 'x' : ' ';
    return `${a.elotag}${jel}${a.szokoz || ' '}[${allapot}] ${a.torzs}`;
  }, 'input.feladat');
}

/** A fejezet a meglévő idézet/lista tárolójában marad; 0 = közönséges szöveg. */
export function fejezetBeallit(view: EditorView, szint: number): boolean {
  if (!Number.isInteger(szint) || szint < 0 || szint > 6) return false;
  const sorok = kijeloltSorok(view.state);
  // Setext-fejezetnél a szövegsor és az aláhúzás együtt változik ATX-jelöléssé. A kijelölt sorok közé
  // nem kell kézzel az aláhúzást is felvenni. Nem törlünk más szöveget vagy elválasztó vonalat.
  const state = view.state;
  const fa = ensureSyntaxTree(state, state.doc.length, 100) ?? syntaxTree(state);
  const alahuzasok = new Set<number>();
  for (const a of sorok) {
    for (let n: SyntaxNode | null = fa.resolveInner(a.sor.from + a.elotag.length, 1); n; n = n.parent) {
      if (n.name.startsWith('SetextHeading')) {
        const veg = state.doc.lineAt(n.to).number;
        if (veg > a.sor.number) alahuzasok.add(veg);
      }
    }
  }
  const celok = sorok.filter((a) => !alahuzasok.has(a.sor.number));
  if (!alahuzasok.size) return alkalmaz(view, celok, (a) => {
    const torzs = a.torzs.replace(/^#{1,6}(?:[ \t]+|$)/, '').replace(/[ \t]+#+[ \t]*$/, a.torzs.match(/^#{1,6}(?:[ \t]+|$)/) ? '' : '$&');
    return `${a.elotag}${a.lista ? a.lista + a.szokoz + (a.feladat === null ? '' : `[${a.feladat}] `) : ''}${szint ? '#'.repeat(szint) + ' ' : ''}${torzs}`;
  }, 'input.fejezet');
  // Setext-aláhúzás üres sor lesz: a környező bekezdések nem olvadnak össze.
  return alkalmaz(view, [...celok, ...[...alahuzasok].map((n) => sorAdat(state.doc.line(n)))].sort((a, b) => a.sor.number - b.sor.number), (a) => {
    if (alahuzasok.has(a.sor.number)) return a.elotag.trimEnd();
    const torzs = a.torzs.replace(/^#{1,6}(?:[ \t]+|$)/, '');
    return `${a.elotag}${a.lista ? a.lista + a.szokoz + (a.feladat === null ? '' : `[${a.feladat}] `) : ''}${szint ? '#'.repeat(szint) + ' ' : ''}${torzs}`;
  }, 'input.fejezet');
}

/** Az összes kijelölt soron egységesen kapcsolja a listatípust; a behúzás és idézet megmarad. */
export function listaValt(view: EditorView, tipus: ListaTipus): boolean {
  const sorok = kijeloltSorok(view.state);
  const azonos = (a: SorAdat) => tipus === 'feladat' ? a.feladat !== null : tipus === 'szamozott' ? /^\d/.test(a.lista) && a.feladat === null : !!a.lista && !/^\d/.test(a.lista) && a.feladat === null;
  const torol = sorok.length > 0 && sorok.every(azonos);
  // Egymástól különálló kijelölések és behúzási szintek külön sorszámozást kapnak.
  const szamok = new Map<string, number>();
  let elozo = 0;
  return alkalmaz(view, sorok, (a) => {
    if (a.sor.number !== elozo + 1) szamok.clear();
    elozo = a.sor.number;
    if (torol) return a.elotag + a.torzs;
    const n = (szamok.get(a.elotag) ?? 0) + 1;
    szamok.set(a.elotag, n);
    const jel = tipus === 'szamozott' ? `${n}. ` : tipus === 'feladat' ? `- [${a.feladat ?? ' '}] ` : '- ';
    return a.elotag + jel + a.torzs;
  }, 'input.lista');
}

/** Szöveg → felsorolás → feladat → szöveg. Vegyes kijelölés először felsorolássá válik. */
export function listaCiklus(view: EditorView): boolean {
  const sorok = kijeloltSorok(view.state);
  if (sorok.length && sorok.every((a) => a.feladat !== null)) return listaValt(view, 'feladat');
  return listaValt(view, sorok.length && sorok.every((a) => !!a.lista) ? 'feladat' : 'lista');
}

/** A legkülső idézetjelölő kapcsolása. A belső lista/idézet teljes tartalma érintetlen. */
export function idezetValt(view: EditorView): boolean {
  const sorok = kijeloltSorok(view.state);
  const torol = sorok.length > 0 && sorok.every((a) => /^[ \t]*>/.test(a.sor.text));
  return alkalmaz(view, sorok, (a) => torol ? a.sor.text.replace(/^([ \t]*)>[ \t]?/, '$1') : a.sor.text.replace(/^([ \t]*)/, '$1> '), 'input.idezet');
}
