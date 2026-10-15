// A CAS-jellemzők kliense (C35a): gyorsítótár, az azonos kérés egy átfutása, megszakítás, a hiba csendes lefokozása
// (a rajz jelölések nélkül is él), az elemzési ablak kiterjesztése, a pontos értékek olvasható szövege.

import { describe, expect, it } from 'vitest';
import {
  JellemzoKliens,
  kiterjeszt,
  szam,
  szepSzoveg,
  type Jellemzok,
} from '../src/szerkeszto/renderelok/plot/jellemzok';

const ok = (kif: string): Jellemzok & { kif: string } => ({
  kif,
  allapot: 'ok',
  zerushelyek: [{ x: '0', ertek: 0 }],
  szelsoertekek: [],
  aszimptotak: [],
  ferde_aszimptotak: [],
  numerikus: false,
  figyelmeztetesek: [],
});

function kliens(valasz?: (torzs: { fuggvenyek: string[]; ablak: number[] }) => unknown) {
  const hivasok: { fuggvenyek: string[]; ablak: number[] }[] = [];
  let ido = 1000;
  const k = new JellemzoKliens(
    async (ut, o) => {
      expect(ut).toBe('/api/grafikon/elemzes');
      expect(o?.metodus).toBe('POST');
      const torzs = o!.torzs as { fuggvenyek: string[]; ablak: number[] };
      hivasok.push(torzs);
      if (valasz) return valasz(torzs);
      return { ok: true, fuggvenyek: torzs.fuggvenyek.map(ok) };
    },
    () => ido,
  );
  return { k, hivasok, ora: (t: number) => (ido += t) };
}

describe('kérés', () => {
  it('a válasz a kifejezésekhez igazítva', async () => {
    const { k, hivasok } = kliens();
    const r = await k.kerd(['x^2', '1/x'], [-3, 3]);
    expect(r).toHaveLength(2);
    expect(r![0]!.zerushelyek[0].x).toBe('0');
    expect(hivasok).toEqual([{ fuggvenyek: ['x^2', '1/x'], ablak: [-3, 3] }]);
  });

  it('a második azonos kérés a gyorsítótárból jön', async () => {
    const { k, hivasok } = kliens();
    await k.kerd(['x^2'], [-3, 3]);
    await k.kerd(['x^2'], [-3, 3]);
    expect(hivasok).toHaveLength(1);
  });

  it('kifejezésenként gyorsítótáraz: csak a hiányzót kéri', async () => {
    const { k, hivasok } = kliens();
    await k.kerd(['x^2'], [-3, 3]);
    const r = await k.kerd(['x^2', 'x^3'], [-3, 3]);
    expect(hivasok.at(-1)!.fuggvenyek).toEqual(['x^3']);
    expect(r!.map((x) => x?.zerushelyek.length)).toEqual([1, 1]);
  });

  it('más ablak új kérés', async () => {
    const { k, hivasok } = kliens();
    await k.kerd(['x^2'], [-3, 3]);
    await k.kerd(['x^2'], [-6, 6]);
    expect(hivasok).toHaveLength(2);
  });

  it('az egyidejű azonos kérés egyszer megy', async () => {
    const { k, hivasok } = kliens();
    const [a, b] = await Promise.all([k.kerd(['x^2'], [-3, 3]), k.kerd(['x^2'], [-3, 3])]);
    expect(hivasok).toHaveLength(1);
    expect(a).toEqual(b);
  });
});

