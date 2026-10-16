// Obsidian %%…%% megjegyzések. Opaque csomópontok: a bennük álló link/képlet/címke/feladat nem renderelődik.
//
// Három alak:
// - `ObsidianCommentBlock`: a sor elején nyíló `%%`, amelynek záró `%%`-a után a sorban nincs más (blokkelemző);
// - `ObsidianComment` soron belül: `%%` nyit, a következő `%%` zár (a kód, képlet, HTML-tag és link-cél belsejét a
//   többi soron belüli elemző előbb elfogyasztja, ott a `%%` nem nyit);
// - a bekezdés (vagy feladat) közepén nyíló, ott le nem záró `%%` (F11 01-rendering-01): az Obsidianhoz hasonlóan a
//   KÖVETKEZŐ `%%`-ig tart, üres sorokon és blokkhatárokon át (a megjegyzés belseje opaque: a benne álló fejezet,
//   kerítés, lista nem blokk), lezáratlanul a dokumentum végéig. A szintaxisfában ez EGY bekezdés (Paragraph/Task),
//   amelynek `ObsidianComment` gyereke átnyúlik az üres sorokon — így az olvasóban nem marad üres `<p>`, a blokkmodell
//   pedig egy egységként mozgatja. Ami előbb nyit, az nyer: a megjegyzésen belüli kerítés vagy `$$` nem véd.
import { tags } from '@lezer/highlight';
import type { BlockContext, Element, InlineContext, LeafBlock, LeafBlockParser, Line, MarkdownConfig } from '@lezer/markdown';
import { aktualisSor, bemenet, keres, levelJelek, levelVege, sorTartalom, tarolobanMarad, vegen } from './belso';

function blokkKezdet(cx: BlockContext, line: Line): number {
  if (line.indent - line.baseIndent >= 4 || !line.text.slice(line.pos).startsWith('%%')) return -1;
  const input = bemenet(cx);
  const veg = keres(input, cx.lineStart + line.pos + 2, '%%');
  if (veg < 0) return -1;
  const sorVeg = keres(input, veg + 2, '\n');
  return input.read(veg + 2, sorVeg < 0 ? input.length : sorVeg).trim() ? -1 : veg + 2;
}

// A levélblokk soron belüli elemzése alatt (és csak akkor) a lezáratlan `%%` a szöveg végéig tartó megjegyzés; a
// címben vagy a táblázatcellában álló lezáratlan `%%` szöveg marad. Az elemzés szinkron, a jelző nem szivároghat.
let vegigNyit = false;
let nyitvaMaradt = false;

function soronBelul(cx: BlockContext, szoveg: string, kezd: number): { elemek: Element[]; nyitott: boolean } {
  const elozo: [boolean, boolean] = [vegigNyit, nyitvaMaradt];
  vegigNyit = true;
  nyitvaMaradt = false;
  try {
    const elemek = cx.parser.parseInline(szoveg, kezd);
    return { elemek, nyitott: nyitvaMaradt };
  } finally {
    [vegigNyit, nyitvaMaradt] = elozo;
  }
}

function hozzafuz(leaf: LeafBlock, line: Line): void {
  leaf.content += '\n' + sorTartalom(line);
  levelJelek(leaf).push(...line.markers);
}

/**
 * A levélblokk (bekezdés, feladat) soron belüli elemei a `%%` megjegyzéssel. Ha a tartalom lezáratlan `%%`-ra
 * végződik, a blokkot a záró `%%`-ig (üres sorokon és blokkhatárokon át) kiterjeszti — a `leaf.content` és a jelölők
 * ekkor bővülnek —, a záró sor után a bekezdés a szokásos szabállyal folytatódik. `null`, ha a tartalomban nincs `%%`
 * (a hívó a saját útján elemez). `eltolas`: a soron belüli rész kezdete a tartalmon belül (a feladat jelölője után).
 */
export function megjegyzesesLevel(cx: BlockContext, leaf: LeafBlock, eltolas = 0): Element[] | null {
  if (!leaf.content.includes('%%')) return null;
  const line = aktualisSor(cx);
  let { elemek, nyitott } = soronBelul(cx, leaf.content.slice(eltolas), leaf.start + eltolas);
  while (nyitott && !vegen(cx)) {
    // a megjegyzés belseje: a záró `%%`-ot tartalmazó sorig, a tárolótól függetlenül (mint a bekezdés lusta sora)
    let zarva = false;
    while (!zarva && !vegen(cx)) {
      hozzafuz(leaf, line);
      zarva = line.text.includes('%%');
      cx.nextLine();
    }
    // a záró sor utáni bekezdés-folytatás: üres sorig vagy blokkot nyitó sorig (lezáratlanul a végén vagyunk)
    while (zarva && !vegen(cx) && line.pos < line.text.length && !levelVege(cx, line, leaf)) {
      hozzafuz(leaf, line);
      cx.nextLine();
    }
    ({ elemek, nyitott } = soronBelul(cx, leaf.content.slice(eltolas), leaf.start + eltolas));
  }
  return elemek;
}

class MegjegyzesLevel implements LeafBlockParser {
  nextLine(): boolean {
    return false;
  }

  finish(cx: BlockContext, leaf: LeafBlock): boolean {
    const elemek = megjegyzesesLevel(cx, leaf);
    if (!elemek) return false;
    cx.addLeafElement(leaf, cx.elt('Paragraph', leaf.start, leaf.start + leaf.content.length, elemek));
    return true;
  }
}

export const Megjegyzes: MarkdownConfig = {
  defineNodes: [
    { name: 'ObsidianComment', style: tags.comment },
    { name: 'ObsidianCommentBlock', block: true, style: tags.comment },
  ],
  parseBlock: [{
    name: 'ObsidianCommentBlock',
    after: 'FencedCode',
    endLeaf: (cx, line) => blokkKezdet(cx, line) >= 0,
    parse(cx: BlockContext, line: Line) {
      const zaro = blokkKezdet(cx, line);
      if (zaro < 0) return false;
      const kezd = cx.lineStart + line.pos;
      let veg = cx.lineStart + line.text.length;
      for (;;) {
        veg = cx.lineStart + line.text.length;
        if (veg >= zaro) { cx.nextLine(); break; }
        if (!cx.nextLine() || !tarolobanMarad(cx, line)) break;
      }
      cx.addElement(cx.elt('ObsidianCommentBlock', kezd, veg));
      return true;
    },
  }, {
    // A bekezdés utolsóként kapja meg a lezárást: a link-referencia, a táblázat és a feladat (az utóbbi maga hívja a
    // `megjegyzesesLevel`-t) előbb dönt.
    name: 'ObsidianCommentParagraph',
    after: 'TaskList',
    leaf: () => new MegjegyzesLevel(),
  }],
  parseInline: [{
    name: 'ObsidianComment',
    before: 'Emphasis',
    parse(cx: InlineContext, next: number, pos: number) {
      if (next !== 37 || cx.char(pos + 1) !== 37) return -1;
      const z = cx.text.indexOf('%%', pos - cx.offset + 2);
      if (z < 0) {
        if (!vegigNyit) return -1;
        nyitvaMaradt = true;
        return cx.addElement(cx.elt('ObsidianComment', pos, cx.end));
      }
      const veg = cx.offset + z + 2;
      return cx.addElement(cx.elt('ObsidianComment', pos, veg));
    },
  }],
};
