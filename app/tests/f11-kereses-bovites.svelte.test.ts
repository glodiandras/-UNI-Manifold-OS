// F11 keresés- és tulajdonság-bővítések, felület (08-search-03/04/05/11 kapcsolók, rendezés, környezet és súgó;
// 03-properties-06 sor-menü, 07 átnevezés, 09 tulajdonság-nézet, 11 címke-rendezés).
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { flushSync, tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EditorState, Text } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import Kereses from '../src/atfedes/KeresoAblak.svelte';
import Oldalsav from '../src/hej/Oldalsav.svelte';
import { alapParancsok } from '../src/alapParancsok';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { vaultKereses, type KeresesValasz } from '../src/lib/kereses/vaultKereses.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { cimkek } from '../src/lib/vault/cimkek.svelte';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { tulajdonsagKulcsok } from '../src/lib/vault/tulajdonsagkulcsok.svelte';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import type { Csere } from '../src/szerkeszto/dokumentum/kulonbseg';
import Olvaso from '../src/szerkeszto/Olvaso.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import Tulajdonsagok from '../src/szerkeszto/tulajdonsagok/Tulajdonsagok.svelte';
import type { Elemzes, Muvelet, TaroltTulajdonsagTipus } from '../src/szerkeszto/tulajdonsagok/tipusok';

// A jsdom-ban az átfedés kifutó átmenete nem fejeződik be (a `.fatyol` megmarad): a Tab-teszt ezért kikapcsolhatja a modális-őrt.
const modalis = vi.hoisted(() => ({ felulirt: false }));
vi.mock('../src/lib/fokusz/hatokor', async (eredeti) => {
  const m = await eredeti<typeof import('../src/lib/fokusz/hatokor')>();
  return { ...m, modalisNyitva: () => (modalis.felulirt ? false : m.modalisNyitva()) };
});

const json = (d: unknown, status = 200) => new Response(JSON.stringify(d), { status, headers: { 'Content-Type': 'application/json' } });
const le: (() => void)[] = [];

function kornyezet(allapot: unknown = {}) {
  const felulet = new Felulet({ kenyelmiVerzio: 1, csend: { be: false }, oldalsav: { nyitva: true, nezet: 'kereses' }, ...(allapot as object) });
  const fajlok = new VaultFajlok(), kapcsolat = new CoreKapcsolat('ws://synthetic');
  fajlok.beallit([
    { ut: 'Alpha.md', tipus: 'md', meret: 1, mtime: 10 },
    { ut: 'Beta.md', tipus: 'md', meret: 1, mtime: 30 },
    { ut: 'Gamma.md', tipus: 'md', meret: 1, mtime: 20 },
  ]);
  vi.spyOn(fajlok, 'frissit').mockResolvedValue();
  return { felulet, fajlok, kapcsolat, context: new Map([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]) };
}

function modulKapcsol(nev: 'kereses' | 'tulajdonsagok' | 'cimkek', be: boolean) {
  const adat = { verzio: 1 as const, rev: `${nev}-${be}`, ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] };
  adat.ertek.modulok[nev] = be;
  beallitasok.fogad(adat);
  flushSync();
}

beforeEach(() => {
  nyelv.beallit('en');
  beallitasok.adat = null;
  szerkesztok.beallit(null);
  vaultKereses.beallit('', true);
  vaultKereses.jelentes = false;
  vaultKereses.modBeallit({ kisnagy: false, reszszo: false, kornyezet: false });
  cimkek.lista = []; cimkek.betoltve = false; cimkek.latszik = false;
  tulajdonsagKulcsok.lista = []; tulajdonsagKulcsok.betoltve = false; tulajdonsagKulcsok.hiba = null; tulajdonsagKulcsok.indexEpul = false;
  vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  while (le.length) le.pop()!();
  vaultKereses.beallit('', true);
  vaultKereses.modBeallit({ kisnagy: false, reszszo: false, kornyezet: false });
  beallitasok.adat = null; szerkesztok.beallit(null);
  document.body.textContent = '';
  vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers();
  nyelv.beallit('hu');
});

// ---------------------------------------------------------------------------------------------------- keresés