describe('hibák: csendes lefokozás', () => {
  it('a hálózati és a 503-as hiba `null`, nem dob', async () => {
    const k = new JellemzoKliens(async () => {
      throw new Error('503');
    });
    expect(await k.kerd(['x'], [-1, 1])).toBeNull();
  });

  it('a hibát nem tartja örökre: rövid várakozás után újra próbál', async () => {
    let n = 0;
    let ido = 0;
    const k = new JellemzoKliens(
      async (_ut, o) => {
        n++;
        if (n === 1) throw new Error('503');
        return { ok: true, fuggvenyek: (o!.torzs as { fuggvenyek: string[] }).fuggvenyek.map(ok) };
      },
      () => ido,
    );
    expect(await k.kerd(['x'], [-1, 1])).toBeNull();
    expect(await k.kerd(['x'], [-1, 1])).toBeNull(); // még a „hűtés” alatt: nem kér újra
    expect(n).toBe(1);
    ido += 20_000;
    expect(await k.kerd(['x'], [-1, 1])).not.toBeNull();
    expect(n).toBe(2);
  });

  it('a hibás válasz-alak `null`', async () => {
    for (const v of [null, {}, { fuggvenyek: 'x' }, { fuggvenyek: [] }, 7]) {
      const k = new JellemzoKliens(async () => v);
      expect(await k.kerd(['x'], [-1, 1])).toBeNull();
    }
  });

  it('a tételenkénti nem-`ok` állapot is átjön (a rajzoló kihagyja)', async () => {
    const { k } = kliens((t) => ({
      ok: true,
      fuggvenyek: t.fuggvenyek.map((f) => (f === 'x' ? ok(f) : { kif: f, allapot: 'hiba', uzenet: 'x' })),
    }));
    const r = await k.kerd(['x', 'y+1'], [-1, 1]);
    expect(r![0]!.allapot).toBe('ok');
    expect(r![1]!.allapot).toBe('hiba');
  });
});

describe('megszakítás', () => {
  it('a megszakított kérés AbortError, de a lekérés a gyorsítótárba fut', async () => {
    const { k, hivasok } = kliens();
    const v = new AbortController();
    const p = k.kerd(['x^2'], [-3, 3], v.signal);
    v.abort();
    await expect(p).rejects.toMatchObject({ name: 'AbortError' });
    await k.kerd(['x^2'], [-3, 3]);
    expect(hivasok).toHaveLength(1);
  });

  it('már megszakított jel azonnal AbortError, kérés nélkül', async () => {
    const { k, hivasok } = kliens();
    const v = new AbortController();
    v.abort();
    await expect(k.kerd(['x^2'], [-3, 3], v.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(hivasok).toHaveLength(0);
  });
});

describe('kiterjeszt', () => {
  it('a látható ablak két oldalán egy-egy szélességgel nagyobb, szép lépcsőre kerekítve', () => {
    const [lo, hi] = kiterjeszt(-5, 5);
    expect(lo).toBeLessThanOrEqual(-15);
    expect(hi).toBeGreaterThanOrEqual(15);
    expect(lo).toBeGreaterThanOrEqual(-20);
    expect(hi).toBeLessThanOrEqual(20);
    expect(Number.isInteger(lo) && Number.isInteger(hi)).toBe(true);
  });
  it('a kis ablak is szép számokra kerekít, és tartalmazza az eredetit', () => {
    const [lo, hi] = kiterjeszt(0.123, 0.456);
    expect(lo).toBeLessThanOrEqual(0.123 - 0.333);
    expect(hi).toBeGreaterThanOrEqual(0.456 + 0.333);
    expect(String(lo)).not.toMatch(/\d{8,}/);
  });
  it('a kis mozgatás ugyanazt az ablakot adja (a gyorsítótár működjön)', () => {
    expect(kiterjeszt(-5.1, 4.9)).toEqual(kiterjeszt(-5, 5));
  });
});

describe('olvasható szöveg', () => {
  it('a pontos értékek: π, √, szorzás, mínusz', () => {
    expect(szepSzoveg('pi/4')).toBe('π/4');
    expect(szepSzoveg('3*pi/2')).toBe('3π/2');
    expect(szepSzoveg('2*pi')).toBe('2π');
    expect(szepSzoveg('sqrt(3)')).toBe('√3');
    expect(szepSzoveg('-sqrt(3)')).toBe('−√3');
    expect(szepSzoveg('2*sqrt(2)')).toBe('2√2');
    expect(szepSzoveg('sqrt(2*x)')).toBe('√(2·x)');
    expect(szepSzoveg('x**2 + 1')).toBe('x^2 + 1');
    expect(szepSzoveg('-1/2')).toBe('−1/2');
  });
  it('az egyenletek: x=…, y=…', () => {
    expect(szepSzoveg('x=-pi/2')).toBe('x=−π/2');
    expect(szepSzoveg('y=sqrt(3)*x')).toBe('y=√3·x');
  });
  it('a szám: magyar tizedesvessző, legfeljebb 4 értékes jegy, mínusz jellel', () => {
    expect(szam(0.739085133)).toBe('0,7391');
    expect(szam(-1.5)).toBe('−1,5');
    expect(szam(1234.5678)).toBe('1235');
    expect(szam(0)).toBe('0');
    expect(szam(2)).toBe('2');
  });
});
