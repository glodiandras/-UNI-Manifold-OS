// CX-006 (80(d)): Élő nézetben a tulajdonság-blokk váltja a nyers YAML-t, Forrás módban a nyers szöveg marad. A widget
// írása a szerkesztő egyetlen tranzakciója (egy ⌘Z); a formai hibás frontmatter nem rejtőzik el (nyers szöveg +
// hibaüzenet); a kurzor nem parkol a widget mögötti, láthatatlan helyeken.

import { cursorDocStart, cursorLineUp, redo, undo, undoDepth } from '@codemirror/commands';
import { EditorSelection } from '@codemirror/state';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet, type SzerkesztoMod } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Szerkeszto from '../src/szerkeszto/Szerkeszto.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import { eloTulajdonsagMezo, torzsEleje } from '../src/szerkeszto/tulajdonsagok/elo.svelte';

const JO = '---\nTags:\n  - AI\nStatus: Completed\n---\n\n# Cím\n\nTörzs.\n';
const ROSSZ = '---\nTags: [AI\nStatus: Completed\n---\n\nTörzs.\n';
let lemez: Map<string, string>;

function valasz(kod: number, adat: unknown): Response {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  lemez = new Map([['J.md', JO]]);
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) {
      const t = lemez.get(u.searchParams.get('ut')!)!;
      return valasz(200, { ut: 'J.md', tartalom: t, hash: `h${t.length}`, jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      return valasz(200, { ok: true, ut: body.ut, hash: `h${body.tartalom.length}`, jel: '', uzenet: '', pillanat: null, elotte: null, git: true });
    }
    if (u.pathname === '/api/vault/sema') {
      return valasz(200, { mezosorrend: ['Tags', 'Source', 'Status', 'NN', 'Canvas'], extra_kulcsok: [], tags_ertekkeszlet: [], status_ertekkeszlet: ['Completed', 'In progress', 'Review'], status_gazdai: true, osztaly: { nev: 'normal', mezosorrend: [], ertekek: true, sema_nelkul: false } });
    }
    if (u.pathname === '/api/vault/tulajdonsagok/elemez') {
      const fm = (body.fm as string | null) ?? '';
      if (fm.includes('[AI\n')) {
        return valasz(200, { van: true, hiba: 'nem zárt lista (2. sor)', osztaly: 'normal', kulcsok: [], tulajdonsagok: [],
          problemak: [{ kod: 'yaml_hiba', szint: 'hiba', kulcs: null, ertek: null, uzenet: 'A frontmatter formai hibás: nem zárt lista (2. sor)' }] });
      }
      const st = /Status: (.*)/.exec(fm)?.[1] ?? null;
      return valasz(200, {
        van: !!fm, hiba: null, osztaly: 'normal', kulcsok: ['Tags', 'Status'], problemak: [],
        tulajdonsagok: [{ kulcs: 'Tags', tipus: 'tags', ertek: ['AI'], ervenyes: true }, { kulcs: 'Status', tipus: 'text', ertek: st, ervenyes: true }],
      });
    }
    if (u.pathname === '/api/vault/tulajdonsagok/modosit') {
      return valasz(200, { ok: true, valtozas: true, megerositheto: false, problemak: [], fm_uj: (body.fm as string).replace(/Status: .*/, `Status: ${body.ertek}`) });
    }
    return valasz(404, { hiba: 'nincs' });
  });
});

afterEach(() => {
  cleanup();
  szerkesztok.dokumentumok.eldob('J.md'); // a következő teszt a lemezről tölt (a módosított dokumentum nem öröklődik)
  vi.unstubAllGlobals();
});

function megjelenit(szerkesztoMod: SzerkesztoMod = 'elo') {
  const felulet = new Felulet({ csend: { be: false }, szerkesztoMod });
  const ful = $state({ id: `f-${Math.random()}`, ut: 'J.md' as string | null, nezet: undefined as Record<string, unknown> | undefined });
  const context = new Map<unknown, unknown>([
    [KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }],
  ]);
  return { ...render(Szerkeszto, { props: { ful, info: undefined, aktiv: true }, context }), felulet };
}

const view = () => szerkesztok.aktiv!.nezet()!;
const sorok = (c: HTMLElement) => [...c.querySelectorAll('.cm-content .cm-line')].map((l) => l.textContent ?? '');

