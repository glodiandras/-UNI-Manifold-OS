import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { VaultGraf } from '../src/lib/vault/graf.svelte';

const kerdez = vi.hoisted(() => vi.fn());
// C33 (T070): a gráf és a graf-meta feltételes kéréssel (ETag) tölt; az álkérés a `kerdez`-en át válaszol, ETag nélkül —
// kivéve, ha a teszt a `kerdezEtag`-et maga állítja (304)
const kerdezEtag = vi.hoisted(() => vi.fn());
vi.mock('../src/lib/core/api', async (orig) => ({ ...(await orig<typeof import('../src/lib/core/api')>()), kerdez, kerdezEtag }));

const VALASZ = {
  csucsok: ['a.md', 'b.md', 'c.png'],
  elek: [
    ['a.md', 'b.md'],
    ['b.md', 'c.png'],
  ],
  feloldatlan: {},
};
const META = { cimkek: { 'a.md': ['X'] }, tulajdonsagok: {} };
const JSON_ = { van: true, szincsoportok: [] };

function valaszol(valasz: unknown = VALASZ, meta: unknown = META) {
  kerdez.mockImplementation(async (ut: string) => {
    if (ut === '/api/vault/graf') return valasz;
    if (ut === '/api/vault/graf-meta') return meta;
    if (ut === '/api/vault/graf-beallitasok') return JSON_;
    throw new Error(`váratlan kérés: ${ut}`);
  });
}

const tipus = () => 'md' as const;

describe('VaultGraf', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    kerdez.mockReset();
    kerdezEtag.mockReset();
    kerdezEtag.mockImplementation(async (ut: string, _etag: string | null, o: unknown) => ({ adat: await kerdez(ut, o), etag: null }));
  });

  it('T070: változatlan szerkezetre (304) nincs újraépítés, és az ETag visszamegy', async () => {
    valaszol();
    kerdezEtag.mockImplementation(async (ut: string, etag: string | null, o: unknown) =>
      etag ? { adat: null, etag } : { adat: await kerdez(ut, o), etag: `"${ut}-1"` },
    );
    const g = new VaultGraf();
    g.megjelenik(tipus);
    await vi.advanceTimersByTimeAsync(0);
    const elso = g.adat;
    expect(g.epitesek).toBe(1);
    await g.frissit();
    expect(g.adat).toBe(elso);
    expect(g.epitesek).toBe(1); // a 304 után a GrafAdat nem épül újra (a fő szál nem dolgozik)
    expect(kerdezEtag).toHaveBeenLastCalledWith('/api/vault/graf-meta', '"/api/vault/graf-meta-1"', expect.anything());
  });
  afterEach(() => vi.useRealTimers());

  it('megjelenéskor betölti a gráfot, a metaadatot és a graph.json-t', async () => {
    valaszol();
    const g = new VaultGraf();
    g.megjelenik(tipus);
    await vi.advanceTimersByTimeAsync(0);
    expect(g.betoltve).toBe(true);
    expect(g.adat?.n).toBe(3);
    expect(g.json?.van).toBe(true);
    expect(kerdez).toHaveBeenCalledTimes(3);
  });

  it('változatlan szerkezetnél és attribútumokkal a régi adat marad (nincs újraépítés)', async () => {
    valaszol();
    const g = new VaultGraf();
    g.megjelenik(tipus);
    await vi.advanceTimersByTimeAsync(0);
    const elso = g.adat;
    await g.frissit();
    expect(g.adat).toBe(elso);
  });

  it('új él: új adat, más aláírással; csak a metaadat változik: új adat, azonos aláírással', async () => {
    valaszol();
    const g = new VaultGraf();
    g.megjelenik(tipus);
    await vi.advanceTimersByTimeAsync(0);
    const elso = g.adat!;
    valaszol(VALASZ, { cimkek: { 'a.md': ['Y'] }, tulajdonsagok: {} });
    await g.frissit();
    expect(g.adat).not.toBe(elso);
    expect(g.adat!.alairas).toBe(elso.alairas);
    const masodik = g.adat!;
    valaszol({ ...VALASZ, elek: [['a.md', 'b.md']] }, META);
    await g.frissit();
    expect(g.adat!.alairas).not.toBe(masodik.alairas);
  });

  it('látszó nézet nélkül a WS-esemény csak elavultnak jelöl, nem tölt', async () => {
    valaszol();
    const g = new VaultGraf();
    const k = new CoreKapcsolat('ws://nincs');
    g.figyel(k);
    k.szetoszt({ tipus: 'vault_valtozas', utak: ['a.md'] });
    await vi.advanceTimersByTimeAsync(5000);
    expect(kerdez).not.toHaveBeenCalled();
    g.megjelenik(tipus); // megjelenéskor tölt
    await vi.advanceTimersByTimeAsync(0);
    expect(g.betoltve).toBe(true);
  });

  it('látszó nézetnél a vault-változások egy töltésbe vonódnak össze', async () => {
    valaszol();
    const g = new VaultGraf();
    const k = new CoreKapcsolat('ws://nincs');
    g.figyel(k);
    g.megjelenik(tipus);
    await vi.advanceTimersByTimeAsync(0);
    kerdez.mockClear();
    for (let i = 0; i < 5; i++) k.szetoszt({ tipus: 'vault_valtozas', utak: [`n${i}.md`] });
    await vi.advanceTimersByTimeAsync(1500);
    expect(kerdez.mock.calls.filter((c) => c[0] === '/api/vault/graf')).toHaveLength(1);
  });

  it('a nézet eltűnése után nincs ütemezett töltés', async () => {
    valaszol();
    const g = new VaultGraf();
    const k = new CoreKapcsolat('ws://nincs');
    g.figyel(k);
    const le = g.megjelenik(tipus);
    await vi.advanceTimersByTimeAsync(0);
    kerdez.mockClear();
    k.szetoszt({ tipus: 'vault_valtozas', utak: ['q.md'] });
    le();
    await vi.advanceTimersByTimeAsync(5000);
    expect(kerdez).not.toHaveBeenCalled();
  });

  it('503-ra (az index épül) nincs hiba, az `index` esemény hoz újra', async () => {
    const { ApiHiba } = await import('../src/lib/core/api');
    kerdez.mockRejectedValue(new ApiHiba(503, 'épül'));
    const g = new VaultGraf();
    g.megjelenik(tipus);
    await vi.advanceTimersByTimeAsync(0);
    expect(g.hiba).toBeNull();
    expect(g.betoltve).toBe(false);
  });
});
