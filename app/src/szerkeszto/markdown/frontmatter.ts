// Frontmatter: az L39 szabálya (a legacy `vaultlib` és a core indexe, `FM_RE`), a C29.8 (T130) kiegészítésével:
//   \A\ufeff?---\r?\n(.*?)(?:(?<=\n)|\r?\n)---\r?\n?
// azaz az első sor `---` (előtte esetleg BOM), a lezáró a következő `---`-val kezdődő sor — az üres blokk (`---`/`---`)
// is frontmatter; lezáró nélkül nincs frontmatter (a `---` akkor elválasztó). A CodeMirror a sorvéget `\n`-re
// egységesíti, így itt csak `\n` áll.

import type { BlockContext, Line, MarkdownConfig } from '@lezer/markdown';
import { bemenet, keres } from './belso';
import { cimkek } from './cimkek';

export const Frontmatter: MarkdownConfig = {
  defineNodes: [
    { name: 'Frontmatter', block: true },
    { name: 'FrontmatterContent', style: cimkek.frontmatter },
    { name: 'FrontmatterMark', style: cimkek.frontmatter },
  ],
  parseBlock: [
    {
      name: 'Frontmatter',
      parse(cx: BlockContext, line: Line) {
        const bom = line.text.startsWith('\ufeff') ? 1 : 0;
        if (cx.lineStart !== 0 || line.text.slice(bom) !== '---') return false;
        // a `(.*?)` a nyitó sor után kezdődik: a lezáró `\n---` legkorábban a nyitó sor sortörése (üres blokk); az üres blokk
        // tehát frontmatter (a következő `---` sor nem számít), ahogy a regex
        const p = keres(bemenet(cx), bom + 3, '\n---');
        if (p < 0) return false;
        const zaroKezd = p + 1;
        const elemek = [cx.elt('FrontmatterMark', bom, bom + 3)];
        if (p > bom + 4) elemek.push(cx.elt('FrontmatterContent', bom + 4, p));
        elemek.push(cx.elt('FrontmatterMark', zaroKezd, zaroKezd + 3));
        let veg = 0;
        for (;;) {
          const ez = cx.lineStart;
          veg = ez + line.text.length;
          const van = cx.nextLine();
          if (ez >= zaroKezd || !van) break;
        }
        cx.addElement(cx.elt('Frontmatter', 0, veg, elemek));
        return true;
      },
      before: 'LinkReference',
    },
  ],
};
