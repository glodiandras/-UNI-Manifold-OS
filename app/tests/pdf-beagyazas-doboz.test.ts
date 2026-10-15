// A beágyazott PDF görgethető lapdoboza (E14): az összes lap függőlegesen, lusta rajzolással (csak a látható és a szomszédos
// lapok), a távoli lap vászna felszabadul; „N / M” lapszám-mező (Enterre ugrik), ‹ ›, kezdő lap a `#page=N`-ből; a dobozon
// belüli kattintás nem vált forrásra (a widget `SAJAT_VEZERLO`-ja); betöltési hibánál érthető üzenet és „Megnyitás”.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const lapHivasok: number[] = [];
let szamLapok = 5;
let nyitHiba: Error | null = null;

vi.mock('../src/media/pdf/dokumentum', () => ({
  nyit: async () => {
    if (nyitHiba) throw nyitHiba;
    return {
      dok: {
        numPages: szamLapok,
        getPage: async (n: number) => ({
          getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 338 * scale }), // 16:9-es PPTX-lap
          render: () => {
            lapHivasok.push(n);
            return { promise: Promise.resolve(), cancel() {} };
          },
          cleanup() {},
        }),
      },
      elenged() {},
    };
  },
}));

import { pdfBeagyazasRenderelo } from '../src/media/pdf/beagyazas';
import type { LinkAdat } from '../src/szerkeszto/linkek/adat';
import { BeagyazasWidget } from '../src/szerkeszto/beagyazas/widget';

class HamisIO {
  static peldanyok: HamisIO[] = [];
  celok = new Set<Element>();
  constructor(
    readonly fv: (b: Array<{ target: Element; isIntersecting: boolean }>) => void,
    readonly opciok?: IntersectionObserverInit,
  ) {
    HamisIO.peldanyok.push(this);
  }
  observe(e: Element) {
    this.celok.add(e);
  }
  disconnect() {
    this.celok.clear();
  }
  unobserve(e: Element) {
    this.celok.delete(e);
  }
  jelez(lathato: (e: Element) => boolean, celok = [...this.celok]) {
    this.fv(celok.map((target) => ({ target, isIntersecting: lathato(target) })));
  }
}
class HamisRO {
  observe() {}
  disconnect() {}
}

const ures = () => new Promise((r) => setTimeout(r, 0));
const link = (alcel: string | null = null, alias: string | null = null): LinkAdat => ({ cel: 'd.pdf', alcel, alias }) as LinkAdat;

async function doboz(alcel: string | null = null, alias: string | null = null) {
  const kont = document.createElement('span');
  document.body.appendChild(kont);
  const ac = new AbortController();
  await pdfBeagyazasRenderelo.render({ tipus: 'pdf', ut: 'K/d.pdf' }, link(alcel, alias), kont, { forras: 'Fő.md', jel: ac.signal });
  const kontIO = HamisIO.peldanyok.at(-1)!;
  kontIO.jelez(() => true); // a doboz láthatóvá vált → betöltés
  await vi.waitFor(() => expect(kont.querySelectorAll('.pdf-be-lapdoboz').length).toBeGreaterThan(0));
  const lapIO = HamisIO.peldanyok.at(-1)!;
  return { kont, ac, lapIO, test: kont.querySelector<HTMLElement>('.pdf-be-test')! };
}

beforeEach(() => {
  HamisIO.peldanyok = [];
  lapHivasok.length = 0;
  szamLapok = 5;
  nyitHiba = null;
  vi.stubGlobal('IntersectionObserver', HamisIO);
  vi.stubGlobal('ResizeObserver', HamisRO);
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.textContent = '';
});

