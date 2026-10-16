import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Setup from '../src/setup/Setup.svelte';
import { elmenyModulok } from '../src/setup/elmeny';
import { BeallitasokTar } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok, type BeallitasokValasz, type BeallitasokValtozas } from '../src/lib/beallitasok/tipusok';
import { nyelv } from '../src/lib/i18n';
import { naptarHid } from '../src/lib/naptar/hid.svelte';

function valasz(adat: unknown, statusz = 200) { return new Response(JSON.stringify(adat), { status: statusz, headers: { 'Content-Type': 'application/json' } }); }
function alap(): BeallitasokValasz { return { verzio: 1, rev: 'rev-1', ertek: alapBeallitasok(), munkater: { id: 'teszt', nev: 'Example notes', vault: '/synthetic/Example notes' }, setup_szukseges: true, ujrainditas: [] }; }
let lemez: BeallitasokValasz;
let keresek: { rev: string; valtozas: BeallitasokValtozas }[];
let kovetkezoHiba: number;

beforeEach(() => {
  nyelv.beallit('en');
  lemez = alap(); keresek = []; kovetkezoHiba = 0;
  naptarHid.fogad({ esemeny: 'nincs_dontes', emlekezteto: 'nincs_dontes' });
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    expect(url).toBe('/api/beallitasok');
    if (init?.method !== 'PUT') return valasz(lemez);
    const keres = JSON.parse(String(init.body)) as typeof keresek[number];
    keresek.push(keres);
    if (kovetkezoHiba) { const h = kovetkezoHiba; kovetkezoHiba = 0; return valasz({ hiba: 'Synthetic save failure' }, h); }
    if (keres.rev !== lemez.rev) return valasz({ hiba: 'Conflict' }, 409);
    for (const [k, v] of Object.entries(keres.valtozas)) Object.assign(lemez.ertek[k as keyof typeof lemez.ertek], v);
    lemez = { ...lemez, rev: 'rev-2', setup_szukseges: !lemez.ertek.setup.kesz };
    return valasz(lemez);
  }));
});
afterEach(() => { cleanup(); nyelv.beallit('hu'); naptarHid.fogad({}); vi.unstubAllGlobals(); });

async function megjelenit(plusz: { onai?: () => void; betoltetlen?: boolean } = {}) {
  const tar = new BeallitasokTar();
  if (!plusz.betoltetlen) tar.fogad(structuredClone(lemez));
  const onbezar = vi.fn(); const onkesz = vi.fn();
  const r = render(Setup, { props: { tar, onbezar, onkesz, onai: plusz.onai } });
  await waitFor(() => expect(r.getByRole('heading', { name: 'Welcome to Manifold' })).toBeTruthy());
  const tovabb = async () => { await fireEvent.click(r.getByRole('button', { name: 'Continue' })); };
  const aiig = async () => { for (let i = 0; i < 4; i++) await tovabb(); };
  const keszig = async () => { await aiig(); await fireEvent.click(r.getByRole('button', { name: 'Continue without AI' })); await tovabb(); };
  return { ...r, tar, onbezar, onkesz, tovabb, aiig, keszig };
}

