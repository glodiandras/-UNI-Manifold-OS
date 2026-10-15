// F2 (2026-10-14): a foglalt kör-zár (409 `foglalt`) után a darab újraküldődik; más hiba nem.
import { describe, expect, it, vi } from 'vitest';

const valaszok: Array<() => unknown> = [];
const torzsek: unknown[] = [];
vi.mock('../src/lib/core/api', async () => {
  const valodi = await vi.importActual<typeof import('../src/lib/core/api')>('../src/lib/core/api');
  return {
    ApiHiba: valodi.ApiHiba,
    kerdez: vi.fn(async (_ut: string, o: { torzs: unknown }) => {
      torzsek.push(o.torzs);
      const k = valaszok.shift();
      if (!k) throw new Error('nincs több válasz');
      return k();
    }),
  };
});
vi.mock('../src/lib/vault/linkek.svelte', () => ({ linkek: { linkCel: async (u: string) => u } }));
vi.mock('../src/lib/ertesites/ertesites.svelte', () => ({ ertesitesek: { ertesit: vi.fn() } }));

import { ApiHiba } from '../src/lib/core/api';
import { FOGLALT_UJRA, fajlImport } from '../src/szerkeszto/csatolmany';

describe('fájlimport foglalt kör-zárnál', () => {
  it('a foglalt választ újrapróbálja ugyanazzal a darabbal', async () => {
    FOGLALT_UJRA.varakozasMs = 1;
    torzsek.length = 0;
    valaszok.push(
      () => { throw new ApiHiba(409, 'foglalt', { foglalt: true }); },
      () => ({ azon: 'a'.repeat(32), ut: 'Média/kep.png', kesz: true }),
    );
    const fajl = new File([new Uint8Array([1, 2, 3])], 'kep.png');
    await expect(fajlImport(fajl, { mappa: 'Média' })).resolves.toBe('Média/kep.png');
    expect(torzsek).toHaveLength(2);
    expect(torzsek[1]).toEqual(torzsek[0]);
  });

  it('a sorrend-hibát és a többi hibát nem próbálja újra', async () => {
    torzsek.length = 0;
    valaszok.length = 0;
    valaszok.push(() => { throw new ApiHiba(409, 'A feltöltési darabok sorrendje eltér.', { offset: 0 }); });
    await expect(fajlImport(new File([new Uint8Array([1])], 'x.png'), {})).rejects.toThrow('sorrendje');
    expect(torzsek).toHaveLength(1);
  });
});
