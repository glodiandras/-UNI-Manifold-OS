// Outline UI → a valódi editor tranzakciója → Dokumentum → CAS. Nem második szakaszmozgató implementáció.
import { undo, redo } from '@codemirror/commands';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Vazlat from '../src/hej/kapcsolatok/Vazlat.svelte';
import { vazlatAllapot } from '../src/hej/kapcsolatok/vazlatAllapot.svelte';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Szerkeszto from '../src/szerkeszto/Szerkeszto.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const INTRO = '---\nUnknown: preserved\n---\n\nIntro.\n\n';
const PARENT = '# Parent\n\np\n\n## Álgebra\n\na\n\n## Keep\n\nk\n\n';
const BETA = '# Beta\n\nb\n\n';
const TAIL = '# Gamma\n\ng\n\n# Delta\n\nd\n';
const SZOVEG = INTRO + PARENT + BETA + TAIL;
let ut: string, lemez: string, hash: string;
let csakOlvashato: boolean, elutasit: boolean;
let irasok: Record<string, unknown>[];
let sorszam = 0;
const json = (x: unknown, status = 200) => new Response(JSON.stringify(x), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  ut = `Synthetic-outline-${++sorszam}.md`; lemez = SZOVEG.replaceAll('\n', '\r\n'); hash = 'original';
  irasok = []; csakOlvashato = false; elutasit = false; vazlatAllapot.torol();
  const ertek = alapBeallitasok(); ertek.modulok.cimkek = false; ertek.modulok.tulajdonsagok = false;
  beallitasok.fogad({ verzio: 1, rev: 'synthetic', ertek, munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
  vi.stubGlobal('fetch', async (input: string, init?: RequestInit) => {
    const u = new URL(input, 'http://127.0.0.1');
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) return json({ ut, tartalom: lemez, hash, jel: '', mtime: 0, kodolas_hiba: csakOlvashato });
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      const k = JSON.parse(String(init.body)); irasok.push(k);
      if (elutasit || k.alap !== hash) return json({ hiba: 'Synthetic CAS conflict', utkozes: true, hash: 'external' }, 409);
      lemez = k.tartalom; hash = `saved-${irasok.length}`;
      return json({ ok: true, ut, hash, jel: '', uzenet: '', pillanat: k.pillanat ? 'snapshot' : null, elotte: null, git: true });
    }
    return json({ hiba: 'No synthetic route' }, 404);
  });
});
afterEach(async () => {
  await szerkesztok.dokumentumok.mindLezar(); cleanup();
  await szerkesztok.dokumentumok.mindLezar(); szerkesztok.dokumentumok.eldob(ut);
  vazlatAllapot.torol(); beallitasok.adat = null; vi.unstubAllGlobals();
});

async function nyit() {
  const ful = $state({ id: `outline-${sorszam}`, ut: ut as string | null });
  const felulet = new Felulet({ csend: { be: false } });
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }]]);
  render(Szerkeszto, { props: { ful, aktiv: true, info: undefined }, context });
  await waitFor(() => expect(szerkesztok.aktiv?.ut === ut && szerkesztok.aktiv.nezet()).toBeTruthy());
  const c = render(Vazlat);
  await waitFor(() => expect(c.getByRole('button', { name: 'Parent' })).toBeTruthy());
  return { ...c, p: szerkesztok.aktiv!, view: szerkesztok.aktiv!.nezet()! };
}
const sor = (c: Awaited<ReturnType<typeof nyit>>, nev: string) => c.getByRole('button', { name: nev }).closest('li')!;
const adat = () => ({ setData: vi.fn(), effectAllowed: 'none', dropEffect: 'none' });
async function huz(c: Awaited<ReturnType<typeof nyit>>, kozben?: () => void) {
  const dt = adat();
  await fireEvent.dragStart(sor(c, 'Parent'), { dataTransfer: dt });
  kozben?.(); await tick();
  await fireEvent.dragOver(sor(c, 'Beta'), { clientY: 1, dataTransfer: dt }); // jsdom rect 0 → az „után” fél
  await fireEvent.drop(sor(c, 'Beta'), { dataTransfer: dt }); await tick();
}

