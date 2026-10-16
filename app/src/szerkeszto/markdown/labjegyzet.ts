// Lábjegyzetek: hivatkozás `[^címke]` a szövegben, definíció `[^címke]: szöveg` a sor elején. A definíció
// összetett blokk (mint a listaelem): a négy szóközzel behúzott és az üres sorok hozzá tartoznak, a
// bekezdés lusta folytatása is. Soron belüli lábjegyzet (01-rendering-10): `^[szöveg]` — a törzse Markdown (kiemelés,
// link), egy bekezdésen belül; a záró `]` a kiegyensúlyozott szögletes zárójelek után áll (a belső `[link](…)`, `[[…]]`
// nem zárja le). Lezáratlan `^[` szöveg marad.

import type { BlockContext, DelimiterType, InlineContext, Line, LeafBlock, MarkdownConfig } from '@lezer/markdown';
import { cimkek } from './cimkek';

const DEFINICIO = /^\[\^([^\s[\]]+)\]:[ \t]?/;
const HIVATKOZAS = /^\[\^([^\s[\]]+)\]/;
const BEHUZAS = 4;
/** A soron belüli lábjegyzet nyitó jele (`^[`): saját határoló, nincs automatikus feloldása (lezáratlanul szöveg). */
const SORON_BELULI: DelimiterType = {};

/** A nyitó jel utáni szöveg zárójel-egyensúlya (a kódrészlet és a `\`-es jel nem számít). */
function zarojelEgyensuly(s: string): number {
  let n = 0;
  const tiszta = s.replace(/\\[\s\S]/g, '').replace(/(`+)[\s\S]*?\1/g, '');
  for (const c of tiszta) if (c === '[') n++;
  else if (c === ']') n--;
  return n;
}

function definicio(line: Line): RegExpExecArray | null {
  if (line.next !== 91 || line.indent - line.baseIndent >= 4) return null;
  return DEFINICIO.exec(line.text.slice(line.pos));
}

export const Labjegyzet: MarkdownConfig = {
  defineNodes: [
    {
      name: 'FootnoteDefinition',
      block: true,
      composite(_cx: BlockContext, line: Line, ertek: number) {
        if (line.indent < line.baseIndent + ertek && line.next > -1) return false;
        line.moveBaseColumn(line.baseIndent + ertek);
        return true;
      },
    },
    { name: 'FootnoteReference', style: { 'FootnoteReference/...': cimkek.labjegyzet } },
    { name: 'FootnoteLabel', style: cimkek.labjegyzet },
    { name: 'FootnoteMark', style: cimkek.labjegyzet },
    { name: 'FootnoteInline' },
  ],
  parseBlock: [
    {
      name: 'FootnoteDefinition',
      parse(cx: BlockContext, line: Line) {
        const m = definicio(line);
        if (!m) return false;
        const kezd = cx.lineStart + line.pos;
        const cimkeVeg = kezd + 2 + m[1].length;
        cx.startComposite('FootnoteDefinition', line.pos, BEHUZAS);
        cx.addElement(cx.elt('FootnoteMark', kezd, kezd + 2));
        cx.addElement(cx.elt('FootnoteLabel', kezd + 2, cimkeVeg));
        cx.addElement(cx.elt('FootnoteMark', cimkeVeg, cimkeVeg + 2));
        line.moveBase(line.pos + m[0].length);
        return null;
      },
      endLeaf: (_cx: BlockContext, line: Line, _leaf: LeafBlock) => definicio(line) !== null,
      before: 'LinkReference',
    },
  ],
  parseInline: [
    {
      name: 'FootnoteReference',
      parse(cx: InlineContext, next: number, pos: number) {
        if (next !== 91 || cx.char(pos + 1) !== 94) return -1;
        const m = HIVATKOZAS.exec(cx.slice(pos, Math.min(cx.end, pos + 256)));
        if (!m) return -1;
        const veg = pos + m[0].length;
        return cx.addElement(
          cx.elt('FootnoteReference', pos, veg, [
            cx.elt('FootnoteMark', pos, pos + 2),
            cx.elt('FootnoteLabel', pos + 2, veg - 1),
            cx.elt('FootnoteMark', veg - 1, veg),
          ]),
        );
      },
      before: 'Link',
    },
    {
      name: 'FootnoteInlineStart',
      parse(cx: InlineContext, next: number, pos: number) {
        if (next !== 94 || cx.char(pos + 1) !== 91) return -1;
        return cx.addDelimiter(SORON_BELULI, pos, pos + 2, true, false);
      },
      before: 'Link',
    },
    {
      name: 'FootnoteInlineEnd',
      parse(cx: InlineContext, next: number, pos: number) {
        if (next !== 93) return -1;
        const i = cx.findOpeningDelimiter(SORON_BELULI);
        if (i === null) return -1;
        const nyito = cx.getDelimiterAt(i)!;
        if (zarojelEgyensuly(cx.slice(nyito.to, pos)) !== 0) return -1;
        const tartalom = cx.takeContent(i);
        return cx.addElement(
          cx.elt('FootnoteInline', nyito.from, pos + 1, [cx.elt('FootnoteMark', nyito.from, nyito.to), ...tartalom, cx.elt('FootnoteMark', pos, pos + 1)]),
        );
      },
      before: 'LinkEnd',
    },
  ],
};
