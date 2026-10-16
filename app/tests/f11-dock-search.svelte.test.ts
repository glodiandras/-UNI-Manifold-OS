import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync, tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Harness from './F11DockHarness.svelte';
import Oldalsav from '../src/hej/Oldalsav.svelte';
import { alapParancsok } from '../src/alapParancsok';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { belep } from '../src/lib/fokusz/hatokor';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { keresoMegnyit, keresoOldalsav } from '../src/lib/kereses/kereso';
import { VaultKereses, vaultKereses, type KeresesValasz } from '../src/lib/kereses/vaultKereses.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const json = (d: unknown) => new Response(JSON.stringify(d), { headers: { 'Content-Type': 'application/json' } });
const fajl = (ut: string) => ({ ut, pont: 1, talalatok: [{ sor: 1, oszlop: 0, hossz: 5, szoveg: 'alpha example' }] });
const alapValasz = (q = 'alpha'): KeresesValasz => ({ q, osszes: 2, talalatok: [fajl('Alpha.md'), fajl('Beta.md')] });
const le: (() => void)[] = [];
let kerelmek: string[], eredmeny: KeresesValasz;
beforeEach(() => {
  nyelv.beallit('en'); kerelmek = []; eredmeny = alapValasz();
  vaultKereses.beallit('', true); vaultKereses.jelentes = false;
  beallitasok.adat = null; szerkesztok.beallit(null);
  vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/'); kerelmek.push(u.pathname);
    if (u.pathname.includes('kereses')) return json({ ...eredmeny, q: u.searchParams.get('q') });
    if (u.pathname === '/api/vault/cimkek') return json({ cimkek: [] });
    return json({});
  });
});
afterEach(() => { cleanup(); while (le.length) le.pop()!(); vaultKereses.beallit('', true); beallitasok.adat = null; szerkesztok.beallit(null); document.body.textContent = ''; vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); nyelv.beallit('hu'); });
function kornyezet(nezet: 'fajlok' | 'kereses' = 'kereses') {
  const felulet = new Felulet({ kenyelmiVerzio: 1, csend: { be: false }, oldalsav: { nyitva: true, nezet } });
  const fajlok = new VaultFajlok(), kapcsolat = new CoreKapcsolat('ws://synthetic');
  fajlok.beallit([{ ut: 'Alpha.md', tipus: 'md', meret: 1, mtime: 1 }, { ut: 'Beta.md', tipus: 'md', meret: 1, mtime: 1 }]);
  return { felulet, fajlok, kapcsolat, context: new Map([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]) };
}
const mezo = () => screen.getByRole('combobox', { name: 'Search' });
const keres = async () => { await fireEvent.input(mezo(), { target: { value: 'alpha' } }); await screen.findByText('2 matching files'); };

