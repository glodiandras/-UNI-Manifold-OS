// Sorvégek és a bájthű visszaírás. A CodeMirror a sorvéget belül egy jelként tárolja; a fájl alakját a
// `lineSeparator` dönti el. A tisztán LF-es (a vault minden jegyzete, 2026-10-01) és a tisztán CRLF-es
// fájl bájtra visszaírható; a vegyes (vagy magányos CR-t tartalmazó) fájlt a szerkesztő csak olvasásra
// nyitja, mert egységes elválasztóval nem írható vissza változatlanul.

export type Sorveg = 'lf' | 'crlf' | 'vegyes';

export function sorvegElemez(s: string): Sorveg {
  if (!s.includes('\r')) return 'lf';
  let crlf = 0;
  let lf = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c === 13) {
      if (s.charCodeAt(i + 1) !== 10) return 'vegyes';
      crlf++;
      i++;
    } else if (c === 10) lf++;
  }
  return lf === 0 && crlf > 0 ? 'crlf' : 'vegyes';
}

/** A `lineSeparator` értéke (undefined: a CodeMirror alapja, `\n`). */
export function elvalaszto(s: Sorveg): string | undefined {
  return s === 'crlf' ? '\r\n' : undefined;
}
