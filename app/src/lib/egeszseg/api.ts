import { kerdez } from '../core/api';
import type { DokuCel, EgeszsegJelentes, JavitasEredmeny } from './tipusok';

export const egeszsegApi = {
  betolt: () => kerdez<EgeszsegJelentes>('/api/egeszseg'),
  diagnosztika: (kod: string) => kerdez<{ verzio: 1; ellenorzesek: EgeszsegJelentes['ellenorzesek'] }>(`/api/egeszseg/diagnosztika?kod=${encodeURIComponent(kod)}`),
  /** A Learn more célja: az ellenőrzés kódjából `health.<kod>` téma. */
  tudjMeg: (kod: string) => kerdez<DokuCel>(`/api/doku/learn?tema=${encodeURIComponent(`health.${kod}`)}`),
  javit: (javitas: string) => kerdez<JavitasEredmeny>('/api/egeszseg/javitas', { metodus: 'POST', torzs: { javitas }, idokorlat: 120_000 }),
};
