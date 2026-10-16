// F11 (8. tétel): a közös ProbaJel (ikon + „Trial”) kötése a Kérdezz, a Dolgozat és a képlet-OCR meglévő próba-jelzései helyére: ugyanaz
// a komponens (azonos jel, ikon, szó, leírás), a mellette álló szövegek változatlanok; nem próba esetén nincs jel.
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Dolgozat from '../src/dolgozat/Dolgozat.svelte';
import { dolgozatAdat } from '../src/dolgozat/modell.svelte';
import Ertesitesek from '../src/hej/Ertesitesek.svelte';
import Kerdezz from '../src/hej/vezerlo/Kerdezz.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { nyelv } from '../src/lib/i18n';
import { kerdezzAllapot } from '../src/lib/kereses/kerdezz.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { kepletOcr } from '../src/szerkeszto/kepletOcr';
import { T1, T2, T3, ertekeles, json, kalibracio, lista, reszlet, tema } from './dolgozat-fixture';

const context = () => new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet: new Felulet({}), fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);

/** A jel egységes alakja: ikon (svg) + szó + a komponens leírása (title). */
function jelek(gyoker: ParentNode) {
  return [...gyoker.querySelectorAll<HTMLElement>('[data-jel="proba"]')].map((e) => ({ szo: e.textContent?.trim(), svg: !!e.querySelector('svg'), title: e.getAttribute('title') }));
}
const EGYSEGES = { szo: 'Trial', svg: true, title: expect.stringMatching(/calibrated/i) };

beforeEach(() => nyelv.beallit('en'));
afterEach(() => {
  cleanup();
  nyelv.beallit('hu');
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  ertesitesek.lista = [];
  Object.assign(kerdezzAllapot, { vege: null, mondatok: [], forrasok: [], hiba: null });
});

describe('Kérdezz', () => {
  it('próba-válasznál a közös jel áll a változatlan szöveg előtt; kalibrált válasznál nincs jel', () => {
    kerdezzAllapot.vege = { allapot: 'kesz', ok: null, mondatok: 1, elvetve: {}, proba: true } as never;
    const c = render(Kerdezz, { context: context() });
    expect(jelek(c.container)).toEqual([EGYSEGES]);
    const sor = c.container.querySelector('.proba-sor')!;
    expect(sor.textContent).toContain('Trial: the model is not calibrated for this task.');
    c.unmount();
    kerdezzAllapot.vege = { allapot: 'kesz', ok: null, mondatok: 1, elvetve: {}, proba: false } as never;
    const d = render(Kerdezz, { context: context() });
    expect(jelek(d.container)).toEqual([]);
    expect(d.container.textContent).not.toContain('not calibrated');
  });
});

describe('Dolgozat szöveges értékelése', () => {
  async function ertekeljProbaval(proba: boolean) {
    const r = reszlet({
      szam: 0.62, kilatas: 0.55, szint: 'kozepes', lefedettseg: { van: 2, osszes: 3 }, ertekeles_kulcs: 'kulcs-1',
      temak: [tema(T1, '01 - Hatvány', 0.82), tema(T2, '02 - Gyökvonás', 0.41), tema(T3, '03 - Logaritmus', null)],
    });
    vi.stubGlobal('fetch', async (url: string) => {
      if (url.includes('/ertekeles')) return json(ertekeles({ proba, kalibralt: !proba, modell: 'qwen35_4b' }));
      if (url.includes('/kalibracio')) return json(kalibracio());
      return url.includes('/dolgozat?') ? json(r) : json(lista());
    });
    Object.assign(dolgozatAdat, { lista: null, reszlet: null, valasztott: null, hiba: null, reszletHiba: null, betoltve: false, ertekeles: null, ertekelesFut: false, ertekelesHiba: null, kalibracio: null, kalibracioHiba: null, kalibracioTolt: false });
    dolgozatAdat.utemez();
    await dolgozatAdat.frissit();
    const c = render(Dolgozat, { context: context(), props: { ful: { id: 'f1', ut: null, nezet: { tipus: 'dolgozat' } }, info: undefined, aktiv: true } });
    const s = screen.getByRole('region', { name: 'Written evaluation' });
    await fireEvent.click(within(s).getByRole('button', { name: 'Request evaluation' }));
    await vi.waitFor(() => expect(s.querySelector('.ertekeles-szoveg')).not.toBeNull());
    return { c, s };
  }

  it('próba-értékelésnél a közös jel áll a változatlan mondat előtt', async () => {
    const { s } = await ertekeljProbaval(true);
    expect(jelek(s)).toEqual([EGYSEGES]);
    expect(within(s).getByText(/Trial: the model \(qwen35_4b\) is not calibrated for this task/)).toBeTruthy();
  });

  it('kalibrált értékelésnél nincs próba-jel', async () => {
    const { s } = await ertekeljProbaval(false);
    expect(jelek(s)).toEqual([]);
    expect(within(s).getByText(/Calibrated local model \(qwen35_4b\)/)).toBeTruthy();
  });
});

describe('képlet-OCR', () => {
  const nezet = () => new EditorView({ state: EditorState.create({ doc: 'a b', selection: { anchor: 1 } }) });

  it('próba-modellnél az értesítés a közös jelet viseli (a szövegek változatlanok); kalibrált modellnél nem', async () => {
    const v = nezet();
    await kepletOcr(v, (async () => ({ latex: 'x^2', modell: 'glm_ocr', proba: true })) as never);
    const c = render(Ertesitesek);
    expect(jelek(c.container)).toEqual([EGYSEGES]);
    expect(c.container.textContent).toContain('Formula inserted — with a trial model');
    expect(c.container.textContent).toContain('glm_ocr: not calibrated, please check it.');
    c.unmount();
    ertesitesek.lista = [];

    await kepletOcr(v, (async () => ({ latex: 'y', modell: 'glm_ocr', proba: false })) as never);
    const d = render(Ertesitesek);
    expect(jelek(d.container)).toEqual([]);
    expect(d.container.textContent).toContain('Formula inserted');
    v.destroy();
  });

  it('az értesítési szolgáltatás a próba-jelzőt kulcsos frissítésnél is átveszi, és nem vonja össze a jel nélküli társával', () => {
    const k = ertesitesek.ertesit({ kulcs: 'x', cim: 'A', proba: true });
    expect(ertesitesek.lista.find((e) => e.id === k)!.proba).toBe(true);
    ertesitesek.ertesit({ kulcs: 'x', cim: 'A' });
    expect(ertesitesek.lista.find((e) => e.id === k)!.proba).toBe(false);
    const a = ertesitesek.ertesit({ cim: 'B', proba: true });
    const b = ertesitesek.ertesit({ cim: 'B' });
    expect(a).not.toBe(b);
  });
});
