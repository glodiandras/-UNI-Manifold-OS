// F11 explorer, second batch (07-explorer-03/04/06/07/11/12/15): inline rename, multi-select with bulk Trash/Move,
// Make a copy, Reveal in Finder, auto-reveal of the active file, hiding unsupported file types, direct drag-move and
// the palette commands. Synthetic vaults and a stubbed fetch only: nothing here touches a real vault.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import Fa from '../src/hej/Fa.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { faEpit, kijelolesTartomany, lapit, lathatoFajlok, legfelsoUtak, nemTamogatott } from '../src/lib/vault/fa';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';
import { atnevezesParancsok } from '../src/szerkeszto/linkek/atnevezes';

const f = (ut: string, tipus: FajlInfo['tipus'] = 'md'): FajlInfo => ({ ut, tipus, meret: 1, mtime: 1 });
const FAJLOK = [f('A.md'), f('B.md'), f('C.md'), f('Zeta/Child.md'), f('Zeta/Sub/Leaf.md'), f('x.zip', 'egyeb'), f('main.cpp', 'egyeb'), f('pic.png', 'kep')];
const MAPPAK = ['Zeta', 'Zeta/Sub', 'Empty'];

type Kerelem = { url: string; metodus: string; body?: Record<string, unknown> };
let kerelmek: Kerelem[];
let utvonalak: Record<string, (body: Record<string, unknown>) => unknown>;
const valasz = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
const terv = (regi: string, uj: string, extra: Record<string, unknown> = {}) => ({ ok: true, regi, uj, blokkolok: [], fajlok: [], modositott_linkek: 0, osszes_link: 0, uj_feloldott: 0, terv_hash: `h-${regi}`, ...extra });
const eredmeny = (regi: string, uj: string) => ({ ok: true, regi, uj, modositott: [], pillanat: `p-${regi}`, ms: 1, visszavonhato: true });
const hivasok = (suffix: string) => kerelmek.filter((k) => k.url === suffix);
const le: (() => void)[] = [];

beforeEach(() => {
  nyelv.beallit('hu');
  kerelmek = [];
  utvonalak = {};
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined;
    kerelmek.push({ url: u.pathname, metodus: init?.method ?? 'GET', body });
    const h = utvonalak[u.pathname];
    if (!h) return valasz({ hiba: 'nincs' }, 404);
    const r = h(body ?? {});
    return r instanceof Response ? r : valasz(r);
  });
});
afterEach(() => {
  cleanup();
  while (le.length) le.pop()!();
  ertesitesek.lista = [];
  document.body.textContent = '';
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  nyelv.beallit('hu');
});

function kornyezet(mentett: unknown = { csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: ['Zeta'] } }) {
  const felulet = new Felulet(mentett), fajlok = new VaultFajlok(), kapcsolat = new CoreKapcsolat('ws://synthetic');
  fajlok.mappak = MAPPAK;
  fajlok.beallit(FAJLOK);
  const frissit = vi.spyOn(fajlok, 'frissit').mockResolvedValue();
  return { felulet, fajlok, kapcsolat, frissit, context: new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]) };
}
const sor = (ut: string) => document.querySelector<HTMLElement>(`[data-fa-ut="${ut}"]`)!;
const sorUtak = () => [...document.querySelectorAll('[data-fa-ut]')].map((e) => e.getAttribute('data-fa-ut'));
const kijeloltek = () => [...document.querySelectorAll('[data-fa-ut]')].filter((e) => e.classList.contains('kijelolt')).map((e) => e.getAttribute('data-fa-ut'));