describe('08-search: kapcsolók, rendezés, környezet és súgó a keresőpanelen', () => {
  let kerelmek: URL[];
  const fajl = (ut: string) => ({ ut, pont: 1, talalatok: [{ sor: 5, oszlop: 0, hossz: 5, szoveg: 'alpha line', elotte: ['line before'], utana: ['line after'] }] });
  const valasz: KeresesValasz = { q: 'alpha', osszes: 3, talalatok: [fajl('Gamma.md'), fajl('Alpha.md'), fajl('Beta.md')] };
  beforeEach(() => {
    kerelmek = [];
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname.includes('kereses')) { kerelmek.push(u); return json({ ...valasz, q: u.searchParams.get('q') }); }
      return json({});
    });
  });
  const mezo = () => screen.getByRole('combobox', { name: 'Search' });
  async function keres(k: ReturnType<typeof kornyezet>) {
    render(Oldalsav, { context: k.context });
    await fireEvent.input(mezo(), { target: { value: 'alpha' } });
    await screen.findByText('3 matching files');
  }
  const kartyaNevek = () => [...document.querySelectorAll('.kartya .nev')].map((e) => e.textContent);

  it('Match case és Inside words csomagol a core operátoraiba, tartós, a válasz a felhasználó szövegét idézi', async () => {
    const k = kornyezet();
    await keres(k);
    expect(kerelmek.at(-1)!.searchParams.get('q')).toBe('alpha');
    const mc = screen.getByRole('button', { name: 'Match case' });
    expect(mc.getAttribute('aria-pressed')).toBe('false');
    await fireEvent.click(mc);
    expect(k.felulet.kereso.kisnagy).toBe(true);
    await waitFor(() => expect(kerelmek.at(-1)!.searchParams.get('q')).toBe('match-case:(alpha)'));
    expect(screen.getByRole('button', { name: 'Match case' }).getAttribute('aria-pressed')).toBe('true');
    await fireEvent.click(screen.getByRole('button', { name: 'Inside words' }));
    await waitFor(() => expect(kerelmek.at(-1)!.searchParams.get('q')).toBe('match-case:(substring:(alpha))'));
    await screen.findByText('3 matching files');
    expect(screen.queryByText(/Nincs találat|No results/)).toBeNull();
    const mentett = k.felulet.sorosit();
    expect(mentett.kereso).toMatchObject({ kisnagy: true, reszszo: true });
    const uj = new Felulet(mentett);
    expect(uj.kereso).toMatchObject({ kisnagy: true, reszszo: true, kornyezet: false, rendezes: 'relevancia' });
    await fireEvent.click(screen.getByRole('button', { name: 'Match case' }));
    await waitFor(() => expect(kerelmek.at(-1)!.searchParams.get('q')).toBe('substring:(alpha)'));
  });

  it('More context: kornyezet=2 kérés, a sor előtti/utáni sorok halványan; kikapcsolva nincsenek', async () => {
    const k = kornyezet();
    await keres(k);
    expect(kerelmek.at(-1)!.searchParams.get('kornyezet')).toBe('1');
    expect(screen.queryAllByText('line before')).toHaveLength(0);
    await fireEvent.click(screen.getByRole('button', { name: 'More context' }));
    await waitFor(() => expect(kerelmek.at(-1)!.searchParams.get('kornyezet')).toBe('2'));
    await waitFor(() => expect(screen.getAllByText('line before')).toHaveLength(3));
    expect(screen.getAllByText('line after')[0].classList.contains('kontekst')).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: 'More context' }));
    await waitFor(() => expect(screen.queryAllByText('line before')).toHaveLength(0));
    await waitFor(() => expect(kerelmek.at(-1)!.searchParams.get('kornyezet')).toBe('1'));
  });

  it('a hibrid (Jelentés szerint) ág a környezetet is kéri', async () => {
    const k = kornyezet();
    await keres(k);
    await fireEvent.click(screen.getByRole('button', { name: 'More context' }));
    await fireEvent.click(screen.getByRole('checkbox', { name: 'By meaning' }));
    await waitFor(() => expect(kerelmek.at(-1)!.pathname).toBe('/api/kereses/hibrid'));
    expect(kerelmek.at(-1)!.searchParams.get('kornyezet')).toBe('2');
  });

  it('a rendezés: relevancia (alap), név A–Z/Z–A, módosítás; tartós, a billentyűzet-sorrend követi', async () => {
    const k = kornyezet();
    await keres(k);
    expect(kartyaNevek()).toEqual(['Gamma', 'Alpha', 'Beta']);
    const valaszt = async (nev: string) => {
      await fireEvent.click(screen.getByRole('button', { name: /^Sort:/ }));
      await fireEvent.click(await screen.findByRole('option', { name: new RegExp(`^${nev}`) }));
    };
    await valaszt('File name \\(A–Z\\)');
    await waitFor(() => expect(kartyaNevek()).toEqual(['Alpha', 'Beta', 'Gamma']));
    await valaszt('File name \\(Z–A\\)');
    await waitFor(() => expect(kartyaNevek()).toEqual(['Gamma', 'Beta', 'Alpha']));
    await valaszt('Modified: newest first');
    await waitFor(() => expect(kartyaNevek()).toEqual(['Beta', 'Gamma', 'Alpha']));       // mtime 30, 20, 10
    await valaszt('Modified: oldest first');
    await waitFor(() => expect(kartyaNevek()).toEqual(['Alpha', 'Gamma', 'Beta']));
    expect(k.felulet.sorosit().kereso?.rendezes).toBe('modositva-regi');
    await fireEvent.keyDown(mezo(), { key: 'Enter' });
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('Alpha.md');                         // az első a rendezett listában
    await valaszt('Relevance');
    await waitFor(() => expect(kartyaNevek()).toEqual(['Gamma', 'Alpha', 'Beta']));
    expect(kerelmek.filter((u) => u.searchParams.get('q') !== 'alpha')).toHaveLength(0);   // a rendezés nem új kérés
  });

  it('érvénytelen mentett rendezés / hiányzó beállítás: az alapértékek', () => {
    const f = new Felulet({ kenyelmiVerzio: 1, kereso: { kivagasok: false, rendezes: 'ismeretlen', kisnagy: 'igen' } });
    expect(f.kereso).toEqual({ kivagasok: false, kisnagy: false, reszszo: false, kornyezet: false, rendezes: 'relevancia' });
    expect(new Felulet({}).kereso.rendezes).toBe('relevancia');
  });

  it('a súgó az új operátorokat sorolja', async () => {
    const k = kornyezet();
    render(Oldalsav, { context: k.context });
    for (const sz of ['section:(a b)', 'task:word', '[key]', '[key:value]', 'match-case:(…)', '*word']) {
      expect(screen.getAllByText(sz, { exact: false }).length, sz).toBeGreaterThan(0);
    }
  });

  it('Tab a Reading nézetben a keresett szavakkal előtölti a jegyzetbeli keresőt (overlay)', async () => {
    const k = kornyezet();
    k.felulet.atfedes = 'kereso';
    render(Kereses, { context: k.context });
    await fireEvent.input(mezo(), { target: { value: 'alpha -skip' } });
    await screen.findByText('3 matching files');
    const keresesNyit = vi.fn();
    const p = { ut: 'Gamma.md', nezet: () => null, mod: () => 'olvaso', keresesNyit } as never;     // a kijelölt (első) kártya a Gamma
    k.felulet.munkaterulet.megnyit('Gamma.md', 'aktiv');
    szerkesztok.beallit(p);
    modalis.felulirt = true;
    try {
      await fireEvent.keyDown(mezo(), { key: 'Tab' });
      await waitFor(() => expect(keresesNyit).toHaveBeenCalledWith('alpha'), { timeout: 4000 });
    } finally { modalis.felulirt = false; }
    expect(k.felulet.atfedes).toBeNull();
    szerkesztok.megszunt(p);
  });
});

