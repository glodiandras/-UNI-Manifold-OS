// A szövegtörzs címkéjének szintaxis-alapú célzása. A keresés a közös navigációs szolgáltatásé.
import { syntaxTree } from '@codemirror/language';
import type { EditorState } from '@codemirror/state';
import type { SyntaxNode } from '@lezer/common';
import { cimkeAdat } from '../markdown/cimke';

/** Linkfeliratban nem készülhet második interaktív hivatkozás. */
export function cimkeLinkben(n: SyntaxNode): boolean {
  for (let p = n.parent; p; p = p.parent)
    if (['Link', 'Autolink', 'Wikilink', 'Embed', 'Image', 'URL'].includes(p.name)) return true;
  return false;
}

export function cimkeAt(state: EditorState, pos: number): { cimke: string; from: number; to: number } | null {
  const fa = syntaxTree(state);
  for (const oldal of [1, -1] as const) {
    for (let n: SyntaxNode | null = fa.resolveInner(pos, oldal); n; n = n.parent) {
      if (n.name !== 'Hashtag') continue;
      if (cimkeLinkben(n)) return null;
      const cimke = cimkeAdat(n, (a, b) => state.doc.sliceString(a, b));
      return cimke ? { cimke, from: n.from, to: n.to } : null;
    }
  }
  return null;
}
