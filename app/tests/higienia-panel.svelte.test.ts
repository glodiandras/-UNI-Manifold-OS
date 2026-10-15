// A jobb panel „Higiénia” szakasza (C30a): a jegyzet észrevételei az indexből — a komponens megjelenítése (ugrás a sorra,
// sor nélküli tétel, üres és hibás állapot, a hosszú lista vágása) és a `JobbPanel` bekötése (alapból zárt, a cím a darabszámot
// csak N > 0-nál mutatja, kikapcsolt Asszisztensnél nincs szakasz és nincs kérés, a hiányzó végpont csendes).

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import JobbPanel from '../src/hej/JobbPanel.svelte';
import Higienia from '../src/hej/kapcsolatok/Higienia.svelte';
import type { HigieniaTetel } from '../src/lib/asszisztens/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { vezerloKapcsolok } from '../src/lib/vezerlo/kapcsolok.svelte';

const tetel = (n: number, mezok: Partial<HigieniaTetel> = {}): HigieniaTetel => ({
  azonosito: `torott_link:${n}`, fajta: 'torott_link', szint: 'hiba', ut: 'A.md', sor: n + 8, uzenet: `Törött link: Nincs ${n}`, ...mezok,
});

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

describe('a Higienia komponens', () => {
  afterEach(cleanup);

  it('a tételek gombok: a sorra ugrás a sor számával hívódik', async () => {
    const onnyit = vi.fn();
    render(Higienia, { props: { tetelek: [tetel(1), tetel(2, { fajta: 'hibas_keplet', szint: 'figyelmeztetes' })], onnyit } });
    const gombok = screen.getAllByRole('button');
    expect(gombok).toHaveLength(2);
    expect(gombok[0].getAttribute('title')).toBe('Törött link — ugrás a 9. sorra');
    expect(gombok[1].getAttribute('title')).toBe('Hibás képlet — ugrás a 10. sorra');
    await fireEvent.click(gombok[1]);
    expect(onnyit).toHaveBeenCalledTimes(1);
    expect(onnyit.mock.calls[0][0]).toBe(10);
  });

  it('a sor nélküli tétel (árva jegyzet) nem gomb, de látszik', () => {
    render(Higienia, { props: { tetelek: [tetel(1, { fajta: 'arva_jegyzet', szint: 'tajekoztato', sor: null, uzenet: 'Árva jegyzet: nincs bejövő és nincs kimenő jegyzet-link.' })], onnyit: vi.fn() } });
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText(/Árva jegyzet/)).toBeTruthy();
  });

  it('üres lista: nincs észrevétel; hiba: riasztás', () => {
    const r = render(Higienia, { props: { tetelek: [], onnyit: vi.fn() } });
    expect(screen.getByRole('status').textContent).toContain('Nincs észrevétel');
    r.rerender({ tetelek: [], hiba: 'váratlan hiba', onnyit: vi.fn() });
    return waitFor(() => expect(screen.getByRole('alert').textContent).toBe('váratlan hiba'));
  });

  it('a hosszú lista 50-nél vágódik, a maradék száma kimondva', () => {
    render(Higienia, { props: { tetelek: Array.from({ length: 52 }, (_, i) => tetel(i)), onnyit: vi.fn() } });
    expect(screen.getAllByRole('button')).toHaveLength(50);
    expect(screen.getByText('… és még 2 észrevétel.')).toBeTruthy();
  });
});

describe('a JobbPanel Higiénia-szakasza', () => {
  let kerelmek: string[];
  let higienia: () => Response;

  beforeEach(() => {
    kerelmek = [];
    higienia = () => json({ kesz: true, jegyzetek: 1, tetelek: [tetel(1), tetel(2)] });
    vezerloKapcsolok.ertek = { asszisztens: true, tracker: true };
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      kerelmek.push(u.pathname + u.search);
      if (u.pathname === '/api/higienia') return higienia();
      return json({ hiba: 'nincs' }, 404);
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vezerloKapcsolok.ertek = { asszisztens: true, tracker: true };
  });

  function panel(ut: string | null = 'Matek/Mértani sorozat.md') {
    const felulet = new Felulet({ csend: { be: false } }); // a mindent mutató felület (C38: csendben a panel alapból zárt)
    if (ut) felulet.munkaterulet.megnyit(ut);
    const kapcsolat = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat }]]);
    return { ...render(JobbPanel, { context }), felulet, kapcsolat };
  }

  it('alapból zárt; a cím a darabszámot mutatja; megnyitva a tételek látszanak', async () => {
    const { felulet } = panel();
    const gomb = await screen.findByRole('button', { name: /Higiénia \(2\)/ });
    expect(gomb.getAttribute('aria-expanded')).toBe('false');
    expect(felulet.jobbPanel.higienia).toBe(false);
    expect(kerelmek).toContain('/api/higienia?ut=Matek%2FM%C3%A9rtani%20sorozat.md');
    await fireEvent.click(gomb);
    expect(gomb.getAttribute('aria-expanded')).toBe('true');
    expect(felulet.jobbPanel.higienia).toBe(true);
    expect(screen.getByText('Törött link: Nincs 1')).toBeTruthy();
  });

  it('a szakasz az Előzmények után áll (a meglévő sorrend nem változik)', async () => {
    panel();
    await screen.findByRole('button', { name: /Higiénia/ });
    const cimek = [...document.querySelectorAll('section h2 .cim')].map((e) => e.textContent?.replace(/\s*\(\d+\)$/, ''));
    expect(cimek).toEqual(['Visszahivatkozások', 'Linkeletlen említések', 'Kimenő linkek', 'Vázlat', 'Előzmények', 'Higiénia', 'Hasonló jegyzetek']);
  });

  it('nincs tétel: a cím szám nélkül; a hiányzó végpont (404) csendes', async () => {
    higienia = () => json({ hiba: 'nincs ilyen jegyzet az indexben' }, 404);
    panel();
    const gomb = await screen.findByRole('button', { name: 'Higiénia' });
    await fireEvent.click(gomb);
    expect(screen.getByText('Nincs észrevétel ebben a jegyzetben.')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('kikapcsolt Asszisztensnél nincs szakasz és nincs kérés', async () => {
    vezerloKapcsolok.ertek = { asszisztens: false, tracker: true };
    panel();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole('button', { name: /Higiénia/ })).toBeNull();
    expect(kerelmek.filter((k) => k.startsWith('/api/higienia'))).toEqual([]);
  });

  it('nem md-fájlnál nincs kérés (a fülhöz nincs higiénia)', async () => {
    panel('Könyvek/tankonyv.pdf');
    await new Promise((r) => setTimeout(r, 50));
    expect(kerelmek.filter((k) => k.startsWith('/api/higienia'))).toEqual([]);
  });
});