describe('08-search-12: az Olvasó keresője', () => {
  it('a kezdő szöveggel megnyitva előtölti a mezőt, és ékezetfüggetlenül talál; kezdő szöveg nélkül a régi szöveg marad', async () => {
    nyelv.beallit('hu');
    const szoveg = 'Árvíz árviz ARVIZ\n\nmásik';
    const view = new EditorView({ state: EditorState.create({ doc: szoveg }) });
    const dok = new Dokumentum({ olvas: vi.fn(), ir: vi.fn() }, { ut: 'Host.md', tartalom: szoveg, hash: 'base', jel: '', mtime: 0 });
    try {
      const { component, container } = render(Olvaso, { props: { view, dok, ut: 'Host.md', valtozat: 0 } });
      await component.keresesNyit('arviz');
      const mezo = screen.getByRole('textbox', { name: 'Keresés az olvasóban' }) as HTMLInputElement;
      expect(mezo.value).toBe('arviz');
      await vi.waitFor(() => expect(screen.getByRole('status').textContent).toBe('1/3 találat'));
      expect([...container.querySelectorAll('mark.olvaso-talalat')].map((m) => m.textContent)).toEqual(['Árvíz', 'árviz', 'ARVIZ']);
      await fireEvent.keyDown(mezo, { key: 'Escape' });
      await component.keresesNyit();
      expect((screen.getByRole('textbox', { name: 'Keresés az olvasóban' }) as HTMLInputElement).value).toBe('arviz');
      await component.keresesNyit('másik');
      expect((screen.getByRole('textbox', { name: 'Keresés az olvasóban' }) as HTMLInputElement).value).toBe('másik');
    } finally { view.destroy(); }
  });
});

