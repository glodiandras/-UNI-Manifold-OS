// A jelenet (C35a), könyvtár nélkül: a görbék és a kitöltés adata az aktuális ablakra, a CAS-jelölők, a kiemelt
// pontok, a jelmagyarázat és a képernyőolvasónak szóló leírás. A rajzoló (JSXGraph) ebből építkezik.

import { describe, expect, it } from 'vitest';
import { elemez } from '../src/szerkeszto/renderelok/plot/forras';
import {
  JELOLO_SZIN,
  jelmagyarazat,
  jelolok,
  kitoltesAdat,
  leiras,
  vonalAdat,
} from '../src/szerkeszto/renderelok/plot/jelenet';
import type { Jellemzok } from '../src/szerkeszto/renderelok/plot/jellemzok';
import { SOROZAT_SZIN, terv } from '../src/szerkeszto/renderelok/plot/terv';

const MERET = { szelesseg: 400, magassag: 300 };
const NEZET = { x: [-5, 5] as [number, number], y: [-5, 5] as [number, number] };
const t = (szoveg: string) => terv(elemez(szoveg));

function jellemzok(mas: Partial<Jellemzok> = {}): Jellemzok {
  return {
    allapot: 'ok',
    zerushelyek: [],
    szelsoertekek: [],
    aszimptotak: [],
    ferde_aszimptotak: [],
    numerikus: false,
    figyelmeztetesek: [],
    ...mas,
  };
}

describe('vonalAdat', () => {
  it('a függvény az ablakon: NaN-nal szakított szakaszok pólusnál', () => {
    const d = vonalAdat(t('y = 1/x').gorbek[0], NEZET, MERET);
    expect(d.x.length).toBe(d.y.length);
    expect(d.x.some(Number.isNaN)).toBe(true);
    const nemNaN = d.x.filter((x) => !Number.isNaN(x));
    expect(Math.min(...nemNaN)).toBeGreaterThanOrEqual(-5);
    expect(Math.max(...nemNaN)).toBeLessThanOrEqual(5);
  });

  it('a függvény pontjai a kifejezés értékei', () => {
    const d = vonalAdat(t('y = x^2').gorbek[0], NEZET, MERET);
    for (let i = 0; i < d.x.length; i += 25) expect(d.y[i]).toBeCloseTo(Math.min(d.x[i] ** 2, 105), 9);
  });

  it('a paraméteres görbe a kör: a sugár állandó, a kezdő és a záró pont egybeesik', () => {
    const d = vonalAdat(t('x = 3*cos(t), y = 3*sin(t), t in [0, 2*pi]').gorbek[0], NEZET, MERET);
    expect(d.x.length).toBeGreaterThan(100);
    for (let i = 0; i < d.x.length; i += 10) expect(Math.hypot(d.x[i], d.y[i])).toBeCloseTo(3, 9);
    expect(d.x[0]).toBeCloseTo(d.x.at(-1)!, 9);
    expect(d.y[0]).toBeCloseTo(d.y.at(-1)!, 9);
  });

  it('a paraméteres görbe NaN-nál szakad (spirál gyökkel)', () => {
    const d = vonalAdat(t('x = sqrt(t), y = t, t in [-2, 2]').gorbek[0], NEZET, MERET);
    expect(d.x.filter((x) => !Number.isNaN(x)).length).toBeGreaterThan(10);
    expect(d.x.filter((x) => !Number.isNaN(x)).every((x) => x >= 0)).toBe(true);
  });

  it('a pontszám az ablak szélességétől függ, de korlátos', () => {
    const kicsi = vonalAdat(t('y = sin(x)').gorbek[0], NEZET, { szelesseg: 100, magassag: 100 });
    const nagy = vonalAdat(t('y = sin(x)').gorbek[0], NEZET, { szelesseg: 4000, magassag: 300 });
    expect(nagy.x.length).toBeGreaterThan(kicsi.x.length);
    expect(nagy.x.length).toBeLessThan(8000);
  });
});

describe('kitoltesAdat (egyenlőtlenség)', () => {
  it('az y > f(x) a görbe fölötti terület: a zárás az ablak tetején', () => {
    const d = kitoltesAdat(t('y > x').tartomanyok[0], NEZET, MERET);
    const veges = d.x.map((x, i) => [x, d.y[i]]).filter(([x]) => !Number.isNaN(x));
    expect(veges.length).toBeGreaterThan(10);
    const utolso = veges.at(-1)!;
    const elsoElotti = veges.at(-2)!;
    expect(utolso[1]).toBe(5); // a felső él
    expect(elsoElotti[1]).toBe(5);
    expect(veges.some(([x, y]) => Math.abs(y - x) < 1e-9)).toBe(true); // a határgörbe pontjai
  });

  it('az y < f(x) az ablak aljára zár', () => {
    const d = kitoltesAdat(t('y <= x^2 - 3').tartomanyok[0], NEZET, MERET);
    const veges = d.y.filter((y) => !Number.isNaN(y));
    expect(veges.at(-1)).toBe(-5);
  });

  it('a pólus két oldala külön sokszög (NaN-nal elválasztva)', () => {
    const d = kitoltesAdat(t('y > 1/x').tartomanyok[0], NEZET, MERET);
    expect(d.x.some(Number.isNaN)).toBe(true);
  });
});

