// A @lezer/markdown belső mezői, amelyeket a beépített több soros blokkelemzők (FencedCode) is
// használnak, de a típusleírás nem publikus: a bemenet (előretekintéshez) és a tárolómélység (hogy a
// blokk ne nyúljon ki az idézetből vagy a listaelemből). A csomag verziója rögzített (package.json);
// ha egy frissítés átnevezné őket, az elemző-tesztek azonnal jeleznek.

import type { Input } from '@lezer/common';
import type { BlockContext, Line } from '@lezer/markdown';

export function bemenet(cx: BlockContext): Input {
  return (cx as unknown as { input: Input }).input;
}

/** Igaz, ha a sor még a jelenlegi blokk tárolóihoz tartozik (a FencedCode feltétele). */
export function tarolobanMarad(cx: BlockContext, line: Line): boolean {
  const melyseg = (line as unknown as { depth: number }).depth;
  const verem = (cx as unknown as { stack: unknown[] }).stack;
  return melyseg >= verem.length;
}

/** A `szoveg` első előfordulása a `tol` pozíciótól, darabokban olvasva (a teljes maradék beolvasása
 *  nagy jegyzetben, sok blokknál négyzetes lenne). -1, ha nincs. */
export function keres(input: Input, tol: number, szoveg: string, darab = 4096): number {
  let poz = tol;
  while (poz < input.length) {
    const veg = Math.min(input.length, poz + darab + szoveg.length - 1);
    const i = input.read(poz, veg).indexOf(szoveg);
    if (i >= 0) return poz + i;
    poz += darab;
  }
  return -1;
}
