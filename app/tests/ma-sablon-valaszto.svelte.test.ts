// A „Sablon beszúrása…” átfedés (C15): a core sablonlistája, ékezetfüggetlen szűrés, üres és hibás állapot, a választás
// bezár és beszúr a nyitott jegyzet kurzorához.

import { history } from '@codemirror/commands';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import SablonValaszto from '../src/ma/SablonValaszto.svelte';
import { szerkesztok, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';

const LISTA = {
  mappa: '_Template',
  sablonok: [
    { ut: '_Template/Napló.md', nev: 'Napló' },
    { ut: '_Template/Órarend.md', nev: 'Órarend' },
    { ut: '_Template/Zárthelyi.md', nev: 'Zárthelyi' },
  ],
};

let felulet: Felulet;
let context: Map<unknown, unknown>;
let kerelmek: { ut: string; torzs?: unknown }[];
let listaValasz: () => Response;

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  kerelmek = [];
  listaValasz = () => json(LISTA);
  vi.stubGlobal('fetch', async (url: string, o?: { body?: string }) => {
    kerelmek.push({ ut: url, torzs: o?.body ? JSON.parse(o.body) : undefined });
    if (url === '/api/sablon/lista') return listaValasz();
    return json({ szoveg: '## Beszúrt\n', kurzor: null, frontmatter: false });
  });
  felulet = new Felulet({});
  felulet.atfedes = 'sablon';
  context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  szerkesztok.beallit(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const mezo = () => screen.getByRole('combobox', { name: 'Sablon keresése' });

describe('lista és szűrés', () => {
  it('a core sablonjai név szerint, a mező fókuszban', async () => {
    render(SablonValaszto, { context });
    expect((await screen.findAllByRole('option')).map((o) => o.textContent?.trim())).toEqual(['Napló', 'Órarend', 'Zárthelyi']);
    expect(kerelmek[0].ut).toBe('/api/sablon/lista');
  });

  it('a szűrés ékezetfüggetlen', async () => {
    render(SablonValaszto, { context });
    await screen.findAllByRole('option');
    await fireEvent.input(mezo(), { target: { value: 'orar' } });
    expect(screen.getAllByRole('option').map((o) => o.textContent?.trim())).toEqual(['Órarend']);
    await fireEvent.input(mezo(), { target: { value: 'zzz' } });
    expect(screen.getByRole('status').textContent).toBe('Nincs találat erre: „zzz”');
  });

  it('üres sablonmappa: megmondja, melyik', async () => {
    listaValasz = () => json({ mappa: '_Template', sablonok: [] });
    render(SablonValaszto, { context });
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe('A sablonmappa (_Template) még üres.'));
  });

  it('a core hibája a listában jelenik meg', async () => {
    listaValasz = () => json({ hiba: 'a vault nem érhető el' }, 400);
    render(SablonValaszto, { context });
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe('a vault nem érhető el'));
  });
});

describe('választás', () => {
  it('az Enter bezárja az átfedést, és beszúr a nyitott jegyzet kurzorához', async () => {
    const hely = document.createElement('div');
    document.body.append(hely);
    const view = new EditorView({ state: EditorState.create({ doc: 'első\n', extensions: [history()], selection: { anchor: 5 } }), parent: hely });
    szerkesztok.beallit({ ut: 'Matek/Jegyzet.md', nezet: () => view, mod: () => 'elo', fokuszban: () => true } as unknown as SzerkesztoPeldany);
    render(SablonValaszto, { context });
    await screen.findAllByRole('option');
    await fireEvent.keyDown(mezo(), { key: 'ArrowDown' }); // Órarend
    await fireEvent.keyDown(mezo(), { key: 'Enter' });
    expect(felulet.atfedes).toBeNull();
    await waitFor(() => expect(view.state.doc.toString()).toBe('első\n## Beszúrt\n'));
    expect(kerelmek.filter((k) => k.ut !== '/api/asszisztens/tanul').at(-1)).toEqual({ ut: '/api/sablon/kiertekel', torzs: { ut: '_Template/Órarend.md', cim: 'Jegyzet' } });
  });

  it('C32b: „új jegyzet sablonból” módban a választás a fának ad kérést (név és létrehozás a fában), nem szúr be', async () => {
    felulet.sablonUj = { mappa: 'Matek' };
    render(SablonValaszto, { context });
    expect(screen.getByRole('dialog', { name: 'Új jegyzet sablonból' })).toBeTruthy();
    await screen.findAllByRole('option');
    await fireEvent.keyDown(mezo(), { key: 'ArrowDown' }); // Órarend
    await fireEvent.keyDown(mezo(), { key: 'Enter' });
    expect(felulet.atfedes).toBeNull();
    expect(felulet.sablonUj).toBeNull();
    expect(felulet.faUjSablon).toEqual({ mappa: 'Matek', sablon: '_Template/Órarend.md' });
    expect(felulet.oldalsav.nezet).toBe('fajlok');
    expect(kerelmek.map((k) => k.ut)).toEqual(['/api/sablon/lista']);        // nincs kiértékelés: azt a core végzi a létrehozáskor
  });

  it('C32b: az Esc az új-jegyzet módot is lezárja', async () => {
    felulet.sablonUj = { mappa: null };
    render(SablonValaszto, { context });
    await screen.findAllByRole('option');
    await fireEvent.keyDown(mezo(), { key: 'Escape' });
    expect(felulet.sablonUj).toBeNull();
    expect(felulet.faUjSablon).toBeNull();
  });

  it('az Esc bezárja az átfedést, kérés nélkül', async () => {
    render(SablonValaszto, { context });
    await screen.findAllByRole('option');
    await fireEvent.keyDown(mezo(), { key: 'Escape' });
    expect(felulet.atfedes).toBeNull();
    expect(kerelmek.map((k) => k.ut)).toEqual(['/api/sablon/lista']);
  });
});
