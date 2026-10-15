// Feladatlista: a GFM `[ ]`/`[x]` jelölője helyett bármely egykarakteres állapot (`[/]`, `[-]`, `[>]` …),
// ahogy az index (`_FELADAT`) és a Tasks-bővítmény olvassa. A csomópontok neve a GFM-é (`Task`,
// `TaskMarker`), így a CodeMirror lista-folytatása is felismeri őket. A `[ ]` jelöletlen, minden más jelölt.

import type { BlockContext, LeafBlock, LeafBlockParser, MarkdownConfig } from '@lezer/markdown';
import { tags as t } from '@lezer/highlight';

const JELOLO = /^\[[^\n]\][ \t]/u;

class FeladatElemzo implements LeafBlockParser {
  nextLine() {
    return false;
  }

  finish(cx: BlockContext, leaf: LeafBlock) {
    const hossz = (leaf.content.codePointAt(1) ?? 0) > 0xffff ? 4 : 3;
    cx.addLeafElement(
      leaf,
      cx.elt('Task', leaf.start, leaf.start + leaf.content.length, [
        cx.elt('TaskMarker', leaf.start, leaf.start + hossz),
        ...cx.parser.parseInline(leaf.content.slice(hossz), leaf.start + hossz),
      ]),
    );
    return true;
  }
}

/** A jelölő állapota: `' '` jelöletlen, minden más jelölt. */
export function feladatAllapot(jelolo: string): string {
  return [...jelolo.slice(1, -1)][0] ?? ' ';
}

export const Feladat: MarkdownConfig = {
  defineNodes: [
    { name: 'Task', block: true, style: t.list },
    { name: 'TaskMarker', style: t.atom },
  ],
  parseBlock: [
    {
      name: 'TaskList',
      leaf: (cx: BlockContext, leaf: LeafBlock) =>
        JELOLO.test(leaf.content) && cx.parentType().name === 'ListItem' ? new FeladatElemzo() : null,
      after: 'SetextHeading',
    },
  ],
};