describe('S1 Outline fogyasztói: tree/filter/drag és meglévő mentés', () => {
  it('az összecsukás és az ékezetfüggetlen szűrő a valódi sorokon együtt működik, a találat forrássorára navigál', async () => {
    const c = await nyit();
    await fireEvent.click(c.getByRole('button', { name: 'Szakasz összecsukása: Parent' }));
    expect(c.queryByRole('button', { name: 'Álgebra' })).toBeNull();
    const szuro = c.getByRole('textbox', { name: 'Fejezetek szűrése' });
    await fireEvent.input(szuro, { target: { value: 'algebra' } });
    expect(c.getByRole('button', { name: 'Parent' }).classList.contains('halvany')).toBe(true);
    const cel = c.getByRole('button', { name: 'Álgebra' });
    expect(c.queryByRole('button', { name: 'Beta' })).toBeNull();
    await fireEvent.click(cel);
    expect(c.view.state.selection.main.head).toBe(c.view.state.doc.lineAt(SZOVEG.indexOf('## Álgebra')).from);
    await fireEvent.keyDown(szuro, { key: 'Escape' });
    expect(c.queryByRole('button', { name: 'Álgebra' })).toBeNull();
    await fireEvent.click(c.getByRole('button', { name: 'Összes kibontása' }));
    expect(c.getByRole('button', { name: 'Álgebra' })).toBeTruthy();
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
    expect(irasok).toEqual([]);
    expect(undo(c.view)).toBe(false);
  });

  it('drag → egy tranzakció → CAS-mentés → Undo/Redo a teljes alfejezetet és CRLF bájtokat megőrzi', async () => {
    const c = await nyit();
    await huz(c);
    const vart = INTRO + BETA + PARENT + TAIL;
    expect(c.view.state.doc.toString()).toBe(vart);
    expect(document.activeElement).toBe(c.getByRole('button', { name: 'Parent' }));
    await c.p.mentes();
    expect(irasok[0].alap).toBe('original');
    expect(lemez).toBe(vart.replaceAll('\n', '\r\n'));
    expect(undo(c.view)).toBe(true); await c.p.mentes();
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
    expect(irasok.at(-1)!.alap).toBe('saved-1');
    expect(lemez).toBe(SZOVEG.replaceAll('\n', '\r\n'));
    expect(redo(c.view)).toBe(true);
    expect(c.view.state.doc.toString()).toBe(vart);
  });

  it('drag alatt megváltozott dokumentum elutasítja a régi verziót, az új szöveg és sorrend megmarad', async () => {
    const c = await nyit();
    await huz(c, () => c.view.dispatch({ changes: { from: c.view.state.doc.length, insert: 'Typed meanwhile\n' }, userEvent: 'input.type' }));
    expect(c.view.state.doc.toString()).toBe(SZOVEG + 'Typed meanwhile\n');
    expect(c.getByRole('alert').textContent).toContain('A jegyzet közben megváltozott');
    expect(irasok).toEqual([]);
  });

  it('409-nél a lemez változatlan, a mozgatott draft megmarad; új drag/move nem írhat az ütközésre', async () => {
    const c = await nyit();
    const eredeti = lemez; await huz(c); elutasit = true;
    await c.p.mentes(); await tick();
    expect(szerkesztok.dokumentumok.kap(ut)!.allapot).toBe('utkozes');
    expect(lemez).toBe(eredeti);
    expect(c.view.state.doc.toString()).toBe(INTRO + BETA + PARENT + TAIL);
    expect(sor(c, 'Parent').draggable).toBe(false);
    const elo = c.view.state.doc.toString();
    await fireEvent.keyDown(c.getByRole('button', { name: 'Parent' }), { key: 'ArrowUp', altKey: true });
    expect(c.getByRole('alert').textContent).toContain('Mentési ütközés');
    expect(c.view.state.doc.toString()).toBe(elo);
    expect(irasok).toHaveLength(1);
  });

  it.each(['olvaso', 'readonly'] as const)('%s alatt a mozgatás tiltott és a billentyű sem ír', async mod => {
    csakOlvashato = mod === 'readonly';
    const c = await nyit();
    if (mod === 'olvaso') { c.p.olvasoValt(); await tick(); }
    expect(sor(c, 'Parent').draggable).toBe(false);
    await fireEvent.keyDown(c.getByRole('button', { name: 'Parent' }), { key: 'ArrowDown', altKey: true });
    expect(c.getByRole('alert').textContent).toContain(mod === 'olvaso' ? 'Olvasó módban' : 'csak olvasható');
    expect(c.view.state.doc.toString()).toBe(SZOVEG);
    expect(irasok).toEqual([]);
  });
});
