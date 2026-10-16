// Közös tesztadatok a Model Manager komponens-teszteihez: szintetikus modellek, feladatleírások és feladatok (valós modell vagy hálózat nélkül).
import type { Halmazok, Kalibracio, Modell, ModellLista, SajatOsszegzes, TesztRiport } from '../src/lib/modellek/tipusok';
import type { Feladat } from '../src/lib/vezerlo/tipusok';

export const modell = (id: string, extra: Partial<Modell> = {}): Modell => ({
  id, repo: `org/${id}`, revizio: 'a'.repeat(40), licenc: 'Apache-2.0', nyelvek: ['*'], szerep: 'szoveg', ajanlott: false, feladat: ['szoveg'],
  meret_gb: 2.5, csucs_gb: 3.1, keret: 'munka', futtato: 'mlx-lm', konvertalas: false, allapot: 'nincs', lemez_bajt: 0, ellenorizve: null,
  kalibracio: [], letoltes: null, teszt: null, ...extra,
});

export const kal = (feladat: string, kalibralt: boolean, extra: Partial<Kalibracio> = {}): Kalibracio => ({
  feladat, pontszam: 0.82, kalibralt, aranyhalmaz_verzio: `${feladat}-v1`, datum: '2026-10-10T10:00:00', mero: 'szallitott', ...extra,
});

export const lista = (modellek: Modell[]): ModellLista => ({
  modellek,
  feladatok: {
    szoveg: { cim: 'Text understanding', leiras: 'Summaries, cards and answers from your notes.', kuszob: 0.4, min_tetel: 20, funkciok: ['kerdezz'] },
    kiegeszites: { cim: 'Text completion', leiras: 'Continues the sentence you are typing.', kuszob: 0.7, min_tetel: 12, funkciok: ['asszisztens'] },
    atirat: { cim: 'Speech to text', leiras: 'Transcribes video audio.', kuszob: null, min_tetel: null, funkciok: ['video'] },
  },
  funkciok: { kerdezz: { cim: 'Ask your workspace', feladatok: ['szoveg'] }, asszisztens: { cim: 'Writing assistant', feladatok: ['kiegeszites'] } },
  keretek: { munka: 5, tavol: 9 },
});

export const feladat = (id: string, tipus: 'modell_letoltes' | 'modell_teszt', extra: Partial<Feladat> = {}): Feladat => ({
  id, tipus, cim: tipus, osszegzes: '', figyelmeztetes: [], lepesek: [], kulturalt_stop: true, allapot: 'fut', letrehozva: '2026-10-16T10:00:00',
  indult: '2026-10-16T10:00:01', vegzett: null, szazalek: 0, lepes_i: 0, kilepes: null, hiba: null, leallitas_kerve: false, forras: '2.0',
  vault_ir: false, modell: false, ...extra,
});

export const sajatOsszegzes = (extra: Partial<SajatOsszegzes> = {}): SajatOsszegzes => ({
  feladat: 'kiegeszites', van: false, allapot: null, tetelszam: 0, nyelv: null, min_tetel: 2, valasztva: false, tetelek: [], ...extra,
});

export const halmazok = (extra: Partial<Halmazok> = {}): Halmazok => ({
  szallitott: [{ feladat: 'szoveg', router_feladat: 'szoveg', nyelv: 'en', licenc: 'CC0-1.0', verzio: 'szoveg-v1', allapot: 'jovahagyott', tetelszam: 24, min_tetel: 20, kalibralhato: true }],
  sajat: { kiegeszites: sajatOsszegzes() },
  tamogatott: ['kiegeszites'],
  ...extra,
});

export const riport = (extra: Partial<TesztRiport> = {}): TesztRiport => ({
  modell: 'alap', feladat: 'szoveg', halmaz: 'szallitott', datum: '2026-10-16T11:00:00', allapot: 'kesz', jel: 'kalibralt', okok: [], kuszob: 0.4, min_tetel: 20, rogzitve: true,
  ertekeles: { pontszam: 0.82, n: 24, tetelszam: 24, teljes: true, ervenyes: true, aranyhalmaz_verzio: 'szoveg-v1', mero: 'szallitott', ervenyesseg: { levagott: 0, hurok: 0, ures: 0, hiba: 0, hianyzo: 0 } },
  ...extra,
});

export const json = (d: unknown, kod = 200) => new Response(JSON.stringify(d), { status: kod, headers: { 'Content-Type': 'application/json' } });
