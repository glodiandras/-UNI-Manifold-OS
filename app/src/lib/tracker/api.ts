// A tracker (C27) core-hívásai. A küldés a `kliens.svelte.ts`-é; ez az olvasás, az export és a törlés.

import { kerdez } from '../core/api';
import type { ExportEredmeny, Hasznalat, Statisztika, TorlesMit } from './tipusok';

const q = encodeURIComponent;

export const trackerApi = {
  statisztika: (tol: string, ig: string, bontas: 'nap' | 'het') =>
    kerdez<Statisztika>(`/api/tracker/statisztika?tol=${q(tol)}&ig=${q(ig)}&bontas=${bontas}`, { idokorlat: 10000 }),
  hasznalat: (tol: string, ig: string) => kerdez<Hasznalat>(`/api/tracker/hasznalat?tol=${q(tol)}&ig=${q(ig)}`, { idokorlat: 10000 }),
  exportal: (tol: string, ig: string, tevekenyseg: boolean) =>
    kerdez<ExportEredmeny>('/api/tracker/export', { metodus: 'POST', torzs: { tol, ig, tevekenyseg }, idokorlat: 15000 }),
  torol: (mit: TorlesMit) =>
    kerdez<{ torolt: number; tisztitva?: boolean }>('/api/tracker/torles', { metodus: 'POST', torzs: { mit }, idokorlat: 15000 }),
};
