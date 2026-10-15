// Képletek: `$…$` (soron belül), `$$…$$` (megjelenítési, soron belül is) és a sor eleji `$$` blokk.
//
// A szabály az index szabályát tükrözi (core/index/elemzo.py), hogy a darabszámok összevethetők legyenek:
//   _KEPLET_BLOKK = \$\$(.+?)\$\$                (a nyitó után legalább egy karakter, több soron át is)
//   _KEPLET_SOR   = \$(?<![\\$]\$)(?:(?=[^\s$])([^$\n]*?[^\s\\$])|([^\s$\\]))\$(?!\d)
// azaz a soron belüli képlet nyitó `$`-ja előtt nem áll `\` vagy `$`, utána nem áll szóköz; a tartalom
// egy sorban marad és nincs benne `$`; a záró `$` előtt nem áll szóköz vagy `\`, utána nem áll számjegy.
// Lezáró nélkül nincs képlet. A sor eleji `$$` blokk-elem (a bekezdést is megszakítja), a tartalma
// soronként `MathText`, a tárolójelek (`>`) nélkül.

import type { BlockContext, InlineContext, LeafBlock, Line, MarkdownConfig } from '@lezer/markdown';
import { bemenet, keres, tarolobanMarad } from './belso';
import { cimkek } from './cimkek';

const DOLLAR = 36;
const VISSZAPER = 92;

const ures = (c: number) => c >= 0 && /\s/.test(String.fromCharCode(c));
const szamjegy = (c: number) => c >= 0 && /\p{Nd}/u.test(String.fromCharCode(c));

function dollarralKezdodik(line: Line): boolean {
  return line.next === DOLLAR && line.text.charCodeAt(line.pos + 1) === DOLLAR;
}

/** A sor eleji `$$` egysoros blokkja: a záró `$$` pozíciója a sorban, vagy -1 (nincs záró a sorban),
 *  vagy -2 (van záró, de utána szöveg áll: az soron belüli képlet egy bekezdésben). */
function egysorosZaro(line: Line): number {
  const z = line.text.indexOf('$$', line.pos + 3);
  if (z < 0) return -1;
  return line.text.slice(z + 2).trim() ? -2 : z;
}

/** Páratlan számú `$$` áll-e a bekezdés eddigi szövegében (azaz egy soron belüli `$$` még nyitva van). */
function nyitottDupla(szoveg: string): boolean {
  let n = 0;
  for (let i = szoveg.indexOf('$$'); i >= 0; i = szoveg.indexOf('$$', i + 2)) n++;
  return n % 2 === 1;
}

function blokkKezdheto(cx: BlockContext, line: Line): boolean {
  if (!dollarralKezdodik(line)) return false;
  const z = egysorosZaro(line);
  if (z >= 0) return true;
  if (z === -2) return false;
  return keres(bemenet(cx), cx.lineStart + line.text.length, '$$') >= 0;
}

function blokk(cx: BlockContext, line: Line): boolean {
  if (!blokkKezdheto(cx, line)) return false;
  const nyit = cx.lineStart + line.pos;
  const elemek = [cx.elt('MathMark', nyit, nyit + 2)];
  const z = egysorosZaro(line);
  if (z >= 0) {
    const zaro = cx.lineStart + z;
    if (zaro > nyit + 2) elemek.push(cx.elt('MathText', nyit + 2, zaro));
    elemek.push(cx.elt('MathMark', zaro, zaro + 2));
    cx.addElement(cx.elt('MathBlock', nyit, cx.lineStart + line.text.length, elemek));
    cx.nextLine();
    return true;
  }
  let veg = cx.lineStart + line.text.length;
  if (veg > nyit + 2) elemek.push(cx.elt('MathText', nyit + 2, veg));
  while (cx.nextLine() && tarolobanMarad(cx, line)) {
    for (const m of line.markers) elemek.push(m);
    const kezd = line.basePos;
    const i = line.text.indexOf('$$', kezd);
    veg = cx.lineStart + line.text.length;
    if (i >= 0) {
      if (i > kezd) elemek.push(cx.elt('MathText', cx.lineStart + kezd, cx.lineStart + i));
      elemek.push(cx.elt('MathMark', cx.lineStart + i, cx.lineStart + i + 2));
      cx.nextLine();
      break;
    }
    if (line.text.length > kezd) elemek.push(cx.elt('MathText', cx.lineStart + kezd, veg));
  }
  cx.addElement(cx.elt('MathBlock', nyit, veg, elemek));
  return true;
}

/** A `szoveg` `i`. karakterén (`$`) kezdődő soron belüli képlet vége (kizárólagos), vagy -1. A `$$…$$`
 *  megjelenítési képlet lezárója a szöveg bármely későbbi pontján állhat (a bekezdésben több soron át is);
 *  a `$…$` egy sorban marad. Ugyanezt használja a táblázat sorbontása, hogy a képletben álló `|` ne vágja
 *  szét a cellát. */
export function kepletVege(szoveg: string, i: number): { veg: number; display: boolean } | null {
  if (szoveg.charCodeAt(i) !== DOLLAR) return null;
  if (szoveg.charCodeAt(i + 1) === DOLLAR) {
    const z = szoveg.indexOf('$$', i + 3);
    return z < 0 ? null : { veg: z + 2, display: true };
  }
  if (i > 0) {
    const elozo = szoveg.charCodeAt(i - 1);
    if (elozo === VISSZAPER || elozo === DOLLAR) return null;
  }
  const elso = i + 1 < szoveg.length ? szoveg.charCodeAt(i + 1) : -1;
  if (elso < 0 || ures(elso)) return null;
  for (let j = i + 1; j < szoveg.length; j++) {
    const c = szoveg.charCodeAt(j);
    if (c === 10) return null;
    if (c !== DOLLAR) continue;
    const utolso = szoveg.charCodeAt(j - 1);
    const utana = j + 1 < szoveg.length ? szoveg.charCodeAt(j + 1) : -1;
    if (ures(utolso) || utolso === VISSZAPER || szamjegy(utana)) return null;
    return { veg: j + 1, display: false };
  }
  return null;
}

function sorban(cx: InlineContext, next: number, pos: number): number {
  if (next !== DOLLAR) return -1;
  const k = kepletVege(cx.text, pos - cx.offset);
  if (!k) return -1;
  const veg = cx.offset + k.veg;
  const jel = k.display ? 2 : 1;
  return cx.addElement(
    cx.elt(k.display ? 'DisplayMath' : 'InlineMath', pos, veg, [
      cx.elt('MathMark', pos, pos + jel),
      cx.elt('MathMark', veg - jel, veg),
    ]),
  );
}

export const Matek: MarkdownConfig = {
  defineNodes: [
    { name: 'InlineMath', style: { 'InlineMath/...': cimkek.keplet } },
    { name: 'DisplayMath', style: { 'DisplayMath/...': cimkek.keplet } },
    { name: 'MathBlock', block: true },
    { name: 'MathText', style: cimkek.keplet },
    { name: 'MathMark', style: cimkek.kepletJel },
  ],
  parseBlock: [
    {
      name: 'MathBlock',
      parse: blokk,
      endLeaf: (cx: BlockContext, line: Line, leaf: LeafBlock) => !nyitottDupla(leaf.content) && blokkKezdheto(cx, line),
      after: 'FencedCode',
    },
  ],
  parseInline: [{ name: 'Math', parse: sorban, before: 'Emphasis' }],
};
