// Függő behúzás (01-rendering-13): a tördelt listaelem, feladat és idézet folytatósorai a szöveg alá kerülnek, nem a sor
// elejére. A látható előtag (behúzás, listajel, `[ ]`, Forrás módban a `> `) szélessége a kirajzolás után mérve jön (a Live
// Preview a jeleket widgetre cseréli vagy elrejti, ezért a karakterszám nem adná vissza a valódi szélességet); a sor
// `--fuggo-behuzas` értéket kap, a CSS ebből negatív `text-indent`-et és vele egyenlő bal belső margót ad. A mérés a
// látható sorokra korlátozott, és csak tényleges változáskor vált ki új díszítést (nincs mérési hurok).

import { syntaxTree } from '@codemirror/language';
import { type EditorState, type Range, StateEffect } from '@codemirror/state';
import { Decoration, type DecorationSet, type EditorView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';

/** Ahol a sor eleje nem próza-előtag: itt nincs függő behúzás. */
const KIZART = new Set(['FencedCode', 'CodeBlock', 'Frontmatter', 'MathBlock', 'Table', 'HTMLBlock', 'CommentBlock', 'ObsidianCommentBlock']);

/** A sor látható előtagjának vége (idézetjelek, behúzás, listajel, feladatjelölő és az utánuk álló szóközök), vagy `null`,
 *  ha a sornak nincs előtagja, üres a tartalma, vagy kódban / táblázatban / frontmatterben áll. */
export function elotagVege(state: EditorState, sorKezdet: number): number | null {
  const doc = state.doc;
  const sor = doc.lineAt(sorKezdet);
  const alap = /^(?:[ \t]*>)*[ \t]*/.exec(sor.text)![0].length;
  if (alap === sor.length) return null;
  const fa = syntaxTree(state);
  for (let p: SyntaxNode | null = fa.resolveInner(sor.from + alap, 1); p; p = p.parent) if (KIZART.has(p.name)) return null;
  let veg = sor.from + alap;
  const jel = fa.resolveInner(veg, 1);
  if (jel.name === 'ListMark' && jel.from === veg) {
    veg = jel.to;
    while (veg < sor.to && /[ \t]/.test(doc.sliceString(veg, veg + 1))) veg++;
    const feladat = fa.resolveInner(veg, 1);
    if (feladat.name === 'TaskMarker' && feladat.from === veg) {
      veg = feladat.to;
      while (veg < sor.to && /[ \t]/.test(doc.sliceString(veg, veg + 1))) veg++;
    }
  }
  return veg > sor.from && veg < sor.to ? veg : null;
}

const meresKesz = StateEffect.define<ReadonlyMap<number, number>>();

function diszitesek(view: EditorView, meretek: ReadonlyMap<number, number>): DecorationSet {
  const ki: Range<Decoration>[] = [];
  for (const { from, to } of view.visibleRanges)
    for (let p = from; p <= to; ) {
      const sor = view.state.doc.lineAt(p);
      const w = meretek.get(sor.from);
      if (w && w > 0) ki.push(Decoration.line({ class: 'cm-fuggo', attributes: { style: `--fuggo-behuzas: ${w}px` } }).range(sor.from));
      p = sor.to + 1;
    }
  return Decoration.set(ki, true);
}

/** A látható előtagok mért szélessége (px, egészre kerekítve); a mérhetetlen sor kimarad. */
export function elotagSzelessegek(view: EditorView): Map<number, number> {
  const ki = new Map<number, number>();
  for (const { from, to } of view.visibleRanges)
    for (let p = from; p <= to; ) {
      const sor = view.state.doc.lineAt(p);
      const veg = elotagVege(view.state, sor.from);
      if (veg !== null) {
        const a = view.coordsAtPos(sor.from, 1);
        const b = view.coordsAtPos(veg, 1);
        if (a && b && Math.abs(b.top - a.top) < Math.max(4, (a.bottom - a.top) / 2)) {
          const w = Math.round(b.left - a.left);
          if (w > 0) ki.set(sor.from, w);
        }
      }
      p = sor.to + 1;
    }
  return ki;
}

const egyezik = (a: ReadonlyMap<number, number>, b: ReadonlyMap<number, number>) =>
  a.size === b.size && [...a].every(([k, v]) => b.get(k) === v);

export const fuggoBehuzas = ViewPlugin.fromClass(
  class {
    meretek: ReadonlyMap<number, number> = new Map();
    decorations: DecorationSet;
    private varakozik = false;
    private halott = false;

    constructor(readonly view: EditorView) {
      this.decorations = Decoration.none;
      this.mer();
    }

    update(u: ViewUpdate) {
      let uj = false;
      if (u.docChanged && this.meretek.size) {
        const m = new Map<number, number>();
        for (const [k, v] of this.meretek) {
          const p = u.changes.mapPos(k, 1);
          if (u.state.doc.lineAt(p).from === p) m.set(p, v);
        }
        this.meretek = m;
        uj = true;
      }
      for (const tr of u.transactions)
        for (const e of tr.effects)
          if (e.is(meresKesz)) {
            this.meretek = e.value;
            uj = true;
          }
      if (uj || u.viewportChanged) this.decorations = diszitesek(u.view, this.meretek);
      if (u.docChanged || u.viewportChanged || u.geometryChanged || u.selectionSet || syntaxTree(u.startState) !== syntaxTree(u.state)) this.mer();
    }

    destroy() {
      this.halott = true;
    }

    mer() {
      if (this.varakozik) return;
      this.varakozik = true;
      this.view.requestMeasure({
        key: this,
        read: (v) => elotagSzelessegek(v),
        write: (m, v) => {
          this.varakozik = false;
          if (egyezik(m, this.meretek)) return;
          // a mérés írási fázisában nem indulhat tranzakció: a következő mikrolépésben
          queueMicrotask(() => {
            if (!this.halott && !egyezik(m, this.meretek)) v.dispatch({ effects: meresKesz.of(m) });
          });
        },
      });
    }
  },
  { decorations: (p) => p.decorations },
);
