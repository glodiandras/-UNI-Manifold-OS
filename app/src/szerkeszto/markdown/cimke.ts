// A törzs #címkéje a core/index/elemzo.py _CIMKE nyelvtanával. A Python \w Unicode betű/szám/_;
// a kombináló jelek nem részei. A \d csak Nd, ezért pl. a ² önmagában is érvényes címke.

import { tags } from '@lezer/highlight';
import type { InlineContext, MarkdownConfig } from '@lezer/markdown';

export const CIMKE_KARAKTER = /^[\p{L}\p{N}_/-]$/u;
const NEM_CSUPA_SZAM = /[^\p{Nd}/]/u;
// A Python str.isspace / re \s készlete; a JS \s NEL/FS–US/BOM esetén eltérne.
const PY_SZOKOZ = /^[\t\n\v\f\r\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/u;
export const CIMKE_PREFIX = /(?:^|[\t\n\v\f\r\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000])#([\p{L}\p{N}_/-]*)$/u;

function cimkeHossz(szoveg: string, kezd: number): number {
  let hossz = 0;
  for (const c of szoveg.slice(kezd)) {
    if (!CIMKE_KARAKTER.test(c)) break;
    hossz += c.length;
  }
  return hossz;
}

/** Teljes címkeérték (opcionális #, környező szóköz, záró / nélkül); hibás régi értékre null. */
export function cimkeErtek(nyers: string): string | null {
  const vagott = nyers.replace(/^[\t\n\v\f\r\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t\n\v\f\r\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu, '');
  const cimke = (vagott.startsWith('#') ? vagott.slice(1) : vagott).replace(/\/+$/, '');
  return cimke && cimkeHossz(cimke, 0) === cimke.length && NEM_CSUPA_SZAM.test(cimke) ? cimke : null;
}

/** Egy teljes #tag token validálása, a végén nem szerepelhet levágandó írásjel. */
export function cimkeSzoveg(nyers: string): string | null {
  if (!nyers.startsWith('#')) return null;
  const cimke = nyers.slice(1);
  return cimke && !cimke.endsWith('/') && cimkeHossz(cimke, 0) === cimke.length && NEM_CSUPA_SZAM.test(cimke) ? cimke : null;
}

/** A navigáció és a megjelenítés ugyanazt az ellenőrzött értéket kapja a Hashtag csomópontból. */
export function cimkeAdat(n: { name: string; from: number; to: number }, olvas: (from: number, to: number) => string): string | null {
  if (n.name === 'Hashtag') return cimkeSzoveg(olvas(n.from, n.to));
  if (n.name === 'HashtagLabel') return cimkeErtek(olvas(n.from, n.to));
  return null;
}

export const Cimke: MarkdownConfig = {
  defineNodes: [
    { name: 'Hashtag', style: { 'Hashtag/...': tags.labelName } },
    { name: 'HashtagMark', style: tags.labelName },
    { name: 'HashtagLabel', style: tags.labelName },
  ],
  parseInline: [{
    name: 'Hashtag',
    before: 'Link',
    parse(cx: InlineContext, next: number, pos: number) {
      if (next !== 35) return -1;
      const elotte = cx.slice(pos - 1, pos);
      if (elotte && !PY_SZOKOZ.test(elotte)) return -1;
      const kezd = pos - cx.offset + 1;
      const hossz = cimkeHossz(cx.text, kezd);
      const cimke = cx.text.slice(kezd, kezd + hossz).replace(/\/+$/, '');
      if (!cimke || !NEM_CSUPA_SZAM.test(cimke)) return -1;
      const veg = pos + 1 + cimke.length;
      return cx.addElement(cx.elt('Hashtag', pos, veg, [cx.elt('HashtagMark', pos, pos + 1), cx.elt('HashtagLabel', pos + 1, veg)]));
    },
  }],
};