// ---------------------------------------------------------------------------------------------------- tulajdonságok oldalsáv

describe('03-properties-09: Tulajdonságok oldalsáv-nézet', () => {
  const KULCSOK = [
    { kulcs: 'status', db: 5, sema: false, tipus: 'text' },
    { kulcs: 'rating', db: 9, sema: true, tipus: 'number' },
    { kulcs: 'archive', db: 1, sema: false, tipus: null },
    { kulcs: 'unused', db: 0, sema: true, tipus: null },
  ];
  beforeEach(() => {
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname === '/api/vault/tulajdonsagok/kulcsok') return json({ kulcsok: KULCSOK, index_kesz: true });
      if (u.pathname === '/api/vault/jegyzet') return json({ tulajdonsagok: [{ kulcs: 'status', tipus: 'text', ertek: 'done' }, { kulcs: 'tags', tipus: 'tags', ertek: ['a', 'b'] }] });
      if (u.pathname.includes('kereses')) return json({ q: u.searchParams.get('q'), osszes: 0, talalatok: [] });
      return json({});
    });
  });
  const sorok = () => within(screen.getByRole('listbox', { name: 'All properties' })).getAllByRole('option').map((e) => e.getAttribute('data-kulcs'));

  it('a fül, az aktív jegyzet tulajdonságai és az összes kulcs számmal, használaton kívüli séma-kulcs nélkül', async () => {
    const k = kornyezet({ oldalsav: { nyitva: true, nezet: 'tulajdonsagok' } });
    k.felulet.munkaterulet.megnyit('Alpha.md', 'aktiv');
    render(Oldalsav, { context: k.context });
    expect(screen.getByRole('tab', { name: 'Properties', selected: true })).toBeTruthy();
    await waitFor(() => expect(sorok()).toEqual(['archive', 'rating', 'status']));
    const rating = screen.getByRole('option', { name: /rating/ });
    expect(rating.textContent).toContain('9');
    expect(rating.textContent).toContain('schema');
    await screen.findByText('done');                                                      // ez a jegyzet: status = done
    expect(screen.getByText('a, b')).toBeTruthy();
    expect(screen.getByText('3 properties in the vault')).toBeTruthy();
  });

  it('kulcsra kattintás a [kulcs] kereséssel nyitja a keresőt; Enter/szóköz és a nyilak billentyűről is', async () => {
    const k = kornyezet({ oldalsav: { nyitva: true, nezet: 'tulajdonsagok' } });
    render(Oldalsav, { context: k.context });
    await waitFor(() => expect(sorok()).toHaveLength(3));
    await fireEvent.click(screen.getByRole('option', { name: /status/ }));
    expect(k.felulet.atfedes).toBe('kereso');
    expect(vaultKereses.q).toBe('[status]');
    k.felulet.atfedes = null;
    const elso = screen.getAllByRole('option')[0];
    elso.focus();
    await fireEvent.keyDown(elso, { key: 'ArrowDown' });
    await waitFor(() => expect(document.activeElement?.getAttribute('data-kulcs')).toBe('rating'));
    await fireEvent.keyDown(document.activeElement!, { key: 'End' });
    await waitFor(() => expect(document.activeElement?.getAttribute('data-kulcs')).toBe('status'));
    await fireEvent.keyDown(document.activeElement!, { key: 'Enter' });
    expect(vaultKereses.q).toBe('[status]');
    await fireEvent.keyDown(document.activeElement!, { key: 'Home' });
    await waitFor(() => expect(document.activeElement?.getAttribute('data-kulcs')).toBe('archive'));
    await fireEvent.keyDown(document.activeElement!, { key: ' ' });
    expect(vaultKereses.q).toBe('[archive]');
  });

  it('a rendezés menü (név/darabszám) tartós', async () => {
    const k = kornyezet({ oldalsav: { nyitva: true, nezet: 'tulajdonsagok' } });
    render(Oldalsav, { context: k.context });
    await waitFor(() => expect(sorok()).toHaveLength(3));
    await fireEvent.click(screen.getByRole('button', { name: /Sort order: Property name \(A–Z\)/ }));
    await fireEvent.click(await screen.findByRole('option', { name: 'Count: high to low' }));
    await waitFor(() => expect(sorok()).toEqual(['rating', 'status', 'archive']));
    expect(k.felulet.sorosit().oldalsav.tulajdonsagRendezes).toBe('db');
    expect(new Felulet(k.felulet.sorosit()).oldalsav.tulajdonsagRendezes).toBe('db');
    await fireEvent.click(screen.getByRole('button', { name: /Sort order: Count: high to low/ }));
    await fireEvent.click(await screen.findByRole('option', { name: 'Property name (Z–A)' }));
    await waitFor(() => expect(sorok()).toEqual(['status', 'rating', 'archive']));
  });

  it('a Keresés modul nélkül a kulcs nem nyit keresést; a Tulajdonságok modul nélkül nincs fül; a parancs a nézetre vált', async () => {
    const k = kornyezet({ oldalsav: { nyitva: true, nezet: 'tulajdonsagok' } });
    render(Oldalsav, { context: k.context });
    await waitFor(() => expect(sorok()).toHaveLength(3));
    modulKapcsol('kereses', false);
    await fireEvent.click(screen.getByRole('option', { name: /status/ }));
    expect(k.felulet.atfedes).toBe(null);
    modulKapcsol('tulajdonsagok', false);
    expect(screen.queryByRole('tab', { name: 'Properties' })).toBeNull();
    expect(screen.queryByRole('listbox', { name: 'All properties' })).toBeNull();
    modulKapcsol('tulajdonsagok', true);
    k.felulet.oldalsav.nezet = 'fajlok';
    const reg = new Regiszter(); le.push(alapParancsok(reg, k.felulet));
    expect(await reg.futtat('tulajdonsagok.panel', 'gomb')).toBe(true);
    expect(k.felulet.oldalsav.nezet).toBe('tulajdonsagok');
  });

  it('index épül: üzenet, nem hamis üres lista', async () => {
    vi.stubGlobal('fetch', async () => json({ kulcsok: [], index_kesz: false }));
    const k = kornyezet({ oldalsav: { nyitva: true, nezet: 'tulajdonsagok' } });
    render(Oldalsav, { context: k.context });
    await screen.findByText('The index is still being built…');
    expect(screen.queryByText('The vault has no properties.')).toBeNull();
  });
});