describe('élő tulajdonságok a szerkesztőben (CX-006)', () => {
  it('Élő nézetben a widget áll a YAML helyén, a nyers sorok nem látszanak; a panel nem duplázódik', async () => {
    const { container } = megjelenit();
    await screen.findByLabelText('Status');
    const widget = container.querySelector('.cm-content .cm-tulajdonsagok');
    expect(widget).not.toBeNull();
    expect(widget!.querySelector('.tul')).not.toBeNull();
    expect(container.querySelectorAll('.tul')).toHaveLength(1);
    expect(sorok(container).some((s) => s.includes('Status: Completed') || s === '---')).toBe(false);
    expect(sorok(container)).toContain('Törzs.');
  });

  it('Forrás módban a nyers YAML látszik, widget és külön panel nélkül; a visszaváltás a widgetet hozza', async () => {
    const { container } = megjelenit('forras');
    await waitFor(() => expect(sorok(container)).toContain('Status: Completed'));
    expect(container.querySelector('.cm-tulajdonsagok')).toBeNull();
    expect(container.querySelector('.tul')).toBeNull();
    szerkesztok.aktiv!.forrasValt();
    await waitFor(() => expect(container.querySelector('.cm-tulajdonsagok')).not.toBeNull());
    expect(sorok(container)).not.toContain('Status: Completed');
  });

  it('a widget módosítása egy tranzakció: egy ⌘Z-lépés, és pontosan visszaáll', async () => {
    megjelenit();
    const mezo = await screen.findByLabelText('Status');
    const elotte = undoDepth(view().state);
    await fireEvent.change(mezo, { target: { value: 'Review' } });
    await waitFor(() => expect(view().state.doc.toString()).toBe(JO.replace('Completed', 'Review')));
    expect(undoDepth(view().state)).toBe(elotte + 1);
    expect(undo(view())).toBe(true);
    expect(view().state.doc.toString()).toBe(JO);
    expect(redo(view())).toBe(true);
    expect(view().state.doc.toString()).toBe(JO.replace('Completed', 'Review'));
  });

  it('a formai hibás frontmatter nyersen, szerkeszthetően látszik a hibaüzenettel; a javítás után visszaáll a widget', async () => {
    lemez.set('J.md', ROSSZ);
    const { container } = megjelenit();
    await waitFor(() => expect(view().state.field(eloTulajdonsagMezo).hiba).toBe('nem zárt lista (2. sor)'));
    const hiba = await screen.findByText(/A frontmatter formai hibás: nem zárt lista/);
    expect(hiba.getAttribute('role')).toBe('alert');
    expect(hiba.classList.contains('hiba')).toBe(true); // ikonos hibasor (alap.css), nem csak szín
    await waitFor(() => expect(sorok(container)).toContain('Tags: [AI'));
    expect(sorok(container)).toContain('Status: Completed');
    // a kurzor a nyers blokkban állhat (nem tolódik a törzsbe)
    view().dispatch({ selection: { anchor: 8 } });
    expect(view().state.selection.main.head).toBe(8);
    // javítás a nyers szövegben
    view().dispatch({ changes: { from: 'Tags: [AI'.length + 4, insert: ']' } });
    await waitFor(() => expect(sorok(container)).not.toContain('Tags: [AI]'));
    expect(screen.queryByText(/formai hibás/)).toBeNull();
    expect(container.querySelector('.cm-tulajdonsagok .tul')).not.toBeNull();
  });
});

describe('a kurzor a widget körül (CX-006, kettőzött caret)', () => {
  it('Élő nézetben a kezdő kurzor a törzs elejére kerül, nem a `---` elé', async () => {
    megjelenit();
    await screen.findByLabelText('Status');
    const hatar = JO.indexOf('---\n', 4) + 4;
    expect(torzsEleje(view().state)).toBe(hatar);
    expect(view().state.selection.main.head).toBe(hatar);
  });

  it('a dokumentum eleje (⌘↑) és a felfelé lépés sem viszi a widget mögé; a gépelés nem rontja el a frontmattert', async () => {
    megjelenit();
    await screen.findByLabelText('Status');
    const hatar = torzsEleje(view().state)!;
    view().dispatch({ selection: { anchor: view().state.doc.length } });
    cursorDocStart(view());
    expect(view().state.selection.main.head).toBe(hatar);
    cursorLineUp(view());
    expect(view().state.selection.main.head).toBe(hatar);
    view().dispatch({ selection: EditorSelection.create([EditorSelection.cursor(0), EditorSelection.cursor(hatar - 1)]) });
    expect(view().state.selection.ranges.map((r) => r.head)).toEqual([hatar]);
    view().dispatch(view().state.replaceSelection('x'));
    expect(view().state.doc.toString().startsWith('---\nTags:')).toBe(true);
    expect(view().state.doc.sliceString(hatar, hatar + 1)).toBe('x');
  });

  it('a kijelölés (nem üres tartomány) érintetlen; Forrás módban a kurzor a frontmatterbe állhat', async () => {
    megjelenit();
    await screen.findByLabelText('Status');
    view().dispatch({ selection: { anchor: 0, head: view().state.doc.length } });
    expect(view().state.selection.main.from).toBe(0);
    szerkesztok.aktiv!.forrasValt();
    view().dispatch({ selection: { anchor: 0 } });
    expect(view().state.selection.main.head).toBe(0);
  });
});