describe('Setup actual workflow', () => {
  it('skips AI with Automatic selected and saves all choices in one request only on Finish', async () => {
    const r = await megjelenit();
    await r.tovabb();
    expect(r.getByText('/synthetic/Example notes')).toBeTruthy();
    await r.tovabb();
    expect((r.getByRole('radio', { name: /Automatic/ }) as HTMLInputElement).checked).toBe(true);
    expect(r.getByText(/automatically recognises the language/)).toBeTruthy();
    await r.tovabb();
    await fireEvent.click(r.getByRole('radio', { name: /Developer/ }));
    await r.tovabb();
    expect(r.queryByRole('button', { name: /Review AI/ })).toBeNull();
    await fireEvent.click(r.getByRole('button', { name: 'Continue without AI' }));
    expect(r.getByRole('switch', { name: 'Assistant' }).getAttribute('aria-checked')).toBe('true');
    await fireEvent.click(r.getByRole('switch', { name: 'Usage statistics' }));
    expect(keresek).toHaveLength(0);
    expect(r.tar.ertek.adatvedelem.tracker).toBe(true);
    await r.tovabb();
    await fireEvent.click(r.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(r.onkesz).toHaveBeenCalledTimes(1));
    expect(r.onbezar).toHaveBeenCalledTimes(1);
    expect(keresek).toHaveLength(1);
    expect(keresek[0]).toMatchObject({ rev: 'rev-1', valtozas: { altalanos: { nyelv: 'auto' }, adatvedelem: { tracker: false, asszisztens: true }, setup: { kesz: true, elmeny: 'fejleszto' }, modulok: { kod: true, kviz: false, hivatkozasok: true } } });
    expect(r.tar.adat?.setup_szukseges).toBe(false);
    expect(nyelv.kod).toBe('en');
  });

  it('keeps optional language and experience choices while moving Back, and Custom restores the original modules', async () => {
    lemez.ertek.modulok.graf = false;
    const r = await megjelenit();
    await r.tovabb(); await r.tovabb();
    await fireEvent.click(r.getByRole('radio', { name: 'Hungarian' }));
    await r.tovabb();
    await fireEvent.click(r.getByRole('radio', { name: /Student/ }));
    await fireEvent.click(r.getByRole('radio', { name: /Custom/ }));
    await fireEvent.click(r.getByRole('button', { name: 'Back' }));
    expect((r.getByRole('radio', { name: 'Hungarian' }) as HTMLInputElement).checked).toBe(true);
    await r.tovabb(); await r.tovabb();
    await fireEvent.click(r.getByRole('button', { name: 'Continue without AI' }));
    await r.tovabb();
    await fireEvent.click(r.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(r.onkesz).toHaveBeenCalled());
    expect(keresek[0].valtozas).toMatchObject({ altalanos: { nyelv: 'hu' }, modulok: { graf: false, kviz: true } });
  });

  it('asks for calendar permission only through the explicit action and can finish without permission', async () => {
    const postMessage = vi.fn();
    vi.stubGlobal('webkit', { messageHandlers: { manifold: { postMessage } } });
    const r = await megjelenit(); await r.aiig();
    await fireEvent.click(r.getByRole('button', { name: 'Continue without AI' }));
    expect(postMessage).not.toHaveBeenCalled();
    await fireEvent.click(r.getByRole('switch', { name: 'Calendar integration' }));
    expect(postMessage).not.toHaveBeenCalled();
    await fireEvent.click(r.getByRole('button', { name: 'Request calendar access' }));
    expect(postMessage).toHaveBeenCalledWith({ tipus: 'naptar-engedely', esemeny: true, emlekezteto: true });
    naptarHid.fogad({ esemeny: 'megtagadva', emlekezteto: 'megtagadva' });
    await waitFor(() => expect(r.getByRole('status').textContent).toContain('not allowed yet'));
    await r.tovabb(); await fireEvent.click(r.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(r.onkesz).toHaveBeenCalled());
    expect(keresek[0].valtozas.adatvedelem?.naptar).toBe(true);
  });

  it('shows a failed save, preserves the draft, and retries safely', async () => {
    const r = await megjelenit(); await r.keszig(); kovetkezoHiba = 503;
    await fireEvent.click(r.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(r.getByRole('alert').textContent).toContain('Could not save settings'));
    expect(r.onbezar).not.toHaveBeenCalled(); expect(r.tar.ertek.setup.kesz).toBe(false);
    await fireEvent.click(r.getByRole('button', { name: 'Try saving again' }));
    await waitFor(() => expect(r.onkesz).toHaveBeenCalled());
    expect(keresek).toHaveLength(2); expect(keresek[1]).toEqual(keresek[0]);
  });

  it('retains the draft revision across external updates and requires explicit reload on conflict', async () => {
    const r = await megjelenit(); await r.keszig();
    lemez.rev = 'external'; lemez.ertek.adatvedelem.tracker = false;
    r.tar.fogad(structuredClone(lemez));
    await fireEvent.click(r.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(r.getByRole('alert').textContent).toContain('Settings changed elsewhere'));
    expect(keresek[0].rev).toBe('rev-1'); expect(r.onbezar).not.toHaveBeenCalled();
    expect((r.getByRole('button', { name: 'Try saving again' }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(r.getByRole('button', { name: 'Reload and review' }));
    await waitFor(() => expect(r.getByRole('heading', { name: 'Your workspace' })).toBeTruthy());
    await r.tovabb(); await r.tovabb(); await r.tovabb();
    await fireEvent.click(r.getByRole('button', { name: 'Continue without AI' }));
    expect(r.getByRole('switch', { name: 'Usage statistics' }).getAttribute('aria-checked')).toBe('false');
    await r.tovabb(); await fireEvent.click(r.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(r.onkesz).toHaveBeenCalled());
    expect(keresek[1].rev).toBe('external');
  });

  it('traps focus and restores the opener on Escape without writing settings', async () => {
    const opener = document.createElement('button'); document.body.append(opener); opener.focus();
    const r = await megjelenit();
    const dialog = r.getByRole('dialog');
    const last = r.getByRole('button', { name: 'Continue' }); last.focus();
    await fireEvent.keyDown(last, { key: 'Tab' });
    expect(document.activeElement).toBe(r.getByRole('button', { name: 'Set up later' }));
    await fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(r.onbezar).toHaveBeenCalledTimes(1); expect(keresek).toHaveLength(0);
    r.unmount(); await waitFor(() => expect(document.activeElement).toBe(opener)); opener.remove();
  });

  it('opens AI tools only after successful setup when the user selected that action', async () => {
    const onai = vi.fn(); const r = await megjelenit({ onai }); await r.aiig();
    await fireEvent.click(r.getByRole('button', { name: 'Review AI tools after setup' }));
    expect(onai).not.toHaveBeenCalled();
    await r.tovabb(); await r.tovabb();
    await fireEvent.click(r.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(onai).toHaveBeenCalledTimes(1));
    expect(r.onkesz).toHaveBeenCalled();
  });

  it('blocks Escape and duplicate saves while the atomic save is in flight', async () => {
    const r = await megjelenit(); await r.keszig();
    let befejez!: (v: Response) => void;
    const iras = vi.fn(() => new Promise<Response>((felold) => { befejez = felold; }));
    vi.stubGlobal('fetch', iras);
    await fireEvent.click(r.getByRole('button', { name: 'Start writing' }));
    await waitFor(() => expect(r.getByRole('button', { name: 'Saving settings…' })).toBeTruthy());
    await fireEvent.keyDown(r.getByRole('dialog'), { key: 'Escape' });
    await fireEvent.click(r.getByRole('button', { name: 'Saving settings…' }));
    expect(r.onbezar).not.toHaveBeenCalled(); expect(iras).toHaveBeenCalledTimes(1);
    lemez.ertek.setup.kesz = true; lemez.setup_szukseges = false;
    befejez(valasz(lemez));
    await waitFor(() => expect(r.onkesz).toHaveBeenCalledTimes(1));
  });

  it('shows a load failure and recovers through explicit reload', async () => {
    const tar = new BeallitasokTar();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(valasz({ hiba: 'Synthetic load failure' }, 503)).mockResolvedValueOnce(valasz(lemez)));
    const r = render(Setup, { props: { tar, onbezar: vi.fn() } });
    await waitFor(() => expect(r.getByRole('alert').textContent).toContain('Could not load settings'));
    expect(r.queryByRole('button', { name: 'Continue' })).toBeNull();
    await fireEvent.click(r.getByRole('button', { name: 'Reload and review' }));
    await waitFor(() => expect(r.getByRole('heading', { name: 'Your workspace' })).toBeTruthy());
    expect(keresek).toHaveLength(0);
  });
});

it('all experience presets keep essential editor navigation and Custom copies values without mutation', () => {
  const eredeti = alapBeallitasok().modulok; eredeti.kereses = false;
  for (const id of ['diak', 'tudasmunka', 'fejleszto', 'kutato'] as const) {
    expect(elmenyModulok(id, eredeti)).toMatchObject({ kereses: true, gyorsvalto: true, hivatkozasok: true, asszisztens: true });
  }
  expect(eredeti.kereses).toBe(false);
  expect(elmenyModulok('egyeni', eredeti)).toEqual(eredeti);
  expect(elmenyModulok('egyeni', eredeti)).not.toBe(eredeti);
});
