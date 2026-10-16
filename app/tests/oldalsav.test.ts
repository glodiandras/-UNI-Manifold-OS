// Az oldalsáv fájlfája (C11a): a fa megjelenése (mappák elöl, magyar rend, számlálók), a billentyűzet (ARIA tree),
// a nyitott mappák tartóssága, az új jegyzet (soron belüli névmező), az átnevezés és a húzás (mindkettő a terv-átfedést
// nyitja: a húzás sosem ír közvetlenül), a „Megmutatás a fában”, és a fülek átcímzése mappa-átnevezésnél.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';
import Oldalsav from '../src/hej/Oldalsav.svelte';
import { atnevezesParancsok } from '../src/szerkeszto/linkek/atnevezes';

const f = (ut: string, tipus: FajlInfo['tipus'] = 'md'): FajlInfo => ({ ut, tipus, meret: 1, mtime: 1 });
const FAJLOK = [
  f('Zöld.md'),
  f('Árvíz.md'),
  f('F02 - Dinamika/Elmélet/10 - Vége.md'),
  f('F02 - Dinamika/Elmélet/02 - Newton II. törvénye.md'),
  f('F02 - Dinamika/Vászon.canvas', 'canvas'),
  f('ATTCHMNTS/foto.jpg', 'kep'),
  f('Alma.md'),
];
const MAPPAK = ['ATTCHMNTS', 'F02 - Dinamika', 'F02 - Dinamika/Elmélet', 'Üres'];

let kerelmek: { url: string; metodus: string; body?: Record<string, unknown> }[];
let beallitasElotte: { adat: BeallitasokValasz | null; elerheto: boolean };

function ujMappaBeallitas(mappa: string): void {
  const ertek = alapBeallitasok();
  ertek.fajlok.uj_mappa = mappa;
  beallitasok.fogad({ verzio: 1, rev: 'synthetic-revision', ertek, munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
}

function kornyezet(allapot: unknown = {}) {
  const felulet = new Felulet(allapot);
  const fajlok = new VaultFajlok();
  fajlok.mappak = MAPPAK;
  fajlok.beallit(FAJLOK);
  const kapcsolat = new CoreKapcsolat('ws://x');
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]);
  return { felulet, fajlok, kapcsolat, context };
}

function valasz(adat: unknown, kod = 200) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

const sorok = () => screen.getAllByRole('treeitem').map((e) => e.querySelector('.nev')?.textContent);

