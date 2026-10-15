// A naptár és az emlékeztetők (C29) értesítései a core WS-eseményeire. Csendes: egy esemény = legfeljebb egy rövid
// értesítés, a Ma oldal és a vezérlő saját újratöltése ettől független (az a saját store-jukban él).

import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { naptarApi } from '../lib/naptar/api';
import { utkozesErtesites, valtozasErtesites } from '../lib/naptar/megjelenites';
import type { NaptarValtozas } from '../lib/naptar/tipusok';

export interface ErtesitesCelok {
  /** egy jegyzet megnyitása új fülben */
  jegyzetNyit: (ut: string) => void;
  /** a Ma oldal megnyitása */
  maNyit: () => void;
  /** a vezérlő naptár-szakaszának megnyitása */
  vezerloNyit: () => void;
}

/** Az új naptárak, amelyeknél a kategóriát már jelentettük (az értesítés naptáranként egyszer jön). */
const bejelentett = new Set<string>();

export function bejelentettekTorol(): void {
  bejelentett.clear();
}

async function ujNaptarak(azonok: string[], celok: ErtesitesCelok): Promise<void> {
  let allapot;
  try {
    allapot = await naptarApi.allapot();
  } catch {
    return; // a vezérlő listája nem elérhető: nincs mit megerősíttetni, az értesítés elmarad
  }
  for (const n of allapot.naptarak) {
    if (!azonok.includes(n.azon) || n.kategoria_forras !== 'javaslat' || n.eltunt || bejelentett.has(n.azon)) continue;
    bejelentett.add(n.azon);
    ertesitesek.ertesit({
      szint: 'info',
      cim: `Új naptár: „${n.nev}”`,
      szoveg: 'A kategóriát a vezérlőben erősítheted meg.',
      muvelet: { nev: 'Vezérlő', futtat: celok.vezerloNyit },
    });
  }
}

/** Feliratkozás a naptár- és emlékeztető-eseményekre; a visszaadott függvény leiratkozik. */
export function naptarErtesitesek(k: CoreKapcsolat, celok: ErtesitesCelok): () => void {
  const le = [
    k.figyel('emlekezteto_utkozes', (e) => {
      const { cim, szoveg } = utkozesErtesites({
        fajta: String(e.fajta ?? ''),
        szoveg: typeof e.szoveg === 'string' ? e.szoveg : null,
        reszlet: typeof e.reszlet === 'string' ? e.reszlet : null,
      });
      const ut = typeof e.ut === 'string' && e.ut ? e.ut : null;
      ertesitesek.ertesit({
        szint: 'figyelmeztetes',
        cim,
        szoveg,
        ...(ut ? { muvelet: { nev: 'Megnyitás', futtat: () => celok.jegyzetNyit(ut) } } : {}),
      });
    }),
    k.figyel('naptar_valtozas', (e) => {
      const lista = (Array.isArray(e.valtozasok) ? e.valtozasok : []) as NaptarValtozas[];
      const ujak: string[] = [];
      for (const v of lista) {
        const r = valtozasErtesites(v);
        if (r) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: r.cim, szoveg: r.szoveg });
        else if (v.fajta === 'uj' && typeof v.azon === 'string') ujak.push(v.azon);
      }
      if (ujak.length) void ujNaptarak(ujak, celok);
    }),
    k.figyel('naptar_javaslat', (e) => {
      if (typeof e.uj === 'number' && e.uj > 0) {
        ertesitesek.ertesit({ szint: 'info', cim: 'Új tanulási blokk javaslat a Ma oldalon', muvelet: { nev: 'Ma', futtat: celok.maNyit } });
      }
    }),
  ];
  return () => le.forEach((f) => f());
}
