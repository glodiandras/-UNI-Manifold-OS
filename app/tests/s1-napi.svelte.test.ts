import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { EditorSelection, EditorState, StateEffect } from '@codemirror/state';
import { history, undo } from '@codemirror/commands';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Beallitasok from '../src/beallitasok/Beallitasok.svelte';
import SablonFormatum from '../src/beallitasok/SablonFormatum.svelte';
import { beallitasAblak } from '../src/beallitasok/allapot.svelte';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { beallitasokApi } from '../src/lib/beallitasok/api';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { ApiHiba } from '../src/lib/core/api';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { nyelv } from '../src/lib/i18n';
import * as napiApi from '../src/ma/api';
import { napiIndito } from '../src/ma/inditas';
import { maTelepit } from '../src/ma';
import { datumIdoBeszur, napiJegyzetNyit, naploSzomszedNyit } from '../src/ma/naplo';
import { szerkesztok, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';

const adat = (): BeallitasokValasz => ({ verzio: 1, rev: 'r1', ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
const json = (x: unknown) => new Response(JSON.stringify(x), { status: 200, headers: { 'Content-Type': 'application/json' } });
const kesleltet = <T,>() => { let kesz!: (v: T) => void; const p = new Promise<T>(r => kesz = r); return { p, kesz }; };
let view: EditorView | undefined;
beforeEach(() => { nyelv.beallit('en'); ertesitesek.lista.length = 0; });
afterEach(() => { cleanup(); view?.destroy(); view = undefined; szerkesztok.beallit(null); beallitasok.adat = null; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); nyelv.beallit('hu'); });

describe('S1 napi settings', () => {
  it.each([400, 409])('a hat új mezőt pontosan menti, %i után az értékek és a régi rev megmaradnak', async (statusz) => {
    beallitasAblak.szakasz = 'fajlok';
    const tar = new BeallitasokTar(); tar.fogad(adat());
    vi.spyOn(napiApi, 'mostSzoveg').mockResolvedValue({ szoveg: 'preview', formatum: 'x', ismeretlen: [] });
    const put = vi.spyOn(beallitasokApi, 'ment').mockRejectedValueOnce(new ApiHiba(statusz, 'Synthetic error'));
    render(Beallitasok, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
    await fireEvent.input(screen.getByLabelText('Template date format'), { target: { value: 'DD.MM.YYYY' } });
    await fireEvent.input(screen.getByLabelText('Template time format'), { target: { value: 'h:mm A' } });
    await fireEvent.input(screen.getByLabelText('Daily note template'), { target: { value: 'Other/Daily.md' } });
    await fireEvent.click(screen.getByLabelText('Open daily note on startup'));
    await fireEvent.change(screen.getByLabelText('After extracting a selection'), { target: { value: 'beagyazas' } });
    await fireEvent.input(screen.getByLabelText('Extraction template'), { target: { value: 'Other/Extract.md' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(tar.hiba).not.toBeNull());
    expect(tar.utkozes).toBe(statusz === 409);
    const ertek = { sablon_datum: 'DD.MM.YYYY', sablon_ido: 'h:mm A', napi_sablon: 'Other/Daily.md', napi_inditaskor: true, kivonas_utana: 'beagyazas', kivonas_sablon: 'Other/Extract.md' };
    expect(put.mock.calls[0]).toEqual(['r1', { fajlok: { ...alapBeallitasok().fajlok, ...ertek } }]);
    expect((screen.getByLabelText('Daily note template') as HTMLInputElement).value).toBe('Other/Daily.md');
    const saved = adat(); saved.rev = 'r2'; Object.assign(saved.ertek.fajlok, ertek);
    put.mockResolvedValueOnce(saved);
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(tar.adat?.rev).toBe('r2'));
    expect(tar.ertek.fajlok).toMatchObject(ertek);
  });

  it('az előnézet régi válasza és a lebontott mező válasza eldobódik; az ismeretlen token látható', async () => {
    vi.useFakeTimers();
    const elso = kesleltet<napiApi.MostSzoveg>(), masodik = kesleltet<napiApi.MostSzoveg>();
    vi.spyOn(napiApi, 'mostSzoveg').mockReturnValueOnce(elso.p).mockReturnValueOnce(masodik.p);
    const { unmount } = render(SablonFormatum, { props: { fajta: 'date', cimke: 'Format', ertek: 'YYYY' } });
    flushSync(); await vi.advanceTimersByTimeAsync(180);
    await fireEvent.input(screen.getByLabelText('Format'), { target: { value: 'YYYY z' } });
    await vi.advanceTimersByTimeAsync(180);
    masodik.kesz({ szoveg: '2026 z', formatum: 'YYYY z', ismeretlen: ['z'] });
    await vi.advanceTimersByTimeAsync(0); flushSync();
    expect(screen.getByText('Preview: 2026 z')).toBeTruthy();
    expect(screen.getByText(/Unsupported format tokens remain literal: z/)).toBeTruthy();
    elso.kesz({ szoveg: 'OLD', formatum: 'YYYY', ismeretlen: [] });
    await vi.advanceTimersByTimeAsync(0); flushSync();
    expect(screen.queryByText('Preview: OLD')).toBeNull();
    unmount();
    expect(document.querySelector('input')).toBeNull();
  });
});

function szerkeszto(doc = 'abc def') {
  view = new EditorView({ state: EditorState.create({ doc, selection: EditorSelection.create([EditorSelection.range(0, 3), EditorSelection.range(4, 7)]), extensions: [history(), EditorState.allowMultipleSelections.of(true)] }), parent: document.body });
  const p = { ut: 'Notes/Test.md', nezet: () => view!, mod: () => 'elo' } as unknown as SzerkesztoPeldany;
  szerkesztok.beallit(p);
  return view;
}

describe('S1 napi műveletek', () => {
  it('dátum/idő minden kijelölést egy Undo-lépésben cserél, a formázás a core-é', async () => {
    const v = szerkeszto();
    const most = vi.spyOn(napiApi, 'mostSzoveg').mockResolvedValue({ szoveg: '18/10/2026', formatum: 'DD/MM/YYYY', ismeretlen: [] });
    await datumIdoBeszur('date');
    expect(most).toHaveBeenCalledWith('date');
    expect(v.state.doc.toString()).toBe('18/10/2026 18/10/2026');
    expect(undo(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('abc def');
  });

  it.each(['jegyzet', 'szoveg', 'kijeloles', 'readonly'] as const)('késői dátumválasz nem ír, ha megváltozott: %s', async (valtozas) => {
    const v = szerkeszto();
    const r = kesleltet<napiApi.MostSzoveg>();
    vi.spyOn(napiApi, 'mostSzoveg').mockReturnValue(r.p);
    const p = datumIdoBeszur('time');
    if (valtozas === 'jegyzet') szerkesztok.beallit(null);
    if (valtozas === 'szoveg') v.dispatch({ changes: { from: 0, insert: 'X' } });
    if (valtozas === 'kijeloles') v.dispatch({ selection: { anchor: 1 } });
    if (valtozas === 'readonly') v.dispatch({ effects: StateEffect.reconfigure.of([EditorState.readOnly.of(true)]) });
    const alap = v.state.doc.toString();
    r.kesz({ szoveg: '10:20', formatum: 'HH:mm', ismeretlen: [] }); await p;
    expect(v.state.doc.toString()).toBe(alap);
    expect(ertesitesek.lista.at(-1)?.cim).toBe('Insertion canceled');
  });

  it('a napi template fallback és snapshot-hiba külön látszik; meglévő jegyzetnél nincs false fallback', async () => {
    const f = new Felulet({});
    const fetch = vi.fn().mockResolvedValueOnce(json({ ut: 'Daily/2026-10-18.md', letrejott: true, kurzor: 0, figyelmeztetes: 'Snapshot failed', sablon_hiany: 'Templates/Missing.md' }))
      .mockResolvedValueOnce(json({ ut: 'Daily/2026-10-18.md', letrejott: false, kurzor: null, figyelmeztetes: null, sablon_hiany: 'Templates/Missing.md' }));
    vi.stubGlobal('fetch', fetch);
    await napiJegyzetNyit(f);
    expect(ertesitesek.lista.map(e => e.cim)).toEqual(['Daily note created', 'Saved without a snapshot', 'Daily template unavailable']);
    expect(ertesitesek.lista.at(-1)?.szoveg).toContain('Templates/Missing.md');
    ertesitesek.lista.length = 0;
    await napiJegyzetNyit(f);
    expect(ertesitesek.lista).toHaveLength(0);
  });

  it('az előző/következő napot a core az aktív út alapján oldja fel, a frontend nem számol fájlnevet', async () => {
    const f = new Felulet({}); f.munkaterulet.megnyit('Journal/2024/Dec/31.md');
    const fetch = vi.fn().mockResolvedValue(json({ ut: 'Journal/2025/Jan/01.md', datum: '2025-01-01', letrejott: false, kurzor: null, figyelmeztetes: null }));
    vi.stubGlobal('fetch', fetch);
    await naploSzomszedNyit(f, 'kovetkezo');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ ut: 'Journal/2024/Dec/31.md', irany: 'kovetkezo' });
    expect(f.munkaterulet.aktivFul?.ut).toBe('Journal/2025/Jan/01.md');
  });

  it('startup vár a settingsre/layout/setupra, egyszer fut, a modultiltást tiszteli', () => {
    const nyit = vi.fn().mockResolvedValue(undefined), f = new Felulet({}), indit = napiIndito(f, nyit), d = adat();
    d.ertek.fajlok.napi_inditaskor = true;
    indit(null, true, false); indit(d, false, false); indit(d, true, true);
    d.setup_szukseges = true; indit(d, true, false); expect(nyit).not.toHaveBeenCalled();
    d.setup_szukseges = false; indit(d, true, false); indit(d, true, false); expect(nyit).toHaveBeenCalledTimes(1);
    d.ertek.modulok.napi = false; napiIndito(f, nyit)(d, true, false); expect(nyit).toHaveBeenCalledTimes(1);
  });

  it('a napi előző/következő parancsok tisztelik a napi modulkapcsolót', () => {
    const d = adat(); beallitasok.fogad(d);
    const reg = new Regiszter(), le = maTelepit(reg, new Felulet({}), new CoreKapcsolat('ws://synthetic'));
    try {
      for (const id of ['naplo.elozo', 'naplo.kovetkezo']) expect(reg.elerheto(reg.kap(id)!)).toBe(true);
      beallitasok.ertek.modulok.napi = false;
      for (const id of ['naplo.elozo', 'naplo.kovetkezo']) expect(reg.elerheto(reg.kap(id)!)).toBe(false);
    } finally { le(); }
  });
});
