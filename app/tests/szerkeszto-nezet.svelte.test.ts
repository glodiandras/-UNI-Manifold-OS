// A szerkesztő nézete (C08) jsdom-ban, ál-core-ral: betöltés, Live Preview / Olvasó váltás, automatikus
// mentés `elso`-val, a fül elhagyása lezár (`pillanat`). A WebKit-specifikus megjelenést a képernyőképes
// kör és a kézi próbák mérik; ez a komponens kötéseit védi.

import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { nyelv } from '../src/lib/i18n';
import { tartalmiNyelv } from '../src/lib/munkater/nyelv.svelte';
import { undoDepth } from '@codemirror/commands';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Szerkeszto from '../src/szerkeszto/Szerkeszto.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

interface Iras {
  ut: string;
  tartalom: string;
  alap: string;
  elso: boolean;
  pillanat: boolean;
}

let lemez: Map<string, string>;
let irasok: Iras[];
let fulSorszam = 0;

const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;

function valasz(kod: number, adat: unknown): Response {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  lemez = new Map([['Matek/Mértani.md', '# Mértani sorozat\n\nA $q$ hányados.\n']]);
  irasok = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) {
      const ut = u.searchParams.get('ut')!;
      const t = lemez.get(ut);
      if (t === undefined) return valasz(404, { hiba: 'nincs ilyen fájl' });
      return valasz(200, { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      const k = JSON.parse(String(init.body)) as Iras;
      const t = lemez.get(k.ut)!;
      if (hash(t) !== k.alap) return valasz(409, { hiba: 'ütközés', utkozes: true, hash: hash(t) });
      irasok.push(k);
      lemez.set(k.ut, k.tartalom);
      return valasz(200, { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: k.pillanat ? 'abc' : null, elotte: null, git: true });
    }
    return valasz(404, { hiba: 'nincs' });
  });
});

afterEach(() => {
  cleanup();
  nyelv.beallit('hu');
  tartalmiNyelv.beallit('');
  vi.unstubAllGlobals();
});

function megjelenit() {
  const felulet = new Felulet({});
  const ful = $state({ id: `f${++fulSorszam}`, ut: 'Matek/Mértani.md' as string | null, nezet: undefined as Record<string, unknown> | undefined });
  const context = new Map<unknown, unknown>([
    [KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }],
  ]);
  const r = render(Szerkeszto, { props: { ful, info: undefined, aktiv: true }, context });
  return { ...r, ful, felulet };
}