describe('a fa tiszta segédjei', () => {
  it('nemTamogatott / lathatoFajlok: az egyeb típus rejtve, kivéve a .cpp; kérésre minden látszik', () => {
    expect(FAJLOK.filter(nemTamogatott).map((x) => x.ut)).toEqual(['x.zip']);
    expect(lathatoFajlok(FAJLOK, false).map((x) => x.ut)).not.toContain('x.zip');
    expect(lathatoFajlok(FAJLOK, false).map((x) => x.ut)).toContain('main.cpp');
    expect(lathatoFajlok(FAJLOK, true)).toBe(FAJLOK);
    expect(nemTamogatott(f('MAIN.CPP', 'egyeb'))).toBe(false);
  });

  it('legfelsoUtak: a mappa és a részfájának elemei közül csak a mappa marad, az egyéb sorrend megmarad', () => {
    expect(legfelsoUtak(['Zeta/Sub/Leaf.md', 'A.md', 'Zeta', 'Zeta/Child.md', 'Zeta2/x.md', 'A.md'])).toEqual(['A.md', 'Zeta', 'Zeta2/x.md']);
    expect(legfelsoUtak([])).toEqual([]);
  });

  it('kijelolesTartomany: a látható sorok tartománya mindkét irányban; ismeretlen horgonynál egy elem', () => {
    const sorok = lapit(faEpit(FAJLOK, MAPPAK), new Set(['Zeta']));
    const ut = sorok.map((s) => s.cs.ut);
    const i = ut.indexOf('A.md'), j = ut.indexOf('C.md');
    expect(kijelolesTartomany(sorok, 'A.md', 'C.md')).toEqual(ut.slice(i, j + 1));
    expect(kijelolesTartomany(sorok, 'C.md', 'A.md')).toEqual(ut.slice(i, j + 1));
    expect(kijelolesTartomany(sorok, 'nincs', 'B.md')).toEqual(['B.md']);
    expect(kijelolesTartomany(sorok, null, 'B.md')).toEqual(['B.md']);
    expect(kijelolesTartomany(sorok, 'A.md', 'nincs')).toEqual([]);
  });
});

