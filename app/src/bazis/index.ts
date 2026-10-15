// A Bases telepítése (C12): a `.base` fül nézete, a ```` ```base ```` blokk és a `![[x.base]]` beágyazás. Az `App.svelte`
// hívja egyszer a szerkesztő telepítése mellett.

import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import type { Kornyezet } from '../lib/kornyezet';
import { beagyazasRenderelok } from '../szerkeszto/beagyazas/regiszter';
import { kodRenderelok } from '../szerkeszto/renderelok/regiszter';
import BazisFul from './BazisFul.svelte';
import { bazisBeagyazasRenderelo, bazisKodRenderelo } from './beagyazas';

export function bazisTelepit(k: Kornyezet): () => void {
  const le = [
    nezetek.regisztral({
      id: 'bazis.base',
      illeszkedik: (f, info) => !!f.ut && (info ? info.tipus === 'base' : f.ut.toLowerCase().endsWith('.base')),
      komponens: BazisFul,
      prioritas: 10,
    }),
    kodRenderelok.regisztral(bazisKodRenderelo(k)),
    beagyazasRenderelok.regisztral(bazisBeagyazasRenderelo(k)),
  ];
  return () => le.forEach((f) => f());
}
