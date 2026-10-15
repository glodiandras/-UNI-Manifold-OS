// C33 (T185, A2-tesztek-15; a 24(f) döntés gépi őre): a Graf.svelte renderelve, hamis időzítőkkel és rAF-fal — a betöltés és a
// lehűlés után **nyugalomban nincs ütemezés** (sem rAF, sem fizika-időzítő), és egy tartalmi vault-változás (304: a szerkezet
// változatlan) sem indít újra semmit. A valódi WebKit nyugalmi CPU-ja a `tests/kezi/graf_nyugalmi_cpu.py` (kézi).
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Graf from '../src/graf/Graf.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import type { Ful } from '../src/lib/elrendezes/munkaterulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { grafAdat } from '../src/lib/vault/graf.svelte';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';

const kerdez = vi.hoisted(() => vi.fn());
const kerdezEtag = vi.hoisted(() => vi.fn());
vi.mock('../src/lib/core/api', async (orig) => ({ ...(await orig<typeof import('../src/lib/core/api')>()), kerdez, kerdezEtag }));

const N = 24;
const CSUCSOK = Array.from({ length: N }, (_, i) => `J${i}.md`);
const VALASZ = { csucsok: CSUCSOK, elek: CSUCSOK.slice(1).map((u, i) => [CSUCSOK[i], u]), feloldatlan: {} };
const META = { cimkek: {}, tulajdonsagok: {} };

let rafHivas = 0;

/** Egy 2D-kontextus álmása: minden metódus no-op, a `measureText` szélességet ad. */
function alKontextus(): CanvasRenderingContext2D {
  const cel: Record<string | symbol, unknown> = { measureText: () => ({ width: 10 }), canvas: null };
  return new Proxy(cel, {
    get: (t, k) => (k in t ? t[k] : typeof k === 'string' ? () => undefined : undefined),
    set: (t, k, v) => {
      t[k] = v;
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
}

beforeEach(() => {
  vi.useFakeTimers();
  rafHivas = 0;
  kerdez.mockReset();
  kerdezEtag.mockReset();
  kerdez.mockImplementation(async (ut: string) => {
    if (ut === '/api/vault/graf-beallitasok') return { van: false, szincsoportok: [] };
    throw new Error(`váratlan: ${ut}`);
  });
  // az első töltés adatot ad ETag-gel, a feltételes kérés (változatlan szerkezet) 304-et
  kerdezEtag.mockImplementation(async (ut: string, etag: string | null) => {
    if (etag) return { adat: null, etag };
    return { adat: ut === '/api/vault/graf' ? VALASZ : META, etag: `"${ut}"` };
  });
  vi.stubGlobal('Worker', undefined); // a fizika a fő szálon fut (a hamis időzítőkkel mérhető)
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal('requestAnimationFrame', (f: FrameRequestCallback) => {
    rafHivas++;
    return setTimeout(() => f(performance.now()), 16) as unknown as number;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => alKontextus() as never);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function nyit(k: CoreKapcsolat) {
  const ful = $state<Ful>({ id: 'g1', ut: null, nezet: { tipus: 'graf' } } as Ful);
  const kornyezet = { felulet: new Felulet({}), fajlok: new VaultFajlok(), kapcsolat: k };
  return render(Graf, { props: { ful } as never, context: new Map([[KORNYEZET_KULCS, kornyezet]]) });
}

describe('Graf.svelte nyugalomban', () => {
  it('a betöltés és a lehűlés után nincs ütemezés; a tartalmi vault-változás sem indít számolást', async () => {
    const k = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = grafAdat.figyel(k);
    try {
      nyit(k);
      await vi.advanceTimersByTimeAsync(0);
      await waitFor(() => expect(grafAdat.adat?.n).toBe(N));
      // a fizika lehűl (a fő szálú motor ~300 tick), a rajz utána leáll
      await vi.advanceTimersByTimeAsync(30_000);
      const meres = (window as unknown as { __grafMeres?: () => { utemezesek: number; workerben: boolean } }).__grafMeres!;
      expect(meres().workerben).toBe(false);
      const ut0 = meres().utemezesek;
      const raf0 = rafHivas;
      expect(ut0).toBeGreaterThan(0); // a beállás alatt rajzolt
      // nyugalom: 60 s alatt egyetlen ütemezés sincs, és függő időzítő sem marad
      await vi.advanceTimersByTimeAsync(60_000);
      expect(meres().utemezesek).toBe(ut0);
      expect(rafHivas).toBe(raf0);
      expect(vi.getTimerCount()).toBe(0);
      // tartalmi mentés: a core 304-et ad (a szerkezet változatlan) → nincs újraépítés, nincs rajz, nincs fizika
      const epitesek = grafAdat.epitesek;
      k.szetoszt({ tipus: 'vault_valtozas', utak: ['J3.md'], torolt: [], kulso: [] });
      await vi.advanceTimersByTimeAsync(5_000);
      expect(kerdezEtag).toHaveBeenCalledWith('/api/vault/graf', '"/api/vault/graf"', expect.anything());
      expect(grafAdat.epitesek).toBe(epitesek);
      expect(meres().utemezesek).toBe(ut0);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      le();
    }
  });
});
