// A Bases tiszta segédei (C12 6. lépés): az ablakozás, a sormagasság és az értékek magyar megjelenítése.

import { describe, expect, it } from 'vitest';
import { ablak, sorMagassagPx } from '../src/bazis/ablak';
import { datumSzoveg, ertekSzoveg, fajta, osszesitoSzoveg, szamSzoveg } from '../src/bazis/ertek';
import type { Ertek } from '../src/bazis/tipusok';

describe('ablak', () => {
  it('az elején az első elemektől a nézet magassága + a tartalék', () => {
    const a = ablak(0, 300, 30, 2000, 8);
    expect(a).toEqual({ elso: 0, utolso: 18, fent: 0, lent: (2000 - 18) * 30 });
  });

  it('középen a görgetés szerinti sorok, a tartalékkal', () => {
    const a = ablak(3000, 300, 30, 2000, 8);
    expect(a.elso).toBe(100 - 8);
    expect(a.utolso).toBe(110 + 8);
    expect(a.fent).toBe(a.elso * 30);
    expect(a.lent).toBe((2000 - a.utolso) * 30);
  });

  it('a végén nem lóg túl', () => {
    const a = ablak(1_000_000, 300, 30, 2000, 8);
    expect(a.utolso).toBe(2000);
    expect(a.lent).toBe(0);
    expect(a.elso).toBeLessThanOrEqual(2000);
    expect(a.fent + (a.utolso - a.elso) * 30 + a.lent).toBe(2000 * 30);
  });

  it('a fent + látható + lent mindig a teljes magasság', () => {
    for (const g of [0, 1, 29, 30, 31, 777, 59_000, 60_000, 99_999]) {
      const a = ablak(g, 450, 30, 2000, 5);
      expect(a.fent + (a.utolso - a.elso) * 30 + a.lent).toBe(60_000);
    }
  });

  it('üres lista, érvénytelen sormagasság, negatív görgetés', () => {
    expect(ablak(0, 300, 30, 0)).toEqual({ elso: 0, utolso: 0, fent: 0, lent: 0 });
    expect(ablak(0, 300, 0, 10)).toEqual({ elso: 0, utolso: 0, fent: 0, lent: 0 });
    expect(ablak(-50, 300, 30, 100).elso).toBe(0);
  });

  it('kevesebb elem, mint a nézet: mind látszik', () => {
    const a = ablak(0, 900, 30, 5);
    expect(a).toEqual({ elso: 0, utolso: 5, fent: 0, lent: 0 });
  });

  it('2000 elemnél a kirajzolt sorok száma korlátos', () => {
    for (const g of [0, 12_345, 59_000]) {
      const a = ablak(g, 800, 30, 2000);
      expect(a.utolso - a.elso).toBeLessThan(60);
    }
  });
});

describe('sorMagassagPx', () => {
  it('az Obsidian rowHeight-értékei', () => {
    expect(sorMagassagPx(undefined)).toBe(30);
    expect(sorMagassagPx('short')).toBe(30);
    expect(sorMagassagPx('medium')).toBe(44);
    expect(sorMagassagPx('tall')).toBe(62);
    expect(sorMagassagPx('extra tall')).toBe(84);
    expect(sorMagassagPx('Extra-Tall')).toBe(84);
    expect(sorMagassagPx('ismeretlen')).toBe(30);
    expect(sorMagassagPx(3)).toBe(30);
  });
});

describe('értékek megjelenítése', () => {
  it('szám', () => {
    expect(szamSzoveg(4.5)).toBe('4,5');
    expect(szamSzoveg(1234.5678)).toBe('1234,5678');
    expect(szamSzoveg(12_345)).toBe('12345');
    expect(szamSzoveg(0)).toBe('0');
    expect(szamSzoveg(-2)).toBe('-2');
  });

  it('dátum', () => {
    expect(datumSzoveg('2026-09-01', false)).toBe('2026. 09. 01.');
    expect(datumSzoveg('2026-09-01T14:30:00', true)).toMatch(/^2026\. 09\. 01\. 14:30$/);
    expect(datumSzoveg('nem dátum', false)).toBe('nem dátum');
  });

  const esetek: [Ertek, string, string][] = [
    [null, '', 'ures'],
    [true, 'igen', 'logikai'],
    [false, 'nem', 'logikai'],
    [4.5, '4,5', 'szam'],
    ['szöveg', 'szöveg', 'szoveg'],
    [{ t: 'szam', v: 'Infinity' }, '∞', 'egyeb'],
    [{ t: 'szam', v: 'NaN' }, 'NaN', 'egyeb'],
    [{ t: 'lista', e: ['a', 2, null] }, 'a, 2, ', 'lista'],
    [{ t: 'datum', iso: '2026-09-01', ido: false }, '2026. 09. 01.', 'datum'],
    [{ t: 'idotartam', szoveg: '1d', ms: 86400000 }, '1d', 'egyeb'],
    [{ t: 'link', cel: 'Cél', ut: 'A/Cél.md', nev: 'Cél' }, 'Cél', 'link'],
    [{ t: 'cimke', v: '#Book' }, '#Book', 'cimke'],
    [{ t: 'hiba', u: 'rossz' }, 'Hiba: rossz', 'hiba'],
    [{ t: 'kep', ut: 'kep/a.jpg' }, 'kep/a.jpg', 'kep'],
    [{ t: 'ikon', nev: 'plus' }, 'plus', 'egyeb'],
    [{ t: 'objektum', e: { a: 1, b: 'x' } }, 'a: 1, b: x', 'egyeb'],
    [{ t: 'regex', v: '/a/g' }, '/a/g', 'egyeb'],
  ];
  it.each(esetek)('%j → %s (%s)', (e, szoveg, f) => {
    expect(ertekSzoveg(e)).toBe(szoveg);
    expect(osszesitoSzoveg(e)).toBe(szoveg);
    expect(fajta(e)).toBe(f);
  });
});
