// A Bases core-hívásai (C12): két tiszta végpont, a core nem ír fájlt. A `.base` szövegét a `BazisForras` adja,
// az írás az egyetlen írási úton megy (fájlnál a `Dokumentum`, blokknál a befoglaló jegyzet tranzakciója).

import { kerdez } from '../lib/core/api';
import type { LekerdezOpciok, ModositValasz, Muvelet, Valasz } from './tipusok';

export interface BazisApi {
  lekerdez(szoveg: string, o?: LekerdezOpciok, jel?: AbortSignal): Promise<Valasz>;
  modosit(szoveg: string, muvelet: Muvelet): Promise<ModositValasz>;
}

export function bazisApi(alap = ''): BazisApi {
  return {
    lekerdez: (szoveg, o = {}) =>
      kerdez<Valasz>(`${alap}/api/vault/bazis/lekerdez`, {
        metodus: 'POST',
        torzs: { szoveg, ...o },
        idokorlat: 20000,
      }),
    modosit: (szoveg, muvelet) =>
      kerdez<ModositValasz>(`${alap}/api/vault/bazis/modosit`, {
        metodus: 'POST',
        torzs: { szoveg, muvelet },
        idokorlat: 8000,
      }),
  };
}
