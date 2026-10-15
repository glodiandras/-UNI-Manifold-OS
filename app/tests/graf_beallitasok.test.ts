import { describe, expect, it } from 'vitest';
import { EROK_TARTOMANY, effektiv, erokGraphJsonbol, feluliras, fizikaBeallitas, type GrafJson } from '../src/lib/graf/beallitasok';
import { repulesInterpolator } from '../src/lib/graf/rajzolo';

// a valódi vault graph.json-ja (C13 mérése) a /api/vault/graf-beallitasok alakjában
const JSON_: GrafJson = {
  van: true,
  kereses: 'tag:#x',
  mutat_mellekletek: true,
  mutat_arvak: false,
  nyil: true,
  meret_szorzo: 2.25,
  vonal_szorzo: 0.5,
  erok: { kozep: 0.245699285075961, taszitas: 20, rugo: 0.548257372654156, tavolsag: 230 },
  szincsoportok: [
    { lekerdezes: 'tag:#Mathematics', szin: '#4caf50', alfa: 1 },
    { lekerdezes: 'file:.canvas', szin: '#f00000', alfa: 0.5 },
  ],
};

describe('gráf-beállítások', () => {
  it('graph.json nélkül az alapértékek', () => {
    const e = effektiv(null, {});
    expect(e).toMatchObject({ lekerdezes: '', mellekletek: true, arvak: true, nyilak: false, szincsoportForras: 'nincs' });
    expect(e.erok).toEqual({ taszitas: 1, rugo: 1, rugohossz: 1, kozep: 1 });
    expect(effektiv({ van: false }, {}).szincsoportok).toEqual([]);
  });

  it('a graph.json az alap, a felülírás erősebb', () => {
    const e = effektiv(JSON_, {});
    expect(e).toMatchObject({ lekerdezes: 'tag:#x', arvak: false, nyilak: true, szincsoportForras: 'graph.json', meretSzorzo: 2.25 });
    expect(e.szincsoportok).toEqual([
      { lekerdezes: 'tag:#Mathematics', szin: '#4caf50' },
      { lekerdezes: 'file:.canvas', szin: '#f00000' },
    ]);
    const f = effektiv(JSON_, { lekerdezes: '', arvak: true, szincsoportok: [{ lekerdezes: 'path:A/', szin: '#0000ff' }], erok: { taszitas: 2 } });
    expect(f).toMatchObject({ lekerdezes: '', arvak: true, nyilak: true, szincsoportForras: 'sajat' });
    expect(f.szincsoportok).toEqual([{ lekerdezes: 'path:A/', szin: '#0000ff' }]);
    expect(f.erok.taszitas).toBe(2); // a többi erő a graph.json-ból marad
    expect(f.erok.rugo).toBeCloseTo(0.548, 3);
  });

  it('az Obsidian erői a csúszkák szorzóira képeződnek (a legacy leképezése), a tartományon belül', () => {
    const e = erokGraphJsonbol(JSON_);
    expect(e.taszitas).toBe(2); // 20 / 10
    expect(e.rugohossz).toBeCloseTo(0.92, 2); // 230 / 250
    expect(e.kozep).toBeCloseTo(0.4737, 3); // 0,2457 / 0,5187
    const szelso = erokGraphJsonbol({ van: true, erok: { taszitas: 1000, rugo: -5, tavolsag: 1, kozep: 9 } });
    expect(szelso.taszitas).toBe(EROK_TARTOMANY.taszitas.max);
    expect(szelso.rugo).toBe(EROK_TARTOMANY.rugo.min);
    expect(szelso.kozep).toBe(EROK_TARTOMANY.kozep.max);
  });

  it('a mentett felülírás ellenőrzése: hibás mezőt eldob, a számot a tartományba szorítja', () => {
    expect(feluliras(null)).toEqual({});
    expect(feluliras([1, 2])).toEqual({});
    expect(
      feluliras({
        lekerdezes: 'x'.repeat(900),
        mellekletek: 'igen',
        arvak: false,
        erok: { taszitas: 99, rugo: 'sok', kozep: 1.5, ismeretlen: 3 },
        szincsoportok: [
          { lekerdezes: 'a', szin: '#ABCDEF' },
          { lekerdezes: 'b', szin: 'piros' },
          { lekerdezes: 7, szin: '#000000' },
          null,
        ],
      }),
    ).toEqual({
      lekerdezes: 'x'.repeat(500),
      arvak: false,
      erok: { taszitas: EROK_TARTOMANY.taszitas.max, kozep: 1.5 },
      szincsoportok: [{ lekerdezes: 'a', szin: '#abcdef' }],
    });
    expect(feluliras({ szincsoportok: Array.from({ length: 80 }, () => ({ lekerdezes: 'a', szin: '#000000' })) }).szincsoportok).toHaveLength(30);
  });

  it('a fizika beállítása az effektív erőkből', () => {
    expect(fizikaBeallitas(effektiv(JSON_, {}))).toEqual({ taszitas: 2, rugo: expect.closeTo(0.548, 3), rugohossz: expect.closeTo(0.92, 2), kozep: expect.closeTo(0.4737, 3) });
  });
});

describe('repülés (van Wijk–Nuij)', () => {
  it('a végpontokat pontosan eléri, és közben végig véges', () => {
    const { f, ido } = repulesInterpolator([0, 0, 1000], [4000, -2500, 200]);
    const [x0, y0, w0] = f(0);
    const [x1, y1, w1] = f(1);
    expect([x0, y0, w0].map((v) => Math.round(v * 1000) / 1000)).toEqual([0, 0, 1000]);
    expect([x1, y1, w1].map((v) => Math.round(v * 1000) / 1000)).toEqual([4000, -2500, 200]);
    for (let t = 0; t <= 1; t += 0.05) expect(f(t).every(Number.isFinite)).toBe(true);
    expect(ido).toBeGreaterThan(0);
    // távoli cél: a nézet közben kitágul (kisebb nagyítás), majd beáll
    expect(Math.max(...Array.from({ length: 21 }, (_, i) => f(i / 20)[2]))).toBeGreaterThan(1000);
  });

  it('azonos helyen csak nagyít (nincs 0-val osztás)', () => {
    const { f } = repulesInterpolator([10, 10, 800], [10, 10, 100]);
    expect(f(1)[2]).toBeCloseTo(100, 6);
    expect(f(0.5).every(Number.isFinite)).toBe(true);
  });
});
