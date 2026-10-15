// A callout-ok összecsukott állapota a Live Preview-ban. A forrás `-` jele csukva, a `+` nyitva indít; a
// felhasználó átkapcsolása nézet-állapot (a fájlba nem íródik, ahogy az Obsidianban sem). A kulcs az
// idézet első sorának eleje, a változásokon át leképezve.

import { StateEffect, StateField } from '@codemirror/state';

export const calloutHajtasValt = StateEffect.define<{ pos: number; csukva: boolean }>({
  map: (v, m) => ({ pos: m.mapPos(v.pos), csukva: v.csukva }),
});

export const calloutHajtas = StateField.define<ReadonlyMap<number, boolean>>({
  create: () => new Map(),
  update(ertek, tr) {
    let m = ertek;
    if (tr.docChanged && ertek.size) {
      const uj = new Map<number, boolean>();
      for (const [p, c] of ertek) uj.set(tr.changes.mapPos(p, -1), c);
      m = uj;
    }
    for (const e of tr.effects)
      if (e.is(calloutHajtasValt)) {
        if (m === ertek) m = new Map(ertek);
        (m as Map<number, boolean>).set(e.value.pos, e.value.csukva);
      }
    return m;
  },
});
