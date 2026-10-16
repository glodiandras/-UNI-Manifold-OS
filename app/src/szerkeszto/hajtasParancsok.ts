// Az összecsukás parancsai (05-editing-03) a ⌘P palettában; alapból akkord nélkül (az Obsidian sem ad alapértelmezett
// billentyűt), a Beállítások → Gyorsbillentyűk lapon kioszthatók. A „váltás” a kurzor sorát kéri (Olvasóban nincs kurzor);
// a „mind” / „több” / „kevesebb” az Olvasóban is fut (a rejtett szerkesztő állapotát írja, az Olvasó követi).

import type { EditorView } from '@codemirror/view';
import { tk } from '../lib/i18n';
import { ChevronsDownUp } from '../lib/ikon/ikonok';
import type { Parancs } from '../lib/parancsok/regiszter';
import { hajtasKevesebb, hajtasTobb, hajtasValt, mindetHajt, mindetKibont } from './hajtogatas';
import type { SzerkesztoPeldany } from './szerkesztok.svelte';

export function hajtasParancsok(sz: () => SzerkesztoPeldany | null): Parancs[] {
  const parancs = (id: string, nev: string, fut: (v: EditorView) => unknown, kurzorral = false, tobb: Partial<Parancs> = {}): Parancs => ({
    id: `szerkeszto.${id}`,
    nev,
    kategoria: tk('Szerkesztő'),
    elerheto: () => !!sz()?.nezet() && (!kurzorral || sz()!.mod() !== 'olvaso'),
    futtat: () => {
      const p = sz();
      const v = p?.nezet();
      if (!v) return;
      fut(v);
      if (kurzorral) v.focus();
    },
    ...tobb,
  });
  return [
    parancs('hajtas-valt', tk('Összecsukás váltása a kurzor soránál'), hajtasValt, true, { ikon: ChevronsDownUp }),
    parancs('hajt-mind', tk('Minden címsor és lista összecsukása'), mindetHajt),
    parancs('kibont-mind', tk('Minden címsor és lista kibontása'), mindetKibont),
    parancs('hajt-tobb', tk('Több összecsukása'), hajtasTobb),
    parancs('hajt-kevesebb', tk('Kevesebb összecsukása'), hajtasKevesebb),
  ];
}
