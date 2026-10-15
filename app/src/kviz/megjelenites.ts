// A kvíz szövegeinek megjelenítése (C22a): a kérdés, a válaszok, a magyarázat és a forrásmondat Markdownja (képlet: KaTeX)
// ugyanazzal az elemzővel és renderelővel, mint a jegyzet (L42: egy szabály, nem saját). A Markdown soha nem kerül `innerHTML`-be.

import { obsidianElemzo } from '../szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../szerkeszto/olvaso/html';
import { LustaRajzolo } from '../szerkeszto/olvaso/lusta';

export interface MdParam {
  szoveg: string;
  /** a kvízt tartalmazó jegyzet útja (a linkek feloldásához) */
  ut: string | null;
}

let sorszam = 0;

/** Svelte-akció: a `szoveg` Markdownja a csomópontba (blokkszintű `<p>` nélkül nem; a stílus a margót nullázza). */
export function md(node: HTMLElement, p: MdParam) {
  const elotag = `kv${++sorszam}`;
  const rajzol = (q: MdParam) => {
    const fa = obsidianElemzo.parse(q.szoveg);
    node.replaceChildren(dokumentumRenderel(fa, { olvas: (a, b) => q.szoveg.slice(a, b), ut: q.ut, lusta: LustaRajzolo.azonnali(), elotag }));
  };
  rajzol(p);
  return {
    update: rajzol,
    destroy: () => node.replaceChildren(),
  };
}