describe('07-explorer-12: nem támogatott fájltípusok elrejtése', () => {
  it('alapból rejtve (de a .cpp és a támogatott fájlok látszanak), a felületi kapcsoló előhozza, a számláló a láthatókat számolja', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    expect(sorUtak()).toEqual(['Empty', 'Zeta', 'A.md', 'B.md', 'C.md', 'main.cpp', 'pic.png']);
    expect(screen.getByText('Zeta').closest('[data-fa-ut]')!.querySelector('.db')!.textContent).toBe('2'); // csak a láthatók
    k.felulet.oldalsav.mindenFajl = true; flushSync();
    expect(sorUtak()).toContain('x.zip');
  });

  it('a vault showUnsupportedFiles beállítása is előhozza; a fa végpont válaszából jön', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    k.fajlok.mindenKiterjesztes = true; flushSync();
    expect(sorUtak()).toContain('x.zip');
    const valodi = new VaultFajlok();
    utvonalak['/api/vault/index'] = () => ({ kesz: true });
    utvonalak['/api/vault/fa'] = () => ({ fajlok: [f('x.zip', 'egyeb')], mappak: [], beallitasok: { minden_kiterjesztes: true } });
    await valodi.frissit();
    expect(valodi.mindenKiterjesztes).toBe(true);
    utvonalak['/api/vault/fa'] = () => ({ fajlok: [f('x.zip', 'egyeb')], mappak: [] });
    await valodi.frissit();
    expect(valodi.mindenKiterjesztes).toBe(false);
  });

  it('az üres terület helyi menüje átkapcsolja és mentésre kész állapotot hagy', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.contextMenu(screen.getByRole('tree'), { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Minden fájltípus mutatása' }));
    expect(k.felulet.oldalsav.mindenFajl).toBe(true);
    expect(new Felulet(JSON.parse(JSON.stringify(k.felulet.sorosit()))).oldalsav.mindenFajl).toBe(true);
    await fireEvent.contextMenu(screen.getByRole('tree'), { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Az aktív fájl automatikus megmutatása' }));
    expect(k.felulet.oldalsav.autoMegmutat).toBe(true);
  });
});

describe('07-explorer-04: többes kijelölés', () => {
  it('Shift-kattintás tartományt, ⌘-kattintás hozzáad / elvesz; nem nyit fájlt; a fa többes kijelölésű', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    expect(screen.getByRole('tree').getAttribute('aria-multiselectable')).toBe('true');
    await fireEvent.click(screen.getByText('A'));
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('A.md');
    await fireEvent.click(screen.getByText('C'), { shiftKey: true });
    expect(kijeloltek()).toEqual(['A.md', 'B.md', 'C.md']);
    expect(sor('B.md').getAttribute('aria-selected')).toBe('true');
    await fireEvent.click(screen.getByText('B'), { metaKey: true });
    expect(kijeloltek()).toEqual(['A.md', 'C.md']);
    await fireEvent.click(sor('pic.png'), { ctrlKey: true });
    expect(kijeloltek()).toEqual(['A.md', 'C.md', 'pic.png']);
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('A.md'); // a kijelölés nem nyitott meg semmit
    await fireEvent.click(screen.getByText('B')); // egyszerű kattintás: kijelölés megszűnik, a fájl megnyílik
    expect(kijeloltek()).toEqual([]);
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('B.md');
  });

  it('Shift+nyíl a horgonytól bővíti, Esc törli a kijelölést', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.click(screen.getByText('A'), { metaKey: true });
    await fireEvent.keyDown(sor('A.md'), { key: 'ArrowDown', shiftKey: true });
    await waitFor(() => expect(kijeloltek()).toEqual(['A.md', 'B.md']));
    await fireEvent.keyDown(sor('B.md'), { key: 'ArrowDown', shiftKey: true });
    await waitFor(() => expect(kijeloltek()).toEqual(['A.md', 'B.md', 'C.md']));
    await fireEvent.keyDown(sor('C.md'), { key: 'Escape' });
    expect(kijeloltek()).toEqual([]);
  });

  it('a kijelölésen jobb klikk tömeges menüt ad; a kijelöletlen soron egyetlen elem menüjét', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.click(screen.getByText('A'), { metaKey: true });
    await fireEvent.click(screen.getByText('B'), { metaKey: true });
    await fireEvent.contextMenu(sor('A.md'), { clientX: 5, clientY: 5 });
    expect(screen.getAllByRole('option').map((o) => o.textContent?.trim().replace(/\s+/g, ' '))).toEqual(['Áthelyezés (2 elem)…', 'Áthelyezés a Kukába (2 elem)…']);
    await fireEvent.keyDown(document.body, { key: 'Escape' });
    await fireEvent.contextMenu(sor('C.md'), { clientX: 5, clientY: 5 });
    expect(kijeloltek()).toEqual([]);
    expect(screen.getByRole('option', { name: /Átnevezés…/ })).toBeTruthy();
  });

  it('tömeges Kuka: megerősítés után sorban megy, a mappa és a részfája egyszer; a Kukába csak a megerősített végponton', async () => {
    utvonalak['/api/vault/kuka'] = () => ({ ok: true });
    const k = kornyezet();
    render(Fa, { context: k.context });
    await fireEvent.click(screen.getByText('A'), { metaKey: true });
    await fireEvent.click(screen.getByText('Zeta'), { metaKey: true });
    await fireEvent.click(screen.getByText('Child'), { metaKey: true });
    await fireEvent.contextMenu(sor('A.md'), { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Áthelyezés a Kukába (2 elem)…' })); // a mappa + részfájának egy eleme: 2 legfelső elem
    expect(hivasok('/api/vault/kuka')).toEqual([]); // megerősítés nélkül semmi nem megy
    expect(screen.getByText('2 kijelölt elem')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Áthelyezés a Kukába' }));
    await waitFor(() => expect(hivasok('/api/vault/kuka').length).toBe(2));
    expect(hivasok('/api/vault/kuka').map((x) => x.body)).toEqual([{ ut: 'A.md', megerosit: true }, { ut: 'Zeta', megerosit: true }]);
    await waitFor(() => expect(k.frissit).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Mégse' })).toBeNull());
    expect(kijeloltek()).toEqual([]);
  });

  it('a Kuka hibája megállítja a sort; a már Kukába tett elemek száma és a hátralévők látszanak, törlés végleg soha', async () => {
    utvonalak['/api/vault/kuka'] = (b) => (b.ut === 'B.md' ? valasz({ hiba: 'A Kuka nem érhető el.' }, 503) : { ok: true });
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.click(screen.getByText('A'), { metaKey: true });
    await fireEvent.click(screen.getByText('B'), { metaKey: true });
    await fireEvent.click(screen.getByText('C'), { metaKey: true });
    await fireEvent.keyDown(sor('C.md'), { key: 'Delete' });
    await fireEvent.click(screen.getByRole('button', { name: 'Áthelyezés a Kukába' }));
    const hiba = await screen.findByRole('alert');
    expect(hiba.textContent).toContain('1 elem a Kukába került, a hátralévők nem');
    expect(hiba.textContent).toContain('A Kuka nem érhető el.');
    expect(hivasok('/api/vault/kuka').map((x) => x.body?.ut)).toEqual(['A.md', 'B.md']); // C.md-hez nem is jutott
    expect(kerelmek.some((x) => x.metodus === 'DELETE')).toBe(false);
    expect(screen.getByText('2 kijelölt elem')).toBeTruthy(); // a hátralévők maradtak a kérdésben
  });

  it('a Delete billentyű egy sorra is a Kuka megerősítését kéri, ⌘⌫ ugyanígy', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.keyDown(sor('B.md'), { key: 'Delete' });
    expect(screen.getByText('B.md')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Mégse' }));
    await fireEvent.keyDown(sor('C.md'), { key: 'Backspace', metaKey: true });
    expect(screen.getByText('C.md')).toBeTruthy();
    expect(k.felulet.atfedes).toBeNull();
  });

  it('kijelölés húzása mappára: megerősítő párbeszéd a tervvel, utána elemenként átnevezés; link-változás látszik', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj), b.ut === 'B.md' ? { fajlok: [{ ut: 'Hivo.md', alap: 'x', darab: 2, linkek: [] }], modositott_linkek: 2 } : {});
    utvonalak['/api/vault/atnevezes'] = (b) => eredmeny(String(b.ut), String(b.uj));
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.click(screen.getByText('A'), { metaKey: true });
    await fireEvent.click(screen.getByText('B'), { metaKey: true });
    const adat = new Map<string, string>();
    const dataTransfer = { setData: (a: string, v: string) => adat.set(a, v), getData: (a: string) => adat.get(a) ?? '', types: [], files: [], effectAllowed: '', dropEffect: '' };
    await fireEvent.dragStart(sor('A.md'), { dataTransfer });
    expect(adat.get('text/plain')).toBe('A.md\nB.md');
    await fireEvent.dragOver(sor('Empty'), { dataTransfer });
    await fireEvent.drop(sor('Empty'), { dataTransfer });
    expect(await screen.findByText('→')).toBeTruthy();
    await waitFor(() => expect(hivasok('/api/vault/atnevezes/terv').length).toBe(2));
    expect(hivasok('/api/vault/atnevezes')).toEqual([]); // megerősítés nélkül nem ír
    await screen.findByText(/1 fájlban 2 link/);
    await fireEvent.click(screen.getByRole('button', { name: 'Áthelyezés' }));
    await waitFor(() => expect(hivasok('/api/vault/atnevezes').length).toBe(2));
    expect(hivasok('/api/vault/atnevezes').map((x) => [x.body?.ut, x.body?.uj, x.body?.terv_hash])).toEqual([['A.md', 'Empty/A.md', 'h-A.md'], ['B.md', 'Empty/B.md', 'h-B.md']]);
    expect(kijeloltek()).toEqual([]);
  });

  it('a tömeges áthelyezés blokkolt tervnél nem engedi a végrehajtást; a célmappa a menüből választható', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj), b.ut === 'B.md' ? { ok: false, blokkolok: ['Már van ilyen fájl.'] } : {});
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.click(screen.getByText('A'), { metaKey: true });
    await fireEvent.click(screen.getByText('B'), { metaKey: true });
    await fireEvent.contextMenu(sor('B.md'), { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Áthelyezés (2 elem)…' }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Empty' }));
    const hiba = await screen.findByRole('alert');
    expect(hiba.textContent).toContain('Már van ilyen fájl.');
    expect((screen.getByRole('button', { name: 'Áthelyezés' }) as HTMLButtonElement).disabled).toBe(true);
    expect(hivasok('/api/vault/atnevezes')).toEqual([]);
  });
});

