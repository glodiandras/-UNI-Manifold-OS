// Callout-felismerés: idézet, amelynek első sora `[!típus]±cím` (az Obsidian szabálya). Az elemzőben nincs
// külön csomópont (a forrás idézet marad); a Live Preview és az Olvasó ezzel a segéddel ismeri fel.

import type { SyntaxNode } from '@lezer/common';
import type { Olvaso } from './fa';

const CALLOUT = /^\[!([^\]\s]+)\]([+-]?)/;

export interface CalloutAdat {
  /** a típus, ahogy a forrásban áll */
  tipus: string;
  /** `''` nem összecsukható, `'+'` nyitva, `'-'` csukva indul */
  hajtas: '' | '+' | '-';
  /** a `[!típus]±` jel tartománya */
  jelFrom: number;
  jelTo: number;
  /** a cím szövege (szóközök nélkül); `cimFrom === cimTo`, ha nincs cím */
  cimFrom: number;
  cimTo: number;
  /** a fejléc sorának vége (a sortörés pozíciója, vagy az első bekezdés vége) */
  fejVeg: number;
  /** az első bekezdés (benne a fejléc) */
  bekezdes: SyntaxNode;
}

export function calloutAdat(idezet: SyntaxNode, olvas: Olvaso): CalloutAdat | null {
  let c = idezet.firstChild;
  while (c && c.name === 'QuoteMark') c = c.nextSibling;
  if (!c || c.name !== 'Paragraph') return null;
  const szoveg = olvas(c.from, c.to);
  const m = CALLOUT.exec(szoveg);
  if (!m) return null;
  const sor = szoveg.indexOf('\n');
  const fejVeg = sor >= 0 ? c.from + sor : c.to;
  const jelTo = c.from + m[0].length;
  const fej = olvas(jelTo, fejVeg);
  const eleje = fej.length - fej.trimStart().length;
  const cim = fej.trim();
  return {
    tipus: m[1],
    hajtas: m[2] as CalloutAdat['hajtas'],
    jelFrom: c.from,
    jelTo,
    cimFrom: jelTo + eleje,
    cimTo: jelTo + eleje + cim.length,
    fejVeg,
    bekezdes: c,
  };
}