// ---------------------------------------------------------------------------------------------------- címkék rendezése

describe('03-properties-11: címkepanel rendezése', () => {
  const CIMKEK = [
    { cimke: 'AI', kis: 'ai', db: 2, ossz: 2 },
    { cimke: 'Fizika', kis: 'fizika', db: 1, ossz: 8 },
    { cimke: 'Zene', kis: 'zene', db: 4, ossz: 4 },
  ];
  beforeEach(() => {
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname === '/api/vault/cimkek') return json({ cimkek: CIMKEK });
      return json({ osszes: 0, talalatok: [] });
    });
  });
  const nevek = () => screen.getAllByRole('treeitem').map((e) => e.getAttribute('data-cimke'));

  it('a menü négy rendezése, tartós, a kiválasztott jelölt', async () => {
    const k = kornyezet({ oldalsav: { nyitva: true, nezet: 'cimkek' } });
    render(Oldalsav, { context: k.context });
    await waitFor(() => expect(nevek()).toEqual(['ai', 'fizika', 'zene']));
    await fireEvent.click(screen.getByRole('button', { name: /Sort order: Tag name \(A–Z\)/ }));
    expect(within(await screen.findByRole('listbox', { name: 'Sort tags' })).getAllByRole('option')).toHaveLength(4);
    await fireEvent.click(screen.getByRole('option', { name: 'Count: high to low' }));
    await waitFor(() => expect(nevek()).toEqual(['fizika', 'zene', 'ai']));
    expect(k.felulet.oldalsav.cimkeRendezes).toBe('db');
    await fireEvent.click(screen.getByRole('button', { name: /Sort order: Count: high to low/ }));
    expect(screen.getByRole('option', { name: /^Count: high to low/ }).textContent).toContain('✓');
    await fireEvent.click(screen.getByRole('option', { name: 'Count: low to high' }));
    await waitFor(() => expect(nevek()).toEqual(['ai', 'zene', 'fizika']));
    await fireEvent.click(screen.getByRole('button', { name: /Sort order: Count: low to high/ }));
    await fireEvent.click(screen.getByRole('option', { name: 'Tag name (Z–A)' }));
    await waitFor(() => expect(nevek()).toEqual(['zene', 'fizika', 'ai']));
    expect(new Felulet(k.felulet.sorosit()).oldalsav.cimkeRendezes).toBe('nev-forditott');
  });

  it('érvénytelen mentett érték az alap név szerinti sorrend', () => {
    expect(new Felulet({ oldalsav: { cimkeRendezes: 'ismeretlen', tulajdonsagRendezes: 5 } }).oldalsav.cimkeRendezes).toBe('nev');
    expect(new Felulet({ oldalsav: { tulajdonsagRendezes: 5 } }).oldalsav.tulajdonsagRendezes).toBe('nev');
  });
});