beforeEach(() => {
  beallitasElotte = { adat: beallitasok.adat, elerheto: beallitasok.elerheto };
  beallitasok.adat = null;
  kerelmek = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push({ url: u.pathname, metodus: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/vault/uj') {
      const b = JSON.parse(String(init!.body));
      if (b.nev === 'Rossz?') return valasz({ hiba: 'Érvénytelen név — tilos benne: ? ' }, 400);
      return valasz({ ok: true, ut: `${b.mappa ? b.mappa + '/' : ''}${b.nev}.md` }, 201);
    }
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  beallitasok.adat = beallitasElotte.adat;
  beallitasok.elerheto = beallitasElotte.elerheto;
  document.body.textContent = '';
  vi.unstubAllGlobals();
});

describe('a fa megjelenése', () => {
  it('a mappák elöl, magyar rendben, a fájlok után; a zárt mappák tartalma nem látszik; számlálók', () => {
    const { context } = kornyezet();
    render(Oldalsav, { context });
    expect(sorok()).toEqual(['ATTCHMNTS', 'F02 - Dinamika', 'Üres', 'Alma', 'Árvíz', 'Zöld']);
    expect(screen.getByRole('tree', { name: 'Fájlok' })).toBeTruthy();
    const dinamika = screen.getAllByRole('treeitem')[1];
    expect(dinamika.getAttribute('aria-expanded')).toBe('false');
    expect(dinamika.querySelector('.db')!.textContent).toBe('3');
    expect(screen.getAllByRole('treeitem')[2].querySelector('.db')).toBeNull(); // az üres mappának nincs száma
    expect(screen.getByText('7 fájl')).toBeTruthy();
  });

  it('a nyitott mappák (tartós állapotból) és a behúzás/szint', () => {
    const { context } = kornyezet({ oldalsav: { szelesseg: 264, nyitva: true, nyitott: ['F02 - Dinamika', 'F02 - Dinamika/Elmélet'] } });
    render(Oldalsav, { context });
    expect(sorok()).toEqual(['ATTCHMNTS', 'F02 - Dinamika', 'Elmélet', '02 - Newton II. törvénye', '10 - Vége', 'Vászon.canvas', 'Üres', 'Alma', 'Árvíz', 'Zöld']);
    const szintek = screen.getAllByRole('treeitem').map((e) => e.getAttribute('aria-level'));
    expect(szintek).toEqual(['1', '1', '2', '3', '3', '2', '1', '1', '1', '1']);
  });

  it('kattintásra a mappa kinyílik (és a tartós állapotba kerül), a fájl megnyílik; a középső gomb új fülben', async () => {
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    await fireEvent.click(screen.getByText('F02 - Dinamika'));
    expect(felulet.oldalsav.nyitott).toEqual(['F02 - Dinamika']);
    expect(sorok()).toContain('Elmélet');
    await fireEvent.click(screen.getByText('Alma'));
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('Alma.md');
    await fireEvent(screen.getByText('Árvíz'), new MouseEvent('auxclick', { button: 1, bubbles: true })); // 07-explorer-04: a ⌘-kattintás már kijelöl, az új fül a középső gomb
    expect(felulet.munkaterulet.aktivPanel.fulek.map((x) => x.ut)).toContain('Árvíz.md');
    expect(felulet.munkaterulet.aktivPanel.fulek.length).toBe(2);
    expect(screen.getByText('Alma').closest('[role=treeitem]')!.getAttribute('aria-selected')).toBe('false'); // az aktív az Árvíz
  });

  it('az aktív fájl kiemelt (aria-selected)', () => {
    const { felulet, context } = kornyezet();
    felulet.munkaterulet.megnyit('Alma.md', 'aktiv');
    render(Oldalsav, { context });
    expect(screen.getByText('Alma').closest('[role=treeitem]')!.getAttribute('aria-selected')).toBe('true');
  });
});

describe('billentyűzet (ARIA tree)', () => {
  it('gördülő tabindex: egy sor tabbolható; ↓↑ Home End lép; → kinyit, belép; ← becsuk, szülőre lép', async () => {
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    const fa = screen.getByRole('tree');
    const tab = () => screen.getAllByRole('treeitem').filter((e) => e.getAttribute('tabindex') === '0').map((e) => e.querySelector('.nev')!.textContent);
    expect(tab()).toEqual(['ATTCHMNTS']);
    screen.getAllByRole('treeitem')[0].focus();
    await fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' });
    await waitFor(() => expect(document.activeElement!.querySelector('.nev')!.textContent).toBe('F02 - Dinamika'));
    expect(tab()).toEqual(['F02 - Dinamika']);
    await fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' });
    expect(felulet.oldalsav.nyitott).toEqual(['F02 - Dinamika']);
    await fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' }); // belép az első gyerekbe
    await waitFor(() => expect(document.activeElement!.querySelector('.nev')!.textContent).toBe('Elmélet'));
    await fireEvent.keyDown(document.activeElement!, { key: 'ArrowLeft' }); // zárt mappán: a szülőre
    await waitFor(() => expect(document.activeElement!.querySelector('.nev')!.textContent).toBe('F02 - Dinamika'));
    await fireEvent.keyDown(document.activeElement!, { key: 'ArrowLeft' }); // nyitott: becsuk
    expect(felulet.oldalsav.nyitott).toEqual([]);
    await fireEvent.keyDown(document.activeElement!, { key: 'End' });
    await waitFor(() => expect(document.activeElement!.querySelector('.nev')!.textContent).toBe('Zöld'));
    await fireEvent.keyDown(document.activeElement!, { key: 'Home' });
    await waitFor(() => expect(document.activeElement!.querySelector('.nev')!.textContent).toBe('ATTCHMNTS'));
    expect(fa).toBeTruthy();
  });

  it('↩ a fájlt megnyitja, a mappát kapcsolja; F2 a fókuszált sorban helyben szerkeszthető nevet nyit', async () => {
    const { felulet, context } = kornyezet();
    const le = atnevezesParancsok(felulet);
    render(Oldalsav, { context });
    const alma = screen.getByText('Alma').closest<HTMLElement>('[role=treeitem]')!;
    alma.focus();
    await fireEvent.keyDown(alma, { key: 'Enter' });
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('Alma.md');
    const mappa = screen.getByText('F02 - Dinamika').closest<HTMLElement>('[role=treeitem]')!;
    mappa.focus();
    const f2 = le.find((p) => p.id === 'vault.atnevezes')!;
    expect(f2.elerheto?.()).toBe(true);
    f2.futtat();
    expect(felulet.faAtnevezKer?.ut).toBe('F02 - Dinamika'); // 07-explorer-03: nem a terv-átfedés, hanem a sorban szerkeszthető név
    expect(await screen.findByRole('textbox', { name: 'A mappa új neve' })).toBeTruthy();
    expect(felulet.atfedes).toBeNull();
    felulet.atnevezes = null;
    alma.focus();
    le.find((p) => p.id === 'vault.athelyezes')!.futtat();
    expect(felulet.atnevezes).toEqual({ ut: 'Alma.md', mod: 'hely' });
  });
});

describe('új jegyzet', () => {
  it('a névmező a fókuszált mappában nyílik; ↩ létrehozza és megnyitja; a mappa megnyílik', async () => {
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    const mappa = screen.getByText('F02 - Dinamika').closest<HTMLElement>('[role=treeitem]')!;
    mappa.focus();
    await fireEvent.click(screen.getByRole('button', { name: 'Új jegyzet' }));
    const mezo = await screen.findByLabelText('Az új jegyzet neve');
    expect(document.activeElement).toBe(mezo);
    expect(felulet.oldalsav.nyitott).toContain('F02 - Dinamika');
    await fireEvent.input(mezo, { target: { value: 'Új gondolat' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(felulet.munkaterulet.aktivFul?.ut).toBe('F02 - Dinamika/Új gondolat.md'));
    expect(kerelmek.find((k) => k.url === '/api/vault/uj')!.body).toEqual({ mappa: 'F02 - Dinamika', nev: 'Új gondolat' });
    expect(screen.queryByLabelText('Az új jegyzet neve')).toBeNull();
  });

  it('gyökérben, ha nincs fókuszált sor; Esc elvet; a core hibája a mező alatt látszik', async () => {
    const { context } = kornyezet();
    render(Oldalsav, { context });
    await fireEvent.click(screen.getByRole('button', { name: 'Új jegyzet' }));
    let mezo = await screen.findByLabelText('Az új jegyzet neve');
    await fireEvent.input(mezo, { target: { value: 'Rossz?' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    expect((await screen.findByRole('alert')).textContent).toContain('Érvénytelen név');
    expect(kerelmek.find((k) => k.url === '/api/vault/uj')!.body).toEqual({ mappa: '', nev: 'Rossz?' });
    mezo = screen.getByLabelText('Az új jegyzet neve');
    await fireEvent.keyDown(mezo, { key: 'Escape' });
    expect(screen.queryByLabelText('Az új jegyzet neve')).toBeNull();
  });

  it('üres névre ↩ nem kér a core-tól, bezárja a mezőt', async () => {
    const { context } = kornyezet();
    render(Oldalsav, { context });
    await fireEvent.click(screen.getByRole('button', { name: 'Új jegyzet' }));
    const mezo = await screen.findByLabelText('Az új jegyzet neve');
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    expect(screen.queryByLabelText('Az új jegyzet neve')).toBeNull();
    expect(kerelmek.length).toBe(0);
  });
});

describe('új jegyzet mappája a Settings API-ból', () => {
  it('üres beállításnál a gyökérbe ír akkor is, ha egy mappasor fókuszált', async () => {
    ujMappaBeallitas('');
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    screen.getByText('F02 - Dinamika').closest<HTMLElement>('[role=treeitem]')!.focus();
    await fireEvent.click(screen.getByRole('button', { name: 'Új jegyzet' }));
    const mezo = await screen.findByLabelText('Az új jegyzet neve');
    expect(mezo.getAttribute('title')).toBe('/');
    await fireEvent.input(mezo, { target: { value: 'Root note' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(felulet.munkaterulet.aktivFul?.ut).toBe('Root note.md'));
    expect(kerelmek.find(k => k.url === '/api/vault/uj')?.body).toEqual({ mappa: '', nev: 'Root note' });
  });

  it('a pont az aktív jegyzet szülőmappáját használja a fa fókuszától függetlenül', async () => {
    ujMappaBeallitas('.');
    const { felulet, context } = kornyezet();
    felulet.munkaterulet.megnyit('F02 - Dinamika/Elmélet/10 - Vége.md', 'aktiv');
    render(Oldalsav, { context });
    screen.getByText('ATTCHMNTS').closest<HTMLElement>('[role=treeitem]')!.focus();
    await fireEvent.click(screen.getByRole('button', { name: 'Új jegyzet' }));
    const mezo = await screen.findByLabelText('Az új jegyzet neve');
    expect(mezo.getAttribute('title')).toBe('F02 - Dinamika/Elmélet');
    await fireEvent.input(mezo, { target: { value: 'Related note' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(felulet.munkaterulet.aktivFul?.ut).toBe('F02 - Dinamika/Elmélet/Related note.md'));
    expect(kerelmek.find(k => k.url === '/api/vault/uj')?.body).toEqual({ mappa: 'F02 - Dinamika/Elmélet', nev: 'Related note' });
  });

  it('a még nem létező célmappánál is látszik és fókuszált a névmező, a POST pedig kéri a mappa létrehozását', async () => {
    ujMappaBeallitas('Drafts/Missing');
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    await fireEvent.click(screen.getByRole('button', { name: 'Új jegyzet' }));
    const mezo = await screen.findByLabelText('Az új jegyzet neve');
    expect(document.activeElement).toBe(mezo);
    expect(mezo.getAttribute('title')).toBe('Drafts/Missing');
    expect(mezo.closest('[hidden], [inert]')).toBeNull();
    await fireEvent.input(mezo, { target: { value: 'Draft note' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(felulet.munkaterulet.aktivFul?.ut).toBe('Drafts/Missing/Draft note.md'));
    const keres = kerelmek.find(k => k.url === '/api/vault/uj');
    expect(keres?.metodus).toBe('POST');
    expect(keres?.body).toEqual({ mappa: 'Drafts/Missing', nev: 'Draft note', mappa_keszit: true });
  });

  it('a helyi menü Új jegyzet itt művelete felülírja az alapértelmezett célmappát', async () => {
    ujMappaBeallitas('Drafts/Missing');
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    const mappa = screen.getByText('F02 - Dinamika').closest<HTMLElement>('[role=treeitem]')!;
    await fireEvent.contextMenu(mappa, { clientX: 20, clientY: 20 });
    await fireEvent.click(screen.getByRole('option', { name: 'Új jegyzet itt' }));
    const mezo = await screen.findByLabelText('Az új jegyzet neve');
    expect(mezo.getAttribute('title')).toBe('F02 - Dinamika');
    await fireEvent.input(mezo, { target: { value: 'Local note' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(felulet.munkaterulet.aktivFul?.ut).toBe('F02 - Dinamika/Local note.md'));
    expect(kerelmek.find(k => k.url === '/api/vault/uj')?.body).toEqual({ mappa: 'F02 - Dinamika', nev: 'Local note' });
  });
});

describe('húzás: link-változásnál (vagy hibánál) a terv-átfedést nyitja, megerősítés nélkül nem ír', () => {
  function huz(honnan: HTMLElement, hova: HTMLElement) {
    const adat = new Map<string, string>();
    const dataTransfer = { setData: (k: string, v: string) => adat.set(k, v), getData: (k: string) => adat.get(k) ?? '', effectAllowed: '', dropEffect: '' };
    fireEvent.dragStart(honnan, { dataTransfer });
    flushSync();
    const fogad = fireEvent.dragOver(hova, { dataTransfer });
    flushSync();
    fireEvent.drop(hova, { dataTransfer });
    flushSync();
    return fogad;
  }

  it('fájl mappára húzva, ha a terv nem kapható: az átnevezés-párbeszéd mod=hely és a célmappa megadva; írás nem ment', async () => {
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    huz(screen.getByText('Alma').closest<HTMLElement>('[role=treeitem]')!, screen.getByText('ATTCHMNTS').closest<HTMLElement>('[role=treeitem]')!);
    await waitFor(() => expect(felulet.atnevezes).toEqual({ ut: 'Alma.md', mod: 'hely', mappa: false, cel: 'ATTCHMNTS' }));
    expect(felulet.atfedes).toBe('atnevezes');
    expect(kerelmek.map((k) => k.url)).toEqual(['/api/vault/atnevezes/terv']); // csak terv kérdés, végrehajtás nincs
  });

  it('mappa a saját részfájába, vagy oda, ahol már van: nem ejthető (nincs átfedés)', () => {
    const { felulet, context } = kornyezet({ oldalsav: { szelesseg: 264, nyitva: true, nyitott: ['F02 - Dinamika'] } });
    render(Oldalsav, { context });
    const dinamika = screen.getByText('F02 - Dinamika').closest<HTMLElement>('[role=treeitem]')!;
    huz(dinamika, screen.getByText('Elmélet').closest<HTMLElement>('[role=treeitem]')!);
    expect(felulet.atnevezes).toBeNull();
    huz(dinamika, dinamika);
    expect(felulet.atnevezes).toBeNull();
  });

  it('fájl a gyökérre (a fa üres helyére) húzva: a célmappa a gyökér', async () => {
    const { felulet, context } = kornyezet({ oldalsav: { szelesseg: 264, nyitva: true, nyitott: ['F02 - Dinamika'] } });
    render(Oldalsav, { context });
    huz(screen.getByText('Vászon.canvas').closest<HTMLElement>('[role=treeitem]')!, screen.getByRole('tree'));
    await waitFor(() => expect(felulet.atnevezes).toEqual({ ut: 'F02 - Dinamika/Vászon.canvas', mod: 'hely', mappa: false, cel: '' }));
  });
});

describe('megmutatás a fában és átcímzés', () => {
  it('megmutatFaban: az ősmappák kinyílnak, a fa nézet aktív, a sor fókuszált', async () => {
    const { felulet, context } = kornyezet({ oldalsav: { szelesseg: 264, nyitva: false, nezet: 'cimkek' } });
    render(Oldalsav, { context });
    felulet.megmutatFaban('F02 - Dinamika/Elmélet/10 - Vége.md');
    await waitFor(() => expect(document.activeElement?.getAttribute('data-fa-ut')).toBe('F02 - Dinamika/Elmélet/10 - Vége.md'));
    expect(felulet.oldalsav).toMatchObject({ nezet: 'fajlok', nyitva: true, nyitott: ['F02 - Dinamika', 'F02 - Dinamika/Elmélet'] });
  });

  it('a mappa átnevezésekor a fülek, a legutóbbiak és a nyitott mappák az új útra címződnek (előtag)', () => {
    const { felulet } = kornyezet({ oldalsav: { szelesseg: 264, nyitva: true, nyitott: ['F02 - Dinamika', 'F02 - Dinamika/Elmélet', 'Más'] }, legutobbiFajlok: ['F02 - Dinamika/Vászon.canvas', 'F02 - Dinamikai.md'] });
    felulet.munkaterulet.megnyit('F02 - Dinamika/Elmélet/10 - Vége.md', 'aktiv');
    felulet.munkaterulet.megnyit('F02 - Dinamikai.md', 'ujful');
    felulet.utatNevez('F02 - Dinamika', 'Fizika/Dinamika');
    expect(felulet.munkaterulet.aktivPanel.fulek.map((x) => x.ut)).toEqual(['Fizika/Dinamika/Elmélet/10 - Vége.md', 'F02 - Dinamikai.md']);
    expect(felulet.legutobbiFajlok).toContain('Fizika/Dinamika/Vászon.canvas');
    expect(felulet.legutobbiFajlok).toContain('F02 - Dinamikai.md'); // az előtag-hasonló név érintetlen
    expect(felulet.oldalsav.nyitott).toEqual(['Fizika/Dinamika', 'Fizika/Dinamika/Elmélet', 'Más']);
  });
});

describe('az oldalsáv nézetei', () => {
  it('a fülek: Fájlok és Címkék (a Keresés fül megszűnt, E3); a váltás tartós; a címkék nézetben a fa nincs a DOM-ban', async () => {
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    expect(screen.getAllByRole('tab').map((t) => t.textContent?.trim())).toEqual(['Fájlok', 'Címkék', 'Tulajdonságok', 'Keresés']);
    expect(screen.getByRole('tab', { name: 'Fájlok' }).getAttribute('aria-selected')).toBe('true');
    await fireEvent.click(screen.getByRole('tab', { name: 'Címkék' }));
    expect(felulet.oldalsav.nezet).toBe('cimkek');
    expect(screen.queryByRole('tree', { name: 'Fájlok' })).toBeNull();
    expect(felulet.sorosit().oldalsav.nezet).toBe('cimkek');
    const uj = new Felulet(JSON.parse(JSON.stringify(felulet.sorosit())));
    expect(uj.oldalsav.nezet).toBe('cimkek');
  });
});
