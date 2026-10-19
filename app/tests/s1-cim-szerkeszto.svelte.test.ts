// U01 a valódi szerkesztőben: ugyanaz a dokumentum, mentés, Undo és navigáció marad minden nézet alatt.
import { undo, redo } from '@codemirror/commands';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';
import Szerkeszto from '../src/szerkeszto/Szerkeszto.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import { hajtottAzonSoron } from '../src/szerkeszto/hajtogatas';
import { navigacioBeallit } from '../src/szerkeszto/linkek/navigacio';

const SZOVEG = '# Title\n\nBody. [[#Title|Back to title]]\n\n## Section\n\nChild.\n\n# Other\n\nRemain.\n';
let regiBeallitas: BeallitasokValasz | null;
let lemez: string;
let lemezHash: string;
let irasok: Record<string, unknown>[];
let csakOlvashato: boolean;
let sorozat = 0;
let ut: string;

function valasz(kod: number, adat: unknown) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}
beforeEach(() => {
  regiBeallitas = beallitasok.adat;
  const ertek = alapBeallitasok();
  ertek.modulok.tulajdonsagok = false; ertek.modulok.cimkek = false;
  beallitasok.fogad({ verzio: 1, rev: 'synthetic-title', ertek, munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
  ut = `Synthetic-${++sorozat}/Title.md`;
  lemez = SZOVEG; lemezHash = 'original-bytes'; irasok = []; csakOlvashato = false;
  linkek.ervenytelenit();
  vi.stubGlobal('fetch', async (input: string, init?: RequestInit) => {
    const u = new URL(input, 'http://127.0.0.1');
    if (u.pathname === '/api/vault/fajl') {
      if (!init?.method || init.method === 'GET') return valasz(200, { ut, tartalom: lemez, hash: lemezHash, jel: '', mtime: 0, kodolas_hiba: csakOlvashato });
      if (init.method === 'PUT') {
        const k = JSON.parse(String(init.body)); irasok.push(k);
        if (k.alap !== lemezHash) return valasz(409, { hiba: 'CAS conflict' });
        lemez = k.tartalom; lemezHash = `saved-${irasok.length}`;
        return valasz(200, { ok: true, ut, hash: lemezHash, jel: '', uzenet: '', pillanat: k.pillanat ? 'snapshot' : null, elotte: null, git: true });
      }
    }
    if (u.pathname === '/api/vault/beagyazas') return valasz(200, { tipus: 'jegyzet', ut, szoveg: lemez, kezd: 1, alcel_hiba: false });
    return valasz(404, { hiba: 'No synthetic route' });
  });
});
afterEach(async () => {
  await szerkesztok.dokumentumok.mindLezar();
  cleanup();
  await szerkesztok.dokumentumok.mindLezar();
  szerkesztok.dokumentumok.eldob(ut);
  beallitasok.adat = regiBeallitas;
  navigacioBeallit(null);
  vi.unstubAllGlobals();
});
async function nyit(mod: 'elo' | 'forras' | 'olvaso' = 'elo') {
  const felulet = new Felulet({ csend: { be: false } });
  const ful = $state({ id: `title-${sorozat}`, ut: ut as string | null, nezet: { mod } as Record<string, unknown> });
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }]]);
  const c = render(Szerkeszto, { props: { ful, info: undefined, aktiv: true }, context });
  await waitFor(() => expect(szerkesztok.aktiv?.ut === ut && szerkesztok.aktiv.nezet()).toBeTruthy());
  await tick();
  return { ...c, felulet, p: szerkesztok.aktiv!, view: szerkesztok.aktiv!.nezet()!, title: c.getByLabelText('Jegyzet fájlneve') as HTMLInputElement };
}