// ---------------------------------------------------------------------------------------------------- tulajdonságsor

describe('03-properties-06/07: sor-menü és átnevezés a tulajdonságpanelen', () => {
  const FM = '---\nrating: 5\ntags:\n  - a\n  - b\nnote: x\n---\n\nBody';
  const sorokAdat = [
    { kulcs: 'rating', tipus: 'number' as const, ertek: 5, ervenyes: true },
    { kulcs: 'tags', tipus: 'tags' as const, ertek: ['a', 'b'], ervenyes: true },
    { kulcs: 'note', tipus: 'text' as const, ertek: 'x', ervenyes: true },
  ];
  let vagolap = '';
  function felallit(irhato = true, modositEredmeny?: (m: Muvelet) => unknown) {
    const doc = Text.of(FM.split('\n'));
    const modosit = vi.fn(async (_ut: string, _fm: string | null, m: Muvelet) => modositEredmeny?.(m) ?? { ok: true, fm_uj: null, megerositheto: false, valtozas: false, problemak: [] });
    const api = {
      elemez: vi.fn(async (): Promise<Elemzes> => ({ van: true, hiba: null, osztaly: 'normal', kulcsok: sorokAdat.map((s) => s.kulcs), problemak: [], tulajdonsagok: sorokAdat })),
      sema: vi.fn(async () => ({ mezosorrend: [], extra_kulcsok: [], tags_ertekkeszlet: [], status_ertekkeszlet: [], status_gazdai: false, osztaly: null })),
      modosit: modosit as never,
      tipusok: vi.fn(async () => ({ rev: 'r', types: {} })),
      tipusBeallit: vi.fn(async (_k: string, _t: TaroltTulajdonsagTipus, _r: string) => ({ rev: 'r2', types: {} })),
    };
    const alkalmaz = vi.fn<(c: Csere) => void>();
    render(Tulajdonsagok, { props: { ut: 'Jegyzet.md', szoveg: () => doc, alkalmaz, valtozat: 0, irhato, api } });
    return { api, modosit, alkalmaz, doc };
  }
  const sor = (kulcs: string) => document.querySelector<HTMLElement>(`.sor[data-kulcs="${kulcs}"]`)!;
  const menuElem = (nev: string) => screen.findByRole('option', { name: nev });
  beforeEach(() => {
    vagolap = '';
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn(async (s: string) => { vagolap = s; }), readText: vi.fn(async () => vagolap) } });
    nyelv.beallit('en');
  });
  afterEach(() => { Reflect.deleteProperty(navigator, 'clipboard'); });

  it('jobb klikk: Rename, Cut, Copy, Paste, Remove — olvasható jegyzetben csak a Copy', async () => {
    felallit();
    await screen.findByText('rating');
    await fireEvent.contextMenu(sor('rating'));
    const nevek = within(screen.getByRole('listbox', { name: /rating/ })).getAllByRole('option').map((e) => e.textContent?.trim());
    expect(nevek).toEqual(['Rename', 'Cut', 'Copy', 'Paste', 'Remove property']);
    await fireEvent.keyDown(document.querySelector('.nt-lebego')!, { key: 'Escape' });
    expect(document.querySelector('.nt-lebego')).toBeNull();
    cleanup();
    felallit(false);
    await screen.findByText('rating');
    await fireEvent.contextMenu(sor('rating'));
    expect(within(screen.getByRole('listbox', { name: /rating/ })).getAllByRole('option').map((e) => e.textContent?.trim())).toEqual(['Copy']);
  });

  it('Copy: kulcs: érték a vágólapra, a jegyzet érintetlen; Cut ugyanez + törlés; a lista YAML-szerű', async () => {
    const f = felallit();
    await screen.findByText('rating');
    await fireEvent.contextMenu(sor('tags'));
    await fireEvent.click(await menuElem('Copy'));
    await waitFor(() => expect(vagolap).toBe('tags: [a, b]'));
    expect(f.modosit).not.toHaveBeenCalled();
    await fireEvent.contextMenu(sor('rating'));
    await fireEvent.click(await menuElem('Cut'));
    await waitFor(() => expect(f.modosit).toHaveBeenCalledTimes(1));
    expect(vagolap).toBe('rating: 5');
    expect(f.modosit.mock.calls[0][2]).toEqual({ muvelet: 'torol', kulcs: 'rating' });
  });

  it('Remove property: törlés a megszokott úton; a billentyűs belépő (ContextMenu / Shift+F10) ugyanazt a menüt adja', async () => {
    const f = felallit();
    await screen.findByText('note');
    const mezo = sor('note').querySelector('input')!;
    await fireEvent.keyDown(mezo, { key: 'F10', shiftKey: true });
    await fireEvent.click(await menuElem('Remove property'));
    await waitFor(() => expect(f.modosit.mock.calls.at(-1)?.[2]).toEqual({ muvelet: 'torol', kulcs: 'note' }));
    await fireEvent.keyDown(sor('note').querySelector('input')!, { key: 'ContextMenu' });
    expect(await menuElem('Rename')).toBeTruthy();
  });

  it('Paste: a vágólap kulcs: érték szövege a megfelelő típussal állítja be a kulcsot; kulcs nélküli szöveg ennek a sornak az értéke; nem tulajdonság: hiba a sor alatt', async () => {
    const f = felallit();
    await screen.findByText('note');
    vagolap = 'rating: 8';
    await fireEvent.contextMenu(sor('note'));
    await fireEvent.click(await menuElem('Paste'));
    await waitFor(() => expect(f.modosit).toHaveBeenCalled());
    expect(f.modosit.mock.calls.at(-1)?.[2]).toEqual({ muvelet: 'beallit', kulcs: 'rating', ertek: 8, tipus: 'number' });
    vagolap = 'plain value';
    await fireEvent.contextMenu(sor('note'));
    await fireEvent.click(await menuElem('Paste'));
    await waitFor(() => expect(f.modosit).toHaveBeenCalledTimes(2));
    expect(f.modosit.mock.calls.at(-1)?.[2]).toEqual({ muvelet: 'beallit', kulcs: 'note', ertek: 'plain value', tipus: 'text' });
    vagolap = 'tags: [x, y]';
    await fireEvent.contextMenu(sor('note'));
    await fireEvent.click(await menuElem('Paste'));
    await waitFor(() => expect(f.modosit).toHaveBeenCalledTimes(3));
    expect(f.modosit.mock.calls.at(-1)?.[2]).toEqual({ muvelet: 'beallit', kulcs: 'tags', ertek: ['x', 'y'], tipus: 'tags' });
    vagolap = 'egy\nmásik sor';
    await fireEvent.contextMenu(sor('note'));
    await fireEvent.click(await menuElem('Paste'));
    await screen.findByText('The clipboard text is not a property.');
    expect(f.modosit).toHaveBeenCalledTimes(3);
  });

  it('átnevezés: dupla kattintás → mező → Enter az atnevez műveletet küldi; Escape és változatlan név nem küld semmit', async () => {
    const f = felallit();
    await screen.findByText('note');
    await fireEvent.dblClick(screen.getByText('note', { selector: 'label' }));
    const mezo = (await screen.findByRole('textbox', { name: 'New name of note' })) as HTMLInputElement;
    expect(mezo.value).toBe('note');
    await fireEvent.input(mezo, { target: { value: 'megjegyzes' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(f.modosit).toHaveBeenCalledTimes(1));
    expect(f.modosit.mock.calls[0][2]).toEqual({ muvelet: 'atnevez', kulcs: 'note', uj_kulcs: 'megjegyzes' });
    await waitFor(() => expect(screen.queryByRole('textbox', { name: 'New name of note' })).toBeNull());
    // Escape
    await fireEvent.dblClick(screen.getByText('rating', { selector: 'label' }));
    const m2 = await screen.findByRole('textbox', { name: 'New name of rating' });
    await fireEvent.input(m2, { target: { value: 'pontszam' } });
    await fireEvent.keyDown(m2, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('textbox', { name: 'New name of rating' })).toBeNull());
    // változatlan név
    await fireEvent.dblClick(screen.getByText('rating', { selector: 'label' }));
    const m3 = await screen.findByRole('textbox', { name: 'New name of rating' });
    await fireEvent.keyDown(m3, { key: 'Enter' });
    await waitFor(() => expect(screen.queryByRole('textbox', { name: 'New name of rating' })).toBeNull());
    expect(f.modosit).toHaveBeenCalledTimes(1);
    expect(f.alkalmaz).not.toHaveBeenCalled();
  });

  it('a menüből is indul; sikeres átnevezés a dokumentumba kerül, a core elutasítása a sor alatt látszik és a mező nyitva marad', async () => {
    const f = felallit(true, (m) => (m.muvelet === 'atnevez' && m.uj_kulcs === 'tags'
      ? { ok: false, fm_uj: null, megerositheto: false, valtozas: false, problemak: [{ kod: 'duplikalt_kulcs', szint: 'hiba', kulcs: 'note', ertek: null, uzenet: 'The ‘tags’ property already exists in this note.' }] }
      : { ok: true, fm_uj: '---\nrating: 5\ntags:\n  - a\n  - b\nmegjegyzes: x\n---\n', megerositheto: false, valtozas: true, problemak: [] }));
    await screen.findByText('note');
    await fireEvent.contextMenu(sor('note'));
    await fireEvent.click(await menuElem('Rename'));
    let mezo = (await screen.findByRole('textbox', { name: 'New name of note' })) as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'tags' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await screen.findByText('The ‘tags’ property already exists in this note.');
    mezo = screen.getByRole('textbox', { name: 'New name of note' }) as HTMLInputElement;        // javítható
    expect(f.alkalmaz).not.toHaveBeenCalled();
    await fireEvent.input(mezo, { target: { value: 'megjegyzes' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(f.alkalmaz).toHaveBeenCalledTimes(1));
    expect(f.modosit.mock.calls.map((c) => (c[2] as { uj_kulcs?: string }).uj_kulcs)).toEqual(['tags', 'megjegyzes']);
  });

  it('olvasható jegyzetben a dupla kattintás nem nyit mezőt', async () => {
    felallit(false);
    await screen.findByText('note');
    await fireEvent.dblClick(screen.getByText('note', { selector: 'label' }));
    await tick();
    expect(screen.queryByRole('textbox', { name: /New name/ })).toBeNull();
  });
});