describe('F11 tartós oldalsáv-keresés', () => {
  it('eredmény megnyitása után a mező, lista, lekérdezés és görgetés megmarad; a következő találat billentyűről nyitható', async () => {
    const k = kornyezet(); render(Oldalsav, { context: k.context }); await keres();
    const input = mezo(), lista = document.querySelector<HTMLElement>('.eredmenyek')!;
    lista.scrollTop = 210;
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('Alpha.md');
    expect(mezo()).toBe(input); expect(document.querySelector('.eredmenyek')).toBe(lista);
    expect(lista.scrollTop).toBe(210); expect((input as HTMLInputElement).value).toBe('alpha');
    await fireEvent.keyDown(input, { key: 'ArrowDown' }); await fireEvent.keyDown(input, { key: 'ArrowDown' });
    await fireEvent.keyDown(input, { key: 'Enter', metaKey: true });
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('Beta.md'); expect(k.felulet.munkaterulet.aktivPanel.fulek).toHaveLength(2);
    await fireEvent.keyDown(input, { key: 'Enter', metaKey: true, altKey: true });
    expect(k.felulet.munkaterulet.panelek()).toHaveLength(2);
    expect(screen.getByRole('listbox', { name: 'Results' })).toBeTruthy(); expect(k.felulet.atfedes).toBe(null);
    await tick(); expect(document.activeElement).toBe(input);
  });

  it('a későn betöltő jegyzet automatikus fókusza után folytatható a lista, de kifejezett külső kattintást nem von vissza', async () => {
    const k = kornyezet(); render(Oldalsav, { context: k.context }); await keres();
    const input = mezo(), editor = document.createElement('button'); document.body.append(editor);
    await fireEvent.keyDown(input, { key: 'Enter' });
    const p = { ut: 'Alpha.md', nezet: () => ({}), mod: () => 'elo' } as never;
    szerkesztok.beallit(p); queueMicrotask(() => editor.focus());
    await waitFor(() => expect(document.activeElement).toBe(input));
    szerkesztok.beallit(null);
    await fireEvent.keyDown(input, { key: 'Enter' });
    await fireEvent.pointerDown(editor); editor.focus();
    szerkesztok.beallit(p); queueMicrotask(() => editor.focus());
    await new Promise(r => setTimeout(r, 30)); expect(document.activeElement).toBe(editor);
    szerkesztok.megszunt(p); editor.remove();
  });

  it('másik modális ablak alatt a visszaengedett Search fül nem veszi el a fókuszt', async () => {
    const k = kornyezet(); render(Oldalsav, { context: k.context }); await keres();
    const gomb = document.createElement('button'); document.body.append(gomb); gomb.focus();
    const kilep = belep('synthetic-modal'); le.push(kilep);
    k.felulet.oldalsav.nezet = 'fajlok'; flushSync();
    k.felulet.oldalsav.nezet = 'kereses'; flushSync(); await tick();
    expect(document.activeElement).toBe(gomb);
  });

  it('a link beszúrása a késői core-válasz után sem írhat csak olvasható vagy már elhagyott szerkesztőbe', async () => {
    const k = kornyezet(); render(Oldalsav, { context: k.context }); await keres();
    const dispatch = vi.fn();
    let csakOlvashato = false;
    const v = { state: { get readOnly() { return csakOlvashato; }, replaceSelection: (szoveg: string) => ({ changes: { from: 0, insert: szoveg } }), update: (...a: unknown[]) => ({ a }) }, dispatch, focus: vi.fn() };
    const p = { ut: 'Source.md', mod: () => 'elo', nezet: () => v } as never;
    szerkesztok.beallit(p);
    let kiad!: (s: string) => void;
    const linkCel = vi.spyOn(linkek, 'linkForma').mockImplementation(() => new Promise(r => { kiad = (cel) => r({ cel, alak: 'wiki', md: '' }); })); // 02-links-12/13: a link alakja a core formájából
    await fireEvent.keyDown(mezo(), { key: 'Enter', altKey: true });
    expect(linkCel).toHaveBeenCalledTimes(1); csakOlvashato = true; kiad('Target');
    await tick(); expect(dispatch).not.toHaveBeenCalled();
    csakOlvashato = false;
    await fireEvent.keyDown(mezo(), { key: 'Enter', altKey: true });
    await fireEvent.click(screen.getByRole('tab', { name: 'Files' })); kiad('Target');
    await tick(); expect(dispatch).not.toHaveBeenCalled();
    szerkesztok.megszunt(p);
  });

  it('a Search fül elhagyása és visszatérés ugyanazt a DOM-listát és görgetést hozza vissza; a nézet tartós', async () => {
    const k = kornyezet(); render(Oldalsav, { context: k.context }); await keres();
    const input = mezo(), lista = document.querySelector<HTMLElement>('.eredmenyek')!; lista.scrollTop = 315;
    await fireEvent.click(screen.getByRole('tab', { name: 'Files' })); expect(screen.queryByRole('combobox')).toBeNull();
    await fireEvent.click(screen.getByRole('tab', { name: 'Search' }));
    expect(mezo()).toBe(input); expect(document.querySelector('.eredmenyek')).toBe(lista); expect(lista.scrollTop).toBe(315);
    expect(vaultKereses.q).toBe('alpha');
    expect(new Felulet(JSON.parse(JSON.stringify(k.felulet.sorosit()))).oldalsav.nezet).toBe('kereses');
  });

  it('a Dock művelet kivárja az overlay bezárását, egy közös lekérdezéssel és fókuszátadással', async () => {
    const k = kornyezet('fajlok'); k.felulet.atfedes = 'kereso'; render(Harness, { context: k.context }); await keres();
    const elotte = kerelmek.filter(u => u.includes('kereses')).length;
    await fireEvent.click(screen.getByRole('button', { name: 'Dock search in sidebar' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(mezo()));
    expect((mezo() as HTMLInputElement).value).toBe('alpha'); expect(k.felulet.oldalsav.nezet).toBe('kereses');
    expect(kerelmek.filter(u => u.includes('kereses'))).toHaveLength(elotte);
  });

  it('az overlay Tab olvasó nézetben a megjelenített szöveg keresőjét nyitja a rejtett szerkesztő helyett', async () => {
    const megnyito = document.createElement('button'), olvasoMezo = document.createElement('input');
    document.body.append(megnyito, olvasoMezo); megnyito.focus();
    const k = kornyezet('fajlok'); k.felulet.atfedes = 'kereso'; render(Harness, { context: k.context }); await keres();
    const keresesNyit = vi.fn(() => olvasoMezo.focus()), nezet = vi.fn(() => null);
    const p = { ut: 'Alpha.md', mod: () => 'olvaso', nezet, keresesNyit } as never;
    szerkesztok.beallit(p);
    await fireEvent.keyDown(mezo(), { key: 'Tab' });
    await waitFor(() => expect(keresesNyit).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(olvasoMezo);
    expect(nezet).not.toHaveBeenCalled(); expect(k.felulet.atfedes).toBe(null);
    szerkesztok.megszunt(p);
  });

  it('modulkikapcsolás elrejti a Search fület, megőrzi az adatot, az új parancs és a régi overlay kapuzott', async () => {
    const adat = { verzio: 1 as const, rev: 'synthetic', ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] };
    beallitasok.fogad(adat);
    const k = kornyezet(); render(Oldalsav, { context: k.context }); await keres();
    const reg = new Regiszter(); le.push(alapParancsok(reg, k.felulet));
    adat.ertek.modulok.kereses = false; beallitasok.fogad({ ...adat, rev: 'off' }); flushSync();
    expect(screen.queryByRole('tab', { name: 'Search' })).toBeNull(); expect(screen.queryByRole('combobox')).toBeNull();
    expect(vaultKereses.q).toBe('alpha'); expect(vaultKereses.eredmeny?.osszes).toBe(2);
    expect(await reg.futtat('kereses.oldalsav', 'gomb')).toBe(false);
    k.felulet.atfedes = null; keresoMegnyit(k.felulet, 'changed'); expect(k.felulet.atfedes).toBe(null); expect(vaultKereses.q).toBe('alpha');
    adat.ertek.modulok.kereses = true; beallitasok.fogad({ ...adat, rev: 'on' }); flushSync();
    expect(mezo()).toBeTruthy(); expect(k.felulet.oldalsav.nezet).toBe('kereses');
  });

  it('azonos lekérdezés élő frissítése megőrzi az aktív találat kulcsát és a görgetést', async () => {
    const k = kornyezet(); render(Oldalsav, { context: k.context }); await keres();
    const input = mezo(), lista = document.querySelector<HTMLElement>('.eredmenyek')!;
    await fireEvent.keyDown(input, { key: 'ArrowDown' }); await fireEvent.keyDown(input, { key: 'ArrowDown' }); lista.scrollTop = 170;
    eredmeny = { q: 'alpha', osszes: 3, talalatok: [fajl('New.md'), ...alapValasz().talalatok] };
    k.kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['New.md'] });
    await screen.findByText('3 matching files', {}, { timeout: 2500 });
    const aktiv = screen.getAllByRole('option').find(e => e.getAttribute('aria-selected') === 'true')!;
    expect(aktiv.textContent).toContain('Beta'); expect(lista.scrollTop).toBe(170); expect(document.activeElement).toBe(input);
  });
});

