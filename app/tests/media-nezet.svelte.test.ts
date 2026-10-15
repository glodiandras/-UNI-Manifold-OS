// C16: a lejátszó és a PDF-fül kötései jsdom-ban, ál-core-ral és ál-pdf.js-szel: a horgony a pontos helyen nyit és
// elfogy, a tartós állapot a fül `nezet`-jébe kerül, az átirat mondata ugrik, a billentyűk, a keresés eseménye, a
// lapozás. A valódi megjelenést (WKWebView, Range, kodekek) a kézi lista méri; ez a komponens kötéseit védi.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import type { Ful } from '../src/lib/elrendezes/munkaterulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { mediaNezetek } from '../src/media/aktiv.svelte';
import Lejatszo from '../src/media/Lejatszo.svelte';
import PdfFul from '../src/media/pdf/PdfFul.svelte';

// ---------------------------------------------------------------- ál-pdf.js

const esemenyek: { nev: string; adat: unknown }[] = [];
let utolsoNezo: AlNezo | null = null;

class AlBusz {
  private f = new Map<string, ((e: unknown) => void)[]>();
  on(n: string, fn: (e: unknown) => void) {
    this.f.set(n, [...(this.f.get(n) ?? []), fn]);
  }
  dispatch(n: string, e: unknown = {}) {
    esemenyek.push({ nev: n, adat: e });
    for (const fn of this.f.get(n) ?? []) fn(e);
  }
}

class AlNezo {
  eventBus: AlBusz;
  private oldal = 1;
  currentScale = 1;
  private ertek = 'auto';
  constructor(o: { eventBus: AlBusz }) {
    this.eventBus = o.eventBus;
    utolsoNezo = this;
  }
  get currentPageNumber() {
    return this.oldal;
  }
  set currentPageNumber(n: number) {
    this.oldal = n;
    this.eventBus.dispatch('pagechanging', { pageNumber: n });
  }
  get currentScaleValue() {
    return this.ertek;
  }
  set currentScaleValue(v: string) {
    this.ertek = v;
    this.eventBus.dispatch('scalechanging', { scale: 1.25, presetValue: v });
  }
  setDocument(d: unknown) {
    if (d) queueMicrotask(() => this.eventBus.dispatch('pagesinit'));
  }
  cleanup() {}
}

vi.mock('../src/media/pdf/pdfjs', () => ({
  pdfjs: async () => ({
    lib: { AnnotationMode: { ENABLE: 2 }, AnnotationEditorType: { DISABLE: -1 } },
    viewer: {
      EventBus: AlBusz,
      PDFLinkService: class {
        externalLinkEnabled = true;
        setViewer() {}
        setDocument() {}
      },
      PDFFindController: class {},
      PDFViewer: AlNezo,
    },
  }),
  BETOLTES: {},
}));

const elengedve = vi.fn();
vi.mock('../src/media/pdf/dokumentum', () => ({
  nyit: async () => ({ dok: { numPages: 20, getPage: async () => ({}) }, elenged: elengedve }),
  ervenytelenit: () => {},
}));

// ---------------------------------------------------------------- ál-core

const valasz = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

const ATIRAT = {
  ut: 'ATTCHMNTS - Videos/A Nyugat.mp4',
  vtt: 'I23/Média/A Nyugat.hu.vtt',
  nyelv: 'hu',
  gepi: true,
  leiro: 'I23/Média/A Nyugat.md',
  cuek: [
    { k: 1, v: 18, szoveg: 'Mi jut eszedbe?' },
    { k: 18, v: 22, szoveg: 'Először az égtáj.' },
    { k: 760, v: 770, szoveg: 'A folyóirat címe' },
  ],
  figyelmeztetes: null,
};

