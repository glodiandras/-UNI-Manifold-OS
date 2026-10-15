// Lábjegyzetek: hivatkozás `[^címke]` a szövegben, definíció `[^címke]: szöveg` a sor elején. A definíció
// összetett blokk (mint a listaelem): a négy szóközzel behúzott és az üres sorok hozzá tartoznak, a
// bekezdés lusta folytatása is.

import type { BlockContext, InlineContext, Line, LeafBlock, MarkdownConfig } from '@lezer/markdown';
import { cimkek } from './cimkek';

const DEFINICIO = /^\[\^([^\s[\]]+)\]:[ \t]?/;
const HIVATKOZAS = /^\[\^([^\s[\]]+)\]/;
const BEHUZAS = 4;

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
  ],
};
