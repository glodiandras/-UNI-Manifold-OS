// A Manifold-lap (C17): a szakaszok és üres állapotaik, a feladatlista és a részlet (leállítás, napló, mit változtatott,
// visszavonás hibaágakkal), az Asszisztens-kapcsolók, a Rendszer szakasz, és a jelenlét-pont az oldalsávban.

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { trackerKliens } from '../src/lib/tracker/kliens.svelte';
import { feladatsor } from '../src/lib/vezerlo/feladatsor.svelte';
import { vezerloKapcsolok } from '../src/lib/vezerlo/kapcsolok.svelte';
import { rendszerAllapot } from '../src/lib/vezerlo/rendszer.svelte';
import type { Feladat, FeladatReszlet, Valtozasok } from '../src/lib/vezerlo/tipusok';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import ManifoldLap from '../src/hej/ManifoldLap.svelte';
import Ikonsav from '../src/hej/Ikonsav.svelte';
import FeladatSor from '../src/hej/vezerlo/FeladatSor.svelte';
import { nyelv } from '../src/lib/i18n';

vi.mock('../src/hej/kapcsolatok/mergeNezet', () => ({
  lf: (s: string | null) => s ?? '',
  mergeNezet: (parent: HTMLElement) => {
    parent.textContent = 'összevetés';
    return { destroy() {} };
  },
}));

function feladat(id: string, mezok: Partial<Feladat> = {}): Feladat {
  return {
    id, tipus: 'proba', cim: `Feladat ${id}`, osszegzes: '', figyelmeztetes: [], lepesek: [{ cim: 'a' }, { cim: 'b' }],
    kulturalt_stop: false, allapot: 'sorban', letrehozva: '2026-10-02T10:00:00', indult: null, vegzett: null, szazalek: 0,
    lepes_i: 0, kilepes: null, hiba: null, leallitas_kerve: false, forras: '2.0', vault_ir: true, modell: false, ...mezok,
  };
}

const valasz = (adat: unknown, kod = 200) =>
  new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

let kerelmek: { url: string; metodus: string; body?: Record<string, unknown> }[];
let valaszok: Record<string, (init?: RequestInit) => Response>;

function kornyezet() {
  const felulet = new Felulet();
  const kapcsolat = new CoreKapcsolat('ws://x');
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat }]]);
  return { felulet, kapcsolat, context };
}

const VALTOZAS: Valtozasok = {
  feladat: 'F-1',
  nincs_tar: false,
  korok: [
    {
      kor: 'LEPES-20261002-100001',
      visszavonva: false,
      visszavonhato: true,
      commitok: [
        {
          sha: 'a'.repeat(40), datum: '2026-10-02T10:00:01', targy: 'próba 1', tetel: 'proba-1',
          fajlok: [
            { ut: '_Proba/egy.md', allapot: 'A', plusz: 3, minusz: 0 },
            { ut: 'T01/valtozott.md', allapot: 'M', plusz: 1, minusz: 2 },
          ],
        },
      ],
    },
    { kor: 'LEPES-20261002-100002', visszavonva: true, visszavonhato: false, commitok: [{ sha: 'b'.repeat(40), datum: '', targy: 'x', tetel: null, fajlok: [{ ut: '_Proba/ketto.md', allapot: 'A', plusz: 1, minusz: 0 }] }] },
  ],
};

