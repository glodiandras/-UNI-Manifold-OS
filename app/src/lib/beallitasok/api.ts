import { kerdez } from '../core/api';
import type { BeallitasokValasz, BeallitasokValtozas } from './tipusok';
export const beallitasokApi = {
  betolt: () => kerdez<BeallitasokValasz>('/api/beallitasok'),
  ment: (rev: string, valtozas: BeallitasokValtozas) => kerdez<BeallitasokValasz>('/api/beallitasok', { metodus: 'PUT', torzs: { rev, valtozas } }),
};
