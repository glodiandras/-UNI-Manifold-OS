// Közös adat a dolgozat-oldal tesztjeihez (C28a): a core `GET /api/felkeszultseg*` válaszának alakja.

import type { DolgozatSor, Ertekeles, Kalibracio, ListaValasz, Reszlet, Tema } from '../src/dolgozat/tipusok';

export const FELK = 'X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-07 - Matematika.md';
export const T1 = 'M06 - Exponenciális/Elmélet/01 - Hatvány.md';
export const T2 = 'M06 - Exponenciális/Elmélet/02 - Gyökvonás.md';
export const T3 = 'M06 - Exponenciális/Elmélet/03 - Logaritmus.md';

export function sor(felul: Partial<DolgozatSor> = {}): DolgozatSor {
  return {
    azon: 'd1|2026-10-07T10:00:00+02:00', cim: 'Matek témazáró', nap: '2026-10-07', ora: '10:00', napok: 4, tantargy: 'Matematika',
    lezart: false, jegyzet: FELK, kotes: { fok: 'biztos', ok: 'azonos nap és tantárgy (Matematika)' }, szam: null, kilatas: null,
    szint: 'nincs_adat', lefedettseg: { van: 0, osszes: 3 }, gyenge_db: 0, nincs_adat_db: 3, esedekes_kartya: 0, uj_kartya: 0, temak_db: 3,
    ...felul,
  };
}

export function lista(dolgozatok: DolgozatSor[] = [sor()], felul: Partial<ListaValasz> = {}): ListaValasz {
  return {
    nap: '2026-10-03', dolgozatok, naptar: { utolso_szinkron: '2026-10-03T06:00:00+02:00', regi: false },
    adatok: {}, figyelmeztetesek: [], ...felul,
  };
}

export function tema(ut: string, nev: string, szam: number | null, felul: Partial<Tema> = {}): Tema {
  return {
    ut, nev, szam, kilatas: szam === null ? null : Math.max(0, szam - 0.1), bizonyitek: szam === null ? 0 : 0.7,
    ok: szam === null ? 'nincs_mert_tudas' : null, szint: szam === null ? 'nincs_adat' : szam >= 0.8 ? 'jo' : szam >= 0.6 ? 'kozepes' : 'gyenge',
    osszetevok: [
      { nev: 'kartya', ertek: szam, bizalom: szam === null ? 0 : 1, suly: 0.4, adat: { db: szam === null ? 0 : 6, uj: 1 } },
      { nev: 'kviz', ertek: null, bizalom: 0, suly: 0.35, adat: { db: 0, kerdes: 0 } },
      { nev: 'frissesseg', ertek: szam === null ? null : 0.8, bizalom: szam === null ? 0 : 1, suly: 0.1, adat: { nap: szam === null ? null : 3 } },
      { nev: 'ido', ertek: 0.5, bizalom: 1, suly: 0.15, adat: { perc: 30 } },
    ],
    aliasok: [], tanult_perc: 30, utolso_tanulas: szam === null ? null : '2026-10-01',
    kartya: { db: szam === null ? 0 : 6, uj: szam === null ? 0 : 1, esedekes: szam === null ? 0 : 2, gyenge: [] }, kviz: { db: 0 },
    ...felul,
  };
}

export function reszlet(felul: Partial<Reszlet> = {}): Reszlet {
  return {
    ...sor(), temak: [tema(T1, '01 - Hatvány', null), tema(T2, '02 - Gyökvonás', null), tema(T3, '03 - Logaritmus', null)],
    forrasok: [{ ut: 'M07 - Tankönyvek/11 - Matematika.pdf', tipus: 'pdf', oldalak: '18–19, 28' }], onmaga: false,
    gyenge_pontok: { temak: [], nincs_adat: [{ ut: T1, nev: '01 - Hatvány' }], kartyak: [] },
    terv: {
      uzenet: null,
      napok: [
        { nap: '2026-10-03', perc: 45, kartya_esedekes: 0, naptar: [], javaslat: null, szeletek: [{ tema_ut: T1, tema: '01 - Hatvány', perc: 45, ok: 'nincs adat' }] },
      ],
    },
    keplet: { suly: { kartya: 0.4, kviz: 0.35, frissesseg: 0.1, ido: 0.15 }, min_bizonyitek: 0.15, cel: 0.85, gyenge: 0.6, jo: 0.8, kalibralt: false, leiras: 'A téma számát a négy összetevő súlyozott átlaga adja.' },
    naptar: { utolso_szinkron: '2026-10-03T06:00:00+02:00', regi: false },
    adatok: {
      kartya: { van: false, ok: 'még nincs kártya: a tanulas.sqlite nem létezik' },
      kviz: { van: false, ok: 'nincs kvíz-adatforrás' },
      tracker: { van: false, ok: 'még nincs tracker-adat' },
    },
    figyelmeztetesek: [],
    ...felul,
  };
}

export function json(adat: unknown, status = 200): Response {
  return new Response(JSON.stringify(adat), { status, headers: { 'Content-Type': 'application/json' } });
}

/** `POST /api/felkeszultseg/ertekeles` válasza (C28b). */
export function ertekeles(felul: Partial<Ertekeles> = {}): Ertekeles {
  return {
    ok: true, allapot: 'kesz', szoveg: 'A felkészültséged most 62%, a kilátás 55%. A leggyengébb a Gyökvonás.', modell: 'qwen35_9b', proba: false,
    kalibralt: true, probalkozas: 1, tiltott_szamok: [], kulcs: 'kulcs-1', uzenet: null, ...felul,
  };
}

/** `GET /api/felkeszultseg/kalibracio` válasza (C28b): a mai állapot — egyetlen kalibrációs pont sincs. */
export function kalibracio(felul: Partial<Kalibracio> = {}): Kalibracio {
  return {
    allapot: 'nem_teljesitheto', ok: 'A kalibráció még nem teljesíthető: 0 / 8 dolgozatra van egyszerre számszerű eredmény és mért tudás.',
    pontok: 0, kell: 8, lezart: 9, eredmennyel: 9, kalibralt: false, elotte_nap: 3, kis_minta: true, kihagyott: [],
    alap: { n: 0, rmse: null, mae: null, torzitas: null }, loo: { n: 0, rmse: null, mae: null, torzitas: null }, pontok_reszlet: [], ...felul,
  };
}
