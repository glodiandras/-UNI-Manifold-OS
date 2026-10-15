// Átnevezés és áthelyezés a felületen (C10): a párbeszéd (név/mappa → terv-lista → megerősítés → értesítés
// „Visszavonás”-sal), a blokkolók, a közben megváltozott vault; a `vault_atnevezes` WS-esemény (a fülek átcímzése, az
// „eltűnt” értesítés elnyomása); a parancsok; `Munkaterulet.utatNevez`. A link-átírás és a referencia-próba a core
// tesztjeié (tests/test_atnevezes.py, tests/kezi/atnevezes_proba.py).

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Atnevezes from '../src/atfedes/Atnevezes.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { szerkesztoTelepit } from '../src/szerkeszto';
import { atnevezesParancsok } from '../src/szerkeszto/linkek/atnevezes';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

let kerelmek: { url: string; body?: Record<string, unknown> }[];
let terv: Record<string, unknown>;
let vegrehajtas: { kod: number; adat: Record<string, unknown> };

const TERV = {
  ok: true,
  regi: 'Matek/Mértani.md',
  uj: 'Matek/Mértani sorozat.md',
  blokkolok: [],
  fajlok: [
    { ut: 'Matek/Számtani.md', alap: 'a', darab: 2, linkek: [{ sor: 3, regi: 'Lásd [[Mértani]]', uj: 'Lásd [[Mértani sorozat]]' }, { sor: 9, regi: '[[Mértani|q]]', uj: '[[Mértani sorozat|q]]' }] },
    { ut: 'Vászon.canvas', alap: 'b', darab: 1, linkek: [{ sor: 4, regi: 'Matek/Mértani.md', uj: 'Matek/Mértani sorozat.md' }] },
  ],
  modositott_linkek: 3,
  osszes_link: 13638,
  uj_feloldott: 1,
  terv_hash: 'hash1',
};

function valasz(adat: unknown, kod = 200) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  kerelmek = [];
  terv = TERV;
  vegrehajtas = { kod: 200, adat: { ok: true, regi: TERV.regi, uj: TERV.uj, modositott: ['Matek/Számtani.md', 'Vászon.canvas'], pillanat: 'abc123', ms: 900 } };
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push({ url: u.pathname, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/vault/atnevezes/terv') return valasz(terv);
    if (u.pathname === '/api/vault/atnevezes') return valasz(vegrehajtas.adat, vegrehajtas.kod);
    if (u.pathname === '/api/pillanat/vault/visszavonas') return valasz({ ok: true, sha: 'def' });
    if (u.pathname === '/api/vault/fajl') return valasz({ hiba: 'nincs' }, 404);
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  ertesitesek.lista.length = 0;
  szerkesztok.atnevezesAlatt.clear();
  vi.unstubAllGlobals();
});

function kornyezet(ut = 'Matek/Mértani.md', mod: 'nev' | 'hely' = 'nev', extra: { mappa?: boolean; cel?: string } = {}) {
  const felulet = new Felulet({});
  felulet.munkaterulet.megnyit(ut);
  const fajlok = new VaultFajlok();
  fajlok.mappak = ['Matek', 'Matek/Sorozatok', 'Történelem'];
  felulet.atnevezes = { ut, mod, ...extra };
  felulet.atfedes = 'atnevezes';
  const kapcsolat = new CoreKapcsolat('ws://x');
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]);
  return { felulet, fajlok, kapcsolat, context };
}

