// 01-rendering-14 (a betűméret maradéka): a jegyzet címsorai a felhasználói betűmérettel arányosan nőnek, 16 px-nél a
// tokenek pontos értékével; a felület krómja rögzített marad. A UI-nagyítás (⌘= / ⌘− / ⌘0) a 06-workspace-28 sor része.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const olvas = (ut: string) => readFileSync(decodeURIComponent(new URL(ut, import.meta.url).pathname), 'utf8');
const tokenek = olvas('../src/styles/tokens.css');
const megjelenites = olvas('../src/szerkeszto/megjelenites.css');

describe('a jegyzet címsorainak skálázása', () => {
  it('a tartalmi hatókör a --betu-torzs szorzójával adja a címsorokat; 16 px-nél a tokenek értéke', () => {
    const torzs = Number(/--betu-torzs:\s*(\d+)px/.exec(tokenek)![1]);
    expect(torzs).toBe(16);
    const blokk = /\.tipo,\s*\.szerkeszto\s*\{([^}]*)\}/.exec(megjelenites)![1];
    for (const n of [1, 2, 3, 4, 5]) {
      const token = Number(new RegExp(`--betu-h${n}:\\s*(\\d+)px`).exec(tokenek)![1]);
      const sor = new RegExp(`--betu-h${n}:\\s*([^;]+);`).exec(blokk)![1].trim();
      const szorzo = sor === 'var(--betu-torzs)' ? 1 : Number(/calc\(var\(--betu-torzs\) \* ([\d.]+)\)/.exec(sor)![1]);
      expect(torzs * szorzo).toBeCloseTo(token, 5);
      // 20 px-es betűméretnél arányosan nagyobb
      expect(20 * szorzo).toBeGreaterThan(token);
    }
  });

  it('a krómban (tokens.css gyökér) a címsor-tokenek rögzítettek maradnak', () => {
    for (const n of [1, 2, 3, 4, 5]) expect(tokenek).toMatch(new RegExp(`--betu-h${n}:\\s*\\d+px;`));
  });
});
