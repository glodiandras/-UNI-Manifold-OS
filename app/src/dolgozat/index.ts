// A dolgozat-oldal telepítése (C28a): a nézet-regisztráció és a parancs. Az `App.svelte` hívja egyszer, a „Ma” mellett.

import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { GraduationCap } from '../lib/ikon/ikonok';
import type { Regiszter } from '../lib/parancsok/regiszter';
import Dolgozat from './Dolgozat.svelte';
import { dolgozatAdat } from './modell.svelte';

export function dolgozatTelepit(reg: Regiszter, felulet: Felulet, kapcsolat: CoreKapcsolat): () => void {
  const leNezet = nezetek.regisztral({
    id: 'dolgozat.nezet',
    illeszkedik: (f) => f.ut === null && f.nezet?.tipus === 'dolgozat',
    komponens: Dolgozat,
    prioritas: -50, // az „Új fül” (−100) fölött, mint a „Ma” és a gráf
  });
  const leParancsok = reg.regisztralMind([
    {
      id: 'dolgozat.megnyit',
      nev: 'Dolgozat-felkészültség',
      kategoria: 'Tanulás',
      ikon: GraduationCap,
      futtat: () => {
        felulet.atfedes = null;
        felulet.munkaterulet.megnyitNezet('dolgozat');
      },
    },
  ]);
  const leFigyel = dolgozatAdat.figyel(kapcsolat);
  return () => {
    leFigyel();
    leParancsok();
    leNezet();
  };
}
