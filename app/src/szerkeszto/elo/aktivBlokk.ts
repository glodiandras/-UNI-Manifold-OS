// Az aktív egység: a Live Preview-ban a jelölés csak a kijelölés által érintett levélblokkban látszik
// (bekezdés, fejezet, kódblokk, képletblokk, táblázat, elválasztó, frontmatter, feladat …). A callout
// fejléce (az első sora) külön egység, a törzse a többi. Az egység mindig teljes sorokra nyúlik.
// A fókusz elvesztése nem változtat rajta, így a tartalom nem ugrik.

import { syntaxTree } from '@codemirror/language';
import { type EditorState, StateField } from '@codemirror/state';
import type { SyntaxNode } from '@lezer/common';
import { calloutAdat } from '../markdown/callout';

export interface Tartomany {
  from: number;
  to: number;
}

const LEVEL = new Set([
  'Paragraph',
  'ATXHeading1',
  'ATXHeading2',
  'ATXHeading3',
  'ATXHeading4',
  'ATXHeading5',
  'ATXHeading6',
  'SetextHeading1',
  'SetextHeading2',
  'FencedCode',
  'CodeBlock',
  'MathBlock',
  'Table',
  'HorizontalRule',
  'Frontmatter',
  'HTMLBlock',
  'LinkReference',
  'CommentBlock',
  'ProcessingInstructionBlock',
  'Task',
]);

export function levelBlokk(n: SyntaxNode | null): SyntaxNode | null {
  for (let c = n; c; c = c.parent) if (LEVEL.has(c.name)) return c;
  return null;
}

/** A pozíciót tartalmazó egység (teljes sorokra nyújtva). */
function egyseg(state: EditorState, pos: number): Tartomany {
  const fa = syntaxTree(state);
  const n = levelBlokk(fa.resolveInner(pos, 1)) ?? levelBlokk(fa.resolveInner(pos, -1));
  const doc = state.doc;
  if (!n) {
    const s = doc.lineAt(pos);
    return { from: s.from, to: s.to };
  }
  let from = n.from;
  let to = n.to;
  // a callout első bekezdése: a fejléc sora és a törzs két külön egység
  if (n.name === 'Paragraph' && n.parent?.name === 'Blockquote') {
    const a = calloutAdat(n.parent, (x, y) => doc.sliceString(x, y));
    if (a && a.bekezdes.from === n.from && a.fejVeg < n.to) {
      if (pos <= a.fejVeg) to = a.fejVeg;
      else from = a.fejVeg + 1;
    }
  }
  return { from: doc.lineAt(from).from, to: doc.lineAt(Math.min(to, doc.length)).to };
}

export function aktivEgysegek(state: EditorState): Tartomany[] {
  const ki: Tartomany[] = [];
  for (const r of state.selection.ranges) {
    if (r.empty) {
      ki.push(egyseg(state, r.head));
      continue;
    }
    // a kijelölés minden érintett egysége
    let pos = r.from;
    for (let lepes = 0; pos <= r.to && lepes < 10000; lepes++) {
      const e = egyseg(state, pos);
      ki.push(e);
      if (e.to >= r.to) break;
      pos = e.to + 1;
    }
  }
  ki.sort((a, b) => a.from - b.from);
  const osszevont: Tartomany[] = [];
  for (const t of ki) {
    const u = osszevont[osszevont.length - 1];
    if (u && t.from <= u.to + 1) u.to = Math.max(u.to, t.to);
    else osszevont.push({ ...t });
  }
  return osszevont;
}

function egyenlo(a: readonly Tartomany[], b: readonly Tartomany[]): boolean {
  return a.length === b.length && a.every((t, i) => t.from === b[i].from && t.to === b[i].to);
}

export const aktivBlokkok = StateField.define<readonly Tartomany[]>({
  create: (s) => aktivEgysegek(s),
  update(ertek, tr) {
    if (!tr.docChanged && !tr.selection && syntaxTree(tr.startState) === syntaxTree(tr.state)) return ertek;
    const uj = aktivEgysegek(tr.state);
    return egyenlo(uj, ertek) ? ertek : uj;
  },
});

/** Metszi-e a `[from, to]` tartomány valamelyik aktív egységet. */
export function aktiv(egysegek: readonly Tartomany[], from: number, to: number): boolean {
  for (const t of egysegek) {
    if (t.from > to) return false;
    if (t.to >= from) return true;
  }
  return false;
}