describe('07-explorer-03: soron belüli átnevezés', () => {
  async function indit(ut: string, mappa = false) {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.keyDown(sor(ut), { key: 'F2' });
    const mezo = (await screen.findByRole('textbox', { name: mappa ? 'A mappa új neve' : 'A fájl új neve' })) as HTMLInputElement;
    return { k, mezo };
  }

  it('link-változás nélkül a terv után azonnal átnevez (kiterjesztés megmarad), Visszavonás értesítéssel', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj));
    utvonalak['/api/vault/atnevezes'] = (b) => eredmeny(String(b.ut), String(b.uj));
    const { k, mezo } = await indit('B.md');
    expect(mezo.value).toBe('B'); // a jegyzet kiterjesztése rejtett
    await fireEvent.input(mezo, { target: { value: 'Új név' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(hivasok('/api/vault/atnevezes').length).toBe(1));
    expect(hivasok('/api/vault/atnevezes/terv')[0].body).toEqual({ ut: 'B.md', uj: 'Új név.md' });
    expect(hivasok('/api/vault/atnevezes')[0].body).toEqual({ ut: 'B.md', uj: 'Új név.md', terv_hash: 'h-B.md' });
    expect(k.felulet.atfedes).toBeNull();
    await waitFor(() => expect(screen.queryByRole('textbox')).toBeNull());
    expect(ertesitesek.lista.at(-1)?.muvelet?.nev).toBe('Visszavonás');
  });

  it('link-változásnál a terv-átfedés nyílik az új névvel, megerősítés nélkül semmi nem ír', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj), { fajlok: [{ ut: 'Hivo.md', alap: 'x', darab: 1, linkek: [] }], modositott_linkek: 1 });
    const { k, mezo } = await indit('B.md');
    await fireEvent.input(mezo, { target: { value: 'Z' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(k.felulet.atfedes).toBe('atnevezes'));
    expect(k.felulet.atnevezes).toEqual({ ut: 'B.md', mod: 'nev', mappa: false, nev: 'Z' });
    expect(hivasok('/api/vault/atnevezes')).toEqual([]);
    expect(screen.queryByRole('textbox', { name: 'A fájl új neve' })).toBeNull();
  });

  it('átnézendő adatbázis-kifejezés is az átfedésbe terel; a mappa átnevezése a mappa nevével megy', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj), { mappa: true, figyelmeztetesek: [{ ut: 'x.base', hely: 'f', kifejezes: 'k', uzenet: 'u' }] });
    const { k, mezo } = await indit('Zeta', true);
    expect(mezo.value).toBe('Zeta');
    await fireEvent.input(mezo, { target: { value: 'Omega' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(k.felulet.atfedes).toBe('atnevezes'));
    expect(hivasok('/api/vault/atnevezes/terv')[0].body).toEqual({ ut: 'Zeta', uj: 'Omega' });
    expect(k.felulet.atnevezes?.mappa).toBe(true);
  });

  it('blokkoló vagy hibás terv: a hiba a sor alatt látszik ikonnal, a mező marad; írás nem történik', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj), { ok: false, blokkolok: ['Már van ilyen nevű fájl.'] });
    const { mezo } = await indit('B.md');
    await fireEvent.input(mezo, { target: { value: 'A' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    const hiba = await screen.findByRole('alert');
    expect(hiba.textContent).toContain('Már van ilyen nevű fájl.');
    expect(hiba.querySelector('svg')).not.toBeNull();
    expect(screen.getByRole('textbox', { name: 'A fájl új neve' })).toBeTruthy();
    utvonalak['/api/vault/atnevezes/terv'] = () => valasz({ hiba: 'Hálózati hiba.' }, 500);
    await fireEvent.keyDown(screen.getByRole('textbox', { name: 'A fájl új neve' }), { key: 'Enter' });
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Hálózati hiba.'));
    expect(hivasok('/api/vault/atnevezes')).toEqual([]);
  });

  it('Esc elvet, azonos vagy üres név nem kérdez semmit, a fókusz visszatér a sorra', async () => {
    const { mezo } = await indit('B.md');
    await fireEvent.keyDown(mezo, { key: 'Escape' });
    expect(screen.queryByRole('textbox')).toBeNull();
    await fireEvent.keyDown(sor('B.md'), { key: 'F2' });
    let m2 = (await screen.findByRole('textbox')) as HTMLInputElement;
    await fireEvent.keyDown(m2, { key: 'Enter' }); // változatlan név
    expect(screen.queryByRole('textbox')).toBeNull();
    await fireEvent.keyDown(sor('B.md'), { key: 'F2' });
    m2 = (await screen.findByRole('textbox')) as HTMLInputElement;
    await fireEvent.input(m2, { target: { value: '   ' } });
    await fireEvent.keyDown(m2, { key: 'Enter' });
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(kerelmek).toEqual([]);
  });

  it('a ⌘P F2-parancs a fókuszált fa-sorban helyben indít, az aktív fájlra továbbra is a terv-átfedés', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    const parancs = atnevezesParancsok(k.felulet).find((p) => p.id === 'vault.atnevezes')!;
    render(Fa, { context: k.context });
    sor('C.md').focus();
    parancs.futtat();
    expect(await screen.findByRole('textbox', { name: 'A fájl új neve' })).toBeTruthy();
    expect(k.felulet.atfedes).toBeNull();
    cleanup();
    k.felulet.munkaterulet.megnyit('A.md');
    (document.activeElement as HTMLElement | null)?.blur();
    parancs.futtat();
    expect(k.felulet.atfedes).toBe('atnevezes');
    expect(k.felulet.atnevezes).toMatchObject({ ut: 'A.md', mod: 'nev' });
  });
});

