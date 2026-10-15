import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Fizika } from '../src/lib/graf/fizika';
import { FizikaMotor, type Be, type Ki } from '../src/lib/graf/fizikaMotor';
import { szintetikus } from './graf-segedek';

describe('Fizika', () => {
  it('determinisztikus: ugyanarra a gráfra ugyanaz az elrendezés', () => {
    const g = szintetikus(200, 400);
    const futtat = () => {
      const f = new Fizika(g.n, g.elek, g.poz.slice());
      for (let i = 0; i < 60; i++) f.tick();
      return [...f.helyzetek()];
    };
    expect(futtat()).toEqual(futtat());
  });

  it('lehűl és nyugalomba kerül (kb. 300 tick után), a pozíciók végesek', () => {
    const g = szintetikus(150, 300);
    const f = new Fizika(g.n, g.elek, g.poz.slice());
    expect(f.nyugalomban()).toBe(false);
    let db = 0;
    while (!f.nyugalomban() && db < 5000) {
      f.tick();
      db++;
    }
    expect(f.nyugalomban()).toBe(true);
    expect(db).toBeGreaterThan(250);
    expect(db).toBeLessThan(400);
    expect(f.helyzetek().every(Number.isFinite)).toBe(true);
  });

  it('az élek összehúzzák a szomszédokat: a lánc rövidebb élhosszra áll be, mint a szétszórt kezdet', () => {
    const n = 20;
    const elek = Int32Array.from(Array.from({ length: n - 1 }, (_, i) => [i, i + 1]).flat());
    const poz = new Float32Array(2 * n);
    for (let i = 0; i < n; i++) {
      poz[2 * i] = (i % 5) * 400 - 800;
      poz[2 * i + 1] = Math.floor(i / 5) * 400 - 600;
    }
    const f = new Fizika(n, elek, poz);
    const atlag = (h: Float32Array) => {
      let s = 0;
      for (let i = 0; i < n - 1; i++) s += Math.hypot(h[2 * i] - h[2 * i + 2], h[2 * i + 1] - h[2 * i + 3]);
      return s / (n - 1);
    };
    const elotte = atlag(f.helyzetek());
    for (let i = 0; i < 400; i++) f.tick();
    expect(atlag(f.helyzetek())).toBeLessThan(elotte / 3);
  });

  it('a rejtett (inaktív) csúcs nem mozog és nem hat másokra', () => {
    const g = szintetikus(80, 160);
    const f = new Fizika(g.n, g.elek, g.poz.slice());
    const maszk = new Uint8Array(g.n).fill(1);
    maszk[5] = 0;
    f.aktival(maszk);
    const x0 = f.x[5];
    const y0 = f.y[5];
    for (let i = 0; i < 50; i++) f.tick();
    expect(f.x[5]).toBe(x0);
    expect(f.y[5]).toBe(y0);
  });

  it('a rögzített csúcs ott marad, ahová tették', () => {
    const g = szintetikus(60, 120);
    const f = new Fizika(g.n, g.elek, g.poz.slice());
    f.fx[3] = 111;
    f.fy[3] = -222;
    for (let i = 0; i < 40; i++) f.tick();
    expect(f.x[3]).toBe(111);
    expect(f.y[3]).toBe(-222);
  });

  it('az egybeeső pontok szétválnak (nincs NaN)', () => {
    const n = 30;
    const f = new Fizika(n, new Int32Array(0), new Float32Array(2 * n)); // mind a (0, 0)-n
    for (let i = 0; i < 30; i++) f.tick();
    expect(f.helyzetek().every(Number.isFinite)).toBe(true);
    expect(new Set(Array.from({ length: n }, (_, i) => `${f.x[i]},${f.y[i]}`)).size).toBe(n);
  });

  it('a vault méretén a tick költsége a csúcsok számával közel lineárisan nő (arány, nem falióra)', () => {
    // T008 (2. audit): az abszolút ms-kapu (a 16 ms-os képkocka alatt) a perf-készletben van (tests/perf/graf_fizika.perf.ts,
    // `bin/mos perf`); itt a skálázás: a Barnes–Hut fa O(n log n), egy négyzetes bejárás a kétszeres méretre ~4×-es költséget
    // adna. A két méretet egymás után, ugyanabban a folyamatban, mediánnal mérjük, így a gép pillanatnyi terhelése kiesik.
    const mer = (n: number, m: number) => {
      const g = szintetikus(n, m);
      const f = new Fizika(g.n, g.elek, g.poz.slice());
      for (let i = 0; i < 3; i++) f.tick(); // bemelegítés (JIT)
      const korok = [0, 1, 2, 3, 4].map(() => {
        const t0 = performance.now();
        for (let i = 0; i < 6; i++) f.tick();
        return (performance.now() - t0) / 6;
      });
      return korok.sort((a, b) => a - b)[2];
    };
    const kicsi = mer(1926, 5256);
    const nagy = mer(3852, 10512);
    expect(Number.isFinite(nagy)).toBe(true);
    expect(nagy / kicsi).toBeLessThan(3.4); // lineáris ≈ 2, n·log n ≈ 2,2, négyzetes ≈ 4
  });
});

