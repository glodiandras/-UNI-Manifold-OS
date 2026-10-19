import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { ChangeSet, EditorState, StateEffect } from '@codemirror/state';
import { history, undo } from '@codemirror/commands';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Komponalo from '../src/ma/Komponalo.svelte';
import { komponaloAblak, komponaloNyit, kivonasVegez, osszefuzesTerv, osszefuzesVegez, type KivonasEredmeny, type OsszefuzesTerv } from '../src/ma/komponaloAllapot.svelte';
import { szerkesztok, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { nyelv } from '../src/lib/i18n';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { vezerloApi } from '../src/lib/vezerlo/api';

const json = (x: unknown, status = 200) => new Response(JSON.stringify(x), { status, headers: { 'Content-Type': 'application/json' } });
const kivonva: KivonasEredmeny = { ok: true, ut: 'Notes/Extracted.md', nev: 'Extracted', letrejott: true, pillanat: 'p1', figyelmeztetes: null };
const terv: OsszefuzesTerv = { ok: true, forras: 'Notes/Source.md', cel: 'Notes/Target.md', hely: 'veg', terv_hash: 'exact-reviewed-hash', blokkolok: [], figyelmeztetesek: [], modositott_linkek: 2, kukaba: 'Notes/Source.md', cel_sorok: { elotte: 4, utana: 7 }, fajlok: [{ ut: 'Notes/Linker.md', darab: 2, linkek: [{ sor: 1, regi: '[[Source]]', uj: '[[Target]]' }] }] };
const egyesitve = { ok: true, forras: terv.forras, cel: terv.cel, hely: 'veg', modositott: [terv.cel], kor: 'KOMP-synthetic', forras_kukaban: true, forras_hiba: null, visszavonhato: true };
const kesleltet = <T,>() => { let kesz!: (v: T) => void; const p = new Promise<T>(r => kesz = r); return { p, kesz }; };
let v: EditorView, f: Felulet;
let hivasok: Array<{ url: string; d: Record<string, unknown> }>;
let valasz: (url: string, d: Record<string, unknown>) => Response | Promise<Response>;

beforeEach(() => {
  nyelv.beallit('en');
  ertesitesek.lista.length = 0; hivasok = [];
  f = new Felulet({}); f.munkaterulet.megnyit('Notes/Source.md');
  v = new EditorView({ state: EditorState.create({ doc: 'Before chosen after', selection: { anchor: 7, head: 13 }, extensions: [history()] }), parent: document.body });
  szerkesztok.beallit({ ut: 'Notes/Source.md', nezet: () => v, mod: () => 'elo' } as unknown as SzerkesztoPeldany);
  vi.spyOn(szerkesztok.dokumentumok, 'mindLezar').mockResolvedValue([]);
  vi.spyOn(szerkesztok.dokumentumok, 'mentetlenUtak').mockReturnValue([]);
  vi.spyOn(linkek, 'linkForma').mockResolvedValue({ cel: 'Extracted', alak: 'wiki', md: '' });
  valasz = (url) => json(url.endsWith('/kivon') ? kivonva : url.endsWith('/terv') ? terv : egyesitve);
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => { const d = JSON.parse(String(init?.body ?? '{}')); hivasok.push({ url: String(url), d }); return valasz(String(url), d); });
});
afterEach(() => { cleanup(); v.destroy(); komponaloAblak.keres = null; szerkesztok.beallit(null); ertesitesek.lista.length = 0; vi.restoreAllMocks(); vi.unstubAllGlobals(); nyelv.beallit('hu'); });