describe('07-explorer-06/07: másolat és Finder', () => {
  it('Make a copy: a core másol, a másolat megnyílik új fülben és látszik a fában', async () => {
    utvonalak['/api/vault/masolat'] = (b) => ({ ok: true, forras: b.ut, ut: 'B 1.md', pillanat: 'p', figyelmeztetes: null });
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.contextMenu(sor('B.md'), { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Másolat készítése' }));
    await waitFor(() => expect(hivasok('/api/vault/masolat').length).toBe(1));
    expect(hivasok('/api/vault/masolat')[0].body).toEqual({ ut: 'B.md' });
    await waitFor(() => expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('B 1.md'));
    expect(k.frissit).toHaveBeenCalled();
    expect(k.felulet.faMegmutat?.ut).toBe('B 1.md');
    expect(ertesitesek.lista.at(-1)).toMatchObject({ szint: 'siker', cim: 'Másolat elkészült' });
  });

  it('a másolás hibája értesítésként látszik, fül nem nyílik; mappán a menü nem kínál másolatot', async () => {
    utvonalak['/api/vault/masolat'] = () => valasz({ hiba: 'A fájlban mentetlen dokumentum van.' }, 409);
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.contextMenu(sor('Zeta'), { clientX: 5, clientY: 5 });
    expect(screen.queryByRole('option', { name: 'Másolat készítése' })).toBeNull();
    await fireEvent.keyDown(document.body, { key: 'Escape' });
    await fireEvent.contextMenu(sor('A.md'), { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Másolat készítése' }));
    await waitFor(() => expect(ertesitesek.lista.at(-1)?.szint).toBe('hiba'));
    expect(ertesitesek.lista.at(-1)?.szoveg).toContain('mentetlen dokumentum');
    expect(k.felulet.munkaterulet.aktivFul?.ut ?? null).toBeNull();
  });

  it('Reveal in Finder: fájlra és mappára a core végpontját hívja, a hibát megmutatja', async () => {
    utvonalak['/api/vault/finder'] = (b) => (b.ut === 'Zeta' ? valasz({ hiba: 'A Finder csak macOS-en érhető el.' }, 501) : { ok: true });
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    await fireEvent.contextMenu(sor('A.md'), { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Megmutatás a Finderben' }));
    await waitFor(() => expect(hivasok('/api/vault/finder').length).toBe(1));
    expect(hivasok('/api/vault/finder')[0].body).toEqual({ ut: 'A.md' });
    await fireEvent.contextMenu(sor('Zeta'), { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Megmutatás a Finderben' }));
    await waitFor(() => expect(ertesitesek.lista.at(-1)?.szint).toBe('hiba'));
    expect(k.felulet.munkaterulet.aktivFul?.ut ?? null).toBeNull(); // semmi nem nyílt meg
  });
});

describe('07-explorer-11: az aktív fájl automatikus követése', () => {
  it('bekapcsolva az ősmappák kinyílnak és a sor látszik, a fókuszt nem veszi el; kikapcsolva a fa nem változik', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [], autoMegmutat: true } });
    render(Fa, { context: k.context });
    const kulso = document.createElement('input'); document.body.append(kulso); kulso.focus();
    k.felulet.munkaterulet.megnyit('Zeta/Sub/Leaf.md'); flushSync();
    await waitFor(() => expect(k.felulet.oldalsav.nyitott).toEqual(expect.arrayContaining(['Zeta', 'Zeta/Sub'])));
    await waitFor(() => expect(sorUtak()).toContain('Zeta/Sub/Leaf.md'));
    expect(document.activeElement).toBe(kulso);
    k.felulet.oldalsav.autoMegmutat = false; k.felulet.oldalsav.nyitott = []; flushSync();
    k.felulet.munkaterulet.megnyit('Zeta/Child.md'); flushSync();
    await new Promise((r) => setTimeout(r, 10));
    expect(k.felulet.oldalsav.nyitott).toEqual([]);
  });

  it('a beállítás mentődik, és a ⌘P-parancs kapcsolja', () => {
    const felulet = new Felulet({ csend: { be: false } }), reg = new Regiszter();
    le.push(alapParancsok(reg, felulet));
    reg.futtat('fa.auto-megmutat');
    expect(felulet.oldalsav.autoMegmutat).toBe(true);
    expect(new Felulet(JSON.parse(JSON.stringify(felulet.sorosit()))).oldalsav.autoMegmutat).toBe(true);
    reg.futtat('fa.auto-megmutat');
    expect(felulet.oldalsav.autoMegmutat).toBe(false);
  });
});

describe('07-explorer-15: húzásos áthelyezés megerősítés nélkül, ha nincs link-változás', () => {
  function huz(honnan: HTMLElement, hova: HTMLElement) {
    const adat = new Map<string, string>();
    const dataTransfer = { setData: (a: string, v: string) => adat.set(a, v), getData: (a: string) => adat.get(a) ?? '', types: [], files: [], effectAllowed: '', dropEffect: '' };
    fireEvent.dragStart(honnan, { dataTransfer }); flushSync();
    fireEvent.dragOver(hova, { dataTransfer }); flushSync();
    fireEvent.drop(hova, { dataTransfer }); flushSync();
  }

  it('terv link nélkül: azonnal átkerül, a Visszavonás értesítés megvan, átfedés nincs', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj));
    utvonalak['/api/vault/atnevezes'] = (b) => eredmeny(String(b.ut), String(b.uj));
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    huz(sor('A.md'), sor('Empty'));
    await waitFor(() => expect(hivasok('/api/vault/atnevezes').length).toBe(1));
    expect(hivasok('/api/vault/atnevezes')[0].body).toEqual({ ut: 'A.md', uj: 'Empty/A.md', terv_hash: 'h-A.md' });
    expect(k.felulet.atfedes).toBeNull();
    expect(k.felulet.atnevezes).toBeNull();
    expect(ertesitesek.lista.at(-1)?.muvelet?.nev).toBe('Visszavonás');
  });

  it('terv link-változással, blokkolóval, figyelmeztetéssel vagy hibával: az átfedés nyílik, a core-ba semmi nem ír', async () => {
    for (const eset of [
      terv('A.md', 'Empty/A.md', { fajlok: [{ ut: 'H.md', alap: 'x', darab: 1, linkek: [] }], modositott_linkek: 1 }),
      terv('A.md', 'Empty/A.md', { ok: false, blokkolok: ['Foglalt.'] }),
      terv('A.md', 'Empty/A.md', { figyelmeztetesek: [{ ut: 'x.base', hely: 'f', kifejezes: 'k', uzenet: 'u' }] }),
    ]) {
      kerelmek.length = 0;
      utvonalak['/api/vault/atnevezes/terv'] = () => eset;
      const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
      const r = render(Fa, { context: k.context });
      huz(sor('A.md'), sor('Empty'));
      await waitFor(() => expect(k.felulet.atnevezes).toEqual({ ut: 'A.md', mod: 'hely', mappa: false, cel: 'Empty' }));
      expect(hivasok('/api/vault/atnevezes')).toEqual([]);
      r.unmount();
    }
  });

  it('ha a végrehajtás hibázik, az átfedés újratervez (nem vész el a kérés)', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj));
    utvonalak['/api/vault/atnevezes'] = () => valasz({ hiba: 'A vault közben megváltozott.' }, 409);
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    render(Fa, { context: k.context });
    huz(sor('A.md'), sor('Empty'));
    await waitFor(() => expect(k.felulet.atnevezes?.cel).toBe('Empty'));
  });

  it('mappa is azonnal mozog, ha a terv link nélküli; a saját részfájába húzás továbbra sem ejthető', async () => {
    utvonalak['/api/vault/atnevezes/terv'] = (b) => terv(String(b.ut), String(b.uj), { mappa: true, mozgo_fajlok: 2 });
    utvonalak['/api/vault/atnevezes'] = (b) => ({ ...eredmeny(String(b.ut), String(b.uj)), mappa: true, mozgo_fajlok: 2 });
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: ['Zeta'] } });
    render(Fa, { context: k.context });
    huz(sor('Zeta'), sor('Zeta/Sub'));
    await new Promise((r) => setTimeout(r, 10));
    expect(kerelmek).toEqual([]);
    huz(sor('Zeta'), sor('Empty'));
    await waitFor(() => expect(hivasok('/api/vault/atnevezes').length).toBe(1));
    expect(hivasok('/api/vault/atnevezes')[0].body).toMatchObject({ ut: 'Zeta', uj: 'Empty/Zeta' });
  });
});