describe('a párbeszéd: átnevezés', () => {
  it('az új név bevitele → terv-lista → megerősítés → egy kérés a terv hash-ével, értesítés visszavonással', async () => {
    const { felulet, context } = kornyezet();
    render(Atnevezes, { context });
    const mezo = screen.getByLabelText('Új név') as HTMLInputElement;
    expect(mezo.value).toBe('Mértani');
    expect(document.activeElement).toBe(mezo);
    await fireEvent.input(mezo, { target: { value: 'Mértani sorozat' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(screen.getByText(/2 fájlban 3 link/)).toBeTruthy());
    expect(kerelmek[0]).toEqual({ url: '/api/vault/atnevezes/terv', body: { ut: 'Matek/Mértani.md', uj: 'Matek/Mértani sorozat.md' } });
    expect(screen.getByText(/13638 linkjéből/)).toBeTruthy();
    expect(screen.getByText(/1 eddig feloldatlan link/)).toBeTruthy();
    expect(screen.getByText('Matek/Számtani.md')).toBeTruthy();
    expect(screen.getAllByText('Lásd [[Mértani sorozat]]')).toHaveLength(1); // az előtte→utána sorok a fájl kibontásában
    await fireEvent.click(screen.getByRole('button', { name: 'Átnevezés' }));
    await waitFor(() => expect(felulet.atfedes).toBeNull());
    expect(kerelmek.at(-1)).toEqual({ url: '/api/vault/atnevezes', body: { ut: 'Matek/Mértani.md', uj: 'Matek/Mértani sorozat.md', terv_hash: 'hash1' } });
    const e = ertesitesek.lista.at(-1)!;
    expect(e.cim).toBe('Átnevezve');
    expect(e.szoveg).toContain('2 jegyzet linkjei átírva');
    expect(e.muvelet!.nev).toBe('Visszavonás');
  });

  it('a kiterjesztés a névből kihagyva (a .md-t beírva sem duplázódik); a mappa marad', async () => {
    const { context } = kornyezet('Matek/Sorozatok/Mértani.md');
    render(Atnevezes, { context });
    const mezo = screen.getByLabelText('Új név');
    await fireEvent.input(mezo, { target: { value: 'Új.md' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(kerelmek[0].body).toEqual({ ut: 'Matek/Sorozatok/Mértani.md', uj: 'Matek/Sorozatok/Új.md' }));
  });

  it('blokkolók: a gomb tiltva, a lista indokkal; „Vissza” a névmezőhöz visz', async () => {
    terv = { ...TERV, ok: false, blokkolok: ['Már van ilyen nevű fájl: Matek/Mértani sorozat.md'], fajlok: [] };
    const { context } = kornyezet();
    render(Atnevezes, { context });
    await fireEvent.keyDown(screen.getByLabelText('Új név'), { key: 'Enter' });
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Már van ilyen'));
    expect((screen.getByRole('button', { name: 'Átnevezés' }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: 'Vissza' }));
    expect(screen.getByLabelText('Új név')).toBeTruthy();
  });

  it('a `.base`-kifejezések figyelmeztetései (C12b): láthatók, nem tiltják az átnevezést', async () => {
    terv = {
      ...TERV,
      figyelmeztetesek: [{ ut: 'Bazis/Konyvek.base', hely: 'filters.and[1]', kifejezes: 'file.name == "Mértani"', uzenet: 'a név szerinti összehasonlítást nem írom át' }],
    };
    const { context } = kornyezet();
    render(Atnevezes, { context });
    await fireEvent.keyDown(screen.getByLabelText('Új név'), { key: 'Enter' });
    const lista = await waitFor(() => screen.getByRole('status', { name: 'Átnézendő adatbázis-kifejezések' }));
    expect(lista.textContent).toContain('Bazis/Konyvek.base');
    expect(lista.textContent).toContain('filters.and[1]');
    expect((screen.getByRole('button', { name: 'Átnevezés' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('közben megváltozott vault (409 valtozott): új terv jelenik meg, nem zár be', async () => {
    const { felulet, context } = kornyezet();
    render(Atnevezes, { context });
    await fireEvent.keyDown(screen.getByLabelText('Új név'), { key: 'Enter' });
    await waitFor(() => screen.getByRole('button', { name: 'Átnevezés' }));
    vegrehajtas = { kod: 409, adat: { hiba: 'A vault közben megváltozott', valtozott: true } };
    terv = { ...TERV, terv_hash: 'hash2' };
    await fireEvent.click(screen.getByRole('button', { name: 'Átnevezés' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('közben megváltozott'));
    expect(felulet.atfedes).toBe('atnevezes');
    expect(kerelmek.filter((k) => k.url === '/api/vault/atnevezes/terv')).toHaveLength(2);
  });

  it('a referencia-próba hibája: a hibák felsorolva, a párbeszéd nyitva', async () => {
    vegrehajtas = { kod: 500, adat: { hiba: 'A referencia-próba hibát talált, az átnevezés visszaállt.', proba_hibak: ['Számtani.md: a 2. link …'] } };
    const { felulet, context } = kornyezet();
    render(Atnevezes, { context });
    await fireEvent.keyDown(screen.getByLabelText('Új név'), { key: 'Enter' });
    await waitFor(() => screen.getByRole('button', { name: 'Átnevezés' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Átnevezés' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('visszaállt'));
    expect(screen.getByRole('alert').textContent).toContain('Számtani.md: a 2. link');
    expect(felulet.atfedes).toBe('atnevezes');
  });

  it('a „Visszavonás” művelet a pillanatkép-végpontra megy, és visszacímzi a füleket', async () => {
    const { felulet, context, kapcsolat } = kornyezet();
    render(Atnevezes, { context });
    await fireEvent.keyDown(screen.getByLabelText('Új név'), { key: 'Enter' });
    await waitFor(() => screen.getByRole('button', { name: 'Átnevezés' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Átnevezés' }));
    await waitFor(() => expect(felulet.atfedes).toBeNull());
    felulet.utatNevez('Matek/Mértani.md', 'Matek/Mértani sorozat.md'); // ezt a WS-esemény tenné
    ertesitesek.lista.at(-1)!.muvelet!.futtat();
    await waitFor(() => expect(kerelmek.at(-1)).toEqual({ url: '/api/pillanat/vault/visszavonas', body: { sha: 'abc123' } }));
    await waitFor(() => expect(felulet.munkaterulet.aktivFul!.ut).toBe('Matek/Mértani.md'));
    void kapcsolat;
  });
});

describe('a párbeszéd: áthelyezés', () => {
  it('a mappa fuzzy keresése, ↩ a kijelöltre tervez (a név marad)', async () => {
    const { context } = kornyezet('Matek/Mértani.md', 'hely');
    render(Atnevezes, { context });
    const mezo = screen.getByRole('combobox');
    expect(screen.getAllByRole('option').map((o) => o.textContent!.trim())).toEqual(['(a vault gyökere)', 'Matek', 'Matek/Sorozatok', 'Történelem']);
    await fireEvent.input(mezo, { target: { value: 'sorozat' } });
    await waitFor(() => expect(screen.getAllByRole('option')[0].textContent!.trim()).toBe('Matek/Sorozatok'));
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(kerelmek[0].body).toEqual({ ut: 'Matek/Mértani.md', uj: 'Matek/Sorozatok/Mértani.md' }));
  });

  it('a gyökérbe: a mappa nélküli új út', async () => {
    const { context } = kornyezet('Matek/Mértani.md', 'hely');
    render(Atnevezes, { context });
    await fireEvent.click(screen.getAllByRole('option')[0].querySelector('button')!);
    await waitFor(() => expect(kerelmek[0].body).toEqual({ ut: 'Matek/Mértani.md', uj: 'Mértani.md' }));
  });
});

describe('parancsok', () => {
  it('csak szöveges aktív fájlra élnek; futtatva a párbeszédet nyitják', () => {
    const felulet = new Felulet({});
    const reg = new Regiszter();
    const le = reg.regisztralMind(atnevezesParancsok(felulet));
    const ids = () => reg.lista().map((p) => p.id);
    expect(ids()).not.toContain('vault.atnevezes'); // nincs megnyitott fájl
    felulet.munkaterulet.megnyit('Könyv.pdf');
    expect(ids()).not.toContain('vault.atnevezes');
    felulet.munkaterulet.megnyit('Matek/Mértani.md');
    expect(ids()).toEqual(expect.arrayContaining(['vault.atnevezes', 'vault.athelyezes']));
    void reg.futtat('vault.athelyezes');
    expect(felulet.atfedes).toBe('atnevezes');
    expect(felulet.atnevezes).toEqual({ ut: 'Matek/Mértani.md', mod: 'hely' });
    le();
  });
});

describe('a vault_atnevezes WS-esemény és a fülek', () => {
  it('Munkaterulet.utatNevez: az új útra vált, a nézet-állapot megmarad', () => {
    const felulet = new Felulet({});
    felulet.munkaterulet.megnyit('A.md');
    felulet.munkaterulet.aktivFul!.nezet = { sor: 12, mod: 'olvaso' };
    felulet.munkaterulet.megnyit('C.md', 'ujful');
    felulet.fajlNyitva('A.md');
    felulet.utatNevez('A.md', 'B.md');
    const fulek = felulet.munkaterulet.aktivPanel.fulek;
    expect(fulek.map((f) => f.ut)).toEqual(['B.md', 'C.md']);
    expect(fulek[0].nezet).toEqual({ sor: 12, mod: 'olvaso' });
    expect(felulet.legutobbiFajlok).toEqual(['B.md', 'C.md'].filter((u) => felulet.legutobbiFajlok.includes(u)));
    expect(felulet.legutobbiFajlok).not.toContain('A.md');
  });

  it('kezd: a közbeeső „eltűnt” elnémul; kesz: átcímzés, a régi dokumentum kikerül; vissza: újra figyel', async () => {
    const felulet = new Felulet({});
    felulet.munkaterulet.megnyit('A.md');
    const fajlok = new VaultFajlok();
    const kapcsolat = new CoreKapcsolat('ws://x');
    const reg = new Regiszter();
    const le = szerkesztoTelepit(reg, kapcsolat, felulet, fajlok);
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://x/');
      return u.pathname === '/api/vault/fajl' ? valasz({ ut: 'A.md', tartalom: '# A\n', hash: 'h', jel: '', mtime: 0, kodolas_hiba: false }) : valasz({}, 404);
    });
    const dok = await szerkesztok.dokumentumok.megnyit('A.md');
    const eltunt = () => ertesitesek.lista.some((e) => e.cim.includes('eltűnt'));

    kapcsolat.szetoszt({ tipus: 'vault_atnevezes', allapot: 'kezd', regi: 'A.md', uj: 'B.md' });
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: [], torolt: ['A.md'], kulso: [] });
    expect(dok.allapot).not.toBe('eltunt');
    expect(eltunt()).toBe(false);

    kapcsolat.szetoszt({ tipus: 'vault_atnevezes', allapot: 'kesz', regi: 'A.md', uj: 'B.md', modositott: ['B.md'], pillanat: 'x' });
    expect(felulet.munkaterulet.aktivFul!.ut).toBe('B.md');
    expect(szerkesztok.dokumentumok.kap('A.md')).toBeUndefined();

    // egy másik fájl valódi eltűnése továbbra is jelez
    const masik = await szerkesztok.dokumentumok.megnyit('A.md'); // (az ál-core újra „A”-t ad: itt csak a jelzés kell)
    kapcsolat.szetoszt({ tipus: 'vault_atnevezes', allapot: 'vissza', regi: 'A.md', uj: 'B.md' });
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: [], torolt: ['A.md'], kulso: [] });
    expect(masik.allapot).toBe('eltunt');
    expect(eltunt()).toBe(true);
    le();
  });
});

describe('mappa átnevezése és áthelyezése (C11a, 21. döntés)', () => {
  const MAPPA_TERV = {
    ...TERV,
    regi: 'Matek/Sorozatok',
    uj: 'Matek/Sor',
    mappa: true,
    mozgo_fajlok: 5,
    terv_hash: 'mappahash',
  };

  it('átnevezés: a mappa neve a mező (kiterjesztés nélkül), a terv a mappa útját kapja, az összegzés a mozgó jegyzeteket is mondja', async () => {
    terv = MAPPA_TERV;
    vegrehajtas = { kod: 200, adat: { ok: true, regi: 'Matek/Sorozatok', uj: 'Matek/Sor', mappa: true, mozgo_fajlok: 5, modositott: ['Matek/Sor/A.md', 'Más.md'], pillanat: 'm1', ms: 1200 } };
    const { felulet, context } = kornyezet('Matek/Sorozatok', 'nev', { mappa: true });
    render(Atnevezes, { context });
    expect(screen.getByRole('heading', { name: 'Mappa átnevezése' })).toBeTruthy();
    const mezo = screen.getByLabelText('Új név') as HTMLInputElement;
    expect(mezo.value).toBe('Sorozatok');
    await fireEvent.input(mezo, { target: { value: 'Sor' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(screen.getByText(/5 jegyzet/)).toBeTruthy());
    expect(kerelmek[0]).toEqual({ url: '/api/vault/atnevezes/terv', body: { ut: 'Matek/Sorozatok', uj: 'Matek/Sor' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Átnevezés' }));
    await waitFor(() => expect(felulet.atfedes).toBeNull());
    const e = ertesitesek.lista.at(-1)!;
    expect(e.cim).toBe('Mappa átnevezve');
    expect(e.szoveg).toContain('5 jegyzet');
    expect(e.szoveg).toContain('1 jegyzet linkjei átírva'); // a mappán kívüli módosított fájl
    expect(e.muvelet!.nev).toBe('Visszavonás');
  });

  it('a húzás célmappával nyílik: azonnal a terv látszik (a mappa-választó kimarad), és a kérés a célmappába mutat', async () => {
    terv = { ...MAPPA_TERV, uj: 'Történelem/Sorozatok' };
    const { context } = kornyezet('Matek/Sorozatok', 'hely', { mappa: true, cel: 'Történelem' });
    render(Atnevezes, { context });
    await waitFor(() => expect(screen.getByText(/5 jegyzet/)).toBeTruthy());
    expect(kerelmek[0]).toEqual({ url: '/api/vault/atnevezes/terv', body: { ut: 'Matek/Sorozatok', uj: 'Történelem/Sorozatok' } });
    expect(screen.getByRole('button', { name: 'Áthelyezés' })).toBeTruthy();
    expect(screen.queryByPlaceholderText('Mappa keresése…')).toBeNull();
  });

  it('a terv megjelenésekor a fókusz a párbeszédben marad, és az Esc a fókuszvesztés után is zár (húzás utáni eset)', async () => {
    terv = { ...MAPPA_TERV, uj: 'Történelem/Sorozatok' };
    const { felulet, context } = kornyezet('Matek/Sorozatok', 'hely', { mappa: true, cel: 'Történelem' });
    render(Atnevezes, { context });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Áthelyezés' })).toBeTruthy());
    expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true);
    (document.activeElement as HTMLElement).blur(); // a fókusz a törzsre esik (a megszűnt mező után)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
    expect(felulet.atfedes).toBeNull();
  });

  it('fájl húzása a gyökérre: a célmappa üres, a kérés a gyökérbe mutat', async () => {
    terv = { ...TERV, uj: 'Mértani.md' };
    const { context } = kornyezet('Matek/Mértani.md', 'hely', { cel: '' });
    render(Atnevezes, { context });
    await waitFor(() => expect(kerelmek[0]).toEqual({ url: '/api/vault/atnevezes/terv', body: { ut: 'Matek/Mértani.md', uj: 'Mértani.md' } }));
  });

  it('mappa áthelyezésekor a választó nem kínálja a saját részfáját', () => {
    const { context } = kornyezet('Matek', 'hely', { mappa: true });
    render(Atnevezes, { context });
    const lista = screen.getByRole('listbox', { name: 'Mappák' });
    const nevek = [...lista.querySelectorAll('li')].map((l) => l.textContent?.trim());
    expect(nevek).toContain('(a vault gyökere)');
    expect(nevek).toContain('Történelem');
    expect(nevek).not.toContain('Matek/Sorozatok'); // a saját részfája
    expect(nevek).not.toContain('Matek');
  });

  it('a mappa blokkolója (média a részfában) indokkal látszik, a gomb tiltva', async () => {
    terv = { ...MAPPA_TERV, ok: false, fajlok: [], blokkolok: ['A mappa nem csak jegyzetet és canvast tartalmaz: Kep/kep.png.'] };
    const { context } = kornyezet('Matek/Sorozatok', 'nev', { mappa: true });
    render(Atnevezes, { context });
    await fireEvent.keyDown(screen.getByLabelText('Új név'), { key: 'Enter' });
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('nem csak jegyzetet'));
    expect((screen.getByRole('button', { name: 'Átnevezés' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a `vault_atnevezes` esemény mappánál: a fülek előtag szerint átcímződnek, az „eltűnt” elnyomva a mappa alatt', async () => {
    const { felulet, kapcsolat } = kornyezet('Matek/Sorozatok/A.md');
    const { atnevezesFigyel } = await import('../src/szerkeszto/linkek/atnevezes');
    const le = atnevezesFigyel(kapcsolat, felulet);
    kapcsolat.szetoszt({ tipus: 'vault_atnevezes', allapot: 'kezd', regi: 'Matek/Sorozatok', uj: 'Matek/Sor', mappa: true });
    expect(szerkesztok.atnevezesAlatt.has('Matek/Sorozatok/A.md')).toBe(true);
    expect(szerkesztok.atnevezesAlatt.has('Matek/Sorozatokx/A.md')).toBe(false); // az előtag-hasonló név nem
    kapcsolat.szetoszt({ tipus: 'vault_atnevezes', allapot: 'kesz', regi: 'Matek/Sorozatok', uj: 'Matek/Sor', mappa: true });
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('Matek/Sor/A.md');
    le();
  });
});

describe('mentetlen dokumentum az átnevezéskor (C29.6, T015)', () => {
  let leszed: (() => void) | null = null;
  beforeEach(() => {
    for (const d of szerkesztok.dokumentumok.lista()) szerkesztok.dokumentumok.eldob(d.ut); // az előző tesztek dokumentumai ne maradjanak
  });
  afterEach(() => {
    leszed?.();
    leszed = null;
  });
  it('kesz: a mentetlen dokumentum nem dobódik el — eltunt állapotban megmarad, az értesítés „Másolás” a szövegét adja', async () => {
    const felulet = new Felulet({});
    felulet.munkaterulet.megnyit('A.md');
    const kapcsolat = new CoreKapcsolat('ws://x');
    leszed = szerkesztoTelepit(new Regiszter(), kapcsolat, felulet, new VaultFajlok());
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://x/');
      return u.pathname === '/api/vault/fajl' ? valasz({ ut: 'A.md', tartalom: '# A\n', hash: 'h', jel: '', mtime: 0, kodolas_hiba: false }) : valasz({}, 404);
    });
    const dok = await szerkesztok.dokumentumok.megnyit('A.md');
    const { ChangeSet, Text } = await import('@codemirror/state');
    dok.valtozott(ChangeSet.of([{ from: 0, to: dok.szoveg.length, insert: '# A\ngépelt közben' }], dok.szoveg.length), Text.of(['# A', 'gépelt közben']), null);
    expect(dok.mentetlen).toBe(true);
    const vagolap: string[] = [];
    vi.stubGlobal('navigator', { clipboard: { writeText: async (s: string) => void vagolap.push(s) } });

    kapcsolat.szetoszt({ tipus: 'vault_atnevezes', allapot: 'kezd', regi: 'A.md', uj: 'B.md' });
    kapcsolat.szetoszt({ tipus: 'vault_atnevezes', allapot: 'kesz', regi: 'A.md', uj: 'B.md', modositott: ['B.md'], pillanat: 'x' });

    expect(szerkesztok.dokumentumok.kap('A.md')).toBe(dok);          // megmaradt
    expect(dok.allapot).toBe('eltunt');
    expect(dok.mentetlen).toBe(false);                               // a core többé nem tekinti mentetlennek
    expect(szerkesztok.dokumentumok.mentetlenUtak()).toEqual([]);
    const e = ertesitesek.lista.find((x) => x.cim.includes('Mentetlen szöveg'))!;
    expect(e).toBeTruthy();
    expect(e.muvelet!.nev).toBe('Másolás');
    e.muvelet!.futtat();
    await new Promise((r) => setTimeout(r, 0));
    expect(vagolap).toEqual(['# A\ngépelt közben']);
  });

  it('kesz mappánál: a mappa alatti tiszta dokumentum kikerül, a mentetlen megmarad', async () => {
    const felulet = new Felulet({});
    const kapcsolat = new CoreKapcsolat('ws://x');
    leszed = szerkesztoTelepit(new Regiszter(), kapcsolat, felulet, new VaultFajlok());
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://x/');
      const ut = u.searchParams.get('ut') ?? '';
      return u.pathname === '/api/vault/fajl' ? valasz({ ut, tartalom: '# x\n', hash: 'h', jel: '', mtime: 0, kodolas_hiba: false }) : valasz({}, 404);
    });
    const tiszta = await szerkesztok.dokumentumok.megnyit('M/Tiszta.md');
    const piszkos = await szerkesztok.dokumentumok.megnyit('M/Piszkos.md');
    const kivul = await szerkesztok.dokumentumok.megnyit('Mas.md');
    const { ChangeSet, Text } = await import('@codemirror/state');
    piszkos.valtozott(ChangeSet.of([{ from: 0, to: piszkos.szoveg.length, insert: 'új' }], piszkos.szoveg.length), Text.of(['új']), null);

    kapcsolat.szetoszt({ tipus: 'vault_atnevezes', allapot: 'kesz', regi: 'M', uj: 'N', mappa: true, modositott: [], pillanat: 'x' });

    expect(szerkesztok.dokumentumok.kap('M/Tiszta.md')).toBeUndefined();
    expect(szerkesztok.dokumentumok.kap('M/Piszkos.md')).toBe(piszkos);
    expect(piszkos.allapot).toBe('eltunt');
    expect(szerkesztok.dokumentumok.kap('Mas.md')).toBe(kivul);
    void tiszta;
  });

  it('409 „nyitott”: a felület egyszer újrapróbál (a WS-jelentés lemaradhat a mentés mögött)', async () => {
    let hivas = 0;
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname === '/api/vault/atnevezes') {
        hivas++;
        return hivas === 1
          ? valasz({ hiba: 'A jegyzet nyitva van mentetlen változással', nyitott: true, utak: ['A.md'] }, 409)
          : valasz({ ok: true, regi: 'A.md', uj: 'B.md', modositott: [], pillanat: 'p', ms: 1 });
      }
      return valasz({}, 404);
    });
    const { atnevezesVegrehajt } = await import('../src/szerkeszto/linkek/atnevezes');
    const r = await atnevezesVegrehajt('A.md', 'B.md', 'h');
    expect(r.ok).toBe(true);
    expect(hivas).toBe(2);
  });

  it('más 409 (nem „nyitott”) nem próbálkozik újra', async () => {
    let hivas = 0;
    vi.stubGlobal('fetch', async () => {
      hivas++;
      return valasz({ hiba: 'A vault közben megváltozott', valtozott: true }, 409);
    });
    const { atnevezesVegrehajt } = await import('../src/szerkeszto/linkek/atnevezes');
    await expect(atnevezesVegrehajt('A.md', 'B.md', 'h')).rejects.toThrow();
    expect(hivas).toBe(1);
  });
});
