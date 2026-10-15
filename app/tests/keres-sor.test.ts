// C33 (T184, A2-nezetek-8): a canvas jegyzetkártyáinak kérés-sora — legfeljebb 6 egyidejű kérés, a megszakított várakozó
// nem indul el és helyet sem foglal.
import { describe, expect, it } from 'vitest';
import { KeresSor } from '../src/lib/core/keresSor';

function nyitott() {
  let ok!: (v: number) => void;
  const p = new Promise<number>((r) => (ok = r));
  return { p, ok };
}

describe('KeresSor', () => {
  it('60 kérésből egyszerre legfeljebb 6 fut, és mind lefut', async () => {
    const sor = new KeresSor(6);
    const nyitottak = Array.from({ length: 60 }, () => nyitott());
    const eredmenyek = nyitottak.map((n, i) => sor.futtat(() => n.p.then(() => i)));
    expect(sor.futo).toBe(6);
    expect(sor.varakozik).toBe(54);
    for (const n of nyitottak) {
      n.ok(1);
      await Promise.resolve();
    }
    expect(await Promise.all(eredmenyek)).toEqual(Array.from({ length: 60 }, (_, i) => i));
    expect(sor.csucs).toBe(6);
    expect(sor.futo).toBe(0);
  });

  it('a megszakított várakozó kérés nem indul el, a hely a következőé', async () => {
    const sor = new KeresSor(1);
    const elso = nyitott();
    const indult: string[] = [];
    const a = sor.futtat(() => {
      indult.push('a');
      return elso.p;
    });
    const vezerlo = new AbortController();
    const b = sor.futtat(async () => {
      indult.push('b');
      return 2;
    }, vezerlo.signal);
    const c = sor.futtat(async () => {
      indult.push('c');
      return 3;
    });
    vezerlo.abort();
    await expect(b).rejects.toThrow('megszakítva');
    elso.ok(1);
    expect(await a).toBe(1);
    expect(await c).toBe(3);
    expect(indult).toEqual(['a', 'c']);
  });

  it('a dobó feladat hibája a hívóé, a sor megy tovább', async () => {
    const sor = new KeresSor(1);
    const hibas = sor.futtat(() => Promise.reject(new Error('rossz')));
    const jo = sor.futtat(async () => 5);
    await expect(hibas).rejects.toThrow('rossz');
    expect(await jo).toBe(5);
  });
});
