// A saját Markdown-csomópontok kiemelési címkéi. A Forrás-mód és a Live Preview stílusa ezekhez köt
// (szerkeszto/elo/tema.ts); a beépített csomópontok a @lezer/highlight szabványos címkéit kapják.

import { Tag, tags as t } from '@lezer/highlight';

export const cimkek = {
  /** A képlet TeX-forrása (soron belül és blokkban). */
  keplet: Tag.define(),
  /** A képlet `$` / `$$` jele. */
  kepletJel: Tag.define(t.processingInstruction),
  /** `==kiemelés==` */
  jeloles: Tag.define(),
  /** Lábjegyzet-hivatkozás és -címke. */
  labjegyzet: Tag.define(),
  /** Wikilink és beágyazás (a megjelenítésük a C10-é). */
  wikilink: Tag.define(t.link),
  /** A frontmatter (YAML) tartalma. */
  frontmatter: Tag.define(t.meta),
};
