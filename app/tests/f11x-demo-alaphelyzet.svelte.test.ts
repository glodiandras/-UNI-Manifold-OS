// F11 (9. tétel): a „Reset demo” gomb a Settings › General oldalon: csak a demo munkatérben látszik, megerősítéssel, a
// `POST /api/demo/alaphelyzet {megerosit: true}` végpontra megy; a hiba ikonnal és szóval jelenik meg; felhasználói munkatérben
// (vagy ismeretlen állapotnál) nincs gomb és nem megy ki alaphelyzet-kérés.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Beallitasok from '../src/beallitasok/Beallitasok.svelte';
import { beallitasAblak } from '../src/beallitasok/allapot.svelte';
import DemoAlaphelyzet from '../src/beallitasok/DemoAlaphelyzet.svelte';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { nyelv } from '../src/lib/i18n';

const json = (d: unknown, status = 200) => new Response(JSON.stringify(d), { status, headers: { 'Content-Type': 'application/json' } });
let kerek: { metodus: string; ut: string; torzs: unknown }[];
let allapot: () => Response;
let alaphelyzetValasz: () => Response;

beforeEach(() => {
  nyelv.beallit('en');
  kerek = [];
  allapot = () => json({ ok: true, demo: true, fajl: 12, modositott: 0, hianyzo: 0, hozzaadott: 0 });
  alaphelyzetValasz = () => json({ ok: true, visszaallitva: 2, ujra_letrehozva: 1, felretett: ['Mine/Note.md'], pillanatkep: { elotte: 'a', utana: 'b' } });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerek.push({ metodus: init?.method ?? 'GET', ut: u.pathname, torzs: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/demo/allapot') return allapot();
    if (u.pathname === '/api/demo/alaphelyzet') return alaphelyzetValasz();
    return json({ hiba: 'nincs' }, 404);
  });
});
afterEach(() => { cleanup(); beallitasok.adat = null; beallitasAblak.szakasz = 'altalanos'; vi.unstubAllGlobals(); nyelv.beallit('hu'); });

const postok = () => kerek.filter((k) => k.metodus === 'POST');

describe('Reset demo', () => {
  it('felhasználói munkatérben nincs gomb, és semmi nem megy ki az alaphelyzet végpontra', async () => {
    allapot = () => json({ ok: true, demo: false });
    const c = render(DemoAlaphelyzet);
    await waitFor(() => expect(kerek.some((k) => k.ut === '/api/demo/allapot')).toBe(true));
    await new Promise((r) => setTimeout(r, 0));
    expect(c.container.querySelector('[data-demo-alaphelyzet]')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reset demo' })).toBeNull();
    expect(postok()).toEqual([]);
  });

  it('ismeretlen állapotnál (a kérés hibás) sincs gomb', async () => {
    allapot = () => json({ hiba: 'x' }, 503);
    const c = render(DemoAlaphelyzet);
    await waitFor(() => expect(kerek.length).toBe(1));
    await new Promise((r) => setTimeout(r, 0));
    expect(c.container.querySelector('[data-demo-alaphelyzet]')).toBeNull();
  });

  it('demóban: a gomb megerősítést kér; a Mégse nem küld semmit; a megerősítés pontosan {megerosit: true}-t küld, majd összegez', async () => {
    const c = render(DemoAlaphelyzet);
    const gomb = await screen.findByRole('button', { name: 'Reset demo' });
    await fireEvent.click(gomb);
    expect(postok()).toEqual([]);                                               // a gomb önmagában nem állít vissza
    expect(screen.getByRole('alertdialog').textContent).toContain('A snapshot is saved first');
    await fireEvent.click(c.container.querySelector<HTMLElement>('[data-demo-megse]')!);
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(postok()).toEqual([]);

    await fireEvent.click(await screen.findByRole('button', { name: 'Reset demo' }));
    await fireEvent.click(c.container.querySelector<HTMLElement>('[data-demo-megerosit]')!);
    await waitFor(() => expect(c.container.querySelector('.siker')).not.toBeNull());
    expect(postok()).toEqual([{ metodus: 'POST', ut: '/api/demo/alaphelyzet', torzs: { megerosit: true } }]);
    expect(c.container.querySelector('.siker')!.textContent).toContain('The demo was reset: 3 restored or recreated, 1 set aside.');
    expect(c.container.querySelector('.siker svg')).not.toBeNull();             // nem csak szín
  });

  it('a hiba ikonnal és szóval, role="alert"-ben jelenik meg; a gomb újra használható', async () => {
    alaphelyzetValasz = () => json({ hiba: 'The demo workspace is open.', kod: 'demo.fut' }, 409);
    const c = render(DemoAlaphelyzet);
    await fireEvent.click(await screen.findByRole('button', { name: 'Reset demo' }));
    await fireEvent.click(c.container.querySelector<HTMLElement>('[data-demo-megerosit]')!);
    const riado = await screen.findByRole('alert');
    expect(riado.textContent).toContain('The demo could not be reset:');
    expect(riado.querySelector('svg')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Reset demo' })).toBeTruthy();
    expect(c.container.querySelector('.siker')).toBeNull();
  });

  it('a Settings › General oldalon jelenik meg (demóban), felhasználói munkatérben nem', async () => {
    const ertek = alapBeallitasok();
    const valasz: BeallitasokValasz = { verzio: 1, rev: 'r1', ertek, munkater: { id: 'demo', nev: 'Demo', vault: '/synthetic/demo' }, setup_szukseges: false, ujrainditas: [] };
    const nyit = () => {
      const tar = new BeallitasokTar();
      tar.fogad(valasz);
      beallitasok.fogad(valasz);
      return render(Beallitasok, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
    };
    const a = nyit();
    expect(await screen.findByText('Demo workspace')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reset demo' })).toBeTruthy();
    a.unmount();
    allapot = () => json({ ok: true, demo: false });
    kerek = [];
    const b = nyit();
    await waitFor(() => expect(kerek.some((k) => k.ut === '/api/demo/allapot')).toBe(true));
    await new Promise((r) => setTimeout(r, 0));
    expect(b.container.querySelector('[data-demo-alaphelyzet]')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reset demo' })).toBeNull();
  });
});
