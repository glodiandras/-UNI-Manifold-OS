// Wikilink `[[cél#fejezet|alias]]` és beágyazás `![[…]]` — csak a szerkezet (a megjelenítés, a feloldás
// és a navigáció a C10-é; feloldani csak a core-ban szabad, L42). A cél az index szabálya szerint a
// `[[` utáni `[^\]|#]*`; a táblázatcellában álló `\|` elválasztó, a `\` a jelhez tartozik. A link egy
// soron belül marad, és üres `[[]]` nem link.

import type { InlineContext, MarkdownConfig } from '@lezer/markdown';
import { cimkek } from './cimkek';

const FELKIALTO = 33;
const NYITO = 91;

export const Wikilink: MarkdownConfig = {
  defineNodes: [
    { name: 'Wikilink', style: { 'Wikilink/...': cimkek.wikilink } },
    { name: 'Embed', style: { 'Embed/...': cimkek.wikilink } },
    { name: 'WikilinkMark', style: cimkek.wikilink },
    { name: 'WikilinkTarget', style: cimkek.wikilink },
    { name: 'WikilinkSubpath', style: cimkek.wikilink },
    { name: 'WikilinkAlias', style: cimkek.wikilink },
  ],
  parseInline: [
    {
      name: 'Wikilink',
      parse(cx: InlineContext, next: number, pos: number) {
        let nyitoVeg: number;
        if (next === FELKIALTO && cx.char(pos + 1) === NYITO && cx.char(pos + 2) === NYITO) nyitoVeg = pos + 3;
        else if (next === NYITO && cx.char(pos + 1) === NYITO) nyitoVeg = pos + 2;
        else return -1;
        const i = cx.text.indexOf(']]', nyitoVeg - cx.offset);
        if (i < 0) return -1;
        const zaro = cx.offset + i;
        const belso = cx.slice(nyitoVeg, zaro);
        if (!belso || belso.includes('\n')) return -1;

        const gyerek = [cx.elt('WikilinkMark', pos, nyitoVeg)];
        const cso = belso.indexOf('|');
        const hash = belso.indexOf('#');
        const celVeg = Math.min(...[cso, hash, belso.length].filter((x) => x >= 0));
        // `\|` (táblázatban): a visszaper a cél utolsó karaktere helyett az elválasztóhoz tartozik
        const celVegAbs = nyitoVeg + (cso >= 0 && celVeg === cso && belso[cso - 1] === '\\' ? cso - 1 : celVeg);
        if (celVegAbs > nyitoVeg) gyerek.push(cx.elt('WikilinkTarget', nyitoVeg, celVegAbs));
        if (hash >= 0 && (cso < 0 || hash < cso)) {
          const alVeg = cso >= 0 ? (belso[cso - 1] === '\\' ? cso - 1 : cso) : belso.length;
          if (alVeg > hash) gyerek.push(cx.elt('WikilinkSubpath', nyitoVeg + hash, nyitoVeg + alVeg));
        }
        if (cso >= 0) {
          const jelKezd = belso[cso - 1] === '\\' ? cso - 1 : cso;
          gyerek.push(cx.elt('WikilinkMark', nyitoVeg + jelKezd, nyitoVeg + cso + 1));
          if (cso + 1 < belso.length) gyerek.push(cx.elt('WikilinkAlias', nyitoVeg + cso + 1, zaro));
        }
        gyerek.push(cx.elt('WikilinkMark', zaro, zaro + 2));
        return cx.addElement(cx.elt(nyitoVeg === pos + 3 ? 'Embed' : 'Wikilink', pos, zaro + 2, gyerek));
      },
      before: 'Link',
    },
  ],
};