beforeEach(() => {
  esemenyek.length = 0;
  utolsoNezo = null;
  elengedve.mockClear();
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname === '/api/allapot') return valasz({ media_token: 'tok' });
    if (u.pathname === '/api/media/atirat') return valasz(ATIRAT);
    if (u.pathname === '/api/pdf/kiemelesek') return valasz({ pdf: u.searchParams.get('ut'), fajl: null, hash: null, kiemelesek: [] });
    return valasz({});
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function kornyezet() {
  return new Map([[KORNYEZET_KULCS, { felulet: new Felulet({}), fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }]]);
}

// ---------------------------------------------------------------- lejátszó

describe('lejátszó', () => {
  function nyit(nezet: Record<string, unknown>) {
    const ful = $state<Ful>({ id: 'v1', ut: ATIRAT.ut, nezet });
    const c = render(Lejatszo, { props: { ful, info: undefined, aktiv: true }, context: kornyezet() });
    return { c, ful };
  }

  async function betolt(c: { container: HTMLElement }, hossz = 900) {
    const v = await waitFor(() => {
      const x = c.container.querySelector('video');
      if (!x?.getAttribute('src')) throw new Error('nincs src');
      return x as HTMLVideoElement;
    });
    Object.defineProperty(v, 'duration', { configurable: true, value: hossz });
    v.pause = vi.fn();
    v.play = vi.fn(async () => {});
    await fireEvent(v, new Event('loadedmetadata'));
    return v;
  }

  it('a `t=12:40` horgony a pontos helyen nyit és elfogy; a média URL tokenes, `controls` nélkül', async () => {
    const { c, ful } = nyit({ horgony: 't=12:40', sebesseg: 1.5 });
    const v = await betolt(c);
    expect(v.getAttribute('src')).toBe('/media/tok/ATTCHMNTS%20-%20Videos/A%20Nyugat.mp4');
    expect(v.controls).toBe(false);
    expect(v.currentTime).toBe(760);
    expect(v.playbackRate).toBe(1.5);
    expect(ful.nezet?.horgony).toBeUndefined();
    expect(mediaNezetek.cel('lejatszo')?.ut).toBe(ATIRAT.ut);
  });

  it('a lejátszás állapota a regiszterben (az aktív idő bevitele, 38. döntés): play → játszik, pause → nem, bezárás → nem', async () => {
    const { c } = nyit({});
    const v = await betolt(c);
    expect(mediaNezetek.jatszikUt(ATIRAT.ut)).toBe(false);
    await fireEvent(v, new Event('play'));
    await waitFor(() => expect(mediaNezetek.jatszikUt(ATIRAT.ut)).toBe(true));
    expect(mediaNezetek.jatszikUt('Mas.mp4')).toBe(false);
    await fireEvent(v, new Event('pause'));
    await waitFor(() => expect(mediaNezetek.jatszikUt(ATIRAT.ut)).toBe(false));
    await fireEvent(v, new Event('play'));
    await waitFor(() => expect(mediaNezetek.jatszikUt(ATIRAT.ut)).toBe(true));
    c.unmount();
    expect(mediaNezetek.jatszikUt(ATIRAT.ut)).toBe(false); // a bezárt lejátszó nem „játszik”
  });

  it('az átirat: gépi jelölés, a mondat kattintásra ugrik és indít; az aktív mondat kiemelve', async () => {
    const { c } = nyit({});
    const v = await betolt(c);
    const gombok = await waitFor(() => {
      const g = c.container.querySelectorAll<HTMLButtonElement>('.mondatok button');
      if (g.length !== 3) throw new Error('nincs átirat');
      return g;
    });
    expect(c.container.querySelector('.atirat-jel')?.textContent).toBe('gépi · hu');
    await fireEvent.click(gombok[1]);
    expect(v.currentTime).toBe(18);
    expect(v.play).toHaveBeenCalled();
    await fireEvent(v, new Event('timeupdate'));
    await waitFor(() => expect(c.container.querySelector('.mondatok li.aktiv')?.textContent).toContain('Először'));
  });

  it('billentyűk: L előre, J vissza, ⇧> gyorsabb; a tartós állapot a fül nézetébe kerül', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { c, ful } = nyit({});
      const v = await betolt(c);
      const cikk = c.container.querySelector('article')!;
      v.currentTime = 100;
      await fireEvent(v, new Event('timeupdate'));
      await fireEvent.keyDown(cikk, { key: 'l' });
      expect(v.currentTime).toBe(110);
      await fireEvent.keyDown(cikk, { key: 'j' });
      await fireEvent.keyDown(cikk, { key: 'j' });
      expect(v.currentTime).toBe(90);
      await fireEvent.keyDown(cikk, { key: '>' });
      expect(v.playbackRate).toBe(1.25);
      vi.advanceTimersByTime(3500);
      expect(ful.nezet).toMatchObject({ pozicio: 90, sebesseg: 1.25, felirat: false });
    } finally {
      vi.useRealTimers();
    }
  });

  it('a nem lejátszható formátum magyar hibát ad', async () => {
    const { c } = nyit({});
    const v = await betolt(c);
    Object.defineProperty(v, 'error', { configurable: true, value: { code: 4, message: '' } });
    await fireEvent(v, new Event('error'));
    expect(c.container.querySelector('.hiba')?.textContent).toContain('nem tudja lejátszani');
  });
});

