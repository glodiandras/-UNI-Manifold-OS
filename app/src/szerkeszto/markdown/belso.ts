// A @lezer/markdown belső mezői, amelyeket a beépített több soros blokkelemzők (FencedCode) is
// használnak, de a típusleírás nem publikus: a bemenet (előretekintéshez) és a tárolómélység (hogy a
// blokk ne nyúljon ki az idézetből vagy a listaelemből). A csomag verziója rögzített (package.json);
// ha egy frissítés átnevezné őket, az elemző-tesztek azonnal jeleznek.

import type { Input } from '@lezer/common';
import type { BlockContext, Element, LeafBlock, Line } from '@lezer/markdown';

export function bemenet(cx: BlockContext): Input {
  return (cx as unknown as { input: Input }).input;
}

/** Az elemző aktuális sora (a levélblokk-elemző `finish`-e nem kapja meg paraméterként). */
export function aktualisSor(cx: BlockContext): Line {
  return (cx as unknown as { line: Line }).line;
}

/** A sor szövege a tárolójelölők (`>`, listabehúzás) helyén szóközzel — a bekezdés tartalma így épül (a pozíciók a
 *  dokumentumbeliekkel egyeznek). */
export function sorTartalom(line: Line): string {
  return (line as unknown as { scrub(): string }).scrub();
}

/** Igaz, ha az elemző a bemenet végére ért (a `nextLine` hamisat adott). */
export function vegen(cx: BlockContext): boolean {
  return (cx as unknown as { atEnd: boolean }).atEnd;
}

/** A levélblokk soraiból gyűjtött tárolójelölők (`>` …): az `addLeafElement` ezeket fűzi a gyerekek közé. */
export function levelJelek(leaf: LeafBlock): Element[] {
  return (leaf as unknown as { marks: Element[] }).marks;
}

/** Igaz, ha a sor (a beépített levélciklus szabálya szerint) lezárja a bekezdést: kód, idézet, lista, fejezet … */
export function levelVege(cx: BlockContext, line: Line, leaf: LeafBlock): boolean {
  if (line.indent >= line.baseIndent + 4) return false;
  const vegek = (cx.parser as unknown as { endLeafBlock: ((cx: BlockContext, line: Line, leaf: LeafBlock) => boolean)[] }).endLeafBlock;
  return vegek.some((v) => v(cx, line, leaf));
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