describe('PDF-doboz: görgethető lapok', () => {
  it('az összes lap külön dobozban, a doboz fix magasságú (alap 520 px, a |N méret megmarad)', async () => {
    const a = await doboz();
    expect(a.kont.querySelectorAll('.pdf-be-lapdoboz')).toHaveLength(5);
    expect(a.test.style.height).toBe('520px');
    expect(a.kont.querySelector('.pdf-be-osszes')!.textContent).toBe('/ 5');
    expect(a.kont.querySelector('.beagyazas-cim')!.textContent).toBe('d.pdf');
    const b = await doboz(null, '300');
    expect(b.test.style.height).toBe('300px');
  });

  it('a lapdoboz magassága a PPTX-lap (16:9) arányát követi, nem A4-et', async () => {
    const { kont } = await doboz();
    const d = kont.querySelector<HTMLElement>('.pdf-be-lapdoboz')!;
    expect(parseInt(d.style.height, 10) / parseInt(d.style.width, 10)).toBeCloseTo(338 / 600, 1);
  });

  it('lusta: csak a látható lapok rajzolódnak; a kilépő lap vászna felszabadul', async () => {
    const { kont, lapIO } = await doboz();
    const dobozok = [...kont.querySelectorAll<HTMLElement>('.pdf-be-lapdoboz')];
    expect(lapIO.opciok?.rootMargin).toBeTruthy(); // a szomszédos lapok is
    lapIO.jelez((e) => e === dobozok[0] || e === dobozok[1]);
    await vi.waitFor(() => expect(kont.querySelectorAll('canvas.pdf-be-lap')).toHaveLength(2));
    expect([...lapHivasok].sort()).toEqual([1, 2]);
    const vaszon = dobozok[0].querySelector('canvas')!;
    lapIO.jelez((e) => e === dobozok[1] || e === dobozok[2]); // az 1. kilép, a 3. belép
    await vi.waitFor(() => expect(kont.querySelectorAll('canvas.pdf-be-lap')).toHaveLength(2));
    expect(dobozok[0].querySelector('canvas')).toBeNull();
    expect(vaszon.width).toBe(0); // a bitmap felszabadult
    expect(lapHivasok).toContain(3);
    expect(lapHivasok.filter((n) => n === 2)).toHaveLength(1); // a bent maradó lap nem rajzolódik újra
  });

  it('lapszám-mező: Enterre a lapra ugrik, a határokra szorítva; a ‹ › a szomszédra', async () => {
    const { kont, test } = await doboz();
    const dobozok = [...kont.querySelectorAll<HTMLElement>('.pdf-be-lapdoboz')];
    dobozok.forEach((d, i) => Object.defineProperty(d, 'offsetTop', { value: i * 200, configurable: true }));
    const mezo = kont.querySelector<HTMLInputElement>('.pdf-be-oldal')!;
    mezo.value = '4';
    mezo.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(test.scrollTop).toBe(600);
    mezo.value = '99';
    mezo.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(test.scrollTop).toBe(800);
    const gombok = kont.querySelectorAll<HTMLButtonElement>('button.pdf-be-gomb');
    gombok[0].click(); // ‹
    expect(test.scrollTop).toBe(600);
    expect(mezo.value).toBe('4');
    gombok[1].click(); // ›
    expect(test.scrollTop).toBe(800);
    expect(gombok[1].disabled).toBe(true);
  });

  it('a #page=N a kezdő lap', async () => {
    const { kont, test } = await doboz('page=3');
    expect(kont.querySelector<HTMLInputElement>('.pdf-be-oldal')!.value).toBe('3');
    expect(test.scrollTop).toBeGreaterThanOrEqual(0);
    expect(kont.querySelectorAll('.pdf-be-lapdoboz')).toHaveLength(5);
  });

  it('betöltési hiba: érthető üzenet és „Megnyitás”', async () => {
    nyitHiba = new Error('Hibás PDF');
    const kont = document.createElement('span');
    document.body.appendChild(kont);
    await pdfBeagyazasRenderelo.render({ tipus: 'pdf', ut: 'K/d.pdf' }, link(), kont, { forras: 'Fő.md' });
    HamisIO.peldanyok.at(-1)!.jelez(() => true);
    await vi.waitFor(() => expect(kont.classList.contains('beagyazas-hiba')).toBe(true));
    expect(kont.textContent).toContain('A PDF nem tölthető be: Hibás PDF');
    expect(kont.querySelector('button')!.textContent).toBe('Megnyitás');
  });

  it('lezárás (abort) után nem rajzol és nem szivárog', async () => {
    const { kont, ac, lapIO } = await doboz();
    ac.abort();
    expect(lapIO.celok.size).toBe(0);
    await ures();
    expect(kont.querySelectorAll('canvas')).toHaveLength(0);
  });
});

describe('PDF-doboz a Live Preview widgetben', () => {
  function widget() {
    const view = {
      state: { readOnly: false, doc: { length: 100 } },
      posAtDOM: () => 7,
      dispatch: vi.fn(),
      focus: vi.fn(),
      requestMeasure: vi.fn(),
    };
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ tipus: 'nincs', cel: 'x' }), { headers: { 'Content-Type': 'application/json' } }));
    const w = new BeagyazasWidget({ cel: 'd.pdf', alcel: null, alias: null } as LinkAdat, 'Fő.md', 1, true);
    const kont = w.toDOM(view as never);
    document.body.appendChild(kont);
    return { view, kont };
  }

  it('a dobozon belüli kattintás (lap, fejléc, görgetősáv) nem vált forrásra; a doboz melletti igen', () => {
    const { view, kont } = widget();
    const nezo = document.createElement('span');
    nezo.className = 'beagyazas beagyazas-pdf-nezo';
    const test = document.createElement('div');
    test.className = 'pdf-be-test';
    const lap = document.createElement('canvas');
    test.appendChild(lap);
    nezo.appendChild(test);
    kont.appendChild(nezo);
    for (const cel of [lap, test, nezo]) cel.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
    expect(view.dispatch).not.toHaveBeenCalled();
    kont.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
    expect(view.dispatch).toHaveBeenCalledTimes(1);
  });
});
