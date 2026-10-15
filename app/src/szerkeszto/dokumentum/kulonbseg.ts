// A régi és az új szöveg legkisebb egyetlen cseréje (közös eleje és vége nélkül). A külső változás így
// egy csereként kerül a szerkesztőbe: a kurzor és a kijelölés a változáson túl a helyén marad.

import type { Text } from '@codemirror/state';

export interface Csere {
  from: number;
  to: number;
  insert: string;
}

export function csere(regi: Text | string, uj: string): Csere | null {
  const a = typeof regi === 'string' ? regi : regi.toString();
  if (a === uj) return null;
  const min = Math.min(a.length, uj.length);
  let eleje = 0;
  while (eleje < min && a.charCodeAt(eleje) === uj.charCodeAt(eleje)) eleje++;
  // ne vágjunk szét UTF-16 párt
  if (eleje > 0 && eleje < min && (a.charCodeAt(eleje) & 0xfc00) === 0xdc00) eleje--;
  let vege = 0;
  while (vege < min - eleje && a.charCodeAt(a.length - 1 - vege) === uj.charCodeAt(uj.length - 1 - vege)) vege++;
  if (vege > 0 && (a.charCodeAt(a.length - vege) & 0xfc00) === 0xdc00) vege--;
  return { from: eleje, to: a.length - vege, insert: uj.slice(eleje, uj.length - vege) };
}
