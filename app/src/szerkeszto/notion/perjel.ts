// A `/` menü (C09): a sor elején vagy szóköz után gépelt `/` megnyitja a beszúrás-menüt a kurzor alatt; a
// szűrő a `/` utáni gépelt szöveg (ékezetfüggetlen, elírástűrő). ↑↓ léptet, ↩ vagy ⇥ választ, esc zár; a
// fókusz végig a szerkesztőben marad, a menü a `aria-activedescendant`-tal követhető. A beszúrt sablonok
// és a környezetek leírása: `sablonok.ts` (tiszta, tesztelt); itt csak az állapot és a DOM-ragasz van.

import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import { type EditorState, type Extension, Prec, StateEffect, StateField } from '@codemirror/state';
import { EditorView, showTooltip, type Tooltip, type TooltipView, type ViewUpdate } from '@codemirror/view';
import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
import { FuzzyIndex } from '../../lib/kereses/fuzzy';
import { fokuszKer } from './fokusz';
import { Menu, type MenuElem } from './menu';
import { perjelBeszur, type PerjelKornyezet, perjelKornyezet, type SablonElem, sablonElemek } from './sablonok';

/** A `/` menü alkalmazás-szintű műveletei (C32b): az app telepítése köti be (a szerkesztő nem ismeri a felületet). */
export const perjelMuveletek: { sablonValaszto: (() => void) | null } = { sablonValaszto: null };

interface PerjelAllapot {
  /** a `/` helye */
  from: number;
  /** a szűrő vége (a kurzor) */
  veg: number;
  kornyezet: PerjelKornyezet;
  elemek: SablonElem[];
  index: FuzzyIndex<SablonElem>;
}

const perjelZar = StateEffect.define<null>();

/** Itt a `/` nem nyit menüt: kód, képlet, link, HTML, megjegyzés, frontmatter. */
const TILTOTT = new Set([
  'FencedCode',
  'CodeBlock',
  'InlineCode',
  'MathBlock',
  'InlineMath',
  'DisplayMath',
  'Frontmatter',
  'Link',
  'Image',
  'Autolink',
  'URL',
  'Wikilink',
  'Embed',
  'HTMLBlock',
  'HTMLTag',
  'CommentBlock',
  'Comment',
  'LinkReference',
  'Table',
]);

/** Nyithat-e menüt a most gépelt, `p` helyén álló `/`. */
export function perjelNyithato(state: EditorState, p: number): boolean {
  if (state.readOnly) return false;
  const sor = state.doc.lineAt(p);
  if (p > sor.from && !/\s/.test(state.sliceDoc(p - 1, p))) return false;
  const fa = ensureSyntaxTree(state, Math.min(state.doc.length, p + 1), 50) ?? syntaxTree(state);
  for (let n: ReturnType<typeof fa.resolveInner> | null = fa.resolveInner(p, 1); n; n = n.parent) if (TILTOTT.has(n.name)) return false;
  return true;
}

function ujAllapot(state: EditorState, p: number): PerjelAllapot {
  const kornyezet = perjelKornyezet(state, p, p + 1);
  const elemek = sablonElemek().filter((e) => e.kontextusok.includes(kornyezet.kontextus));
  return {
    from: p,
    veg: p + 1,
    kornyezet,
    elemek,
    index: new FuzzyIndex(elemek.map((e) => ({ ertek: e, nev: e.nev, ut: e.kulcsszavak }))),
  };
}

const perjelMezo = StateField.define<PerjelAllapot | null>({
  create: () => null,
  update(ertek, tr) {
    if (tr.effects.some((e) => e.is(perjelZar))) return null;
    if (ertek) {
      if (!tr.docChanged && !tr.selection) return ertek;
      const from = tr.changes.mapPos(ertek.from, -1);
      const veg = tr.changes.mapPos(ertek.veg, 1);
      const s = tr.state;
      const r = s.selection.main;
      if (!r.empty || r.head !== veg || veg <= from || s.sliceDoc(from, from + 1) !== '/') return null;
      if (s.doc.lineAt(from).number !== s.doc.lineAt(veg).number) return null;
      const szuro = s.sliceDoc(from + 1, veg);
      // szóköz után, találat nélkül a gépelés már nem a menüé
      if (/\s$/.test(szuro) && !ertek.index.keres(szuro.trim(), { limit: 1 }).length) return null;
      return from === ertek.from && veg === ertek.veg ? ertek : { ...ertek, from, veg };
    }
    if (!tr.docChanged || !tr.isUserEvent('input.type')) return null;
    let p = -1;
    let db = 0;
    tr.changes.iterChanges((fa, ta, fb, _tb, ins) => {
      db++;
      if (fa === ta && ins.length === 1 && ins.toString() === '/') p = fb;
    });
    if (db !== 1 || p < 0) return null;
    const s = tr.state;
    const r = s.selection.main;
    if (!r.empty || r.head !== p + 1 || !perjelNyithato(s, p)) return null;
    return ujAllapot(s, p);
  },
});

const menuk = new WeakMap<EditorView, Menu>();

