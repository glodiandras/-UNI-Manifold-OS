// A Bases-kérések azonosítása (C29.8, T040): a `BazisModell` minden lekérdezéshez sorszámot (`kerdes`) és állandó nézet-azonosítót
// (`azon`) küld, hogy a core az újabb kéréssel leállíthassa a régebbit (az elavult válaszból a kliens eddig is eldobta a
// régit, de a szerver tovább számolt).

import { describe, expect, it } from 'vitest';
import type { BazisApi } from '../src/bazis/api';
import { rogzitettForras } from '../src/bazis/forras';
import { BazisModell } from '../src/bazis/modell.svelte';
import type { LekerdezOpciok, Valasz } from '../src/bazis/tipusok';

function valasz(): Valasz {
  return {
    ok: true,
    nezetek: [{ nev: 'Táblázat', tipus: 'table', ismert: true }],
    nezet: { index: 0, nev: 'Táblázat', tipus: 'table', eredeti_tipus: 'table', beallitas: {} },
    oszlopok: [],
    sorok: [],
    csoportok: null,
    osszesitok: {},
    fajl: { szuro: '', szuro_nezet: '', kepletek: {}, osszesitok: [], elerheto: [] },
    osszes: 0,
    levagva: false,
    hibak: [],
    figyelmeztetesek: [],
    ido_ms: 1,
    generacio: 1,
  };
}

function alApi(kert: LekerdezOpciok[]): BazisApi {
  return {
    lekerdez: async (_szoveg, o) => {
      kert.push(o ?? {});
      return valasz();
    },
    modosit: async () => ({ ok: true, szoveg_uj: '', valtozas: '', hibak: [] }),
  };
}

describe('Bases-kérés azonosítók (T040)', () => {
  it('minden kérés növekvő sorszámot és ugyanazt a nézet-azonosítót viszi', async () => {
    const kert: LekerdezOpciok[] = [];
    const m = new BazisModell(rogzitettForras('views: []\n', 'Jegyzet.md'), { api: alApi(kert) });
    await m.frissit();
    await m.frissit();
    await m.frissit();
    expect(kert).toHaveLength(3);
    expect(kert.map((o) => o.kerdes)).toEqual([1, 2, 3]);
    expect(new Set(kert.map((o) => o.azon)).size).toBe(1);
    expect(kert[0].azon).toMatch(/^bm-[a-z0-9]{4,}$/);
    m.lebont();
  });

  it('két modell azonosítója különbözik: az egyik nézet kérése nem állítja le a másikét', async () => {
    const a: LekerdezOpciok[] = [];
    const b: LekerdezOpciok[] = [];
    const m1 = new BazisModell(rogzitettForras('', 'A.md'), { api: alApi(a) });
    const m2 = new BazisModell(rogzitettForras('', 'B.md'), { api: alApi(b) });
    await m1.frissit();
    await m2.frissit();
    expect(a[0].azon).not.toBe(b[0].azon);
    m1.lebont();
    m2.lebont();
  });
});
