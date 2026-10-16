// Obsidian %%…%% megjegyzések. Opaque csomópontok: a bennük álló link/képlet nem renderelődik.
import { tags } from '@lezer/highlight';
import type { BlockContext, InlineContext, Line, MarkdownConfig } from '@lezer/markdown';
import { bemenet, keres, tarolobanMarad } from './belso';

function blokkKezdet(cx: BlockContext, line: Line): number {
  if (line.indent - line.baseIndent >= 4 || !line.text.slice(line.pos).startsWith('%%')) return -1;
  const input = bemenet(cx);
  const veg = keres(input, cx.lineStart + line.pos + 2, '%%');
  if (veg < 0) return -1;
  const sorVeg = keres(input, veg + 2, '\n');
  return input.read(veg + 2, sorVeg < 0 ? input.length : sorVeg).trim() ? -1 : veg + 2;
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
  }],
  parseInline: [{
    name: 'ObsidianComment',
    before: 'Emphasis',
    parse(cx: InlineContext, next: number, pos: number) {
      if (next !== 37 || cx.char(pos + 1) !== 37) return -1;
      const z = cx.text.indexOf('%%', pos - cx.offset + 2);
      if (z < 0) return -1;
      const veg = cx.offset + z + 2;
      return cx.addElement(cx.elt('ObsidianComment', pos, veg));
    },
  }],
};
