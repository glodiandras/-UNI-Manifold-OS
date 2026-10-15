// C25c: a keresőpanel a PDF-találatot az oldalára, a felirat-találatot a videó másodpercére nyitja (a horgony a fül nézetéé),
// a sor helyét oldalként / időkódként mutatja, és kimondja, ha a PDF-szöveg kinyerése még tart; a jobb panel „Hasonló
// jegyzetek” szakasza alapból zárt, csak kinyitva kér, és a vektor hiányát kimondja; a ⌘P-parancs kinyitja.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import JobbPanel from '../src/hej/JobbPanel.svelte';
import Kereses from '../src/atfedes/KeresoAblak.svelte';
import Hasonlok from '../src/hej/kapcsolatok/Hasonlok.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { allapotSzoveg, pontSzazalek } from '../src/lib/kereses/hasonlo.svelte';
import { helyCimke, idokod, pdfFolyamatban, sorokraEgyesit, talalatCel, vaultKereses } from '../src/lib/kereses/vaultKereses.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { vezerloKapcsolok } from '../src/lib/vezerlo/kapcsolok.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

const PDF = { ut: 'Könyvek/Irodalom 10.pdf', pont: 2, tipus: 'pdf' as const, talalatok: [{ sor: 40, oszlop: 2, hossz: 7, szoveg: 'A Himnusz keletkezése', oldal: 12 }] };
const VTT = {
  ut: 'I11 - Romantika/Média/Kölcsey.hu.vtt',
  pont: 1,
  tipus: 'felirat' as const,
  media: 'ATTCHMNTS - Videos/Kölcsey.mp4',
  talalatok: [{ sor: 2, oszlop: 0, hossz: 7, szoveg: 'Himnusz született', mp: 83.4 }],
};

describe('a hely és a cél (tiszta függvények)', () => {
  it('időkód, oldal, sorszám', () => {
    expect(idokod(83.4)).toBe('1:23');
    expect(idokod(3725)).toBe('1:02:05');
    expect(helyCimke({ sor: 40, oldal: 12 })).toBe('12. o.');
    expect(helyCimke({ sor: 2, mp: 83.4 })).toBe('1:23');
    expect(helyCimke({ sor: 7 })).toBe('7');
  });

  it('a cél: PDF az oldalára, felirat a videó másodpercére, média nélküli felirat önmaga', () => {
    const [h] = sorokraEgyesit(PDF);
    expect(h.oldal).toBe(12);
    expect(talalatCel(PDF, h)).toEqual({ ut: PDF.ut, horgony: 'page=12' });
    expect(talalatCel(PDF)).toEqual({ ut: PDF.ut, horgony: null });
    expect(talalatCel(VTT, sorokraEgyesit(VTT)[0])).toEqual({ ut: VTT.media, horgony: 't=83' });
    expect(talalatCel({ ...VTT, media: null }, VTT.talalatok[0])).toEqual({ ut: VTT.ut, horgony: null });
    expect(talalatCel({ ut: 'A.md', pont: 1, talalatok: [] }, { sor: 3 })).toEqual({ ut: 'A.md', horgony: null });
  });

  it('a PDF-folyamat csak futó kinyerőnél és hiányzó PDF-nél látszik', () => {
    expect(pdfFolyamatban({ osszes: 130, kesz: 12, kinyero: true })).toBeTruthy();
    expect(pdfFolyamatban({ osszes: 130, kesz: 130, kinyero: true })).toBeNull();
    expect(pdfFolyamatban({ osszes: 130, kesz: 0, kinyero: false })).toBeNull();
    expect(pdfFolyamatban(null)).toBeNull();
  });
});