/** A menü elemei a szűrőhöz: üresre csoportosítva, egyébként találati sorrendben, kiemeléssel. */
export function perjelLista(a: Pick<PerjelAllapot, 'elemek' | 'index'>, szuro: string): MenuElem[] {
  const q = szuro.trim();
  const mind = (e: SablonElem, kiemeles?: [number, number][]): MenuElem => ({
    id: e.id,
    nev: e.nev,
    ikon: e.ikon,
    jelzo: e.jelzo,
    csoport: q ? undefined : e.csoport,
    kiemeles,
  });
  if (!q) return a.elemek.map((e) => mind(e));
  return a.index.keres(q, { limit: 12 }).map((t) => mind(t.ertek, t.kiemeles));
}

function alkalmaz(view: EditorView, id: string): void {
  const a = view.state.field(perjelMezo, false);
  const e = a?.elemek.find((x) => x.id === id);
  if (!a || !e) return;
  const r = perjelBeszur(view.state, a.from, a.veg, e, new Date());
  if (!r) {
    view.dispatch({ effects: perjelZar.of(null) });
    return;
  }
  view.dispatch({
    changes: r.changes,
    selection: r.selection,
    effects: perjelZar.of(null),
    userEvent: 'input.perjel',
    scrollIntoView: true,
  });
  if (r.tabla !== undefined) fokuszKer(view, view.state.doc.line(r.tabla + 1).from, 0, 0);
  view.focus();
  if (e.muvelet === 'sablon-valaszto') perjelMuveletek.sablonValaszto?.();
}

function jelez(view: EditorView, id: string | null): void {
  if (id) view.contentDOM.setAttribute('aria-activedescendant', id);
  else view.contentDOM.removeAttribute('aria-activedescendant');
}

function letrehoz(view: EditorView): TooltipView {
  const menu = new Menu({
    cimke: 'Beszúrás',
    ures: 'Nincs találat',
    csoportok: true,
    onValaszt: (e) => alkalmaz(view, e.id),
    onAktiv: (id) => jelez(view, id),
  });
  menuk.set(view, menu);
  menu.elem.classList.add('nt-perjel');
  let utolso: string | null = null;
  const frissit = (state: EditorState) => {
    const a = state.field(perjelMezo, false);
    if (!a) return;
    const szuro = state.sliceDoc(a.from + 1, a.veg);
    if (szuro === utolso) return;
    utolso = szuro;
    menu.beallit(perjelLista(a, szuro));
    jelez(view, menu.aktivId);
  };
  frissit(view.state);
  const c = view.contentDOM;
  c.setAttribute('aria-haspopup', 'listbox');
  c.setAttribute('aria-expanded', 'true');
  c.setAttribute('aria-controls', `${menu.id}-lista`);
  return {
    dom: menu.elem,
    update: (u: ViewUpdate) => frissit(u.state),
    destroy() {
      menuk.delete(view);
      c.removeAttribute('aria-activedescendant');
      c.removeAttribute('aria-haspopup');
      c.removeAttribute('aria-expanded');
      c.removeAttribute('aria-controls');
    },
  };
}

const perjelTooltip = showTooltip.compute([perjelMezo], (state): Tooltip | null => {
  const a = state.field(perjelMezo);
  return a ? { pos: a.from, above: false, strictSide: false, arrow: false, create: letrehoz } : null;
});

const billentyuk = Prec.highest(
  EditorView.domEventHandlers({
    keydown(e, view) {
      const a = view.state.field(perjelMezo, false);
      if (!a || e.isComposing) return false;
      if (e.key === 'Escape') {
        view.dispatch({ effects: perjelZar.of(null) });
        e.preventDefault();
        return true;
      }
      const m = menuk.get(view);
      if (!m) return false;
      if ((e.key === 'Enter' || e.key === 'Tab') && m.meret === 0) {
        view.dispatch({ effects: perjelZar.of(null) });
        return false;
      }
      if (m.billentyu(e)) {
        e.preventDefault();
        return true;
      }
      return false;
    },
    blur(_e, view) {
      if (view.state.field(perjelMezo, false)) view.dispatch({ effects: perjelZar.of(null) });
      return false;
    },
  }),
);

/** A `/` menü a Live Preview-ban. */
export function perjelBovitmeny(): Extension {
  return [perjelMezo, perjelTooltip, billentyuk];
}

/** Nyitva van-e a menü (a tesztekhez és a parancsokhoz). */
export function perjelNyitva(state: EditorState): boolean {
  return !!state.field(perjelMezo, false);
}

/** A menü megnyitása a kurzornál (parancs): beír egy `/`-t, ha a környezet engedi; ahol a menü nem nyílhat (kód, link,
 *  szó közepe), nem ír semmit, csak szól (T169). */
export function perjelNyit(view: EditorView): boolean {
  const r = view.state.selection.main;
  if (view.state.readOnly || !r.empty) return false;
  const proba = view.state.update({ changes: { from: r.head, insert: '/' } }).state;
  if (!perjelNyithato(proba, r.head)) {
    ertesitesek.ertesit({ szint: 'info', cim: 'A beszúrás-menü itt nem nyílik meg', szoveg: 'Kódban, linkben, táblázatban vagy szó közepén a / szöveg marad.' });
    return false;
  }
  view.dispatch({ changes: { from: r.head, insert: '/' }, selection: { anchor: r.head + 1 }, userEvent: 'input.type' });
  return true;
}
