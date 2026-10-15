// A dolgozat-oldal adatának élete (C28a): betöltés megjelenéskor (lista, majd a kiválasztott dolgozat részlete), a
// kiválasztás váltása, WS-re összevont frissítés csak látszó nézetnek, elavult válasz eldobása, a core hibái.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DolgozatAdat, alapertelmezett } from '../src/dolgozat/modell.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { json, lista, reszlet, sor } from './dolgozat-fixture';

let hivasok: string[];
let valasz: (url: string) => Promise<Response> | Response;
let lathato: boolean;
const ora = new Date(2026, 9, 3, 10, 0, 0);

const modell = () => new DolgozatAdat(() => ora, () => lathato);
const D1 = sor();
const D2 = sor({ azon: 'd2|x', cim: 'Fizika dolgozat', nap: '2026-10-09', napok: 6 });

beforeEach(() => {
  hivasok = [];
  lathato = true;
  valasz = (url) => (url.includes('/dolgozat?') ? json(reszlet({ azon: decodeURIComponent(url.split('azon=')[1]) })) : json(lista([D1, D2])));
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  vi.stubGlobal('fetch', async (url: string) => {
    hivasok.push(url);
    return valasz(url);
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('alapértelmezett dolgozat', () => {
  it('az első még le nem zárt, különben az első', () => {
    expect(alapertelmezett([sor({ azon: 'a', lezart: true }), sor({ azon: 'b' })])).toBe('b');
    expect(alapertelmezett([sor({ azon: 'a', lezart: true })])).toBe('a');
    expect(alapertelmezett([])).toBeNull();
  });
});

describe('betöltés', () => {
  it('a megjelenéskor a listát, majd az alapértelmezett dolgozat részletét tölti', async () => {
    const m = modell();
    m.megjelenik();
    await vi.waitFor(() => expect(m.reszlet).not.toBeNull());
    expect(hivasok).toEqual(['/api/felkeszultseg', `/api/felkeszultseg/dolgozat?azon=${encodeURIComponent(D1.azon)}`]);
    expect(m.valasztott).toBe(D1.azon);
    expect(m.lista?.dolgozatok).toHaveLength(2);
  });

  it('a kiválasztás váltása csak a részletet tölti újra', async () => {
    const m = modell();
    await m.frissit();
    hivasok.length = 0;
    await m.valaszt(D2.azon);
    expect(hivasok).toEqual([`/api/felkeszultseg/dolgozat?azon=${encodeURIComponent(D2.azon)}`]);
    expect(m.reszlet?.azon).toBe(D2.azon);
  });

  it('a megszűnt kiválasztott dolgozat helyett az alapértelmezettet választja', async () => {
    const m = modell();
    m.valasztott = 'nincs-mar';
    await m.frissit();
    expect(m.valasztott).toBe(D1.azon);
  });

  it('dolgozat nélkül nincs részlet-kérés', async () => {
    valasz = () => json(lista([], { hiba: 'nincs naptáradat' }));
    const m = modell();
    await m.frissit();
    expect(hivasok).toEqual(['/api/felkeszultseg']);
    expect(m.reszlet).toBeNull();
    expect(m.lista?.hiba).toBe('nincs naptáradat');
  });

  it('a lista hibája a `hiba` mezőbe kerül', async () => {
    valasz = () => json({ hiba: 'az index még épül' }, 503);
    const m = modell();
    await m.frissit();
    expect(m.hiba).toBe('az index még épül');
    expect(m.lista).toBeNull();
    expect(m.betoltve).toBe(true);
  });

  it('a részlet hibája (404) külön mezőbe kerül, a lista megmarad', async () => {
    valasz = (url) => (url.includes('/dolgozat?') ? json({ hiba: 'nincs ilyen dolgozat' }, 404) : json(lista([D1])));
    const m = modell();
    await m.frissit();
    expect(m.reszletHiba).toBe('nincs ilyen dolgozat');
    expect(m.reszlet).toBeNull();
    expect(m.lista?.dolgozatok).toHaveLength(1);
  });

  it('az elavult válasz nem írja felül az újabbat', async () => {
    let kiad: (r: Response) => void = () => {};
    let n = 0;
    valasz = (url) => {
      if (url.includes('/dolgozat?')) return json(reszlet({ azon: D1.azon, cim: `részlet ${n}` }));
      return ++n === 1 ? new Promise<Response>((r) => (kiad = r)) : json(lista([D1], { nap: 'friss' }));
    };
    const m = modell();
    const lassu = m.frissit();
    await m.frissit();
    expect(m.lista?.nap).toBe('friss');
    kiad(json(lista([D1], { nap: 'régi' })));
    await lassu;
    expect(m.lista?.nap).toBe('friss');
  });
});

describe('változás-események', () => {
  it('látszó nézetnek az események egy frissítésbe vonódnak össze', async () => {
    const m = modell();
    const k = new CoreKapcsolat('ws://x');
    const le = m.figyel(k);
    m.megjelenik();
    await vi.waitFor(() => expect(m.betoltve).toBe(true));
    hivasok.length = 0;
    k.szetoszt({ tipus: 'vault_valtozas' });
    k.szetoszt({ tipus: 'naptar_javaslat' });
    k.szetoszt({ tipus: 'index' });
    await vi.advanceTimersByTimeAsync(1000);
    expect(hivasok.filter((u) => u === '/api/felkeszultseg')).toHaveLength(1);
    le();
  });

  it('látszó nézet nélkül nem ütemez, csak elavultnak jelöl; a következő megjelenéskor tölt', async () => {
    const m = modell();
    const k = new CoreKapcsolat('ws://x');
    const le = m.figyel(k);
    await m.frissit();
    hivasok.length = 0;
    k.szetoszt({ tipus: 'vault_valtozas' });
    await vi.advanceTimersByTimeAsync(2000);
    expect(hivasok).toEqual([]);
    m.megjelenik();
    await vi.waitFor(() => expect(hivasok).toContain('/api/felkeszultseg'));
    le();
  });

  it('rejtett lapon nem tölt', async () => {
    const m = modell();
    const k = new CoreKapcsolat('ws://x');
    const le = m.figyel(k);
    m.megjelenik();
    await vi.waitFor(() => expect(m.betoltve).toBe(true));
    hivasok.length = 0;
    lathato = false;
    k.szetoszt({ tipus: 'index' });
    await vi.advanceTimersByTimeAsync(2000);
    expect(hivasok).toEqual([]);
    le();
  });
});
