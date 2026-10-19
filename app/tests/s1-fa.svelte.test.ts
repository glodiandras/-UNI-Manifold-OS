// S1/U03/U16: a név/kiterjesztés és a közös Kuka-alertdialog szerződése, kizárólag szintetikus adatokkal.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Fa from '../src/hej/Fa.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { fajlNev, VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';

const f = (ut: string, tipus: FajlInfo['tipus'] = 'md'): FajlInfo => ({ ut, tipus, meret: 1, mtime: 1 });
const HOSSZU = `${'Árvíztűrő dokumentum '.repeat(10)}.md`;
type Kerelem = { url: string; metodus: string; body?: Record<string, unknown> };
let kerelmek: Kerelem[];
let valaszolo: (k: Kerelem) => Response | Promise<Response>;
const valasz = (adat: unknown, status = 200) => new Response(JSON.stringify(adat), { status, headers: { 'Content-Type': 'application/json' } });
const sor = (ut: string) => [...document.querySelectorAll<HTMLElement>('[data-fa-ut]')].find((el) => el.dataset.faUt === ut)!;
const kukaHivasok = () => kerelmek.filter((k) => k.url === '/api/vault/kuka');

beforeEach(() => {
  kerelmek = [];
  valaszolo = () => valasz({ ok: true });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const k = { url: new URL(url, 'http://127.0.0.1/').pathname, metodus: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined };
    kerelmek.push(k); return valaszolo(k);
  });
});
afterEach(() => { cleanup(); ertesitesek.lista = []; document.body.textContent = ''; vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function felallit(adatok: FajlInfo[] = [f('A.md'), f('B.md'), f('C.md')], mappak: string[] = []) {
  const felulet = new Felulet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [], mindenFajl: true } });
  const fajlok = new VaultFajlok(); fajlok.mappak = mappak; fajlok.beallit(adatok);
  const frissit = vi.spyOn(fajlok, 'frissit').mockResolvedValue();
  const kapcsolat = new CoreKapcsolat('ws://synthetic');
  render(Fa, { context: new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]) });
  return { felulet, fajlok, frissit };
}

describe('S1/U03: a fájlfa helyi névformázása', () => {
  it('ikon nélkül mutatja a nevet és a tényleges extensiont; a globális névsegéd és az eredeti út változatlan', async () => {
    const adatok = [f('Note.md'), f('Board.CANVAS', 'canvas'), f('Table.base', 'base'), f('Paper.pdf', 'pdf'), f('Movie.m4v', 'video'), f('Photo.PNG', 'kep'), f('main.test.cpp', 'egyeb'), f('Archive.odd', 'egyeb'), f('.env', 'egyeb'), f('LICENSE', 'egyeb'), f(HOSSZU)];
    const k = felallit(adatok, ['Projects']);
    for (const [ut, nev, badge] of [
      ['Note.md', 'Note', 'MD'], ['Board.CANVAS', 'Board', 'CANVAS'], ['Table.base', 'Table', 'BASE'], ['Paper.pdf', 'Paper', 'PDF'], ['Movie.m4v', 'Movie', 'M4V'], ['Photo.PNG', 'Photo', 'PNG'], ['main.test.cpp', 'main.test', 'CPP'], ['Archive.odd', 'Archive', 'ODD'], ['.env', '.env', null], ['LICENSE', 'LICENSE', null], [HOSSZU, HOSSZU.slice(0, -3), 'MD'],
    ]) {
      const el = sor(ut!); expect(el).toBeTruthy();
      expect(el.getAttribute('aria-label')).toBe(ut);
      expect(el.querySelector('.nev')!.textContent).toBe(nev);
      expect(el.querySelector('.kiterjesztes')?.textContent ?? null).toBe(badge);
      if (badge) expect(el.querySelector('.kiterjesztes')!.getAttribute('aria-hidden')).toBe('true');
      expect(el.querySelector('svg')).toBeNull();
    }
    expect(sor('Projects').querySelectorAll('svg')).toHaveLength(1); // kizárólag a mappa chevronja
    expect(sor('Projects').querySelector('.kiterjesztes')).toBeNull();
    expect(fajlNev('Photo.PNG')).toBe('Photo.PNG'); // más nézetek és a navigáció nem változnak
    await fireEvent.click(sor('Photo.PNG'));
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('Photo.PNG');
    await fireEvent.keyDown(sor('Photo.PNG'), { key: 'F2' });
    const atnev = await screen.findByRole('textbox', { name: 'A fájl új neve' }) as HTMLInputElement;
    expect(atnev.value).toBe('Photo.PNG');
    expect(sor('Photo.PNG').querySelector('.kiterjesztes')!.textContent).toBe('PNG');
    await fireEvent.keyDown(atnev, { key: 'Escape' });
    expect(kerelmek).toEqual([]);
  });
});

