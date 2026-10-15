// A ```plot blokk formátuma (C35a): a Python-oldal (`modulok/grafikon/formatum.py`) tükre. A közös vektorok
// (`modulok/grafikon/vektorok/forras.json`) rögzítik, hogy ugyanabból a szövegből ugyanaz az ábra, ugyanaz a hibalista
// és ugyanaz a kanonikus alak jön; az ismeretlen sor megmarad (kézi szerkesztés), hibát nem okoz.

import { describe, expect, it } from 'vitest';
import {
  MAX_BLOKK,
  MAX_ELEM,
  MAX_SOR,
  elemez,
  szerializal,
  type Abra,
} from '../src/szerkeszto/renderelok/plot/forras';
import { dokumentacio, vektor } from './plot-segedek';

interface Tetel {
  szoveg: string;
  abra: Abra;
  kanonikus: string;
  forras?: string;
}
const V = vektor<{ tetelek: Tetel[] }>('forras');

describe('paritás a Python-oldallal (közös vektorok)', () => {
  it('a vektor elegendő, sokféle blokkot tartalmaz', () => {
    expect(V.tetelek.length).toBeGreaterThanOrEqual(55);
  });

  it('minden blokk ugyanazt az ábrát és kanonikus alakot adja', () => {
    for (const t of V.tetelek) {
      const a = elemez(t.szoveg);
      expect(a, JSON.stringify(t.szoveg).slice(0, 80)).toEqual(t.abra);
      expect(szerializal(a), JSON.stringify(t.szoveg).slice(0, 80)).toBe(t.kanonikus);
    }
  });

  it('a kanonikus alak fixpont, és a körút azonos ábrát ad', () => {
    for (const t of V.tetelek) {
      const a = elemez(t.kanonikus);
      expect(szerializal(a)).toBe(t.kanonikus);
      expect({ ...a, hibak: [] }).toEqual({ ...elemez(t.szoveg), hibak: [] });
    }
  });
});

describe('az elemek', () => {
  it('függvény, címke, sorvégi megjegyzés, `#` a címkében', () => {
    const a = elemez('y = x^2 + 2  "f \\"x\\""   # megjegyzés\ny = x "a # b"');
    expect(a.elemek).toEqual([
      { fajta: 'fuggveny', kifejezes: 'x^2 + 2', cimke: 'f "x"' },
      { fajta: 'fuggveny', kifejezes: 'x', cimke: 'a # b' },
    ]);
  });

  it('paraméteres görbe a paraméter betűjével', () => {
    const a = elemez('x = cos(s), y = sin(s), s in [0, 2*pi] "kör"');
    expect(a.elemek).toEqual([
      { fajta: 'parameteres', x: 'cos(s)', y: 'sin(s)', t: 's', tartomany: ['0', '2*pi'], cimke: 'kör' },
    ]);
  });

  it('egyenlőtlenség, pont, tartomány; a Unicode relációk és mínusz normalizálódnak', () => {
    const a = elemez('x in [-4, 4]\ny in [-2, 10]\ny ≤ x^2\ny ≥ 1\npont (pi/2, 1) "csúcs"\ny = x − 1');
    expect(a.x_tartomany).toEqual(['-4', '4']);
    expect(a.y_tartomany).toEqual(['-2', '10']);
    expect(a.elemek.map((e) => e.fajta)).toEqual(['egyenlotlenseg', 'egyenlotlenseg', 'pont', 'fuggveny']);
    expect(a.elemek[0]).toMatchObject({ relacio: '<=', kifejezes: 'x^2' });
    expect(a.elemek[3]).toMatchObject({ kifejezes: 'x - 1' });
  });

  it('az ismeretlen sor megmarad, hibát jelez, nem dob', () => {
    const a = elemez('valami ismeretlen\ny = x\nx = 3');
    expect(a.elemek.map((e) => e.fajta)).toEqual(['ismeretlen', 'fuggveny', 'ismeretlen']);
    expect(a.hibak).toEqual([
      [1, 'ismeretlen vagy hibás sor'],
      [3, 'ismeretlen vagy hibás sor'],
    ]);
  });

  it('a tartomány legfeljebb egyszer; a második ismeretlen', () => {
    const a = elemez('x in [-4, 4]\nx in [-1, 1]');
    expect(a.x_tartomany).toEqual(['-4', '4']);
    expect(a.hibak).toEqual([[2, 'a tartomány már meg van adva']]);
  });

  it('a sortörés a Pythonéval azonos: CRLF, CR, Unicode-sorelválasztó', () => {
    expect(elemez('y = x\r\ny = 2x\r\n').elemek).toHaveLength(2);
    expect(elemez('y = x\ry = 2x').elemek).toHaveLength(2);
    expect(elemez('y = x y = 2x').elemek).toHaveLength(2);
    expect(elemez('y = x\u000by = 2x').elemek).toHaveLength(2);
  });
});

describe('plafonok', () => {
  it('túl hosszú sor ismeretlen', () => {
    const a = elemez('y = x' + '+x'.repeat(1100));
    expect(a.elemek).toHaveLength(1);
    expect(a.elemek[0].fajta).toBe('ismeretlen');
    expect(a.hibak[0][1]).toContain(String(MAX_SOR));
  });

  it(`legfeljebb ${MAX_ELEM} rajzelem, a többi ismeretlen`, () => {
    const a = elemez(Array.from({ length: 70 }, (_, k) => `y = x + ${k}`).join('\n'));
    expect(a.elemek.filter((e) => e.fajta === 'fuggveny')).toHaveLength(MAX_ELEM);
    expect(a.elemek.filter((e) => e.fajta === 'ismeretlen')).toHaveLength(6);
  });

  it('a nagy blokkot nem elemzi', () => {
    const a = elemez('y = x\n'.repeat(Math.ceil(MAX_BLOKK / 6) + 10));
    expect(a).toEqual({ x_tartomany: null, y_tartomany: null, elemek: [], hibak: [[0, 'túl nagy blokk']] });
  });
});

describe('dokumentáció', () => {
  it('a docs/PLOT-FORMATUM.md minden ```plot példája hiba nélkül elemződik', () => {
    const blokkok = [...dokumentacio.matchAll(/^`{3,}plot\n([\s\S]*?)^`{3,}$/gm)].map((m) => m[1]);
    expect(blokkok.length).toBeGreaterThanOrEqual(1);
    for (const b of blokkok) expect(elemez(b).hibak, b).toEqual([]);
  });
});
