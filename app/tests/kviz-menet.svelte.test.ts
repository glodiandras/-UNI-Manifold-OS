// A kvíz kitöltésének állapotgépe (C22a): betöltés, kérdésenként válasz → ellenőrzés → visszajelzés, a végén a core értékelése,
// a tracker-esemény, a billentyűk, a „hibás kérdés” jelölés, az ismételt kitöltés. Ál-API-val, determinisztikus véletlennel.

import { describe, expect, it, vi } from 'vitest';
import type { KvizApi } from '../src/kviz/api';
import { KvizMenet, keveres } from '../src/kviz/menet.svelte';
import type { Ertekeles, KitoltesValasz, KvizValasz, Megoldas } from '../src/kviz/tipusok';

const UT = 'ATTCHMNTS - quizes/Cím — Kvíz 2026-10-04 2030.md';
const HELYES: Record<string, number> = { k1: 1, k2: 2, k3: 0 };

function kvizAdat(felul: Partial<KvizValasz> = {}): KvizValasz {
  return {
    ok: true,
    ut: UT,
    forras_ut: 'M03/Forrás.md',
    kviz: {
      azon: 'KVIZ-20261004-203015',
      cim: 'Cím',
      forras: 'M03/Forrás',
      modell: 'm',
      keszult: '2026-10-04 2030',
      kerdesek: ['k1', 'k2', 'k3'].map((id, i) => ({
        id,
        kerdes: `Kérdés ${i + 1}?`,
        valaszok: ['a', 'b', 'c', 'd'].map((x) => `${x}${i + 1}`),
        szakasz: i === 0 ? 'Első' : 'Második',
        jelolt: false,
      })),
    },
    token: 'tok-1',
    hibak: [],
    ujra: [],
    megvaltozott: false,
    elozmenyek: [],
    ...felul,
  };
}

function ertekeles(felul: Partial<Ertekeles> = {}): Ertekeles {
  return {
    mod: 'teljes',
    eredmenyek: [],
    osszegzes: { pont: 2, osszes: 3, szazalek: 67, matrix: { tudja: 1, szerencses: 1, tevkepzet: 1, hiany: 0 }, atnezni: [], jelolt: [] },
    szakaszok: [],
    javaslatok: [],
    fo_uzenet: '67 %.',
    onismeret: { biztos: 2, biztos_helyes: 1, tipp: 1, tipp_helyes: 1 },
    trend: null,
    fedetlen_szakaszok: [],
    ujra: ['k2', 'k3'],
    ido_ms: 1000,
    ...felul,
  };
}

interface Hivasok {
  megoldas: [string, string, number | null][];
  /** a `megoldas` hívások tokenje és a küldött tipp */
  megoldasRészlet: { token: string; tipp: boolean }[];
  kitoltes: { token: string; kulcs: string; mod: string; idoMs: number }[];
  jelol: [string, string, boolean][];
}

function almodell(adat: KvizValasz = kvizAdat()) {
  const h: Hivasok = { megoldas: [], megoldasRészlet: [], kitoltes: [], jelol: [] };
  let kitoltesHiba = 0;
  const api: KvizApi = {
    kviz: async () => adat,
    megoldas: async (ut, token, v) => {
      const { kerdes, valasz } = v;
      h.megoldas.push([ut, kerdes, valasz]);
      h.megoldasRészlet.push({ token, tipp: v.tipp });
      const q = adat.kviz.kerdesek.find((x) => x.id === kerdes)!;
      return {
        ok: true,
        kerdes,
        helyes: valasz === HELYES[kerdes],
        helyes_index: HELYES[kerdes],
        helyes_valasz: q.valaszok[HELYES[kerdes]],
        magyarazat: 'mert',
        idezet: `Idézet ${kerdes}`,
        szakasz: q.szakasz,
        horgony: q.szakasz,
        jegyzet: adat.kviz.forras,
        forras_ut: adat.forras_ut,
      } satisfies Megoldas;
    },
    kitoltes: async (_ut, token, kulcs, mod, idoMs) => {
      if (kitoltesHiba > 0) {
        kitoltesHiba--;
        throw new Error('hálózati hiba');
      }
      h.kitoltes.push({ token, kulcs, mod, idoMs });
      return { ok: true, uj: true, ertekeles: ertekeles({ mod }), token: 'tok-2', tracker: { ut: adat.forras_ut, adat: { kviz: adat.kviz.azon, pont: 2 } } } satisfies KitoltesValasz;
    },
    jelol: async (_ut, token, kerdes, hibas) => {
      h.jelol.push([token, kerdes, hibas]);
      return { ok: true, jelolesek: hibas ? [kerdes] : [] };
    },
  };
  return { api, h, hibasKitoltes: (n: number) => (kitoltesHiba = n) };
}

