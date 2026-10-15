// A gépelési késleltetés folyamatos mérése (C27 használati mérés): a billentyű eseményének idejétől addig, amíg a
// szerkesztő a leütés változását feldolgozta (a `docChanged` frissítés vége). Nem tartalmazza a kijelző
// frissítésére várást (60 Hz-en 0–16,7 ms), és nem kényszerít elrendezést, ezért a hatása elhanyagolható:
// leütésenként egy időbélyeg-különbség és egy vödör-növelés. A `szerkeszto/meres.ts` fejlesztői mérője ennél
// szigorúbb (layoutot is kényszerít), az a C08 kapu eszköze; a kettő nem összevethető.

import type { Extension } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { trackerKliens } from './kliens.svelte';

const ERVENYES_MS = 500; // a leütés és a változás közt ennél több idő: nem a leütés változása

function gepelesTaszto(e: KeyboardEvent): boolean {
  if (e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return false;
  return e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete' || e.key === 'Enter';
}

export function gepelesMero(): Extension {
  let leutes: number | null = null;
  return [
    EditorView.domEventHandlers({
      keydown: (e) => {
        leutes = gepelesTaszto(e) ? e.timeStamp : null;
        return false;
      },
    }),
    EditorView.updateListener.of((u) => {
      if (!u.docChanged || leutes === null) return;
      const ms = performance.now() - leutes;
      leutes = null;
      if (ms >= 0 && ms < ERVENYES_MS) trackerKliens.gepelesMs(ms);
    }),
  ];
}
