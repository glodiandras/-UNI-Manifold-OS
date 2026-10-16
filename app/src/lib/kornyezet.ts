// A héj közös objektumai Svelte-kontextusként (a komponensek innen érik el, nem globálisból).


import { getContext, setContext } from 'svelte';
import type { CoreKapcsolat } from './core/ws.svelte';
import type { Felulet } from './elrendezes/felulet.svelte';
import type { VaultFajlok } from './vault/fajlok.svelte';

export interface Kornyezet {
  felulet: Felulet;
  fajlok: VaultFajlok;
  kapcsolat: CoreKapcsolat;
}

export const KORNYEZET_KULCS = Symbol('manifold-kornyezet');
const KULCS = KORNYEZET_KULCS;

export function kornyezetBeallit(k: Kornyezet): Kornyezet {
  return setContext(KULCS, k);
}

export function kornyezet(): Kornyezet {
  const k = getContext<Kornyezet | undefined>(KULCS);
  if (!k) throw new Error('hiányzó Manifold-környezet'); // i18n-ignore: programozói hiba
  return k;
}
