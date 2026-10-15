// A „Ma” oldal adatának élete (C15): betöltés megjelenéskor, WS-re összevont frissítés csak látszó nézetnek, éjféli
// átfordulás, elavult válasz eldobása, a nyugalom (nincs időzítő látszó nézet nélkül), a core hibája.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { MaAdat } from '../src/ma/modell.svelte';
import type { MaValasz } from '../src/ma/tipusok';

function valasz(felirat: string): MaValasz {
  return {
    datum: '2026-10-02',
    felirat,
    ma: true,
    napi: { ut: 'X/2026-10-02.md', letezik: false, kivonat: '' },
    dolgozatok: { lista: [], utolso_szinkron: null, regi: false },
    naptar: { esemenyek: [], utolso_szinkron: null, regi: false },
    feladatok: { ma: [], lejart: [], osszes_ma: 0, osszes_lejart: 0 },
    kartyak: { allapot: 'nincs', esedekes: 0 },
  };
}

let hivasok: number;
let adj: (n: number) => Promise<Response> | Response;
let ora: Date;
let lathato: boolean;

const kesz = (n: number) => new Response(JSON.stringify(valasz(`válasz ${n}`)), { status: 200, headers: { 'Content-Type': 'application/json' } });
const modell = () => new MaAdat(() => ora, () => lathato);

beforeEach(() => {
  hivasok = 0;
  adj = kesz;
  ora = new Date(2026, 9, 2, 10, 0, 0);
  lathato = true;
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  vi.stubGlobal('fetch', async () => adj(++hivasok));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('betöltés', () => {
  it('a megjelenéskor tölt egyszer; a friss adatnál az újabb megjelenés nem', async () => {
    const m = modell();
    const le = m.megjelenik();
    await vi.waitFor(() => expect(m.betoltve).toBe(true));
    expect(hivasok).toBe(1);
    expect(m.adat?.felirat).toBe('válasz 1');
    le();
    m.megjelenik()();
    await Promise.resolve();
    expect(hivasok).toBe(1);
  });

  it('a core hibája a `hiba` mezőbe kerül, az adat marad üres', async () => {
    adj = () => new Response(JSON.stringify({ hiba: 'az index még épül' }), { status: 503, headers: { 'Content-Type': 'application/json' } });
    const m = modell();
    m.megjelenik();
    await vi.waitFor(() => expect(m.betoltve).toBe(true));
    expect(m.adat).toBeNull();
    expect(m.hiba).toBe('az index még épül');
  });

  it('az elavult válasz nem írja felül az újabbat', async () => {
    let kiad: (r: Response) => void = () => {};
    adj = (n) => (n === 1 ? new Promise<Response>((r) => (kiad = r)) : kesz(n));
    const m = modell();
    const lassu = m.frissit();
    await m.frissit();
    expect(m.adat?.felirat).toBe('válasz 2');
    kiad(kesz(1));
    await lassu;
    expect(m.adat?.felirat).toBe('válasz 2');
  });
});

describe('változás-események', () => {
  it('látszó nézetnek az események egy frissítésbe vonódnak össze', async () => {
    const m = modell();
    const k = new CoreKapcsolat('ws://x');
    const le = m.figyel(k);
    m.megjelenik();
    await vi.waitFor(() => expect(hivasok).toBe(1));
    for (let i = 0; i < 5; i++) k.szetoszt({ tipus: 'vault_valtozas' });
    k.szetoszt({ tipus: 'vault_iras' });
    expect(hivasok).toBe(1);
    await vi.advanceTimersByTimeAsync(900);
    expect(hivasok).toBe(2);
    le();
  });

  it('látszó nézet nélkül nincs hálózat és nincs időzítő, a következő megjelenés tölt', async () => {
    const m = modell();
    const k = new CoreKapcsolat('ws://x');
    const le = m.figyel(k);
    await m.frissit();
    expect(hivasok).toBe(1);
    k.szetoszt({ tipus: 'vault_valtozas' });
    k.szetoszt({ tipus: 'index' });
    expect(vi.getTimerCount()).toBe(0);
    expect(hivasok).toBe(1);
    const elrejt = m.megjelenik();
    await vi.waitFor(() => expect(m.adat?.felirat).toBe('válasz 2'));
    elrejt();
    expect(vi.getTimerCount()).toBe(0);
    le();
  });

  it('rejtett lapon az esemény csak elavultnak jelöl; a láthatóvá válás tölt', async () => {
    const m = modell();
    const k = new CoreKapcsolat('ws://x');
    const le = m.figyel(k);
    m.megjelenik();
    await vi.waitFor(() => expect(m.betoltve).toBe(true));
    lathato = false;
    k.szetoszt({ tipus: 'vault_valtozas' });
    await vi.advanceTimersByTimeAsync(2000);
    expect(hivasok).toBe(1);
    lathato = true;
    m.lathatovaValt();
    await vi.waitFor(() => expect(hivasok).toBe(2));
    le();
  });
});

describe('töltés közbeni változás', () => {
  it('a töltés közben érkező esemény nem vész el: a válasz után a nézet még elavult, és újratölt', async () => {
    let kiad: (r: Response) => void = () => {};
    adj = (n) => (n === 1 ? new Promise<Response>((r) => (kiad = r)) : kesz(n));
    const m = modell();
    const k = new CoreKapcsolat('ws://x');
    const le = m.figyel(k);
    m.megjelenik();
    await vi.waitFor(() => expect(hivasok).toBe(1));
    k.szetoszt({ tipus: 'vault_iras' }); // a válasz előtt
    kiad(kesz(1));
    await vi.advanceTimersByTimeAsync(600);
    expect(hivasok).toBe(2);
    expect(m.adat?.felirat).toBe('válasz 2');
    le();
  });
});

describe('éjfél', () => {
  it('éjfélkor újratölt, és újra ütemez a következő éjfélre', async () => {
    ora = new Date(2026, 9, 2, 23, 59, 30);
    const m = modell();
    const le = m.megjelenik();
    await vi.waitFor(() => expect(hivasok).toBe(1));
    ora = new Date(2026, 9, 3, 0, 0, 1);
    await vi.advanceTimersByTimeAsync(31_000);
    expect(hivasok).toBe(2);
    expect(vi.getTimerCount()).toBe(1); // a következő éjfél
    le();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('a nap átfordulása után a következő megjelenés tölt, akkor is, ha az adat friss volt', async () => {
    const m = modell();
    m.megjelenik()();
    await vi.waitFor(() => expect(hivasok).toBe(1));
    ora = new Date(2026, 9, 3, 8, 0, 0);
    m.megjelenik();
    await vi.waitFor(() => expect(hivasok).toBe(2));
  });
});