describe('F11 közös keresési életciklus', () => {
  it('két fogyasztó ugyanazt a három WS-előfizetést használja; az utolsó leállítja a várakozó élő frissítést', async () => {
    vi.useFakeTimers();
    const tar = new VaultKereses(), k = new CoreKapcsolat('ws://synthetic');
    const figyel = vi.spyOn(k, 'figyel'), keres = vi.spyOn(tar, 'keres').mockResolvedValue();
    const egyik = tar.igenyel(k), masik = tar.igenyel(k); expect(figyel).toHaveBeenCalledTimes(3);
    tar.q = 'alpha'; k.szetoszt({ tipus: 'vault_valtozas', utak: ['A.md'] }); k.szetoszt({ tipus: 'vault_valtozas', utak: ['B.md'] });
    await vi.advanceTimersByTimeAsync(601); expect(keres).toHaveBeenCalledTimes(1);
    egyik(); egyik(); k.szetoszt({ tipus: 'vault_valtozas', utak: ['A.md'] });
    masik(); await vi.advanceTimersByTimeAsync(1000); expect(keres).toHaveBeenCalledTimes(1);
    k.szetoszt({ tipus: 'index' }); await vi.advanceTimersByTimeAsync(1000); expect(keres).toHaveBeenCalledTimes(1);
  });

  it('az utolsó fogyasztó megszakítja a futó kérést, megtartja az adatokat, a késői válasz nem írhatja felül őket', async () => {
    const tar = new VaultKereses(), k = new CoreKapcsolat('ws://synthetic');
    const ki = tar.igenyel(k); tar.eredmeny = alapValasz('kept');
    let kiad!: (r: Response) => void, jel: AbortSignal | undefined;
    vi.stubGlobal('fetch', (_url: string, opciok: RequestInit) => { jel = opciok.signal as AbortSignal; return new Promise<Response>(r => { kiad = r; }); });
    tar.beallit('pending', true); await waitFor(() => expect(kiad).toBeTypeOf('function'));
    ki(); expect(jel?.aborted).toBe(true); expect(tar.q).toBe('pending'); expect(tar.eredmeny?.q).toBe('kept');
    kiad(json(alapValasz('pending'))); await new Promise(r => setTimeout(r, 30));
    expect(tar.eredmeny?.q).toBe('kept'); expect(tar.hiba).toBeNull(); expect(tar.folyamat).toBe(false);
  });

  it('a dokkoló parancs megtartja a lekérdezést, és a felhasználó közben más nézetre váltva nem kap késői fókuszt', async () => {
    const k = kornyezet('fajlok'), reg = new Regiszter(); le.push(alapParancsok(reg, k.felulet));
    vaultKereses.q = 'kept';
    expect(await reg.futtat('kereses.oldalsav', 'gomb')).toBe(true);
    expect(k.felulet.oldalsav.nezet).toBe('kereses'); expect(vaultKereses.q).toBe('kept');
    const fatyol = document.createElement('div'); fatyol.className = 'fatyol'; document.body.append(fatyol);
    const elotte = vaultKereses.fokuszKer; keresoOldalsav(k.felulet); k.felulet.oldalsav.nezet = 'fajlok'; fatyol.remove();
    await new Promise(r => setTimeout(r, 50)); expect(vaultKereses.fokuszKer).toBe(elotte);
  });
});
