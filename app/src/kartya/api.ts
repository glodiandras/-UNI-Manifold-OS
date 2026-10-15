// A kártyák core-hívásai (C23b; docs/C23-TERV.md 7.). A szöveg a vaultból, az állapot a `tanulas.sqlite`-ból jön; az
// értékelést a core számolja (py-fsrs), a felület csak mutat és küld.

import { kerdez } from '../lib/core/api';
import type { Feladat } from '../lib/vezerlo/tipusok';

export interface Kartya {
  azon: string;
  jegyzet: string;
  kerdes: string;
  valasz: string;
  forras: string | null;
  allapot: number;
  uj: boolean;
  esedekes: string | null;
  sor: number;
  esedekes_most?: boolean;
  /** a négy gomb következő intervalluma másodpercben ("1".."4") */
  elorejelzes?: Record<string, number> | null;
}

export interface Osszegzes {
  allapot: 'kesz' | 'nincs';
  esedekes: number;
  uj: number;
  holnap?: number;
  osszes?: number;
}

export interface EsedekesValasz extends Osszegzes {
  ok: boolean;
  kartyak: Kartya[];
}

export interface PakliValasz {
  ok: boolean;
  ut: string;
  kartyak: Kartya[];
  esedekes: number;
  uj: number;
  osszes: number;
  hibak: { sor: number; fajta: string; szoveg: string }[];
}

export interface ValaszValasz {
  ok: boolean;
  allapot: Record<string, unknown>;
  tracker: { ut: string | null; adat: { jegy: number; kartya_id: string; ms?: number } };
}

export interface KartyaApi {
  esedekes(): Promise<EsedekesValasz>;
  jegyzet(ut: string): Promise<PakliValasz>;
  valasz(azon: string, jegy: number, ms: number | null): Promise<ValaszValasz>;
  visszavon(azon: string): Promise<{ ok: boolean; visszavonva: boolean }>;
  allapot(): Promise<Osszegzes>;
  general(ut: string, kijeloles?: string): Promise<Feladat>;
}

export const kartyaApi: KartyaApi = {
  esedekes: () => kerdez<EsedekesValasz>('/api/kartya/esedekes', { idokorlat: 15000 }),
  jegyzet: (ut) => kerdez<PakliValasz>(`/api/kartya/jegyzet?ut=${encodeURIComponent(ut)}`, { idokorlat: 15000 }),
  valasz: (azon, jegy, ms) =>
    kerdez<ValaszValasz>('/api/kartya/valasz', { metodus: 'POST', torzs: { azon, jegy, ms }, idokorlat: 10000 }),
  visszavon: (azon) => kerdez('/api/kartya/visszavon', { metodus: 'POST', torzs: { azon }, idokorlat: 10000 }),
  allapot: () => kerdez<Osszegzes>('/api/kartya/allapot', { idokorlat: 10000 }),
  general: (ut, kijeloles) =>
    kerdez<Feladat>('/api/feladatok', {
      metodus: 'POST',
      torzs: { tipus: 'kartya_general', parameterek: kijeloles ? { ut, kijeloles } : { ut } },
      idokorlat: 15000,
    }),
};
