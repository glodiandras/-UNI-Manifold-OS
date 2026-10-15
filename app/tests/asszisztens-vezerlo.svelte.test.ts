// Az Asszisztens statisztikája a vezérlőben (C30a): a táblázat fajtánként (elfogadva, elutasítva, arány, küszöb), a Tracker
// kikapcsolt állapotának jelzése, a higiénia állása, és az egy gombos, kétlépcsős törlés (megerősítés nélkül nem töröl;
// hibánál a hiba látszik; sikernél értesítés és újratöltött statisztika).

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AsszisztensStatisztika from '../src/hej/vezerlo/AsszisztensStatisztika.svelte';
import { asszisztensMa, asszisztensStatisztika } from '../src/lib/asszisztens/adat.svelte';
import type { HigieniaOsszegzes, Statisztika } from '../src/lib/asszisztens/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

const STAT = (modosit: Partial<Statisztika> = {}): Statisztika => ({
  kapcsolo: { asszisztens: true, tracker: true }, ablak_nap: 30, osszes: { elfogad: 3, elutasit: 12 },
  fajtak: {
    emlites: { elfogad: 1, elutasit: 12, db: 13, arany: 1 / 13, kuszob: { szint: 'szigoru', szorzo: 1.5 } },
    szokas: { elfogad: 2, elutasit: 0, db: 2, arany: 1, kuszob: { szint: 'alap', szorzo: 1 } },
    higienia: { elfogad: 0, elutasit: 0, db: 0, arany: null, kuszob: { szint: 'alap', szorzo: 1 } },
  },
  ...modosit,
});

const HIGIENIA = (m: Partial<HigieniaOsszegzes> = {}): HigieniaOsszegzes => ({
  kapcsolo: true, kesz: true, szamolva: '2026-10-04T21:00:00+02:00', szamol: false, szunetel: false, hiba: null, alapvonal: false,
  osszesites: { ossz: 41 }, ossz: 41, uj: 3, uj_tetelek: [], ...m,
});

let kerelmek: { url: string; metodus: string }[];
let valaszok: Record<string, () => Response>;

beforeEach(() => {
  kerelmek = [];
  valaszok = { 'GET /api/asszisztens/mintak': () => json({ mintak: [] }), 'GET /api/asszisztens/statisztika': () => json(STAT()), 'GET /api/asszisztens/higienia': () => json(HIGIENIA()) };
  asszisztensStatisztika.adat = null;
  asszisztensStatisztika.hiba = null;
  asszisztensMa.osszegzes = null;
  ertesitesek.lista = [];
  ertesitesek.elozmeny = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const metodus = init?.method ?? 'GET';
    kerelmek.push({ url: u.pathname, metodus });
    const f = valaszok[`${metodus} ${u.pathname}`];
    return f ? f() : json({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function megjelenit() {
  const kapcsolat = new CoreKapcsolat('ws://x');
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet: new Felulet({}), fajlok: new VaultFajlok(), kapcsolat }]]);
  return { ...render(AsszisztensStatisztika, { context }), kapcsolat };
}