// ---------------------------------------------------------------- PDF

describe('PDF-fül', () => {
  const PDF = 'Mx - Tankönyvek/10 - Matematika.pdf';

  function nyit(nezet: Record<string, unknown>) {
    const ful = $state<Ful>({ id: 'p1', ut: PDF, nezet });
    const c = render(PdfFul, { props: { ful, info: undefined, aktiv: true }, context: kornyezet() });
    return { c, ful };
  }

  it('a `page=7` horgony a 7. lapon nyit és elfogy; a mentett nagyítás visszaáll', async () => {
    const { c, ful } = nyit({ horgony: 'page=7', nagyitas: 'page-fit' });
    await waitFor(() => expect(utolsoNezo?.currentPageNumber).toBe(7));
    expect(utolsoNezo?.currentScaleValue).toBe('page-fit');
    expect(ful.nezet?.horgony).toBeUndefined();
    const mezo = c.container.querySelector<HTMLInputElement>('.oldal input')!;
    expect(mezo.value).toBe('7');
    expect(c.container.querySelector('.osszes')?.textContent).toBe('/ 20');
  });

  it('a már nyitott fülre érkező új horgony lapoz; a lap mezője ugrik; az állapot a nézetbe kerül', async () => {
    const { c, ful } = nyit({ oldal: 3 });
    await waitFor(() => expect(utolsoNezo?.currentPageNumber).toBe(3));
    ful.nezet = { ...ful.nezet, horgony: 'page=12' };
    await waitFor(() => expect(utolsoNezo?.currentPageNumber).toBe(12));
    const mezo = c.container.querySelector<HTMLInputElement>('.oldal input')!;
    await fireEvent.input(mezo, { target: { value: '99' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    expect(utolsoNezo?.currentPageNumber).toBe(20); // a lapszámra vágva
    await waitFor(() => expect(ful.nezet).toMatchObject({ oldal: 20 }), { timeout: 2000 });
  });

  it('keresés: a mező a pdf.js `find` eseményét küldi (ékezetfüggetlenül), ↩ a következőre lép', async () => {
    const { c } = nyit({});
    await waitFor(() => expect(utolsoNezo).not.toBeNull());
    await waitFor(() => expect(c.container.querySelector<HTMLButtonElement>('[aria-label="Keresés a PDF-ben"]')?.disabled).toBe(false));
    await fireEvent.click(c.container.querySelector<HTMLButtonElement>('[aria-label="Keresés a PDF-ben"]')!);
    const mezo = await waitFor(() => {
      const m = c.container.querySelector<HTMLInputElement>('.keresosav input');
      if (!m) throw new Error('nincs keresőmező');
      return m;
    });
    await fireEvent.input(mezo, { target: { value: 'függvény' } });
    await waitFor(() => expect(esemenyek.some((e) => e.nev === 'find' && (e.adat as { query: string }).query === 'függvény')).toBe(true), { timeout: 1000 });
    const find = esemenyek.find((e) => e.nev === 'find')!.adat as Record<string, unknown>;
    expect(find).toMatchObject({ matchDiacritics: false, caseSensitive: false, highlightAll: true, type: '' });
    await fireEvent.keyDown(mezo, { key: 'Enter', shiftKey: true });
    expect(esemenyek.at(-1)?.adat).toMatchObject({ type: 'again', findPrevious: true });
    await fireEvent.keyDown(mezo, { key: 'Escape' });
    expect(esemenyek.at(-1)?.nev).toBe('findbarclose');
  });

  it('a fül bezárásakor a dokumentum elengedődik', async () => {
    const { c } = nyit({});
    await waitFor(() => expect(utolsoNezo).not.toBeNull());
    c.unmount();
    expect(elengedve).toHaveBeenCalledTimes(1);
    expect(mediaNezetek.cel('pdf', true)).toBeNull();
  });
});