function megjelenit(mod: 'kivon'|'osszefuz') {
  komponaloNyit(f, mod);
  return render(Komponalo, { context: new Map([[KORNYEZET_KULCS, { felulet: f, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://synthetic') }]]) });
}

describe('S1 kivonás: valódi szerkesztő-tranzakció és célírás-határ', () => {
  it.each(['link', 'beagyazas', 'semmi'] as const)('%s cserét egyetlen Undo állítja vissza; az API előbb pontos kijelölést kap', async (utana) => {
    komponaloNyit(f, 'kivon'); const k = komponaloAblak.keres!;
    const r = await kivonasVegez(k, { mod: 'uj', nev: 'Extracted', mappa: 'Notes' }, () => true, utana);
    expect(hivasok).toEqual([{ url: '/api/komponalo/kivon', d: { forras: 'Notes/Source.md', szoveg: 'chosen', cel: { mod: 'uj', nev: 'Extracted', mappa: 'Notes' } } }]);
    expect(r.cserelve).toBe(true);
    expect(v.state.doc.toString()).toBe(`Before ${utana === 'semmi' ? '' : `${utana === 'beagyazas' ? '!' : ''}[[Extracted]]`} after`);
    expect(undo(v)).toBe(true); expect(v.state.doc.toString()).toBe('Before chosen after');
  });

  it('a meglévő cél a core pontos append/prepend alakját kapja; Markdown-linknél a core kódolását tartja meg', async () => {
    vi.mocked(linkek.linkForma).mockResolvedValue({ cel: '../Target', alak: 'md', md: '../Target%20note.md' });
    komponaloNyit(f, 'kivon');
    await kivonasVegez(komponaloAblak.keres!, { mod: 'meglevo', ut: 'Target note.md', hely: 'eleje' }, () => true, 'link');
    expect(hivasok[0].d.cel).toEqual({ mod: 'meglevo', ut: 'Target note.md', hely: 'eleje' });
    expect(v.state.doc.toString()).toContain('[Extracted](../Target%20note.md)');
  });

  it.each(['iras', 'kijeloles', 'readonly', 'bezar'] as const)('célírás közben %s: a forrás megmarad, az eredmény jelzi a már létrejött célt', async (eset) => {
    const p = kesleltet<Response>(); valasz = () => p.p;
    komponaloNyit(f, 'kivon'); const k = komponaloAblak.keres!;
    let aktiv = true;
    const pending = kivonasVegez(k, { mod: 'uj', nev: 'Extracted' }, () => aktiv);
    if (eset === 'iras') v.dispatch({ changes: { from: 0, insert: 'X' } });
    if (eset === 'kijeloles') v.dispatch({ selection: { anchor: 0 } });
    if (eset === 'readonly') v.dispatch({ effects: StateEffect.reconfigure.of([EditorState.readOnly.of(true)]) });
    if (eset === 'bezar') aktiv = false;
    const alap = v.state.doc.toString();
    p.kesz(json(kivonva)); const r = await pending;
    expect(r).toEqual({ eredmeny: kivonva, cserelve: false });
    expect(v.state.doc.toString()).toBe(alap);
    expect(linkek.linkForma).not.toHaveBeenCalled();
  });

  it('linkformázási hibánál a cél megvan, a forrás érintetlen', async () => {
    vi.mocked(linkek.linkForma).mockRejectedValue(new Error('Offline'));
    komponaloNyit(f, 'kivon');
    expect(await kivonasVegez(komponaloAblak.keres!, { mod: 'uj', nev: 'Extracted' }, () => true)).toEqual({ eredmeny: kivonva, cserelve: false });
    expect(v.state.doc.toString()).toBe('Before chosen after');
  });

  it.each([false, true])('nyitott kivonási cél közvetlenül frissül, piszkos=%s esetén a saját szöveg megmarad és konfliktus lesz', async (piszkos) => {
    const ir = vi.fn();
    const d = new Dokumentum({ olvas: async () => ({ ut: kivonva.ut, tartalom: 'Old target\n\nchosen\n', hash: 'new', jel: '', mtime: 1 }), ir }, { ut: kivonva.ut, tartalom: 'Old target', hash: 'old', jel: '', mtime: 0 });
    vi.spyOn(szerkesztok.dokumentumok, 'kap').mockImplementation(ut => ut === kivonva.ut ? d : undefined);
    if (piszkos) { const cs = ChangeSet.of({ from: 0, insert: 'My edit ' }, d.szoveg.length); d.valtozott(cs, cs.apply(d.szoveg), null); }
    komponaloNyit(f, 'kivon');
    await kivonasVegez(komponaloAblak.keres!, { mod: 'meglevo', ut: kivonva.ut, hely: 'veg' }, () => true);
    expect(d.szoveg.toString()).toBe(piszkos ? 'My edit Old target' : 'Old target\n\nchosen\n');
    expect(d.allapot).toBe(piszkos ? 'utkozes' : 'tiszta');
    expect(ir).not.toHaveBeenCalled();
  });

  it('névütközésnél a mező/kijelölés megmarad, új névvel egy külön felhasználói próbálkozás sikerül', async () => {
    let utkozes = true;
    valasz = () => utkozes ? json({ hiba: 'Synthetic conflict' }, 409) : json(kivonva);
    megjelenit('kivon');
    await fireEvent.input(screen.getByLabelText('New note name'), { target: { value: 'Taken' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Extract selection…' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Synthetic conflict'));
    expect((screen.getByLabelText('New note name') as HTMLInputElement).value).toBe('Taken');
    expect(v.state.doc.toString()).toBe('Before chosen after');
    utkozes = false;
    await fireEvent.input(screen.getByLabelText('New note name'), { target: { value: 'Available' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Extract selection…' }));
    await waitFor(() => expect(v.state.doc.toString()).toContain('[[Extracted]]'));
    expect(komponaloAblak.keres).toBeNull();
  });
});

describe('S1 merge: terv, CAS és körönkénti Undo', () => {
  it.each([
    ['terv', 'bezar'], ['terv', 'inaktiv'], ['terv', 'readonly'],
    ['iras', 'bezar'], ['iras', 'inaktiv'], ['iras', 'readonly'],
  ] as const)('%s előtti mentés közben %s: késői POST sem indul', async (fazis, eset) => {
    const mentes = kesleltet<unknown>();
    vi.mocked(szerkesztok.dokumentumok.mindLezar).mockReturnValue(mentes.p);
    komponaloNyit(f, 'osszefuz'); const k = komponaloAblak.keres!;
    let aktiv = true;
    const pending = fazis === 'terv' ? osszefuzesTerv(k, terv.cel, 'veg', () => aktiv) : osszefuzesVegez(k, terv, () => aktiv);
    const elutasitva = expect(pending).rejects.toThrow('The editor or selection changed');
    if (eset === 'bezar') aktiv = false;
    if (eset === 'inaktiv') szerkesztok.beallit(null);
    if (eset === 'readonly') v.dispatch({ effects: StateEffect.reconfigure.of([EditorState.readOnly.of(true)]) });
    mentes.kesz([]); await elutasitva;
    expect(hivasok).toHaveLength(0);
  });
  it('terv előtt lezárja az írásokat; mentési hibánál kérés sem megy', async () => {
    vi.mocked(szerkesztok.dokumentumok.mentetlenUtak).mockReturnValue(['Notes/Source.md']);
    komponaloNyit(f, 'osszefuz');
    await expect(osszefuzesTerv(komponaloAblak.keres!, terv.cel, 'veg')).rejects.toThrow('Some notes could not be saved');
    expect(hivasok).toHaveLength(0);
  });

  it('a blokkolt terv nem végrehajtható; megerősítés nélkül nincs írás', async () => {
    valasz = () => json({ ...terv, ok: false, blokkolok: ['Synthetic blocker'] });
    megjelenit('osszefuz');
    await fireEvent.input(screen.getByLabelText('Destination note path'), { target: { value: terv.cel } });
    await fireEvent.click(screen.getByRole('button', { name: 'Review merge plan' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Synthetic blocker'));
    expect((screen.getByRole('button', { name: 'Merge and move source to Trash' }) as HTMLButtonElement).disabled).toBe(true);
    expect(hivasok.map(x => x.url)).toEqual(['/api/komponalo/osszefuz/terv']);
    await expect(osszefuzesVegez(komponaloAblak.keres!, { ...terv, ok: false, blokkolok: ['Blocked'] })).rejects.toThrow('Resolve the blockers');
  });

  it('a megerősített terv pontos hash-e íródik; a visszavonás a meglévő kör-revert API-n megy', async () => {
    const revert = vi.spyOn(vezerloApi, 'visszavon').mockResolvedValue({ ok: true, sha: 'revert' });
    megjelenit('osszefuz');
    await fireEvent.input(screen.getByLabelText('Destination note path'), { target: { value: terv.cel } });
    await fireEvent.click(screen.getByRole('button', { name: 'Review merge plan' }));
    await waitFor(() => expect(screen.getByText('Links to update: 2')).toBeTruthy());
    expect(screen.getByText(/will move to Trash/)).toBeTruthy();
    expect(hivasok).toHaveLength(1);
    await fireEvent.click(screen.getByRole('button', { name: 'Merge and move source to Trash' }));
    await waitFor(() => expect(ertesitesek.lista.at(-1)?.cim).toBe('Notes merged'));
    expect(hivasok[1]).toEqual({ url: '/api/komponalo/osszefuz', d: { forras: terv.forras, cel: terv.cel, hely: 'veg', terv_hash: 'exact-reviewed-hash' } });
    expect(f.munkaterulet.aktivFul?.ut).toBe(terv.cel);
    await ertesitesek.lista.at(-1)!.muvelet!.futtat();
    await waitFor(() => expect(revert).toHaveBeenCalledWith('KOMP-synthetic'));
  });

  it('409 után a terv elavul, új megerősítéshez új terv kell', async () => {
    valasz = url => url.endsWith('/terv') ? json(terv) : json({ hiba: 'Synthetic stale hash' }, 409);
    megjelenit('osszefuz');
    await fireEvent.input(screen.getByLabelText('Destination note path'), { target: { value: terv.cel } });
    await fireEvent.click(screen.getByRole('button', { name: 'Review merge plan' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Merge and move source to Trash' })).not.toBeNull());
    await fireEvent.click(screen.getByRole('button', { name: 'Merge and move source to Trash' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Synthetic stale hash'));
    expect(screen.queryByRole('button', { name: 'Merge and move source to Trash' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Review merge plan' })).toBeTruthy();
    expect(f.munkaterulet.aktivFul?.ut).toBe(terv.forras);
  });

  it('a bezárt/lecserélt ablak késői sikeréről szól, de másik jegyzetre nem navigál', async () => {
    const p = kesleltet<Response>();
    valasz = url => url.endsWith('/terv') ? json(terv) : p.p;
    const { unmount } = megjelenit('osszefuz');
    await fireEvent.input(screen.getByLabelText('Destination note path'), { target: { value: terv.cel } });
    await fireEvent.click(screen.getByRole('button', { name: 'Review merge plan' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Merge and move source to Trash' })).not.toBeNull());
    await fireEvent.click(screen.getByRole('button', { name: 'Merge and move source to Trash' }));
    await waitFor(() => expect(hivasok).toHaveLength(2));
    unmount(); komponaloAblak.keres = null; f.munkaterulet.megnyit('Other.md');
    p.kesz(json(egyesitve));
    await waitFor(() => expect(ertesitesek.lista.at(-1)?.cim).toBe('Notes merged'));
    expect(f.munkaterulet.aktivFul?.ut).toBe('Other.md');
  });
});
