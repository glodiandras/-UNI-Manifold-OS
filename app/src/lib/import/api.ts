import { kerdez } from '../core/api';
import type { ImportAllapot, ImportOpciok, IndulasValasz, MegszakitasValasz, ObsidianElonezet, V2Elonezet, V2Eredmeny, VisszaforditasEredmeny } from './tipusok';

/** Egy nagy vault bejárása és a Kukába tétel hosszabb ideig tarthat: a szokásosnál tágabb időkorlát. */
const HOSSZU = 300_000;

export const importApi = {
  obsidianElonezet: (forras: string, cel: string, opciok: ImportOpciok) =>
    kerdez<ObsidianElonezet>('/api/import/obsidian/elonezet', { metodus: 'POST', torzs: { forras, cel, opciok }, idokorlat: HOSSZU }),
  obsidianIndit: (forras: string, cel: string, opciok: ImportOpciok, terv_hash: string) =>
    kerdez<IndulasValasz>('/api/import/obsidian', { metodus: 'POST', torzs: { forras, cel, opciok, terv_hash }, idokorlat: HOSSZU }),
  v2Elonezet: (forras: string) => kerdez<V2Elonezet>('/api/import/v2/elonezet', { metodus: 'POST', torzs: { forras }, idokorlat: HOSSZU }),
  v2Indit: (forras: string, terv_hash: string) => kerdez<V2Eredmeny>('/api/import/v2', { metodus: 'POST', torzs: { forras, terv_hash }, idokorlat: HOSSZU }),
  lista: () => kerdez<{ importok: ImportAllapot[] }>('/api/import'),
  allapot: (id: string) => kerdez<ImportAllapot>(`/api/import/allapot?id=${encodeURIComponent(id)}`),
  megszakit: (id: string) => kerdez<MegszakitasValasz>('/api/import/megszakit', { metodus: 'POST', torzs: { id }, idokorlat: HOSSZU }),
  visszafordit: (id: string) => kerdez<VisszaforditasEredmeny>('/api/import/visszafordit', { metodus: 'POST', torzs: { id }, idokorlat: HOSSZU }),
};
