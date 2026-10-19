// A megismételt első H1 csak LP-ben rejtett. Az atomikus tartomány mögött nincs láthatatlan szerkesztési hely.
import { EditorSelection, EditorState, StateField, type Extension } from '@codemirror/state';
import { Decoration, EditorView, type DecorationSet } from '@codemirror/view';
import { osszevontCim } from './cim';

export function cimElo(ut: string, fokusz: () => void): Extension {
  const diszites = (s: EditorState): DecorationSet => {
    const c = osszevontCim(s, ut);
    return c ? Decoration.set([Decoration.replace({ block: true }).range(c.from, c.utan)]) : Decoration.none;
  };
  const mezo = StateField.define<DecorationSet>({
    create: diszites,
    update: (regi, tr) => tr.docChanged || tr.reconfigured ? diszites(tr.state) : regi,
    provide: f => [EditorView.decorations.from(f), EditorView.atomicRanges.of(v => v.state.field(f))],
  });
  return [mezo,
    EditorState.transactionFilter.of(tr => {
      if (!tr.selection) return tr;
      const c = osszevontCim(tr.state, ut);
      if (!c || !tr.newSelection.ranges.some(r => r.empty && r.head >= c.from && r.head < c.utan)) return tr;
      const ranges = tr.newSelection.ranges.map(r => r.empty && r.head >= c.from && r.head < c.utan ? EditorSelection.cursor(c.utan) : r);
      return [tr, { selection: EditorSelection.create(ranges, tr.newSelection.mainIndex), sequential: true }];
    }),
    EditorView.domEventHandlers({ keydown(e, view) {
      if (e.isComposing || e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return false;
      const c = osszevontCim(view.state, ut);
      const s = view.state.selection.main;
      if (!c || !s.empty || s.head !== c.utan || (e.key !== 'Backspace' && e.key !== 'ArrowUp')) return false;
      e.preventDefault(); fokusz(); return true;
    } }),
    EditorView.inputHandler.of((view, from, to, text) => {
      const c = osszevontCim(view.state, ut);
      if (!c || !text || c.to !== c.utan || from !== c.to || to !== from || view.state.readOnly) return false;
      // Az első tényleges törzsgépelés hoz létre sort; a prezentáció önmagában nem ír.
      view.dispatch({ changes: { from, insert: '\n' + text }, selection: { anchor: from + 1 + text.length }, userEvent: 'input.type' });
      return true;
    }),
  ];
}
