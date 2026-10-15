// Perf-készlet (T008, 2. audit): abszolút falióra-kapu — NEM része az alap vitest-készletnek (`*.perf.ts`).
// Futtatás: `bin/mos perf`, tétlen gépen (`MOS_TELJESITMENY=1`). A funkcionális megfelelő: tests/fuzzy.test.ts (arány).
// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { FuzzyIndex } from '../../src/lib/kereses/fuzzy';

describe('FuzzyIndex (perf)', () => {
  it('4000 elemen gyors (< 15 ms / lekérdezés)', () => {
    const szavak = ['sorozat', 'mértani', 'függvény', 'határérték', 'derivált', 'integrál', 'vektor', 'mátrix', 'gráf'];
    const nevek = Array.from({ length: 4000 }, (_, i) => `${szavak[i % 9]} ${szavak[(i * 7) % 9]} ${i}`);
    const ix = new FuzzyIndex(nevek.map((n) => ({ ertek: n, nev: n, ut: `Matek/${n}.md` })));
    ix.keres('fugveny'); // bemelegítés
    // a három kör közül a leggyorsabb számít
    const korok = [0, 1, 2].map(() => {
      const t0 = performance.now();
      for (const q of ['mertani', 'fugveny hatar', 'drivalt', 'xyz', 'm']) ix.keres(q);
      return (performance.now() - t0) / 5;
    });
    expect(Math.min(...korok)).toBeLessThan(15);
  });
});
