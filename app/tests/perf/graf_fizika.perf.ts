// Perf-készlet (T008, 2. audit): abszolút falióra-kapuk — NEM része az alap vitest-készletnek (`*.perf.ts`, nem `*.test.ts`).
// Futtatás: `bin/mos perf`, tétlen gépen (`MOS_TELJESITMENY=1`). A funkcionális megfelelő: tests/graf_fizika.test.ts (arány).
// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { Fizika } from '../../src/lib/graf/fizika';
import { szintetikus } from '../graf-segedek';

describe('Fizika (perf)', () => {
  it('a vault méretén (3852 csúcs, 10 512 él) egy tick messze a 16 ms-os képkocka alatt marad', () => {
    const g = szintetikus(3852, 10512);
    const f = new Fizika(g.n, g.elek, g.poz.slice());
    for (let i = 0; i < 5; i++) f.tick(); // bemelegítés (JIT)
    const t0 = performance.now();
    const db = 20;
    for (let i = 0; i < db; i++) f.tick();
    const atlag = (performance.now() - t0) / db;
    expect(Number.isFinite(atlag)).toBe(true); // a mért érték (≈ 3 ms) a NAPLO-ban; a kapu a 12 ms alatti átlag
    expect(atlag).toBeLessThan(12);
  });
});
