// A `html()`, `image()` és `icon()` értékek biztonságos megjelenítése (10-bases-08). A core típusos értéket ad (`html` / `kep` /
// `ikon`); itt dől el, mi rajzolható:
//   - html: a meglévő inert, korlátos szanitizáló másolata (`olvaso/htmlSzures.ts`): nincs szkript, esemény-attribútum, külső
//     betöltés; a kép alt-szöveggé válik, a link `data-url`-t kap (a héj megnyitója nyitja, `href` nincs). Korláton túl a nyers szöveg;
//   - kép: csak vault-helyi út (a média-végponton át), vagy `#szín`; a külső URL helyőrző marad (D3: nincs automatikus hálózat);
//   - ikon: a felület saját, szűkített ikonkészletéből; ismeretlen név esetén a név szövegként.

import type { IconNode } from 'lucide';
import * as IKONOK from '../lib/ikon/ikonok';
import { htmlBlokk } from '../szerkeszto/olvaso/htmlSzures';

const SZIN = /^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
const KEP_KITERJESZTES = /\.(png|jpe?g|gif|webp|svg|avif|bmp|heic|tiff?)$/i;

/** Érvényes CSS-szín (`#rgb`, `#rrggbb`, alfával); minden más (`url(…)`, szín-függvény, kulcsszó) elutasított. */
export function biztosSzin(s: unknown): string | null {
  return typeof s === 'string' && SZIN.test(s.trim()) ? s.trim() : null;
}

/** Vault-helyi képút: nem abszolút, nincs `..`, nincs séma és visszaper, képkiterjesztés. A feloldás és a hozzáférés a core dolga. */
export function biztosKepUt(ut: unknown): string | null {
  if (typeof ut !== 'string') return null;
  const s = ut.trim();
  if (!s || s.startsWith('/') || s.includes('\\') || /^[a-z][a-z0-9+.-]*:/i.test(s) || s.split('/').includes('..')) return null;
  return KEP_KITERJESZTES.test(s) ? s : null;
}

const pascal = (nev: string) =>
  nev
    .replace(/^lucide[-_:\s]*/i, '')
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((r) => r.charAt(0).toUpperCase() + r.slice(1))
    .join('');

/** Az `icon("book-open")` ikonja a felület ikonkészletéből, vagy `null`. */
export function ikonKeres(nev: unknown): IconNode | null {
  if (typeof nev !== 'string' || nev.length > 60) return null;
  const k = pascal(nev.trim());
  if (!/^[A-Za-z][A-Za-z0-9]*$/.test(k)) return null;
  const ikon = (IKONOK as unknown as Record<string, unknown>)[k];
  return Array.isArray(ikon) ? (ikon as IconNode) : null;
}

/** A szanitizált HTML a `cel` elembe (új csomópontok, nincs `innerHTML`); a korláton túli forrás szövegként kerül be. */
export function htmlBeszur(cel: HTMLElement, forras: string): void {
  cel.replaceChildren();
  const f = htmlBlokk(forras, { ut: null });
  if (f) cel.append(f);
  else cel.textContent = forras;
}
