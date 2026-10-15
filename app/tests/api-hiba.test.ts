// A core-kérés hibái (javítókör D, 8., 12., 13. lelet): a nem JSON hibaválasz státusza megmarad, a nyers hálózati hiba és a
// státusz magyarul, alap időkorlát.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChangeSet, Text } from '@codemirror/state';
import { ALAP_IDOKORLAT, ApiHiba, KAPCSOLAT_HIBA, hibaSzoveg, kerdez, kerdezEtag } from '../src/lib/core/api';
import { vaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';

const HTML_413 = '<!DOCTYPE HTML><html><head><title>Error response</title></head><body><h1>Error response</h1><p>Error code: 413</p></body></html>';

async function hiba(p: Promise<unknown>): Promise<ApiHiba> {
  try {
    await p;
  } catch (e) {
    return e as ApiHiba;
  }
  throw new Error('nem dobott');
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('a core hibaválaszai', () => {
  it('a nem JSON (HTML) hibaválasz: a státusz megmarad, magyar üzenettel', async () => {
    vi.stubGlobal('fetch', async () => new Response(HTML_413, { status: 413, statusText: 'Request Entity Too Large' }));
    const e = await hiba(kerdez('/api/vault/fajl', { metodus: 'PUT', torzs: {} }));
    expect(e).toBeInstanceOf(ApiHiba);
    expect(e.statusz).toBe(413);
    expect(e.message).toBe('A kérés túl nagy (413).');
    vi.stubGlobal('fetch', async () => new Response('<html>500</html>', { status: 500 }));
    expect((await hiba(kerdezEtag('/api/vault/graf', null))).statusz).toBe(500);
  });

  it('a core magyar hibaüzenete elsőbbséget kap; a hiányzó a státusz magyar szövege', async () => {
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ hiba: 'a kör-zár foglalt' }), { status: 423 }));
    expect((await hiba(kerdez('/x'))).message).toBe('a kör-zár foglalt');
    vi.stubGlobal('fetch', async () => new Response('{}', { status: 418, statusText: "I'm a teapot" }));
    expect((await hiba(kerdez('/x'))).message).toBe('A core hibát adott (418).');
  });

  it('a sikeres, de nem JSON válasz értelmezhetetlen (nem nyers SyntaxError)', async () => {
    vi.stubGlobal('fetch', async () => new Response('<html>', { status: 200 }));
    const e = await hiba(kerdez('/x'));
    expect(e.message).toBe('A core válasza nem értelmezhető.');
  });

  it('a nyers WebKit-hálózati hiba magyarul', async () => {
    for (const nyers of ['Load failed', 'The network connection was lost.', 'Failed to fetch', 'Could not connect to the server.']) {
      vi.stubGlobal('fetch', async () => {
        throw new TypeError(nyers);
      });
      const e = await hiba(kerdez('/x'));
      expect(e.statusz).toBe(0);
      expect(e.message).toBe(KAPCSOLAT_HIBA);
    }
  });

  it('a hibaSzoveg: az ApiHiba üzenete előtag nélkül, a nyers hálózati hiba magyarul', () => {
    expect(String(new ApiHiba(500, 'baj'))).toBe('ApiHiba: baj'); // ezért nem String(e)
    expect(hibaSzoveg(new ApiHiba(500, 'baj'))).toBe('baj');
    expect(hibaSzoveg(new TypeError('Load failed'))).toBe(KAPCSOLAT_HIBA);
    expect(hibaSzoveg('valami')).toBe('valami');
  });
});

describe('alap időkorlát', () => {
  it('a megadott korlát nélküli kérés is lejár (a sosem válaszoló kérés nem akaszt meg mindent)', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', (_u: string, o: RequestInit) => new Promise((_, el) => o.signal?.addEventListener('abort', () => el(new DOMException('x', 'AbortError')))));
    const p = hiba(kerdez('/api/lassu'));
    await vi.advanceTimersByTimeAsync(ALAP_IDOKORLAT - 1);
    let kesz = false;
    void p.then(() => (kesz = true));
    await Promise.resolve();
    expect(kesz).toBe(false);
    await vi.advanceTimersByTimeAsync(2);
    expect((await p).message).toBe('időtúllépés');
  });

  it('a 0 korlát: nincs időkorlát', async () => {
    vi.useFakeTimers();
    let megszakitva = false;
    vi.stubGlobal('fetch', (_u: string, o: RequestInit) => new Promise(() => o.signal?.addEventListener('abort', () => (megszakitva = true))));
    void kerdez('/api/hosszu', { idokorlat: 0 });
    await vi.advanceTimersByTimeAsync(10 * ALAP_IDOKORLAT);
    expect(megszakitva).toBe(false);
  });
});

describe('a szerkesztő mentése a nem JSON 413-ra', () => {
  it('tartós elutasítás: nincs újrapróba-hurok', async () => {
    vi.useFakeTimers();
    let irasok = 0;
    vi.stubGlobal('fetch', async (_u: string, o: RequestInit) => {
      if (o?.method === 'PUT') {
        irasok++;
        return new Response(HTML_413, { status: 413 });
      }
      return new Response('{}', { status: 200 });
    });
    const d = new Dokumentum(vaultApi(), { ut: 'a.md', tartalom: 'x\n', hash: 'h', jel: '', mtime: 0 });
    d.valtozott(ChangeSet.of([{ from: 0, insert: 'a' }], 2), Text.of(['ax', '']), null as never);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(irasok).toBe(1);
    expect(d.allapot).toBe('hiba');
    expect(d.hiba).toBe('A kérés túl nagy (413).');
  });
});
