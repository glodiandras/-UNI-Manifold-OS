// A naptár és az emlékeztetők (C29) core-hívásai. A javaslat jóváhagyása az egyetlen út, amely a naptárba ír,
// ezért csak kifejezett felhasználói kattintásból hívható.

import { kerdez } from '../core/api';
import type { NaptarAllapotValasz } from './tipusok';

export const naptarApi = {
  /** `frissit`: a core előbb a segédtől kérdezi az engedély aktuális állapotát. */
  allapot: (frissit = false) => kerdez<NaptarAllapotValasz>(`/api/naptar/allapot${frissit ? '?frissit=1' : ''}`, { idokorlat: 15000 }),
  szinkron: () => kerdez<NaptarAllapotValasz>('/api/naptar/szinkron', { metodus: 'POST', torzs: {}, idokorlat: 90000 }),
  kategoria: (azon: string, kategoria: string) =>
    kerdez<{ ok: boolean }>('/api/naptar/kategoria', { metodus: 'POST', torzs: { azon, kategoria }, idokorlat: 10000 }),
  jovahagy: (id: number) => kerdez<{ ok: boolean }>(`/api/naptar/javaslat/${id}/jovahagy`, { metodus: 'POST', torzs: {}, idokorlat: 30000 }),
  elvet: (id: number) => kerdez<{ ok: boolean }>(`/api/naptar/javaslat/${id}/elvet`, { metodus: 'POST', torzs: {}, idokorlat: 10000 }),
  utkozesLatva: (azonok?: number[]) =>
    kerdez<{ ok: boolean; db: number }>('/api/emlekezteto/utkozes/latva', { metodus: 'POST', torzs: azonok ? { azonok } : {}, idokorlat: 10000 }),
};
