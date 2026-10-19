// U01: csak a törzs ELSŐ, felső szintű H1-je lehet a fájlcím vizuális megfelelője. A szöveg nem változik.
import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import type { EditorState } from '@codemirror/state';
import { fajlNev } from '../lib/vault/fajlok.svelte';

export interface OsszevontCim {
  from: number;
  to: number;
  /** A következő sor eleje, vagy a fájl vége, ha nincs záró sortörés. */
  utan: number;
  sor: number;
}

export function osszevontCim(state: EditorState, ut: string): OsszevontCim | null {
  const fa = ensureSyntaxTree(state, Math.min(state.doc.length, 20_000), 30) ?? syntaxTree(state);
  let n = fa.topNode.firstChild;
  if (n?.name === 'Frontmatter') n = n.nextSibling;
  if (!n || (n.name !== 'ATXHeading1' && n.name !== 'SetextHeading1')) return null;
  // Linket, képletet vagy jelentéssel bíró formázást nem tüntetünk el.
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name !== 'HeaderMark') return null;
  const elso = n.firstChild;
  const utolso = n.lastChild;
  const kezdet = n.name === 'ATXHeading1' && elso?.name === 'HeaderMark' ? elso.to : n.from;
  const veg = utolso?.name === 'HeaderMark' && (n.name === 'SetextHeading1' || utolso.from > kezdet) ? utolso.from : n.to;
  // Az ékezet és a kis/nagybetű jelentéssel bír; csak NFC és a címsor szélső szóközei normalizálódnak.
  const szoveg = state.doc.sliceString(kezdet, veg).trim().normalize('NFC');
  if (!szoveg || szoveg !== fajlNev(ut).normalize('NFC')) return null;
  const zaroSor = state.doc.lineAt(n.to);
  return { from: n.from, to: n.to, utan: zaroSor.number < state.doc.lines ? state.doc.line(zaroSor.number + 1).from : state.doc.length,
    sor: state.doc.lineAt(n.from).number };
}

export const cimTartalmaz = (cim: OsszevontCim | null, poz: number): boolean => !!cim && poz >= cim.from && poz <= cim.to;
