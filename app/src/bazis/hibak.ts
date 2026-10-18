// A Bases-hibák és -figyelmeztetések szövege (10-bases-01): a core `kod` + `param` + angol tartalékot ad; a kliens a meglévő
// `hiba.<kod>` fordításon át (`kodUzenet`) mondja ki az aktív nyelven, a core angol mondata a tartalék.

import { kodUzenet } from '../lib/core/api';
import type { BazisHiba } from './tipusok';

export function hibaSzoveg(h: BazisHiba): string {
  return kodUzenet({ hiba: h.uzenet, kod: h.kod, param: h.param }, h.uzenet);
}
