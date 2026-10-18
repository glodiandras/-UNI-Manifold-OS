// A gráfnézet telepítése (C13): a nézet regisztrálása és a parancsai. Az `App.svelte` hívja egyszer.

import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { Network } from '../lib/ikon/ikonok';
import type { Regiszter } from '../lib/parancsok/regiszter';
import Graf from './Graf.svelte';
import { tk } from '../lib/i18n';

export function grafTelepit(reg: Regiszter, felulet: Felulet): () => void {
  const m = felulet.munkaterulet;
  const leNezet = nezetek.regisztral({
    id: 'graf.nezet',
    illeszkedik: (f) => f.ut === null && f.nezet?.tipus === 'graf',
    komponens: Graf,
    prioritas: -50, // az „Új fül” (−100) fölött: az üres fül nézete csak `ut === null` és nézet-állapot nélkül marad
  });
  const leParancsok = reg.regisztralMind([
    {
      id: 'graf.megnyit',
      nev: tk('Gráfnézet megnyitása'),
      kategoria: tk('Gráf'),
      ikon: Network,
      futtat: () => {
        felulet.atfedes = null;
        m.megnyitNezet('graf', { mod: 'globalis' });
      },
    },
    {
      id: 'graf.helyi',
      nev: tk('Helyi gráf a jegyzetből'),
      kategoria: tk('Gráf'),
      ikon: Network,
      elerheto: () => !!m.aktivFul?.ut,
      futtat: () => {
        const ut = m.aktivFul?.ut;
        if (!ut) return;
        felulet.atfedes = null;
        // a jegyzet mellett nyílik (osztott panel), és az aktív jegyzetet követi; a kapcsoló a nézet eszköztárában kikapcsolható
        m.megnyitNezet('graf', { mod: 'helyi', kozeppont: ut, melyseg: 1, kovet: true }, { oldalra: true });
      },
    },
  ]);
  return () => {
    leParancsok();
    leNezet();
  };
}