describe('FizikaMotor: nyugalomban nem számol', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function motor() {
    const kimenet: Ki[] = [];
    const m = new FizikaMotor((k) => kimenet.push(k));
    return { m, kimenet };
  }
  const init = (g: ReturnType<typeof szintetikus>, extra: Partial<Extract<Be, { tipus: 'init' }>> = {}): Be => ({
    tipus: 'init',
    n: g.n,
    elek: g.elek.slice().buffer,
    poz: g.poz.slice().buffer,
    ...extra,
  });

  it('az init előmelegít, jelez, majd időzítővel fut, amíg le nem hűl; utána nincs időzítő', () => {
    const g = szintetikus(100, 200);
    const { m, kimenet } = motor();
    m.kezel(init(g, { elore: 20, elore_ms: 10_000 }));
    expect(kimenet.some((k) => k.tipus === 'kesz')).toBe(true);
    expect(m.tickek).toBe(20);
    expect(m.utemezve).toBe(true);
    vi.advanceTimersByTime(60_000);
    expect(m.utemezve).toBe(false); // lehűlt: nincs több időzítő
    const utolso = [...kimenet].reverse().find((k) => k.tipus === 'poz');
    expect(utolso && utolso.tipus === 'poz' && utolso.fut).toBe(false);
    const tickek = m.tickek;
    vi.advanceTimersByTime(60_000);
    expect(m.tickek).toBe(tickek); // nyugalomban semmi nem számol
  });

  it('szünet leállítja az időzítőt, a folytatás újraindítja', () => {
    const g = szintetikus(100, 200);
    const { m } = motor();
    m.kezel(init(g));
    expect(m.utemezve).toBe(true);
    m.kezel({ tipus: 'szunet' });
    expect(m.utemezve).toBe(false);
    const t = m.tickek;
    vi.advanceTimersByTime(5000);
    expect(m.tickek).toBe(t);
    m.kezel({ tipus: 'folytat' });
    expect(m.utemezve).toBe(true);
  });

  it('a nyugalomban érkező üzenet (húzás, erő, szűrő) felébreszti, és újra lehűl', () => {
    const g = szintetikus(60, 120);
    const { m } = motor();
    m.kezel(init(g));
    vi.advanceTimersByTime(60_000);
    expect(m.utemezve).toBe(false);
    m.kezel({ tipus: 'beall', beall: { taszitas: 2 } });
    expect(m.utemezve).toBe(true);
    vi.advanceTimersByTime(60_000);
    expect(m.utemezve).toBe(false);
    m.kezel({ tipus: 'rogzit', i: 1, x: 5, y: 5, huz: true });
    expect(m.utemezve).toBe(true);
    m.kezel({ tipus: 'enged', i: 1 });
    vi.advanceTimersByTime(60_000);
    expect(m.utemezve).toBe(false);
  });

  it('szünetelő motornál az üzenet nem indít időzítőt', () => {
    const g = szintetikus(40, 80);
    const { m } = motor();
    m.kezel(init(g));
    m.kezel({ tipus: 'szunet' });
    m.kezel({ tipus: 'melegit', alpha: 1 });
    expect(m.utemezve).toBe(false);
  });

  it('a leállítás után nincs időzítő', () => {
    const g = szintetikus(40, 80);
    const { m } = motor();
    m.kezel(init(g));
    m.leallit();
    expect(m.utemezve).toBe(false);
  });
});