describe('a keresőablak', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', async () => json({ q: 'Himnusz', osszes: 2, talalatok: [PDF, VTT] }));
    vaultKereses.beallit('', true);
    vaultKereses.pdfSzoveg = null;
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vaultKereses.beallit('', true);
    vaultKereses.pdfSzoveg = null;
  });

  function panel() {
    const felulet = new Felulet({});
    const fajlok = new VaultFajlok();
    const kapcsolat = new CoreKapcsolat('ws://x');
    render(Kereses, { context: new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]) });
    return { felulet, fajlok };
  }

  it('oldal és időkód a sorban; a kattintás a horgonnyal nyit, a szerkesztő nem ugrik', async () => {
    const { felulet } = panel();
    const ugras = vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
    vaultKereses.beallit('Himnusz', true);
    expect(await screen.findByText('12. o.')).toBeTruthy();
    expect(screen.getByText('1:23')).toBeTruthy();
    expect(screen.getByText('Kölcsey.mp4')).toBeTruthy(); // a felirat-találat fejléce a videó
    expect(screen.getByText('átirat')).toBeTruthy();
    await fireEvent.click(screen.getByText('12. o.'));
    expect(felulet.munkaterulet.aktivFul?.ut).toBe(PDF.ut);
    expect(felulet.munkaterulet.aktivFul?.nezet?.horgony).toBe('page=12');
    await fireEvent.click(screen.getByText('1:23'));
    expect(felulet.munkaterulet.aktivFul?.ut).toBe(VTT.media);
    expect(felulet.munkaterulet.aktivFul?.nezet?.horgony).toBe('t=83');
    expect(ugras).not.toHaveBeenCalled();
  });

  it('a futó PDF-kinyerést kimondja (a fájllista indexállapotából, majd az eseményből)', async () => {
    const { fajlok } = panel();
    fajlok.index = { kesz: true, pdf_szoveg: { osszes: 130, kesz: 12, kinyero: true } };
    vaultKereses.beallit('Himnusz', true);
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('PDF-szöveg indexelése: 12/130'));
    vaultKereses.pdfSzoveg = { osszes: 130, kesz: 130, kinyero: true };
    await waitFor(() => expect(screen.getByRole('status').textContent).not.toContain('PDF-szöveg'));
  });
});

describe('a Hasonló jegyzetek', () => {
  afterEach(cleanup);

  it('a komponens: lista, link-jel, százalék; az állapotok kimondva', async () => {
    const onnyit = vi.fn();
    const r = render(Hasonlok, {
      props: {
        valasz: {
          ut: 'A.md',
          allapot: 'ok',
          elavult: true,
          talalatok: [
            { ut: 'T/Spárta hadserege.md', pont: 0.834, kimeno: false, bejovo: true },
            { ut: 'Athén.md', pont: 0.41, kimeno: true, bejovo: false },
          ],
        },
        onnyit,
      },
    });
    expect(screen.getByText('Spárta hadserege')).toBeTruthy();
    expect(screen.getByText('83%')).toBeTruthy();
    expect(screen.getByText(/korábbi változatáé/)).toBeTruthy();
    expect(screen.getByTitle('Ez linkeli a megnyitott jegyzetet')).toBeTruthy();
    await fireEvent.click(screen.getByText('Athén'));
    expect(onnyit.mock.calls[0][0]).toBe('Athén.md');
    r.rerender({ valasz: { ut: 'A.md', allapot: 'nincs_vektor', elavult: false, talalatok: [] }, onnyit });
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('még nincs vektora'));
    expect(allapotSzoveg('nincs_tar')).toContain('vektorindex');
    expect(pontSzazalek(1.2)).toBe('100%');
  });

  describe('a JobbPanel szakasza', () => {
    let kerelmek: string[];
    beforeEach(() => {
      kerelmek = [];
      vezerloKapcsolok.ertek = { asszisztens: false, tracker: true };
      vi.stubGlobal('fetch', async (url: string) => {
        const u = new URL(url, 'http://127.0.0.1/');
        kerelmek.push(u.pathname + u.search);
        if (u.pathname === '/api/kereses/hasonlo')
          return json({ ut: 'A.md', allapot: 'ok', elavult: false, talalatok: [{ ut: 'B.md', pont: 0.7, kimeno: false, bejovo: false }] });
        return json({ hiba: 'nincs' }, 404);
      });
    });
    afterEach(() => {
      vi.unstubAllGlobals();
      vezerloKapcsolok.ertek = { asszisztens: true, tracker: true };
    });

    it('alapból zárt és nem kér; kinyitva kér és listáz; a parancs kinyitja', async () => {
      const felulet = new Felulet({ csend: { be: false } });
      felulet.munkaterulet.megnyit('A.md');
      const kapcsolat = new CoreKapcsolat('ws://127.0.0.1:1/ws');
      render(JobbPanel, { context: new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat }]]) });
      const gomb = await screen.findByRole('button', { name: 'Hasonló jegyzetek' });
      expect(gomb.getAttribute('aria-expanded')).toBe('false');
      expect(kerelmek.some((k) => k.startsWith('/api/kereses/hasonlo'))).toBe(false);
      await fireEvent.click(gomb);
      expect(await screen.findByText('B')).toBeTruthy();
      expect(kerelmek).toContain('/api/kereses/hasonlo?ut=A.md&n=12');
      felulet.jobbPanel.hasonlo = false;
      felulet.jobbPanel.nyitva = false;
      const reg = new Regiszter();
      alapParancsok(reg, felulet);
      reg.futtat('kereses.hasonlo', 'paletta');
      expect(felulet.jobbPanel.nyitva).toBe(true);
      expect(felulet.jobbPanel.hasonlo).toBe(true);
    });
  });
});
