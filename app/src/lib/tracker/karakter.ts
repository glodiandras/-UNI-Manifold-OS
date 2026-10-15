// A szerkesztett karakterek számolása (C27): egy CodeMirror-tranzakció beszúrt és törölt karakterei. Csak a számot
// adja; a szöveg nem kerül sehova.

import type { ChangeSet } from '@codemirror/state';

export function valtozasMeret(valtozasok: ChangeSet): { beszurt: number; torolt: number } {
  let beszurt = 0;
  let torolt = 0;
  valtozasok.iterChanges((fromA, toA, fromB, toB) => {
    torolt += toA - fromA;
    beszurt += toB - fromB;
  });
  return { beszurt, torolt };
}