function menet(adat: KvizValasz = kvizAdat(), felul: { api?: KvizApi; tracker?: (ut: string, adat: Record<string, unknown>) => void } = {}) {
  const m = almodell(adat);
  const tracker = felul.tracker ?? vi.fn();
  let ido = 1000;
  let kulcsSzam = 0;
  const k = new KvizMenet(UT, {
    api: felul.api ?? m.api,
    tracker,
    veletlen: () => 0.5,
    most: () => (ido += 100),
    kulcs: () => `k-${++kulcsSzam}-abcdefgh`,
  });
  return { k, ...m, tracker };
}

const pozicio = (k: KvizMenet, tarolt: number) => k.lista[k.i].sorrend.indexOf(tarolt);

describe('keveres', () => {
  it('permutáció, a véletlen magjából determinisztikus', () => {
    const seq = [0.9, 0.1, 0.5];
    let i = 0;
    const p = keveres(4, () => seq[i++ % seq.length]);
    expect([...p].sort()).toEqual([0, 1, 2, 3]);
    i = 0;
    expect(keveres(4, () => seq[i++ % seq.length])).toEqual(p);
    expect(keveres(0, Math.random)).toEqual([]);
  });
});

describe('betöltés', () => {
  it('kezdő állapot a kvízzel; a hiba üzenettel', async () => {
    const { k } = menet();
    expect(k.fazis).toBe('betolt');
    await k.betolt();
    expect(k.fazis).toBe('kezdo');
    expect(k.adat?.kviz.kerdesek).toHaveLength(3);

    const hibas = new KvizMenet(UT, { api: { ...almodell().api, kviz: async () => { throw new Error('nincs ilyen fájl'); } }, tracker: vi.fn() });
    await hibas.betolt();
    expect(hibas.fazis).toBe('hiba');
    expect(hibas.hiba).toBe('nincs ilyen fájl');
  });
});