describe('az Asszisztens statisztikája a vezérlőben', () => {
  it('fajtánként mutatja a darabszámot, az arányt és a küszöböt', async () => {
    megjelenit();
    const sor = await screen.findByRole('row', { name: /Linkjavaslat/ });
    expect(within(sor).getAllByRole('cell').map((c) => c.textContent)).toEqual(['1', '12', '8%', 'szigorúbb (×1,5)']);
    const szokas = screen.getByRole('row', { name: /Szokás-javaslat/ });
    expect(within(szokas).getAllByRole('cell').map((c) => c.textContent)).toEqual(['2', '0', '100%', 'alap']);
    expect(screen.getByText(/utolsó 30 nap/)).toBeTruthy();
    expect(screen.getByText('Csak darabszám, helyben; útvonalat és szöveget nem tárol.')).toBeTruthy();
  });

  it('kikapcsolt Trackernél kimondja, hogy nem gyűlik', async () => {
    valaszok['GET /api/asszisztens/statisztika'] = () => json(STAT({ kapcsolo: { asszisztens: true, tracker: false } }));
    megjelenit();
    expect((await screen.findByRole('status')).textContent).toContain('A Tracker ki van kapcsolva');
  });

  it('a higiénia állása: összes és új tétel, a számolás ideje', async () => {
    megjelenit();
    expect(await screen.findByText(/41 észrevétel, ebből 3 új/)).toBeTruthy();
  });

  it('a számítás szünetelése aktív használat miatt látszik; kikapcsolt Asszisztens és még nincs riport szövege', async () => {
    valaszok['GET /api/asszisztens/higienia'] = () => json(HIGIENIA({ szunetel: true }));
    megjelenit();
    expect((await screen.findAllByRole('status')).some((e) => e.textContent?.includes('aktív használat alatt nem fut'))).toBe(true);
    cleanup();
    valaszok['GET /api/asszisztens/higienia'] = () => json(HIGIENIA({ kapcsolo: false, kesz: false, osszesites: null, ossz: 0, uj: 0 }));
    asszisztensMa.osszegzes = null;
    megjelenit();
    expect(await screen.findByText(/kikapcsolva nem számolódik/)).toBeTruthy();
    cleanup();
    valaszok['GET /api/asszisztens/higienia'] = () => json(HIGIENIA({ kesz: false, osszesites: null, ossz: 0, uj: 0 }));
    asszisztensMa.osszegzes = null;
    megjelenit();
    expect(await screen.findByText(/tétlenségben készül el/)).toBeTruthy();
  });

  it('a törlés kétlépcsős: megerősítés nélkül nem töröl, a Mégse visszavon', async () => {
    megjelenit();
    await fireEvent.click(await screen.findByRole('button', { name: 'Statisztika törlése…' }));
    expect(screen.getByRole('alert').textContent).toContain('Biztosan törlöd');
    expect(kerelmek.some((k) => k.metodus === 'POST')).toBe(false);
    await fireEvent.click(screen.getByRole('button', { name: 'Mégse' }));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(kerelmek.some((k) => k.metodus === 'POST')).toBe(false);
  });

  it('a megerősített törlés a core-nak megy, értesít és újratölt', async () => {
    valaszok['POST /api/asszisztens/statisztika/torles'] = () => json({ torolt: 15, tisztitva: true });
    megjelenit();
    await fireEvent.click(await screen.findByRole('button', { name: 'Statisztika törlése…' }));
    kerelmek.length = 0;
    valaszok['GET /api/asszisztens/statisztika'] = () =>
      json(STAT({ osszes: { elfogad: 0, elutasit: 0 }, fajtak: { emlites: STAT().fajtak.higienia, szokas: STAT().fajtak.higienia, higienia: STAT().fajtak.higienia } }));
    await fireEvent.click(screen.getByRole('button', { name: 'Igen, törlés' }));
    await waitFor(() => expect(kerelmek.map((k) => `${k.metodus} ${k.url}`)).toEqual(['POST /api/asszisztens/statisztika/torles', 'GET /api/asszisztens/statisztika']));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(ertesitesek.lista.some((e) => e.cim === 'Az Asszisztens statisztikája törölve')).toBe(true);
    const sor = screen.getByRole('row', { name: /Linkjavaslat/ });
    expect(within(sor).getAllByRole('cell').map((c) => c.textContent)).toEqual(['0', '0', '—', 'alap']);
  });

  it('a törlés hibája látszik, és a megerősítés nyitva marad', async () => {
    valaszok['POST /api/asszisztens/statisztika/torles'] = () => json({ hiba: 'a statisztika adatbázisa nem írható' }, 503);
    megjelenit();
    await fireEvent.click(await screen.findByRole('button', { name: 'Statisztika törlése…' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Igen, törlés' }));
    await waitFor(() => expect(screen.getAllByRole('alert').some((e) => e.textContent === 'a statisztika adatbázisa nem írható')).toBe(true));
    expect(screen.getByRole('button', { name: 'Igen, törlés' })).toBeTruthy();
  });

  it('az asszisztens_valtozas eseményre újratölt', async () => {
    const { kapcsolat } = megjelenit();
    await screen.findByRole('row', { name: /Linkjavaslat/ });
    kerelmek.length = 0;
    kapcsolat.szetoszt({ tipus: 'asszisztens_valtozas', mi: 'higienia' });
    await waitFor(() => expect(kerelmek.map((k) => k.url)).toContain('/api/asszisztens/statisztika'));
  });
});
