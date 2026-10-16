import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { beallitasAblak } from '../src/beallitasok/allapot.svelte';
import { nyelv } from '../src/lib/i18n';

const valasz = (adat: unknown, statusz = 200) => new Response(JSON.stringify(adat), { status: statusz });
afterEach(() => { cleanup(); beallitasok.adat = null; beallitasAblak.nyitva = false; nyelv.beallit('hu'); document.documentElement.style.removeProperty('--betu-torzs'); delete document.documentElement.dataset.tema; vi.unstubAllGlobals(); });

describe('App settings integration', () => {
  it('loads and saves theme and editor font size through the real Settings dialog', async () => {
    nyelv.beallit('en');
    let adat: BeallitasokValasz = { verzio: 1, rev: 'r1', ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] };
    adat.ertek.megjelenes.betumeret = 18;
    const irasok: unknown[] = [];
    vi.stubGlobal('WebSocket', class { readyState = 0; close() {} send() {} });
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      if (String(url) === '/api/beallitasok') {
        if (init?.method === 'PUT') {
          const keres = JSON.parse(String(init.body)); irasok.push(keres);
          adat = { ...adat, rev: 'r2', ertek: { ...adat.ertek, megjelenes: { ...adat.ertek.megjelenes, ...keres.valtozas.megjelenes } } };
        }
        return valasz(adat);
      }
      return valasz({ hiba: 'Synthetic endpoint is unavailable.' }, 404);
    });
    render(App, { props: { felulet: new Felulet({ csend: { be: false } }) } });
    await waitFor(() => expect(document.documentElement.style.getPropertyValue('--betu-torzs')).toBe('18px'));
    await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Appearance' }));
    await fireEvent.input(screen.getByLabelText('Editor font size'), { target: { value: '22' } });
    await fireEvent.change(screen.getByLabelText('Theme'), { target: { value: 'sotet' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(document.documentElement.style.getPropertyValue('--betu-torzs')).toBe('22px'));
    expect(document.documentElement.dataset.tema).toBe('sotet');
    expect(irasok).toHaveLength(1);
  });
  it('finishes automatic setup before running its deferred AI navigation', async () => {
    nyelv.beallit('en');
    let adat: BeallitasokValasz = { verzio: 1, rev: 'setup-r1', ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic' }, setup_szukseges: true, ujrainditas: [] };
    vi.stubGlobal('WebSocket', class { readyState = 0; close() {} send() {} });
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      if (String(url) === '/api/beallitasok') {
        if (init?.method === 'PUT') {
          const keres = JSON.parse(String(init.body));
          adat = { ...adat, rev: 'setup-r2', setup_szukseges: false, ertek: { ...adat.ertek, ...keres.valtozas } };
        }
        return valasz(adat);
      }
      return valasz({ hiba: 'Synthetic endpoint is unavailable.' }, 404);
    });
    const felulet = new Felulet({ csend: { be: false } }); render(App, { props: { felulet } });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Welcome to Manifold' })).toBeTruthy());
    for (let i = 0; i < 4; i++) await fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Review AI tools after setup' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(felulet.vezerlo.nyitott.modellek).toBe(true));
    expect(beallitasok.adat?.setup_szukseges).toBe(false);
    expect(screen.queryByRole('button', { name: 'Start writing' })).toBeNull();
  });
  it('an old core without settings preserves the saved interface preferences', async () => {
    const felulet = new Felulet({ tema: 'sotet', csend: { be: true }, szerkesztoMod: 'forras', rendszerErtesites: false });
    vi.stubGlobal('WebSocket', class { readyState = 0; close() {} send() {} });
    vi.stubGlobal('fetch', async () => valasz({ hiba: 'Synthetic old API.' }, 404));
    render(App, { props: { felulet } });
    await waitFor(() => expect(beallitasok.elerheto).toBe(false));
    expect(felulet.tema).toBe('sotet'); expect(felulet.csend.be).toBe(true);
    expect(felulet.szerkesztoMod).toBe('forras'); expect(felulet.rendszerErtesites).toBe(false);
  });

});
