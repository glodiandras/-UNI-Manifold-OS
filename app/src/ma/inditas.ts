import type { BeallitasokValasz } from '../lib/beallitasok/tipusok';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { napiJegyzetNyit } from './naplo';

/** Egy UI-élettartamban egyszer, a settings és az elrendezés sikeres betöltése után. A hibát a napi megnyitás láthatóan jelzi. */
export function napiIndito(felulet: Felulet, nyit: typeof napiJegyzetNyit = napiJegyzetNyit) {
  let eldontve = false;
  return (adat: BeallitasokValasz | null, elrendezesKesz: boolean, beallitasNyitva: boolean): void => {
    if (eldontve || !adat || !elrendezesKesz || adat.setup_szukseges || beallitasNyitva) return;
    eldontve = true;
    if (adat.ertek.fajlok.napi_inditaskor && adat.ertek.modulok.napi) void nyit(felulet);
  };
}
