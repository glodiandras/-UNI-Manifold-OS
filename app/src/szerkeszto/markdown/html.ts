// A soron belüli HTML engedélylistája: az Olvasó (`olvaso/html.ts`) és a Live Preview (`elo/sorok.ts`) közös szabálya (C32).
// Csak attribútum nélküli, szöveget formázó címke jelenik meg; a többi szövegként látszik (CSP és biztonság: nincs
// `innerHTML`, nincs kép, link vagy stílus).

/** A soron belül megjelenített HTML-címkék engedélylistája (attribútum nélkül); a Live Preview is ezt használja (C32). */
export const ENGEDETT_HTML = new Set(['sub', 'sup', 'br', 'u', 'mark', 'kbd', 'b', 'i', 's', 'em', 'strong', 'small', 'del', 'ins']);

/** Egy soron belüli HTML-címke (`<x>`, `</x>`, `<x/>`) az engedélylistáról, attribútum nélkül; különben `null`. */
export function engedettCimke(cimke: string): { nev: string; zaro: boolean; onzaro: boolean } | null {
  const m = /^<(\/?)([a-zA-Z][a-zA-Z0-9]*)\s*(\/?)>$/.exec(cimke.trim());
  const nev = m?.[2].toLowerCase();
  return m && nev && ENGEDETT_HTML.has(nev) ? { nev, zaro: !!m[1], onzaro: !!m[3] } : null;
}
