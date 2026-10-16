import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BeallitasokAblak from '../src/beallitasok/Beallitasok.svelte';
import { beallitasAblak } from '../src/beallitasok/allapot.svelte';
import { beallitasokTelepit } from '../src/beallitasok';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { beallitasokApi } from '../src/lib/beallitasok/api';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { ApiHiba } from '../src/lib/core/api';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { nyelv } from '../src/lib/i18n';
import { Regiszter, regiszter } from '../src/lib/parancsok/regiszter';
import { kezel } from '../src/lib/parancsok/kezelo';
import { NezetRegiszter } from '../src/lib/elrendezes/nezetek.svelte';
import Helyorzo from '../src/hej/nezetek/Helyorzo.svelte';
import { alapParancsok } from '../src/alapParancsok';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { fokuszalhatok } from '../src/lib/fokusz/fokusz';
import ModulKikapcsolva from '../src/beallitasok/ModulKikapcsolva.svelte';
import type { Ful } from '../src/lib/elrendezes/munkaterulet.svelte';

const valasz = (rev = 'r1'): BeallitasokValasz => ({ verzio: 1, rev, ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic/vault' }, setup_szukseges: false, ujrainditas: [] });
const le: (() => void)[] = [];
beforeEach(() => { nyelv.beallit('en'); beallitasAblak.szakasz = 'altalanos'; });
afterEach(() => { cleanup(); while (le.length) le.pop()!(); beallitasok.adat = null; vi.restoreAllMocks(); nyelv.beallit('hu'); });

function nyit() {
  const tar = new BeallitasokTar(); tar.fogad(valasz());
  const onbezar = vi.fn(), onsetup = vi.fn(), onrendszer = vi.fn();
  render(BeallitasokAblak, { props: { tar, onbezar, onsetup, onrendszer } });
  return { tar, onbezar, onsetup, onrendszer };
}

describe('shared settings store', () => {
  it('sends revision + partial change and accepts only successful saved values', async () => {
    const tar = new BeallitasokTar(); tar.fogad(valasz());
    const saved = valasz('r2'); saved.ertek.megjelenes.tema = 'sotet';
    const m = vi.spyOn(beallitasokApi, 'ment').mockResolvedValue(saved);
    expect(await tar.ment({ megjelenes: { tema: 'sotet' } })).toBe(true);
    expect(m).toHaveBeenCalledWith('r1', { megjelenes: { tema: 'sotet' } });
    expect(tar.ertek.megjelenes.tema).toBe('sotet');
  });
  it('does not replace external settings or lose its error after a conflict', async () => {
    const tar = new BeallitasokTar(); tar.fogad(valasz('r2'));
    const m = vi.spyOn(beallitasokApi, 'ment').mockRejectedValue(new ApiHiba(409, 'Conflict'));
    expect(await tar.ment({ altalanos: { nyelv: 'hu' } }, 'r1')).toBe(false);
    expect(m).toHaveBeenCalledWith('r1', { altalanos: { nyelv: 'hu' } });
    expect(tar.adat?.rev).toBe('r2'); expect(tar.utkozes).toBe(true); expect(tar.hiba).toMatch(/changed elsewhere/);
  });
  it('keeps defaults and editor available with an older API', async () => {
    const tar = new BeallitasokTar(); vi.spyOn(beallitasokApi, 'betolt').mockRejectedValue(new ApiHiba(404, 'Missing'));
    await tar.betolt(); expect(tar.adat).toBeNull(); expect(tar.elerheto).toBe(false); expect(tar.ertek.szerkeszto.helyesiras).toBe(true);
    expect(await tar.ment({ setup: { kesz: true } })).toBe(false);
  });
  it('refreshes on hello and accepts broadcast values without writing notes', async () => {
    const tar = new BeallitasokTar(), k = new CoreKapcsolat('ws://synthetic');
    const get = vi.spyOn(beallitasokApi, 'betolt').mockResolvedValue(valasz());
    const stop = tar.figyel(k); await waitFor(() => expect(tar.adat?.rev).toBe('r1'));
    k.szetoszt({ tipus: 'beallitasok', ...valasz('r2') }); expect(tar.adat?.rev).toBe('r2');
    k.szetoszt({ tipus: 'hello' }); await waitFor(() => expect(get).toHaveBeenCalledTimes(2)); stop();
  });
  it('a delayed save response does not replace a newer settings broadcast', async () => {
    const tar = new BeallitasokTar(), k = new CoreKapcsolat('ws://synthetic');
    vi.spyOn(beallitasokApi, 'betolt').mockResolvedValue(valasz());
    const stop = tar.figyel(k); await waitFor(() => expect(tar.adat?.rev).toBe('r1'));
    let resolve!: (v: BeallitasokValasz) => void;
    vi.spyOn(beallitasokApi, 'ment').mockReturnValue(new Promise(r => resolve = r));
    const pending = tar.ment({ megjelenes: { csend: true } });
    k.szetoszt({ tipus: 'beallitasok', ...valasz('newer') });
    resolve(valasz('saved-before-broadcast')); await pending;
    expect(tar.adat?.rev).toBe('newer'); stop();
  });
  it('a pending old load cannot overwrite a newer save', async () => {
    const tar = new BeallitasokTar(); tar.fogad(valasz());
    let resolve!: (v: BeallitasokValasz) => void;
    vi.spyOn(beallitasokApi, 'betolt').mockReturnValue(new Promise(r => resolve = r));
    vi.spyOn(beallitasokApi, 'ment').mockResolvedValue(valasz('saved'));
    const pending = tar.betolt(); await tar.ment({ megjelenes: { csend: true } }); resolve(valasz('old')); await pending;
    expect(tar.adat?.rev).toBe('saved');
  });
});

describe('Settings flow', () => {
  it('keeps note language automatic and opens setup again without changing configuration', async () => {
    const { onsetup, onbezar } = nyit();
    expect((screen.getByLabelText('Content language hint') as HTMLInputElement).value).toBe('auto');
    expect(screen.getByText(/detects the language of each note automatically/)).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Run setup again' }));
    expect(onsetup).toHaveBeenCalledOnce(); expect(onbezar).toHaveBeenCalledOnce();
  });
  it('saves actual editor and file settings together, then shows saved state', async () => {
    nyit(); const saved = valasz('r2'); saved.ertek.szerkeszto.tab_meret = 4; saved.ertek.fajlok.uj_mappa = 'Inbox';
    const put = vi.spyOn(beallitasokApi, 'ment').mockResolvedValue(saved);
    await fireEvent.click(screen.getByRole('button', { name: 'Editor' }));
    await fireEvent.input(screen.getByLabelText('Tab size'), { target: { value: '4' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Files & links' }));
    await fireEvent.input(screen.getByLabelText('New note folder'), { target: { value: 'Inbox' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe('Settings saved'));
    expect(put.mock.calls[0][0]).toBe('r1'); expect(put.mock.calls[0][1].fajlok?.uj_mappa).toBe('Inbox'); expect(put.mock.calls[0][1].szerkeszto?.tab_meret).toBe(4);
  });
  it('rejects an empty numeric field before it can disappear during JSON serialization', async () => {
    nyit(); const put = vi.spyOn(beallitasokApi, 'ment');
    await fireEvent.click(screen.getByRole('button', { name: 'Editor' }));
    await fireEvent.input(screen.getByLabelText('Tab size'), { target: { value: '' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(screen.getByRole('alert').textContent).toContain('Tab size must be a whole number');
    expect(put).not.toHaveBeenCalled();
  });
  it('preserves the draft on error and reloads explicitly after conflicts', async () => {
    const { tar } = nyit();
    vi.spyOn(beallitasokApi, 'ment').mockRejectedValue(new ApiHiba(409, 'Conflict'));
    vi.spyOn(beallitasokApi, 'betolt').mockResolvedValue(valasz('r3'));
    await fireEvent.change(screen.getByLabelText('Content language hint'), { target: { value: 'hu' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' })); await waitFor(() => expect(tar.utkozes).toBe(true));
    expect((screen.getByLabelText('Content language hint') as HTMLInputElement).value).toBe('hu');
    await fireEvent.click(screen.getByRole('button', { name: 'Reload settings' })); await waitFor(() => expect(tar.adat?.rev).toBe('r3'));
    expect((screen.getByLabelText('Content language hint') as HTMLInputElement).value).toBe('auto');
  });
  it('does not silently overwrite edits arriving through WS while a draft is open', async () => {
    const { tar } = nyit();
    await fireEvent.change(screen.getByLabelText('Content language hint'), { target: { value: 'hu' } });
    flushSync(() => tar.fogad(valasz('external')));
    expect((screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText('Content language hint') as HTMLInputElement).value).toBe('hu');
  });
  it('traps focus, confirms discarding a draft, and restores focus after unmount', async () => {
    const opener = document.createElement('button'); document.body.append(opener); opener.focus();
    const { onbezar } = nyit();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'General' }));
    const fokusz = fokuszalhatok(screen.getByRole('dialog')); fokusz.at(-1)!.focus();
    await fireEvent.keyDown(fokusz.at(-1)!, { key: 'Tab' }); expect(document.activeElement).toBe(fokusz[0]);
    await fireEvent.change(screen.getByLabelText('Content language hint'), { target: { value: 'hu' } });
    const language = screen.getByLabelText('Content language hint'); language.focus();
    await fireEvent.keyDown(window, { key: 'Escape' }); expect(onbezar).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Keep editing' }));
    await fireEvent.keyDown(window, { key: 'Escape' }); expect(document.activeElement).toBe(language);
    await fireEvent.keyDown(window, { key: 'Escape' });
    await fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    await fireEvent.keyDown(window, { key: 'Escape' });
    await fireEvent.click(screen.getByRole('button', { name: 'Discard changes' })); expect(onbezar).toHaveBeenCalledOnce();
    cleanup(); await waitFor(() => expect(document.activeElement).toBe(opener)); opener.remove();
  });
});

describe('module and shortcut enforcement', () => {
  it('disabled modules block palette, keys and direct command invocation, preserving data', () => {
    const v = valasz(); v.ertek.modulok.graf = false; beallitasok.fogad(v);
    const r = new Regiszter(), f = vi.fn(); r.regisztral({ id: 'graf.megnyit', nev: 'Graph', billentyu: 'Mod+g', futtat: f });
    expect(r.lista()).toEqual([]); expect(r.futtat('graf.megnyit')).toBe(false);
    expect(kezel(new KeyboardEvent('keydown', { key: 'g', metaKey: true }), r)).toBe(false); expect(f).not.toHaveBeenCalled();
    expect(beallitasok.adat?.munkater.id).toBe('synthetic');
  });
  it('disabled specialized views show an actionable preserved-data message', () => {
    const v = valasz(); v.ertek.modulok.canvas = false; beallitasok.fogad(v);
    const r = new NezetRegiszter(); r.regisztral({ id: 'canvas', illeszkedik: () => true, komponens: Helyorzo });
    const f = { id: 'synthetic-tab', ut: 'file.canvas' } as Ful; expect(r.valaszt(f, undefined)?.komponens).toBe(ModulKikapcsolva);
    beallitasok.adat!.ertek.modulok.canvas = true;
    expect(r.valaszt(f, undefined)?.komponens).toBe(Helyorzo);
  });
  it('shortcut replacement updates lookups and unregister cleans the new chord', () => {
    const r = new Regiszter(); const stop = r.regisztral({ id: 'x.y', nev: 'Example', billentyu: 'Mod+x', futtat: () => {} });
    r.billentyuketAlkalmaz({ 'x.y': 'Mod+Shift+y' }); expect(r.akkordhoz('Mod+x')).toBeUndefined(); expect(r.akkordhoz('Mod+Shift+y')?.id).toBe('x.y');
    stop(); expect(r.akkordhoz('Mod+Shift+y')).toBeUndefined();
  });
  it('shortcut conflicts preserve the working map and Cmd+, opens settings', () => {
    const r = new Regiszter(); r.regisztral({ id: 'x.one', nev: 'One', billentyu: 'Mod+x', futtat: () => {} }); r.regisztral({ id: 'x.two', nev: 'Two', billentyu: 'Mod+y', futtat: () => {} });
    expect(() => r.billentyuketAlkalmaz({ 'x.two': 'Mod+x' })).toThrow(); expect(r.akkordhoz('Mod+y')?.id).toBe('x.two');
    const stop = beallitasokTelepit(r); le.push(stop); expect(kezel(new KeyboardEvent('keydown', { key: ',', metaKey: true }), r)).toBe(true); expect(beallitasAblak.nyitva).toBe(true); beallitasAblak.nyitva = false;
  });
  it('rejects malformed stored shortcuts and keeps app navigation shortcuts reserved', () => {
    const r = new Regiszter(); beallitasokTelepit(r);
    expect(() => r.billentyuketEllenoriz({ 'future.command': 'garbage' })).toThrow();
    expect(() => r.billentyuketEllenoriz({ 'future.command': 'Mod+Shift+o' })).toThrow();
    expect(() => r.billentyuketEllenoriz({ 'beallitasok.megnyit': '' })).toThrow();
    expect(r.akkordhoz('Mod+,')?.id).toBe('beallitasok.megnyit');
  });
  it('theme, quiet and notification commands persist to the same settings API', async () => {
    beallitasok.fogad(valasz()); const f = new Felulet(), r = new Regiszter(); le.push(alapParancsok(r, f));
    const put = vi.spyOn(beallitasokApi, 'ment').mockImplementation(async (_rev, change) => {
      const next = valasz('r2');
      next.ertek = JSON.parse(JSON.stringify(beallitasok.ertek));
      for (const [key, value] of Object.entries(change)) Object.assign(next.ertek[key as keyof typeof next.ertek], value);
      return next;
    });
    r.futtat('tema.sotet'); await waitFor(() => expect(f.tema).toBe('sotet'));
    expect(put.mock.calls[0][1]).toEqual({ megjelenes: { tema: 'sotet' } });
    const quiet = !f.csend.be; r.futtat('hej.csend'); await waitFor(() => expect(f.csend.be).toBe(quiet));
    expect(put.mock.calls[1][1]).toEqual({ megjelenes: { csend: quiet } });
    r.futtat('ertesites.rendszer'); await waitFor(() => expect(f.rendszerErtesites).toBe(false));
    expect(put.mock.calls[2][1]).toEqual({ adatvedelem: { ertesitesek: false } });
  });
  it('a failed appearance save retains the working theme and reports the error', async () => {
    beallitasok.fogad(valasz()); const f = new Felulet(), r = new Regiszter(); le.push(alapParancsok(r, f));
    vi.spyOn(beallitasokApi, 'ment').mockRejectedValue(new ApiHiba(409, 'Conflict'));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    r.futtat('tema.sotet'); await waitFor(() => expect(beallitasok.utkozes).toBe(true));
    expect(f.tema).toBe('rendszer');
  });
  it('edits modules and shortcut fields through the Settings UI', async () => {
    le.push(regiszter.regisztral({ id: 'example.command', nev: 'Example action', billentyu: 'Mod+e', futtat: () => {} }));
    nyit(); await fireEvent.click(screen.getByRole('button', { name: 'Modules' }));
    await fireEvent.click(screen.getByLabelText('Graph'));
    await fireEvent.click(screen.getByRole('button', { name: 'Hotkeys' }));
    await fireEvent.keyDown(screen.getByLabelText('Shortcut for Example action'), { key: 'k', metaKey: true, shiftKey: true });
    expect((screen.getByLabelText('Shortcut for Example action') as HTMLInputElement).value).toBe('⇧⌘K');
    expect(screen.getByText('Unsaved settings changes')).toBeTruthy();
  });
});