describe('S1/U16: a közös Kuka-alertdialog', () => {
  it('hosszú eredeti út, leírás, Cancel-alapfókusz, Tab-csapda, Escape és fókuszvisszaadás; megerősítés előtt nincs kérés', async () => {
    felallit([f(HOSSZU)]);
    const nyito = sor(HOSSZU); nyito.focus();
    await fireEvent.keyDown(nyito, { key: 'Delete' });
    const dialog = await screen.findByRole('alertdialog', { name: 'Áthelyezés a Kukába' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const leiras = document.getElementById(dialog.getAttribute('aria-describedby')!)!;
    expect(leiras.textContent).toContain(HOSSZU);
    expect(leiras.textContent).toContain('a macOS Kukájából visszahozható');
    const megse = within(dialog).getByRole('button', { name: 'Mégse' });
    const megerosit = within(dialog).getByRole('button', { name: 'Áthelyezés a Kukába' });
    expect(document.activeElement).toBe(megse);
    await fireEvent.keyDown(megse, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(megerosit);
    await fireEvent.keyDown(megerosit, { key: 'Tab' });
    expect(document.activeElement).toBe(megse);
    expect(kerelmek).toEqual([]);
    await fireEvent.keyDown(megse, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(nyito));
    expect(kerelmek).toEqual([]);
  });

  it('folyamatban Escape és a fátyol sem zár; a gombok védettek, a megerősített kérés sikerét megvárja', async () => {
    let kesz!: (r: Response) => void;
    valaszolo = () => new Promise((r) => { kesz = r; });
    const k = felallit();
    await fireEvent.keyDown(sor('A.md'), { key: 'Delete' });
    const dialog = await screen.findByRole('alertdialog');
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Áthelyezés a Kukába' }));
    await waitFor(() => expect(kukaHivasok()).toHaveLength(1));
    expect(kukaHivasok()[0]).toMatchObject({ metodus: 'POST', body: { ut: 'A.md', megerosit: true } });
    expect(within(dialog).getAllByRole('button').every((b) => (b as HTMLButtonElement).disabled)).toBe(true);
    expect(dialog.querySelector('[aria-busy="true"]')).toBeTruthy();
    await fireEvent.keyDown(window, { key: 'Escape' });
    await fireEvent.pointerDown(dialog.parentElement!);
    expect(screen.getByRole('alertdialog')).toBe(dialog);
    expect(kukaHivasok()).toHaveLength(1);
    kesz(valasz({ ok: true }));
    await waitFor(() => expect(k.frissit).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
  });

  it('részleges hiba után csak a hátralévők próbálhatók újra; az üzenet és a szám megmarad, végleges DELETE nincs', async () => {
    let egyszerHiba = true;
    valaszolo = (k) => {
      if (k.body?.ut === 'B.md' && egyszerHiba) { egyszerHiba = false; return valasz({ hiba: 'Synthetic Trash unavailable.' }, 503); }
      return valasz({ ok: true });
    };
    felallit();
    for (const ut of ['A.md', 'B.md', 'C.md']) await fireEvent.click(sor(ut), { metaKey: true });
    await fireEvent.keyDown(sor('C.md'), { key: 'Delete' });
    const dialog = await screen.findByRole('alertdialog');
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Áthelyezés a Kukába' }));
    const hiba = await within(dialog).findByRole('alert');
    expect(hiba.textContent).toContain('1 elem a Kukába került'); expect(hiba.textContent).toContain('Synthetic Trash unavailable.');
    expect(within(dialog).getByText('2 kijelölt elem')).toBeTruthy();
    expect(kukaHivasok().map((k) => k.body?.ut)).toEqual(['A.md', 'B.md']);
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Áthelyezés a Kukába' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(kukaHivasok().map((k) => k.body?.ut)).toEqual(['A.md', 'B.md', 'B.md', 'C.md']);
    expect(kerelmek.every((k) => k.url === '/api/vault/kuka' && k.metodus === 'POST' && k.body?.megerosit === true)).toBe(true);
  });
});
