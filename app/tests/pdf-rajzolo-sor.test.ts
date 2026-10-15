// A beágyazott PDF sorba rendezett rajzolása (C32, T067): gyors lapozásnál vagy átméretezésnél egy vászonra egyszerre
// legfeljebb egy render() fut; az új kérés megszakítja a futót, a közben elavult kérés ki sem indul, és a megszakítás
// (`RenderingCancelledException`) nem hiba.

import { describe, expect, it } from 'vitest';
import { megszakitva, rajzoloSor, type RajzolasTarto } from '../src/media/pdf/beagyazas';

function hamisFeladat() {
  let elutasit!: (e: unknown) => void;
  let teljesit!: () => void;
  const promise = new Promise<void>((t, e) => {
    teljesit = t;
    elutasit = e;
  });
  const f = {
    promise,
    megszakitva: false,
    teljesit,
    cancel() {
      f.megszakitva = true;
      elutasit(Object.assign(new Error('Rendering cancelled'), { name: 'RenderingCancelledException' }));
    },
  };
  return f;
}

const ures = () => new Promise((r) => setTimeout(r, 0));

describe('rajzoloSor', () => {
  it('egyszerre egy rajzolás fut; az új kérés megszakítja a futót, a közbülső ki sem indul', async () => {
    let egyszerre = 0;
    let csucs = 0;
    const indult: number[] = [];
    const feladatok: ReturnType<typeof hamisFeladat>[] = [];
    const hibak: unknown[] = [];
    const sor = rajzoloSor(async (sajat: number, tarto: RajzolasTarto) => {
      indult.push(sajat);
      egyszerre++;
      csucs = Math.max(csucs, egyszerre);
      const f = hamisFeladat();
      feladatok.push(f);
      tarto.feladat = f;
      try {
        await f.promise;
      } catch (e) {
        if (!megszakitva(e)) hibak.push(e);
      } finally {
        egyszerre--;
        if (tarto.feladat === f) tarto.feladat = null;
      }
    });
    const elso = sor.kerj();
    await ures();
    expect(indult).toEqual([1]);
    void sor.kerj(); // 2: elavul, mielőtt sorra kerülne
    const utolso = sor.kerj(); // 3
    expect(feladatok[0].megszakitva).toBe(true);
    await elso;
    await ures();
    expect(indult).toEqual([1, 3]);
    feladatok[1].teljesit();
    await utolso;
    expect(csucs).toBe(1);
    expect(hibak).toEqual([]);
  });

  it('a megszakit() a futót leállítja, és utána a lánc nem indít újat', async () => {
    const indult: number[] = [];
    let f: ReturnType<typeof hamisFeladat> | null = null;
    const sor = rajzoloSor(async (sajat, tarto) => {
      indult.push(sajat);
      f = hamisFeladat();
      tarto.feladat = f;
      await f.promise.catch(() => undefined);
    });
    const p = sor.kerj();
    await ures();
    sor.megszakit();
    await p;
    expect(f!.megszakitva).toBe(true);
    expect(indult).toEqual([1]);
  });

  it('a RenderingCancelledException nem hiba, más hiba igen', () => {
    expect(megszakitva(Object.assign(new Error('x'), { name: 'RenderingCancelledException' }))).toBe(true);
    expect(megszakitva(new Error('Cannot use the same canvas'))).toBe(false);
    expect(megszakitva(null)).toBe(false);
  });
});