beforeEach(() => {
  kerelmek = [];
  valaszok = {};
  feladatsor.lista = [];
  feladatsor.betoltve = true;
  feladatsor.hiba = null;
  vezerloKapcsolok.ertek = { asszisztens: true, tracker: true };
  vezerloKapcsolok.hiba = null;
  trackerKliens.nemFogad = null;
  rendszerAllapot.adat = null;
  rendszerAllapot.hiba = null;
  ertesitesek.lista = [];
  ertesitesek.elozmeny = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push({ url: u.pathname, metodus: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const f = valaszok[`${init?.method ?? 'GET'} ${u.pathname}`];
    return f ? f(init) : valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  nyelv.beallit('hu');
});

describe('a szakaszok', () => {
  it('mind a hét szakasz megvan; alapból csak a Most nyitott; a nem épült szakasz üres állapotot mutat', () => {
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    const nevek = ['Most', 'Bevitel', 'Tanulás', 'Statisztika', 'Asszisztens', 'Modellek', 'Rendszer'];
    for (const n of nevek) expect(screen.getByRole('button', { name: n })).toBeTruthy();
    expect(nevek.map((n) => screen.getByRole('button', { name: n }).getAttribute('aria-expanded'))).toEqual(['true', 'false', 'false', 'false', 'false', 'false', 'false']);
    expect(screen.getByText(/Nem fut és nem vár feladat/)).toBeTruthy();
    expect(screen.queryByLabelText(/Videólinkek/)).toBeNull();     // a Bevitel (C20a) zárva nem rajzolódik ki
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('a szakasz nyitott állapota a felület tartós állapotába kerül', async () => {
    const { context, felulet } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: 'Bevitel' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Most' }));
    expect(felulet.vezerlo.nyitott).toEqual({ bevitel: true, most: false });
  });

  it('a Rendszer szakasz csak nyitva kérdez a core-tól', async () => {
    valaszok['GET /api/vezerlo/rendszer'] = () =>
      valasz({
        memoria: { szabad_szazalek: 41, osszes_gb: 16, swap_mb: 0, core_rss_mb: 120 },
        modellzar: { szabad: false, tartalom: '', pid: 4242, repo: 'mlx/x', ido: '14:03:11', elavult: false },
        worker: { fut: true, pid: 1, rss_mb: 2048, modell: 'qwen3_vl_4b', repo: 'r', keret_gb: 5, szunetek: 0, aktivitas: 'tetlen' },
        ssd: { elerheto: true, kotet: 'Work', osszes_gb: 1000, szabad_gb: 420 },
        mentes: { utolso: '2026-10-02T09:00:00', friss: false, tarolok: {}, mappa: '/x' },
        kapcsolok: { asszisztens: true, tracker: true },
      });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    expect(kerelmek.some((k) => k.url === '/api/vezerlo/rendszer')).toBe(false);
    await fireEvent.click(screen.getByRole('button', { name: 'Rendszer' }));
    await screen.findByText(/41 % szabad/);
    expect(screen.getByText(/mlx\/x · pid 4242 · 14:03:11 óta/)).toBeTruthy();
    expect(screen.getByText(/qwen3_vl_4b · keret 5 GB/)).toBeTruthy();
    expect(screen.getByText(/Work · 420 GB szabad/)).toBeTruthy();
    expect(screen.getByText(/a mentés régebbi/)).toBeTruthy();
    valaszok['POST /api/feladatok'] = () => valasz(feladat('F-5', { tipus: 'mentes' }), 201);
    await fireEvent.click(screen.getByRole('button', { name: 'Mentés most' }));
    await waitFor(() => expect(kerelmek.some((k) => k.metodus === 'POST' && k.body?.tipus === 'mentes')).toBe(true));
  });

  it('a Rendszer szakasz kimondja a belső lemezes mentés hibáját (C29.6/C29.7b: a core `mentes.hiba`-ja)', async () => {
    const alap = {
      memoria: { szabad_szazalek: 41, osszes_gb: 16, swap_mb: 0, core_rss_mb: 120 },
      modellzar: { szabad: true, tartalom: '', pid: null, repo: null, ido: null, elavult: false },
      worker: { fut: false },
      ssd: { elerheto: true, kotet: 'Work', osszes_gb: 1000, szabad_gb: 420 },
      kapcsolok: { asszisztens: true, tracker: true },
    };
    valaszok['GET /api/vezerlo/rendszer'] = () =>
      valasz({
        ...alap,
        mentes: {
          utolso: '2026-10-02T09:00:00', friss: false, tarolok: {}, mappa: '/x',
          hiba: { ido: '2026-10-04T18:30:00', hibak: { vault: 'a lemez megtelt', 'mos-kodtar': 'nincs hely' } },
        },
      });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: 'Rendszer' }));
    const sor = await screen.findByRole('alert');
    expect(sor.textContent).toMatch(/belső lemezes mentés nem sikerült/);
    expect(sor.textContent).toContain('vault: a lemez megtelt');
    expect(sor.textContent).toContain('mos-kodtar: nincs hely');
  });

  it('hiba nélküli mentésnél nincs hibasor', async () => {
    valaszok['GET /api/vezerlo/rendszer'] = () =>
      valasz({
        memoria: { szabad_szazalek: 41, osszes_gb: 16, swap_mb: 0, core_rss_mb: 120 },
        modellzar: { szabad: true, tartalom: '', pid: null, repo: null, ido: null, elavult: false },
        worker: { fut: false },
        ssd: { elerheto: true, kotet: 'Work', osszes_gb: 1000, szabad_gb: 420 },
        mentes: { utolso: '2026-10-02T09:00:00', friss: true, tarolok: {}, mappa: '/x', hiba: null },
        kapcsolok: { asszisztens: true, tracker: true },
      });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: 'Rendszer' }));
    await screen.findByText(/41 % szabad/);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('az Asszisztens és a Tracker kapcsoló a core-nak ír; hibánál visszaáll', async () => {
    valaszok['PUT /api/vezerlo/kapcsolok'] = (init) => {
      const b = JSON.parse(String(init!.body));
      return b.tracker === false ? valasz({ hiba: 'nem írható' }, 400) : valasz({ ok: true, kapcsolok: { asszisztens: false, tracker: true } });
    };
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: 'Asszisztens' }));
    const asszisztens = screen.getByRole('switch', { name: 'Asszisztens' }) as HTMLInputElement;
    const tracker = screen.getByRole('switch', { name: 'Tracker' }) as HTMLInputElement;
    expect([asszisztens.checked, tracker.checked]).toEqual([true, true]);
    await fireEvent.click(asszisztens);
    await waitFor(() => expect(vezerloKapcsolok.ertek.asszisztens).toBe(false));
    await fireEvent.click(tracker);
    await screen.findByText('nem írható');
    await waitFor(() => expect(vezerloKapcsolok.ertek.tracker).toBe(true));
  });
});

