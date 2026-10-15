// A frontmatter-blokk a nyitott dokumentumban (L39): `---` a legelső sorban, a záró `---`-ig, az `FM_RE` szerint
// (`\A\ufeff?---\r?\n(.*?)(?:(?<=\n)|\r?\n)---\r?\n?`: az üres blokk és az elején álló BOM is frontmatter, C29.8 T130)
// — a core ugyanezzel az illesztéssel olvassa. A CodeMirror-szöveg sorvége `\n`
// (a CRLF a mentéskor áll vissza), a core a blokk sorvégét a bemenetből veszi, ezért a csere sorvég-hű.

import type { Text } from '@codemirror/state';
import type { Csere } from '../dokumentum/kulonbseg';

export interface FmBlokk {
  tol: 0;
  ig: number;
  szoveg: string;
}

// a `---` alternatíva az ÜRES blokk (a záró sor közvetlenül a nyitó után), a másik a tartalmas; az üres elsőbbséget kap, mint a core-ban
const FM = /^\ufeff?---\r?\n(?:---|[\s\S]*?\r?\n---)\r?\n?/;
const ELSO_SZELET = 20_000;

/** A frontmatter-blokk, vagy `null`, ha nincs. Gépelés közben hívják: az első szeletet olvassa, csak ha az
 *  nem elég (nagy frontmatter), akkor a teljes szöveget. */
export function fmBlokk(szoveg: Text | string): FmBlokk | null {
  const hossz = typeof szoveg === 'string' ? szoveg.length : szoveg.length;
  const szelet = (n: number) => (typeof szoveg === 'string' ? szoveg.slice(0, n) : szoveg.sliceString(0, n));
  const kezd = szelet(4);
  if (!kezd.replace(/^\ufeff/, '').startsWith('---')) return null;
  let s = szelet(Math.min(hossz, ELSO_SZELET));
  let m = FM.exec(s);
  if (!m && hossz > ELSO_SZELET) {
    s = szelet(hossz);
    m = FM.exec(s);
  }
  return m ? { tol: 0, ig: m[0].length, szoveg: m[0] } : null;
}

/** A blokk cseréje az újra, a legkisebb egyetlen cserével (a változatlan sorok érintetlenek maradnak; a
 *  nyitott dokumentum kurzora a blokkon túl a helyén marad). Új blokk (nincs régi): a dokumentum elejére. */
export function blokkCsere(regi: FmBlokk | null, uj: string): Csere | null {
  const a = regi?.szoveg ?? '';
  if (a === uj) return null;
  const min = Math.min(a.length, uj.length);
  let eleje = 0;
  while (eleje < min && a.charCodeAt(eleje) === uj.charCodeAt(eleje)) eleje++;
  if (eleje > 0 && eleje < min && (a.charCodeAt(eleje) & 0xfc00) === 0xdc00) eleje--;
  let vege = 0;
  while (vege < min - eleje && a.charCodeAt(a.length - 1 - vege) === uj.charCodeAt(uj.length - 1 - vege)) vege++;
  if (vege > 0 && (a.charCodeAt(a.length - vege) & 0xfc00) === 0xdc00) vege--;
  return { from: eleje, to: a.length - vege, insert: uj.slice(eleje, uj.length - vege) };
}
