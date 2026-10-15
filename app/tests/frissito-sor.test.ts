// C33 (T070): a `vault_valtozas` utáni újralekérdezések közös sora — egyszerre egy fut, kulcsonként a legutóbbi kérés
// számít, a késleltetés kulcsonként összevon.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FrissitoSor } from '../src/lib/core/frissitoSor';

describe('FrissitoSor', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('a mentés utáni roham kérései sorban futnak, nem párhuzamosan', async () => {
    const sor = new FrissitoSor();
    const naplo: string[] = [];
    const lassu = (nev: string) => async () => {
      naplo.push(`${nev}+`);
      await new Promise((r) => setTimeout(r, 100));
      naplo.push(`${nev}-`);
    };
    sor.ker('kapcsolatok', lassu('k'), 300);
    sor.ker('bazis', lassu('b'), 300);
    sor.ker('graf', lassu('g'), 1200);
    await vi.advanceTimersByTimeAsync(2000);
    expect(naplo).toEqual(['k+', 'k-', 'b+', 'b-', 'g+', 'g-']);
    expect(sor.csucs).toBe(1);
    expect(sor.lefutott).toBe(3);
  });

  it('kulcsonként a késleltetésen belüli kérések egy futásba vonódnak össze, és a legutóbbi feladat fut', async () => {
    const sor = new FrissitoSor();
    const futott: number[] = [];
    for (let i = 0; i < 5; i++) {
      sor.ker('graf', () => futott.push(i), 300);
      await vi.advanceTimersByTimeAsync(100);
    }
    await vi.advanceTimersByTimeAsync(500);
    expect(futott).toEqual([4]);
  });

  it('a sosem végző tétel legfeljebb a tétel-korlátig tartja a sort (javítókör D, 13.)', async () => {
    const sor = new FrissitoSor(1000);
    const futott: string[] = [];
    sor.ker('akad', () => new Promise(() => {}));
    sor.ker('fa', () => futott.push('fa'));
    await vi.advanceTimersByTimeAsync(999);
    expect(futott).toEqual([]);
    await vi.advanceTimersByTimeAsync(2);
    expect(futott).toEqual(['fa']);
    expect(sor.fuggo).toBe(0);
  });

  it('az elvetett kulcs nem fut, és a hibás feladat nem állítja meg a sort', async () => {
    const sor = new FrissitoSor();
    const futott: string[] = [];
    sor.ker('a', () => futott.push('a'), 100);
    sor.ker('b', () => {
      throw new Error('hiba');
    }, 50);
    sor.ker('c', () => futott.push('c'), 200);
    sor.elvet('a');
    await vi.advanceTimersByTimeAsync(500);
    expect(futott).toEqual(['c']);
    expect(sor.fuggo).toBe(0);
  });
});
