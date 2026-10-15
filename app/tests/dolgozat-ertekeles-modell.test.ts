// A dolgozat-oldal adata, C28b: a szöveges értékelés kérése (egyszerre egy, hiba esetén az előző megmarad) és az önkalibráció lusta
// betöltése (egyszer tölt; változás-esemény után újra; hiba után újrapróbál).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DolgozatAdat } from '../src/dolgozat/modell.svelte';
import { ertekeles, json, kalibracio, sor } from './dolgozat-fixture';

const ora = new Date(2026, 9, 3, 10, 0, 0);
const modell = () => new DolgozatAdat(() => ora, () => true);
const D1 = sor();

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('szöveges értékelés', () => {
  it('POST-tal megy az azonosítóval, az eredmény az azonosítóhoz kötve marad', async () => {
    const m = modell();
    const kerelmek: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      kerelmek.push({ url, init });
      return json(ertekeles());
    });
    await m.ertekelesKer(D1.azon);
    expect(kerelmek).toHaveLength(1);
    expect(kerelmek[0].url).toBe('/api/felkeszultseg/ertekeles');
    expect(kerelmek[0].init?.method).toBe('POST');
    expect(JSON.parse(String(kerelmek[0].init?.body))).toEqual({ azon: D1.azon });
    expect(m.ertekeles?.azon).toBe(D1.azon);
    expect(m.ertekeles?.szoveg).toContain('62%');
    expect(m.ertekelesFut).toBe(false);
    expect(m.ertekelesHiba).toBeNull();
  });

  it('egyszerre egy értékelés fut', async () => {
    const m = modell();
    let n = 0;
    let kiad: (r: Response) => void = () => {};
    vi.stubGlobal('fetch', async () => {
      n++;
      return new Promise<Response>((r) => (kiad = r));
    });
    const egy = m.ertekelesKer(D1.azon);
    await m.ertekelesKer(D1.azon);
    expect(n).toBe(1);
    expect(m.ertekelesFut).toBe(true);
    kiad(json(ertekeles()));
    await egy;
    expect(m.ertekelesFut).toBe(false);
  });

  it('a hiba a mezőbe kerül, az előző értékelés megmarad', async () => {
    const m = modell();
    vi.stubGlobal('fetch', async () => json(ertekeles()));
    await m.ertekelesKer(D1.azon);
    vi.stubGlobal('fetch', async () => json({ hiba: 'nincs kalibrált modell' }, 503));
    await m.ertekelesKer(D1.azon);
    expect(m.ertekelesHiba).toBe('nincs kalibrált modell');
    expect(m.ertekeles?.szoveg).toContain('62%');
    expect(m.ertekelesFut).toBe(false);
  });
});

describe('önkalibráció', () => {
  it('egyszer tölt, utána csak változás-esemény után újra', async () => {
    const m = modell();
    let n = 0;
    vi.stubGlobal('fetch', async () => {
      n++;
      return json(kalibracio({ pontok: n }));
    });
    await m.kalibracioBetolt();
    await m.kalibracioBetolt();
    expect(n).toBe(1);
    expect(m.kalibracio?.allapot).toBe('nem_teljesitheto');
    m.utemez();
    await m.kalibracioBetolt();
    expect(n).toBe(2);
    expect(m.kalibracio?.pontok).toBe(2);
  });

  it('a hiba mezőbe kerül, és a következő kérés újrapróbál', async () => {
    const m = modell();
    vi.stubGlobal('fetch', async () => json({ hiba: 'az index még épül' }, 503));
    await m.kalibracioBetolt();
    expect(m.kalibracioHiba).toBe('az index még épül');
    expect(m.kalibracio).toBeNull();
    vi.stubGlobal('fetch', async () => json(kalibracio()));
    await m.kalibracioBetolt();
    expect(m.kalibracio?.kell).toBe(8);
    expect(m.kalibracioHiba).toBeNull();
  });
});
