// A feladat-napló követése (javítókör D, 6. lelet): egyszerre egy kérés, az elavult `tol` válasza eldobva, plafonos sorszám.

import { describe, expect, it } from 'vitest';
import { egyszerre, naploHozzafuz, type NaploAllapot } from '../src/lib/vezerlo/naplo';

const ures: NaploAllapot = { sorok: [], tol: 0, levagva: 0 };

describe('naploHozzafuz', () => {
  it('hozzáfűz, és a következő kezdősor a core összes sora', () => {
    const a = naploHozzafuz(ures, 0, { sorok: ['a', 'b'], osszes_sor: 2 })!;
    expect(a).toEqual({ sorok: ['a', 'b'], tol: 2, levagva: 0 });
    expect(naploHozzafuz(a, 2, { sorok: ['c'], osszes_sor: 3 })).toEqual({ sorok: ['a', 'b', 'c'], tol: 3, levagva: 0 });
  });

  it('az elavult tol-ra jött válasz eldobódik (nincs duplázott sor)', () => {
    const a = naploHozzafuz(ures, 0, { sorok: ['a', 'b'], osszes_sor: 2 })!;
    expect(naploHozzafuz(a, 0, { sorok: ['a', 'b'], osszes_sor: 2 })).toBeNull();
    expect(naploHozzafuz(a, 2, { sorok: [], osszes_sor: 2 })).toBeNull();
  });

  it('a sorok száma plafonos, a levágott sorok száma látszik', () => {
    let a: NaploAllapot = ures;
    for (let i = 0; i < 5; i++) a = naploHozzafuz(a, a.tol, { sorok: [`s${2 * i}`, `s${2 * i + 1}`], osszes_sor: a.tol + 2 }, 4)!;
    expect(a.sorok).toEqual(['s6', 's7', 's8', 's9']);
    expect(a.levagva).toBe(6);
    expect(a.tol).toBe(10);
  });
});

describe('egyszerre', () => {
  it('futás közben nem indul párhuzamos kérés; a közben jött kérések egy ismétlésbe olvadnak', async () => {
    let fut = 0;
    let max = 0;
    let hivas = 0;
    const engedok: (() => void)[] = [];
    const f = egyszerre(async () => {
      hivas++;
      fut++;
      max = Math.max(max, fut);
      await new Promise<void>((r) => engedok.push(r));
      fut--;
    });
    const p1 = f();
    void f();
    void f();
    expect(hivas).toBe(1);
    engedok.shift()!();
    await new Promise((r) => setTimeout(r, 0));
    expect(hivas).toBe(2); // egy ismétlés
    engedok.shift()!();
    await p1;
    expect(max).toBe(1);
    expect(hivas).toBe(2);
    const p2 = f(); // a futás után újra indítható
    expect(hivas).toBe(3);
    engedok.shift()!();
    await p2;
  });
});
