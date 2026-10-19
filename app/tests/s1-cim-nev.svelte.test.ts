import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { createRawSnippet, tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const atnev = vi.hoisted(() => ({ terv: vi.fn(), vegrehajt: vi.fn(), ertesites: vi.fn() }));
vi.mock('../src/szerkeszto/linkek/atnevezes', () => ({ atnevezesTerv: atnev.terv, atnevezesVegrehajt: atnev.vegrehajt, atnevezesErtesites: atnev.ertesites }));
import FajlCim from '../src/szerkeszto/FajlCim.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { beallitasAblak } from '../src/beallitasok/allapot.svelte';
import { egeszsegAblak } from '../src/lib/egeszseg/allapot.svelte';
import Atfedes from '../src/lib/ui/Atfedes.svelte';

const terv = { ok: true, regi: 'Title.md', uj: 'New.md', blokkolok: [], fajlok: [], terv_hash: 'plan' };
const eredmeny = { ok: true, regi: 'Title.md', uj: 'New.md', modositott: [], pillanat: 'snapshot' };
function fuggo<T>() { let resolve!: (v: T) => void; let reject!: (e: Error) => void; const promise = new Promise<T>((r, j) => { resolve = r; reject = j; }); return { promise, resolve, reject }; }
beforeEach(() => {
  atnev.terv.mockReset().mockResolvedValue(terv);
  atnev.vegrehajt.mockReset().mockResolvedValue(eredmeny);
  atnev.ertesites.mockReset();
  beallitasAblak.nyitva = false; egeszsegAblak.nyitva = false;
  vi.spyOn(szerkesztok.dokumentumok, 'mindLezar').mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); ertesitesek.lista.length = 0; beallitasAblak.nyitva = false; egeszsegAblak.nyitva = false; });
function nyit() {
  const felulet = new Felulet({});
  const kesz = vi.fn();
  const c = render(FajlCim, { props: { ut: 'Title.md', irhato: true, aktiv: true, onkesz: kesz }, context: new Map([[KORNYEZET_KULCS, { felulet }]]) });
  const mezo = c.getByRole('textbox') as HTMLInputElement;
  return { ...c, mezo, felulet, kesz };
}
async function nev(c: ReturnType<typeof nyit>, value = 'New') { await fireEvent.input(c.mezo, { target: { value } }); }
function modalNyit(c: ReturnType<typeof nyit>, mod: 'paletta'|'beallitasok'|'egeszseg'|'setup') {
  if (mod === 'paletta') c.felulet.atfedes = 'paletta';
  if (mod === 'beallitasok') beallitasAblak.nyitva = true;
  if (mod === 'egeszseg') egeszsegAblak.nyitva = true;
  // A külön Setup helyi App-állapotát ugyanaz az Atfedes nev="setup" köti a közös hatókörhöz.
  const m = render(Atfedes, { props: { nev: mod, cimke: mod, onbezar: () => {}, children: createRawSnippet(() => ({ render: () => '<input aria-label="Modal field" />' })) } });
  const mezo = m.getByLabelText('Modal field') as HTMLInputElement;
  mezo.focus();
  return mezo;
}

