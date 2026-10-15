// Kért fókusz a táblázat-szerkesztőn (C09): a `/` menü beszúrása után az új táblázat első cellájára kell
// állni, de a widget csak a tranzakció után jön létre. A kérés a nézethez kötve vár, a widget az első
// felépítésekor beváltja.

import type { EditorView } from '@codemirror/view';

interface Kereses {
  /** a táblázat első sorának eleje a dokumentumban */
  from: number;
  sor: number;
  oszlop: number;
}

const kertek = new WeakMap<EditorView, Kereses>();

export function fokuszKer(view: EditorView, from: number, sor: number, oszlop: number): void {
  kertek.set(view, { from, sor, oszlop });
}

/** Ha az adott táblázatra volt kérés, visszaadja (és törli). */
export function fokuszBevalt(view: EditorView, from: number): { sor: number; oszlop: number } | null {
  const k = kertek.get(view);
  if (!k || k.from !== from) return null;
  kertek.delete(view);
  return { sor: k.sor, oszlop: k.oszlop };
}
