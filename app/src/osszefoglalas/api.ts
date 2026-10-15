// Az összefoglaló core-hívásai (C26b; docs/C26-TERV.md 7.). Az olvasó végpontok csak olvasnak; a készítés a `osszefoglalas`
// feladat (a gépi-írás szolgáltatáson át ír, visszavonható), a külső AI válaszát a felhasználó illeszti be (49. döntés).

import { kerdez } from '../lib/core/api';
import type { Feladat } from '../lib/vezerlo/tipusok';

export interface OsszAllitas {
  id: string;
  szoveg: string;
  idezet: string;
  /** a forrás vault-relatív útja `.md` nélkül (videónál a média kiterjesztéssel) */
  cel: string;
  /** `^blokk`, a fejezet címe vagy `t=<mp>` */
  alcel: string | null;
  felirat: string;
  sodrodott: boolean;
  horgony_hianyzik: boolean;
  forras_hianyzik: boolean;
}

export interface OsszJegyzet {
  ok: boolean;
  ut: string;
  szint: 'jegyzet' | 'mappa' | 'video' | 'kontextus' | null;
  cim: string | null;
  azon: string | null;
  modell: string | null;
  keszult: string | null;
  forrasok: string[];
  forras_ut: string | null;
  allitasok: OsszAllitas[];
  hibak: { sor: number; fajta: string; szoveg: string }[];
  sodrodott: string[];
  horgony_hianyzik: string[];
  forras_hianyzik: string[];
}

export interface MappaTerv {
  ok: boolean;
  jegyzetek: string[];
  van: string[];
  hianyzik: string[];
  keszul: string[];
  /** a gépi írások száma, a mappa-szinttel együtt */
  tetelek: number;
}

export interface KontextusValasz {
  ok: boolean;
  szoveg: string;
  azonositok: Record<string, string>;
  benne: string[];
  csonkolt: string[];
  kihagyott: { azon: string; ut: string; ok: string }[];
  karakter: number;
}

export interface KulsoValasz {
  ok: boolean;
  allitasok: number;
  elvetett: { allitas: string; ok: string; reszlet: string }[];
  statisztika: Record<string, unknown>;
  /** az `## Állítások` blokk — a felhasználó kézzel illeszti a szerkesztőbe */
  torzs: string;
  jegyzet: string;
}

export interface KeszitParam {
  szint: 'jegyzet' | 'mappa' | 'video';
  ut: string;
  kiegeszit?: boolean;
}

export interface OsszefoglalasApi {
  jegyzet(ut: string): Promise<OsszJegyzet>;
  mappaTerv(ut: string, kiegeszit?: boolean): Promise<MappaTerv>;
  kontextus(utak: string[], kerdes?: string): Promise<KontextusValasz>;
  valasz(utak: string[], valasz: string): Promise<KulsoValasz>;
  keszit(p: KeszitParam): Promise<Feladat>;
}

export const osszefoglalasApi: OsszefoglalasApi = {
  jegyzet: (ut) => kerdez<OsszJegyzet>(`/api/osszefoglalas/jegyzet?ut=${encodeURIComponent(ut)}`, { idokorlat: 15000 }),
  mappaTerv: (ut, kiegeszit = true) =>
    kerdez<MappaTerv>(`/api/osszefoglalas/mappa-terv?ut=${encodeURIComponent(ut)}${kiegeszit ? '' : '&kiegeszit=0'}`, { idokorlat: 15000 }),
  kontextus: (utak, kerdes) =>
    kerdez<KontextusValasz>('/api/osszefoglalas/kontextus', { metodus: 'POST', torzs: kerdes ? { utak, kerdes } : { utak }, idokorlat: 20000 }),
  valasz: (utak, valasz) =>
    kerdez<KulsoValasz>('/api/osszefoglalas/valasz', { metodus: 'POST', torzs: { utak, valasz }, idokorlat: 30000 }),
  keszit: (p) =>
    kerdez<Feladat>('/api/feladatok', {
      metodus: 'POST',
      torzs: { tipus: 'osszefoglalas', parameterek: { szint: p.szint, ut: p.ut, ...(p.szint === 'mappa' ? { kiegeszit: p.kiegeszit ?? true } : {}) } },
      idokorlat: 15000,
    }),
};
