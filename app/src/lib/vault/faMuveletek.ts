// A fájlfa fájlműveletei (F11, 07-explorer-04/06/07): másolat, Finder, tömeges Kukába helyezés. Minden írás a core
// megerősített végpontjain megy (Kuka, másolat); a felület nem ír közvetlenül és nem old fel linket.

import { t } from '../i18n';
import { hibaUzenet, kerdez } from '../core/api';
import type { Felulet } from '../elrendezes/felulet.svelte';
import { ertesitesek } from '../ertesites/ertesites.svelte';
import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';
import type { VaultFajlok } from './fajlok.svelte';

/** „Make a copy”: a core `<név> N.<kit>` néven másolja a fájlt; sikerkor a másolat megnyílik és látszik a fában.
 *  A nyitott dokumentumok előbb mentődnek, hogy a másolat az utolsó szerkesztést tartalmazza. → a másolat útja. */
export async function masolatKeszit(felulet: Felulet, ut: string, fajlok?: Pick<VaultFajlok, 'frissit'>): Promise<string | null> {
  try {
    await szerkesztok.dokumentumok.mindLezar();
    const r = await kerdez<{ ut: string; figyelmeztetes?: string | null }>('/api/vault/masolat', { metodus: 'POST', torzs: { ut }, idokorlat: 120000 });
    await fajlok?.frissit();
    felulet.megmutatFaban(r.ut);
    felulet.munkaterulet.megnyit(r.ut, 'ujful');
    ertesitesek.ertesit({ szint: r.figyelmeztetes ? 'figyelmeztetes' : 'siker', cim: t('Másolat elkészült'), szoveg: r.figyelmeztetes ? `${r.ut} — ${r.figyelmeztetes}` : r.ut, idotartam: 4000 });
    return r.ut;
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A másolat nem készült el'), szoveg: hibaUzenet(e) });
    return null;
  }
}

/** „Megmutatás a Finderben”: a core a vaulton belüli útvonalat oldja fel, a megnyitást a rendszer végzi. */
export async function finderMegmutat(ut: string): Promise<boolean> {
  try {
    await kerdez('/api/vault/finder', { metodus: 'POST', torzs: { ut }, idokorlat: 15000 });
    return true;
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A Finder nem nyitható meg'), szoveg: hibaUzenet(e) });
    return false;
  }
}

export interface KukaEredmeny {
  /** A Kukába tett utak (a hiba előtt). */
  kesz: string[];
  /** Az első hiba üzenete; a hátralévő elemek érintetlenek maradnak. */
  hiba: string | null;
}

/** Elemek Kukába helyezése sorban, a macOS Kukájába (visszahozható, végleges törlés soha). Az első hiba megállítja a sort. */
export async function kukabaTesz(utak: readonly string[]): Promise<KukaEredmeny> {
  const kesz: string[] = [];
  try {
    await szerkesztok.dokumentumok.mindLezar();
    for (const ut of utak) {
      await kerdez('/api/vault/kuka', { metodus: 'POST', torzs: { ut, megerosit: true }, idokorlat: 60000 });
      kesz.push(ut);
    }
    return { kesz, hiba: null };
  } catch (e) {
    return { kesz, hiba: e instanceof Error ? e.message : String(e) };
  }
}
