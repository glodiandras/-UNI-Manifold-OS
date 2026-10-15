import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Ertesitesek, MAX_LATHATO } from '../src/lib/ertesites/ertesites.svelte';
import { Mento } from '../src/lib/elrendezes/felulet.svelte';

describe('értesítések', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('időzítés: 5 s után eltűnik, a hiba 10 s-ig marad', () => {
    const e = new Ertesitesek();
    e.ertesit({ cim: 'Kész' });
    e.ertesit({ szint: 'hiba', cim: 'Hiba' });
    vi.advanceTimersByTime(5001);
    expect(e.lista.map((x) => x.cim)).toEqual(['Hiba']);
    vi.advanceTimersByTime(5000);
    expect(e.lista).toEqual([]);
    expect(e.elozmeny.map((x) => x.cim)).toEqual(['Hiba', 'Kész']); // az előzmény megmarad
  });

  it('legfeljebb 3 látszik; az azonos értesítés összevonódik', () => {
    const e = new Ertesitesek();
    for (let i = 0; i < 5; i++) e.ertesit({ cim: `É${i}` });
    expect(e.lathato).toHaveLength(MAX_LATHATO);
    expect(e.lathato[0].cim).toBe('É2');
    e.ertesit({ cim: 'É4' });
    expect(e.lista.filter((x) => x.cim === 'É4')[0].darab).toBe(2);
    expect(e.olvasatlan).toBe(5);
    e.olvasva();
    expect(e.olvasatlan).toBe(0);
  });

  it('a tartós értesítés (mentési hiba) nem szorul ki a látszók közül; a legújabb múló mellette látszik', () => {
    const e = new Ertesitesek();
    e.ertesit({ szint: 'hiba', cim: 'A mentés nem sikerült', idotartam: 0 });
    for (let i = 0; i < 5; i++) e.ertesit({ cim: `É${i}` });
    expect(e.lathato.map((x) => x.cim)).toEqual(['A mentés nem sikerült', 'É3', 'É4']);
    e.ertesit({ szint: 'figyelmeztetes', cim: 'A vault nem érhető el', idotartam: 0 });
    e.ertesit({ szint: 'hiba', cim: 'Harmadik tartós', idotartam: 0 });
    e.ertesit({ cim: 'É5' });
    expect(e.lathato.map((x) => x.cim)).toEqual(['A mentés nem sikerült', 'A vault nem érhető el', 'Harmadik tartós', 'É5']);
  });

  it('hover alatt az időzítő áll, utána a maradékkal folytatódik', () => {
    const e = new Ertesitesek();
    const id = e.ertesit({ cim: 'Szünet', idotartam: 4000 });
    vi.advanceTimersByTime(1000);
    e.szunet(id, true);
    vi.advanceTimersByTime(60000);
    expect(e.lista).toHaveLength(1);
    e.szunet(id, false);
    vi.advanceTimersByTime(2999);
    expect(e.lista).toHaveLength(1);
    vi.advanceTimersByTime(2);
    expect(e.lista).toHaveLength(0);
  });

  it('0 időtartam: amíg be nem zárják; a művelet nem tűnik el 5 s után', () => {
    const e = new Ertesitesek();
    const id = e.ertesit({ cim: 'Marad', idotartam: 0 });
    e.ertesit({ cim: 'Visszavonás?', muvelet: { nev: 'Visszavonás', futtat: () => {} } });
    vi.advanceTimersByTime(9000);
    expect(e.lista.map((x) => x.cim)).toEqual(['Marad', 'Visszavonás?']);
    e.elvet(id);
    expect(e.lista.map((x) => x.cim)).toEqual(['Visszavonás?']);
  });
});

describe('felület-állapot mentése', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('késleltetve, összevonva ment; változatlan állapotot nem küld', () => {
    const kuld = vi.fn(() => Promise.resolve());
    const m = new Mento(kuld, 500);
    m.alap('{"a":1}');
    m.utemez('{"a":1}');
    vi.advanceTimersByTime(1000);
    expect(kuld).not.toHaveBeenCalled();
    m.utemez('{"a":2}');
    vi.advanceTimersByTime(300);
    m.utemez('{"a":3}');
    vi.advanceTimersByTime(500);
    expect(kuld).toHaveBeenCalledExactlyOnceWith('{"a":3}', false);
  });

  it('a lap elhagyásakor azonnal, keepalive-val', () => {
    const kuld = vi.fn(() => Promise.resolve());
    const m = new Mento(kuld, 500);
    m.utemez('{"b":1}');
    m.ki(true);
    expect(kuld).toHaveBeenCalledExactlyOnceWith('{"b":1}', true);
    m.ki(true);
    expect(kuld).toHaveBeenCalledOnce();
  });
});

describe('mentés kilépéskor', () => {
  it('a ki() Promise-a a küldés végén teljesül; hibánál a következő mentés újraküld', async () => {
    let kesz: () => void = () => {};
    const kuld = vi.fn(() => new Promise<void>((r) => (kesz = r)));
    const m = new Mento(kuld, 500);
    m.utemez('{"t":"rendszer"}');
    let vege = false;
    const p = m.ki(true).then(() => (vege = true));
    await Promise.resolve();
    expect(vege).toBe(false);
    kesz();
    await p;
    expect(vege).toBe(true);
    const hibas = new Mento(() => Promise.reject(new Error('nincs core')), 500);
    hibas.utemez('{"a":1}');
    await hibas.ki(true);
    const kuld2 = vi.fn(() => Promise.resolve());
    (hibas as unknown as { kuld: typeof kuld2 }).kuld = kuld2;
    hibas.utemez('{"a":1}');
    await hibas.ki(true);
    expect(kuld2).toHaveBeenCalledOnce();
  });
});
