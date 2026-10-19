// A statikus közös fixture a TS elemző tartományait és a Python indexmaszkot is köti.
// Az offsetek UTF-16 kódegységek; a Python-fogyasztó kifejezetten konvertálja őket, nem normalizálja a forrást.
import { describe, expect, it } from 'vitest';
import adatok from '../../tests/adat/megjegyzes_index.json';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';

describe('S1: komment/index közös parser-fixture', () => {
  it.each(adatok)('$nev', ({ szoveg, utf16_szakaszok, megjegyzesek }) => {
    const szakaszok: number[][] = [];
    obsidianElemzo.parse(szoveg).iterate({ enter(n) {
      if (n.name === 'ObsidianComment' || n.name === 'ObsidianCommentBlock') szakaszok.push([n.from, n.to]);
    } });
    expect(szakaszok).toEqual(utf16_szakaszok);
    expect(szakaszok.map(([a, b]) => szoveg.slice(a, b))).toEqual(megjegyzesek);
  });
});
