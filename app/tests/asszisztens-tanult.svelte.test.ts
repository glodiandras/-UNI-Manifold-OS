// „Mit tanult az asszisztens” (J1) és a javaslat-kártya felülete (J3): a lista minden tétele egyenként törölhető (a core-nak a
// fajtát és a kulcsot küldi), a „Mind törlése” kétlépcsős; a kártya Igen/Nem gombjai a kártya-állapotot hívják, fókuszt nem kérnek.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import AsszisztensTanult from '../src/hej/vezerlo/AsszisztensTanult.svelte';
import JavaslatKartya from '../src/lib/asszisztens/JavaslatKartya.svelte';
import { kartyaAllapot } from '../src/lib/asszisztens/kartya.svelte';
import type { TanultLista } from '../src/lib/asszisztens/tipusok';

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

const LISTA = (): TanultLista => ({
  kapcsolo: true,
  mintak: [{ elotte: 'Megoldom a feladatot', szoveg: ' és ellenőrzöm.' }],
  muveletek: [{ kulcs: 'aaaaaaaaaaaa', muvelet: 'cimke', muvelet_nev: 'címke', mappa: 'M - Matek', ertek: 'Analízis', db: 4, tanult: true }],
  elutasitott: [{ kulcs: 'szerkezet:0123456789ab', tipus: 'szerkezet', cim: 'Mit szólnál egy „Példák” szakaszhoz?' }],
  hangolas: [{ kulcs: 'link|szoveg', tipus: 'link', tipus_nev: 'linkjavaslat', helyzet: 'szoveg', elfogad: 1, elutasit: 3, szint: 'ritkabb' }],
});

let kerelmek: { url: string; metodus: string; torzs: unknown }[];

beforeEach(() => {
  kerelmek = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const metodus = init?.method ?? 'GET';
    const torzs = init?.body ? JSON.parse(String(init.body)) : null;
    kerelmek.push({ url: u.pathname, metodus, torzs });
    if (u.pathname === '/api/asszisztens/tanult') return json(LISTA());
    if (u.pathname === '/api/asszisztens/tanult/torles') return json({ ok: true, ...LISTA(), muveletek: [] });
    if (u.pathname === '/api/asszisztens/kartya/dontes') return json({ fogadva: true });
    return json({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  kartyaAllapot.elrejt(null);
  vi.unstubAllGlobals();
  document.body.textContent = '';
});

describe('Mit tanult az asszisztens', () => {
  it('a négy fajta látszik, és a sor törlése a fajtát és a kulcsot küldi', async () => {
    render(AsszisztensTanult);
    await screen.findByText(/Mit tanult az asszisztens/);
    await screen.findByText(/címke „Analízis” · M - Matek · 4×/);
    expect(screen.getByText(/linkjavaslat, szövegben: 1 igen \/ 3 nem · ritkábban javasol/)).toBeTruthy();
    expect(screen.getByText('Mit szólnál egy „Példák” szakaszhoz?')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'A művelet-minta törlése: Analízis' }));
    await waitFor(() => expect(kerelmek.some((k) => k.url === '/api/asszisztens/tanult/torles')).toBe(true));
    expect(kerelmek.find((k) => k.url === '/api/asszisztens/tanult/torles')!.torzs).toEqual({ fajta: 'muvelet', kulcs: 'aaaaaaaaaaaa' });
    await waitFor(() => expect(screen.queryByText(/címke „Analízis”/)).toBeNull());
  });

  it('a „Mind törlése” megerősítés nélkül nem töröl', async () => {
    render(AsszisztensTanult);
    await screen.findByText(/címke „Analízis”/);
    await fireEvent.click(screen.getByRole('button', { name: 'Mind törlése…' }));
    expect(kerelmek.some((k) => k.url === '/api/asszisztens/tanult/torles')).toBe(false);
    await fireEvent.click(screen.getByRole('button', { name: 'Igen, mindent törlök' }));
    await waitFor(() => expect(kerelmek.find((k) => k.url === '/api/asszisztens/tanult/torles')?.torzs).toEqual({ fajta: 'mind' }));
  });
});

describe('a javaslat-kártya', () => {
  it('Igen beír a szerkesztőbe, a fókusz a szerkesztőn marad', async () => {
    const parent = document.body.appendChild(document.createElement('div'));
    const v = new EditorView({ parent, state: EditorState.create({ doc: 'Szöveg' }) });
    v.focus();
    render(JavaslatKartya);
    kartyaAllapot.mutat({ azon: 'szerkezet:0123456789ab', tipus: 'szerkezet', helyzet: 'szunet_rovid', cim: 'Mit szólnál egy „Példák” szakaszhoz?',
      indok: 'A mappa 4 másik jegyzetéből 3-ban van ilyen szakasz.', allas: 'batrabb', muvelet: { fajta: 'szakasz', szoveg: '## Példák' } },
      v, { ut: 'A.md', linkCel: async (c) => c });
    const dialog = await screen.findByRole('dialog', { name: 'Mit szólnál egy „Példák” szakaszhoz?' });
    expect(dialog.getAttribute('aria-modal')).toBe('false');
    expect(document.activeElement).toBe(v.contentDOM);
    await fireEvent.click(screen.getByRole('button', { name: 'Igen' }));
    await waitFor(() => expect(v.state.doc.toString()).toBe('Szöveg\n\n## Példák\n'));
    await waitFor(() => expect(kerelmek.find((k) => k.url === '/api/asszisztens/kartya/dontes')?.torzs).toMatchObject({ dontes: 'elfogad' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    v.destroy();
  });
});
