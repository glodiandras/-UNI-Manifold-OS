// A „Ma” oldal dátum- és időszövegei (C15): relatív napok, időtartományok, éjfél-számítás, a naptáradat kora.

import { describe, expect, it } from 'vitest';
import { ejfelig, folyamatban, idoSzoveg, napKulcs, napokSzoveg, napRovid, napSzoveg, szinkronSzoveg } from '../src/ma/datum';

describe('napKulcs és ejfelig', () => {
  it('a helyi nap kulcsa kitöltött hónappal és nappal', () => {
    expect(napKulcs(new Date(2026, 0, 3, 23, 59))).toBe('2026-01-03');
    expect(napKulcs(new Date(2026, 9, 2, 0, 0))).toBe('2026-10-02');
  });

  it('az éjfélig hátralévő idő; az éjfél előtti másodperc is legalább 1 s', () => {
    expect(ejfelig(new Date(2026, 9, 2, 23, 0, 0, 0))).toBe(3_600_000);
    expect(ejfelig(new Date(2026, 9, 2, 0, 0, 0, 0))).toBe(86_400_000);
    expect(ejfelig(new Date(2026, 9, 2, 23, 59, 59, 999))).toBe(1000);
  });

  it('hónap- és évhatáron is a következő éjfél', () => {
    expect(ejfelig(new Date(2026, 11, 31, 22, 0))).toBe(2 * 3_600_000);
  });
});

describe('napokSzoveg', () => {
  it.each([
    [0, 'ma'],
    [1, 'holnap'],
    [2, 'holnapután'],
    [3, '3 nap múlva'],
    [11, '11 nap múlva'],
    [-1, 'tegnap'],
    [-2, '2 napja'],
  ])('%i → %s', (n, szoveg) => {
    expect(napokSzoveg(n)).toBe(szoveg);
  });
});

describe('napSzoveg és napRovid', () => {
  it('magyar hónapnévvel, az időzónától függetlenül az `ÉÉÉÉ-HH-NN` kulcsból', () => {
    expect(napSzoveg('2026-10-05')).toBe('2026. október 5.');
    expect(napSzoveg('2026-01-31')).toBe('2026. január 31.');
    expect(napRovid('2026-10-05')).toBe('okt. 5.');
  });
});

describe('idoSzoveg', () => {
  it('tartomány, kezdet, egész nap', () => {
    expect(idoSzoveg({ egesznap: false, kezd_ora: '08:55', veg_ora: '09:40' })).toBe('08:55–09:40');
    expect(idoSzoveg({ egesznap: false, kezd_ora: '08:55', veg_ora: '08:55' })).toBe('08:55');
    expect(idoSzoveg({ egesznap: false, kezd_ora: '08:55', veg_ora: '' })).toBe('08:55');
    expect(idoSzoveg({ egesznap: true, kezd_ora: '', veg_ora: '' })).toBe('egész nap');
    expect(idoSzoveg({ egesznap: false, kezd_ora: '', veg_ora: '' })).toBe('egész nap');
  });
});

describe('szinkronSzoveg', () => {
  it('a szinkron napja magyarul; ismeretlen kornál külön mondat', () => {
    expect(szinkronSzoveg('2026-09-27T22:00:29+02:00')).toBe('Az itt látott naptár a 2026. szeptember 27-i állapot.');
    expect(szinkronSzoveg(null)).toBe('A naptáradat kora ismeretlen.');
  });
});

describe('folyamatban', () => {
  const e = { egesznap: false, kezd_ora: '08:55', veg_ora: '09:40' };
  it('a kezdettől a végig (a vég már nem), egész napos és idő nélküli esemény soha', () => {
    expect(folyamatban(e, new Date(2026, 9, 2, 8, 54))).toBe(false);
    expect(folyamatban(e, new Date(2026, 9, 2, 8, 55))).toBe(true);
    expect(folyamatban(e, new Date(2026, 9, 2, 9, 39))).toBe(true);
    expect(folyamatban(e, new Date(2026, 9, 2, 9, 40))).toBe(false);
    expect(folyamatban({ egesznap: true, kezd_ora: '', veg_ora: '' }, new Date(2026, 9, 2, 9, 0))).toBe(false);
    expect(folyamatban({ egesznap: false, kezd_ora: '08:55', veg_ora: '' }, new Date(2026, 9, 2, 9, 0))).toBe(false);
  });
});