describe('a szerkesztő nézete', () => {
  it('betölt, a fejléc a jegyzet nevét mutatja; Live Preview-ban a képlet widget', async () => {
    const { container } = megjelenit();
    await waitFor(() => expect(container.querySelector('.cm-content')?.textContent).toContain('hányados'));
    expect(container.querySelector('.morzsa')!.textContent).toContain('Mértani');
    await waitFor(() => expect(container.querySelector('.cm-keplet .katex')).not.toBeNull());
    expect(szerkesztok.aktiv?.ut).toBe('Matek/Mértani.md');
  });

  it('⌘E: Olvasó és vissza; a mód a fül nézet-állapotába kerül', async () => {
    const { container, ful } = megjelenit();
    await waitFor(() => expect(container.querySelector('.cm-content')).not.toBeNull());
    szerkesztok.aktiv!.olvasoValt();
    await waitFor(() => expect(container.querySelector('.olvaso h1')?.textContent).toBe('Mértani sorozat'));
    expect(ful.nezet?.mod).toBe('olvaso');
    expect((container.querySelector('.cm-hely') as HTMLElement).hidden).toBe(true);
    szerkesztok.aktiv!.olvasoValt();
    await waitFor(() => expect((container.querySelector('.cm-hely') as HTMLElement).hidden).toBe(false));
    expect(ful.nezet?.mod).toBe('elo');
  });

  it('gépelés után 1 s-mal ment (`elso`); a nézet bezárása pillanatképpel zár', async () => {
    const { container, unmount } = megjelenit();
    await waitFor(() => expect(container.querySelector('.cm-content')).not.toBeNull());
    const v = szerkesztok.aktiv!.nezet()!;
    v.dispatch({ changes: { from: v.state.doc.length, insert: 'Új sor.\n' }, userEvent: 'input.type' });
    await waitFor(() => expect(irasok).toHaveLength(1), { timeout: 3000 });
    expect(irasok[0]).toMatchObject({ elso: true, pillanat: false });
    expect(irasok[0].tartalom.endsWith('Új sor.\n')).toBe(true);
    unmount();
    await waitFor(() => expect(irasok).toHaveLength(2), { timeout: 3000 });
    expect(irasok[1]).toMatchObject({ elso: false, pillanat: true });
  });

  it('a hiányzó jegyzet hibaüzenetet ad, nem dob', async () => {
    lemez.clear();
    const { container } = megjelenit();
    await waitFor(() => expect(container.querySelector('.betoltes-hiba')?.textContent).toContain('nincs meg'));
  });

  it('angol felületen is megőrzi a jegyzet nyelvét: szerkeszt, ment és olvasó nézetre vált', async () => {
    nyelv.beallit('en');
    vi.stubGlobal('webkit', { messageHandlers: { nyelv: { postMessage: async () => ({ nyelv: 'hu', bizalom: 0.99 }) } } });
    const { container, getByRole, ful } = megjelenit();
    await waitFor(() => expect(getByRole('textbox', { name: 'Note: Mértani' })).toBeTruthy());
    await waitFor(() => expect(getByRole('textbox', { name: 'Note: Mértani' }).getAttribute('lang')).toBe('hu'));
    expect(getByRole('button', { name: 'Reading view' })).toBeTruthy();
    const v = szerkesztok.aktiv!.nezet()!;
    const eredeti = '# Mértani sorozat\n\nA $q$ hányados.\n';
    expect(v.state.doc.toString()).toBe(eredeti);
    v.dispatch({ changes: { from: v.state.doc.length, insert: 'Saját jegyzet: ő és ű.\n' }, userEvent: 'input.type' });
    await waitFor(() => expect(irasok).toHaveLength(1), { timeout: 3000 });
    expect(lemez.get('Matek/Mértani.md')).toBe(eredeti + 'Saját jegyzet: ő és ű.\n');
    await waitFor(() => expect(container.querySelector('[data-mentes-jelzes]')?.getAttribute('aria-label')).toContain('Saved'));
    szerkesztok.aktiv!.olvasoValt();
    await waitFor(() => expect(container.querySelector('.olvaso')?.textContent).toContain('Saját jegyzet: ő és ű.'));
    expect(container.querySelector('.olvaso')?.getAttribute('lang')).toBe('hu');
    expect(ful.nezet?.mod).toBe('olvaso');
  });

  it('az automatikus nyelvfelismerés megőrzi a szöveget, kurzort és visszavonást', async () => {
    nyelv.beallit('en');
    const hivasok: ((v: { nyelv: string; bizalom: number }) => void)[] = [];
    vi.stubGlobal('webkit', { messageHandlers: { nyelv: { postMessage: () => new Promise((kesz) => { hivasok.push(kesz); }) } } });
    const { container } = megjelenit();
    await waitFor(() => expect(container.querySelector('.cm-content')).not.toBeNull());
    await waitFor(() => expect(hivasok).toHaveLength(1));
    const v = szerkesztok.aktiv!.nezet()!;
    v.dispatch({ changes: { from: v.state.doc.length, insert: 'Új szöveg.' }, userEvent: 'input.type' });
    const szoveg = v.state.doc.toString();
    const kurzor = v.state.selection.toJSON();
    const vissza = undoDepth(v.state);
    hivasok[0]({ nyelv: 'en', bizalom: 0.99 }); // a gépelés előtti válasz elavult
    await waitFor(() => expect(hivasok).toHaveLength(2), { timeout: 3000 });
    expect(v.contentDOM.lang).toBe('');
    hivasok[1]({ nyelv: 'hu', bizalom: 0.99 });
    await waitFor(() => expect(v.contentDOM.lang).toBe('hu'));
    expect(v.state.doc.toString()).toBe(szoveg);
    expect(v.state.selection.toJSON()).toEqual(kurzor);
    expect(undoDepth(v.state)).toBe(vissza);
    expect(nyelv.kod).toBe('en');
  });
});