describe('kitöltés', () => {
  it('a válasz a tárolt sorrend indexével megy, a tipp jelzése a válasz előtt dől el', async () => {
    const { k, h } = menet();
    await k.betolt();
    k.indit();
    expect(k.fazis).toBe('kerdes');
    expect(k.lista).toHaveLength(3);
    for (const q of k.lista) expect([...q.sorrend].sort()).toEqual([0, 1, 2, 3]);
    k.valaszt(pozicio(k, 1));
    expect(k.valasztott).toBe(1);
    await k.ellenoriz(false);
    expect(h.megoldas).toEqual([[UT, 'k1', 1]]);
    expect(k.fazis).toBe('visszajelzes');
    expect(k.megoldas?.helyes).toBe(true);
    expect(k.valaszok).toEqual([{ kerdes: 'k1', valasz: 1, tipp: false, ms: expect.any(Number) }]);
  });

  it('a „nem tudom” válasz nélkül, tippként megy', async () => {
    const { k, h } = menet();
    await k.betolt();
    k.indit();
    await k.nemTudom();
    expect(h.megoldas[0]).toEqual([UT, 'k1', null]);
    expect(k.valaszok[0]).toMatchObject({ valasz: null, tipp: true });
  });

  it('választás nélkül nincs ellenőrzés; a visszajelzés után a válasz nem módosítható', async () => {
    const { k, h } = menet();
    await k.betolt();
    k.indit();
    await k.ellenoriz(false);
    expect(h.megoldas).toHaveLength(0);
    k.valaszt(0);
    await k.ellenoriz(true);
    const elotte = k.valasztott;
    k.valaszt(3);
    expect(k.valasztott).toBe(elotte);
    expect(k.fazis).toBe('visszajelzes');
  });

  it('végigmegy, a core értékel, a tracker-esemény egyszer megy', async () => {
    const { k, h, tracker } = menet();
    await k.betolt();
    k.indit();
    for (const id of ['k1', 'k2', 'k3']) {
      k.valaszt(pozicio(k, HELYES[id]));
      await k.ellenoriz(false);
      await k.kovetkezo();
    }
    expect(k.fazis).toBe('elemzes');
    expect(h.kitoltes).toHaveLength(1);
    expect(h.megoldas.map((x) => x[1])).toEqual(['k1', 'k2', 'k3']);
    expect(h.megoldasRészlet.every((x) => x.token === 'tok-1')).toBe(true);
    expect(h.kitoltes[0].token).toBe('tok-1');
    expect(h.kitoltes[0].mod).toBe('teljes');
    expect(h.kitoltes[0].kulcs).toMatch(/^k-1-/);
    expect(k.ertekeles?.osszegzes.szazalek).toBe(67);
    expect(tracker).toHaveBeenCalledTimes(1);
    expect(tracker).toHaveBeenCalledWith('M03/Forrás.md', { kviz: 'KVIZ-20261004-203015', pont: 2 });
  });

  it('a tipp és a token a megoldás-hívással megy; a kiértékelés után új token jár a következő körhöz', async () => {
    const { k, h } = menet();
    await k.betolt();
    k.indit();
    k.valaszt(0);
    await k.ellenoriz(true);
    expect(h.megoldasRészlet).toEqual([{ token: 'tok-1', tipp: true }]);
    await k.kiertekel();
    k.indit('hibasak');
    k.valaszt(0);
    await k.ellenoriz(false);
    expect(h.megoldasRészlet[1].token).toBe('tok-2');
  });

  it('a hálózati hiba után az újrapróba ugyanazzal a kulccsal megy', async () => {
    const { k, h, hibasKitoltes } = menet();
    await k.betolt();
    k.indit();
    for (let i = 0; i < 3; i++) {
      k.valaszt(0);
      await k.ellenoriz(false);
      hibasKitoltes(i === 2 ? 1 : 0);
      await k.kovetkezo();
    }
    expect(k.fazis).toBe('visszajelzes');
    expect(k.hiba).toBe('hálózati hiba');
    expect(h.kitoltes).toHaveLength(0);
    await k.kiertekel();
    expect(k.fazis).toBe('elemzes');
    expect(k.hiba).toBeNull();
    expect(h.kitoltes).toHaveLength(1);
    expect(h.kitoltes[0].kulcs).toMatch(/^k-1-/);                       // ugyanaz a kulcs, nem új kitöltés
  });

  it('a megoldás-hívás hibája nem viszi tovább a kérdést', async () => {
    const m = almodell();
    const { k } = menet(kvizAdat(), { api: { ...m.api, megoldas: async () => { throw new Error('nem érhető el'); } } });
    await k.betolt();
    k.indit();
    k.valaszt(0);
    await k.ellenoriz(false);
    expect(k.fazis).toBe('kerdes');
    expect(k.hiba).toBe('nem érhető el');
    expect(k.valaszok).toHaveLength(0);
  });
});

