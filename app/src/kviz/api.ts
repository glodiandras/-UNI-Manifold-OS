// A kvíz core-hívásai (C22a; a `general` a C22b). A pontszámot a core számolja; a kulcsot a core a válasz rögzítése előtt nem adja ki.
// A kitöltés tokenje (A3-03): a `kviz` hívás adja, a `megoldas` a válaszokat rögzíti benne, a `kitoltes` abból pontoz.

import { kerdez } from '../lib/core/api';
import type { Feladat } from '../lib/vezerlo/tipusok';
import type { KitoltesValasz, KitoltesValaszEgy, KvizMod, KvizValasz, Megoldas } from './tipusok';

export interface KvizApi {
  kviz(ut: string): Promise<KvizValasz>;
  megoldas(ut: string, token: string, valasz: KitoltesValaszEgy): Promise<Megoldas>;
  kitoltes(ut: string, token: string, kulcs: string, mod: KvizMod, idoMs: number): Promise<KitoltesValasz>;
  jelol(ut: string, token: string, kerdes: string, hibas: boolean): Promise<{ ok: boolean; jelolesek: string[] }>;
}

export const kvizApi: KvizApi = {
  kviz: (ut) => kerdez<KvizValasz>(`/api/kviz/kviz?ut=${encodeURIComponent(ut)}`, { idokorlat: 10000 }),
  megoldas: (ut, token, v) =>
    kerdez<Megoldas>('/api/kviz/megoldas', {
      metodus: 'POST',
      torzs: { ut, token, kerdes: v.kerdes, valasz: v.valasz, tipp: v.tipp, ms: v.ms },
      idokorlat: 10000,
    }),
  kitoltes: (ut, token, kulcs, mod, idoMs) =>
    kerdez<KitoltesValasz>('/api/kviz/kitoltes', { metodus: 'POST', torzs: { ut, token, kulcs, mod, ido_ms: idoMs }, idokorlat: 15000 }),
  jelol: (ut, token, kerdes, hibas) => kerdez('/api/kviz/jelol', { metodus: 'POST', torzs: { ut, token, kerdes, hibas }, idokorlat: 10000 }),
};

/** C22b: a `kviz_general` feladat indítása a jegyzetre (a modell + a kapuk a feladatsoron, gépi írással). */
export const kvizGeneral = (ut: string): Promise<Feladat> =>
  kerdez<Feladat>('/api/feladatok', { metodus: 'POST', torzs: { tipus: 'kviz_general', parameterek: { ut } }, idokorlat: 15000 });
