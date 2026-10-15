// A függvénygörbe mintavétele (C35a): folytonos szakaszokra bontás szakadásnál és az értelmezési tartomány szélén,
// az aszimptotán át nem húzott vonal, adaptív finomítás, pontplafon.

import { describe, expect, it } from 'vitest';
import { fordit } from '../src/szerkeszto/renderelok/plot/kifejezes';
import { egybe, mintaz, type Minta } from '../src/szerkeszto/renderelok/plot/mintavetel';

const O = { ymin: -5, ymax: 5 };
const pontok = (sz: Minta[]) => sz.reduce((a, s) => a + s.x.length, 0);

describe('szakaszok', () => {
  it('az állandó függvény egy szakasz', () => {
    const sz = mintaz(() => 2, -3, 3, O);
    expect(sz).toHaveLength(1);
    expect(sz[0].y.every((y) => y === 2)).toBe(true);
    expect(sz[0].x[0]).toBe(-3);
    expect(sz[0].x.at(-1)).toBe(3);
  });

  it('az 1/x két szakasz: nincs vonal a pólus fölött', () => {
    const sz = mintaz(fordit('1/x'), -4, 4, O);
    expect(sz).toHaveLength(2);
    expect(sz[0].x.every((x) => x < 0)).toBe(true);
    expect(sz[1].x.every((x) => x > 0)).toBe(true);
    for (const s of sz) expect(s.y.length).toBe(s.x.length);
  });

  it('a tangens ágai külön szakaszok (π/2 körül és az ablakban)', () => {
    const sz = mintaz(fordit('tan(x)'), -4, 4, O);
    expect(sz).toHaveLength(3); // (-4, -π/2), (-π/2, π/2), (π/2, 4)
    for (const s of sz) {
      for (let i = 1; i < s.x.length; i++) {
        expect(Math.abs(s.y[i] - s.y[i - 1])).toBeLessThan(40); // egy ágon belül nincs ugrás a pólus fölött
      }
    }
  });

  it('a gyök értelmezési tartományának széle a görbe kezdete (nincs rés a 0 előtt)', () => {
    const sz = mintaz(fordit('sqrt(x)'), -2, 4, O);
    expect(sz).toHaveLength(1);
    expect(sz[0].x[0]).toBeGreaterThanOrEqual(0);
    expect(sz[0].x[0]).toBeLessThan(1e-6);
    expect(sz[0].y[0]).toBeLessThan(1e-3);
  });

  it('a logaritmus a 0-nál kezdődik, a negatív oldal kimarad', () => {
    const sz = mintaz(fordit('ln(x)'), -3, 3, O);
    expect(sz).toHaveLength(1);
    expect(sz[0].x[0]).toBeGreaterThan(0);
    expect(sz[0].x[0]).toBeLessThan(1e-6);
  });

  it('a teljesen értelmezetlen függvény nem ad szakaszt; a fordított ablak sem', () => {
    expect(mintaz(fordit('sqrt(-x^2-1)'), -3, 3, O)).toEqual([]);
    expect(mintaz(() => 1, 3, -3, O)).toEqual([]);
    expect(mintaz(() => 1, 3, 3, O)).toEqual([]);
  });

  it('a hézag a függvény közepén két szakaszra bont (x^(1/2) a páros gyök miatt hiányzik a negatív oldalon)', () => {
    const sz = mintaz((x) => (Math.abs(x) < 1 ? NaN : x), -3, 3, O);
    expect(sz).toHaveLength(2);
  });
});

describe('pontosság', () => {
  function legnagyobbElteres(f: (x: number) => number, sz: Minta[]): number {
    let m = 0;
    for (const s of sz) {
      for (let i = 1; i < s.x.length; i++) {
        const k = (s.x[i] + s.x[i - 1]) / 2;
        const lin = (s.y[i] + s.y[i - 1]) / 2;
        const v = f(k);
        if (Number.isFinite(v) && Math.abs(v) < 4) m = Math.max(m, Math.abs(v - lin));
      }
    }
    return m;
  }

  it('a szinusz két periódusa a vonalszakaszok közelítésével 1%-on belül', () => {
    const f = fordit('sin(x)');
    expect(legnagyobbElteres(f, mintaz(f, 0, 4 * Math.PI, { ymin: -1.5, ymax: 1.5, pontok: 200 }))).toBeLessThan(0.015);
  });

  it('az éles csúcs (1/(1+100x²)) körül finomít', () => {
    const f = fordit('1/(1+100x^2)');
    const sz = mintaz(f, -2, 2, { ymin: -0.2, ymax: 1.2, pontok: 120 });
    expect(legnagyobbElteres(f, sz)).toBeLessThan(0.02);
  });

  it('a törés (|x|) a mintán a csúcsig lemegy', () => {
    const f = fordit('abs(x)');
    const sz = mintaz(f, -2, 2, { ymin: -1, ymax: 3, pontok: 100 });
    expect(Math.min(...sz[0].y)).toBeLessThan(0.05);
  });

  it('a pontplafon betartva', () => {
    const f = fordit('sin(1000x)');
    const sz = mintaz(f, -5, 5, { ymin: -1, ymax: 1, pontok: 800, maxPont: 3000 });
    expect(pontok(sz)).toBeLessThanOrEqual(3000);
  });

  it('a kilógó érték vágva (a SVG-útvonal ne kapjon óriási számot)', () => {
    const sz = mintaz(fordit('1/x^2'), -1, 1, O);
    for (const s of sz) for (const y of s.y) expect(y).toBeLessThanOrEqual(5 + 20 * 10 + 1e-9);
  });
});

describe('egybe', () => {
  it('a szakaszok NaN-nal elválasztva egy tömbpárban (a JSXGraph curve szakít a NaN-nál)', () => {
    const e = egybe([
      { x: [0, 1], y: [0, 1] },
      { x: [2, 3], y: [2, 3] },
    ]);
    expect(e.x).toHaveLength(5);
    expect(e.x[2]).toBeNaN();
    expect(e.y[2]).toBeNaN();
    expect(e.x.slice(3)).toEqual([2, 3]);
  });

  it('üres bemenetre üres', () => {
    expect(egybe([])).toEqual({ x: [], y: [] });
  });
});