describe('a Tracker nem fogad jelzése (T007)', () => {
  it('a Tracker kapcsoló alatt figyelmeztetés látszik, ha a core nem fogadja az eseményeket', async () => {
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: 'Asszisztens' }));
    expect(screen.queryByText(/A Tracker nem tud írni/)).toBeNull();
    trackerKliens.nemFogad = 'a tracker adatbázisa nem írható';
    flushSync();
    const figy = await screen.findByText(/A Tracker nem tud írni/);
    expect(figy.textContent).toContain('a tracker adatbázisa nem írható');
    expect(figy.getAttribute('role')).toBe('alert');
    trackerKliens.nemFogad = null;
    flushSync();
    await waitFor(() => expect(screen.queryByText(/A Tracker nem tud írni/)).toBeNull());
  });
});

describe('a feladatlista és a részlet', () => {
  it('angol feladatnév és indulási felirat a futó feladat sorában', () => {
    nyelv.beallit('en');
    const { container } = render(FeladatSor, { props: {
      feladat: feladat('en', { cim: 'Füzetfotók bekötése', allapot: 'fut', indult: '2026-10-02T10:00:00' }), onnyit: () => {},
    } });
    expect(container.querySelector('.cim')?.textContent).toBe('Link notebook photos');
    expect(container.querySelector('.meta')?.textContent).toContain('started ');
    expect(container.querySelector('.meta')?.textContent).not.toContain('indult');
  });

  beforeEach(() => {
    feladatsor.lista = [
      feladat('F-3', { allapot: 'kesz', cim: 'Mentés', indult: '2026-10-02T10:00:00', vegzett: '2026-10-02T10:00:09', szazalek: 100 }),
      feladat('F-2', { allapot: 'sorban', cim: 'Várakozó' }),
      feladat('F-1', { allapot: 'fut', cim: 'Próbafeladat', szazalek: 45, lepes_i: 0, indult: '2026-10-02T10:00:00' }),
    ];
  });

  it('a futó és várakozó elöl, a legutóbbiak alatt; a futó haladássávval', () => {
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    const elo = within(screen.getByRole('list', { name: 'Futó és várakozó feladatok' }));
    expect(elo.getAllByRole('button').map((b) => b.querySelector('.cim')!.textContent)).toEqual(['Próbafeladat', 'Várakozó']);
    expect(elo.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('45');
    expect(elo.getByText(/1\/2\. lépés · 45 %/)).toBeTruthy();
    const volt = within(screen.getByRole('list', { name: 'Legutóbbi feladatok' }));
    expect(volt.getByText('Mentés')).toBeTruthy();
    expect(volt.getByText(/9 mp/)).toBeTruthy();
  });

  it('a törölt feladat nem látszik a legutóbbiak közt', () => {
    feladatsor.lista = [feladat('F-7', { allapot: 'torolve', cim: 'Töröltem' })];
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    expect(screen.queryByText('Töröltem')).toBeNull();
  });

  function reszletValaszok(f: Partial<Feladat> = {}, sorok = ['── 1/2. lépés: a', 'Kész: _Proba/egy.md']) {
    valaszok['GET /api/feladatok/F-1'] = () => valasz({ ...feladat('F-1', { allapot: 'fut', ...f }), sorok, tol: 0, osszes_sor: sorok.length } satisfies FeladatReszlet);
    valaszok['GET /api/feladatok/F-1/valtozasok'] = () => valasz(VALTOZAS);
  }

  it('a sorra kattintva a részlet nyílik: napló, változások; a vissza-gomb a listához visz', async () => {
    reszletValaszok();
    const { context, felulet } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Próbafeladat/ }));
    expect(felulet.manifoldFeladat).toBe('F-1');
    await screen.findByText(/Kész: _Proba\/egy\.md/);
    expect(screen.getByLabelText('A feladat naplója').textContent).toContain('── 1/2. lépés: a');
    expect(await screen.findByText('egy.md')).toBeTruthy();
    expect(screen.getByText('+3')).toBeTruthy();
    expect(screen.getByText('−2')).toBeTruthy();
    expect(screen.getByText('visszavonva')).toBeTruthy();                // a második kör már vissza van vonva
    await fireEvent.click(screen.getByRole('button', { name: /Feladatok/ }));
    expect(felulet.manifoldFeladat).toBeNull();
    expect(screen.getByRole('button', { name: 'Most' })).toBeTruthy();
  });

  it('a csonka változáslistát kimondja (T144), a teljes listánál nincs jelzés', async () => {
    reszletValaszok();
    valaszok['GET /api/feladatok/F-1/valtozasok'] = () => valasz({ ...VALTOZAS, levagva: true });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Próbafeladat/ }));
    expect(await screen.findByText(/A lista csonka/)).toBeTruthy();
  });

  it('a nem csonka változáslistánál nincs „csonka” jelzés', async () => {
    reszletValaszok();
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Próbafeladat/ }));
    await screen.findByText('egy.md');
    expect(screen.queryByText(/A lista csonka/)).toBeNull();
  });

  it('a leállítás: kulturált nélküli feladatnál megerősítés kell, utána az azonnali leállítás megy', async () => {
    reszletValaszok();
    valaszok['POST /api/feladatok/F-1/leallitas'] = () => valasz({ allapot: 'leallitva' });
    valaszok['GET /api/feladatok'] = () => valasz({ feladatok: feladatsor.lista });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Próbafeladat/ }));
    await fireEvent.click(await screen.findByRole('button', { name: /Leállítás/ }));
    expect(kerelmek.some((k) => k.url.endsWith('/leallitas'))).toBe(false);   // még megerősítés kell
    await fireEvent.click(screen.getByRole('button', { name: 'Mégse' }));
    await fireEvent.click(screen.getByRole('button', { name: /Leállítás/ }));
    await fireEvent.click(screen.getByRole('button', { name: 'Azonnali leállítás' }));
    await waitFor(() => expect(kerelmek.find((k) => k.url.endsWith('/leallitas'))?.body).toEqual({ azonnal: true }));
  });

  it('a kulturált leállítás megerősítés nélkül megy (a tétel végén áll meg)', async () => {
    feladatsor.lista = [feladat('F-1', { allapot: 'fut', cim: 'Lánc', kulturalt_stop: true })];
    reszletValaszok({ kulturalt_stop: true });
    valaszok['POST /api/feladatok/F-1/leallitas'] = () => valasz({ allapot: 'megall_a_tetel_vegen' });
    valaszok['GET /api/feladatok'] = () => valasz({ feladatok: feladatsor.lista });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Lánc/ }));
    await fireEvent.click(await screen.findByRole('button', { name: /Leállítás/ }));
    await waitFor(() => expect(kerelmek.find((k) => k.url.endsWith('/leallitas'))?.body).toEqual({ azonnal: false }));
  });

  it('a sorban álló feladat törölhető a sorból', async () => {
    feladatsor.lista = [feladat('F-2', { cim: 'Várakozó' })];
    valaszok['GET /api/feladatok/F-2'] = () => valasz({ ...feladat('F-2'), sorok: [], tol: 0, osszes_sor: 0 });
    valaszok['GET /api/feladatok/F-2/valtozasok'] = () => valasz({ feladat: 'F-2', korok: [], nincs_tar: false });
    valaszok['POST /api/feladatok/F-2/leallitas'] = () => valasz({ allapot: 'torolve' });
    valaszok['GET /api/feladatok'] = () => valasz({ feladatok: [] });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Várakozó/ }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Törlés a sorból' }));
    await waitFor(() => expect(kerelmek.find((k) => k.url.endsWith('/leallitas'))?.body).toEqual({ azonnal: false }));
  });

  it('a visszavonás megerősítéssel megy a kör azonosítójával, siker után frissül és értesít', async () => {
    reszletValaszok();
    valaszok['POST /api/pillanat/vault/visszavonas'] = () => valasz({ ok: true, sha: 'c'.repeat(40) });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Próbafeladat/ }));
    await fireEvent.click(await screen.findByRole('button', { name: /Visszavonás/ }));
    expect(kerelmek.some((k) => k.url === '/api/pillanat/vault/visszavonas')).toBe(false);
    await fireEvent.click(screen.getByRole('button', { name: 'Mégse' }));
    await fireEvent.click(screen.getByRole('button', { name: /Visszavonás/ }));
    await fireEvent.click(screen.getByRole('button', { name: 'Visszavonás' }));
    await waitFor(() => expect(kerelmek.find((k) => k.url === '/api/pillanat/vault/visszavonas')?.body).toEqual({ kor: 'LEPES-20261002-100001' }));
    await waitFor(() => expect(ertesitesek.elozmeny[0]?.cim).toBe('Visszavonva'));
  });

  it('a visszavonás hibája (ütközés) megnevezi a fájlokat', async () => {
    reszletValaszok();
    valaszok['POST /api/pillanat/vault/visszavonas'] = () => valasz({ hiba: 'a visszavonás ütközik', utkozes: true, fajlok: ['T01/valtozott.md'] }, 409);
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Próbafeladat/ }));
    await fireEvent.click(await screen.findByRole('button', { name: /Visszavonás/ }));
    await fireEvent.click(screen.getByRole('button', { name: 'Visszavonás' }));
    const hiba = await screen.findByRole('alert');
    expect(hiba.textContent).toContain('a visszavonás ütközik');
    expect(hiba.textContent).toContain('T01/valtozott.md');
  });

  it('fájlra kattintva az összevetés nyílik, a Bezárás zárja', async () => {
    reszletValaszok();
    valaszok['GET /api/vault/elozmeny/valtozat'] = () => valasz({ sha: 'a', ut_akkor: '_Proba/egy.md', szoveg: 'új', szoveg_ok: null, elozo: null, elozo_ok: 'nincs' });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Próbafeladat/ }));
    await fireEvent.click(await screen.findByRole('button', { name: /egy\.md/ }));
    await screen.findByText('összevetés');
    expect(screen.getByText('Még nem létezett')).toBeTruthy();
    const diff = within(screen.getByRole('dialog', { name: 'A feladat változása egy fájlban' }));
    await fireEvent.click(diff.getByRole('button', { name: 'Bezárás' }));
    await waitFor(() => expect(screen.queryByText('összevetés')).toBeNull());
  });

  it('változás nélküli és legacy feladat magyarázatot kap, a hiba a részletben látszik', async () => {
    feladatsor.lista = [feladat('F-1', { allapot: 'hiba', cim: 'Rossz', hiba: 'a(z) 1. lépés hibával ért véget' })];
    valaszok['GET /api/feladatok/F-1'] = () => valasz({ ...feladat('F-1', { allapot: 'hiba', hiba: 'a(z) 1. lépés hibával ért véget' }), sorok: [], tol: 0, osszes_sor: 0 });
    valaszok['GET /api/feladatok/F-1/valtozasok'] = () => valasz({ feladat: 'F-1', korok: [], nincs_tar: false });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Rossz/ }));
    await screen.findByText('Nem írt a vaultba.');
    expect(screen.getAllByRole('alert').some((e) => e.textContent?.includes('hibával ért véget'))).toBe(true);
    expect(screen.getByText('Még nincs naplósor.')).toBeTruthy();
  });

  it('a más eredetű (importált) feladat semleges magyarázatot kap a hiányzó változásról és naplóról', async () => {
    const regi = feladat('F-9', { allapot: 'kesz', cim: 'Régi', forras: 'import' });
    feladatsor.lista = [regi];
    valaszok['GET /api/feladatok/F-9'] = () => valasz({ ...regi, sorok: [], tol: 0, osszes_sor: 0 });
    valaszok['GET /api/feladatok/F-9/valtozasok'] = () => valasz({ feladat: 'F-9', korok: [], nincs_tar: false });
    const { context } = kornyezet();
    render(ManifoldLap, { context });
    await fireEvent.click(screen.getByRole('button', { name: /Régi/ }));
    await screen.findByText('Ehhez a feladathoz nem érhető el változás-előzmény.');
    expect(screen.getByText('Ehhez a feladathoz nincs elérhető napló.')).toBeTruthy();
    expect(screen.queryByText('Nem írt a vaultba.')).toBeNull();
  });

  it('a rendszer tartalma nem veszi el a fókuszt és az Esc nem zár be fület', async () => {
    const { context, felulet } = kornyezet();
    felulet.munkaterulet.megnyitNezet('manifold');
    const mezo = document.createElement('input'); document.body.append(mezo); mezo.focus();
    render(ManifoldLap, { context });
    expect(document.activeElement).toBe(mezo);
    await fireEvent.keyDown(mezo, { key: 'Escape' });
    expect(felulet.munkaterulet.aktivFul?.nezet?.tipus).toBe('manifold');
  });
});

describe('a jelenlét-pont', () => {
  it('csak futó feladatnál látszik a Manifold gomb mellett, szöveg és szám nélkül', () => {
    const { context } = kornyezet();
    render(Ikonsav, { context });
    const gomb = screen.getByRole('navigation', { name: 'Gyorsműveletek' });
    expect(gomb.querySelector('.pont')).toBeNull();
    feladatsor.lista = [feladat('F-1', { allapot: 'sorban' })];
    flushSync();
    expect(gomb.querySelector('.pont')).toBeNull();                      // a várakozó feladat még nem „fut”
    feladatsor.lista = [feladat('F-1', { allapot: 'fut' })];
    flushSync();
    expect(gomb.querySelector('.pont')).not.toBeNull();
    expect(gomb.querySelector('.sr-only')!.textContent).toContain('feladat fut');
    expect(gomb.querySelector('.pont')!.getAttribute('aria-hidden')).toBe('true');
    feladatsor.lista = [feladat('F-1', { allapot: 'kesz' })];
    flushSync();
    expect(gomb.querySelector('.pont')).toBeNull();
  });
});
