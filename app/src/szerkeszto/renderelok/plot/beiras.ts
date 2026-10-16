// A „Grafikonok beírása ebbe a jegyzetbe” parancs (80(a), 80(h) szerint a grafikon csak gombra készül): a megnyitott jegyzet biztosan
// felismert képletei alá ```plot blokk kerül. A felület csak elindítja a meglévő `grafikon_beiras` feladatot (`POST /api/feladatok`,
// `utak: [jegyzet]`); a blokkot a core írja a gépi-írás szolgáltatáson át (egy jegyzet = egy gépi commit, visszavonható), a modell-ág
// és a D9 kapuk a core-ban élnek (a kézi út modell nélkül, a determinisztikus ágon fut). Mentetlen jegyzetet előbb mentünk (28(c)).

import { kerdez } from '../../../lib/core/api';
import { ertesitesek } from '../../../lib/ertesites/ertesites.svelte';
import type { Parancs } from '../../../lib/parancsok/regiszter';

export const GRAFIKON_PARANCS_ID = 'grafikon.beiras';

/** Tartalmi Markdown-jegyzet-e (a core `automatika.tartalmi_ut` tükre): nem gépi kísérőjegyzet, nem rejtett mappa. */
export function grafikonJegyzet(ut: string | null | undefined): ut is string {
  if (!ut || !ut.toLowerCase().endsWith('.md')) return false;
  const u = ut.normalize('NFC');
  // mirror of config — F3 replaces with /api/workspace
  return !u.startsWith('ATTCHMNTS - ') && !u.split('/').some((r) => r.startsWith('.'));
}

export async function grafikonokBeirasa(ut: string, mentes: () => Promise<void>, keres = kerdez): Promise<boolean> {
  try {
    await mentes();
    await keres('/api/feladatok', { metodus: 'POST', torzs: { tipus: 'grafikon_beiras', parameterek: { utak: [ut] } }, idokorlat: 10_000 });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: 'A grafikonok beírása nem indult el', szoveg: e instanceof Error ? e.message : String(e) });
    return false;
  }
  ertesitesek.ertesit({
    szint: 'info',
    cim: 'Grafikonok készülnek',
    szoveg: 'A jegyzet biztosan felismert képletei alá ```plot blokk kerül (gépi írás, visszavonható); a vezérlőben követhető (⌘⇧M).',
  });
  return true;
}

/** `aktiv`: a megnyitott jegyzet útja és mentése (vagy null). */
export function grafikonParancsok(aktiv: () => { ut: string; mentes: () => Promise<void> } | null): Parancs[] {
  return [
    {
      id: GRAFIKON_PARANCS_ID,
      nev: 'Grafikonok beírása ebbe a jegyzetbe',
      kategoria: 'Grafikon',
      elerheto: () => grafikonJegyzet(aktiv()?.ut),
      futtat: async () => {
        const a = aktiv();
        if (a && grafikonJegyzet(a.ut)) await grafikonokBeirasa(a.ut, a.mentes);
      },
    },
  ];
}
