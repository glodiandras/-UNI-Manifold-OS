// Betűcsalád-beállítás (14-appearance-01/02): a jegyzet szövegének és a monospace helyeknek (kód, Forrás mód) a betűje.
//
// Csak TELEPÍTETT családot lehet megnevezni, névvel: nincs `@font-face`, nincs URL, nincs külső betöltés (D3: futás közben nincs
// hálózat). A név szigorú alakú (a core `termek_beallitasok.betu_nev_hiba`-val azonos szabály), és a CSS-be mindig idézőjelben,
// a rendszer-betűvel mint tartalékkal kerül: egy ismeretlen név így az alapértelmezett betűt adja, soha nem érvénytelen CSS-t.
// A színek, méretek tokenek maradnak; itt csak a két betű-token (`--betu-jegyzet`, `--betu-mono`) felülírása történik.

export const BETU_NEV_MAX = 80;

/** Betűk, számjegyek, `.` `_` `+` `-`; szavak között egy szóköz; se idézőjel, se `;{}()\,:/@`, se vezérlőkarakter. */
const NEV_MINTA = /^[\p{L}\p{N}._+-]+(?: [\p{L}\p{N}._+-]+)*$/u;

/** Üres név = alapértelmezett betű (érvényes). */
export function betuNevJo(nev: unknown): nev is string {
  return typeof nev === 'string' && (nev === '' || (nev.length <= BETU_NEV_MAX && NEV_MINTA.test(nev)));
}

/** A CSS-sztring tartalma: a `\` és a `"` escape-elve (a szigorú név miatt ide sosem jut, de a függvény önmagában is biztonságos). */
export function cssSztring(nev: string): string {
  return nev.replace(/[\\"]/g, (c) => '\\' + c).replace(/[\u0000-\u001f\u007f]/g, '');
}

/**
 * A `font-family` értéke: `"Név", <tartalék>`. Érvénytelen vagy üres névre csak a tartalék (az alapértelmezett betű).
 * A `tartalek` token-hivatkozás (`var(--betu-rendszer)` / `var(--betu-mono-alap)`), nem betű-literál.
 */
export function betuCss(nev: string, tartalek: string): string {
  return betuNevJo(nev) && nev !== '' ? `"${cssSztring(nev)}", ${tartalek}` : tartalek;
}

export const SZOVEG_TARTALEK = 'var(--betu-rendszer)';
export const MONO_TARTALEK = 'var(--betu-mono-alap)';

/** A két betű-token a gyökéren; üres/érvénytelen beállítás törli a felülírást (az alap visszaáll). */
export function betuAlkalmaz(megjelenes: { betu_szoveg?: string; betu_mono?: string }, gyoker: HTMLElement = document.documentElement): void {
  const allit = (token: string, nev: string | undefined, tartalek: string) => {
    if (nev && betuNevJo(nev)) gyoker.style.setProperty(token, betuCss(nev, tartalek));
    else gyoker.style.removeProperty(token);
  };
  allit('--betu-jegyzet', megjelenes.betu_szoveg, SZOVEG_TARTALEK);
  allit('--betu-mono', megjelenes.betu_mono, MONO_TARTALEK);
}

/** Ismert, a macOS-hez tartozó vagy széles körben telepített családok: javaslat a mezőhöz (a lista nem kötelező, nem tiltólista). */
export const SZOVEG_JAVASLAT = ['Helvetica Neue', 'Avenir Next', 'Georgia', 'Palatino', 'Times New Roman', 'Iowan Old Style', 'Charter', 'Optima', 'Gill Sans', 'Verdana'] as const;
export const MONO_JAVASLAT = ['SF Mono', 'Menlo', 'Monaco', 'Courier New', 'Andale Mono'] as const;

export type Meroto = (font: string, szoveg: string) => number | null;

function vaszonMero(): Meroto | null {
  try {
    const ctx = document.createElement('canvas').getContext('2d');
    if (!ctx) return null;
    return (font, szoveg) => { ctx.font = font; return ctx.measureText(szoveg).width; };
  } catch { return null; }
}

/**
 * Telepítve van-e a család? A böngésző nem listázza a telepített betűket (ez védi a felhasználót az ujjlenyomatozástól), ezért a
 * szövegszélesség-próba: ha a név bármelyik általános családnál mást mér, létezik. `null`: nem eldönthető (nincs vászon) — a felület
 * ilyenkor nem állít semmit. Üres név: az alapértelmezett, mindig "van".
 */
export function betuTelepitve(nev: string, mero: Meroto | null = vaszonMero()): boolean | null {
  if (nev === '') return true;
  if (!betuNevJo(nev) || !mero) return betuNevJo(nev) ? null : false;
  const minta = 'mmmmmmmmmmlliWWWW0123456789 @#';
  for (const alap of ['monospace', 'serif', 'sans-serif']) {
    const a = mero(`72px ${alap}`, minta);
    const b = mero(`72px "${cssSztring(nev)}", ${alap}`, minta);
    if (a === null || b === null) return null;
    if (Math.abs(a - b) > 0.01) return true;
  }
  return false;
}

/** A javaslatokból azok, amelyek ténylegesen telepítve vannak (ha nem eldönthető: mind). */
export function telepitettJavaslat(lista: readonly string[], mero: Meroto | null = vaszonMero()): string[] {
  const szurt = lista.filter((n) => betuTelepitve(n, mero) !== false);
  return szurt.length ? szurt : [...lista];
}
