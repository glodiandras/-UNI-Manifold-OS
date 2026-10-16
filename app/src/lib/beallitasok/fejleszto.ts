// Developer mód (F7): a technikai nézetek (nyers diagnosztika, mérések, build-jegyek, v2-import) kapcsolója. A mentett beállítás
// (`beallitasok.fejleszto.mod`, Settings › About › Advanced information) és az indító ⌥-kattintása (a core `fejleszto_kenyszer`-rel
// jelzi, erre a munkamenetre) ugyanazt az értéket adja: a core már az összevont értéket küldi. Normál módban a technikai nézet
// nem jelenik meg (a parancs sem a palettán, sem billentyűvel), és nincs fejlesztői szó a felületen (tests/ux-audit.test.ts).
import { beallitasok } from './allapot.svelte';

/** A Developer módhoz kötött parancsok azonosítói; a `fejleszto.*` és a `beallitasok.fejleszto-*` (Settings › Developer) előtagú mindig ide tartozik. */
export const FEJLESZTOI_PARANCSOK: ReadonlySet<string> = new Set([
  'szerkeszto.gepeles-meres',
  'szerkeszto.szintetikus-meres',
  'manifold.hasznalat',
]);

export function fejlesztoMod(): boolean {
  return beallitasok.ertek.fejleszto?.mod === true;
}

export function fejlesztoiParancs(id: string): boolean {
  return id.startsWith('fejleszto.') || id.startsWith('beallitasok.fejleszto-') || FEJLESZTOI_PARANCSOK.has(id);
}
