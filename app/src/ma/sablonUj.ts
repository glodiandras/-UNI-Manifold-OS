// „Új jegyzet sablonból” (C32b, Javító 7): a `POST /api/sablon/uj` hívása és a séma-ellenőrzés kimenetelei. A sablon vázát a core
// szó szerint írja; ha a kiértékelt frontmatter sérti a vault sémáját (ismeretlen kulcs — köztük az `icon`/`cover` —, értékkészleten
// kívüli címke vagy Status, kulcssorrend), a core 409-et ad és nem hoz létre jegyzetet: a felület mutatja a sértéseket, és csak a
// „Mégis létrehozom” után küldi újra `megerosit: true`-val (64(b), 22(b)). A hiba szintű sértés (formai hiba, érvénytelen érték)
// megerősítéssel sem írható: 400, `megerositheto: false`.

import { ApiHiba, hibaSzoveg, kerdez } from '../lib/core/api';
import type { SemaProblema } from '../szerkeszto/tulajdonsagok/tipusok';

export interface UjSablonbolValasz {
  ut: string;
  kurzor: number | null;
  figyelmeztetes?: string | null;
}

export type UjSablonbolEredmeny =
  | { allapot: 'kesz'; valasz: UjSablonbolValasz }
  /** séma-sértés: megerősítéssel létrehozható */
  | { allapot: 'megerosit'; uzenet: string; problemak: SemaProblema[] }
  /** nem létrehozható (hiba szintű sértés, névütközés, hálózat…); a sértések, ha vannak, a `problemak`-ban */
  | { allapot: 'hiba'; uzenet: string; problemak: SemaProblema[] };

function problemak(adat: Record<string, unknown>): SemaProblema[] {
  const p = adat.problemak;
  return Array.isArray(p) ? (p as SemaProblema[]) : [];
}

/** Új jegyzet a sablonból; `megerosit`: a séma-sértések megerősítése (a második hívás). Nem dob: a kimenetel az `allapot`. */
export async function ujJegyzetSablonbolHiv(mappa: string, nev: string, sablon: string, megerosit = false): Promise<UjSablonbolEredmeny> {
  try {
    const valasz = await kerdez<UjSablonbolValasz>('/api/sablon/uj', {
      metodus: 'POST',
      torzs: { mappa, nev, sablon, ...(megerosit ? { megerosit: true } : {}) },
      idokorlat: 10000,
    });
    return { allapot: 'kesz', valasz };
  } catch (e) {
    if (e instanceof ApiHiba) {
      const p = problemak(e.adat);
      if (e.statusz === 409 && e.adat.sema_sertes === true && e.adat.megerositheto === true && p.length > 0) {
        return { allapot: 'megerosit', uzenet: e.message, problemak: p };
      }
      return { allapot: 'hiba', uzenet: e.message, problemak: e.adat.sema_sertes === true ? p : [] };
    }
    return { allapot: 'hiba', uzenet: hibaSzoveg(e), problemak: [] };
  }
}