describe('kilépés, jelölés, ismétlés', () => {
  it('kilépés válasz nélkül a kezdőlapra; válasz után részleges kiértékelés', async () => {
    const { k, h } = menet();
    await k.betolt();
    k.indit();
    await k.kilep();
    expect(k.fazis).toBe('kezdo');
    k.indit();
    k.valaszt(0);
    await k.ellenoriz(false);
    await k.kilep();
    expect(k.fazis).toBe('elemzes');
    expect(h.megoldas).toHaveLength(1);
  });

  it('a „hibás a kérdés” jelölés be/ki', async () => {
    const { k, h } = menet();
    await k.betolt();
    k.indit();
    k.valaszt(0);
    await k.ellenoriz(false);
    await k.jelol();
    expect(k.lista[0].kerdes.jelolt).toBe(true);
    await k.jelol();
    expect(k.lista[0].kerdes.jelolt).toBe(false);
    expect(h.jelol).toEqual([['tok-1', 'k1', true], ['tok-1', 'k1', false]]);
  });

  it('a hibások és tippeltek újra: az előző értékelés listájából, üresnél a teljes', async () => {
    const { k } = menet();
    await k.betolt();
    k.indit();
    for (let i = 0; i < 3; i++) {
      k.valaszt(0);
      await k.ellenoriz(false);
      await k.kovetkezo();
    }
    k.indit('hibasak');
    expect(k.lista.map((q) => q.kerdes.id)).toEqual(['k2', 'k3']);
    expect(k.mod).toBe('hibasak');
    const ures = menet();
    await ures.k.betolt();
    ures.k.indit('hibasak');
    expect(ures.k.lista).toHaveLength(3);                                // nincs mit újra: a teljes
    expect(ures.k.mod).toBe('teljes');
  });

  it('a betöltéskori „újra” lista az előző kitöltésből jön', async () => {
    const { k } = menet(kvizAdat({ ujra: ['k3'] }));
    await k.betolt();
    k.indit('hibasak');
    expect(k.lista.map((q) => q.kerdes.id)).toEqual(['k3']);
  });
});

describe('billentyűk', () => {
  const lenyom = (k: KvizMenet, key: string, mod: Partial<KeyboardEventInit> = {}) =>
    k.billentyu(new KeyboardEvent('keydown', { key, ...mod }));

  it('1–4 és A–D a megjelenített sorrend szerint választ; Enter biztos, T tipp, N nem tudom', async () => {
    const { k, h } = menet();
    await k.betolt();
    k.indit();
    expect(lenyom(k, '2')).toBe(true);
    expect(k.valasztott).toBe(k.lista[0].sorrend[1]);
    expect(lenyom(k, 'c')).toBe(true);
    expect(k.valasztott).toBe(k.lista[0].sorrend[2]);
    expect(lenyom(k, 'Enter')).toBe(true);
    await vi.waitFor(() => expect(k.fazis).toBe('visszajelzes'));
    expect(k.valaszok[0].tipp).toBe(false);
    expect(lenyom(k, 'Enter')).toBe(true);                               // a visszajelzés után: következő
    await vi.waitFor(() => expect(k.i).toBe(1));
    lenyom(k, 'a');
    lenyom(k, 'T');
    await vi.waitFor(() => expect(k.fazis).toBe('visszajelzes'));
    expect(k.valaszok[1].tipp).toBe(true);
    lenyom(k, 'ArrowRight');
    await vi.waitFor(() => expect(k.i).toBe(2));
    lenyom(k, 'n');
    await vi.waitFor(() => expect(k.fazis).toBe('visszajelzes'));
    expect(k.valaszok[2]).toMatchObject({ valasz: null, tipp: true });
    expect(h.megoldas).toHaveLength(3);
  });

  it('módosítóval, ismeretlen billentyűvel és rossz fázisban nem kezel', async () => {
    const { k } = menet();
    await k.betolt();
    expect(lenyom(k, '1')).toBe(false);                                  // kezdőlapon
    k.indit();
    expect(lenyom(k, '1', { metaKey: true })).toBe(false);
    expect(lenyom(k, '5')).toBe(false);
    expect(lenyom(k, 'x')).toBe(false);
    expect(lenyom(k, 'Enter')).toBe(true);                               // még nincs választás: nem csinál semmit, de a gomb sem lép
    expect(k.fazis).toBe('kerdes');
  });
});