describe('jelolok (CAS-jellemzők és kiemelt pontok)', () => {
  const p = t('y = x^2 - 4\ny = 1/x\npont (1, 2) "P"');
  const j = new Map<number, Jellemzok>([
    [
      0,
      jellemzok({
        zerushelyek: [{ x: '-2', ertek: -2 }, { x: '2', ertek: 2 }],
        szelsoertekek: [{ x: '0', y: '-4', x_ertek: 0, y_ertek: -4, tipus: 'minimum' }],
      }),
    ],
    [
      1,
      jellemzok({
        aszimptotak: [
          { egyenlet: 'x=0', tipus: 'fuggoleges', ertek: 0 },
          { egyenlet: 'y=0', tipus: 'vizszintes', ertek: 0 },
        ],
        ferde_aszimptotak: [{ egyenlet: 'y=sqrt(3)*x', tipus: 'ferde', meredekseg: 1.732, eltolas: 0 }],
      }),
    ],
  ]);

  it('zérushely üres, szélsőérték teli pont, a görbe színével, olvasható felirattal', () => {
    const l = jelolok(p, j);
    const nulla = l.filter((e) => e.tipus === 'pont' && e.stilus === 'ures');
    expect(nulla.map((e) => [e.tipus === 'pont' && e.x, e.tipus === 'pont' && e.y])).toEqual([[-2, 0], [2, 0]]);
    expect(nulla.every((e) => e.szin === SOROZAT_SZIN[0])).toBe(true);
    const szelso = l.find((e) => e.tipus === 'pont' && e.stilus === 'teli' && e.szin === SOROZAT_SZIN[0])!;
    expect(szelso).toMatchObject({ x: 0, y: -4, felirat: 'min (0; −4)' });
  });

  it('az aszimptota szaggatott egyenes két pontjával; a ferde is', () => {
    const l = jelolok(p, j).filter((e) => e.tipus === 'egyenes');
    expect(l.map((e) => e.tipus === 'egyenes' && e.felirat)).toEqual(['x=0', 'y=0', 'y=√3·x']);
    const fugg = l[0];
    expect(fugg.tipus === 'egyenes' && fugg.p1[0]).toBe(0);
    expect(fugg.tipus === 'egyenes' && fugg.p2[0]).toBe(0);
    const vizsz = l[1];
    expect(vizsz.tipus === 'egyenes' && vizsz.p1[1]).toBe(0);
    expect(vizsz.tipus === 'egyenes' && vizsz.p2[1]).toBe(0);
    const ferde = l[2];
    expect(ferde.tipus === 'egyenes' && ferde.p2[1] - ferde.p1[1]).toBeCloseTo(1.732, 9);
    expect(l.every((e) => e.szin === JELOLO_SZIN.aszimptota)).toBe(true);
  });

  it('a kiemelt pont a felhasználóé, a szöveg színével', () => {
    const l = jelolok(p, j).filter((e) => e.tipus === 'pont' && e.felirat === 'P');
    expect(l).toHaveLength(1);
    expect(l[0]).toMatchObject({ x: 1, y: 2, stilus: 'teli', szin: JELOLO_SZIN.pont });
  });

  it('a nem kész állapot kimarad; a jellemző nélkül csak a saját pont', () => {
    const l = jelolok(p, new Map([[0, jellemzok({ allapot: 'homokozo_hiba' })]]));
    expect(l).toHaveLength(1);
    expect(jelolok(p, new Map())).toHaveLength(1);
  });

  it('a szín csak token, a tokenek a meglévők', () => {
    const tokenek = new Set([...SOROZAT_SZIN, ...Object.values(JELOLO_SZIN)]);
    for (const e of jelolok(p, j)) expect(tokenek.has(e.szin)).toBe(true);
    for (const s of Object.values(JELOLO_SZIN)) expect(s).toMatch(/^--[a-z-]+$/);
  });
});

describe('jelmagyarazat, leírás', () => {
  it('a jelmagyarázat csak a címkézett görbéket és egyenlőtlenségeket sorolja a színükkel', () => {
    const p = t('y = x "f"\ny = x^2\ny > 1 "tartomány"');
    expect(jelmagyarazat(p)).toEqual([
      { szin: SOROZAT_SZIN[0], cimke: 'f' },
      { szin: SOROZAT_SZIN[2], cimke: 'tartomány' },
    ]);
  });

  it('a leírás magyarul sorolja a függvényeket és a nevezetes pontokat', () => {
    const p = t('y = x^2 - 4');
    const j = new Map([
      [0, jellemzok({
        zerushelyek: [{ x: '-2', ertek: -2 }],
        szelsoertekek: [{ x: '0', y: '-4', x_ertek: 0, y_ertek: -4, tipus: 'minimum' as const }],
        aszimptotak: [{ egyenlet: 'y=1', tipus: 'vizszintes' as const, ertek: 1 }],
      })],
    ]);
    const s = leiras(p, j);
    expect(s).toContain('Grafikon');
    expect(s).toContain('y = x^2 - 4');
    expect(s).toContain('zérushely x = −2');
    expect(s).toContain('minimum (0; −4)');
    expect(s).toContain('aszimptota y=1');
  });

  it('jellemzők nélkül is van leírás', () => {
    expect(leiras(t('y = sin(x)'), new Map())).toContain('y = sin(x)');
  });
});
