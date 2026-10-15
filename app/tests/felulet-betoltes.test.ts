// A felület-állapot betöltése és mentése (javítókör D, 1–2. lelet): a lassú core nem írhatja felül a mentett elrendezést,
// és a bukott mentés nem vész el.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Felulet, Mento, betolt, betoltesPotol } from '../src/lib/elrendezes/felulet.svelte';

const MENTETT = {
  verzio: 1,
  tema: 'sotet',
  oldalsav: { szelesseg: 300, nyitva: true, nezet: 'fajlok', nyitott: ['Matek', 'Matek/Algebra'] },
  jobbPanel: { szelesseg: 300, nyitva: false, visszahivatkozasok: true, emlitesek: false, kimeno: false, vazlat: true },
  csend: { be: true, bemutatva: true },
  munkaterulet: {
    gyoker: { tipus: 'panel', id: 'p1', fulek: [{ id: 'f1', ut: 'Matek/A.md' }, { id: 'f2', ut: 'Matek/B.md' }], aktiv: 'f2' },
    aktivPanelId: 'p1',
  },
  legutobbiFajlok: ['Matek/B.md', 'Matek/A.md'],
  legutobbiParancsok: [],
};

const fulUtak = (f: Felulet) => f.munkaterulet.panelek().flatMap((p) => p.fulek.map((x) => x.ut));

describe('a felület-állapot betöltése', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('a core nem válaszol időben: alapállapot, „nem sikerült” jellel', async () => {
    vi.stubGlobal('fetch', (_u: string, o: RequestInit) => new Promise((_, el) => o.signal?.addEventListener('abort', () => el(new DOMException('x', 'AbortError')))));
    const b = await betolt(20);
    expect(b).toEqual({ allapot: {}, sikerult: false });
  });

  it('a válasz megjön: a mentett állapot, sikerrel', async () => {
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ allapot: MENTETT }), { status: 200 }));
    const b = await betolt(1000);
    expect(b.sikerult).toBe(true);
    expect((b.allapot as typeof MENTETT).tema).toBe('sotet');
  });

  it('bukott betöltés után a mentő zárolva: az alapelrendezés nem megy ki; a pótlás a mentettet hozza vissza', async () => {
    vi.useFakeTimers();
    try {
      const kuld = vi.fn((_j: string, _a: boolean) => Promise.resolve());
      const felulet = new Felulet({});
      felulet.betoltve = false;
      const mento = new Mento(kuld, 500);
      mento.alap(JSON.stringify(felulet.sorosit()));
      mento.zarol();
      // a felhasználó közben fájlt nyit: semmi nem mentődik
      felulet.munkaterulet.megnyit('Történelem/C.md');
      mento.utemez(JSON.stringify(felulet.sorosit()));
      vi.advanceTimersByTime(5000);
      await mento.ki(true);
      expect(kuld).not.toHaveBeenCalled();
      // a core még nem válaszol: marad zárolva
      expect(await betoltesPotol(felulet, mento, async () => ({ allapot: {}, sikerult: false }))).toBe(false);
      expect(mento.zarolt).toBe(true);
      // most igen: a mentett elrendezés, a közben nyitott fájl új fülben, a legutóbbiak elején
      expect(await betoltesPotol(felulet, mento, async () => ({ allapot: MENTETT, sikerult: true }))).toBe(true);
      expect(felulet.betoltve).toBe(true);
      expect(felulet.tema).toBe('sotet');
      expect(felulet.oldalsav.nyitott).toEqual(['Matek', 'Matek/Algebra']);
      expect(fulUtak(felulet)).toEqual(['Matek/A.md', 'Matek/B.md', 'Történelem/C.md']);
      expect(felulet.legutobbiFajlok[0]).toBe('Történelem/C.md');
      expect(felulet.legutobbiFajlok).toContain('Matek/A.md');
      expect(mento.zarolt).toBe(false);
      vi.advanceTimersByTime(600);
      expect(kuld).toHaveBeenCalledOnce();
      const mentve = JSON.parse(kuld.mock.calls[0][0]);
      expect(mentve.tema).toBe('sotet');
      expect(mentve.oldalsav.nyitott).toEqual(['Matek', 'Matek/Algebra']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('változatlan alapállapotnál a pótlás nem ment (a betöltött állapot az alap)', async () => {
    vi.useFakeTimers();
    try {
      const kuld = vi.fn(() => Promise.resolve());
      const felulet = new Felulet({});
      felulet.betoltve = false;
      const mento = new Mento(kuld, 500);
      mento.zarol();
      await betoltesPotol(felulet, mento, async () => ({ allapot: MENTETT, sikerult: true }));
      vi.advanceTimersByTime(1000);
      expect(kuld).not.toHaveBeenCalled();
      expect(fulUtak(felulet)).toEqual(['Matek/A.md', 'Matek/B.md']);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('a bukott mentés újrapróbája', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('a bukott állapot függőben marad, és visszalépő késleltetéssel újra megy', async () => {
    let bukik = true;
    const kuld = vi.fn((_j: string, _a: boolean) => (bukik ? Promise.reject(new Error('nincs core')) : Promise.resolve()));
    const m = new Mento(kuld, 500, 2000, 30000);
    m.utemez('{"a":1}');
    await vi.advanceTimersByTimeAsync(500);
    expect(kuld).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1999);
    expect(kuld).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(kuld).toHaveBeenCalledTimes(2); // 2 s után
    await vi.advanceTimersByTimeAsync(4000);
    expect(kuld).toHaveBeenCalledTimes(3); // 4 s után
    bukik = false;
    await vi.advanceTimersByTimeAsync(8000);
    expect(kuld).toHaveBeenCalledTimes(4);
    expect(kuld).toHaveBeenLastCalledWith('{"a":1}', false);
    await vi.advanceTimersByTimeAsync(60000);
    expect(kuld).toHaveBeenCalledTimes(4); // sikeres után nincs több
  });

  it('a küldés alatt kiment újabb állapot nyer: a bukott régi nem írja felül', async () => {
    const valaszok: { r: () => void; j: () => void }[] = [];
    const kuld = vi.fn((_j: string, _a: boolean) => new Promise<void>((r, j) => valaszok.push({ r, j: () => j(new Error('x')) })));
    const m = new Mento(kuld, 500, 2000, 30000);
    m.utemez('{"a":1}');
    void m.ki(false);
    m.utemez('{"a":2}');
    void m.ki(false); // az újabb kimegy, mielőtt a régi elbukna
    valaszok[1].r();
    valaszok[0].j();
    await vi.advanceTimersByTimeAsync(60000);
    expect(kuld.mock.calls.map((c) => c[0])).toEqual(['{"a":1}', '{"a":2}']);
  });

  it('a bukás alatt függő újabb állapot megy újra', async () => {
    const valaszok: { j: () => void }[] = [];
    const kuld = vi.fn((_j: string, _a: boolean) => new Promise<void>((_r, j) => valaszok.push({ j: () => j(new Error('x')) })));
    const m = new Mento(kuld, 500, 2000, 30000);
    m.utemez('{"a":1}');
    void m.ki(false);
    m.utemez('{"a":2}'); // még nem ment ki
    valaszok[0].j();
    await vi.advanceTimersByTimeAsync(2000);
    expect(kuld).toHaveBeenLastCalledWith('{"a":2}', false);
  });
});
