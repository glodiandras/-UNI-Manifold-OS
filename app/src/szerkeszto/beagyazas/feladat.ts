// A beágyazott szelet csak akkor szerkeszthető, ha a cél élő dokumentumában pontosan ugyanott, változatlanul áll.
// A core adja a kezdő sort; a módosítás a közös Dokumentumon megy át (a panelek és a mentés CAS-védelme megmarad).
import { ChangeSet } from '@codemirror/state';
import type { Dokumentum } from '../dokumentum/dokumentum.svelte';

export function beagyazottFeladatValt(d: Dokumentum, kezd: number, szelet: string, pos: number): string | null {
  if (d.csakOlvashato || d.allapot === 'utkozes' || d.allapot === 'eltunt' ||
    !Number.isSafeInteger(kezd) || kezd < 1 || kezd > d.szoveg.lines ||
    !Number.isSafeInteger(pos) || pos < 0 || !/^\[[^\r\n]\]$/u.test(szelet.slice(pos, pos + 3))) return null;
  const eleje = d.szoveg.line(kezd).from;
  if (d.szoveg.sliceString(eleje, eleje + szelet.length) !== szelet) return null;
  const ujJel = szelet[pos + 1] === ' ' ? 'x' : ' ';
  const valtozas = ChangeSet.of({ from: eleje + pos + 1, to: eleje + pos + 2, insert: ujJel }, d.szoveg.length);
  d.valtozott(valtozas, valtozas.apply(d.szoveg), null, true);
  return szelet.slice(0, pos + 1) + ujJel + szelet.slice(pos + 2);
}
