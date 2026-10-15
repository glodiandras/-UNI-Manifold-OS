// A kártyák ismétlése (C23b): a menet (fordítás, értékelés, „Újra” a menet végére, ⌘Z visszavonás, billentyűk, tracker), az
// intervallum-felirat és a kártyamappa tükre.

import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { intervallum, KARTYA_MAPPA, kartyaUt } from '../src/kartya/allando';
import type { Kartya, KartyaApi } from '../src/kartya/api';
import { IsmetlesMenet } from '../src/kartya/menet.svelte';

const kartya = (azon: string, uj = true): Kartya => ({
  azon, jegyzet: `${KARTYA_MAPPA}/A — kártyák.md`, kerdes: `K ${azon}?`, valasz: `V ${azon}`, forras: 'A#^m-1a2b',
  allapot: uj ? 0 : 2, uj, esedekes: null, sor: 1, esedekes_most: true, elorejelzes: { 1: 60, 2: 360, 3: 600, 4: 86400 * 4 },
});

function alApi(kartyak: Kartya[]) {
  const hivasok: string[] = [];
  const api: KartyaApi = {
    esedekes: async () => ({ ok: true, kartyak, allapot: 'kesz', esedekes: 1, uj: kartyak.length - 1, osszes: 5 }),
    jegyzet: async (ut) => ({ ok: true, ut, kartyak, esedekes: 0, uj: kartyak.length, osszes: kartyak.length, hibak: [] }),
    valasz: async (azon, jegy, ms) => {
      hivasok.push(`valasz ${azon} ${jegy} ${ms}`);
      return { ok: true, allapot: {}, tracker: { ut: 'A.md', adat: { jegy, kartya_id: azon, ms: ms ?? undefined } } };
    },
    visszavon: async (azon) => {
      hivasok.push(`visszavon ${azon}`);
      return { ok: true, visszavonva: true };
    },
    allapot: async () => ({ allapot: 'kesz', esedekes: 0, uj: 0 }),
    general: async () => ({}) as never,
  };
  return { api, hivasok };
}

const bill = (key: string, mod: Partial<KeyboardEvent> = {}) => ({ key, metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...mod }) as KeyboardEvent;

describe('IsmetlesMenet', () => {
  it('fordítás, értékelés a mért idővel, tracker, a végén kész', async () => {
    const { api, hivasok } = alApi([kartya('c-1'), kartya('c-2')]);
    let ido = 1000;
    const tracker = vi.fn();
    const m = new IsmetlesMenet({ tipus: 'pakli', ut: 'x.md' }, { api, tracker, most: () => ido });
    await m.betolt();
    expect(m.fazis).toBe('kerdes');
    expect(m.billentyu(bill('3'))).toBe(false);          // a kérdés oldalán az 1–4 nem értékel
    ido = 4200;
    expect(m.billentyu(bill(' '))).toBe(true);
    expect(m.fazis).toBe('valasz');
    await m.ertekel(3);
    expect(hivasok).toEqual(['valasz c-1 3 3200']);
    expect(tracker).toHaveBeenCalledWith('A.md', { jegy: 3, kartya_id: 'c-1', ms: 3200 });
    m.fordit();
    await m.ertekel(4);
    expect(m.fazis).toBe('kesz');
    expect(m.kesz).toBe(2);
  });

  it('az „Újra” kártya a menet végén még egyszer jön; a ⌘Z visszavon és kiveszi a másolatot', async () => {
    const { api, hivasok } = alApi([kartya('c-1'), kartya('c-2')]);
    const m = new IsmetlesMenet({ tipus: 'mai' }, { api });
    await m.betolt();
    m.fordit();
    await m.ertekel(1);
    expect(m.lista.map((k) => k.azon)).toEqual(['c-1', 'c-2', 'c-1']);
    expect(m.lista[2].elorejelzes).toBeNull();
    expect(m.billentyu(bill('z', { metaKey: true }))).toBe(true);
    await vi.waitFor(() => expect(hivasok).toContain('visszavon c-1'));
    await vi.waitFor(() => expect(m.lista.map((k) => k.azon)).toEqual(['c-1', 'c-2']));
    expect(m.fazis).toBe('kerdes');
    expect(m.i).toBe(0);
    expect(m.kesz).toBe(0);
  });

  it('üres pakli: „ma nincs esedékes”; a ⌘Z értékelés nélkül nem nyeli el a szerkesztő visszavonását', async () => {
    const { api } = alApi([]);
    const m = new IsmetlesMenet({ tipus: 'pakli', ut: 'x.md' }, { api });
    await m.betolt();
    expect(m.fazis).toBe('ures');
    expect(m.billentyu(bill('z', { metaKey: true }))).toBe(false);
  });

  it('hiba a betöltéskor', async () => {
    const { api } = alApi([]);
    api.jegyzet = async () => {
      throw new Error('nincs core');
    };
    const m = new IsmetlesMenet({ tipus: 'pakli', ut: 'x.md' }, { api });
    await m.betolt();
    expect(m.fazis).toBe('hiba');
    expect(m.hiba).toBe('nincs core');
  });
});

describe('allando', () => {
  it('az intervallum rövid felirata', () => {
    expect(intervallum(45)).toBe('45 mp');
    expect(intervallum(600)).toBe('10 p');
    expect(intervallum(7200)).toBe('2 ó');
    expect(intervallum(86400 * 4)).toBe('4 n');
    expect(intervallum(86400 * 60)).toBe('2 hó');
    expect(intervallum(86400 * 548)).toBe('1,5 év');
    expect(intervallum(null)).toBe('');
  });

  it('a kártyamappa a core [kartya] mappa tükre', () => {
    const toml = new TextDecoder().decode(readFileSync(decodeURIComponent(new URL('../../config/os.toml', import.meta.url).pathname).replace(/^\/@fs/, '')));
    const m = /^\[kartya\][\s\S]*?^mappa = "([^"]+)"/m.exec(toml);
    expect(m?.[1]).toBe(KARTYA_MAPPA);
    expect(kartyaUt(`${KARTYA_MAPPA}/A — kártyák.md`)).toBe(true);
    expect(kartyaUt('M/A.md')).toBe(false);
  });
});
