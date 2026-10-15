// „Kérdezz a vaulttól” (C25b): az NDJSON-darabolás, a vége-szövegek és a folyam fogyasztása (álfetch-csel), a megszakítás.
import { describe, expect, it } from 'vitest';
import { KerdezzAllapot, ndjsonSorok, vegeSzoveg } from '../src/lib/kereses/kerdezz.svelte';

function folyam(darabok: string[], megszakit?: AbortSignal): Response {
  const enc = new TextEncoder();
  let i = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(c) {
      if (megszakit?.aborted) return c.error(new DOMException('megszakítva', 'AbortError'));
      if (i < darabok.length) c.enqueue(enc.encode(darabok[i++]));
      else c.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } });
}

const MONDAT = {
  tipus: 'mondat', mondat: 'A spártai fiúkat hétévesen elvették.', ut: 'T02/Spárta.md', link: '[[T02/Spárta#^k1]]',
  blokk: 'k1', sor_kezd: 5, sor_veg: 6, fejezet: ['Nevelés'], idezet: 'a fiúkat hétévesen elvették a családtól',
};

describe('kérdezz', () => {
  it('a sorhatáron átnyúló darabokat egyben adja', () => {
    const a = ndjsonSorok('', '{"tipus":"elvetve","ok":"x"}\n{"tipus":"ve');
    expect(a.esemenyek).toEqual([{ tipus: 'elvetve', ok: 'x' }]);
    const b = ndjsonSorok(a.maradek, 'ge","allapot":"kesz"}\n\n');
    expect(b.esemenyek[0]).toMatchObject({ tipus: 'vege', allapot: 'kesz' });
    expect(b.maradek).toBe('');
  });

  it('a nem kész válasz oka magyarul', () => {
    expect(vegeSzoveg({ allapot: 'nincs_valasz', ok: 'nincs_eleg_forras' })).toMatch(/nincs elég forrás/);
    expect(vegeSzoveg({ allapot: 'nincs_modell', ok: 'nincs_modell' })).toMatch(/kalibrált/);
    expect(vegeSzoveg({ allapot: 'kesz', ok: null })).toBe('');
  });

  it('a folyam eseményei az állapotba kerülnek, a kérés folyamot kér', async () => {
    const a = new KerdezzAllapot();
    let torzs: unknown = null;
    const f = (async (_u: string, o: RequestInit) => {
      torzs = JSON.parse(String(o.body));
      const s = JSON.stringify;
      return folyam([
        s({ tipus: 'forrasok', forrasok: [{ szam: 1, ut: 'T02/Spárta.md', fejezet: ['Nevelés'], sor_kezd: 3, sor_veg: 9 }] }) + '\n',
        s(MONDAT).slice(0, 20), s(MONDAT).slice(20) + '\n',
        s({ tipus: 'vege', allapot: 'kesz', ok: null, mondatok: 1, elvetve: {}, proba: false }) + '\n',
      ]);
    }) as unknown as typeof fetch;
    await a.kerdez('  Mikor vették el a fiúkat?  ', f);
    expect(torzs).toEqual({ kerdes: 'Mikor vették el a fiúkat?', folyam: true });
    expect(a.forrasok).toHaveLength(1);
    expect(a.mondatok.map((m) => m.link)).toEqual(['[[T02/Spárta#^k1]]']);
    expect(a.vege?.allapot).toBe('kesz');
    expect(a.fut).toBe(false);
    expect(a.hiba).toBeNull();
  });

  it('a hibás válasz üzenete megjelenik; a megszakítás nem hiba', async () => {
    const a = new KerdezzAllapot();
    const rossz = (async () => new Response(JSON.stringify({ hiba: 'a modell nem érhető el' }), { status: 503 })) as unknown as typeof fetch;
    await a.kerdez('kérdés', rossz);
    expect(a.hiba).toBe('a modell nem érhető el');
    const lassu = ((_u: string, o: RequestInit) =>
      new Promise<Response>((_res, rej) => o.signal?.addEventListener('abort', () => rej(new DOMException('x', 'AbortError'))))) as unknown as typeof fetch;
    const p = a.kerdez('másik', lassu);
    expect(a.fut).toBe(true);
    a.megszakit();
    await p;
    expect(a.fut).toBe(false);
    expect(a.hiba).toBeNull();
  });
});