describe('U01: title rename a meglévő szolgáltatással, draft/aszinkron életciklus', () => {
  it('Enter és az utána jövő blur egyetlen művelet, a meglévő Undo-értesítéssel', async () => {
    const c = nyit(); await nev(c);
    await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await fireEvent.blur(c.mezo);
    await waitFor(() => expect(atnev.ertesites).toHaveBeenCalledWith(eredmeny, c.felulet));
    expect(atnev.vegrehajt).toHaveBeenCalledTimes(1);
    expect(atnev.vegrehajt).toHaveBeenCalledWith('Title.md', 'New.md', 'plan', expect.any(Function));
    expect(c.kesz).toHaveBeenCalledTimes(1);
  });
  it('IME Enter nem ír; Escape elveti a draftot, a blur nem menti újra', async () => {
    const c = nyit(); await nev(c);
    await fireEvent.compositionStart(c.mezo);
    await fireEvent.keyDown(c.mezo, { key: 'Enter', isComposing: true });
    expect(atnev.terv).not.toHaveBeenCalled();
    await fireEvent.compositionEnd(c.mezo);
    await fireEvent.keyDown(c.mezo, { key: 'Escape' });
    await fireEvent.blur(c.mezo);
    expect(c.mezo.value).toBe('Title');
    expect(atnev.terv).not.toHaveBeenCalled();
  });
  it('409 után megmarad a név és a hiba; a javított draft ugyanazon az úton újrapróbálható', async () => {
    atnev.vegrehajt.mockRejectedValueOnce(new Error('409: the target exists'));
    const c = nyit(); await nev(c);
    await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(c.getByRole('alert').textContent).toContain('409'));
    expect(c.mezo.value).toBe('New');
    expect(c.getByRole('alert').querySelector('svg')).not.toBeNull();
    await nev(c, 'Other');
    // Az Enter nem feltétlenül vált ki blur-t (pl. a hiba után fókuszban marad a mező).
    // Egy új szerkesztés utáni rendes blur már nem nyelhető el az előző Enter miatt.
    await fireEvent.blur(c.mezo);
    await waitFor(() => expect(atnev.vegrehajt).toHaveBeenCalledTimes(2));
    expect(atnev.vegrehajt).toHaveBeenLastCalledWith('Title.md', 'Other.md', 'plan', expect.any(Function));
  });
  it('az eredeti fájlnév .md kiterjesztéssel is no-op, terv és írás nélkül', async () => {
    const c = nyit(); await nev(c, 'Title.md');
    await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    expect(c.mezo.value).toBe('Title');
    expect(atnev.terv).not.toHaveBeenCalled();
    expect(atnev.vegrehajt).not.toHaveBeenCalled();
  });
  it('linkváltozás és Bases-figyelmeztetés a meglévő terv-overlayt nyitja, nem hajt végre csendben', async () => {
    atnev.terv.mockResolvedValue({ ...terv, fajlok: [{ ut: 'Links.md' }], figyelmeztetesek: [{ ut: 'View.base' }] });
    const c = nyit(); await nev(c);
    await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(c.felulet.atfedes).toBe('atnevezes'));
    expect(c.felulet.atnevezes).toMatchObject({ ut: 'Title.md', mod: 'nev', nev: 'New' });
    expect(atnev.vegrehajt).not.toHaveBeenCalled();
    expect(c.mezo.value).toBe('Title');
  });
  it('tervezés közbeni útváltás eldobja a késői választ; a másik jegyzet neve és fókusza marad', async () => {
    const f = fuggo<typeof terv>(); atnev.terv.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.terv).toHaveBeenCalled());
    await c.rerender({ ut: 'Other.md' });
    c.mezo.focus();
    f.resolve(terv);
    await waitFor(() => expect(c.mezo.value).toBe('Other'));
    expect(atnev.vegrehajt).not.toHaveBeenCalled();
    expect(c.kesz).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(c.mezo);
  });
  it('tervezés közbeni readonly nem ír, a draft megmarad', async () => {
    const f = fuggo<typeof terv>(); atnev.terv.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.terv).toHaveBeenCalled());
    await c.rerender({ irhato: false }); f.resolve(terv);
    await waitFor(() => expect(c.mezo.disabled).toBe(true));
    expect(atnev.vegrehajt).not.toHaveBeenCalled();
    expect(c.mezo.value).toBe('New');
  });
  it('bezárás a dokumentum lezárása alatt még tervet sem indít', async () => {
    const f = fuggo<void>(); vi.mocked(szerkesztok.dokumentumok.mindLezar).mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    c.unmount(); f.resolve(undefined);
    await Promise.resolve(); await Promise.resolve();
    expect(atnev.terv).not.toHaveBeenCalled();
  });
  it('a már elküldött siker későn is ad Undo-eredményt, de nem lop fókuszt / nem navigál másik nézeten', async () => {
    const f = fuggo<typeof eredmeny>(); atnev.vegrehajt.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.vegrehajt).toHaveBeenCalled());
    c.unmount(); f.resolve(eredmeny);
    await waitFor(() => expect(atnev.ertesites).toHaveBeenCalledTimes(1));
    expect(c.kesz).not.toHaveBeenCalled();
  });
  it('a belső lezárás alatt érvénytelenedett kérő nem indít írást és nem küld késői hibajelzést', async () => {
    const f = fuggo<typeof eredmeny>(); atnev.vegrehajt.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.vegrehajt).toHaveBeenCalled());
    const mehet = atnev.vegrehajt.mock.calls[0][3] as () => boolean;
    c.unmount();
    expect(mehet()).toBe(false);
    f.reject(new Error('The requesting note is no longer editable'));
    await f.promise.catch(() => {}); await tick();
    expect(ertesitesek.lista).toHaveLength(0);
  });
  it('a ténylegesen elindított írás késői hibája látszik a bezárt kérő után is', async () => {
    const f = fuggo<typeof eredmeny>(); atnev.vegrehajt.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.vegrehajt).toHaveBeenCalled());
    const mehet = atnev.vegrehajt.mock.calls[0][3] as () => boolean;
    expect(mehet()).toBe(true);
    c.unmount(); f.reject(new Error('Connection lost'));
    await waitFor(() => expect(ertesitesek.lista).toHaveLength(1));
    expect(ertesitesek.lista[0]).toMatchObject({ szint: 'hiba', szoveg: 'Title.md: Connection lost', idotartam: 0 });
    expect(c.kesz).not.toHaveBeenCalled();
  });
  it.each(['paletta', 'beallitasok', 'egeszseg', 'setup'] as const)('a késői backlink-terv nem veheti át a közben megnyitott %s modalt', async mod => {
    const f = fuggo<typeof terv>(); atnev.terv.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.terv).toHaveBeenCalled());
    const masik = modalNyit(c, mod);
    f.resolve({ ...terv, fajlok: [{ ut: 'Backlink.md' }] } as typeof terv);
    await waitFor(() => expect(c.mezo.disabled).toBe(false));
    expect(c.felulet.atfedes).toBe(mod === 'paletta' ? 'paletta' : null);
    expect(c.felulet.atnevezes).toBeNull();
    expect(atnev.vegrehajt).not.toHaveBeenCalled();
    expect(c.kesz).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(masik);
    expect(c.mezo.value).toBe('New');
    expect(ertesitesek.lista).toHaveLength(0);
  });
  it.each(['paletta', 'beallitasok', 'egeszseg', 'setup'] as const)('a már elindított siker Undo-eredményt ad a %s mellett is, fókuszátvétel nélkül', async mod => {
    const f = fuggo<typeof eredmeny>(); atnev.vegrehajt.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.vegrehajt).toHaveBeenCalled());
    expect((atnev.vegrehajt.mock.calls[0][3] as () => boolean)()).toBe(true);
    const masik = modalNyit(c, mod);
    f.resolve(eredmeny);
    await waitFor(() => expect(atnev.ertesites).toHaveBeenCalledWith(eredmeny, c.felulet));
    expect(c.kesz).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(masik);
    expect(c.felulet.atfedes).toBe(mod === 'paletta' ? 'paletta' : null);
    expect(ertesitesek.lista).toHaveLength(0);
  });
  it.each(['beallitasok', 'egeszseg'] as const)('a %s flag már az Atfedes mountja előtt védi a felületet', async mod => {
    const f = fuggo<typeof terv>(); atnev.terv.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.terv).toHaveBeenCalled());
    if (mod === 'beallitasok') beallitasAblak.nyitva = true; else egeszsegAblak.nyitva = true;
    f.resolve({ ...terv, fajlok: [{ ut: 'Backlink.md' }] } as typeof terv);
    await waitFor(() => expect(c.mezo.disabled).toBe(false));
    expect(c.felulet.atfedes).toBeNull();
    expect(atnev.vegrehajt).not.toHaveBeenCalled();
    expect(c.mezo.value).toBe('New');
  });
  it('másik vezérlőre váltott fókusz után a backlink-terv nem nyit átfedést, a draft megmarad', async () => {
    const f = fuggo<typeof terv>(); atnev.terv.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.terv).toHaveBeenCalled());
    const masik = document.createElement('button'); masik.textContent = 'Other control'; document.body.appendChild(masik); masik.focus();
    f.resolve({ ...terv, fajlok: [{ ut: 'Backlink.md' }] } as typeof terv);
    await waitFor(() => expect(c.mezo.disabled).toBe(false));
    expect(c.felulet.atfedes).toBeNull(); expect(atnev.vegrehajt).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(masik); expect(c.mezo.value).toBe('New');
    masik.remove();
  });
  it('másik vezérlőre váltott fókuszt a késői siker sem helyezi vissza a törzsbe', async () => {
    const f = fuggo<typeof eredmeny>(); atnev.vegrehajt.mockReturnValue(f.promise);
    const c = nyit(); await nev(c); await fireEvent.keyDown(c.mezo, { key: 'Enter' });
    await waitFor(() => expect(atnev.vegrehajt).toHaveBeenCalled());
    const masik = document.createElement('button'); document.body.appendChild(masik); masik.focus();
    f.resolve(eredmeny);
    await waitFor(() => expect(atnev.ertesites).toHaveBeenCalledTimes(1));
    expect(c.kesz).not.toHaveBeenCalled(); expect(document.activeElement).toBe(masik);
    masik.remove();
  });
});
