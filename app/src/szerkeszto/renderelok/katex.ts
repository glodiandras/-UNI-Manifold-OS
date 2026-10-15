// KaTeX a szerkesztőnek, az olvasónak és a képlet-szkriptnek — EGY beállítással. A vault képleteit az
// Obsidian MathJaxe alá írták; ahol a KaTeX mást vár, itt egy makró hidalja át (a forrás nem változik).
// A képletek vault-szintű próbája: tests/kezi/kepletek.py (0 renderelési hiba a kapu).

import katex, { type KatexOptions } from 'katex';

/** A vault képleteihez kellő makrók. Minden sor mögött mért eset áll (a képlet-szkript riportja). */
export const KATEX_MAKROK: Record<string, string> = {
  // `\text{gáz \to rakéta}`: a MathJax a szövegben is nyilat ad, a KaTeX-ben a `\to` csak math módú
  // (2026-10-01: 2 képlet, F02). Math módban változatlanul `\rightarrow` (ugyanaz a jel).
  '\\to': '\\TextOrMath{$\\rightarrow$}{\\rightarrow}',
};

// A zárójel nélküli alsó/felső indexben álló operátornév (`K_\max`, `F_\min`): a MathJax és a TeX elfogadja,
// a KaTeX nem (2026-10-01: 5 képlet, F02). Csak az argumentum nélküli operátorneveket tesszük kapcsos
// zárójelbe, a forrásfájl nem változik.
const OPERATOR_INDEXBEN =
  /([_^])(\s*)(\\(?:max|min|sup|inf|lim|limsup|liminf|log|ln|lg|exp|sin|cos|tan|cot|sec|csc|sinh|cosh|tanh|coth|arcsin|arccos|arctan|arctg|arcctg|arg|deg|det|dim|gcd|hom|ker|Pr|tg|ctg|cotg|sh|ch|th|cth)(?![a-zA-Z]))/g;

/** A KaTeX elé kerülő forrás: a MathJax-tűrés áthidalása (a fájl nem változik). */
export function kepletElokeszit(tex: string): string {
  return tex.includes('\\') ? tex.replace(OPERATOR_INDEXBEN, '$1$2{$3}') : tex;
}

export interface KatexHiba {
  uzenet: string;
}

export function katexBeallitas(display: boolean, o: { hibaDob?: boolean; szigoru?: KatexOptions['strict'] } = {}): KatexOptions {
  return {
    displayMode: display,
    throwOnError: o.hibaDob ?? false,
    // a hibás képlet a forrásával, a téma hiba-színével látszik (nem tűnik el csendben)
    errorColor: 'var(--hiba)',
    strict: o.szigoru ?? 'ignore',
    trust: false,
    output: 'htmlAndMathml',
    // a KaTeX a makrótáblát a \gdef-fel írhatja: minden híváshoz friss másolat
    macros: { ...KATEX_MAKROK },
  };
}

const TAR_MERET = 4000;
const tar = new Map<string, string>();

/** A képlet HTML-je, gyorsítótárral (a KaTeX kimenete determinisztikus). */
export function katexHtml(tex: string, display: boolean): string {
  const kulcs = (display ? 'D' : 'I') + tex;
  const mar = tar.get(kulcs);
  if (mar !== undefined) {
    tar.delete(kulcs);
    tar.set(kulcs, mar);
    return mar;
  }
  const html = katex.renderToString(kepletElokeszit(tex), katexBeallitas(display));
  tar.set(kulcs, html);
  if (tar.size > TAR_MERET) tar.delete(tar.keys().next().value as string);
  return html;
}

/** Szigorú renderelés (a próbákhoz): ParseError-t dob. */
export function katexEllenoriz(tex: string, display: boolean, szigoru?: KatexOptions['strict']): string {
  return katex.renderToString(kepletElokeszit(tex), katexBeallitas(display, { hibaDob: true, szigoru }));
}