describe('U01 a teljes szerkesztőben', () => {
  it('LP/Source/Reading váltás csak a megismételt első H1 látványát vonja össze, nem ír és nem hoz létre Undo-t', async () => {
    const c = await nyit();
    expect(c.title.value).toBe('Title');
    expect(c.view.contentDOM.textContent).not.toContain('# Title');
    expect(c.view.contentDOM.textContent).toContain('Other');
    expect(c.p.vazlat().map(e => e.szoveg)).toEqual(['Title', 'Section', 'Other']);
    c.p.forrasValt(); await tick();
    expect(c.view.contentDOM.textContent).toContain('# Title');
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
    c.p.olvasoValt();
    await waitFor(() => expect(c.container.querySelector('.olvaso > h1')).not.toBeNull());
    const cimsorok = [...c.container.querySelectorAll<HTMLElement>('.olvaso > h1')];
    expect(cimsorok[0].hidden).toBe(true);
    expect(cimsorok[1].hidden).toBe(false);
    expect(cimsorok[1].textContent).toBe('Other');
    c.p.olvasoValt(); await tick();
    c.p.forrasValt(); await tick();
    expect(c.p.mod()).toBe('elo');
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
    expect(undo(c.view)).toBe(false);
    expect(irasok).toEqual([]);
  });

  it('eltérő vagy későbbi azonos H1 a Readingben is megmarad', async () => {
    lemez = '# Different\n\nBody\n\n# Title\n\nMore\n';
    const c = await nyit('olvaso');
    await waitFor(() => expect(c.container.querySelectorAll('.olvaso > h1')).toHaveLength(2));
    expect([...c.container.querySelectorAll<HTMLElement>('.olvaso > h1')].every(h => !h.hidden)).toBe(true);
    expect(c.view.state.doc.toString()).toBe(lemez);
    expect(irasok).toEqual([]);
  });

  it('Outline közös ugrási útja és a valódi Reader heading-link a látható címre fókuszál; Source az eredeti sorra ugrik', async () => {
    const c = await nyit();
    szerkesztok.ugras(ut, 1);
    expect(document.activeElement).toBe(c.title);
    szerkesztok.ugras(ut, 5);
    expect(c.view.state.selection.main.head).toBe(c.view.state.doc.line(5).from);
    expect(c.view.hasFocus).toBe(true);
    c.p.forrasValt(); await tick();
    szerkesztok.ugras(ut, 1);
    expect(c.view.state.selection.main.head).toBe(0);
    expect(c.view.hasFocus).toBe(true);
    c.p.olvasoValt();
    const megnyit = vi.fn(); navigacioBeallit({ megnyit });
    await waitFor(() => expect(c.container.querySelector('.olvaso .wikilink')).not.toBeNull());
    c.view.focus();
    await fireEvent.click(c.container.querySelector('.olvaso .wikilink')!);
    await waitFor(() => expect(document.activeElement).toBe(c.title));
    expect(megnyit).not.toHaveBeenCalled();
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
  });

  it('az összevont cím gombja a meglévő source-fold állapotot használja, és Readingben is megmarad a hajtás', async () => {
    const c = await nyit();
    const gomb = c.container.querySelector<HTMLButtonElement>('.fajlcim .hajto')!;
    expect(gomb.getAttribute('aria-expanded')).toBe('true');
    await fireEvent.click(gomb);
    expect(hajtottAzonSoron(c.view.state, 0)).not.toBeNull();
    c.p.olvasoValt();
    await waitFor(() => expect(c.container.querySelector('.olvaso > p')).not.toBeNull());
    const body = c.container.querySelector<HTMLElement>('.olvaso > p')!;
    expect(body.hidden).toBe(true);
    expect(c.container.querySelector<HTMLElement>('.olvaso > h1')!.hidden).toBe(true);
    expect([...c.container.querySelectorAll<HTMLElement>('.olvaso > h1')][1].hidden).toBe(false);
    await fireEvent.click(gomb);
    expect(body.hidden).toBe(false);
    expect(c.container.querySelector<HTMLElement>('.olvaso > h1')!.hidden).toBe(true);
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
    expect(irasok).toEqual([]);
  });

  it('a törzsszerkesztés a szokásos CAS-mentésen és egy Undo/Redo lépésen halad, az eredeti H1 bájtjai megmaradnak', async () => {
    // A dokumentum megőrzi a valódi CRLF-et is; CodeMirror belül LF-et használ.
    lemez = SZOVEG.replaceAll('\n', '\r\n');
    const eredeti = lemez;
    const c = await nyit();
    const pos = c.view.state.doc.toString().indexOf('Body.');
    c.view.dispatch({ changes: { from: pos, to: pos + 5, insert: 'Edited.' }, userEvent: 'input.type' });
    await c.p.mentes();
    expect(irasok[0].alap).toBe('original-bytes');
    expect(lemez).toBe(eredeti.replace('Body.', 'Edited.'));
    expect(undo(c.view)).toBe(true);
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
    await c.p.mentes();
    expect(irasok.at(-1)!.alap).toBe('saved-1');
    expect(lemez).toBe(eredeti);
    expect(redo(c.view)).toBe(true);
    expect(c.view.state.doc.toString()).toBe(SZOVEG.replace('Body.', 'Edited.'));
  });

  it('readonly jegyzet címe navigálható a wrapperre, de nem szerkeszthető és nem ír', async () => {
    csakOlvashato = true;
    const c = await nyit();
    expect(c.title.disabled).toBe(true);
    szerkesztok.ugras(ut, 1);
    expect(document.activeElement).toBe(c.container.querySelector('.fajlcim'));
    expect(c.view.state.readOnly).toBe(true);
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
    expect(irasok).toEqual([]);
  });
});
