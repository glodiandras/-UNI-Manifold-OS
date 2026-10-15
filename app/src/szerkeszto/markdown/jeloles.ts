// `==kiemelés==` — az Obsidian szövegkiemelése. A határolók szabálya a GFM-áthúzásé (`~~`), ugyanazzal a
// szóköz- és írásjel-vizsgálattal, mint a @lezer/markdown Strikethrough bővítése.

import type { InlineContext, MarkdownConfig } from '@lezer/markdown';
import { cimkek } from './cimkek';

const EGYENLO = 61;
const IRASJEL = /[\p{S}\p{P}]/u;
const JelolesHatarolo = { resolve: 'Highlight', mark: 'HighlightMark' };

export const Jeloles: MarkdownConfig = {
  defineNodes: [
    { name: 'Highlight', style: { 'Highlight/...': cimkek.jeloles } },
    { name: 'HighlightMark', style: cimkek.jeloles },
  ],
  parseInline: [
    {
      name: 'Highlight',
      parse(cx: InlineContext, next: number, pos: number) {
        if (next !== EGYENLO || cx.char(pos + 1) !== EGYENLO || cx.char(pos + 2) === EGYENLO) return -1;
        const elotte = cx.slice(pos - 1, pos);
        const utana = cx.slice(pos + 2, pos + 3);
        const szElotte = /\s|^$/.test(elotte);
        const szUtana = /\s|^$/.test(utana);
        const iElotte = IRASJEL.test(elotte);
        const iUtana = IRASJEL.test(utana);
        return cx.addDelimiter(
          JelolesHatarolo,
          pos,
          pos + 2,
          !szUtana && (!iUtana || szElotte || iElotte),
          !szElotte && (!iElotte || szUtana || iUtana),
        );
      },
      after: 'Emphasis',
    },
  ],
};
