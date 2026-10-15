// A naptár és az emlékeztetők (C29) tiszta megjelenítési logikája: engedély-szövegek, a Ma oldal jelzése, időszövegek,
// az ütközés- és változás-értesítések szövegei, a javaslat ideje.

import { describe, expect, it } from 'vitest';
import { javaslatIdo, napKulonbseg } from '../src/ma/datum';
import {
  engedelySzoveg,
  mikorSzoveg,
  naptarJelzes,
  rovidit,
  szinkronEredmeny,
  utkozesErtesites,
  utkozesFajtaSzoveg,
  valtozasErtesites,
  valtozasSor,
} from '../src/lib/naptar/megjelenites';

describe('engedély-szövegek', () => {
  it('minden állapotnak emberi szövege van', () => {
    expect(engedelySzoveg('engedelyezve')).toBe('engedélyezve');
    expect(engedelySzoveg('nincs_dontes')).toContain('kérhető');
    expect(engedelySzoveg('megtagadva')).toBe('megtagadva');
    expect(engedelySzoveg('korlatozott')).toContain('teljes hozzáférés');
    expect(engedelySzoveg('csak_iras')).toContain('olvasáshoz');
    expect(engedelySzoveg('ismeretlen')).toBe('ismeretlen');
    expect(engedelySzoveg(null)).toBe('még nem ismert');
  });
});

describe('a Ma oldal naptár-jelzése', () => {
  it('nincs döntés: a gomb kérhető', () => {
    const j = naptarJelzes({ seged: true, esemeny_engedely: 'nincs_dontes', hiba: null });
    expect(j?.kerheto).toBe(true);
    expect(j?.szoveg).toContain('nem kapott hozzáférést');
  });

  it('megtagadva: csak a Rendszerbeállítások teendője, gomb nélkül', () => {
    const j = naptarJelzes({ seged: true, esemeny_engedely: 'megtagadva', hiba: null });
    expect(j?.kerheto).toBe(false);
    expect(j?.szoveg).toContain('Rendszerbeállítások › Adatvédelem és biztonság › Naptárak');
  });

  it('korlátozott és csak írás: a teljes hozzáférés kell', () => {
    expect(naptarJelzes({ seged: true, esemeny_engedely: 'korlatozott' })?.szoveg).toContain('korlátozott');
    expect(naptarJelzes({ seged: true, esemeny_engedely: 'csak_iras' })?.szoveg).toContain('írási');
  });

  it('nincs segéd: a core hibaüzenetével', () => {
    const j = naptarJelzes({ seged: false, esemeny_engedely: null, hiba: 'nincs naptár-segéd: a Manifold.app újrafordítása kell' });
    expect(j?.kerheto).toBe(false);
    expect(j?.szoveg).toContain('újrafordítása');
  });

  it('engedélyezve hiba nélkül és a még nem próbált szolgáltatás: nincs jelzés', () => {
    expect(naptarJelzes({ seged: true, esemeny_engedely: 'engedelyezve', hiba: null })).toBeNull();
    expect(naptarJelzes({ seged: null, esemeny_engedely: null, hiba: null })).toBeNull();
    expect(naptarJelzes({ seged: null })).toBeNull();
    expect(naptarJelzes(undefined)).toBeNull();
  });

  it('engedélyezve, de a szinkron hibát jelzett: a hiba látszik', () => {
    expect(naptarJelzes({ seged: true, esemeny_engedely: 'engedelyezve', hiba: 'időtúllépés' })?.szoveg).toContain('időtúllépés');
  });

  it('a szakasz saját hibája (`{hiba}`) is jelzés, gomb nélkül', () => {
    const j = naptarJelzes({ hiba: 'a szolgáltatás nem érhető el' });
    expect(j?.kerheto).toBe(false);
    expect(j?.szoveg).toContain('a szolgáltatás nem érhető el');
  });
});

describe('időszövegek', () => {
  it('a mai időpont „ma”, a korábbi nap rövid dátum; az ISO saját órája számít', () => {
    expect(mikorSzoveg('2026-10-03T14:05:12+02:00', '2026-10-03')).toBe('ma 14:05');
    expect(mikorSzoveg('2026-10-02T09:30:00+02:00', '2026-10-03')).toBe('okt. 2. 09:30');
    expect(mikorSzoveg(null, '2026-10-03')).toBe('még nem');
  });

  it('a javaslat ideje: relatív nap, rövid dátum, időablak, hossz', () => {
    const j = { nap: '2026-10-04', kezd: '2026-10-04T16:00:00+02:00', veg: '2026-10-04T17:00:00+02:00', perc: 60 };
    expect(javaslatIdo(j, '2026-10-03')).toBe('holnap · okt. 4. · 16:00–17:00 · 60 perc');
    expect(javaslatIdo({ ...j, perc: null }, '2026-10-04')).toBe('ma · okt. 4. · 16:00–17:00');
    expect(napKulonbseg('2026-11-01', '2026-10-31')).toBe(1);
    expect(napKulonbseg('2026-03-29', '2026-03-28')).toBe(1); // az óraátállítás napja is egy nap
  });
});

