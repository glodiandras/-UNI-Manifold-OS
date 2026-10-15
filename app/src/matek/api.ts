// A matek-motor core-hívásai (C24b): a levezetés-ellenőrzés (szinkron, a margójelhez) és a „Megoldás” feladat indítása.

import { kerdez } from '../lib/core/api';
import type { Feladat } from '../lib/vezerlo/tipusok';
import type { LevezetesValasz } from './margo';

export interface MegoldasParameterek {
  ut: string;
  tol: number;
  ig: number;
  /** a `tol`–`ig` sorok szövege, változatlanul (a lépés ezzel ellenőrzi, hogy a jegyzet nem változott) */
  feladat: string;
}

export const matekApi = {
  levezetes: (sorok: { sor: number; szoveg: string }[], vegeredmeny = false) =>
    kerdez<LevezetesValasz & { ok: boolean }>('/api/matek/levezetes', {
      metodus: 'POST',
      torzs: { sorok, vegeredmeny },
      idokorlat: 100000,
    }),
  megoldas: (p: MegoldasParameterek) =>
    kerdez<Feladat>('/api/feladatok', { metodus: 'POST', torzs: { tipus: 'matek_megoldas', parameterek: p }, idokorlat: 15000 }),
};
