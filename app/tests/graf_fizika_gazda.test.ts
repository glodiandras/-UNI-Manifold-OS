// C33 (T068, A2-nezetek-2): a Worker menet közbeni hibája után a gazda a fő szálra vált és ugyanannak a motornak küldi újra
// az utolsó initet — nincs új Worker, nincs újraindítási hurok. Ál-Workerrel (a jsdom-ban nincs valódi Worker).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FizikaGazda } from '../src/lib/graf/fizikaGazda';
import type { Be, Ki } from '../src/lib/graf/fizikaMotor';
import { szintetikus } from './graf-segedek';

class AlWorker {
  static peldanyok: AlWorker[] = [];
  onmessage: ((ev: MessageEvent<Ki>) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  kapott: Be[] = [];
  leallitva = false;
  constructor() {
    AlWorker.peldanyok.push(this);
  }
  postMessage(d: Be, atad?: Transferable[]) {
    this.kapott.push(d);
    // a valódi postMessage leválasztja az átadott puffereket: a gazdának másolatot kell őriznie
    for (const t of atad ?? []) if (t instanceof ArrayBuffer) structuredClone(t, { transfer: [t] });
  }
  terminate() {
    this.leallitva = true;
  }
  hiba() {
    this.onerror?.({});
  }
  valasz(m: Ki) {
    this.onmessage?.({ data: m } as MessageEvent<Ki>);
  }
}

function initUzenet(n = 40, m = 80): Be {
  const g = szintetikus(n, m);
  return { tipus: 'init', n: g.n, elek: g.elek.slice().buffer, poz: g.poz.slice().buffer as ArrayBuffer, alpha: 1, elore: 5 };
}

describe('FizikaGazda: a Worker hibája (T068)', () => {
  beforeEach(() => {
    AlWorker.peldanyok = [];
    vi.stubGlobal('Worker', AlWorker);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('a hiba után a fő szálon fut tovább, új Worker nélkül (nincs hurok)', () => {
    const kapott: Ki[] = [];
    const g = new FizikaGazda((m) => kapott.push(m));
    expect(g.workerben).toBe(true);
    g.kuld(initUzenet());
    expect(AlWorker.peldanyok).toHaveLength(1);
    const w = AlWorker.peldanyok[0];
    w.hiba();
    expect(w.leallitva).toBe(true);
    expect(g.workerben).toBe(false);
    expect(g.foszalraValtas).toBe(1);
    // ugyanannak a motornak ment az init: a fő szálú motor jelentett (kesz + poz), és nem indult új Worker
    expect(kapott.some((m) => m.tipus === 'kesz')).toBe(true);
    expect(kapott.some((m) => m.tipus === 'poz')).toBe(true);
    vi.advanceTimersByTime(5000);
    expect(AlWorker.peldanyok).toHaveLength(1);
    // egy újabb (késő) hibajel sem indít semmit
    w.hiba();
    expect(AlWorker.peldanyok).toHaveLength(1);
    expect(g.foszalraValtas).toBe(1);
    g.leallit();
  });

  it('a Worker utolsó helyzeteiről folytat, és a szünet megmarad (nem számol a háttérben)', () => {
    const kapott: Ki[] = [];
    const g = new FizikaGazda((m) => kapott.push(m));
    const init = initUzenet(30, 50);
    g.kuld(init);
    g.kuld({ tipus: 'szunet' });
    const w = AlWorker.peldanyok[0];
    const poz = new Float32Array(60).map((_, i) => i * 10);
    w.valasz({ tipus: 'poz', poz, alpha: 0, fut: false });
    kapott.length = 0;
    w.hiba();
    const pozUzenet = kapott.find((m) => m.tipus === 'poz') as Extract<Ki, { tipus: 'poz' }>;
    expect(pozUzenet).toBeTruthy();
    expect(Array.from(pozUzenet.poz)).toEqual(Array.from(poz));
    // szünetel: nincs ütemezett tick
    const elotte = kapott.length;
    vi.advanceTimersByTime(2000);
    expect(kapott.length).toBe(elotte);
    g.leallit();
  });

  it('a hiba előtt küldött beállítás és maszk az újraküldött initbe olvad (a nyugvó gráfot nem melegíti fel)', () => {
    const kapott: Ki[] = [];
    const g = new FizikaGazda((m) => kapott.push(m));
    const init = initUzenet(20, 30);
    g.kuld({ ...init, alpha: 0, elore: 0 } as Be);
    const maszk = new Uint8Array(20).fill(1);
    maszk[3] = 0;
    g.kuld({ tipus: 'aktiv', maszk: maszk.buffer, alpha: 0 });
    g.kuld({ tipus: 'beall', beall: { taszitas: 3 } as never });
    kapott.length = 0;
    AlWorker.peldanyok[0].hiba();
    const poz = kapott.find((m) => m.tipus === 'poz') as Extract<Ki, { tipus: 'poz' }>;
    expect(poz.alpha).toBe(0);
    expect(poz.fut).toBe(false);
    g.leallit();
  });

  it('a leállított gazda hibajele nem indít motort', () => {
    const kapott: Ki[] = [];
    const g = new FizikaGazda((m) => kapott.push(m));
    g.kuld(initUzenet());
    g.leallit();
    AlWorker.peldanyok[0].hiba();
    expect(kapott).toHaveLength(0);
    expect(g.foszalraValtas).toBe(0);
  });
});