describe('a szinkron eredménye', () => {
  const alap = { seged: true as boolean | null, hiba: null, utolso_szinkron: null };
  it('hiba, nincs segéd, olvasott események, nincs engedély', () => {
    expect(szinkronEredmeny({ ...alap, hiba: 'időtúllépés', naptar: null })).toBe('hiba: időtúllépés');
    expect(szinkronEredmeny({ ...alap, seged: false, naptar: null })).toBe('nincs naptár-segéd');
    expect(szinkronEredmeny({ ...alap, naptar: { allapot: 'engedelyezve', uj: 2, valtozott: 1, torolt: 0, osszes: 48, valtozasok: [], blokkok: 3 } })).toBe(
      '48 esemény (2 új, 1 változott)',
    );
    expect(szinkronEredmeny({ ...alap, naptar: { allapot: 'engedelyezve', uj: 0, valtozott: 0, torolt: 0, osszes: 48, valtozasok: [], blokkok: 3 } })).toBe(
      '48 esemény, nincs változás',
    );
    expect(szinkronEredmeny({ ...alap, naptar: { allapot: 'megtagadva', uj: 0, valtozott: 0, torolt: 0, osszes: 0, valtozasok: [], blokkok: null } })).toBe(
      'nem olvasható (megtagadva)',
    );
    expect(szinkronEredmeny({ ...alap, naptar: null })).toBe('még nem futott');
    expect(szinkronEredmeny({ ...alap, naptar: null, utolso_szinkron: { vege: 'x', allapot: 'engedelyezve', utolso_sikeres: 'x', uzenet: null } })).toBe('rendben');
  });
});

describe('értesítés-szövegek', () => {
  it('az ütközés: a jegyzet nyert, a fajta szerint rövidítve', () => {
    expect(utkozesErtesites({ fajta: 'kesz', szoveg: 'Beadni a házit', reszlet: 'A jegyzetben nyitott, az Emlékeztetőben kész: a jegyzet nyert.' })).toEqual({
      cim: 'A jegyzet nyert: Beadni a házit',
      szoveg: 'ellentétes pipálás — A jegyzetben nyitott, az Emlékeztetőben kész: a jegyzet nyert.',
    });
    expect(utkozesErtesites({ fajta: 'szerkesztve', szoveg: 'Dolgozat', reszlet: null })).toEqual({ cim: 'A jegyzet nyert: Dolgozat', szoveg: 'az emlékeztetőt átírták' });
    expect(utkozesErtesites({ fajta: 'sor_nincs', szoveg: null, reszlet: null }).cim).toBe('A jegyzet nyert');
    const t = utkozesErtesites({ fajta: 'torles_visszatartva', szoveg: null, reszlet: '12 tükör törlődne egy körben: a törlés visszatartva.' });
    expect(t.cim).toBe('Emlékeztető-törlés visszatartva');
  });

  it('a hosszú szöveg rövidül', () => {
    expect(rovidit('a'.repeat(100), 20)).toHaveLength(20);
    expect(rovidit('  két   szó ', 20)).toBe('két szó');
    expect(utkozesErtesites({ fajta: 'kesz', szoveg: 'x'.repeat(200), reszlet: null }).cim.length).toBeLessThan(90);
  });

  it('a naptár-változás: csak az átnevezés és az eltűnés értesít', () => {
    expect(valtozasErtesites({ fajta: 'atnevezve', regi: 'Suli', uj: 'Órarend' })).toEqual({ cim: 'A(z) „Órarend” naptár átnevezve', szoveg: 'Régi neve: „Suli”.' });
    expect(valtozasErtesites({ fajta: 'eltunt', regi: 'Edzés', uj: null })).toEqual({ cim: 'A(z) „Edzés” naptár eltűnt', szoveg: '' });
    expect(valtozasErtesites({ fajta: 'szin', regi: '#fff', uj: '#000' })).toBeNull();
    expect(valtozasErtesites({ fajta: 'uj', regi: null, uj: 'Új' })).toBeNull();
  });

  it('a változás-lista sorai és az ütközés-fajták', () => {
    expect(valtozasSor({ azon: 'a', fajta: 'atnevezve', regi: 'A', uj: 'B' })).toBe('átnevezve: „A” → „B”');
    expect(valtozasSor({ azon: 'a', fajta: 'eltunt', regi: 'A', uj: null })).toBe('eltűnt: „A”');
    expect(valtozasSor({ azon: 'a', fajta: 'szin', regi: '#1', uj: '#2' }, 'Órarend')).toBe('„Órarend” színe megváltozott');
    expect(utkozesFajtaSzoveg('kesz')).toContain('a jegyzet nyert');
    expect(utkozesFajtaSzoveg('valami')).toBe('valami');
  });
});
