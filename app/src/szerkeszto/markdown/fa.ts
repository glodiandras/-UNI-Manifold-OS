// Segédek a szintaxisfához: a képletek TeX-forrása (a tárolójelek nélkül) és felsorolásuk.

import type { SyntaxNode, Tree } from '@lezer/common';

export interface Keplet {
  from: number;
  to: number;
  /** megjelenítési (`$$`) vagy soron belüli (`$`) */
  display: boolean;
  /** sor eleji `$$` blokk (a többi soron belül áll) */
  blokk: boolean;
  tex: string;
}

export type Olvaso = (from: number, to: number) => string;

const KEPLET_NEVEK = new Set(['InlineMath', 'DisplayMath', 'MathBlock']);

export function kepletCsomopont(nev: string): boolean {
  return KEPLET_NEVEK.has(nev);
}

/** Egy képlet-csomópont TeX-forrása. A blokk soronkénti `MathText`-jeiből áll; a soron belüli képletből
 *  a több sorra nyúló `$$` idézetben álló `>` jeleit szóközre cseréli (a TeX-nek a szóköz közömbös). */
export function kepletForras(node: SyntaxNode, olvas: Olvaso): string {
  if (node.name === 'MathBlock') {
    const sorok: string[] = [];
    for (let c = node.firstChild; c; c = c.nextSibling) if (c.name === 'MathText') sorok.push(olvas(c.from, c.to));
    return sorok.join('\n');
  }
  const elso = node.firstChild;
  const utolso = node.lastChild;
  if (!elso || !utolso || elso === utolso) return '';
  const kezd = elso.to;
  const veg = utolso.from;
  let tex = olvas(kezd, veg);
  for (let c = elso.nextSibling; c && c.from < veg; c = c.nextSibling) {
    if (c.name !== 'QuoteMark') continue;
    const a = c.from - kezd;
    tex = tex.slice(0, a) + ' '.repeat(c.to - c.from) + tex.slice(a + c.to - c.from);
  }
  return tex;
}

/** A dokumentum összes képlete, sorrendben. */
export function kepletek(fa: Tree, olvas: Olvaso, from = 0, to = fa.length): Keplet[] {
  const ki: Keplet[] = [];
  fa.iterate({
    from,
    to,
    enter(n) {
      if (!KEPLET_NEVEK.has(n.name)) return;
      ki.push({
        from: n.from,
        to: n.to,
        display: n.name !== 'InlineMath',
        blokk: n.name === 'MathBlock',
        tex: kepletForras(n.node, olvas),
      });
      return false;
    },
  });
  return ki;
}