describe('07-explorer palettaparancsok: rendezés, kinyitás, kapcsolók, Finder, másolat', () => {
  it('a hat rendezési mód parancsként elérhető, az aktuális nem kínálja magát; a rendezés tartós', () => {
    const felulet = new Felulet({ csend: { be: false } }), reg = new Regiszter();
    le.push(alapParancsok(reg, felulet));
    const azonositok = ['nev', 'nev-forditva', 'modositva', 'modositva-regi', 'letrehozva', 'letrehozva-regi'];
    for (const mod of azonositok) expect(reg.kap(`fa.rendez-${mod}`)).toBeTruthy();
    expect(reg.elerheto(reg.kap('fa.rendez-nev')!)).toBe(false);
    reg.futtat('fa.rendez-letrehozva-regi');
    expect(felulet.oldalsav.rendezes).toBe('letrehozva-regi');
    expect(reg.elerheto(reg.kap('fa.rendez-letrehozva-regi')!)).toBe(false);
    expect(new Felulet(JSON.parse(JSON.stringify(felulet.sorosit()))).oldalsav.rendezes).toBe('letrehozva-regi');
  });

  it('az „Összes mappa kinyitása” parancs a fában minden mappát kinyit', async () => {
    const k = kornyezet({ csend: { be: false }, oldalsav: { szelesseg: 264, nyitva: true, nyitott: [] } });
    const reg = new Regiszter();
    le.push(alapParancsok(reg, k.felulet));
    render(Fa, { context: k.context });
    reg.futtat('fa.kinyit-mind'); flushSync();
    await waitFor(() => expect([...k.felulet.oldalsav.nyitott].sort()).toEqual(['Empty', 'Zeta', 'Zeta/Sub']));
    expect(k.felulet.oldalsav.nezet).toBe('fajlok');
  });

  it('a „minden fájltípus” kapcsoló parancs, a Finder és a másolat az aktív fájlra hívja a core-t', async () => {
    utvonalak['/api/vault/finder'] = () => ({ ok: true });
    utvonalak['/api/vault/masolat'] = (b) => ({ ok: true, forras: b.ut, ut: 'A 1.md', pillanat: null, figyelmeztetes: null });
    const felulet = new Felulet({ csend: { be: false } }), reg = new Regiszter();
    le.push(alapParancsok(reg, felulet));
    reg.futtat('fa.minden-fajl'); expect(felulet.oldalsav.mindenFajl).toBe(true);
    expect(reg.elerheto(reg.kap('fa.finder')!)).toBe(false);
    expect(reg.elerheto(reg.kap('fa.masolat')!)).toBe(false);
    felulet.munkaterulet.megnyit('A.md');
    expect(reg.elerheto(reg.kap('fa.finder')!)).toBe(true);
    reg.futtat('fa.finder');
    await waitFor(() => expect(hivasok('/api/vault/finder')[0]?.body).toEqual({ ut: 'A.md' }));
    reg.futtat('fa.masolat');
    await waitFor(() => expect(hivasok('/api/vault/masolat')[0]?.body).toEqual({ ut: 'A.md' }));
    await waitFor(() => expect(felulet.munkaterulet.aktivFul?.ut).toBe('A 1.md'));
  });
});
