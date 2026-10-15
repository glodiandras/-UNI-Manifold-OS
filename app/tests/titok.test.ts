// A core API-titka a felületen (C29.7b, 35. döntés / T071): a héj a kézfogásból kapott titkot a lap betöltése ELŐTT injektálja
// (`window.__MOS_TITOK__`, WKUserScript); fejlesztői tartalék (Browser pane, kézi próba): a címben `#titok=<t>` — a szerver nem
// látja, az app egyszer olvassa és törli. Minden API-kérés `X-Manifold: <titok>`-kal megy, a WS az alprotokollban küldi.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kerdez } from '../src/lib/core/api';
import { apiTitok, titokBeallit, titokBetolt } from '../src/lib/core/titok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';

const TITOK = 'teszt-titok-AbC123_.-0123456789';

type TitokAblak = Window & { __MOS_TITOK__?: unknown };
const ablak = () => window as TitokAblak;

beforeEach(() => {
  titokBeallit(null);
  delete ablak().__MOS_TITOK__;
  history.replaceState(null, '', '/');
});
afterEach(() => {
  titokBeallit(null);
  delete ablak().__MOS_TITOK__;
  history.replaceState(null, '', '/');
  vi.unstubAllGlobals();
});

describe('a titok forrása', () => {
  it('a héj injektálta `window.__MOS_TITOK__` az elsődleges forrás; beolvasás után a lapról eltűnik', () => {
    ablak().__MOS_TITOK__ = TITOK;
    expect(titokBetolt()).toBe(TITOK);
    expect(apiTitok()).toBe(TITOK);
    expect(ablak().__MOS_TITOK__).toBeUndefined(); // nem marad a globális névtérben (kevesebb felület a lap szkriptjeinek)
  });

  it('tartalék: a `#titok=` a címben — beolvassa és letörli a címből (a history-ba sem marad)', () => {
    history.replaceState(null, '', `/#titok=${TITOK}`);
    expect(titokBetolt()).toBe(TITOK);
    expect(location.hash).toBe('');
    expect(location.href).not.toContain(TITOK);
  });

  it('a héj titka elsőbbséget élvez a címbelivel szemben', () => {
    ablak().__MOS_TITOK__ = TITOK;
    history.replaceState(null, '', '/#titok=masik-titok-0123456789');
    expect(titokBetolt()).toBe(TITOK);
  });

  it('érvénytelen alak (rövid, tiltott karakter, nem szöveg) vagy hiány: üres titok', () => {
    for (const rossz of ['rovid', 'szóköz van benne 0123456789', 'a'.repeat(129), 'ékezetes-é-0123456789', 42, null, {}]) {
      titokBeallit(null);
      ablak().__MOS_TITOK__ = rossz;
      expect(titokBetolt(), String(rossz)).toBe('');
    }
    titokBeallit(null);
    delete ablak().__MOS_TITOK__;
    expect(apiTitok()).toBe('');
  });

  it('lusta: az első `apiTitok()` hívás is beolvassa', () => {
    ablak().__MOS_TITOK__ = TITOK;
    expect(apiTitok()).toBe(TITOK);
  });
});

describe('a titok használata', () => {
  it('a `kerdez` az X-Manifold fejlécben a titkot küldi (nem a régi statikus „1”-et)', async () => {
    titokBeallit(TITOK);
    const fetchStub = vi.fn(async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchStub);
    await kerdez('/api/allapot');
    const init = (fetchStub.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)['X-Manifold']).toBe(TITOK);
  });

  it('a `CoreKapcsolat` a titkot az alprotokollban küldi: `mos.<titok>`', () => {
    titokBeallit(TITOK);
    const peldanyok: { url: string; protokollok: unknown }[] = [];
    class AlWs {
      static OPEN = 1;
      readyState = 0;
      onopen = null;
      onmessage = null;
      onclose = null;
      constructor(url: string, protokollok?: unknown) {
        peldanyok.push({ url, protokollok });
      }
      close() {}
      send() {}
    }
    vi.stubGlobal('WebSocket', AlWs);
    const k = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    k.indit();
    expect(peldanyok).toEqual([{ url: 'ws://127.0.0.1:1/ws', protokollok: [`mos.${TITOK}`] }]);
    k.leallit();
  });
});

describe('böngésző nélkül (kézi Node-próbák)', () => {
  it('a `MOS_API_TITOK` környezeti változóból veszi', () => {
    const regi = process.env.MOS_API_TITOK;
    process.env.MOS_API_TITOK = TITOK;
    try {
      expect(titokBetolt(null)).toBe(TITOK);
      titokBeallit(null);
      process.env.MOS_API_TITOK = 'rovid';
      expect(titokBetolt(null)).toBe('');
    } finally {
      if (regi === undefined) delete process.env.MOS_API_TITOK;
      else process.env.MOS_API_TITOK = regi;
    }
  });
});
