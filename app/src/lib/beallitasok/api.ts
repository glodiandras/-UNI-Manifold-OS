import { kerdez } from '../core/api';
import type { BeallitasokValasz, BeallitasokValtozas } from './tipusok';
export interface KizartElonezet { osszes: number; kizart: number; mintak: { minta: string; db: number; hiba: string | null }[] }
export const beallitasokApi = {
  betolt: () => kerdez<BeallitasokValasz>('/api/beallitasok'),
  /** A vázlat kizárási listája mintánként: érvényesség + találatok száma (nem ír). */
  kizartElonezet: (mintak: string[]) => kerdez<KizartElonezet>('/api/beallitasok/kizart-elonezet', { metodus: 'POST', torzs: { mintak } }),
  ment: (rev: string, valtozas: BeallitasokValtozas) => kerdez<BeallitasokValasz>('/api/beallitasok', { metodus: 'PUT', torzs: { rev, valtozas } }),
};
