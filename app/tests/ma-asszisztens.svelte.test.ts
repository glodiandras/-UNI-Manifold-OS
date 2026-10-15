// Az Asszisztens a „Ma” oldalon (C30a): a szakasz csak akkor jelenik meg, ha van mit mutatni (új higiénia-tétel vagy heti
// javaslat); az új tételek listája kérésre töltődik, a „Láttam” nulláz, a javaslat gombjai döntések; kikapcsolt kapcsolónál
// nincs szakasz és nincs javaslat-kérés; a teljes Ma oldal fejlécei változatlanok, ha nincs mit mutatni.

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { asszisztensMa } from '../src/lib/asszisztens/adat.svelte';
import type { HigieniaOsszegzes, SzokasJavaslat } from '../src/lib/asszisztens/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Asszisztens from '../src/ma/Asszisztens.svelte';
import Ma from '../src/ma/Ma.svelte';
import { maAdat } from '../src/ma/modell.svelte';
import type { MaAsszisztens, MaValasz } from '../src/ma/tipusok';

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

const JAVASLAT: SzokasJavaslat = {
  azon: 'szokas:2026-W41:Mathematics', allapot: 'uj', tantargy: 'Mathematics', tantargy_nev: 'matematika', nap_neve: 'szerda', hit: 6, het: 8,
  atlag_perc: 48, legutobbi_ut: 'M01 - Matek/Függvények.md', szoveg: 'Szerdánként általában tanulsz (tantárgy: matematika).',
};

const OSSZEGZES: HigieniaOsszegzes = {
  kapcsolo: true, kesz: true, szamolva: '2026-10-04T21:00:00+02:00', szamol: false, szunetel: false, hiba: null, alapvonal: false,
  osszesites: { ossz: 7 }, ossz: 7, uj: 2,
  uj_tetelek: [
    { azonosito: 'torott_link:a', fajta: 'torott_link', szint: 'hiba', ut: 'M01 - Matek/Sorozatok.md', sor: 12, uzenet: 'Törött link: Nincs' },
    { azonosito: 'arva_jegyzet:b', fajta: 'arva_jegyzet', szint: 'tajekoztato', ut: 'F01 - Fizika/Mozgás.md', sor: null, uzenet: 'Árva jegyzet' },
  ],
};

const SZAKASZ: MaAsszisztens = { kapcsolo: true, higienia: { kesz: true, ossz: 7, uj: 2 } };

let kerelmek: { url: string; metodus: string; body?: unknown }[];
let valaszok: Record<string, (init?: RequestInit) => Response>;
let context: Map<unknown, unknown>;
let felulet: Felulet;

beforeEach(() => {
  kerelmek = [];
  valaszok = {
    'GET /api/asszisztens/szokas': () => json({ javaslat: null }),
    'GET /api/asszisztens/higienia': () => json(OSSZEGZES),
  };
  asszisztensMa.osszegzes = null;
  asszisztensMa.szokas = null;
  asszisztensMa.hiba = null;
  asszisztensMa.foglalt = false;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const metodus = init?.method ?? 'GET';
    kerelmek.push({ url: u.pathname + u.search, metodus, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const f = valaszok[`${metodus} ${u.pathname}`];
    return f ? f(init) : json({ hiba: 'nincs' }, 404);
  });
  felulet = new Felulet({});
  context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
});

const megjelenit = (szakasz: MaAsszisztens | { hiba: string } | undefined, datum: string | undefined = '2026-10-07') =>
  render(Asszisztens, { context, props: { szakasz, datum } });

describe('az Asszisztens szakasz a Ma oldalon', () => {
  it('nincs mit mutatni: a szakasz nem jelenik meg, és nincs fölösleges kérés kikapcsolva', async () => {
    megjelenit({ kapcsolo: false, higienia: { kesz: true, ossz: 9, uj: 4 } });
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole('region', { name: 'Asszisztens' })).toBeNull();
    expect(kerelmek).toEqual([]);
  });

  it('nincs új tétel és nincs javaslat: üres; hiba-szakasz vagy hiányzó szakasz: üres', async () => {
    megjelenit({ kapcsolo: true, higienia: { kesz: true, ossz: 9, uj: 0 } });
    await waitFor(() => expect(kerelmek.some((k) => k.url === '/api/asszisztens/szokas')).toBe(true));
    expect(screen.queryByRole('region', { name: 'Asszisztens' })).toBeNull();
    cleanup();
    megjelenit({ hiba: 'x' });
    megjelenit(undefined);
    expect(screen.queryByRole('region', { name: 'Asszisztens' })).toBeNull();
  });

  it('új tételek: a szám látszik, az áttekintés kérésre tölt, a sorra ugrás megnyitja a jegyzetet', async () => {
    megjelenit(SZAKASZ);
    const reg = await screen.findByRole('region', { name: 'Asszisztens' });
    expect(within(reg).getByText('2 új észrevétel')).toBeTruthy();
    expect(within(reg).getByText('(összesen 7)')).toBeTruthy();
    expect(kerelmek.some((k) => k.url === '/api/asszisztens/higienia')).toBe(false);          // csak kérésre
    await fireEvent.click(within(reg).getByRole('button', { name: 'Áttekintés' }));
    const elso = await within(reg).findByRole('button', { name: /Törött link.*Nincs.*Sorozatok/ });
    await fireEvent.click(elso);
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('M01 - Matek/Sorozatok.md');
    expect(within(reg).getByRole('button', { name: 'Elrejtés' })).toBeTruthy();
  });

  it('a „Láttam” a core-nak megy, és a szám nullázódik a válasszal', async () => {
    valaszok['POST /api/asszisztens/higienia/latva'] = () => json({ ...OSSZEGZES, uj: 0, uj_tetelek: [] });
    megjelenit(SZAKASZ);
    const reg = await screen.findByRole('region', { name: 'Asszisztens' });
    await fireEvent.click(within(reg).getByRole('button', { name: 'Láttam' }));
    await waitFor(() => expect(kerelmek.some((k) => k.metodus === 'POST' && k.url === '/api/asszisztens/higienia/latva')).toBe(true));
    await waitFor(() => expect(asszisztensMa.osszegzes?.uj).toBe(0));
  });

  it('heti javaslat: megnyitás elfogadás, „Nem kell” elutasítás — mindkettő döntés a core-nak', async () => {
    valaszok['GET /api/asszisztens/szokas'] = () => json({ javaslat: JAVASLAT });
    valaszok['POST /api/asszisztens/szokas/dontes'] = () => json({ ok: true });
    megjelenit({ kapcsolo: true, higienia: { kesz: true, ossz: 0, uj: 0 } });
    const reg = await screen.findByRole('region', { name: 'Asszisztens' });
    expect(within(reg).getByText(/Szerdánként általában tanulsz/)).toBeTruthy();
    await fireEvent.click(within(reg).getByRole('button', { name: /Megnyitás: Függvények/ }));
    await waitFor(() => expect(kerelmek.some((k) => k.metodus === 'POST' && k.url === '/api/asszisztens/szokas/dontes')).toBe(true));
    expect(kerelmek.find((k) => k.metodus === 'POST')?.body).toEqual({ azon: JAVASLAT.azon, dontes: 'elfogad' });
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('M01 - Matek/Függvények.md');
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Asszisztens' })).toBeNull());
  });

  it('a javaslat „Nem kell” gombja elutasítás', async () => {
    valaszok['GET /api/asszisztens/szokas'] = () => json({ javaslat: { ...JAVASLAT, legutobbi_ut: null } });
    valaszok['POST /api/asszisztens/szokas/dontes'] = () => json({ ok: true });
    megjelenit({ kapcsolo: true, higienia: null });
    const reg = await screen.findByRole('region', { name: 'Asszisztens' });
    expect(within(reg).queryByRole('button', { name: /Megnyitás/ })).toBeNull();
    await fireEvent.click(within(reg).getByRole('button', { name: 'Nem kell' }));
    await waitFor(() => expect(kerelmek.find((k) => k.metodus === 'POST')?.body).toEqual({ azon: JAVASLAT.azon, dontes: 'elutasit' }));
  });

  it('a core hibája a szakaszban látszik', async () => {
    valaszok['POST /api/asszisztens/higienia/latva'] = () => json({ hiba: 'még nincs kész riport' }, 409);
    megjelenit(SZAKASZ);
    const reg = await screen.findByRole('region', { name: 'Asszisztens' });
    await fireEvent.click(within(reg).getByRole('button', { name: 'Láttam' }));
    expect((await within(reg).findByRole('alert')).textContent).toBe('még nincs kész riport');
  });
});

describe('a teljes Ma oldal', () => {
  const alap = (asszisztens?: MaAsszisztens): MaValasz => ({
    datum: '2026-10-07', felirat: '2026. október 7., szerda', ma: true,
    napi: { ut: 'X01/2026-10-07.md', letezik: false, kivonat: '' },
    dolgozatok: { lista: [], utolso_szinkron: null, regi: false },
    naptar: { esemenyek: [], utolso_szinkron: null, regi: false },
    feladatok: { ma: [], lejart: [], osszes_ma: 0, osszes_lejart: 0 },
    kartyak: { allapot: 'nincs', esedekes: 0 },
    ...(asszisztens ? { asszisztens } : {}),
  });

  async function oldal(v: MaValasz) {
    valaszok['GET /api/ma'] = () => json(v);
    await maAdat.frissit();
    return render(Ma, { context, props: { ful: { id: 'f1', ut: null, nezet: { tipus: 'ma' } }, info: undefined, aktiv: true } });
  }

  it('asszisztens-szakasz nélkül (régebbi core vagy üres): a tanulási áttekintő és az öt napi szakasz látszik', async () => {
    await oldal(alap());
    const fejlecek = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent?.replace(/\s+/g, ' ').trim());
    expect(fejlecek).toEqual(['Tanulás a héten', 'Következő dolgozat / határidő', 'A nap', 'Napi jegyzet', 'Feladatok ma 0', 'Kártyák —']);
  });

  it('új higiénia-tételnél az utolsó szakasz is megjelenik, a végén', async () => {
    await oldal(alap(SZAKASZ));
    await screen.findByRole('region', { name: 'Asszisztens' });
    const fejlecek = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent?.trim());
    expect(fejlecek.at(-1)).toBe('Asszisztens');
    expect(fejlecek).toHaveLength(7);
  });
});
